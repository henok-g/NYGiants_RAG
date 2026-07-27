import chromadb
import ollama
import json

class RetrievalEvaluator:
    def __init__(self, config):
        self.K = 5
        self.config         = config
        self.db_path        = config['embedding']['chroma_dir']
        self.client         = chromadb.PersistentClient(path=self.db_path)
        self.collection     = self.client.get_collection(name="NY_Giants_Reddit")
        self.embed_model    = config['embedding']['model']

        
    def get_embedding(self, text):
        response = ollama.embeddings(model=self.embed_model, prompt = text)
        return response['embedding']
    
    def run_diagnostic(self, dataset):
        report = {
            "single_hop_specific" : {"hits": 0, "total": 0, "mrr": 0},
            "multi_hop_specific"  : {"hits": 0, "total": 0, "mrr": 0},
            "multi_hop_abstract"  : {"hits": 0, "total": 0, "mrr": 0}
        }
        
        print("Starting Retrieval Diagnostics")
        
        for entry in dataset:
            query = entry["user_input"]
            mode = self._map_mode(entry["synthesizer_name"])
            gold_contexts = entry["reference_contexts"]
            
            # generate embedding
            query_embedding = self.get_embedding(query)
            
            # perform vector search in chroma 
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=self.K
            )
            
            # analyze the results
            retrieved_documents = results['documents'][0]
            found_gold_indices = []
            
            for i,doc in enumerate(retrieved_documents):
                for gold in gold_contexts:
                    clean_gold = gold.split('>')[-1].strip()
                    if clean_gold in doc or doc in clean_gold:
                        found_gold_indices.append(i+1)
                        
            # Update Report
            report[mode]["total"] += 1
            if found_gold_indices:
                report[mode]["hits"] += 1
                # Compute MRR ( 1 / rank of the first correct hit )
                report[mode]["mrr"] += (1.0 / found_gold_indices[0])
                
            # Logging for visibility
            status = "✅ HIT" if found_gold_indices else "❌ MISS"
            print(f"[{mode.upper()}] {status} | Query: {query[:60]}...")
            if not found_gold_indices:
                print(f"   [Expected]: {gold_contexts[0][:60]}...")
                print(f"   [Retrieved]: {retrieved_documents[0][:60]}...")
                
        self._print_final_report(report)
            
            
    def _print_final_report(self, report):
        print("\n" + "="*40)
        print("      FINAL RETRIEVAL HEALTH REPORT")
        print("="*40)
        for mode, stats in report.items():
            print(f"\n{mode.replace('_', ' ').upper()}:")
            if stats["total"] > 0:
                hit_rate = (stats["hits"] / stats["total"]) * 100
                mrr = stats["mrr"] / stats["total"]
                print(f"  - Hit Rate: {hit_rate:.2f}% ({stats['hits']}/{stats['total']})")
                print(f"  - MRR:      {mrr:.4f}")
            else:
                print("  - No data available for this mode.")
        print("="*40)
        
    def _map_mode(self, synth_name):
        if "single_hop" in synth_name: return "single_hop_specific"
        if "multi_hop_specific" in synth_name: return "multi_hop_specific"
        if "multi_hop_abstract" in synth_name: return "multi_hop_abstract"
        return "unknown"