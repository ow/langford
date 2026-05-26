import os
from typing import List, Optional

import numpy as np
from dotenv import load_dotenv

from pipeline.ai_provider import get_ai_config

load_dotenv()


class EmbeddingClient:
    """Provider-selectable embedding client.

    OpenAI is the schema-compatible default for this project because database
    embedding columns are halfvec(384). Gemini remains available only when an
    embedding provider/model is explicitly configured for it.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        provider, configured_model = get_ai_config("embedding")
        self.provider = os.environ.get("EMBEDDING_PROVIDER", provider).lower()
        self.model = model or os.environ.get("EMBEDDING_MODEL") or (
            "text-embedding-3-small"
            if self.provider == "openai"
            else configured_model
        )
        self.dimension = int(os.environ.get("EMBEDDING_DIMENSIONS", "384"))

        if self.provider == "openai":
            from openai import OpenAI

            self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
            if not self.api_key:
                raise ValueError("OPENAI_API_KEY not found in environment or provided.")
            self.client = OpenAI(api_key=self.api_key, max_retries=5)
            return

        from google import genai

        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment or provided.")
        self.client = genai.Client(api_key=self.api_key)

    def embed_text(
        self,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
        title: Optional[str] = None,
    ) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self.dimension

        try:
            if self.provider == "openai":
                response = self.client.embeddings.create(
                    model=self.model,
                    input=text,
                    dimensions=self.dimension,
                )
                return response.data[0].embedding

            config = {
                "task_type": task_type,
                "output_dimensionality": self.dimension,
            }
            if title:
                config["title"] = title
            response = self.client.models.embed_content(
                model=self.model,
                contents=text,
                config=config,
            )
            return response.embeddings[0].values
        except Exception as e:
            print(f"Error generating embedding: {e}")
            return [0.0] * self.dimension

    def embed_batch(
        self,
        texts: List[str],
        task_type: str = "RETRIEVAL_DOCUMENT",
        batch_size: int = 100,
    ) -> List[List[float]]:
        valid_texts = []
        valid_indices = []
        for idx, text in enumerate(texts):
            if text and text.strip():
                valid_texts.append(text)
                valid_indices.append(idx)

        if not valid_texts:
            return [[0.0] * self.dimension] * len(texts)

        all_embeddings = []
        for i in range(0, len(valid_texts), batch_size):
            chunk = valid_texts[i : i + batch_size]
            try:
                if self.provider == "openai":
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=chunk,
                        dimensions=self.dimension,
                    )
                    all_embeddings.extend([item.embedding for item in response.data])
                else:
                    response = self.client.models.embed_content(
                        model=self.model,
                        contents=chunk,
                        config={
                            "task_type": task_type,
                            "output_dimensionality": self.dimension,
                        },
                    )
                    all_embeddings.extend([emb.values for emb in response.embeddings])
            except Exception as e:
                print(f"Error in batch embedding chunk {i // batch_size}: {e}")
                all_embeddings.extend([[0.0] * self.dimension] * len(chunk))

        final_results = [[0.0] * self.dimension] * len(texts)
        for idx, embedding in zip(valid_indices, all_embeddings):
            final_results[idx] = embedding

        return final_results

    @staticmethod
    def cosine_similarity(v1: List[float], v2: List[float]) -> float:
        a = np.array(v1)
        b = np.array(v2)
        if np.all(a == 0) or np.all(b == 0):
            return 0.0
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def get_embedding_client() -> EmbeddingClient:
    return EmbeddingClient()
