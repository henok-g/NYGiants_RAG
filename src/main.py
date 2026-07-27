import yaml
import argparse
from ingestion.pipeline import run_ingestion
from ingestion.chunking import ThreadTree
from retrieval.pipeline import run_retrieval
from generation.pipeline import run_generation
from evaluation.pipeline import run_evaluation

def load_config(path: str)->dict:
    with open(path) as f:
        return yaml.safe_load(f)
    
def main(config_path:str):
    config = load_config(config_path)
    pipeline = config["pipeline"]
    
    if pipeline["run_ingestion"]:
        run_ingestion(config)
    
    if pipeline["run_retrieval"]:
        run_retrieval(config)

    if pipeline["run_generation"]:
        run_generation(config)

    if pipeline["run_evaluation"]:
        
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
    args = parser.parse_args()
    main(args.config)