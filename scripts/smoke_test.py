#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

CASES = {
    "full5000": {
        "limit": 5000,
        "first": 1,
        "last": 5000,
        "pairs": 12502500,
        "candidates": 151842556,
        "results": "1853 4380 4427 32918611718880\n",
    },
    "known2": {
        "limit": 70000,
        "first": 11789,
        "last": 11789,
        "pairs": 58212,
        "candidates": 1194756,
        "results": "11789 68104 68595 284239560530875680\n",
    },
}


def read_state(path):
    return {key: int(value) for key, value in
            (line.split() for line in path.read_text().splitlines())}


def run_case(binary, name, case, work):
    state = work / f"{name}-state.txt"
    results = work / f"{name}-results.txt"
    command = [
        str(binary), str(case["limit"]), str(case["first"]), str(case["last"]),
    ]
    if binary.name == "search":
        command.extend(["2", str(state), str(results)])
    else:
        command.extend([str(results), "0", str(state)])
    environment = os.environ.copy()
    environment["HERON_COVERAGE_FILE"] = str(work / "no-coverage.json")
    completed = subprocess.run(command, cwd=work, env=environment, text=True,
                               capture_output=True, timeout=900)
    (work / f"{name}.stdout").write_text(completed.stdout)
    (work / f"{name}.stderr").write_text(completed.stderr)
    if completed.returncode:
        raise RuntimeError(f"{name} failed with exit code {completed.returncode}")
    values = read_state(state)
    assert values["limit"] == case["limit"], values
    assert values["begin"] == case["first"], values
    assert values["end"] == case["last"], values
    assert values["resume"] == case["last"] + 1, values
    assert values["candidates"] == case["candidates"], values
    if binary.name == "search":
        assert values["pairs"] == case["pairs"], values
    assert results.read_text() == case["results"], results.read_text()
    subprocess.run([os.fsdecode(Path(__file__).resolve().with_name("verify.py")), str(results)],
                   check=True, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--search", default="search")
    parser.add_argument("--gpu-search", default="gpu_search_v42")
    parser.add_argument("--skip-gpu", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().with_name("verify.py").parent.parent
    build = root / "build"
    build.mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="smoke-", dir=build))
    binaries = [Path(args.search).resolve()]
    if not args.skip_gpu:
        binaries.append(Path(args.gpu_search).resolve())
    for binary in binaries:
        if not binary.is_file():
            raise FileNotFoundError(binary)
        for name, case in CASES.items():
            run_case(binary.resolve(), f"{binary.name}-{name}", case, work)
    subprocess.run([os.fsdecode(Path(__file__).resolve().with_name("verify.py"))], check=True,
                   capture_output=True, text=True)
    print(f"SMOKE TEST PASSED binaries={len(binaries)} cases={len(CASES)} workdir={work}")


if __name__ == "__main__":
    main()
