#!/usr/bin/env python3
import datetime
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
LIMIT = 10000000
MIN_WEIGHT = 100
BATCH = 4096
DEADLINE = float(os.environ["HEAVY_QUEUE_DEADLINE"])
stop = threading.Event()
child = None
current_pid = None
current_range = None


def log(message):
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(f"{stamp} {message}", flush=True)


def names(first, last):
    stem = ROOT / f"heavy-v36-w{MIN_WEIGHT}-{first}-{last}"
    return (stem.with_name(stem.name + "-results.txt"),
            stem.with_name(stem.name + "-state.txt"),
            stem.with_name(stem.name + ".log"))


def arguments(first, last):
    results, state, _ = names(first, last)
    return [str(LIMIT), str(first), str(last), results.name, str(GPU), state.name, str(MIN_WEIGHT)]


def process_matches(pid, first, last):
    try:
        fields = [os.fsdecode(value) for value in
                  Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if value]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return len(fields) == 8 and Path(fields[0]).name == "gpu_search_v36" and fields[1:] == arguments(first, last)


def read_state(first, last):
    path = names(first, last)[1]
    if not path.exists():
        return {}
    return {key: int(value) for key, value in
            (line.split() for line in path.read_text().splitlines())}


def complete(first, last):
    values = read_state(first, last)
    return (values.get("limit") == LIMIT and values.get("begin") == first
            and values.get("end") == last and values.get("resume") == last + 1
            and values.get("min_weight") == MIN_WEIGHT)


def verify(first, last):
    if not read_state(first, last):
        return
    subprocess.run([sys.executable, str(ROOT / "verify_heavy.py"), str(names(first, last)[1])],
                   cwd=ROOT, check=True)


def running_other():
    result = subprocess.run(["ps", "-C", "gpu_search_v36", "-o", "pid=,args="],
                            text=True, capture_output=True)
    found = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 9 and Path(fields[1]).name == "gpu_search_v36":
            found.append(int(fields[0]))
    return [pid for pid in found if pid != current_pid]


def launch(first, last):
    global child
    results, state, log_path = names(first, last)
    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = str(ROOT / "cuda-driver") + ":/usr/local/nvidia/lib64"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with log_path.open("a") as output:
        child = subprocess.Popen([str(ROOT / "gpu_search_v36"), *arguments(first, last)],
                                 cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT)
    log(f"START pid={child.pid} range={first}-{last} state={read_state(first, last)}")
    return child.pid


def request_stop(signum, frame):
    stop.set()
    if child is not None and child.poll() is None:
        child.send_signal(signal.SIGTERM)
    elif current_pid is not None and current_range is not None and process_matches(current_pid, *current_range):
        try:
            os.kill(current_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def main():
    global current_pid, current_range, GPU
    if len(sys.argv) != 6:
        raise SystemExit("usage: heavy_queue.py FIRST LAST GPU EXISTING_PID MAX_BATCHES")
    first = int(sys.argv[1])
    last = int(sys.argv[2])
    GPU = int(sys.argv[3])
    current_pid = int(sys.argv[4])
    maximum = int(sys.argv[5])
    if not 1 <= first <= last < LIMIT or (last - first + 1) % BATCH or maximum < 1:
        raise SystemExit("invalid range or batch count")
    if not 0 <= GPU < 8 or DEADLINE <= time.time():
        raise SystemExit("invalid GPU or deadline")
    lines = subprocess.check_output(["ps", "-C", "python3", "-o", "pid=,args="],
                                    text=True).splitlines()
    duplicates = [line for line in lines
                  if int(line.split()[0]) != os.getpid() and "heavy_queue.py" in line]
    if duplicates:
        raise RuntimeError(f"duplicate heavy queue: {duplicates}")
    if current_pid and not process_matches(current_pid, first, last):
        raise RuntimeError(f"process {current_pid} is not the expected heavy worker")
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    log(f"ADOPT pid={current_pid} range={first}-{last} maximum={maximum}")
    finished = 0
    previous_resume = None
    failures = 0
    while finished < maximum and not stop.is_set() and time.time() < DEADLINE:
        current_range = first, last
        if complete(first, last):
            verify(first, last)
            log(f"COMPLETE range={first}-{last}")
            finished += 1
            if finished < maximum:
                first = last + 1
                last = first + BATCH - 1
                current_pid = None
                previous_resume = None
                failures = 0
            continue
        if current_pid is not None and process_matches(current_pid, first, last):
            stop.wait(20)
            continue
        if running_other():
            raise RuntimeError(f"another heavy worker is active: {running_other()}")
        current_pid = None
        values = read_state(first, last)
        verify(first, last)
        resume = values.get("resume", first)
        if resume == previous_resume:
            failures += 1
        else:
            failures = 0
        if failures >= 3:
            raise RuntimeError(f"heavy worker failed to advance: {values}")
        if time.time() >= DEADLINE:
            break
        current_pid = launch(first, last)
        previous_resume = resume
        stop.wait(20)
    if time.time() >= DEADLINE and not stop.is_set():
        request_stop(signal.SIGTERM, None)
    if current_pid is not None and current_range is not None:
        deadline = time.monotonic() + 1800
        while process_matches(current_pid, *current_range) and time.monotonic() < deadline:
            time.sleep(1)
        if process_matches(current_pid, *current_range):
            raise RuntimeError(f"heavy worker did not stop: {current_pid}")
    log(f"HEAVY QUEUE FINISHED batches={finished} range={first}-{last}")


if __name__ == "__main__":
    main()
