from evaluation.dataset_builder import RagasDatasetBuilder

def run_evaluation(config,all_root_nodes: list):
    builder = RagasDatasetBuilder(config)
    builder.run(all_root_nodes)

        
    