import os
import sys
from time import time
from tqdm import tqdm
from openai import OpenAI
from abc import ABC, abstractmethod
from typing import List, Dict, Any

import langchain_google_vertexai
sys.modules['langchain_community.chat_models.vertexai'] = langchain_google_vertexai

# Ragas imports
from ragas.llms import llm_factory
from ragas.llms import LangchainLLMWrapper
from ragas.embeddings import LangchainEmbeddingsWrapper

from ragas.testset import TestsetGenerator
from ragas.testset.graph import KnowledgeGraph, Node, NodeType
from ragas.testset.transforms import default_transforms_for_prechunked,apply_transforms
from ragas.testset.transforms.relationship_builders.traditional import JaccardSimilarityBuilder

# Ragas synthesizer classes
from ragas.testset.synthesizers import (
    SingleHopSpecificQuerySynthesizer,  
    MultiHopSpecificQuerySynthesizer,   
    MultiHopAbstractQuerySynthesizer    
)

# Local imports
from ingestion.chunking import ThreadTree
from ingestion.embedding import LocalEmbedder
from evaluation.build_eval_set.prototypes import PERSONAS,get_distribution
from evaluation.build_eval_set.island_builder import IslandClusterer
from evaluation.build_eval_set.throttled_local_llm import ThrottledLocalLLM

class RagasDatasetBuilder:
    def __init__(self,config):
        self.config = config
        self.build_from_scratch = config["evaluation"].get("build_from_scratch", True)
        self.test_set_path = config["evaluation"].get("test_set_path", "test_set.json")
        
        self.embedder = LocalEmbedder(self.config)
        llm_config = self.config['evaluation']['llm']
        self.client = OpenAI(base_url=llm_config['LOCAL_API_BASE'],api_key="not_needed")
        self.generator_llm = llm_factory(model=llm_config['MODEL_NAME'],
                                    client=self.client,
                                    max_tokens=16000,
                                    extra_body = {
                                        "options": {
                                            "num_predict": 8192,
                                            "num_ctx" : 16384,
                                            "temperature": 0.3
                                        }
                                    })
        
        self.clean_generator_llm = ThrottledLocalLLM(
            model_name=llm_config['MODEL_NAME'],
            base_url=llm_config['LOCAL_API_BASE']
        )
    def run(self, all_root_nodes: list):
        clusterer = IslandClusterer(self.config, self.client)
        islands = clusterer.cluster_into_islands(all_root_nodes)
        
        for i,island_nodes in enumerate(islands):
            kg_path = self.build_kg(island_nodes,i)    
            mode = self.config["evaluation"].get("mode","prototype")
            kg_path = os.path.join(self.test_set_path,"knowledge_graphs",mode,f"kg_{i}.json")
            out_path = os.path.join(self.test_set_path,"golden_datasets",mode,f"golden_dataset_{i}.json")
            self.generate_testset_from_kg(kg_path,out_path)
            
                
       
    def build_kg(self,island_nodes: list, island_idx: int)-> str: 
        mode = self.config["evaluation"].get("mode","prototype")

        # convert each island node into a graph node
        graph_nodes = []
        for root in tqdm(island_nodes):
            chunks = root['chunk_text']    
            metadata = root['metadata']
            # post_id = metadata['post_id'] if metadata['item_type'] != "post" else metadata['id']
            # comment_id = metadata['id']

            graph_nodes.append(Node(type=NodeType.CHUNK,properties={"page_content":chunks,"metadata":metadata}))

        kg = KnowledgeGraph(nodes=graph_nodes)
        transforms = default_transforms_for_prechunked(self.generator_llm,self.embedder)
        apply_transforms(kg,transforms)
        
        target_dir = os.path.join(self.test_set_path,"knowledge_graphs",mode)
        os.makedirs(target_dir, exist_ok=True)
        
        file_name = f"kg_{island_idx}.json"
        full_path = os.path.join(target_dir, file_name)
        
        kg.save(full_path)
        
        return full_path
        
    
    def generate_testset_from_kg(self, kg_path: str, output_filename: str):
        """
        Loads a specific KG and uses Ragas to generate the Gold Standard dataset.
        """
        print(f"--- GENERATING TEST SET FROM: {kg_path} ---")
        
        # Load the saved Knowledge Graph
        kg = KnowledgeGraph.load(kg_path)

        for node in kg.nodes:
            if "summary_embedding" in node.properties:
                del node.properties["summary_embedding"]
                
                
        # Initialize the Generator
        generator = TestsetGenerator(
            self.clean_generator_llm,
            LangchainEmbeddingsWrapper(self.embedder),
            knowledge_graph=kg,
            persona_list=list(PERSONAS.values()),
        )
        # generator = TestsetGenerator(
        #     LangchainLLMWrapper(self.generator_llm),
        #     LangchainEmbeddingsWrapper(self.embedder),
        #     knowledge_graph=kg,
        #     persona_list=list(PERSONAS.values()),
        # )
        # generator = TestsetGenerator.from_langchain(
        #     self.generator_llm, 
        #     self.embedder,
        #     knowledge_graph=kg,
        #     # persona_list=list(PERSONAS.values()),
        # )

        mapping = ["deep","breadth","bridge"]
        query_distribution = get_distribution(mapping[int(kg_path[-6])],self.clean_generator_llm)
        
        from ragas.run_config import RunConfig
        single_worker_config = RunConfig(
            max_workers=1,
            timeout=240,
        )
        
        # Generate the questions
        # 'distribution' allows control over how many questions are simple vs multi-hop/complex.
        # Since islands are already specialized, we can keep it balanced.
        testset = generator.generate(
            testset_size=10, # Number of questions per island
            query_distribution=query_distribution,
            run_config=single_worker_config,
        )

        # 4. Convert to a format easy to use (e.g., a Pandas DataFrame or JSON)
        df = testset.to_pandas()
        
        # 5. Save the Gold Standard
        df.to_json(output_filename, orient="records", indent=4)
        print(f"--- SUCCESS: Test set saved to {output_filename} ---")
        return df
    
     
    def build_kg_old(self):    
        chunky = ThreadTree(self.config)  
        embedder = LocalEmbedder(self.config)
        root_nodes = chunky.createThreadTree()     

        llm_config = self.config['evaluation']['llm']
        client = OpenAI(base_url=llm_config['LOCAL_API_BASE'],api_key="not_needed")
        generator_llm = llm_factory(model=llm_config['MODEL_NAME'],
                                    client=client,
                                    max_tokens=4096,
                                    extra_body = {
                                        "options": {
                                            "num_ctx" : 16384,
                                            "temperature": 0.3
                                        }
                                    })

        start_time = time()
        all_golden_entries = []
        visited = {}
        prechunked_docs = []
        counter = 0
        print("Let's process each chunk")
        for root in tqdm(root_nodes):
            chunks = root['chunk_text']    
            metadata = root['metadata']
            post_id = metadata['post_id'] if metadata['item_type'] != "post" else metadata['id']
            comment_id = metadata['id']
            visited[post_id] = visited.get(post_id, 0) + 1


            if visited[post_id] <= 10:
                prechunked_docs.append(Node(type=NodeType.CHUNK,properties={"page_content":chunks,"metadata":metadata}))
            else:
                break

            
        print(len(prechunked_docs))
        kg = KnowledgeGraph(nodes=prechunked_docs)
        transforms = default_transforms_for_prechunked(generator_llm,embedder)
        apply_transforms(kg,transforms)
        # print(kg)
        print(f"took: {time() - start_time} seconds")
        
        kg.save("kg1.json")
        
    
    
       