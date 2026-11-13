#!/usr/bin/env python3
import json
import math
import os
from fractions import Fraction
from pathlib import Path
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
BOUND = int(sys.argv[1]) if len(sys.argv) > 1 else 100
PREFIX = ROOT / os.environ.get("ELLIPTIC_PREFIX", f"elliptic-b{BOUND}")
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


MOD_PRIMES = (
    1000000007, 1000000009, 1000000021, 1000000033, 1000000087, 1000000093, 1000000097, 1000000103,
    1000000123, 1000000181, 1000000207, 1000000223, 1000000241, 1000000271, 1000000289, 1000000297,
    1000000321, 1000000349, 1000000363, 1000000403, 1000000409, 1000000411, 1000000427, 1000000433,
    1000000439, 1000000447, 1000000453, 1000000459, 1000000483, 1000000513, 1000000531, 1000000579,
    1000000607, 1000000613, 1000000637, 1000000663, 1000000711, 1000000753, 1000000787, 1000000801,
    1000000829, 1000000861, 1000000871, 1000000891, 1000000901, 1000000919, 1000000931, 1000000933,
    1000000993, 1000001011, 1000001021, 1000001053, 1000001087, 1000001099, 1000001137, 1000001161,
    1000001203, 1000001213, 1000001237, 1000001263, 1000001269, 1000001273, 1000001279, 1000001311,
)
BAD = object()


def modular_value(value, prime):
    if value.denominator % prime == 0:
        return BAD
    return value.numerator % prime * pow(value.denominator % prime, prime - 2, prime) % prime


def modular_point(point, prime):
    if point is None:
        return None
    x = modular_value(point[0], prime)
    y = modular_value(point[1], prime)
    return BAD if x is BAD or y is BAD else (x, y)


def modular_add(p, q, a, prime):
    if p is BAD or q is BAD:
        return BAD
    if p is None:
        return q
    if q is None:
        return p
    x1, y1 = p
    x2, y2 = q
    if x1 == x2:
        if (y1 + y2) % prime == 0 or y1 == 0:
            return None
        numerator = 3 * x1 * x1 + a
        denominator = 2 * y1
    else:
        numerator = y2 - y1
        denominator = x2 - x1
    denominator %= prime
    if denominator == 0:
        return BAD
    slope = numerator % prime * pow(denominator, prime - 2, prime) % prime
    x3 = (slope * slope - x1 - x2) % prime
    return x3, (slope * (x1 - x3) - y1) % prime


def multiple(point, n, a):
    if n == 0:
        return None
    result = None
    addend = point
    remaining = abs(n)
    while remaining:
        if remaining & 1:
            result = add(result, addend, a)
        remaining >>= 1
        if remaining:
            addend = add(addend, addend, a)
    if n < 0:
        result = result[0], -result[1]
    return result


def prepare_models(k, h, a, p, q):
    models = []
    for prime in MOD_PRIMES:
        mk = modular_value(k, prime)
        mh = modular_value(h, prime)
        ma = modular_value(a, prime)
        mp = modular_point(p, prime)
        mq = modular_point(q, prime)
        if BAD in (mk, mh, ma, mp, mq) or ma == 0:
            continue
        mps = {0: None}
        mqs = {0: None}
        valid = True
        for n in range(1, BOUND + 1):
            mps[n] = modular_add(mps[n - 1], mp, ma, prime)
            mqs[n] = modular_add(mqs[n - 1], mq, ma, prime)
            if mps[n] is BAD or mps[n] is None or mqs[n] is BAD or mqs[n] is None:
                valid = False
                break
            mps[-n] = mps[n][0], -mps[n][1] % prime
            mqs[-n] = mqs[n][0], -mqs[n][1] % prime
        if valid:
            h2 = 4 * mh * mh % prime
            constant = 2 * mk * pow(mh, prime - 2, prime) % prime
            models.append((prime, mk, ma, mps, mqs, h2, constant))
    return models


def passes_modular(models, n, m, coset):
    if not models:
        return True
    for prime, k, a, ps, qs, h2, constant in models:
        point = modular_add(ps[n], qs[m], a, prime)
        if point is BAD or point is None:
            continue
        if coset:
            point = modular_add(point, (0, 0), a, prime)
            if point is BAD or point is None:
                continue
        x, y = point
        if x == 0 or h2 == 0:
            continue
        denominator = h2 * x % prime
        numerator = (constant * denominator + x * x - (k * k - 1)**2 * h2) % prime
        if numerator != 0 and pow(numerator * denominator % prime, (prime - 1) // 2, prime) == prime - 1:
            return False
    return True


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
    models = prepare_models(k, h, a, p, q)
    coefficients = [0]
    for absolute in range(1, BOUND + 1):
        coefficients.extend((absolute, -absolute))
    print(f"FIBER {fiber} k={k} roots={roots} resume={next_n} models={len(models)}", flush=True)
    for position in range(next_n, len(coefficients)):
        n = coefficients[position]
        for m in range(-BOUND, BOUND + 1):
            if stop:
                save_state(fiber, position)
                return fiber, position
            point = None
            point_computed = False
            for coset in range(2):
                if not passes_modular(models, n, m, coset):
                    continue
                if not point_computed:
                    point = add(multiple(p, n, a), multiple(q, m, a), a)
                    point_computed = True
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
    first_fiber = int(os.environ.get("ELLIPTIC_FIBER_START", "0"))
    last_fiber = int(os.environ.get("ELLIPTIC_FIBER_STOP", "2"))
    if not 0 <= first_fiber <= last_fiber <= 2:
        raise RuntimeError("invalid fiber range")
    fiber, next_n = load_state()
    if fiber < first_fiber:
        fiber, next_n = first_fiber, 0
    seen = load_seen()
    known = [(1853, 4380, 4427), (11789, 68104, 68595)]
    while fiber < last_fiber and not stop:
        fiber, next_n = run_fiber(fiber, next_n, known[fiber], seen)
        if fiber == 2 and next_n != -BOUND:
            break
    if fiber >= last_fiber:
        save_state(fiber, 0)
    print(f"ELLIPTIC FINISHED fiber={fiber} next_n={next_n} classes={len(seen)} stop={stop}", flush=True)


if __name__ == "__main__":
    main()
