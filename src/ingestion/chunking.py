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

class ThreadNode:
    def __init__(
        self,
        node_id: str,
        node_type: str,
        metadata: Dict[str, Any],
        chunks: List[str],
        children: Optional[List[ThreadNode]] = None
    ):
        self.node_id = node_id
        self.node_type = node_type
        self.metadata = metadata
        self.chunks = chunks
        self.children = children if children is not None else []
                
class ThreadTree:
    def __init__(self,config_file:str, root_nodes: Optional[List[ThreadNode]] = None):
        self.config_file = config_file
        self.root_nodes = root_nodes if root_nodes is not None else self.createThreadTree()

    
    def createThreadTree(self):
        with open(self.config_file, 'r') as file:
            config = yaml.safe_load(file)
        
        self.chunk_config = config['ingestion']['chunking']
        self.posts,self.comments = load_corpus(config)
        
        parent_to_child = {}
        for comment in self.comments:
            parent_id   = comment['parent_id']
            
            # map all parent ids to children
            if parent_id in parent_to_child:
                parent_to_child[parent_id].append(comment)
            else:
                parent_to_child[parent_id] = [comment]    
                
        def chunk(node,parent_chunk):
            item_type = node['item_type']
            id = node['id'] # post/comment id
            
            # handle different chunking rules depending on the item type
            if item_type == 'post':
                title = node.pop("title","Missing Title")
                selftext = node.pop("selftext","No Text")
                chunks = ["<parent>" + parent_chunk + "<node>" + title + selftext] #  TODO: break up chunks based on chunking rules later
                id_prefix = "t3_"
                parent_chunk = title + selftext
            elif item_type == 'comment':
                body = node.pop('body', "No Text") # TODO: actually chunk this 
                chunks = ["<parent>" + parent_chunk + "<node>" + body]
                id_prefix = "t1_"
                parent_chunk = body
            else:
                print(f"Wrong item type: {item_type}")
                
            pid = id_prefix + id
            children = []
            if pid in parent_to_child:
                for child in parent_to_child[pid]:
                    children.append(chunk(child, parent_chunk))
            root = ThreadNode(id,item_type,node,chunks,children)
            return root
        
        root_nodes = [chunk(p,"") for p in self.posts]
        return root_nodes
            
            
                

        
if __name__ == "__main__":
    config_file = r"configs/pipeline.yaml"
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

    chunky = ThreadTree(config_file=config_file)  
    root_nodes = chunky.createThreadTree()      
    pass
    
        
    