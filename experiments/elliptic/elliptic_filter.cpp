#include <cstdint>
#include <cstring>

struct FilterModel {
    uint32_t prime;
    uint32_t a;
    uint32_t h2;
    uint32_t e;
    uint32_t ch;
    uint32_t eh;
    uint32_t a2;
    uint32_t ch_a;
    uint32_t h2a;
    uint32_t reserved;
    const int32_t* qx;
    const int32_t* qy;
    const int32_t* psx;
    const int32_t* psy;
};

static inline uint32_t add_mod(uint32_t a, uint32_t b, uint32_t p) {
    uint32_t value = a + b;
    return value >= p ? value - p : value;
}

static inline uint32_t sub_mod(uint32_t a, uint32_t b, uint32_t p) {
    return a >= b ? a - b : a + p - b;
}

static inline uint32_t mul_mod(uint32_t a, uint32_t b, uint32_t p, uint64_t reciprocal) {
    uint64_t product = uint64_t(a) * b;
    uint64_t quotient = (static_cast<unsigned __int128>(product) * reciprocal) >> 64;
    uint32_t value = uint32_t(product - quotient * p);
    return value >= p ? value - p : value;
}

static inline uint32_t legendre(uint32_t value, uint32_t p, uint64_t reciprocal) {
    uint32_t exponent = (p - 1) / 2;
    uint32_t result = 1;
    while (exponent) {
        if (exponent & 1) result = mul_mod(result, value, p, reciprocal);
        exponent >>= 1;
        if (exponent) value = mul_mod(value, value, p, reciprocal);
    }
    return result;
}

static inline void legendre_pair(uint32_t first, uint32_t second, uint32_t p, uint64_t reciprocal,
                                 uint32_t& first_result, uint32_t& second_result) {
    uint32_t exponent = (p - 1) / 2;
    first_result = 1;
    second_result = 1;
    while (exponent) {
        if (exponent & 1) {
            first_result = mul_mod(first_result, first, p, reciprocal);
            second_result = mul_mod(second_result, second, p, reciprocal);
        }
        exponent >>= 1;
        if (exponent) {
            first = mul_mod(first, first, p, reciprocal);
            second = mul_mod(second, second, p, reciprocal);
        }
    }
}

extern "C" uint32_t filter_mul_mod(uint32_t a, uint32_t b, uint32_t p) {
    return mul_mod(a, b, p, uint64_t(~uint64_t(0) / p));
}

extern "C" uint32_t filter_legendre(uint32_t value, uint32_t p) {
    return legendre(value, p, uint64_t(~uint64_t(0) / p));
}

extern "C" uint64_t filter_pass(int32_t size, int32_t center, int32_t n_index,
                                 int32_t previous_bound, int32_t model_count,
                                 const FilterModel* models, uint8_t* remaining) {
    int32_t n = n_index - center;
    bool central = previous_bound && (n >= -previous_bound && n <= previous_bound);
    int32_t lower = center - previous_bound;
    int32_t upper = center + previous_bound;
    for (int32_t i = 0; i < size; ++i) {
        uint8_t selected = !central || i < lower || i > upper;
        remaining[i] = selected;
        remaining[size + i] = selected;
    }
    for (int32_t model_index = 0; model_index < model_count; ++model_index) {
        const FilterModel& model = models[model_index];
        uint32_t p = model.prime;
        if (model.h2 == 0) continue;
        uint64_t reciprocal = uint64_t(~uint64_t(0) / p);
        const int32_t* qx = model.qx;
        const int32_t* qy = model.qy;
        int32_t x1 = model.psx[n_index];
        int32_t y1 = model.psy[n_index];
        bool any = false;
        for (int32_t i = 0; i < size; ++i) {
            if (central && i >= lower && i <= upper) continue;
            if (!remaining[i] && !remaining[size + i]) continue;
            uint32_t x, z;
            bool valid;
            if (x1 < 0) {
                x = uint32_t(qx[i]);
                z = 1;
                valid = central || i != center;
            } else {
                uint32_t h = sub_mod(uint32_t(qx[i]), uint32_t(x1), p);
                uint32_t r = sub_mod(uint32_t(qy[i]), uint32_t(y1), p);
                uint32_t h_squared = mul_mod(h, h, p, reciprocal);
                x = sub_mod(sub_mod(mul_mod(r, r, p, reciprocal),
                                    mul_mod(h_squared, h, p, reciprocal), p),
                            mul_mod(add_mod(uint32_t(x1), uint32_t(x1), p),
                                    h_squared, p, reciprocal), p);
                z = h;
                valid = h != 0 || r == 0;
                if (h == 0 && r == 0) {
                    if (y1 == 0) {
                        valid = false;
                    } else {
                        uint32_t x1_squared = mul_mod(uint32_t(x1), uint32_t(x1), p, reciprocal);
                        uint32_t slope = add_mod(mul_mod(3, x1_squared, p, reciprocal),
                                                 model.a, p);
                        uint32_t twice_x = add_mod(uint32_t(x1), uint32_t(x1), p);
                        uint32_t s = mul_mod(add_mod(twice_x, twice_x, p),
                                             mul_mod(uint32_t(y1), uint32_t(y1), p, reciprocal),
                                             p, reciprocal);
                        x = sub_mod(mul_mod(slope, slope, p, reciprocal),
                                    add_mod(s, s, p), p);
                        z = add_mod(uint32_t(y1), uint32_t(y1), p);
                    }
                }
                if (!central && i == center) {
                    x = uint32_t(x1);
                    z = 1;
                    valid = true;
                }
            }
            valid &= x != 0;
            if (!valid) {
                any |= remaining[i] || remaining[size + i];
                continue;
            }
            uint32_t z2 = mul_mod(z, z, p, reciprocal);
            uint32_t z4 = mul_mod(z2, z2, p, reciprocal);
            uint32_t x2 = mul_mod(x, x, p, reciprocal);
            uint32_t numerator = sub_mod(
                add_mod(x2, mul_mod(mul_mod(model.ch, x, p, reciprocal), z2, p, reciprocal), p),
                mul_mod(model.eh, z4, p, reciprocal), p);
            uint32_t value = mul_mod(mul_mod(model.h2, x, p, reciprocal), numerator, p, reciprocal);
            uint32_t torsion_numerator = sub_mod(
                add_mod(mul_mod(model.a2, z4, p, reciprocal),
                        mul_mod(mul_mod(model.ch_a, x, p, reciprocal), z2, p, reciprocal), p),
                mul_mod(model.eh, x2, p, reciprocal), p);
            uint32_t torsion_value = mul_mod(mul_mod(model.h2a, x, p, reciprocal),
                                              torsion_numerator, p, reciprocal);
            if (remaining[i] && remaining[size + i]) {
                uint32_t first_result, second_result;
                legendre_pair(value, torsion_value, p, reciprocal, first_result, second_result);
                if (first_result == p - 1) remaining[i] = 0;
                if (second_result == p - 1) remaining[size + i] = 0;
            } else {
                if (remaining[i] && legendre(value, p, reciprocal) == p - 1) remaining[i] = 0;
                if (remaining[size + i] && legendre(torsion_value, p, reciprocal) == p - 1)
                    remaining[size + i] = 0;
            }
            any |= remaining[i] || remaining[size + i];
        }
        if (!any) break;
    }
    uint64_t count = 0;
    for (int32_t i = 0; i < 2 * size; ++i) count += remaining[i] != 0;
    return count;
}
