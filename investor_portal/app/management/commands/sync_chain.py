# django_app/management/commands/sync_chain.py
from django.core.management.base import BaseCommand
class Command(BaseCommand):
    help = "Sync RWA events. Use --reset to replay history from block 0."

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Wipe sync state and replay from block 0')

    # django_app/management/commands/sync_chain.py
    def handle(self, *args, **options):
        from app.tasks import sync_blockchain_events
        
        self.stdout.write("Starting manual sync (Blocking)...")
        
        # .apply() runs it locally in this process immediately
        # No broker/RabbitMQ/Redis needed!
        result = sync_blockchain_events.apply() 
        
        self.stdout.write(self.style.SUCCESS(f"Done! Status: {result.result}"))