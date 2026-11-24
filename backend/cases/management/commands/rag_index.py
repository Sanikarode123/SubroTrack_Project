from django.core.management.base import BaseCommand, CommandError
from rag import engine


class Command(BaseCommand):
    help = "Build (or rebuild) the RAG search index for all cases"

    def handle(self, *a, **kw):
        try:
            n = engine.reindex_all()
        except engine.RagUnavailable as e:
            raise CommandError(str(e))
        self.stdout.write(self.style.SUCCESS(f"Indexed {n} cases. {engine.status()}"))
