from django.core.management.base import BaseCommand, CommandError
from analytics import runner


class Command(BaseCommand):
    help = "Run the PySpark analytics jobs manually (same job the Data Analytics page triggers)"

    def handle(self, *a, **kw):
        problem = runner.preflight()
        if problem:
            raise CommandError(problem)
        mode = runner.source_mode()
        runner.write_status(state="running", started_at=runner.now(), message="", triggered_by="command", source=mode, worker=False, data_hash=runner.data_fingerprint())
        st = runner.run_job(mode, "command", use_worker=False)
        if st["state"] != "succeeded":
            raise CommandError(st.get("message", "Spark job failed"))
        self.stdout.write(self.style.SUCCESS(f"Analytics finished in {st['seconds']}s. Results: {runner.OUT}"))
