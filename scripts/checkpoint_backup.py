#!/usr/bin/env python3
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import threading

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = ROOT / "snapshots"
INTERVAL = int(os.environ.get("BACKUP_INTERVAL", "3600"))
stop = threading.Event()


def request_stop(signum, frame):
    stop.set()


def sources():
    names = {
        "main-state.txt", "main.log", "main-results.txt", "main-follow.log",
        "coverage-latest.json", "gpu-queue.log", "gpu-rebalance.log", "cpu-follow-stages.log",
        "elliptic-new-results.txt", "new-verified-results.txt", "full100k-results.txt",
        "experiments/elliptic/elliptic-new-results.txt",
        "src/search_v18.cpp", "src/gpu_search_v42.cu",
        "scripts/gpu_queue.py", "scripts/gpu_follow.py", "scripts/gpu_rebalance.py",
        "scripts/gpu_stages.py", "scripts/main_follow.py", "scripts/cpu_follow.py",
        "scripts/coverage_audit.py", "scripts/result_monitor.py", "scripts/verify.py",
        "scripts/checkpoint_backup.py", "scripts/search_deadline_guard.py",
        "evidence/benchmarks/cpu-opt-benchmark.json",
        "evidence/benchmarks/gpu-opt-benchmark.json",
        "evidence/benchmarks/gpu-recovery-deployment.json",
        "experiments/heavy/heavy_queue.py", "experiments/heavy/verify_heavy.py",
        "experiments/heavy/gpu_search_v36.cu",
        "experiments/elliptic/elliptic_vector_search.py",
        "experiments/elliptic/elliptic_vector_search_fast.py",
        "experiments/elliptic/elliptic_high_follow.py",
        "experiments/elliptic/elliptic_stage_chain.py",
        "experiments/elliptic/elliptic_fast_filter.py",
        "experiments/elliptic/elliptic_filter.cpp",
        "experiments/elliptic/elliptic-fast-filter-benchmark.json",
        "experiments/elliptic/elliptic-fast-filter-deployment.json",
        "experiments/elliptic/elliptic-symmetry-validation.json",
        "experiments/elliptic/elliptic-small-prime-validation.json",
        "experiments/elliptic/elliptic-medium-prime-validation.json",
        "experiments/elliptic/elliptic_vector_search_before_symmetry.py",
        "experiments/elliptic/elliptic_vector_search_before_small_primes.py",
    }
    patterns = (
        "gpu-[0-7]*-state.txt", "gpu-[0-7]*-results.txt", "gpu-[0-7]*.unverified-*",
        "lookahead*-state.txt", "lookahead*-results.txt",
        "experiments/heavy/heavy-v3[56]-*-state.txt",
        "experiments/heavy/heavy-v3[56]-*-state.txt.done",
        "experiments/heavy/heavy-v3[56]-*-results.txt",
        "experiments/elliptic/elliptic-lazy-b*-state.txt",
        "experiments/elliptic/elliptic-lazy-b*-hits.jsonl",
        "experiments/elliptic/elliptic-high-*.log",
        "experiments/elliptic/elliptic-*-summary.json",
        "experiments/elliptic/elliptic-*-launch.json",
        "experiments/elliptic/elliptic-*-resume.json",
        "experiments/elliptic/elliptic-*-preflight.json",
        "experiments/elliptic/elliptic-stage-chain-*.log",
    )
    for pattern in patterns:
        for path in ROOT.glob(pattern):
            names.add(str(path.relative_to(ROOT)))
            if path.name.endswith("-state.txt"):
                names.add(str(path.with_name(path.name.replace("-state.txt", ".log")).relative_to(ROOT)))
    return sorted(ROOT / name for name in names if (ROOT / name).is_file())


def snapshot():
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    temporary = DESTINATION / ("." + stamp + ".tmp")
    final = DESTINATION / stamp
    files = temporary / "files"
    files.mkdir(parents=True)
    entries = []
    for source in sources():
        relative = source.relative_to(ROOT)
        data = source.read_bytes()
        target = files / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        entries.append({"name": str(relative), "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_root": str(ROOT),
        "files": entries,
    }
    (temporary / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    temporary.rename(final)
    for entry in entries:
        data = (final / "files" / entry["name"]).read_bytes()
        assert len(data) == entry["bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    print(f"{manifest['timestamp_utc']} snapshot={final.name} files={len(entries)} "
          f"bytes={sum(entry['bytes'] for entry in entries)} verified=true", flush=True)


def main():
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stop.is_set():
        snapshot()
        if os.environ.get("BACKUP_ONCE") == "1":
            break
        stop.wait(INTERVAL)


if __name__ == "__main__":
    main()
