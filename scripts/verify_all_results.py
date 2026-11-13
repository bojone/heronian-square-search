#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import subprocess

KNOWN = {(1853, 4380, 4427), (11789, 68104, 68595)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--known-only", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    verify = Path(__file__).resolve().with_name("verify.py")
    paths = [root / "main-results.txt", root / "final-results.txt",
             root / "elliptic-new-results.txt"]
    paths.extend(root.glob("lookahead*-results.txt"))
    paths.extend(root.glob("nonempty-results/*-results.txt"))
    paths.extend(root.glob("gpu-[0-7]*-results.txt"))
    paths.extend(root.glob("heavy-v3[56]-*-results.txt"))
    paths.extend(root.glob("experiments/elliptic/elliptic-new-results.txt"))
    paths.extend(root.glob("experiments/heavy/heavy-v3[56]-*-results.txt"))
    nonempty = []
    roots = set()
    lines = 0
    for path in sorted(set(paths)):
        if not path.exists() or not path.read_text().strip():
            continue
        nonempty.append(path)
        result = subprocess.run([os.fsdecode(verify), str(path)], text=True,
                                capture_output=True)
        if result.returncode:
            print(result.stdout, end="")
            print(result.stderr, end="")
            raise SystemExit(f"verification failed for {path}")
        print(f"VERIFIED FILE {path}")
        if result.stdout:
            print(result.stdout, end="")
        for line in path.read_text().splitlines():
            if line.strip():
                roots.add(tuple(map(int, line.split()[:3])))
                lines += 1
    if args.known_only:
        assert roots == KNOWN, roots
    print(f"ALL NONEMPTY RESULT FILES VERIFIED files={len(nonempty)} "
          f"lines={lines} unique={sorted(roots)}")


if __name__ == "__main__":
    main()
