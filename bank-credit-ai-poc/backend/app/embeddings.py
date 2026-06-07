import hashlib
import math
import re

from openai import OpenAI

from app.config import get_settings

EMBEDDING_DIMENSION = 1536


def _local_hash_embedding(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIMENSION
    tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
    if not tokens:
        tokens = [text.lower() or "empty"]

    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMENSION
        sign = -1.0 if digest[4] & 1 else 1.0
        weight = 1.0 + min(len(token), 24) / 24
        vector[index] += sign * weight

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [value / norm for value in vector]


def create_embedding(text: str) -> list[float]:
    settings = get_settings()
    if not settings.openai_api_key:
        return _local_hash_embedding(text)

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(model=settings.embedding_model, input=text)
    return response.data[0].embedding
