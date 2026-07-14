"""Lightweight RAG for the AI assistant.

Course material (lesson text) is indexed into ``KnowledgeChunk`` rows with an
embedding (see the ``build_ai_knowledge`` management command). At chat time we
embed the user's question, find the most similar chunks by cosine similarity,
and inject them into the prompt so answers are grounded in the platform's own
lessons. Everything degrades gracefully: no API key or empty index -> no RAG,
and the chat keeps working normally.
"""
import json
import math

from django.db.models import Q

from .models import KnowledgeChunk

EMBED_MODEL = 'text-embedding-3-small'
RAG_TOP_K = 4
RAG_MIN_SCORE = 0.30  # cosine floor for a chunk to count as relevant


def _client():
    # Lazy import to avoid a circular import with views.py.
    from .views import get_openai_client
    return get_openai_client()


def embed_texts(texts):
    """Embed a list of strings. Returns list[list[float]] or None on failure."""
    if not texts:
        return []
    client = _client()
    if not client:
        return None
    try:
        resp = client.embeddings.create(model=EMBED_MODEL, input=texts)
        return [item.embedding for item in resp.data]
    except Exception as e:
        print(f"RAG embedding error: {e}")
        return None


def embed_text(text):
    result = embed_texts([text])
    return result[0] if result else None


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def has_knowledge():
    """True if there is at least one embedded chunk (cheap existence check)."""
    return KnowledgeChunk.objects.exclude(embedding='').exists()


def retrieve(query, profession_id=None, k=RAG_TOP_K, min_score=RAG_MIN_SCORE):
    """Return the top-k most relevant chunks for a query (empty list if none)."""
    query = (query or '').strip()
    if not query or not has_knowledge():
        return []

    qvec = embed_text(query)
    if not qvec:
        return []

    qs = KnowledgeChunk.objects.exclude(embedding='')
    if profession_id:
        qs = qs.filter(Q(profession_id=profession_id) | Q(profession_id__isnull=True))

    scored = []
    for chunk in qs.only('id', 'title', 'content', 'embedding'):
        try:
            vec = json.loads(chunk.embedding)
        except (ValueError, TypeError):
            continue
        score = _cosine(qvec, vec)
        if score >= min_score:
            scored.append((score, chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [chunk for _score, chunk in scored[:k]]


def build_context(chunks, max_chars=3500):
    """Format retrieved chunks into a compact context block for the prompt."""
    if not chunks:
        return ''
    parts = []
    used = 0
    for chunk in chunks:
        prefix = (chunk.title.strip() + ': ') if chunk.title else ''
        piece = '- ' + prefix + chunk.content.strip()
        if used + len(piece) > max_chars:
            break
        parts.append(piece)
        used += len(piece)
    return '\n\n'.join(parts)
