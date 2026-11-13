#!/usr/bin/env python3
from pathlib import Path
import signal
import subprocess
import threading

ROOT = Path(__file__).resolve().parent.parent
KNOWN = {(1853, 4380, 4427), (11789, 68104, 68595)}
stop = threading.Event()


def request_stop(signum, frame):
    stop.set()


def scan():
    paths = [ROOT / "main-results.txt", ROOT / "elliptic-new-results.txt",
             ROOT / "experiments/elliptic/elliptic-new-results.txt"]
    paths.extend(ROOT.glob("lookahead*-results.txt"))
    paths.extend(ROOT.glob("gpu-[0-7]*-results.txt"))
    paths.extend(ROOT.glob("heavy-v3[56]-*-results.txt"))
    paths.extend(ROOT.glob("experiments/heavy/heavy-v3[56]-*-results.txt"))
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            fields = line.split()
            if not fields:
                continue
            roots = tuple(map(int, fields[:3]))
            if roots in KNOWN:
                continue
            result = subprocess.run(
                ["python3", str(ROOT / "scripts/verify.py"), *fields[:4]],
                cwd=ROOT, text=True, capture_output=True,
            )
            if result.returncode != 0:
                print(f"INVALID RESULT {path}: {line}\n{result.stdout}{result.stderr}", flush=True)
                continue
            with (ROOT / "new-verified-results.txt").open("a") as output:
                output.write(line + "\n")
            print(f"NEW VERIFIED RESULT {path}: {line}\n{result.stdout}", flush=True)
            return roots
    return None


def main():
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stop.is_set():
        found = scan()
        if found is not None:
            return
        stop.wait(20)


if __name__ == "__main__":
    main()
