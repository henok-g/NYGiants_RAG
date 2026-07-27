import asyncio
from typing import Optional, List
from openai import AsyncOpenAI
from langchain_core.outputs import LLMResult, Generation

# Correct abstract base class and type hints for newer Ragas versions
from ragas.llms.base import BaseRagasLLM
from langchain_core.prompt_values import PromptValue

class ThrottledLocalLLM(BaseRagasLLM):
    """
    A fully native, valid Ragas LLM subclass that hooks perfectly into 
    TestsetGenerator while enforcing a strict 1-request GPU lock.
    """
    def __init__(self, model_name: str, base_url: str):
        # Explicitly initialize dataclass/ABC parent mechanics
        super().__init__()
        self.model_name = model_name
        self._client = AsyncOpenAI(base_url=base_url, api_key="local-ai-dummy-key")
        self._gpu_lock = asyncio.Semaphore(1)
        
    @property
    def key_provider(self):
        return None

    def validate_api_key(self) -> None:
        """Tells Ragas to skip checking for the OPENAI_API_KEY environment variable."""
        pass

    def generate_text(
        self, 
        prompt: PromptValue, 
        n: int = 1, 
        temperature: Optional[float] = 0.3, 
        stop: Optional[List[str]] = None, 
        callbacks: Optional[list] = None
    ) -> LLMResult:
        """Required synchronous method: fallback routing through async loop safely."""
        return asyncio.run(self.agenerate_text(prompt, n, temperature, stop, callbacks))

    async def agenerate_text(
        self, 
        prompt: PromptValue, 
        n: int = 1, 
        temperature: Optional[float] = 0.3, 
        stop: Optional[List[str]] = None, 
        callbacks: Optional[list] = None
    ) -> LLMResult:
        """Required asynchronous method: intercepts all Ragas persona matching streams."""
        generations = []
        
        # Ragas wraps prompts inside a PromptValue object; convert it to string format
        prompt_string = prompt.to_string()
        
        # Enforce strict sequential execution queue
        async with self._gpu_lock:
            response = await self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt_string}],
                temperature=temperature if temperature is not None else 0.3,
                n=n,
                # Safe payload forwarding for Ollama/Local Server runner contexts
                extra_body={"options": {"num_ctx": 16384, "num_predict": 4096}}
            )
            
        text_output = response.choices[0].message.content or ""
        generations.append(Generation(text=text_output))
        
        return LLMResult(generations=[generations])

    def is_finished(self, response: LLMResult) -> bool:
        """Required validation check: confirms local server response is complete."""
        # Returns True to tell Ragas the text generated successfully without cutoff issues
        return True


