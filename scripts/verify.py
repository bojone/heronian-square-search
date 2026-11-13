#!/usr/bin/env python3
import math
import sys


def verify(l: int, m: int, n: int, expected_area: int | None = None) -> int:
    sides = (l * l, m * m, n * n)
    s0 = sum(sides)
    s1 = -sides[0] + sides[1] + sides[2]
    s2 = sides[0] - sides[1] + sides[2]
    s3 = sides[0] + sides[1] - sides[2]
    heron = s0 * s1 * s2 * s3
    area4, exact = math.isqrt(heron), 0
    if heron <= 0 or area4 * area4 != heron or area4 % 4:
        raise ValueError(f"not an integer-area nondegenerate triangle: {l, m, n}")
    area = area4 // 4
    if math.gcd(l, m, n) != 1:
        raise ValueError(f"not primitive: {l, m, n}")
    if expected_area is not None and area != expected_area:
        raise ValueError(f"area mismatch: computed {area}, expected {expected_area}")
    print(f"VERIFIED roots=({l},{m},{n}) sides=({sides[0]},{sides[1]},{sides[2]}) area={area}")
    return area


if __name__ == "__main__":
    if len(sys.argv) == 1:
        verify(1853, 4380, 4427, 32918611718880)
        verify(11789, 68104, 68595, 284239560530875680)
    elif len(sys.argv) == 2:
        with open(sys.argv[1]) as source:
            for line in source:
                if line.strip() and not line.startswith("#"):
                    verify(*map(int, line.split()))
    elif len(sys.argv) in (4, 5):
        verify(*map(int, sys.argv[1:]))
    else:
        raise SystemExit("usage: verify.py [RESULTS_FILE | L M N [AREA]]")
