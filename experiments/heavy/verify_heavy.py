#!/usr/bin/env python3
import math
from pathlib import Path
import subprocess
import sys


def read_state(path):
    values = {}
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) != 2:
            raise ValueError(f"invalid state line: {line}")
        values[fields[0]] = int(fields[1])
    return values


def primes_through(limit):
    sieve = bytearray(b"\1") * (limit + 1)
    sieve[:2] = b"\0\0"
    for prime in range(2, math.isqrt(limit) + 1):
        if sieve[prime]:
            sieve[prime * prime::prime] = b"\0" * (((limit - prime * prime) // prime) + 1)
    return [value for value in range(2, limit + 1) if sieve[value]]


def branch_weight(value, primes):
    weight = 1
    for prime in primes:
        if prime * prime > value:
            break
        exponent = 0
        while value % prime == 0:
            value //= prime
            exponent += 1
        if prime % 4 == 1:
            weight *= 4 * exponent + 1
    if value > 1 and value % 4 == 1:
        weight *= 5
    return weight


def read_done(path, state):
    lines = path.read_text().splitlines()
    if len(lines) < 2:
        raise ValueError("incomplete done-file header")
    header = {}
    roots = []
    for line in lines:
        fields = line.split()
        if len(fields) == 2 and fields[0] in {"limit", "min_weight"}:
            header[fields[0]] = int(fields[1])
        elif len(fields) == 1:
            roots.append(int(fields[0]))
        else:
            raise ValueError(f"invalid done-file line: {line}")
    if header.get("limit") != state["limit"] or header.get("min_weight") != state["min_weight"]:
        raise ValueError("done-file header does not match the checkpoint")
    if any(first >= second for first, second in zip(roots, roots[1:])):
        raise ValueError("done-file roots are duplicated or out of order")
    return roots


def verify(state_path):
    state_path = Path(state_path)
    state = read_state(state_path)
    if state.get("version") != 1:
        raise ValueError("unsupported checkpoint version")
    limit = state["limit"]
    first = state["begin"]
    last = state["end"]
    resume = state["resume"]
    minimum = state["min_weight"]
    if not 1 <= first <= last <= limit or not first <= resume <= last + 1:
        raise ValueError("invalid checkpoint range")
    if minimum <= 0:
        raise ValueError("heavy checkpoint has no positive weight threshold")
    done_path = Path(str(state_path) + ".done")
    roots = read_done(done_path, state)
    if any(not first <= root < resume or root > last for root in roots):
        raise ValueError("done-file root is outside the completed prefix")
    primes = primes_through(math.isqrt(last) + 1)
    expected = [root for root in range(first, resume)
                if branch_weight(root, primes) >= minimum]
    if roots != expected:
        missing = sorted(set(expected) - set(roots))
        extra = sorted(set(roots) - set(expected))
        raise ValueError(f"done-file mismatch: missing={missing[:10]} extra={extra[:10]}")
    if not state_path.name.endswith("-state.txt"):
        raise ValueError("state filename must end in -state.txt")
    results = state_path.with_name(state_path.name[:-len("-state.txt")] + "-results.txt")
    if results.exists():
        subprocess.run([sys.executable, "verify.py", str(results)], check=True)
    print(f"VERIFIED HEAVY range={first}-{last} resume={resume} min_weight={minimum} "
          f"rows={len(roots)} candidates={state.get('candidates', 0)}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_heavy.py STATE_FILE")
    verify(sys.argv[1])
