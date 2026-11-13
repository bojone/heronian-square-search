# Primitive Heronian Triangles with Square Sides: CPU/GPU Exhaustive Search

**[中文](README.md) | English**

**This entire project was completed autonomously by Kimi K3.1 Pro [thinkg: max] + Kimi-Code.**

This project searches for primitive Heronian triangles whose three sides are perfect squares and whose area is an integer. It documents the algorithm, implementation, search optimizations, and independent verification. Public sources are used only as background and references; see [References](docs/REFERENCES.md).

For root sides $`l,m,n`$, the actual sides are $`l^2,m^2,n^2`$. The exhaustive search covered all root sides from **1 to 10,000,000**, so the square sides are bounded by $`10^{14}`$.

## Results

**No third primitive solution was found in this complete range.** The only solutions emitted by the search are the two previously known ones:

| Root sides $`(l,m,n)`$ | Actual sides $`(l^2,m^2,n^2)`$ | Integer area |
|---|---|---:|
| `(1853, 4380, 4427)` | `(3433609, 19184400, 19598329)` | `32918611718880` |
| `(11789, 68104, 68595)` | `(138980521, 4638154816, 4705274025)` | `284239560530875680` |

Both solutions were independently checked for nondegeneracy, primitivity, Heron's formula, and area using arbitrary-precision integers. The 17 nonempty result files contain 34 lines but only these two distinct solutions.

This is not a nonexistence claim for larger ranges or for the general problem. It applies only to the complete, checkpoint-audited search space. See [Results and runtime](docs/RESULTS.md).

## Approach

Directly enumerating $`l,m,n`$ is expensive. Define

$$D=l^4+m^4-n^4.$$

Heron's formula gives

$$(4A)^2+D^2=(2l^2m^2)^2.$$

Enumerate only $`l,m`$, generate every relevant Pythagorean representation using the Gaussian factorization of $`2l^2m^2`$, and test whether

$$n^4=l^4+m^4-D$$

is a fourth power. **There is no loop over $`n`$.** The implementation also includes:

- exclusion using inert primes $`p\equiv3\pmod4`$;
- Gaussian factorization caches and modular filters;
- exact 128/256-bit integer checks on the CPU;
- GPU candidate generation followed by independent Python verification;
- continuous checkpoints, recovery, coverage merging, and per-file SHA-256 snapshots.

See [Algorithm and correctness](docs/ALGORITHM.en.md) for the derivation, or [中文算法文档](docs/ALGORITHM.md) for the Chinese version.

## Hardware and elapsed time

- GPU: eight NVIDIA GPUs.
- CUDA: the production environment used CUDA 12.9, with the compiler at `/usr/local/cuda/bin/nvcc`.
- CPU: 288 hardware threads in total; the main search used 272 worker threads, with 16 additional lookahead threads.
- Main search completion: 2026-11-10 00:11:36 UTC.
- Calendar span from project start to completion: `468764` seconds, approximately **130.21 hours**.
- Active work reported by the goal runner: **118 hours 36 minutes**.
- Main v18 worker: `299820` seconds, approximately **83.28 hours**.

These are historical measurements from this machine, not performance promises for other hardware. Calendar span, active work, and individual worker time are different measurements. See [Results and runtime](docs/RESULTS.md) and the [machine-readable record](evidence/hardware.json).

## Layout

```text
heronian-square-search/
├── README.md                 # Default Chinese overview
├── README.en.md              # English overview
├── CONTRIBUTING.md           # Contribution and evidence rules
├── LICENSE                   # MIT license
├── Makefile                  # Production build and regression entry points
├── SHA256SUMS                # Checksums for released files
├── src/                      # Production CPU v18 and GPU v42
├── scripts/                  # Verification, scheduling, recovery, backups and audits
├── docs/                     # Algorithms, reproduction, results, optimization and references
├── evidence/                 # Final coverage, results, logs, benchmarks and snapshot manifest
└── experiments/
    ├── elliptic/             # Auxiliary two-fiber elliptic search
    ├── heavy/                # Targeted high-Gaussian-weight experiments
    └── legacy/               # Historical versions, not production entry points
```

The archived experiments document the research process. **Do not substitute files in `experiments/legacy/` for the production sources.** Production scripts use the project root as their working directory and do not depend on the original absolute search path.

## Audit the archived results without a GPU

Python 3 is required. Production search and result verification use only the Python standard library; NumPy is needed only by the elliptic experiments.

```bash
# Independently recompute the two known solutions
python3 scripts/verify.py

# Verify every archived nonempty result and require exactly the two known solutions
python3 scripts/verify_all_results.py --root evidence --known-only

# Check released files for corruption during transfer
sha256sum -c SHA256SUMS
```

The expected result summary is:

```text
ALL NONEMPTY RESULT FILES VERIFIED files=17 lines=34 unique=[(1853, 4380, 4427), (11789, 68104, 68595)]
```

These commands recompute Heron's formula and the area of every saved result. They do **not** rescan the complete search space in a few minutes. This curated release does not contain every intermediate state or per-GPU interval log referenced by the original coverage report. See [Evidence notes](evidence/README.md) for the frozen report, final manifest, and procedure for regenerating evidence.

## Build and run lightweight self-tests

Requirements:

- a C++17 compiler; G++ 11.4 was used for the production CPU build;
- Python 3.12, standard library only for production scripts;
- optionally, the NVIDIA CUDA toolkit; CUDA 12.9 was used;
- about 9 GiB of free GPU memory per production GPU worker.

```bash
# If nvcc is not on PATH, build CPU/GPU and run all regression cases
make NVCC=/usr/local/cuda/bin/nvcc test

# Without a GPU, build and run only the CPU regression
make test-cpu

# Compile without starting a search
make NVCC=/usr/local/cuda/bin/nvcc all
```

The tests check:

- the exhaustive 1–5000 interval, with `151842556` candidates and the first known solution;
- the single-root interval at 11789, with `1194756` candidates and the second known solution;
- CPU logical pair counts of `12502500` and `58212`, respectively;
- every nonempty result in `evidence/`, which still contains only the two known solutions.

Each binary writes separate state and result files, preventing the GPU test from reusing a CPU hit. Logs are written to `build/smoke-*`; the CI workflow is in `.github/workflows/ci.yml`.

## Single-process reproduction

The CPU arguments are `LIMIT FIRST_L LAST_L THREADS STATE_FILE [RESULTS_FILE]`:

```bash
make cpu
./search 5000 1 5000 2 small-state.txt small-results.txt
python3 scripts/verify.py small-results.txt
```

The GPU arguments are `LIMIT FIRST_L LAST_L RESULTS_FILE [GPU [STATE_FILE]]`:

```bash
make NVCC=/usr/local/cuda/bin/nvcc gpu
./gpu_search_v42 10000000 7500000 7500511 gpu-results.txt 0 gpu-state.txt
python3 scripts/verify.py gpu-results.txt
```

Each GPU checkpoint covers at most 512 root positions. Keep the state, `PROGRESS` log, and result files together. When moving to another GPU architecture, adjust `GPU_ARCH`; historical throughput figures do not transfer automatically.

## Reproduce from scratch and audit complete coverage

A full run involves several days of computation and multiple concurrent CPU/GPU workers. Read the [Reproduction guide](docs/REPRODUCE.en.md) or [中文复现指南](docs/REPRODUCE.md) first. A successful build or self-test is not a full reproduction.

The single-process full CPU entry point is:

```bash
./search 10000000 1 10000000 272 main-state.txt main-results.txt
```

Start each supervisor in a separate terminal, with only one instance of each type per working directory:

```bash
export MAIN_FOLLOW_DEADLINE="$(python3 -c 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).timestamp()+604800)')"
python3 scripts/main_follow.py 0
python3 scripts/gpu_follow.py b
python3 scripts/gpu_rebalance.py
python3 scripts/cpu_follow.py
python3 scripts/result_monitor.py
python3 scripts/checkpoint_backup.py
```

This deadline example is one week, not an unbounded run. The supervisors are configured for this ten-million-root target. When changing the range, inspect the stage configuration and state files rather than mixing old and new checkpoints.

Run the coverage audit when needed:

```bash
python3 scripts/coverage_audit.py
python3 scripts/verify_all_results.py --known-only
```

Only `complete_intervals == [[1,10000000]]` in the newly generated `coverage-latest.json` establishes full target coverage. Partial checkpoints or percentages cannot establish that no third solution exists. Do not overwrite historical evidence with an audit from an empty directory.

## Final evidence

- [Final coverage report](evidence/final-coverage.json): `complete_intervals = [[1,10000000]]` and both coverage ratios are 1.
- [Final main state](evidence/main-state.txt): `resume = 10000001`.
- [Final results](evidence/final-results.txt): the two known solutions.
- [Nonempty result files](evidence/nonempty-results/): 17 files and 34 lines.
- [Final snapshot manifest](evidence/final-snapshot-manifest.json): byte counts and SHA-256 hashes for 1975 files in the original final snapshot.
- [Run logs](evidence/logs/): CPU/GPU queues, rebalancing, coverage, and backup logs.

Approximately 4 GB of historical snapshot data is intentionally not included. The final manifest, essential evidence, and sources needed to regenerate it are included. See [Evidence notes](evidence/README.md).

## Source scope and license

The production CPU/GPU source hashes match the versions used in the original search. Historical binary hashes identify the binaries used in the archived logs; different compilers, drivers, or architectures can produce different hashes without changing the mathematical result.

Documentation: [Algorithm and correctness](docs/ALGORITHM.en.md) · [Reproduction guide](docs/REPRODUCE.en.md) · [Optimizations](docs/OPTIMIZATION.md) · [Results](docs/RESULTS.md) · [References](docs/REFERENCES.md) · [Contributing](CONTRIBUTING.md).

The project is distributed under the [MIT License](LICENSE). The original states, logs, and result evidence are provided under the same license to support independent verification and future research.
