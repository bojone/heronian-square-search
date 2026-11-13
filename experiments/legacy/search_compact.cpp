#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <mutex>
#include <numeric>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using u128 = unsigned __int128;
using i128 = __int128;

struct U256 {
    std::array<uint64_t, 4> limb{};

    explicit U256(u128 value = 0) {
        limb[0] = uint64_t(value);
        limb[1] = uint64_t(value >> 64);
    }
};

static U256 multiply256(const U256& a, const U256& b) {
    std::array<uint64_t, 8> out{};
    for (size_t i = 0; i < 4; ++i) {
        u128 carry = 0;
        for (size_t j = 0; j < 4; ++j) {
            u128 current = u128(a.limb[i]) * b.limb[j] + out[i + j] + carry;
            out[i + j] = uint64_t(current);
            carry = current >> 64;
        }
        size_t k = i + 4;
        while (carry && k < 8) {
            u128 current = u128(out[k]) + carry;
            out[k++] = uint64_t(current);
            carry = current >> 64;
        }
    }
    U256 result;
    std::copy_n(out.begin(), 4, result.limb.begin());
    return result;
}

static bool operator==(const U256& a, const U256& b) {
    return a.limb == b.limb;
}

struct Complex {
    i128 re;
    i128 im;
};

struct SmallComplex {
    int64_t re;
    int64_t im;

    SmallComplex(Complex value) : re(int64_t(value.re)), im(int64_t(value.im)) {}
};

struct NumberInfo {
    std::array<uint32_t, 8> primes{};
    std::array<uint8_t, 8> exponents{};
    uint64_t fixed = 1;
    uint8_t count = 0;
};

struct PrimeData {
    std::array<uint32_t, 32> offsets{};
    std::vector<SmallComplex> values;
};

struct Term {
    const SmallComplex* values;
    uint32_t size;
    uint32_t central;
};

struct Hit {
    uint64_t l;
    uint64_t m;
    uint64_t n;
    i128 area4;
};

static std::atomic<bool> stop_requested{false};
static thread_local uint32_t pair_flags = 0;

static void request_stop(int) {
    stop_requested.store(true);
}

static Complex multiply(Complex a, Complex b) {
    return {a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re};
}

static Complex multiply(Complex a, SmallComplex b) {
    return {a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re};
}

static Complex scale(Complex a, i128 scale_factor) {
    return {a.re * scale_factor, a.im * scale_factor};
}

static Complex conjugate(Complex a) {
    return {a.re, -a.im};
}

static uint64_t integer_power(uint64_t a, uint32_t n) {
    uint64_t result = 1;
    while (n--) result *= a;
    return result;
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
static uint32_t residue(u128 value) {
    constexpr uint64_t shift = (u128(1) << 64) % P;
    uint64_t low = uint64_t(value) % P;
    uint64_t high = uint64_t(value >> 64) % P;
    return (low + high * shift) % P;
}

template <size_t M>
static std::array<bool, M> fourth_residues() {
    std::array<bool, M> result{};
    for (uint64_t n = 0; n < M; ++n) result[(n * n % M) * n % M * n % M] = true;
    return result;
}

class Search {
public:
    Search(uint64_t limit, uint64_t first, uint64_t last, uint32_t thread_count,
           std::string state_path, std::string results_path)
        : n(limit), begin(first), end(last), threads(thread_count),
          state_file(std::move(state_path)), results_file(std::move(results_path)),
          spf(n + 1), info(n + 1), prime_data(n + 1), fourth(n + 1),
          has_inert(n + 1), completed(last - first + 1) {
        for (auto& flag : completed) flag.store(false);
    }

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
                    if (p % 4 == 3) inert = true;
                }
            }
            info[i].fixed = fixed;
            has_inert[i] = inert;
            fourth[i] = u128(i) * i * i * i;
        }
        prepare_gaussian_primes();
    }

    void run() {
        std::ofstream results(results_file, std::ios::app);
        results.close();
        std::ifstream old_results(results_file);
        uint64_t l, m, root;
        std::string area;
        while (old_results >> l >> m >> root >> area) seen.insert({l, m, root});
        next.store(begin);
        resume.store(begin);
        start_time = Clock::now();
        std::vector<std::thread> workers;
        for (uint32_t t = 0; t < threads; ++t)
            workers.emplace_back([this] { work(); });
        uint64_t total = end - begin + 1;
        uint32_t ticks = 0;
        while (completed_count.load() < total && !stop_requested.load()) {
            std::this_thread::sleep_for(std::chrono::seconds(1));
            if (++ticks % 10 == 0) {
                save_checkpoint();
                log_progress();
            }
        }
        for (auto& worker : workers) worker.join();
        save_checkpoint();
        log_progress();
    }

private:
    using Clock = std::chrono::steady_clock;

    uint64_t n;
    uint64_t begin;
    uint64_t end;
    uint32_t threads;
    std::string state_file;
    std::string results_file;
    std::vector<uint32_t> spf;
    std::vector<NumberInfo> info;
    std::vector<std::unique_ptr<PrimeData>> prime_data;
    std::vector<u128> fourth;
    std::vector<bool> has_inert;
    std::vector<std::atomic<uint8_t>> completed;
    std::atomic<uint64_t> next{0};
    std::atomic<uint64_t> resume{0};
    std::atomic<uint64_t> pair_count{0};
    std::atomic<uint64_t> candidate_count{0};
    std::atomic<uint64_t> completed_count{0};
    std::atomic<bool> finished{false};
    std::mutex output_mutex;
    std::set<std::array<uint64_t, 3>> seen;
    Clock::time_point start_time;

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

    void work() {
        uint64_t local_candidates = 0;
        while (!stop_requested.load(std::memory_order_relaxed)) {
            uint64_t l = next.fetch_add(1);
            if (l > end) break;
            if (!process_l(l, local_candidates)) {
                candidate_count.fetch_add(local_candidates);
                break;
            }
            completed[l - begin].store(true);
            completed_count.fetch_add(1);
            pair_count.fetch_add(l > n ? 0 : n - l + 1);
            candidate_count.fetch_add(local_candidates);
            local_candidates = 0;
        }
        if (next.load() > end || stop_requested.load()) finished.store(true);
    }

    bool process_l(uint64_t l, uint64_t& candidates) {
        for (uint64_t m = l; m <= n; ++m) {
            if ((m & 255U) == 0 && stop_requested.load(std::memory_order_relaxed)) return false;
            if ((l & 1) == 0 && (m & 1) == 0) continue;
            uint64_t g = std::gcd(l, m);
            if (g > 1 && has_inert[g]) continue;
            const auto& a = info[l];
            const auto& b = info[m];
            std::array<Term, 16> terms;
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
                const auto* data = prime_data[p].get();
                terms[count++] = {data->values.data() + data->offsets[exponent], 4 * exponent + 1, 2 * exponent};
            }
            if (count == 0) continue;
            pair_flags = ((l % 3 == 0 || m % 3 == 0) ? 1U : 0U) |
                         ((l % 5 != 0 && m % 5 != 0) ? 2U : 0U);
            i128 base = i128(2) * a.fixed * b.fixed;
            enumerate(terms.data(), count, 0, {base, 0}, false, l, m, candidates);
        }
        return true;
    }

    void enumerate(const Term* terms, uint32_t count, uint32_t depth, Complex z, bool free_choice,
                   uint64_t l, uint64_t m, uint64_t& candidates) {
        if (depth == 0 && count == 1) {
            for (uint32_t r = 0; r <= terms[0].central; ++r)
                test_all(multiply(z, terms[0].values[r]), l, m, candidates);
            return;
        }
        if (depth == 0 && count == 2) {
            for (uint32_t r = 0; r <= terms[0].central; ++r) {
                Complex first = multiply(z, terms[0].values[r]);
                bool free = r < terms[0].central;
                uint32_t last = free ? terms[1].size - 1 : terms[1].central;
                for (uint32_t s = 0; s <= last; ++s)
                    test_all(multiply(first, terms[1].values[s]), l, m, candidates);
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
                        test_all(multiply(second, terms[2].values[t]), l, m, candidates);
                }
            }
            return;
        }
        if (depth == 0 && count == 4) {
            for (uint32_t r = 0; r <= terms[0].central; ++r) {
                Complex first = multiply(z, terms[0].values[r]);
                bool free_r = r < terms[0].central;
                uint32_t last_s = free_r ? terms[1].size - 1 : terms[1].central;
                for (uint32_t s = 0; s <= last_s; ++s) {
                    Complex second = multiply(first, terms[1].values[s]);
                    bool free_s = free_r || s < terms[1].central;
                    uint32_t last_t = free_s ? terms[2].size - 1 : terms[2].central;
                    for (uint32_t t = 0; t <= last_t; ++t) {
                        Complex third = multiply(second, terms[2].values[t]);
                        bool free_t = free_s || t < terms[2].central;
                        uint32_t last_u = free_t ? terms[3].size - 1 : terms[3].central;
                        for (uint32_t u = 0; u <= last_u; ++u)
                            test_all(multiply(third, terms[3].values[u]), l, m, candidates);
                    }
                }
            }
            return;
        }
        if (depth < count) {
            for (uint32_t r = 0; r < terms[depth].size; ++r) {
                if (!free_choice && r > terms[depth].central) continue;
                enumerate(terms, count, depth + 1, multiply(z, terms[depth].values[r]),
                          free_choice || r < terms[depth].central, l, m, candidates);
            }
            return;
        }
        test_all(z, l, m, candidates);
    }

    void test_all(Complex z, uint64_t l, uint64_t m, uint64_t& candidates) {
        test_pair(z.re, z.im, l, m, candidates);
        if (z.re != z.im && z.re != -z.im) test_pair(z.im, z.re, l, m, candidates);
    }

    void test_pair(i128 d, i128 area4, uint64_t l, uint64_t m, uint64_t& candidates) {
        if (area4 == 0 || (uint64_t(area4) & 7) != 0) return;
        i128 absolute_area4 = area4 < 0 ? -area4 : area4;
        u128 area_value = u128(absolute_area4);
        if (residue<3>(area_value) != 0) return;
        if ((pair_flags & 1U) && residue<9>(area_value) != 0) return;
        if ((pair_flags & 2U) && residue<5>(area_value) != 0) return;
        test_d(d, area4, l, m, candidates);
        if (d != 0) test_d(-d, area4, l, m, candidates);
    }

    void test_d(i128 d, i128 area4, uint64_t l, uint64_t m, uint64_t& candidates) {
        ++candidates;
        i128 signed_z = i128(fourth[l]) + i128(fourth[m]) - d;
        if (signed_z < 0 || u128(signed_z) < fourth[m] || u128(signed_z) > fourth[n]) return;
        u128 z = signed_z;
        uint64_t low = uint64_t(z) & 15;
        if (low != 0 && low != 1) return;
        static const auto mod625 = fourth_residues<625>();
        static const auto mod9 = fourth_residues<9>();
        static const auto mod7 = fourth_residues<7>();
        static const auto mod13 = fourth_residues<13>();
        static const auto mod17 = fourth_residues<17>();
        if (pair_flags & 2U) {
            if (residue<625>(z) != 0) return;
        } else if (!mod625[residue<625>(z)]) return;
        if (!mod9[residue<9>(z)] || !mod7[residue<7>(z)] ||
            !mod13[residue<13>(z)] || !mod17[residue<17>(z)]) return;
        uint64_t root = std::sqrt((long double)std::sqrt((long double)z));
        while (root > 0 && u128(root) * root * root * root > z) --root;
        while (root < n && u128(root + 1) * (root + 1) * (root + 1) * (root + 1) <= z) ++root;
        if (u128(root) * root * root * root != z) return;
        if (std::gcd(std::gcd(l, m), root) != 1) return;
        if ((l % 5 && m % 5 && root % 5) || root < m || root > n) return;
        record(l, m, root, area4);
    }

    void record(uint64_t l, uint64_t m, uint64_t root, i128 area4) {
        std::array<uint64_t, 3> key{l, m, root};
        std::lock_guard<std::mutex> lock(output_mutex);
        if (!seen.insert(key).second) return;
        uint64_t x = l * l;
        uint64_t y = m * m;
        uint64_t z = root * root;
        i128 factors[4] = {i128(x) + y + z, -i128(x) + y + z,
                           i128(x) - y + z, i128(x) + y - z};
        if (factors[0] <= 0 || factors[1] <= 0 || factors[2] <= 0 || factors[3] <= 0 || area4 % 4 != 0) {
            std::cerr << "rejected internal hit " << l << ' ' << m << ' ' << root << '\n';
            return;
        }
        U256 heron{u128(factors[0])};
        for (size_t i = 1; i < 4; ++i) heron = multiply256(heron, U256(u128(factors[i])));
        i128 absolute_area4 = area4 < 0 ? -area4 : area4;
        U256 expected = multiply256(U256(u128(absolute_area4)), U256(u128(absolute_area4)));
        if (!(heron == expected)) {
            std::cerr << "rejected internal hit " << l << ' ' << m << ' ' << root << '\n';
            return;
        }
        std::string area = string128(absolute_area4 / 4);
        std::ofstream out(results_file, std::ios::app);
        out << l << ' ' << m << ' ' << root << ' ' << area << '\n';
        out.flush();
        std::cout << "HIT " << l << ' ' << m << ' ' << root << " area " << area << std::endl;
    }

    void save_checkpoint() {
        uint64_t r = resume.load();
        while (r <= end && completed[r - begin].load()) ++r;
        resume.store(r);
        std::filesystem::path temporary = state_file + ".tmp";
        {
            std::ofstream out(temporary);
            out << "version 1\nlimit " << n << "\nbegin " << begin << "\nend " << end
                << "\nresume " << r << "\npairs " << pair_count.load()
                << "\ncandidates " << candidate_count.load() << '\n';
        }
        std::filesystem::rename(temporary, state_file);
    }

    void log_progress() {
        double seconds = std::chrono::duration<double>(Clock::now() - start_time).count();
        uint64_t done = completed_count.load();
        std::cout << "PROGRESS resume " << resume.load() << " completed_l " << done
                  << " candidates " << candidate_count.load() << " seconds " << uint64_t(seconds)
                  << " pairs/s " << uint64_t(pair_count.load() / std::max(seconds, 1.0)) << std::endl;
    }
};

int main(int argc, char** argv) {
    if (argc < 6 || argc > 7) {
        std::cerr << "usage: search LIMIT FIRST_L LAST_L THREADS STATE_FILE [RESULTS_FILE]\n";
        return 2;
    }
    uint64_t n = std::stoull(argv[1]);
    uint64_t first = std::stoull(argv[2]);
    uint64_t last = std::stoull(argv[3]);
    uint32_t threads = std::stoul(argv[4]);
    if (!n || !first || first > last || last > n || !threads) return 2;
    std::ifstream state(argv[5]);
    std::string key, value;
    uint64_t stored_limit = 0, stored_end = 0, saved = first;
    while (state >> key >> value) {
        if (key == "limit") stored_limit = std::stoull(value);
        if (key == "end") stored_end = std::stoull(value);
        if (key == "resume") saved = std::stoull(value);
    }
    if (stored_limit) {
        if (stored_limit != n || stored_end != last || saved < first) {
            std::cerr << "checkpoint does not match requested range\n";
            return 2;
        }
        first = saved;
        if (first > last) {
            std::cout << "checkpoint already complete\n";
            return 0;
        }
        std::cerr << "resuming at " << first << '\n';
    }
    std::string results = argc == 7 ? argv[6] : "results.txt";
    std::signal(SIGTERM, request_stop);
    std::signal(SIGINT, request_stop);
    Search search(n, first, last, threads, argv[5], results);
    auto start = std::chrono::steady_clock::now();
    search.prepare();
    std::cerr << "prepared in "
              << std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count()
              << " seconds\n";
    search.run();
    return 0;
}
