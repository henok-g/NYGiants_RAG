import ollama
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from chunking import ThreadTree
import yaml
from tqdm import tqdm
from openai import OpenAI
import jsonlines,json 

# --- CONFIGURATION --- 
LOCAL_API_BASE = "http://localhost:8080"
MODEL_NAME = "gemma4"

OUTPUT_FILE = "golden_dataset.jsonl"
client = OpenAI(base_url=LOCAL_API_BASE,api_key="not_needed")

SYSTEM_PROMPT = """ You are an expert data annotator. Your goal is to create a 'Golden Dataset' for testing RAG retrieval.
You will be given a text chunk formatted as <title>...<parent>...<node>....
You must generate three distinct questions based on this text:
1. A 'Title-based' question (focusing on the high-level topic).
2. A 'Context-based' question (focusing on the relationship between parent and node).
3. A 'Direct' question (focusing on a specific fact in the node).

Each question must be semantically standalone. A user must be able to answer the question accurately without ever seeing the source text.

CONSTRAINTS:

    Semantic Independence: Every question must be self-contained. Replace all pronouns (it, this, they, etc.) with the actual names/entities from the text.
    No Personalities: Do not reference authors, users, or the social context of the text (e.g., avoid "What did the user say about..."). Focus strictly on the information.
    Question Type: Avoid Yes/No questions. Use Wh-questions (Who, What, Where, When, Why, How) to ensure meaningful retrieval testing.
    Answer Completeness: The ground_truth_answer must be a full, standalone factual statement.

Return ONLY a JSON object in this format:
{
"title_question": "...",
"context_question": "...",
"direct_question": "...",
"ground_truth_answer": "..."
}"""

def generate_questions(text_chunk):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Process this chunk: {text_chunk}"}
            ],
            response_format={"type": "json_object"}, # Only works if your local server supports it
            temperature=0.3 # Lower temperature for more consistent, factual questions
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"Error processing chunk: {e}")
        return None

# --- INTEGRATION TEST ---
if __name__ == "__main__":
    config_file = r"configs/pipeline.yaml"        
    chunky = ThreadTree(config_file=config_file)  
    root_nodes = chunky.createThreadTree()     



    all_golden_entries = []
    visited = {}
    for root in tqdm(root_nodes):
        chunks = root['chunk_text']    
        # print("Embedding chunks...")
        # print(chunks)
        # vectors = embedder.embed_plaintext(chunks)
        metadata = root['metadata']
        post_id = metadata['post_id'] if metadata['item_type'] != "post" else metadata['id']
        comment_id = metadata['id']
        visited[post_id] = visited.get(post_id, 0) + 1


        if visited[post_id] <= 3:
            qa_data = generate_questions(chunks)
            
            if qa_data:
                # Create the structured object
                entry = {
                        "post_id": post_id,
                        "comment_id": comment_id,
                        "original_chunk": chunks,
                        "title": qa_data.get("title_question"),
                        "context": qa_data.get("context_question"),
                        "direct": qa_data.get("direct_question"),
                        "answer": qa_data.get("ground_truth_answer")
                    
                }
                # Append to our master list
                # all_golden_entries.append(entry)
                with open(OUTPUT_FILE,"a", encoding="utf-8") as f:
                    f.write(json.dumps(entry) + "\n")
                    
        
    print("Done embedding all chunks")
         
