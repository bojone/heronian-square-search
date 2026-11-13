#!/usr/bin/env python3
import datetime
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

from gpu_stages import MAX_STAGE, stage_first, stage_index, stage_name

LIMIT = 10000000
ROOT = Path(__file__).resolve().parent.parent
BINARY = ROOT / "gpu_search_v42"
GPU_IDS = tuple(int(value) for value in os.environ.get("GPU_IDS", "0,1,2,3,4,5,6,7").split(","))
if not GPU_IDS or len(set(GPU_IDS)) != len(GPU_IDS) or any(not 0 <= gpu < 8 for gpu in GPU_IDS):
    raise SystemExit("invalid GPU_IDS")
STAGE_INDEX = stage_index(sys.argv[1]) if len(sys.argv) > 1 else stage_index("m")
if len(sys.argv) > 2 or not 1 <= STAGE_INDEX <= MAX_STAGE:
    raise SystemExit("usage: gpu_queue.py [STAGE_NAME]")
PREVIOUS_SUFFIX = stage_name(STAGE_INDEX - 1)
TARGET_SUFFIX = stage_name(STAGE_INDEX)
stop = threading.Event()
children = {}
children_lock = threading.Lock()


def read_state(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {}
    return {key: int(value) for key, value in (line.split() for line in path.read_text().splitlines())}


def checkpoint_resume(first, last, state_path):
    values = read_state(state_path)
    resume = values.get("resume", 0)
    if (values.get("limit") != LIMIT or values.get("end") != last
            or not first <= values.get("begin", 0) <= resume <= last + 1):
        return None
    path = Path(state_path)
    if not path.is_absolute():
        path = ROOT / path
    log = path.with_name(path.name.replace("-state.txt", ".log"))
    if not log.exists():
        return None
    expected = first
    for line in log.read_text().splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[:2] != ["PROGRESS", "resume"]:
            continue
        current = int(fields[2])
        if current <= expected:
            continue
        if current != min(expected + 512, last + 1):
            return None
        expected = current
    return expected if expected == resume else None


def complete(first, last, state_path):
    return checkpoint_resume(first, last, state_path) == last + 1


def prepare_checkpoint(first, last, state_path):
    if checkpoint_resume(first, last, state_path) is not None:
        return
    path = Path(state_path)
    if not path.is_absolute():
        path = ROOT / path
    log = path.with_name(path.name.replace("-state.txt", ".log"))
    suffix = f".unverified-{time.time_ns()}"
    for source in (path, log):
        if source.exists():
            destination = source.with_name(source.name + suffix)
            source.replace(destination)
            print(f"PRESERVED UNVERIFIED CHECKPOINT {source.name} -> {destination.name}", flush=True)


def running(gpu):
    result = subprocess.run([
        "ps", "-C", "gpu_search_v14", "-C", "gpu_search_v15", "-C", "gpu_search_v18",
        "-C", "gpu_search_v21", "-C", "gpu_search_v26", "-C", "gpu_search_v30",
        "-C", "gpu_search_v32", "-C", "gpu_search_v40", "-C", "gpu_search_v42", "-o", "pid=,args=",
    ], text=True, capture_output=True)
    output = result.stdout
    found = []
    for line in output.splitlines():
        fields = line.split()
        if (len(fields) == 8 and fields[6] == str(gpu)
                and Path(fields[7]).name.startswith(f"gpu-{gpu}")):
            found.append((int(fields[0]), fields))
    return found


def wait_for_slot(gpu, first, last, results, state):
    while not stop.is_set():
        if complete(first, last, state):
            return True
        processes = running(gpu)
        if not processes:
            return False
        for pid, fields in processes:
            if Path(fields[5]).name != Path(results).name or Path(fields[7]).name != Path(state).name:
                if complete(int(fields[3]), int(fields[4]), fields[7]):
                    continue
                raise RuntimeError(f"unexpected process on GPU {gpu}: {fields}")
        stop.wait(5)
    return False


def report_results(path):
    lines = [line for line in path.read_text().splitlines() if line.strip()]
    if not lines:
        return
    print(f"RESULTS {path}: {lines}", flush=True)
    subprocess.run(["python3", str(ROOT / "scripts/verify.py"), str(path)], check=True)


def earlier_intervals(gpu):
    intervals = []
    pattern = re.compile(rf"gpu-{gpu}([a-z]{{0,2}})-state\.txt")
    for path in ROOT.glob(f"gpu-{gpu}*-state.txt"):
        match = pattern.fullmatch(path.name)
        if match is None:
            continue
        suffix = match.group(1)
        order = stage_index(suffix) if suffix else -1
        if order >= STAGE_INDEX - 1 or order >= MAX_STAGE:
            continue
        base = 9700000 if not suffix else stage_first(order)
        values = read_state(path)
        last = values.get("end", 0)
        first = last - 12499
        if (values.get("limit") != LIMIT or not base <= first < base + 100000
                or first % 12500 != 0 or (first - base) // 12500 != gpu):
            continue
        if not complete(first, last, path):
            intervals.append((order, first, last, suffix))
    return sorted(intervals)


def repair_earlier(gpu):
    for order, first, last, suffix in earlier_intervals(gpu):
        state = ROOT / f"gpu-{gpu}{suffix}-state.txt"
        results = ROOT / f"gpu-{gpu}{suffix}-results.txt"
        failures = 0
        while not stop.is_set() and not covered_by_main(first, last, state, results):
            if wait_for_slot(gpu, first, last, results, state):
                break
            if stop.is_set():
                return
            prepare_checkpoint(first, last, state)
            process = launch(gpu, first, last, suffix)
            process.wait()
            with children_lock:
                children.pop(gpu, None)
            if complete(first, last, state):
                break
            failures += 1
            if failures >= 3:
                raise RuntimeError(f"GPU {gpu} could not complete recovery of {first}-{last}")
            stop.wait(10)
        if complete(first, last, state):
            report_results(results)
            print(f"RECOVERED gpu={gpu} range={first}-{last}", flush=True)


def launch(gpu, first, last, suffix):
    prefix = ROOT / f"gpu-{gpu}{suffix}"
    results = prefix.with_name(prefix.name + "-results.txt")
    state = prefix.with_name(prefix.name + "-state.txt")
    log = prefix.with_name(prefix.name + ".log")
    stamp = prefix.with_name(prefix.name + "-v21-start.txt")
    with stamp.open("a") as output:
        output.write(datetime.datetime.now(datetime.timezone.utc).isoformat() + "\n")
    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = str(ROOT / "cuda-driver") + ":/usr/local/nvidia/lib64"
    with log.open("a") as output:
        process = subprocess.Popen([
            str(BINARY), str(LIMIT), str(first), str(last), str(results), str(gpu), str(state),
        ], cwd=ROOT, env=environment, stdout=output, stderr=subprocess.STDOUT)
    with children_lock:
        children[gpu] = process
    print(f"START gpu={gpu} pid={process.pid} range={first}-{last} state={state.name}", flush=True)
    return process


def covered_by_main(first, last, state, results):
    if complete(first, last, state):
        return True
    try:
        report = json.loads((ROOT / "coverage-latest.json").read_text())
        covered = (report.get("limit") == LIMIT and
                   any(begin <= first and last <= end
                       for begin, end in report["complete_intervals"]))
    except (OSError, ValueError, TypeError, KeyError):
        covered = False
    if not covered:
        main_state = read_state(ROOT / "main-state.txt")
        if main_state.get("limit") != LIMIT or main_state.get("resume", 0) <= last:
            return False
    state = Path(state)
    if not state.is_absolute():
        state = ROOT / state
    results = Path(results)
    if not results.is_absolute():
        results = ROOT / results
    temporary = Path(str(state) + ".tmp")
    temporary.write_text(f"version 1\nlimit {LIMIT}\nbegin {first}\nend {last}\n"
                         f"resume {last + 1}\ncandidates 0\n")
    temporary.replace(state)
    results.touch(exist_ok=True)
    print(f"ALREADY COVERED range={first}-{last} state={state.name}", flush=True)
    return True


def run_worker(gpu):
    current_first = stage_first(STAGE_INDEX - 1) + 12500 * gpu
    current_last = current_first + 12499
    current_state = f"gpu-{gpu}{PREVIOUS_SUFFIX}-state.txt"
    current_results = f"gpu-{gpu}{PREVIOUS_SUFFIX}-results.txt"
    try:
        failures = 0
        while not stop.is_set() and not covered_by_main(current_first, current_last,
                                                        current_state, current_results):
            if wait_for_slot(gpu, current_first, current_last, current_results, current_state):
                break
            if stop.is_set():
                return
            prepare_checkpoint(current_first, current_last, current_state)
            process = launch(gpu, current_first, current_last, PREVIOUS_SUFFIX)
            process.wait()
            with children_lock:
                children.pop(gpu, None)
            if complete(current_first, current_last, ROOT / current_state):
                failures = 0
            else:
                failures += 1
                if failures >= 3:
                    raise RuntimeError(f"GPU {gpu} made no complete checkpoint after three resumes")
                stop.wait(10)
        if stop.is_set():
            return
        report_results(ROOT / current_results)
        repair_earlier(gpu)
        first = stage_first(STAGE_INDEX) + 12500 * gpu
        last = first + 12499
        state = ROOT / f"gpu-{gpu}{TARGET_SUFFIX}-state.txt"
        results = ROOT / f"gpu-{gpu}{TARGET_SUFFIX}-results.txt"
        failures = 0
        while not stop.is_set() and not covered_by_main(first, last, state, results):
            if wait_for_slot(gpu, first, last, results, state):
                break
            if stop.is_set():
                return
            prepare_checkpoint(first, last, state)
            process = launch(gpu, first, last, TARGET_SUFFIX)
            process.wait()
            with children_lock:
                children.pop(gpu, None)
            if complete(first, last, state):
                break
            failures += 1
            if failures >= 3:
                raise RuntimeError(f"GPU {gpu} failed to advance its new interval")
            stop.wait(10)
        if complete(first, last, state):
            report_results(results)
            print(f"DONE gpu={gpu} range={first}-{last}", flush=True)
    except Exception as error:
        print(f"ERROR gpu={gpu}: {error}", flush=True)


def request_stop(signum, frame):
    stop.set()
    with children_lock:
        processes = list(children.values())
    for process in processes:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)


def main():
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    for gpu in GPU_IDS:
        processes = running(gpu)
        if len(processes) > 1:
            raise RuntimeError(f"duplicate processes on GPU {gpu}: {processes}")
    threads = [threading.Thread(target=run_worker, args=(gpu,), daemon=True) for gpu in GPU_IDS]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    with children_lock:
        processes = list(children.values())
    for process in processes:
        process.wait()
    print("QUEUE FINISHED", flush=True)


if __name__ == "__main__":
    main()
