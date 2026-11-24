"""Long-lived Spark worker. The Spark session (the slow part) starts once; every later run only does the calculations.
Django drops a request file in analytics_data/queue/ and this process picks it up. It exits after a few idle minutes."""
import os, threading, time, traceback
from datetime import datetime, timezone
from pathlib import Path
from analytics import spark_jobs, store

ROOT = Path(os.environ["ANALYTICS_DIR"])
STATUS, HB, REQ = ROOT / "status.json", ROOT / "worker.json", ROOT / "queue" / "request.json"
IDLE_SECONDS = int(os.environ.get("SPARK_WORKER_IDLE_MIN", "5")) * 60
now = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_status(**kw):
    store.write_json(STATUS, {**(store.read_json(STATUS, {}) or {}), **kw})


def safe_status(**kw):
    try:
        write_status(**kw)
    except Exception:
        pass


def heartbeat():
    while True:
        try:
            store.write_json(HB, {"pid": os.getpid(), "ts": time.time()})
        except Exception:
            pass
        time.sleep(1)


def elapsed():
    try:
        return round((datetime.now(timezone.utc) - datetime.fromisoformat((store.read_json(STATUS, {}) or {})["started_at"])).total_seconds(), 1)
    except Exception:
        return None


def main():
    (ROOT / "queue").mkdir(parents=True, exist_ok=True)
    threading.Thread(target=heartbeat, daemon=True).start()
    try:
        safe_status(stage="Starting Spark session (first run only)", worker=True)
        spark = spark_jobs.build_session(os.environ.get("ANALYTICS_MODE", "export"))
    except BaseException:
        safe_status(state="failed", finished_at=now(), stage="", message=store.short_error(traceback.format_exc()))
        return
    last = time.time()
    try:
        while time.time() - last < IDLE_SECONDS:
            if REQ.exists():
                try:
                    req = store.read_json(REQ)
                    REQ.unlink()
                except Exception:
                    time.sleep(0.2)
                    continue
                try:
                    spark_jobs.run_analytics(spark, req["mode"], req["input"], req["output"], req["delay_days"], stage=lambda s: safe_status(stage=s))
                    outcome = dict(state="succeeded", message="")
                except BaseException:
                    outcome = dict(state="failed", message=store.short_error(traceback.format_exc()))
                for _ in range(5):  # the final status must always be recorded
                    try:
                        write_status(finished_at=now(), stage="", seconds=elapsed(), worker=True, **outcome)
                        break
                    except Exception:
                        time.sleep(0.3)
                last = time.time()
            time.sleep(0.4)
    finally:
        try:
            spark.stop()
        except Exception:
            pass
        try:
            HB.unlink()
        except Exception:
            pass


if __name__ == "__main__":
    main()
