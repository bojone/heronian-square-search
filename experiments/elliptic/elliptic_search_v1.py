#!/usr/bin/env python3
import json
import math
from fractions import Fraction
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BOUND = int(sys.argv[1]) if len(sys.argv) > 1 else 100
PREFIX = ROOT / f"elliptic-b{BOUND}"
STATE = PREFIX.with_name(PREFIX.name + "-state.txt")
HITS = PREFIX.with_name(PREFIX.name + "-hits.jsonl")
NEW = ROOT / "elliptic-new-results.txt"
stop = False


def add(p, q, a):
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    if x1 == x2:
        if y1 == -y2:
            return None
        slope = (3 * x1 * x1 + a) / (2 * y1)
        x3 = slope * slope - 2 * x1
        return x3, slope * (x1 - x3) - y1
    slope = (y2 - y1) / (x2 - x1)
    x3 = slope * slope - x1 - x2
    return x3, slope * (x1 - x3) - y1


SQUARE_MOD16 = {0, 1, 4, 9}
SQUARE_MOD9 = {0, 1, 4, 7}
SQUARE_MOD25 = {0, 1, 4, 6, 9, 11, 14, 16, 19, 21, 24}


def square_integer(value):
    if value & 15 not in SQUARE_MOD16 or value % 9 not in SQUARE_MOD9 or value % 25 not in SQUARE_MOD25:
        return None
    root = math.isqrt(value)
    return root if root * root == value else None


def square_root(value):
    if value <= 0:
        return None
    root_denominator = square_integer(value.denominator)
    if root_denominator is None:
        return None
    root_numerator = square_integer(value.numerator)
    if root_numerator is None:
        return None
    return Fraction(root_numerator, root_denominator)


def known_point(roots):
    u, w, c = map(Fraction, roots)
    q = w / u
    r = c * c / (u * u)
    a = (1 + r * r - q**4) / (2 * r)
    b2 = 1 - a * a
    root_numerator, root_denominator = math.isqrt(b2.numerator), math.isqrt(b2.denominator)
    b = -Fraction(root_numerator, root_denominator)
    k = a / (1 - b)
    h = k * k + 1
    x = 2 * h * h * (q * q + r - a)
    y = 4 * h**3 * q * (q * q + r - a)
    return k, (x, y)


def save_state(fiber, next_n):
    temporary = STATE.with_suffix(".tmp")
    temporary.write_text(f"bound {BOUND}\nfiber {fiber}\nnext_n {next_n}\n")
    temporary.replace(STATE)


def load_state():
    if not STATE.exists():
        return 0, 0
    values = {key: int(value) for key, value in (line.split() for line in STATE.read_text().splitlines())}
    if values.get("bound") != BOUND:
        raise RuntimeError("checkpoint bound mismatch")
    return values["fiber"], max(0, values["next_n"])


def load_seen():
    seen = set()
    if HITS.exists():
        for line in HITS.read_text().splitlines():
            entry = json.loads(line)
            seen.add((entry["class_q_squared"], entry["class_r"]))
    return seen


def integral_roots(q, rroot):
    q = abs(q)
    denominator = math.lcm(q.denominator, rroot.denominator)
    roots = [denominator, q.numerator * (denominator // q.denominator),
             rroot.numerator * (denominator // rroot.denominator)]
    divisor = math.gcd(*roots)
    return [value // divisor for value in roots]


def verify_new(roots):
    result = subprocess.run(["python3", str(ROOT / "verify.py"), *map(str, roots)],
                            cwd=ROOT, text=True, capture_output=True)
    return result.returncode == 0, result.stdout + result.stderr


def request_stop(signum, frame):
    global stop
    stop = True


def run_fiber(fiber, next_n, roots, seen):
    k, p = known_point(roots)
    h = k * k + 1
    a = 4 * (k**4 - 1)**2
    q = 2 * h * (k + 1)**2, 4 * h * h * (k + 1)**2
    torsion = Fraction(0), Fraction(0)
    ps = {0: None}
    qs = {0: None}
    for n in range(1, BOUND + 1):
        ps[n] = add(ps[n - 1], p, a)
        ps[-n] = ps[n][0], -ps[n][1]
        qs[n] = add(qs[n - 1], q, a)
        qs[-n] = qs[n][0], -qs[n][1]
    coefficients = [0]
    for absolute in range(1, BOUND + 1):
        coefficients.extend((absolute, -absolute))
    print(f"FIBER {fiber} k={k} roots={roots} resume={next_n}", flush=True)
    for position in range(next_n, len(coefficients)):
        n = coefficients[position]
        for m in range(-BOUND, BOUND + 1):
            if stop:
                save_state(fiber, position)
                return fiber, position
            point = add(ps[n], qs[m], a)
            for coset in range(2):
                current = point if coset == 0 else add(point, torsion, a)
                if current is None or current[0] == 0:
                    continue
                x, y = current
                r = 2 * k / h + x / (4 * h * h) - (k * k - 1)**2 / x
                rroot = square_root(r)
                if rroot is None:
                    continue
                ratio = y / (2 * h * x)
                class_q_squared = str(ratio * ratio)
                class_r = str(r)
                key = class_q_squared, class_r
                if key in seen:
                    continue
                seen.add(key)
                integer = integral_roots(ratio, rroot)
                valid, verification = verify_new(integer)
                entry = {"fiber": fiber, "n": n, "m": m, "coset": coset,
                         "class_q_squared": class_q_squared, "class_r": class_r,
                         "roots": integer, "primitive_heron": valid}
                with HITS.open("a") as output:
                    output.write(json.dumps(entry, separators=(",", ":")) + "\n")
                print(f"SQUARE {entry} {verification}", flush=True)
                if valid and tuple(integer) != tuple(roots):
                    with NEW.open("a") as output:
                        output.write(" ".join(map(str, integer)) + "\n")
                    return 2, position
        if position % 10 == 0:
            save_state(fiber, position + 1)
            print(f"PROGRESS fiber={fiber} next_position={position + 1} n={n} classes={len(seen)}", flush=True)
    save_state(fiber + 1, 0)
    return fiber + 1, 0


def main():
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    fiber, next_n = load_state()
    seen = load_seen()
    known = [(1853, 4380, 4427), (11789, 68104, 68595)]
    while fiber < len(known) and not stop:
        fiber, next_n = run_fiber(fiber, next_n, known[fiber], seen)
        if fiber == 2 and next_n != -BOUND:
            break
    if fiber >= len(known):
        save_state(fiber, 0)
    print(f"ELLIPTIC FINISHED fiber={fiber} next_n={next_n} classes={len(seen)} stop={stop}", flush=True)


if __name__ == "__main__":
    main()
