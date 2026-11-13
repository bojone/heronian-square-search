#!/usr/bin/env python3
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
START = int(sys.argv[1]) if len(sys.argv) > 1 else 110000
TARGET = int(sys.argv[2]) if len(sys.argv) > 2 else START + 10000
if not 0 < START <= TARGET:
    raise SystemExit("usage: elliptic_stage_chain.py COMPLETED_BOUND [NEXT_BOUND]")
stop = threading.Event()
child = None


def utc(timestamp=None):
    if timestamp is None:
        return datetime.datetime.now(datetime.timezone.utc).isoformat()
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).isoformat()


def state(prefix):
    path = ROOT / f"{prefix}-state.txt"
    if not path.exists():
        return {}
    return {key: int(value) for key, value in
            (line.split() for line in path.read_text().splitlines())}


def processes(name):
    lines = subprocess.check_output(["ps", "-C", "python3", "-o", "pid=,args="], text=True).splitlines()
    return [(int(fields[0]), fields) for line in lines
            if len(fields := line.split()) >= 2
            and any(Path(field).name == name for field in fields[1:])]


def save_json(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def verify_new_results():
    path = ROOT / "elliptic-new-results.txt"
    if path.exists() and path.read_text().strip():
        subprocess.run([sys.executable, str(ROOT / "verify.py"), str(path)], cwd=ROOT, check=True)
        raise RuntimeError(f"new independently verified result: {path.read_text().strip()}")


def validate_complete(bound, previous):
    fibers = {}
    hits = []
    for index, prefix in enumerate((f"elliptic-lazy-b{bound}", f"elliptic-lazy-b{bound}-f1")):
        terminal = index + 1
        expected = {"bound": bound, "fiber": terminal, "next_n": 0, "previous_bound": previous}
        values = state(prefix)
        assert values == expected, (prefix, values, expected)
        lines = (ROOT / f"{prefix}.log").read_text().splitlines()
        assert lines[-1] == f"ELLIPTIC FINISHED fiber={terminal} next_n=0 classes=0 stop=False", lines[-1]
        hit_path = ROOT / f"{prefix}-hits.jsonl"
        if hit_path.exists():
            hits.append(hit_path.name)
            for line in hit_path.read_text().splitlines():
                roots = json.loads(line)["roots"]
                subprocess.run([sys.executable, str(ROOT / "verify.py"), *map(str, roots)], cwd=ROOT, check=True)
        fibers[prefix] = values
    high_lines = (ROOT / f"elliptic-high-{bound}.log").read_text().splitlines()
    assert high_lines[-2:] == ["ALL FIBERS COMPLETE", "HIGH FOLLOW FINISHED"], high_lines[-2:]
    verify_new_results()
    launch_path = ROOT / f"elliptic-{bound}-launch.json"
    launch = json.loads(launch_path.read_text()) if launch_path.exists() else {}
    summary = {
        "bound": bound,
        "previous_bound": previous,
        "status": "complete",
        "fibers": fibers,
        "hits_files": hits,
        "new_results": [],
        "high_follow": "ALL FIBERS COMPLETE; HIGH FOLLOW FINISHED",
        "completion_log_mtime_utc": utc((ROOT / f"elliptic-high-{bound}.log").stat().st_mtime),
        "verified_utc": utc(),
        "paired_power_filter": True,
        "coefficient_symmetry_reduced": launch.get("coefficient_symmetry_reduced", False),
    }
    save_json(ROOT / f"elliptic-{bound}-summary.json", summary)
    print(f"STAGE COMPLETE {json.dumps(summary)}", flush=True)
    environment = os.environ.copy()
    environment["BACKUP_ONCE"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with (ROOT / "checkpoint-backup.log").open("a") as output:
        subprocess.run([sys.executable, str(ROOT.parents[1] / "scripts/checkpoint_backup.py")], cwd=ROOT,
                       env=environment, stdout=output, stderr=subprocess.STDOUT, check=True)


def launch_next():
    global child
    assert not processes("elliptic_high_follow.py")
    assert not processes("elliptic_vector_search.py")
    for prefix in (f"elliptic-lazy-b{TARGET}", f"elliptic-lazy-b{TARGET}-f1"):
        assert not (ROOT / f"{prefix}-state.txt").exists()
        assert not (ROOT / f"{prefix}.log").exists()
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["ELLIPTIC_BOUND"] = str(TARGET)
    environment["ELLIPTIC_PREVIOUS_BOUND"] = str(START)
    with (ROOT / f"elliptic-high-{TARGET}.log").open("a") as output:
        child = subprocess.Popen([sys.executable, str(ROOT / "elliptic_high_follow.py"), "0", "0"],
                                 cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT)
    print(f"START bound={TARGET} previous_bound={START} follow_pid={child.pid}", flush=True)
    deadline = time.monotonic() + 900
    while not stop.is_set() and time.monotonic() < deadline:
        workers = processes("elliptic_vector_search.py")
        states = [state(f"elliptic-lazy-b{TARGET}"), state(f"elliptic-lazy-b{TARGET}-f1")]
        if len(workers) == 2 and all(states):
            records = []
            for index, (prefix, values) in enumerate(zip(
                    (f"elliptic-lazy-b{TARGET}", f"elliptic-lazy-b{TARGET}-f1"), states)):
                assert values["bound"] == TARGET and values["previous_bound"] == START, values
                assert values["fiber"] == index and values["next_n"] >= 0, values
                text = (ROOT / f"{prefix}.log").read_text()
                matches = re.findall(rf"FIBER {index} .*resume=(\d+) models=(\d+)", text)
                assert matches and int(matches[-1][0]) == 0 and int(matches[-1][1]) > 0, matches
                progress = re.findall(rf"PROGRESS fiber={index} next_position=(\d+)", text)
                assert progress and int(progress[-1]) == values["next_n"], (progress, values)
                records.append({"pid": workers[index][0], "models": int(matches[-1][1]),
                                "state": values, "log_state_match": True})
            monitor_log = ROOT.parents[1] / "result-monitor.log"
            save_json(ROOT / f"elliptic-{TARGET}-launch.json", {
                "bound": TARGET,
                "previous_bound": START,
                "verified_utc": utc(),
                "library_sha256": hashlib.sha256((ROOT / "elliptic_filter.so").read_bytes()).hexdigest(),
                "source_sha256": hashlib.sha256((ROOT / "elliptic_vector_search.py").read_bytes()).hexdigest(),
                "workers": dict(zip((f"elliptic-lazy-b{TARGET}", f"elliptic-lazy-b{TARGET}-f1"), records)),
                "coefficient_symmetry_reduced": True,
                "result_monitor_empty": not monitor_log.exists() or not monitor_log.read_text().strip(),
            })
            print(f"FIRST CHECKPOINT VERIFIED {json.dumps(records)}", flush=True)
            return
        if child.poll() is not None:
            raise RuntimeError(f"new high-level follow exited before its first checkpoint: {child.returncode}")
        time.sleep(2)
    raise RuntimeError("timed out waiting for the first two new-stage checkpoints")


def request_stop(signum, frame):
    stop.set()
    if child is not None and child.poll() is None:
        child.send_signal(signal.SIGTERM)


def main():
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    duplicates = [pid for pid, fields in processes("elliptic_stage_chain.py") if pid != os.getpid()]
    assert not duplicates, duplicates
    while not stop.is_set() and processes("elliptic_high_follow.py"):
        verify_new_results()
        time.sleep(5)
    if not stop.is_set():
        validate_complete(START, START - 10000)
    if not stop.is_set() and TARGET > START:
        launch_next()
        while not stop.is_set() and child.poll() is None:
            verify_new_results()
            time.sleep(5)
        if not stop.is_set():
            assert child.returncode == 0, child.returncode
            validate_complete(TARGET, START)
    print("STAGE CHAIN FINISHED", flush=True)


if __name__ == "__main__":
    main()
