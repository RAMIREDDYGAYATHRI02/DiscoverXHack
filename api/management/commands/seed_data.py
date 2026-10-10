from django.core.management.base import BaseCommand

from api.domain import ensure_seeded


class Command(BaseCommand):
    help = "Initialize the CityCare roster once; existing state is never overwritten."

    def handle(self, *args, **options):
        document = ensure_seeded()
        self.stdout.write(self.style.SUCCESS(
            f"Roster is initialized ({len(document['staff'])} people, {len(document['shifts'])} shifts). Existing changes were preserved."
        ))
