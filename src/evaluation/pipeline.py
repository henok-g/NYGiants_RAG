import os
import glob
import json
from evaluation.build_eval_set.dataset_builder import RagasDatasetBuilder
from evaluation.run_diagnostics import RetrievalEvaluator

def run_evaluation(config,all_root_nodes: list):
    mode                = config['evaluation']['mode']
    test_set_path       = config['evaluation']['test_set_path']
    build_from_scratch  = config['evaluation']['build_from_scratch']
    
    if build_from_scratch:
        builder = RagasDatasetBuilder(config)
        builder.run(all_root_nodes)
    
    if mode == 'prototype':
        golden_datasets = glob.glob(os.path.join(test_set_path,"golden_datasets",mode,"*.json"))
        evaluator = RetrievalEvaluator(config)
        for dataset_path in golden_datasets:
            with open(dataset_path,'r') as f:
                dataset = json.load(f)
                
            evaluator.run_diagnostic(dataset)
        
    

        
    