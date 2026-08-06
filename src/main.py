# The offline RAG Pipeline
import time
import yaml
import argparse


def load_config(path: str)->dict:
    with open(path) as f:
        return yaml.safe_load(f)
    
def main(config_path:str, query: str):
    config = load_config(config_path)
    pipeline = config["pipeline"]
    
    if pipeline["run_ingestion"]:
        from ingestion.pipeline import run_ingestion
        
        run_ingestion(config)
    
    if pipeline["run_retrieval"]:
        from retrieval.pipeline import run_retrieval
        
        run_retrieval(config)

    if pipeline["run_generation"]:
        from generation.pipeline import run_generation
        
        start = time.time()
        run_generation(config,query)
        # print(f"Elapsed time {time.time() - start}")
        
    if pipeline["run_evaluation"]:
        from ingestion.chunking import ThreadTree
        from evaluation.pipeline import run_evaluation

        prepared_chunks = ThreadTree(config=config)  
        root_nodes = list(prepared_chunks.createThreadTree())    
        run_evaluation(config,root_nodes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="configs/pipeline.yaml",
        help="Path to pipeline config file"
    )
    
    parser.add_argument(
        "--query", 
        default="who is jaxson dart?",
        help="Query into the RAG pipeline"
    )
    
    args = parser.parse_args()
    main(args.config, args.query)