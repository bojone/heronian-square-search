# Algorithm and correctness

**[中文](ALGORITHM.md) | English**

This document describes the mathematical basis for the production CPU v18 and GPU v42 implementations, the exact result checks, and the coverage argument. Experimental directories do not contribute to the final completeness claim.

## 1. Problem formulation

For positive root sides $`l,m,n`$, the actual triangle sides are $`l^2,m^2,n^2`$. We require:

- a nondegenerate triangle;
- integer area $`A`$;
- $`\gcd(l,m,n)=1`$.

Primitivity is unchanged by squaring because

$$
\gcd(l^2,m^2,n^2)=\gcd(l,m,n)^2.
$$

Results are ordered as $`l\le m\le n`$ to eliminate permutations.

## 2. Heron to Pythagorean representations

Write $`X=l^2,Y=m^2,Z=n^2`$. Heron's formula states

$$
16A^2=(X+Y+Z)(-X+Y+Z)(X-Y+Z)(X+Y-Z).
$$

Define

$$
D=X^2+Y^2-Z^2=l^4+m^4-n^4.
$$

Expansion gives

$$
16A^2=2(X^2Y^2+Y^2Z^2+Z^2X^2)-(X^4+Y^4+Z^4),
$$

and consequently

$$
(4A)^2+D^2=(2XY)^2=(2l^2m^2)^2. \qquad(1)
$$

We therefore need only generate suitable Pythagorean representations and test whether

$$
n^4=l^4+m^4-D \qquad(2)
$$

is a fourth power. **There is no loop over $`n`$.**

## 3. Gaussian enumeration

The norm of a Gaussian integer $`a+ib`$ is

$$
N(a+ib)=a^2+b^2.
$$

Equation (1) says that $`D+4iA`$ has norm $`(2l^2m^2)^2`$. Unique factorization in the Gaussian integers allows us to generate every relevant representation from the integer factorization of $`2l^2m^2`$.

The implementation:

1. factors $`l`$ and $`m`$;
2. combines Gaussian powers of primes congruent to $`1\pmod4`$;
3. enumerates conjugate choices with central-symmetry deduplication;
4. assigns real and imaginary parts to $`D`$ and $`4A`$.

CPU Gaussian prime powers are prepared in `src/search_v18.cpp:285-307` and products are enumerated in `src/search_v18.cpp:373-434`.

GPU v42 additionally caches factor combinations. The production log records `274268594` cached Gaussian pair values; see `src/gpu_search_v42.cu:525-568`.

## 4. Inert-prime exclusion

A prime $`p\equiv3\pmod4`$ has $`-1`$ as a quadratic nonresidue.

Suppose $`p\mid\gcd(l,m)`$. Equation (1) and $`D=l^4+m^4-n^4`$ imply

$$
n^8+(4A)^2\equiv0\pmod p.
$$

If $`p\nmid n`$, then $`-1`$ would be a quadratic residue modulo $`p`$, a contradiction. Hence $`p\mid n`$, making the root triple nonprimitive.

Therefore root pairs sharing an inert prime can be skipped without losing primitive solutions. CPU v18 applies the 32-bit `inert_part` gcd in `src/search_v18.cpp:337-339`; GPU v42 avoids the gcd whenever it is provably unnecessary in `src/gpu_search_v42.cu:302-315`.

## 5. Candidate tests

Each representation undergoes:

- sign and range tests determined by ordered roots and the search limit;
- a check that $`l^4+m^4-D`$ is nonnegative and exactly $`n^4`$;
- necessary parity and modular conditions modulo 3, 5, 7, 9, 13, 16, 17, and 625;
- $`\gcd(l,m,n)=1`$;
- $`l\le m\le n`$, with $`n`$ inside the requested limit.

Approximate square roots are used only to locate the integer root. Exact 128-bit arithmetic then adjusts and tests the fourth power:

- CPU: `src/search_v18.cpp:455-478`;
- GPU: `src/gpu_search_v42.cu:158-178`.

Modular tables apply necessary congruence tests only; they do not replace exact verification. Root pairs with both entries even are skipped because they cannot be primitive.

## 6. Area and nondegeneracy checks

Before emitting a hit, CPU v18 recomputes all four Heron factors, requires them to be positive, and compares their product with $`(4A)^2`$ using 256-bit integers (`src/search_v18.cpp:481-507`).

GPU results must additionally pass `scripts/verify.py`, which uses Python arbitrary-precision integers to verify:

- all Heron factors are positive;
- their product is a perfect square;
- the square root is divisible by 4, yielding an integer area;
- the root gcd is 1;
- a supplied area matches the computed one.

See `scripts/verify.py:6-22`.

## 7. Why the result is not a floating-point heuristic

The conclusion rests on three layers:

1. **Algebraic enumeration:** equation (1) covers every relevant Gaussian representation of $`D+4iA`$.
2. **Exact filtering:** fourth powers, gcd, nondegeneracy, and area are checked with integer arithmetic.
3. **Independent verification:** every nonempty result file is checked again by `verify.py`.

Floating-point estimates do not create new solutions and do not turn nonintegral areas into integers.

## 8. Checkpoints and complete coverage

### CPU checkpoints

CPU states contain `limit`, `begin`, `end`, `resume`, `pairs`, and `candidates`. `resume` is the next position after a continuously completed prefix, not merely the largest position claimed by any worker.

The final main state is:

```text
limit 10000000
begin 1180045
end 10000000
resume 10000001
pairs 38895816330946
candidates 1501947057268700
```

### GPU checkpoints

Each GPU interval contains 12500 root positions, processed in batches of at most 512. Validation requires:

- consistent `limit`, `end`, and `resume` fields;
- every `PROGRESS resume` increment to be exactly 512, except the final short batch;
- an unbroken log chain from the interval start to `end+1`;
- `resume == end + 1` at completion.

A final state alone is insufficient without its continuous log chain.

### Merging coverage

`complete_intervals` merges only accepted contiguous intervals. Main-search prefixes, GPU intervals, CPU lookahead intervals, and heavy-root intervals with verified `.done` files may overlap, but overlaps are not double-counted.

Only

```json
"complete_intervals": [[1, 10000000]]
```

establishes complete target coverage. Partial coverage cannot support a claim that no third solution exists.

## 9. Computational cost

There are still $`O(N^2)`$ ordered root pairs, but the work per pair is determined by its Gaussian representations rather than by another independent loop over $`n`$. Actual cost varies strongly with integer factor structure and cacheability.

Candidate counters describe particular filter entry points. They must not be compared across versions without matching the interval, counter definition, workload, and output.

## 10. Final conclusion

The exhaustive search and coverage audit completed for $`N=10^7`$. The 17 nonempty result files contain 34 lines, all independently verified to represent only the two known solutions.

Thus **no third primitive Heronian triangle with square sides and root sides bounded by $`10^7`$ was found**. Larger root sides remain open, and this is not a general nonexistence theorem.
