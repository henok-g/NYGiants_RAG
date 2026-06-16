'''
src/ingesting/chunking.py
Takes the data from data/comments.jsonl and data/posts.jsonl
and chunks the data, stores into ***chunks.jsonl***, embed the chunk
and store it into a vector database

Order of business:
1. Chunk text of data
2. figure out how to pass metadata 
'''

from __future__ import annotations  
import json
from filters import load_corpus
import yaml
import matplotlib.pyplot as plt
from typing import List, Optional, Dict, Any
        
class ThreadTree:
    def __init__(self,config_file:str):
        self.config_file = config_file
    
    def createThreadTree(self):
        with open(self.config_file, 'r') as file:
            config = yaml.safe_load(file)
        
        self.chunk_config = config['ingestion']['chunking']
        self.posts, self.comments = load_corpus(config)
        
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
                chunk_text = f"<title>{title}<parent>{current_parent_context}<node>{selftext}"
                id_prefix = "t3_"
                next_context = selftext
            elif item_type == 'comment':
                title = node.get("post_title", "No Title")
                body = node.pop('body', "No Text")
                chunk_text = f"<title>{title}<parent>{current_parent_context}<node>{body}"
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


if __name__ == "__main__":
    config_file = r"configs/pipeline.yaml"
    
    chunky = ThreadTree(config_file=config_file)  
    root_nodes = chunky.createThreadTree()     
    for root in root_nodes:
        print(root['chunk_text'])
        print(root['metadata']) 
        print()
    pass
    # with open(config_file, 'r') as file:
    #     config = yaml.safe_load(file) 
    
    # chunk_config = config['ingestion']['chunking']
    # # load in the filtered posts and comments     
    # posts,comments = load_corpus(config)
    
    # # posts -> comments
    # # Parent id -> children id
    
    # post_to_comment = {}
    # parent_to_child = {}
    
    # for comment in comments:
    #     comment_id  = comment['id']
    #     post_id     = comment['post_id']
    #     parent_id   = comment['parent_id']
        
        
    #     # map all post_ids to list of comments w/ that post_id
    #     if post_id in post_to_comment:
    #         post_to_comment[post_id].append(comment)
    #     else:
    #         post_to_comment[post_id] = [comment]
        
    #     # map all parent ids to children
    #     if parent_id in parent_to_child:
    #         parent_to_child[parent_id].append(comment)
    #     else:
    #         parent_to_child[parent_id] = [comment]    
            
    
    # # Now let's build out the tree using 
    # post_ids = ["t3_" + p['id'] for p in posts]
    
    # post_chunk_len = [len(p['title'] + p['selftext']) for p in posts]
    # comm_chunk_len = [len(c['body']) for c in comments]
    # plt.figure()
    # plt.boxplot(post_chunk_len)
    
    # plt.figure()
    # plt.boxplot(comm_chunk_len)
    
    # import numpy as np
    # post_weight = np.ones((len(post_chunk_len))) / len(post_chunk_len)
    # comm_weight = np.ones((len(comm_chunk_len))) / len(comm_chunk_len)
    
    # plt.figure()
    # plt.hist(post_chunk_len,weights=post_weight,alpha=.3)
    # plt.hist(comm_chunk_len,weights=comm_weight,alpha=.3)
    # plt.legend(["post","comment"])
    
    # pass

  
    
        
    