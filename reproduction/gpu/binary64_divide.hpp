#pragma once
#include <cstdint>

namespace fitness {
// Restoring integer division produces all binary64 significand bits plus the
// exact remainder. This also works on devices without a reliable FP64 divide.
FOG_HD double divide_round_nearest(double numerator, double denominator) {
    using Word = std::uint64_t;
    constexpr Word sign_bit = Word{1} << 63;
    constexpr Word hidden = Word{1} << 52;
    constexpr Word fraction_mask = hidden - 1;
    constexpr Word infinity = Word{0x7ff} << 52;
    union Bits {
        double number;
        Word bits;
    } a, b, result;
    a.number = numerator;
    b.number = denominator;
    const Word sign = (a.bits ^ b.bits) & sign_bit;
    const Word aa = a.bits & ~sign_bit, bb = b.bits & ~sign_bit;
    if (bb == 0)
        return 1.; // GP's protected division includes signed zero.
    if (aa > infinity || bb > infinity || (aa == infinity && bb == infinity)) {
        result.bits = infinity | (hidden >> 1);
        return result.number;
    }
    if (aa == infinity || bb == infinity || aa == 0) {
        result.bits = sign | (aa == infinity ? infinity : 0);
        return result.number;
    }
    int ea = static_cast<int>(aa >> 52) - 1023, eb = static_cast<int>(bb >> 52) - 1023;
    Word ma = aa & fraction_mask, mb = bb & fraction_mask;
    if (ea == -1023) {
        ea = -1022;
        while (ma < hidden) {
            ma <<= 1;
            --ea;
        }
    } else
        ma |= hidden;
    if (eb == -1023) {
        eb = -1022;
        while (mb < hidden) {
            mb <<= 1;
            --eb;
        }
    } else
        mb |= hidden;
    int exponent = ea - eb;
    if (ma < mb) {
        ma <<= 1;
        --exponent;
    }
    if (exponent > 1023) {
        result.bits = sign | infinity;
        return result.number;
    }
    if (exponent < -1074) {
        result.bits = sign | ((exponent == -1075 && ma > mb) ? 1 : 0);
        return result.number;
    }
    const int fractional_bits = exponent >= -1022 ? 52 : exponent + 1074;
    Word quotient = 1, remainder = ma - mb;
    for (int k = 0; k < fractional_bits; ++k) {
        remainder <<= 1;
        const bool bit = remainder >= mb;
        quotient = (quotient << 1) | static_cast<Word>(bit);
        if (bit)
            remainder -= mb;
    }
    const Word twice = remainder << 1;
    if (twice > mb || (twice == mb && (quotient & 1)))
        ++quotient;
    if (exponent < -1022) {
        result.bits = sign | quotient;
        return result.number;
    }
    if (quotient == (hidden << 1)) {
        quotient >>= 1;
        ++exponent;
    }
    result.bits =
        sign | (exponent > 1023 ? infinity
                                : (static_cast<Word>(exponent + 1023) << 52) | (quotient & fraction_mask));
    return result.number;
}
} // namespace fitness
