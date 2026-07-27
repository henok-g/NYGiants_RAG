from collections import defaultdict
from ingestion.embedding import LocalEmbedder

class IslandClusterer:
    def __init__(self, config: dict, client):
        self.config = config
        self.mode = config["evaluation"].get("mode","prototype")
        self.client = client

    def cluster_into_islands(self, all_root_nodes: list) -> list[list]:
        """
        Groups nodes into logical islands.
        
        Args:
            all_root_nodes: The list of all nodes from your ThreadTree.
            mode: 'prototype' (3 specific profiles) or 'production' (many balanced islands).
        """
        # 1. Organize all nodes by their post_id (Thread ID)
        # This ensures an island never "leaks" into another topic.
        threads = defaultdict(list)
        for node in all_root_nodes:
            post_id = node['metadata'].get('post_id') or node['metadata'].get('id')
            threads[post_id].append(node)

        if self.mode == "prototype":
            return self._get_prototype_islands(threads)
        else:
            return self._get_production_islands(threads)

    def _get_prototype_islands(self, threads: dict) -> list[list]:
        """
        Creates exactly 3 highly specialized islands for testing.
        """
        islands = []
        thread_ids = list(threads.keys())

        # --- Island 1: The Deep Dive (Vertical Depth) ---
        # Pick the single largest thread to test multi-hop reasoning.
        deepest_thread_id = max(threads, key=lambda k: len(threads[k]))
        islands.append(threads[deepest_thread_id][:50])
        print(f"Island 1 (Deep) created with {len(threads[deepest_thread_id])} nodes.")

        # --- Island 2: The Broad Sweep (REFACTORED) ---
        # Goal: Pick 5 diverse threads that are NOT junk.
        # Filter out threads that are too small to be meaningful
        # Adjust 'MIN_CHARS' based on your data (e.g., 100-200 is a good start)
        MIN_CHARS = 600 
        
        meaningful_thread_ids = []
        for tid in thread_ids:
            # Calculate total characters in the thread
            total_chars = sum(len(node['chunk_text']) for node in threads[tid])
            
            if total_chars >= MIN_CHARS:
                meaningful_thread_ids.append(tid)

        # If we didn't find enough meaningful threads, fallback to all threads
        if len(meaningful_thread_ids) < 5:
            print("Warning: Not enough meaningful threads found. Falling back to all threads.")
            target_ids = thread_ids
        else:
            target_ids = meaningful_thread_ids

        # Now sort the *meaningful* threads by size (ascending) 
        # so we get the "Smallest but meaningful" threads for breadth.
        sorted_meaningful_ids = sorted(target_ids, key=lambda k: len(threads[k]))
        
        # Take the first 5
        breadth_threads = sorted_meaningful_ids[:25]
        breadth_nodes = []
        for tid in breadth_threads:
            breadth_nodes.extend(threads[tid])
            
        islands.append(breadth_nodes[:25])
        print(f"Island 2 (Breadth) created with {len(breadth_nodes)} nodes from {len(breadth_threads)} meaningful threads.")

         # --- Island 3: The Bridge Island (Using ChromaDB) ---
        print("Creating Island 3 via ChromaDB Retrieval...")
        bridge_nodes = []
        
        try:
            # Pick a random seed thread
            import random
            seed_id = random.choice(thread_ids)
            seed_nodes = threads[seed_id]
            
            # Use a chunk from the seed to query Chroma
            query_text = seed_nodes[0]['chunk_text']
            
            # Query ChromaDB for the top K most similar chunks
            import chromadb
            chroma_client =  chromadb.PersistentClient(path="./chroma_db")
            collection = chroma_client.get_collection(name="NY_Giants_Reddit")
            embedder = LocalEmbedder(self.config)
            query_vector  = embedder.embed_documents(query_text)
            results = collection.query(
                query_embeddings= query_vector.tolist(),
                n_results=30
            )

            # Find which metadata/post_ids these results belong to
            # We want to find a post_id that is NOT our seed_id
            neighbor_post_ids = []
            for i in range(len(results['metadatas'][0])):
                meta = results['metadatas'][0][i]
                pid = meta.get('post_id') or meta.get('id')
                if pid and pid != seed_id:
                    neighbor_post_ids.append(pid)

            # If we found a different post, we have a Bridge!
            if neighbor_post_ids:
                # Start with the seed nodes limit to K
                bridge_nodes.extend(seed_nodes[:5])
                
                # Get unique neighbor IDs (excluding the seed itself)
                unique_neighbors = set(pid for pid in neighbor_post_ids if pid != seed_id)
                
                # Iterate through each unique neighbor and grab up to 5 nodes
                for target_pid in unique_neighbors:
                    if target_pid in threads:
                        # Take up to the first 5 nodes from this specific thread
                        neighbor_subset = threads[target_pid][:2]
                        bridge_nodes.extend(neighbor_subset)
                        print(f"  -> Bridged neighbor {target_pid} ({len(neighbor_subset)} nodes)")
                
                # 4. Finalize the island
                islands.append(bridge_nodes[-14:])
                print(f"Island 3 (Bridge) successfully bridged {seed_id} with {len(unique_neighbors)} neighbors.")
            else:
                # Fallback: If no different post found, just take the seed
                bridge_nodes = seed_nodes
                print("Island 3 (Bridge) fallback: No distinct neighbor found in Chroma.")

        except Exception as e:
            print(f"Bridge Island error: {e}")
            bridge_nodes = threads[thread_ids[0]]


        return islands

    def _get_production_islands(self, threads: dict) -> list[list]:
        """
        Scalable strategy: Divide all threads into N equal-sized islands.
        """
        num_islands = self.config["evaluation"]["num_islands"]
        all_nodes = []
        for nodes in threads.values():
            all_nodes.extend(nodes)
            
        # Split the total node list into N chunks
        chunk_size = len(all_nodes) // num_islands
        return [all_nodes[i:i + chunk_size] for i in range(0, len(all_nodes), chunk_size)]
    
    
class AdversarialCorruptor:
    def __init__(self, client, model_name):
        self.client = client
        self.model = model_name

    def inject_noise(self, clean_nodes: list, noise_type: str) -> list:
        """
        Takes a list of clean nodes and returns a 'corrupted' version.
        """
        corrupted_nodes = [node.copy() for node in clean_nodes] # Start with a copy

        if noise_type == "semantic_hallucination":
            return self._add_semantic_lies(corrupted_nodes)
        
        elif noise_type == "structural_chaos":
            return self._break_hierarchy(corrupted_nodes)
        
        elif noise_type == "syntactic_mess":
            return self._add_slang_and_typos(corrupted_nodes)
            
        return corrupted_nodes

    def _add_semantic_lies(self, nodes):
        """Uses LLM to insert a 'fake' but convincing comment into the thread."""
        # 1. Pick a random node in the thread
        # 2. Ask LLM: "Write a comment that sounds like it belongs here but 
        #    contains a factually incorrect statement about [Topic]."
        # 3. Insert it into the list.
        return nodes

    def _break_hierarchy(self, nodes):
        """Uses LLM to mess up the parent_id mapping."""
        # 1. Pick a comment.
        # 2. Change its parent_id to a random, non-existent ID.
        # 3. This tests if your TreeRetriever crashes or gets lost.
        return nodes

    def _add_slang_and_typos(self, nodes):
        """Uses LLM to rewrite comments into 'Internet Speak'."""
        # 1. Pick a node.
        # 2. Ask LLM: "Rewrite this comment using heavy slang, typos, and emojis."
        # 3. Replace the text.
        return nodes