import yaml
from pathlib import Path

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

class RagGenerator:
    def __init__(self, config):
        self.config = config
        llm_config = self.config['evaluation']['llm']
        self.llm = ChatOpenAI(base_url=llm_config['LOCAL_API_BASE'],api_key="not_needed")


    def load_prompt(self, prompt_name: str) -> ChatPromptTemplate:
        """Load the prompt from prompts dir"""
        prompt_path = Path(__file__).parent.parent / "prompts" / f"{prompt_name}.yaml"
        
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
        
        with open(prompt_path, "r") as f:
            prompt_data = yaml.safe_load(f)
            
        return ChatPromptTemplate.from_messages([
            ("system", prompt_data["system_message"]),
            ("user", prompt_data["user_template"])
        ])

    def generate(self, question: str, context_list: list) -> str:
        """
        Takes the question and the list of retrieved documents and produces an answer.
        """
        # 1. Load the generator prompt
        prompt_template = self.load_prompt("generator")
        
        # 2. Prepare the context string
        # We join the list of document strings into one large block of text
        context_str = "\n\n".join(context_list)
        
        # 3. Build the chain
        chain = prompt_template | self.llm | StrOutputParser()
        
        # 4. Invoke the LLM
        # We pass both the context and the original question
        response = chain.invoke({
            "context": context_str,
            "question": question
        })
        
        return response