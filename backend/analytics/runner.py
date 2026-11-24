"""Starts Spark analytics in the background and keeps its status. Results are read from disk, so page views never touch Spark.
By default a warm Spark worker process is reused between runs (SPARK_WORKER=0 falls back to one process per run)."""
import hashlib, json, os, re, shutil, signal, subprocess, sys, threading, time
from datetime import date, datetime, timezone
from decimal import Decimal
from importlib import metadata
from importlib.util import find_spec
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.models import Count, Max, Sum
from cases.models import RecoveryCase, Payment, Activity
from . import store

ROOT = Path(settings.BASE_DIR) / "analytics_data"
OUT, INP, STATUS, HB, REQ = ROOT / "output", ROOT / "input", ROOT / "status.json", ROOT / "worker.json", ROOT / "queue" / "request.json"
JOB_TIMEOUT = int(os.getenv("SPARK_JOB_TIMEOUT_S", "600"))
STARTUP_TIMEOUT = int(os.getenv("SPARK_STARTUP_TIMEOUT_S", "150"))
_java = {}
_lock = threading.Lock()
now = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")


def source_mode():
    m = os.getenv("SPARK_SOURCE", "auto")
    return "jdbc" if m == "jdbc" or (m == "auto" and os.getenv("DB_NAME")) else "export"


def read_status():
    return store.read_json(STATUS, None) or {"state": "idle"}


def write_status(**kw):
    store.write_json(STATUS, {**read_status(), **kw})


def read_results():
    return store.read_json(OUT / "results.json", None) or {}


def worker_alive():
    try:
        return time.time() - store.read_json(HB)["ts"] < 10
    except Exception:
        return False


def java_major():
    """Major version of the Java that Spark will use (None if not found)."""
    if "v" not in _java:
        exe = os.path.join(os.environ["JAVA_HOME"], "bin", "java") if os.getenv("JAVA_HOME") else shutil.which("java")
        major = None
        try:
            p = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=20)
            m = re.search(r'version "(\d+)(?:\.(\d+))?', p.stderr or p.stdout)
            major = int(m.group(1)) if m and m.group(1) != "1" else int(m.group(2)) if m else None
        except Exception:
            pass
        _java["v"] = major
    return _java["v"]


def preflight():
    """Catch the usual setup problems up front with a clear message instead of a long Java stack trace after a minute of waiting."""
    if find_spec("pyspark") is None:
        return "PySpark is not installed. Run: pip install -r requirements-spark.txt"
    ver, java = metadata.version("pyspark"), java_major()
    spark_major = int(ver.split(".")[0])
    if java is None:
        return "Java was not found. Install JDK 17, then set JAVA_HOME to it (check with: java -version)."
    if java > 21:
        return f"Java {java} is too new for Spark. Install JDK 17 (or 21) and set JAVA_HOME to it."
    if spark_major >= 4 and java < 17:
        return f"PySpark {ver} needs Java 17 or newer, but Java {java} was found. Install JDK 17 and set JAVA_HOME to it."
    if spark_major < 4 and sys.version_info >= (3, 13):
        return f"PySpark {ver} does not support Python {sys.version_info.major}.{sys.version_info.minor}. Run: pip install -U \"pyspark>=4.0,<4.1\""
    return None


def data_fingerprint():
    """Changes whenever case data that the analytics use changes (status, assignment, amounts, payments, activity)."""
    h = hashlib.md5()
    for row in RecoveryCase.objects.order_by("id").values_list("id", "status", "assigned_to_id", "client_id", "third_party", "amount_paid", "expected_recovery"):
        h.update(repr(row).encode())
    h.update(repr(Payment.objects.aggregate(n=Count("id"), m=Max("id"), s=Sum("amount"))).encode())
    h.update(repr(Activity.objects.aggregate(n=Count("id"), m=Max("id"))).encode())
    return h.hexdigest()


def is_stale(st=None):
    st = st or read_status()
    return not read_results() or st.get("data_hash") != data_fingerprint()


def _log_tail():
    try:
        return (ROOT / "worker.log").read_text(errors="ignore")[-600:]
    except Exception:
        return ""


def reconcile():
    """Never leave the page stuck on 'running': detect a dead worker or a job that ran too long."""
    st = read_status()
    if st.get("state") != "running":
        return st
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(st["started_at"])).total_seconds()
    except Exception:
        age = JOB_TIMEOUT + 1
    reason = None
    if st.get("worker") and age > 45 and not worker_alive():
        reason = "The Spark worker stopped unexpectedly. " + store.short_error(_log_tail())
    elif str(st.get("stage", "")).startswith("Starting") and age > STARTUP_TIMEOUT:
        reason = f"Spark did not start within {STARTUP_TIMEOUT} seconds. Check Java (JDK 17) and run `python manage.py check_spark`. " + _log_tail()
        _kill_worker()
    elif age > JOB_TIMEOUT:
        reason = f"The job ran longer than {JOB_TIMEOUT // 60} minutes and was stopped."
        _kill_worker()
    if reason:
        write_status(state="failed", message=reason, stage="", finished_at=now())
    return read_status()


def _kill_worker():
    try:
        pid = (store.read_json(HB) or {}).get("pid")
        if pid:
            os.kill(int(pid), signal.SIGTERM)
    except Exception:
        pass
    try:
        HB.unlink()
    except Exception:
        pass


def cancel():
    try:
        REQ.unlink()
    except Exception:
        pass
    _kill_worker()
    write_status(state="failed", message="Stopped by the manager.", stage="", finished_at=now())
    return read_status()


def _plain(v):
    if isinstance(v, Decimal): return float(v)
    if isinstance(v, datetime): return v.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date): return v.isoformat()
    return v


def _dump(name, qs):
    INP.mkdir(parents=True, exist_ok=True)
    with open(INP / f"{name}.jsonl", "w", encoding="utf-8") as f:
        for r in qs:
            f.write(json.dumps({k: _plain(v) for k, v in r.items()}) + "\n")


def _export():
    _dump("cases", RecoveryCase.objects.values("id", "recovery_id", "third_party", "amount_paid", "expected_recovery", "status", "assigned_to_id", "created_at"))
    _dump("payments", Payment.objects.values("case_id", "amount", "date"))
    _dump("activities", Activity.objects.values("case_id", "type", "created_at"))
    _dump("users", get_user_model().objects.values("id", "username"))


def _env(mode):
    return {**os.environ, "PYSPARK_PYTHON": sys.executable, "PYSPARK_DRIVER_PYTHON": sys.executable, "PYTHONPATH": str(settings.BASE_DIR),
            "ANALYTICS_DIR": str(ROOT), "ANALYTICS_MODE": mode, "SPARK_LOCAL_IP": "127.0.0.1",
            "JAVA_TOOL_OPTIONS": os.getenv("JAVA_TOOL_OPTIONS", "-XX:TieredStopAtLevel=1 -XX:+UseSerialGC")}


def run_job(mode, who="manual"):
    """Blocking one-shot run in its own process (management command, or SPARK_WORKER=0)."""
    t0 = time.time()
    try:
        if mode == "export":
            _export()
        cmd = [sys.executable, "-m", "analytics.spark_jobs", "--mode", mode, "--input", str(INP), "--output", str(OUT),
               "--delay-days", str(settings.DELAY_THRESHOLD_DAYS)]
        p = subprocess.run(cmd, cwd=settings.BASE_DIR, env=_env(mode), capture_output=True, text=True, timeout=900)
        if p.returncode:
            raise RuntimeError(store.short_error(p.stderr or p.stdout))
        write_status(state="succeeded", finished_at=now(), message="", stage="", seconds=round(time.time() - t0, 1), worker=False)
    except Exception as e:
        write_status(state="failed", finished_at=now(), message=str(e)[-1500:], stage="", seconds=round(time.time() - t0, 1))
    finally:
        connection.close()
    return read_status()


def _spawn_worker(mode):
    ROOT.mkdir(parents=True, exist_ok=True)
    log = open(ROOT / "worker.log", "a")
    flags = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if os.name == "nt" else {"start_new_session": True}
    subprocess.Popen([sys.executable, "-m", "analytics.spark_worker"], cwd=settings.BASE_DIR, env=_env(mode), stdout=log, stderr=log, **flags)


def _dispatch(mode, who):
    """Export the data (if needed), queue the request, and start the warm worker if it is not running.
    After the request is queued only the worker writes the status, so the two processes never overwrite each other."""
    try:
        if mode == "export":
            _export()
        REQ.parent.mkdir(parents=True, exist_ok=True)
        store.write_json(REQ, {"mode": mode, "input": str(INP), "output": str(OUT), "delay_days": settings.DELAY_THRESHOLD_DAYS})
        if not worker_alive():
            _spawn_worker(mode)
    except Exception as e:
        try:
            REQ.unlink()
        except Exception:
            pass
        write_status(state="failed", finished_at=now(), message=str(e)[-1500:], stage="")
    finally:
        connection.close()


def start(user, force=False):
    """Returns (status, error). Runs Spark only if forced, never run, failed last time, or the data changed since the last run."""
    problem = preflight()
    if problem:
        return None, problem
    with _lock:
        st = reconcile()
        if st.get("state") == "running":
            return st, None
        h = data_fingerprint()
        if not force and st.get("state") == "succeeded" and read_results() and st.get("data_hash") == h:
            return st, None
        mode, use_worker = source_mode(), os.getenv("SPARK_WORKER", "1") == "1"
        write_status(state="running", started_at=now(), finished_at=None, message="", stage="Preparing data", triggered_by=user.username,
                     source=mode, worker=use_worker, data_hash=h)
        threading.Thread(target=_dispatch if use_worker else run_job, args=(mode, user.username), daemon=True).start()
    return read_status(), None
