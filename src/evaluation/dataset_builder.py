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
from ragas.embeddings import embedding_factory
from ragas.testset.graph import KnowledgeGraph, Node, NodeType
from ragas.testset.transforms import default_transforms_for_prechunked,apply_transforms
from ragas.testset.transforms.relationship_builders.traditional import JaccardSimilarityBuilder

# Local imports
from ingestion.chunking import ThreadTree
from ingestion.embedding import LocalEmbedder
from evaluation.island_builder import IslandClusterer


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
                                    max_tokens=4096,
                                    extra_body = {
                                        "options": {
                                            "num_ctx" : 16384,
                                            "temperature": 0.3
                                        }
                                    })
        
    def run(self, all_root_nodes: list):
        if not self.build_from_scratch and os.path.exists(self.test_set_path):
            print(f"--- LOADING EXISTING TEST SET FROM {self.test_set_path} ---")
            return self._load_existing_test_set() # TODO: implement the load logic
        else:
            clusterer = IslandClusterer(self.config, self.client)
            islands = clusterer.cluster_into_islands(all_root_nodes)
            
            for i,island_nodes in enumerate(islands):
                self.build_kg(island_nodes,i)
        
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
        
        target_dir = os.path.join(self.test_set_path,mode)
        os.makedirs(target_dir, exist_ok=True)
        
        file_name = f"kg_{island_idx}.json"
        full_path = os.path.join(target_dir, file_name)
        
        kg.save(full_path)
        
        
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
        
    
    
       