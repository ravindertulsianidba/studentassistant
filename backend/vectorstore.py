"""Self-hostable vector store (Qdrant) for source-grounded semantic search.

Graceful by design: if QDRANT_URL is unset or Qdrant is unreachable, `enabled`
is False and the caller falls back to keyword search. Embeddings come from the
active AI provider (real OpenAI, or deterministic fixtures). This keeps the app
fully functional without a running vector DB while enabling true semantic
retrieval in production (docker-compose ships Qdrant).
"""
import logging

import config

logger = logging.getLogger("student-assistant")

try:
    from qdrant_client import AsyncQdrantClient
    from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
except Exception:  # pragma: no cover
    AsyncQdrantClient = None

_client = None
_ready = False


def enabled() -> bool:
    return bool(config.QDRANT_URL) and AsyncQdrantClient is not None


async def _get():
    global _client, _ready
    if not enabled():
        return None
    if _client is None:
        _client = AsyncQdrantClient(url=config.QDRANT_URL, timeout=5)
    if not _ready:
        try:
            existing = await _client.get_collections()
            names = {c.name for c in existing.collections}
            if config.QDRANT_COLLECTION not in names:
                await _client.create_collection(
                    collection_name=config.QDRANT_COLLECTION,
                    vectors_config=VectorParams(size=config.EMBED_DIM, distance=Distance.COSINE))
            _ready = True
        except Exception as e:
            logger.warning("Qdrant unavailable, falling back to keyword search: %s", e)
            return None
    return _client


async def upsert(chunk_id, user_id, vector, payload):
    cli = await _get()
    if not cli:
        return False
    try:
        await cli.upsert(collection_name=config.QDRANT_COLLECTION,
                         points=[PointStruct(id=chunk_id, vector=vector,
                                             payload={**payload, "user_id": user_id})])
        return True
    except Exception as e:
        logger.warning("Qdrant upsert failed: %s", e)
        return False


async def search(user_id, vector, limit=6):
    cli = await _get()
    if not cli:
        return None  # signal caller to use keyword fallback
    try:
        res = await cli.query_points(
            collection_name=config.QDRANT_COLLECTION, query=vector, limit=limit,
            query_filter=Filter(must=[FieldCondition(key="user_id", match=MatchValue(value=user_id))]))
        return [p.payload for p in res.points]
    except Exception as e:
        logger.warning("Qdrant search failed: %s", e)
        return None
