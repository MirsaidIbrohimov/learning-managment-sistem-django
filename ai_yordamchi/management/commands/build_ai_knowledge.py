"""Build the AI assistant's knowledge base from lesson content.

Usage:
    python manage.py build_ai_knowledge            # index new/changed lessons
    python manage.py build_ai_knowledge --rebuild  # wipe and rebuild from scratch

Requires OPENAI_API_KEY (uses the embeddings API). Safe to re-run.
"""
import html
import json
import re

from django.core.management.base import BaseCommand

from accounts.models import Lesson
from ai_yordamchi.models import KnowledgeChunk
from ai_yordamchi.rag import embed_texts

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150
BATCH = 64


def strip_html(raw):
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', ' ', raw or '', flags=re.S | re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = html.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    text = (text or '').strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks = []
    start = 0
    step = max(1, size - overlap)
    while start < len(text):
        chunks.append(text[start:start + size])
        start += step
    return chunks


class Command(BaseCommand):
    help = "Darslardan AI bilim bazasini quradi (embeddinglar bilan)."

    def add_arguments(self, parser):
        parser.add_argument('--rebuild', action='store_true',
                            help="Avvalgi bilim bazasini tozalab, boshidan quradi.")

    def handle(self, *args, **options):
        if options['rebuild']:
            deleted = KnowledgeChunk.objects.all().delete()[0]
            self.stdout.write(f"Eski bilim bazasi tozalandi ({deleted} yozuv).")

        lessons = Lesson.objects.select_related('profession').all()
        pending_texts = []
        pending_meta = []
        total = 0
        skipped = 0

        def flush():
            nonlocal total
            if not pending_texts:
                return True
            vectors = embed_texts(pending_texts)
            if not vectors:
                self.stderr.write(self.style.ERROR(
                    "Embedding olinmadi. OPENAI_API_KEY sozlanganini tekshiring."))
                return False
            rows = [
                KnowledgeChunk(
                    profession_id=meta['profession_id'],
                    source_type='lesson',
                    source_id=meta['source_id'],
                    title=meta['title'],
                    content=text,
                    embedding=json.dumps(vec),
                )
                for meta, vec, text in zip(pending_meta, vectors, pending_texts)
            ]
            KnowledgeChunk.objects.bulk_create(rows)
            total += len(rows)
            pending_texts.clear()
            pending_meta.clear()
            return True

        for lesson in lessons:
            body = strip_html(lesson.ai_article)
            if not body:
                skipped += 1
                continue
            # Re-index cleanly: drop existing chunks for this lesson first.
            KnowledgeChunk.objects.filter(source_type='lesson', source_id=lesson.id).delete()
            for piece in chunk_text(lesson.title + '. ' + body):
                pending_texts.append(piece)
                pending_meta.append({
                    'profession_id': lesson.profession_id,
                    'source_id': lesson.id,
                    'title': lesson.title,
                })
                if len(pending_texts) >= BATCH:
                    if not flush():
                        return

        if not flush():
            return

        self.stdout.write(self.style.SUCCESS(
            f"Tayyor: {total} ta bo'lak indekslandi. ({skipped} ta dars matnsiz o'tkazib yuborildi.)"))
