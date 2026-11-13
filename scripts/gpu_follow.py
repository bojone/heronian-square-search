#!/usr/bin/env python3
import os
from pathlib import Path
import signal
import subprocess
import sys

from gpu_stages import MAX_STAGE, stage_index, stage_name

ROOT = Path(__file__).resolve().parent.parent
child = None
stopping = False


def request_stop(signum, frame):
    global stopping
    stopping = True
    if child is not None and child.poll() is None:
        child.send_signal(signal.SIGTERM)


def main():
    global child
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    start = sys.argv[1] if len(sys.argv) > 1 else "o"
    for index in range(stage_index(start), MAX_STAGE + 1):
        if stopping:
            break
        stage = stage_name(index)
        print(f"FOLLOW STAGE {stage}", flush=True)
        child = subprocess.Popen([sys.executable, str(ROOT / "scripts/gpu_queue.py"), stage],
                                 cwd=ROOT, env=environment)
        status = child.wait()
        if status != 0:
            raise SystemExit(f"stage {stage} exited with status {status}")
    print("FOLLOW FINISHED", flush=True)


if __name__ == "__main__":
    main()
