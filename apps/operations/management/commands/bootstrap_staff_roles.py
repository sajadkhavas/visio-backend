from django.core.management.base import BaseCommand, CommandParser

from apps.operations.roles import sync_staff_roles


class Command(BaseCommand):
    help = "Create or reconcile the deterministic VISIO staff groups and permissions."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Resolve the role matrix without mutating groups.",
        )

    def handle(self, *args: object, **options: object) -> None:
        dry_run = bool(options["check"])
        resolved = sync_staff_roles(dry_run=dry_run)
        mode = "CHECK" if dry_run else "SYNC"
        self.stdout.write(f"VISIO_STAFF_ROLES_{mode}=PASS")
        for name, permissions in resolved.items():
            self.stdout.write(f"{name}: {len(permissions)} permissions")
