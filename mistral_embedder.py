"""
Mistral API embedding adapter — drop-in replacement for EmbeddingProcessor.
Same interface, no torch required.
"""

import os
import time
import logging
import requests
from typing import List

logger = logging.getLogger(__name__)

class MistralEmbedder:
    def __init__(self):
        self.api_key = os.environ.get("MISTRAL_API_KEY")
        self.model = os.environ.get("EMBEDDING_MODEL_NAME", "mistral-embed")
        self.vector_size = int(os.environ.get("EMBEDDING_VECTOR_SIZE", 1024))
        self.url = "https://api.mistral.ai/v1/embeddings"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _call_api(self, texts: List[str]) -> List[List[float]]:
        response = requests.post(self.url, headers=self.headers, json={
            "model": self.model,
            "input": texts
        })
        response.raise_for_status()
        data = response.json()
        return [item["embedding"] for item in data["data"]]

    def get_embedding(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self.vector_size
        try:
            return self._call_api([text])[0]
        except Exception as e:
            logger.error(f"Mistral embedding error: {e}")
            return [0.0] * self.vector_size

    def get_batch_embeddings(self, texts: List[str], batch_size: int = 8) -> List[List[float]]:
        results = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            try:
                results.extend(self._call_api(batch))
            except Exception as e:
                logger.error(f"Mistral batch error: {e}")
                results.extend([[0.0] * self.vector_size] * len(batch))
            time.sleep(1.0)  # 1 RPS free tier
        return results

    def unload_model(self):
        pass  # no-op, API client needs no cleanup