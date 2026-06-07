import yaml
import argparse
from src.ingestion.chunker import run_ingestion
from src.retrieval.retriever import run_retrieval
from src.generation.chain import run_generation
from src.evaluation.ragas_eval import run_evaluation

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
        run_evaluation(config)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        default="configs/pipeline.yaml",
        help="Path to pipeline config file"
    )
    args = parser.parse_args()
    main(args.config)