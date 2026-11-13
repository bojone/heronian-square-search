#!/usr/bin/env python3
import os
from pathlib import Path
import signal
import subprocess
import time

from gpu_stages import MAX_STAGE, stage_first, stage_index

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 10000000
GPU_IDS = tuple(int(value) for value in os.environ.get("GPU_IDS", "0,1,2,3,4,5,6,7").split(","))
if not GPU_IDS or len(set(GPU_IDS)) != len(GPU_IDS) or any(not 0 <= gpu < 8 for gpu in GPU_IDS):
    raise SystemExit("invalid GPU_IDS")
pending = None
last_rebalanced = None


def queue_process():
    result = subprocess.run(["ps", "-C", "python3", "-o", "pid=,args="],
                            text=True, capture_output=True)
    found = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 4 and Path(fields[2]).name == "gpu_queue.py" and len(fields[3]) <= 2:
            found.append((int(fields[0]), fields[3]))
    if len(found) > 1:
        raise RuntimeError(f"duplicate GPU queues: {found}")
    return found[0] if found else None


def running(gpu):
    result = subprocess.run([
        "ps", "-C", "gpu_search_v21", "-C", "gpu_search_v26", "-C", "gpu_search_v30",
        "-C", "gpu_search_v32", "-C", "gpu_search_v40", "-C", "gpu_search_v42", "-o", "pid=,args=",
    ], text=True, capture_output=True)
    found = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if (len(fields) == 8 and fields[6] == str(gpu)
                and Path(fields[7]).name.startswith(f"gpu-{gpu}")):
            found.append((int(fields[0]), fields))
    return found


def complete(first, last, path):
    if not path.exists():
        return False
    state = {key: int(value) for key, value in
             (line.split() for line in path.read_text().splitlines())}
    return (state.get("limit") == LIMIT and state.get("end") == last
            and state.get("resume") == last + 1)


def is_recovery(fields, gpu, index):
    name = Path(fields[7]).name
    suffix = name.removeprefix(f"gpu-{gpu}").removesuffix("-state.txt")
    if not suffix:
        return index > 1
    if len(suffix) <= 2 and suffix.isascii() and suffix.isalpha() and suffix.islower():
        return stage_index(suffix) < index
    return False


def main():
    global pending, last_rebalanced
    while True:
        current = queue_process()
        if current is None:
            pending = None
            time.sleep(30)
            continue
        pid, stage = current
        index = stage_index(stage)
        if not 1 <= index < MAX_STAGE:
            pending = None
            time.sleep(30)
            continue
        idle = []
        active = []
        repairing = False
        for gpu in GPU_IDS:
            first = stage_first(index) + 12500 * gpu
            last = first + 12499
            state = ROOT / f"gpu-{gpu}{stage}-state.txt"
            processes = running(gpu)
            if len(processes) > 1:
                raise RuntimeError(f"duplicate processes on GPU {gpu}: {processes}")
            if processes:
                active.append(gpu)
                repairing = repairing or any(is_recovery(fields, gpu, index)
                                            for pid, fields in processes)
            elif complete(first, last, state):
                idle.append(gpu)
        key = (pid, stage, tuple(idle), tuple(active))
        completed = (stage, tuple(idle))
        if (idle and active and idle != list(GPU_IDS) and not repairing
                and completed != last_rebalanced):
            if pending == key:
                print(f"REBALANCE queue={pid} stage={stage} complete_idle={idle} active={active}", flush=True)
                os.kill(pid, signal.SIGTERM)
                last_rebalanced = completed
                pending = None
            else:
                pending = key
        else:
            pending = None
        time.sleep(30)


if __name__ == "__main__":
    main()
