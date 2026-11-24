from django.core.management.base import BaseCommand
from analytics import runner, spark_worker


class Command(BaseCommand):
    help = "Run the warm Spark worker in the foreground (for servers/systemd), or stop a running one with --stop"

    def add_arguments(self, parser):
        parser.add_argument("--stop", action="store_true")

    def handle(self, *a, **o):
        if o["stop"]:
            try:
                runner._call({"cmd": "shutdown"}, 5)
                self.stdout.write("Spark worker stopped.")
            except OSError:
                self.stdout.write("No Spark worker is running.")
            return
        spark_worker.main(["--port", str(runner.PORT)])
