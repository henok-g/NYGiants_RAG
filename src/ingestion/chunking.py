'''
src/ingesting/chunking.py
Takes the data from data/comments.jsonl and data/posts.jsonl
and chunks the data, stores into ***chunks.jsonl***, embed the chunk
and store it into a vector database

'''

from __future__ import annotations  
from ingestion.filters import load_corpus

##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
## Thread Tree Class: for traversing through reddit threads and returning chunks
##%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
class ThreadTree:
    def __init__(self,config:dict):
        self.config = config
    
    def createThreadTree(self):
                
        self.chunk_config = self.config['ingestion']['chunking']
        self.posts, self.comments = load_corpus(self.config)
        
        parent_to_child = {}
        for comment in self.comments:
            parent_id = comment['parent_id']
            if parent_id in parent_to_child:
                parent_to_child[parent_id].append(comment)
            else:
                parent_to_child[parent_id] = [comment]    
                
        def chunk(node, current_parent_context):
            item_type = node['item_type']
            node_id = node['id']
            
            # 1. Prepare the chunk text and identify the next context to pass down
            if item_type == 'post':
                title = node.get("title", "Missing Title")
                selftext = node.pop("selftext", "No Text")
                chunk_text = f"<title>{title}<parent>{current_parent_context} \
                    <node>{selftext}"
                id_prefix = "t3_"
                next_context = selftext
            elif item_type == 'comment':
                title = node.get("post_title", "No Title")
                body = node.pop('body', "No Text")
                chunk_text = f"<title>{title}<parent>{current_parent_context} \
                    <node>{body}"
                id_prefix = "t1_"
                next_context = body
            else:
                print(f"Wrong item type: {item_type}")
                return 
                
            # 2. Yield the current node as a flat object
            yield {
                'chunk_text': chunk_text, # Now a string, not a list
                'metadata': node,
            }
            
            # 3. Recurse to children
            pid = id_prefix + node_id
            if pid in parent_to_child:
                for child in parent_to_child[pid]:
                    # pass 'next_context' (the current body/text) 
                    # to the next level of recursion
                    yield from chunk(child, next_context)
        
        for post in self.posts:
            yield from chunk(post, "")
            

 
  
    
        
    