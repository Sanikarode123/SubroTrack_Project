import sys, time
from importlib import metadata
from django.core.management.base import BaseCommand, CommandError
from analytics import runner


class Command(BaseCommand):
    help = "Diagnose the Spark setup: versions, Java, and a tiny test job with timings"

    def handle(self, *a, **kw):
        out = self.stdout.write
        out(f"Python  : {sys.version.split()[0]}")
        try:
            out(f"PySpark : {metadata.version('pyspark')}")
        except Exception:
            out("PySpark : not installed")
        out(f"Java    : {runner.java_major() or 'not found'}")
        problem = runner.preflight()
        if problem:
            raise CommandError(problem)
        from analytics import spark_jobs
        t = time.time()
        spark = spark_jobs.build_session("export")
        out(f"Spark {spark.version} session started in {time.time() - t:.1f}s")
        t = time.time()
        n = spark.range(100000).selectExpr("id % 7 AS k").groupBy("k").count().count()
        out(f"Test job finished in {time.time() - t:.1f}s ({n} groups)")
        spark.stop()
        self.stdout.write(self.style.SUCCESS("Spark works. If the page still fails, open backend/analytics_data/worker.log."))
