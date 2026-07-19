from __future__ import annotations  
import yaml
from typing import List
import ollama
from langchain_core.embeddings import Embeddings
import numpy as np

##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
##% Local Embedder Class: Converts chunks into embeddings
##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
class LocalEmbedder(Embeddings):
    def __init__(self, config: dict):
        
        self.model = config['embedding']['model']
        print(f"--- Local Embedder Initialized: {self.model} ---")

    def embed_documents(self, texts: List[str]):
        """
        Embeds multiple documents. 
        """
        embeddings = []
        for text in texts:
            try:
                response = ollama.embeddings(model=self.model, prompt=text)
                embeddings.append(response['embedding'])
            except Exception as e:
                print(f"Error embedding text: {e}")
                raise e
        return np.array(embeddings)
        
    def embed_query(self, texts: str):
        """
        Embeds query. 
        """
        try:
            response = ollama.embeddings(model=self.model, prompt=texts)
            return np.array(response['embedding'])
        except Exception as e:
            print(f"Error embedding text: {e}")
            raise e
    
    async def embed_text(self, text):
        return self.embed_query(text).tolist()