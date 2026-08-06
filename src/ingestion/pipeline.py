from __future__ import annotations  
import chromadb
from tqdm import tqdm
from ingestion.chunking import ThreadTree
from ingestion.embedding import LocalEmbedder

##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
##% Chunks corpus, creates embeddings and stores in vector db
##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
def run_ingestion(config: str):    
    prepared_chunks = ThreadTree(config=config)  
    embedder = LocalEmbedder(config=config)    
    root_nodes = prepared_chunks.createThreadTree()     

    # intialize ChromaDB (persistent)
    client = chromadb.PersistentClient(path="./chroma_db2")
    collection = client.get_or_create_collection(name="NY_Giants_Reddit")
    
    for root in tqdm(root_nodes):
        text = [root['chunk_text']]
        metadata = root['metadata']
        
        metadata['distinguished'] = metadata.get('distinguished') or ""  
        doc_id = str(metadata.get("id"))
        
        try:
            vectors = embedder.embed_documents(text)
            collection.add(
                ids=[doc_id],
                embeddings=vectors,
                documents=text,
                metadatas=[metadata]
            )
            
        except Exception as e:
            print(f"Failed to process chunk {doc_id} {e}")
            continue

    print("Done embedding all chunks")
    
