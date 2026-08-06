import yaml
import chromadb
from openai import OpenAI
from pathlib import Path

from langchain_openai import ChatOpenAI
from ingestion.embedding import LocalEmbedder
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

class RagRetriever:
    def __init__(self, config):
        self.config = config         
           
        chroma_client =  chromadb.PersistentClient(path="./chroma_db")
        self.collection = chroma_client.get_collection(name="NY_Giants_Reddit")
        
        self.embedder = LocalEmbedder(self.config)
        
        llm_config = self.config['evaluation']['llm']
        self.llm = ChatOpenAI(base_url=llm_config['LOCAL_API_BASE'],api_key="not_needed")
            
    def load_prompt(self, prompt_name: str) -> ChatPromptTemplate:
        '''Load the prompt from prompts dir'''
        prompt_path = Path(__file__).parent.parent / "prompts" / f"{prompt_name}.yaml"
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        
        with open(prompt_path,"r") as f:
            prompt_data = yaml.safe_load(f)
            
        return ChatPromptTemplate.from_messages([
            ("system", prompt_data["system_message"]),
            ("user", prompt_data["user_template"])
        ])
        
    
    def transform_query(self, query: str) -> str:
        prompt_template = self.load_prompt("query_transformer")
        chain = prompt_template | self.llm | StrOutputParser()
        refined_query = chain.invoke({"question":query})
        return refined_query.strip()
    
    def retrieve(self, query: str)->list:
        optimized_query = self.transform_query(query)
        query_embedding = self.embedder.embed_query(optimized_query)
        
        # search the vector database
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=5
        )
        
        return results['documents'][0]
    
    def hybrid_search(self, query: str) -> list:
        pass
    
    def reranker(self) -> list:
        pass