import os
import base64
from typing import List, Dict, Any, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

class KloudeksAPIError(Exception):
    """Exception raised for errors in the Kloudeks API calls."""
    pass

class KloudeksClient:
    """
    Base client for MIA Kloudeks API.
    Initializes the shared OpenAI client using the MIA base_url and API key.
    """
    def __init__(self, api_key: str = None, base_url: str = "https://mia.csp.kloudeks.com/v1"):
        self.api_key = api_key or os.getenv("MIA_API_KEY") or os.getenv("KLOUDEKS_API_KEY")
        self.base_url = base_url
        
        if not self.api_key:
            raise ValueError("MIA_API_KEY is required in .env")
            
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )


class QwenChatClient(KloudeksClient):
    """
    Client for Qwen3.8-27B model.
    Used for Q&A, summarization, text generation and image interpretation.
    """
    MODEL_ID = "kkbhackathon2026/Qwen3.8-27B"
    
    def chat(self, messages: List[Dict[str, Any]], temperature: float = 0.7) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.MODEL_ID,
                messages=messages,
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            raise KloudeksAPIError(f"QwenChatClient error: {str(e)}")

    def ask(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return self.chat(messages)


class QwenEmbeddingClient(KloudeksClient):
    """
    Client for Qwen3-Embedding-8B model.
    Used for semantic search and text vectors.
    """
    MODEL_ID = "kkbhackathon2026/Qwen3-Embedding-8B"
    
    def get_embedding(self, text: str) -> List[float]:
        try:
            response = self.client.embeddings.create(
                model=self.MODEL_ID,
                input=text,
                encoding_format="float",
            )
            return response.data[0].embedding
        except Exception as e:
            raise KloudeksAPIError(f"QwenEmbeddingClient error: {str(e)}")


class UnlimitedOCRClient(KloudeksClient):
    """
    Client for Unlimited-OCR model.
    """
    MODEL_ID = "kkbhackathon2026/Unlimited-OCR"
    
    def extract_text(self, image_paths: List[str]) -> str:
        if len(image_paths) > 3:
            raise ValueError("Unlimited-OCR accepts a maximum of 3 images.")
            
        content = []
        for path in image_paths:
            with open(path, "rb") as file:
                image_data = base64.b64encode(file.read()).decode("utf-8")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_data}"},
                })
        
        content.append({"type": "text", "text": "<image>\ndocument parsing"})
        window_size = 1024 if len(image_paths) > 1 else 128
        
        try:
            response = self.client.chat.completions.create(
                model=self.MODEL_ID,
                messages=[{
                    "role": "user",
                    "content": content,
                }],
                max_tokens=8192,
                temperature=0.0,
                extra_body={
                    "skip_special_tokens": False,
                    "vllm_xargs": {"ngram_size": 35, "window_size": window_size},
                },
            )
            return response.choices[0].message.content
        except Exception as e:
            raise KloudeksAPIError(f"UnlimitedOCRClient error: {str(e)}")
