from django.core.management.base import BaseCommand, CommandError

from apps.operations.audit import verify_audit_chain


class Command(BaseCommand):
    help = "Verify the VISIO operational audit hash chain."

    def handle(self, *args: object, **options: object) -> None:
        valid, detail = verify_audit_chain()
        if not valid:
            raise CommandError(f"VISIO_AUDIT_CHAIN=FAIL detail={detail}")
        self.stdout.write(self.style.SUCCESS(f"VISIO_AUDIT_CHAIN=PASS detail={detail}"))
