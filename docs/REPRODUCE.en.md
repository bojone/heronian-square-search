# Reproduction guide

**[中文](REPRODUCE.md) | English**

Run all commands from the project root. They cover building, regression tests, single-interval searches, distributed execution, checkpoint audits, and final verification.

## 1. Requirements

Production code requires only:

- a C++17 compiler;
- the Python 3.12 standard library;
- optionally, the CUDA toolkit and an NVIDIA GPU.

The completed run used:

```text
G++ 11.4
CUDA 12.9
Python 3.12
```

Some experimental elliptic scripts use NumPy. Production search and result verification do not require it.

## 2. Build

Build CPU and GPU versions:

```bash
make NVCC=/usr/local/cuda/bin/nvcc all
```

CPU only:

```bash
make cpu
```

Outputs:

```text
build/search
build/gpu_search_v42
search -> build/search
search_v13 -> search
gpu_search_v42 -> build/gpu_search_v42
```

Compiler settings can be overridden:

```bash
make CXX=g++ CXXFLAGS='-O3 -std=c++17 -march=native' cpu
make NVCC=/usr/local/cuda/bin/nvcc GPU_ARCH=native gpu
```

`native` targets the current GPU. Select a suitable architecture when building for a different machine.

## 3. Regression tests

Run CPU and GPU regression tests:

```bash
make NVCC=/usr/local/cuda/bin/nvcc test
```

CPU-only tests:

```bash
make test-cpu
```

The smoke script checks:

| Case | Range | Candidates | Expected result |
|---|---|---:|---|
| `full5000` | `limit=5000, l=1..5000` | `151842556` | `1853 4380 4427 32918611718880` |
| `known2` | `limit=70000, l=11789` | `1194756` | `11789 68104 68595 284239560530875680` |

CPU logical pair counters must also be `12502500` and `58212`. Each binary writes independent state and result files.

Verify the final evidence:

```bash
python3 scripts/verify_all_results.py --root evidence --known-only
```

Expected summary:

```text
ALL NONEMPTY RESULT FILES VERIFIED files=17 lines=34 unique=[(1853, 4380, 4427), (11789, 68104, 68595)]
```

## 4. Single-interval searches

CPU arguments:

```text
search LIMIT FIRST_L LAST_L THREADS STATE_FILE [RESULTS_FILE]
```

Example:

```bash
./search 5000 1 5000 2 small-state.txt small-results.txt
python3 scripts/verify.py small-results.txt
```

GPU arguments:

```text
gpu_search_v42 LIMIT FIRST_L LAST_L RESULTS_FILE [GPU [STATE_FILE]]
```

Example:

```bash
./gpu_search_v42 10000000 7500000 7500511 gpu-results.txt 0 gpu-state.txt
python3 scripts/verify.py gpu-results.txt
```

Every GPU `PROGRESS resume` entry must advance by 512, except for a shorter final batch.

## 5. Full CPU search through root side 10000000

```bash
./search 10000000 1 10000000 272 main-state.txt main-results.txt
```

The final state must contain:

```text
resume 10000001
```

Then run:

```bash
python3 scripts/coverage_audit.py
python3 scripts/verify_all_results.py --known-only
```

`coverage-latest.json` must include:

```json
"complete_intervals": [[1, 10000000]]
```

Use `SIGTERM` or `SIGINT` for a graceful stop and resume later with the same command. Do not force-kill a process while its checkpoint is being written.

## 6. Multi-GPU distributed execution

Set a Unix deadline:

```bash
export MAIN_FOLLOW_DEADLINE="$(python3 -c 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).timestamp()+604800)')"
```

Start each supervisor in a separate terminal. **Only one instance of each supervisor type may run in a given working directory.**

```bash
python3 scripts/main_follow.py 0
python3 scripts/gpu_follow.py b
python3 scripts/gpu_rebalance.py
python3 scripts/cpu_follow.py
python3 scripts/result_monitor.py
python3 scripts/checkpoint_backup.py
```

`main_follow.py 0` starts or adopts the main checkpoint. `gpu_follow.py b` is a fresh scheduling example, not a replay of every historical stage.

Select GPUs with:

```bash
GPU_IDS=0,1,2,3 python3 scripts/gpu_follow.py b
```

For a nonstandard driver location:

```bash
export LD_LIBRARY_PATH="/usr/local/nvidia/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
```

The original host also used a local `cuda-driver/` compatibility directory, which is not required for a normal CUDA installation.

## 7. Deadline protection

Run the guard with the same `MAIN_FOLLOW_DEADLINE`:

```bash
python3 scripts/search_deadline_guard.py
```

It stops auxiliary tasks, direct workers, and the main search in stages. It exits without sending stop signals when an independently verified new solution appears or coverage reaches `[[1,10000000]]`.

The CPU and GPU schedulers also skip intervals that are already covered by the audit.

## 8. Atomic backups

Create one verified snapshot:

```bash
BACKUP_ONCE=1 BACKUP_INTERVAL=3600 python3 scripts/checkpoint_backup.py
```

Run hourly backups:

```bash
BACKUP_INTERVAL=3600 python3 scripts/checkpoint_backup.py
```

Snapshots are stored in `snapshots/<UTC timestamp>/`:

- `files/` contains states, logs, results, and source files;
- `manifest.json` records each file's byte count and SHA-256;
- a temporary directory is atomically renamed after writing;
- every file is read back and verified.

Historical snapshot data is not shipped in this project. The original final manifest is available at `evidence/final-snapshot-manifest.json`.

## 9. State and result formats

Example CPU state:

```text
version 1
limit 10000000
begin 1180045
end 10000000
resume 10000001
pairs 38895816330946
candidates 1501947057268700
```

GPU states omit `pairs`, but must have a continuous `PROGRESS resume` log.

Each result line is:

```text
l m n area
```

Examples:

```text
1853 4380 4427 32918611718880
11789 68104 68595 284239560530875680
```

Candidate counters restart at process launch. Do not add them blindly across logs or compare them across different filter versions.

## 10. Troubleshooting

### `nvcc: command not found`

Run:

```bash
make NVCC=/usr/local/cuda/bin/nvcc gpu
```

or add CUDA's `bin` directory to `PATH`.

### Script permission errors

Run scripts through Python:

```bash
python3 scripts/verify.py
```

or set executable bits:

```bash
chmod +x scripts/*.py
```

### Coverage appears stationary

A long batch may not have reached its next checkpoint. Increasing CPU `pairs` or `candidates`, or a new GPU `PROGRESS` entry, shows that work continues. Do not restart solely because `resume` is temporarily unchanged.

### Result verification fails

Keep the corresponding state, log, and results, then run:

```bash
python3 scripts/verify.py RESULTS_FILE
```

Never report an internal candidate that has not passed exact verification as a final solution.

## 11. Original source hashes

Original production source SHA-256 values:

```text
search_v18.cpp:
523ca758c71d7dd0cb3dd4c3f61f2d02f710aa1c2892aee8dfca294d0afffffc

gpu_search_v42.cu:
a4cfcccba18582c6526d56aaec3e7ad202f4d9bca029b6f944b70973388a27c6
```

Historical production binary hashes are recorded in `evidence/benchmarks/gpu-opt-benchmark.json`. Newly compiled binaries need not be byte-identical across toolchains and architecture settings.
