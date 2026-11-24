"""Tiny JSON file helpers shared by Django and the Spark processes. Writes are atomic and retry on Windows,
where replacing a file that another process is reading can fail for a moment."""
import json, os, time
from pathlib import Path


def read_json(path, default=None):
    for _ in range(5):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return default
        except Exception:
            time.sleep(0.05)
    return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    for _ in range(60):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)
    path.write_text(json.dumps(data), encoding="utf-8")


def short_error(text, limit=900):
    """Keep only the lines of a long Java/Python stack trace that say what went wrong."""
    lines = [l.strip() for l in str(text).splitlines() if l.strip()]
    key = [l for l in lines if any(k in l for k in ("Error", "Exception", "Caused by", "not found", "Unsupported"))]
    return "\n".join(key[-6:] or lines[-6:])[-limit:]
