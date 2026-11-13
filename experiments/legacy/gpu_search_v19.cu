#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cuda_runtime.h>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <numeric>
#include <set>
#include <string>
#include <thread>
#include <vector>

using u128 = unsigned __int128;
using i128 = __int128;

struct Complex {
    i128 re;
    i128 im;
};

struct NumberInfo {
    uint32_t primes[8]{};
    uint32_t inert_primes[8]{};
    uint8_t exponents[8]{};
    uint64_t fixed = 1;
    uint8_t count = 0;
    uint8_t inert_count = 0;
};

struct PrimeData {
    std::array<uint32_t, 32> offsets{};
    std::vector<Complex> values;
};

struct Term {
    const Complex* values;
    uint32_t size;
    uint32_t central;
};

struct Hit {
    uint64_t l;
    uint64_t m;
    uint64_t n;
    i128 area4;
};

struct PairContext {
    uint64_t l;
    uint64_t m;
    u128 l4;
    u128 m4;
    u128 n4;
    i128 lower_d;
    i128 upper_d;
    uint32_t flags;
};

static std::atomic<bool> stop_requested{false};
static __constant__ uint8_t mod625[625];
static __constant__ uint8_t mod9[9];
static __constant__ uint8_t mod7[7];
static __constant__ uint8_t mod13[13];
static __constant__ uint8_t mod17[17];

static void request_stop(int) {
    stop_requested.store(true);
}

static __host__ __device__ Complex multiply(Complex a, Complex b) {
    return {a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re};
}

static __host__ __device__ Complex conjugate(Complex a) {
    return {a.re, -a.im};
}

static uint64_t integer_power(uint64_t a, uint32_t n) {
    uint64_t result = 1;
    while (n--) result *= a;
    return result;
}

static __host__ __device__ uint64_t gcd64(uint64_t a, uint64_t b) {
    while (b) {
        uint64_t r = a % b;
        a = b;
        b = r;
    }
    return a;
}

static std::string string128(i128 value) {
    if (value == 0) return "0";
    bool negative = value < 0;
    u128 n = negative ? u128(-(value + 1)) + 1 : u128(value);
    std::string result;
    while (n) {
        result.push_back(char('0' + n % 10));
        n /= 10;
    }
    if (negative) result.push_back('-');
    std::reverse(result.begin(), result.end());
    return result;
}

template <uint32_t P>
static __host__ __device__ uint32_t residue(u128 value) {
    constexpr uint64_t shift = (u128(1) << 64) % P;
    uint64_t low = uint64_t(value) % P;
    uint64_t high = uint64_t(value >> 64) % P;
    return (low + high * shift) % P;
}

template <size_t M>
static std::array<uint8_t, M> fourth_residues() {
    std::array<uint8_t, M> result{};
    for (uint64_t n = 0; n < M; ++n) result[(n * n % M) * n % M * n % M] = 1;
    return result;
}

static __device__ void test_d(i128 d, i128 area4, const PairContext& ctx, Hit* hits,
                              uint32_t* hit_count, uint64_t& candidates) {
    ++candidates;
    i128 signed_z = i128(ctx.l4) + i128(ctx.m4) - d;
    if (signed_z < 0 || u128(signed_z) < ctx.m4 || u128(signed_z) > ctx.n4) return;
    u128 z = signed_z;
    uint64_t low = uint64_t(z) & 15;
    if (low != 0 && low != 1) return;
    if (ctx.flags & 2U) {
        if (residue<625>(z) != 0) return;
    } else if (!mod625[residue<625>(z)]) return;
    if (!mod9[residue<9>(z)] || !mod7[residue<7>(z)] ||
        !mod13[residue<13>(z)] || !mod17[residue<17>(z)]) return;
    uint64_t root = sqrt(sqrt((double)z));
    while (root > 0 && u128(root) * root * root * root > z) --root;
    while (u128(root + 1) * (root + 1) * (root + 1) * (root + 1) <= z) ++root;
    if (u128(root) * root * root * root != z) return;
    if (gcd64(gcd64(ctx.l, ctx.m), root) != 1) return;
    if ((ctx.l % 5 && ctx.m % 5 && root % 5) || root < ctx.m) return;
    uint32_t index = atomicAdd(hit_count, 1U);
    if (index < 4096) hits[index] = {ctx.l, ctx.m, root, area4};
}

static __device__ void test_pair(i128 d, i128 area4, const PairContext& ctx, Hit* hits,
                                 uint32_t* hit_count, uint64_t& candidates) {
    if (area4 == 0 || (uint64_t(area4) & 7) != 0) return;
    bool positive = d >= ctx.lower_d && d <= ctx.upper_d;
    bool negative = -d >= ctx.lower_d && -d <= ctx.upper_d;
    if (!positive && !negative) return;
    i128 absolute = area4 < 0 ? -area4 : area4;
    u128 area_value = u128(absolute);
    if (residue<3>(area_value) != 0) return;
    if ((ctx.flags & 1U) && residue<9>(area_value) != 0) return;
    if ((ctx.flags & 2U) && residue<5>(area_value) != 0) return;
    if (positive) test_d(d, area4, ctx, hits, hit_count, candidates);
    if (negative && d != 0) test_d(-d, area4, ctx, hits, hit_count, candidates);
}

static __device__ void test_all(Complex z, const PairContext& ctx, Hit* hits,
                                uint32_t* hit_count, uint64_t& candidates) {
    test_pair(z.re, z.im, ctx, hits, hit_count, candidates);
    if (z.re != z.im && z.re != -z.im) test_pair(z.im, z.re, ctx, hits, hit_count, candidates);
}

static __device__ void test_product(Complex a, Complex b, const PairContext& ctx, Hit* hits,
                                    uint32_t* hit_count, uint64_t& candidates) {
    uint64_t re = uint64_t(a.re) * uint64_t(b.re) - uint64_t(a.im) * uint64_t(b.im);
    uint64_t im = uint64_t(a.re) * uint64_t(b.im) + uint64_t(a.im) * uint64_t(b.re);
    uint64_t lm = uint64_t(ctx.l4) + uint64_t(ctx.m4);
    bool first = (im & 7) == 0 && (((lm - re) & 15) <= 1 || ((lm + re) & 15) <= 1);
    bool second = (re - im) & 15 && (re + im) & 15 && (re & 7) == 0 &&
                  (((lm - im) & 15) <= 1 || ((lm + im) & 15) <= 1);
    if (first || second) test_all(multiply(a, b), ctx, hits, hit_count, candidates);
}

static __device__ void enumerate(const Term* terms, uint32_t count, uint32_t depth, Complex z,
                                 bool free_choice, const PairContext& ctx, Hit* hits,
                                 uint32_t* hit_count, uint64_t& candidates) {
    if (depth == 0 && count == 1) {
        for (uint32_t r = 0; r <= terms[0].central; ++r)
            test_product(z, terms[0].values[r], ctx, hits, hit_count, candidates);
        return;
    }
    if (depth == 0 && count == 2) {
        for (uint32_t r = 0; r <= terms[0].central; ++r) {
            Complex first = multiply(z, terms[0].values[r]);
            bool free = r < terms[0].central;
            uint32_t last = free ? terms[1].size - 1 : terms[1].central;
            for (uint32_t s = 0; s <= last; ++s)
                test_product(first, terms[1].values[s], ctx, hits, hit_count, candidates);
        }
        return;
    }
    if (depth == 0 && count == 3) {
        for (uint32_t r = 0; r <= terms[0].central; ++r) {
            Complex first = multiply(z, terms[0].values[r]);
            bool free_r = r < terms[0].central;
            uint32_t last_s = free_r ? terms[1].size - 1 : terms[1].central;
            for (uint32_t s = 0; s <= last_s; ++s) {
                Complex second = multiply(first, terms[1].values[s]);
                bool free_s = free_r || s < terms[1].central;
                uint32_t last_t = free_s ? terms[2].size - 1 : terms[2].central;
                for (uint32_t t = 0; t <= last_t; ++t)
                    test_product(second, terms[2].values[t], ctx, hits, hit_count, candidates);
            }
        }
        return;
    }
    if (depth < count) {
        for (uint32_t r = 0; r < terms[depth].size; ++r) {
            if (!free_choice && r > terms[depth].central) continue;
            enumerate(terms, count, depth + 1, multiply(z, terms[depth].values[r]),
                      free_choice || r < terms[depth].central, ctx, hits, hit_count, candidates);
        }
        return;
    }
    test_all(z, ctx, hits, hit_count, candidates);
}

static __global__ void search_kernel(uint64_t n, uint64_t first_l, const NumberInfo* info,
                                     const u128* fourth, const uint8_t* has_inert,
                                     const uint32_t* prime_offsets, const Complex* values,
                                     Hit* hits, uint32_t* hit_count, uint64_t* candidate_total) {
    constexpr uint32_t split = 4;
    uint64_t l = first_l + blockIdx.x / split;
    uint32_t slice = blockIdx.x % split;
    uint64_t candidates = 0;
    for (uint64_t m = l + slice * blockDim.x + threadIdx.x; m <= n; m += split * blockDim.x) {
        if ((l & 1) == 0 && (m & 1) == 0) continue;
        const NumberInfo& a = info[l];
        bool shared_inert = false;
        for (uint32_t k = 0; k < a.inert_count; ++k) {
            if (m % a.inert_primes[k] == 0) {
                shared_inert = true;
                break;
            }
        }
        if (shared_inert) continue;
        const NumberInfo& b = info[m];
        Term terms[16];
        uint32_t count = 0;
        uint32_t i = 0;
        uint32_t j = 0;
        while (i < a.count || j < b.count) {
            uint32_t p;
            uint32_t exponent;
            if (j == b.count || (i < a.count && a.primes[i] < b.primes[j])) {
                p = a.primes[i];
                exponent = a.exponents[i++];
            } else if (i == a.count || b.primes[j] < a.primes[i]) {
                p = b.primes[j];
                exponent = b.exponents[j++];
            } else {
                p = a.primes[i];
                exponent = a.exponents[i] + b.exponents[j];
                ++i;
                ++j;
            }
            terms[count++] = {values + prime_offsets[32 * p + exponent], 4 * exponent + 1, 2 * exponent};
        }
        if (count == 0) continue;
        PairContext ctx{l, m, fourth[l], fourth[m], fourth[n],
                        i128(fourth[l]) + i128(fourth[m]) - i128(fourth[n]), i128(fourth[l]),
                        ((l % 3 == 0 || m % 3 == 0) ? 1U : 0U) |
                        ((l % 5 != 0 && m % 5 != 0) ? 2U : 0U)};
        i128 base = i128(2) * a.fixed * b.fixed;
        enumerate(terms, count, 0, {base, 0}, false, ctx, hits, hit_count, candidates);
    }
    if (candidates) atomicAdd(reinterpret_cast<unsigned long long*>(candidate_total),
                              static_cast<unsigned long long>(candidates));
}

class Search {
public:
    Search(uint64_t limit, uint64_t first, uint64_t last, std::string output, std::string state)
        : n(limit), begin(first), end(last), results_file(std::move(output)), state_file(std::move(state)),
          spf(n + 1), info(n + 1), prime_data(n + 1), fourth(n + 1), has_inert(n + 1) {}

    void prepare() {
        for (uint64_t i = 2; i <= n; ++i) {
            if (spf[i] == 0) {
                spf[i] = i;
                if (i <= n / i)
                    for (uint64_t j = i * i; j <= n; j += i)
                        if (spf[j] == 0) spf[j] = i;
            }
        }
        spf[1] = 1;
        for (uint64_t i = 1; i <= n; ++i) {
            uint64_t x = i;
            uint64_t fixed = 1;
            bool inert = false;
            while (x > 1) {
                uint32_t p = spf[x];
                uint32_t a = 0;
                do {
                    x /= p;
                    ++a;
                } while (x % p == 0);
                if (p % 4 == 1) {
                    info[i].primes[info[i].count] = p;
                    info[i].exponents[info[i].count] = a;
                    ++info[i].count;
                } else {
                    fixed *= integer_power(p, 2 * a);
                    if (p % 4 == 3) {
                        info[i].inert_primes[info[i].inert_count] = p;
                        ++info[i].inert_count;
                        inert = true;
                    }
                }
            }
            info[i].fixed = fixed;
            has_inert[i] = inert;
            fourth[i] = u128(i) * i * i * i;
        }
        prepare_gaussian_primes();
        flatten_prime_data();
    }

    void run() {
        auto h625 = fourth_residues<625>();
        auto h9 = fourth_residues<9>();
        auto h7 = fourth_residues<7>();
        auto h13 = fourth_residues<13>();
        auto h17 = fourth_residues<17>();
        cudaMemcpyToSymbol(mod625, h625.data(), h625.size());
        cudaMemcpyToSymbol(mod9, h9.data(), h9.size());
        cudaMemcpyToSymbol(mod7, h7.data(), h7.size());
        cudaMemcpyToSymbol(mod13, h13.data(), h13.size());
        cudaMemcpyToSymbol(mod17, h17.data(), h17.size());
        NumberInfo* d_info;
        u128* d_fourth;
        uint8_t* d_inert;
        uint32_t* d_offsets;
        Complex* d_values;
        Hit* d_hits;
        uint32_t* d_hit_count;
        uint64_t* d_candidates;
        cudaMalloc(&d_info, info.size() * sizeof(info[0]));
        cudaMalloc(&d_fourth, fourth.size() * sizeof(fourth[0]));
        cudaMalloc(&d_inert, has_inert.size());
        cudaMalloc(&d_offsets, prime_offsets.size() * sizeof(uint32_t));
        cudaMalloc(&d_values, values.size() * sizeof(Complex));
        cudaMalloc(&d_hits, 4096 * sizeof(Hit));
        cudaMalloc(&d_hit_count, sizeof(uint32_t));
        cudaMalloc(&d_candidates, sizeof(uint64_t));
        cudaMemcpy(d_info, info.data(), info.size() * sizeof(info[0]), cudaMemcpyHostToDevice);
        cudaMemcpy(d_fourth, fourth.data(), fourth.size() * sizeof(fourth[0]), cudaMemcpyHostToDevice);
        cudaMemcpy(d_inert, has_inert.data(), has_inert.size(), cudaMemcpyHostToDevice);
        cudaMemcpy(d_offsets, prime_offsets.data(), prime_offsets.size() * sizeof(uint32_t), cudaMemcpyHostToDevice);
        cudaMemcpy(d_values, values.data(), values.size() * sizeof(Complex), cudaMemcpyHostToDevice);
        cudaMemset(d_hit_count, 0, sizeof(uint32_t));
        cudaMemset(d_candidates, 0, sizeof(uint64_t));
        if (!state_file.empty()) {
            std::ifstream state(state_file);
            std::string key, value;
            uint64_t stored_limit = 0, stored_end = 0, saved = begin;
            while (state >> key >> value) {
                if (key == "limit") stored_limit = std::stoull(value);
                if (key == "end") stored_end = std::stoull(value);
                if (key == "resume") saved = std::stoull(value);
            }
            if (stored_limit && (stored_limit != n || stored_end != end || saved < begin)) {
                std::cerr << "checkpoint does not match requested range\n";
                return;
            }
            begin = saved;
        }
        std::ofstream out(results_file, std::ios::app);
        std::ifstream old_results(results_file);
        uint64_t l, m, root;
        std::string area;
        while (old_results >> l >> m >> root >> area) seen.insert({l, m, root});
        auto start = std::chrono::steady_clock::now();
        uint64_t next = begin;
        uint32_t previous_hit_count = 0;
        while (next <= end && !stop_requested.load()) {
            uint32_t batch = uint32_t(std::min<uint64_t>(512, end - next + 1));
            search_kernel<<<batch * 4, 256>>>(n, next, d_info, d_fourth, d_inert, d_offsets,
                                          d_values, d_hits, d_hit_count, d_candidates);
            cudaError_t error = cudaDeviceSynchronize();
            if (error != cudaSuccess) {
                std::cerr << cudaGetErrorString(error) << '\n';
                return;
            }
            uint32_t hit_count;
            uint64_t candidates;
            cudaMemcpy(&hit_count, d_hit_count, sizeof(hit_count), cudaMemcpyDeviceToHost);
            cudaMemcpy(&candidates, d_candidates, sizeof(candidates), cudaMemcpyDeviceToHost);
            if (hit_count > previous_hit_count) {
                uint32_t count = std::min(hit_count, 4096U);
                std::vector<Hit> hits(count);
                cudaMemcpy(hits.data(), d_hits, count * sizeof(Hit), cudaMemcpyDeviceToHost);
                for (uint32_t i = previous_hit_count; i < count; ++i) {
                    if (!seen.insert({hits[i].l, hits[i].m, hits[i].n}).second) continue;
                    i128 area4 = hits[i].area4 < 0 ? -hits[i].area4 : hits[i].area4;
                    out << hits[i].l << ' ' << hits[i].m << ' ' << hits[i].n << ' ' << string128(area4 / 4) << '\n';
                }
                out.flush();
                previous_hit_count = hit_count;
            }
            next += batch;
            if (!state_file.empty()) {
                std::filesystem::path temporary = state_file + ".tmp";
                {
                    std::ofstream state(temporary);
                    state << "version 1\nlimit " << n << "\nbegin " << begin << "\nend " << end
                          << "\nresume " << next << "\ncandidates " << candidates << '\n';
                }
                std::filesystem::rename(temporary, state_file);
            }
            double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            std::cout << "PROGRESS resume " << next << " candidates " << candidates
                      << " seconds " << uint64_t(seconds) << std::endl;
        }
        cudaFree(d_info);
        cudaFree(d_fourth);
        cudaFree(d_inert);
        cudaFree(d_offsets);
        cudaFree(d_values);
        cudaFree(d_hits);
        cudaFree(d_hit_count);
        cudaFree(d_candidates);
    }

private:
    uint64_t n;
    uint64_t begin;
    uint64_t end;
    std::string results_file;
    std::string state_file;
    std::set<std::array<uint64_t, 3>> seen;
    std::vector<uint32_t> spf;
    std::vector<NumberInfo> info;
    std::vector<std::unique_ptr<PrimeData>> prime_data;
    std::vector<u128> fourth;
    std::vector<uint8_t> has_inert;
    std::vector<uint32_t> prime_offsets;
    std::vector<Complex> values;

    void prepare_gaussian_primes() {
        for (uint64_t p = 5; p <= n; p += 2) {
            if (p % 4 != 1 || spf[p] != p) continue;
            uint64_t u = 1;
            uint64_t v = 0;
            for (; u * u <= p; ++u) {
                v = std::sqrt(double(p - u * u));
                if (v * v == p - u * u) break;
            }
            auto data = std::make_unique<PrimeData>();
            uint32_t max_a = 0;
            for (uint64_t power = p; power <= n; power *= p) ++max_a;
            max_a *= 2;
            Complex pi{u, v};
            for (uint32_t a = 1; a <= max_a; ++a) {
                data->offsets[a] = data->values.size();
                std::vector<Complex> powers(4 * a + 1);
                powers[0] = {1, 0};
                for (uint32_t r = 1; r <= 4 * a; ++r) powers[r] = multiply(powers[r - 1], pi);
                for (uint32_t r = 0; r <= 4 * a; ++r)
                    data->values.push_back(multiply(powers[r], conjugate(powers[4 * a - r])));
            }
            prime_data[p] = std::move(data);
        }
    }

    void flatten_prime_data() {
        prime_offsets.assign((n + 1) * 32, UINT32_MAX);
        for (uint64_t p = 5; p <= n; ++p) {
            const auto* data = prime_data[p].get();
            if (!data) continue;
            uint32_t base = values.size();
            for (uint32_t a = 1; a < 32 && (a == 1 || data->offsets[a] != 0); ++a)
                prime_offsets[32 * p + a] = base + data->offsets[a];
            values.insert(values.end(), data->values.begin(), data->values.end());
        }
        std::cerr << "flattened " << values.size() << " Gaussian values\n";
    }
};

int main(int argc, char** argv) {
    if (argc < 5 || argc > 7) {
        std::cerr << "usage: gpu_search LIMIT FIRST_L LAST_L RESULTS_FILE [GPU [STATE_FILE]]\n";
        return 2;
    }
    uint64_t n = std::stoull(argv[1]);
    uint64_t first = std::stoull(argv[2]);
    uint64_t last = std::stoull(argv[3]);
    int device = argc >= 6 ? std::stoi(argv[5]) : 0;
    std::string state = argc == 7 ? argv[6] : "";
    cudaSetDevice(device);
    cudaDeviceSetLimit(cudaLimitStackSize, 8192);
    std::signal(SIGTERM, request_stop);
    std::signal(SIGINT, request_stop);
    Search search(n, first, last, argv[4], state);
    auto start = std::chrono::steady_clock::now();
    search.prepare();
    std::cerr << "prepared in "
              << std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count()
              << " seconds\n";
    search.run();
    return 0;
}
