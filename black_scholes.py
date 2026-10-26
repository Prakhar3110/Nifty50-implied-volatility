"""European Black-Scholes call/put pricing with continuous dividend yield.

All rates and volatility are decimals: 6.1% -> 0.061, 20% -> 0.20.
Time T is in calendar years. Prices are in index points (INR per unit).
"""

import numpy as np
from scipy.stats import norm


def d1(S, K, T, r, sigma, q=0.0):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        raise ValueError("S, K, T and sigma must be positive to calculate d1")
    return (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (
        sigma * np.sqrt(T)
    )


def d2(S, K, T, r, sigma, q=0.0):
    return d1(S, K, T, r, sigma, q) - sigma * np.sqrt(T)


def price_bounds(option_type, S, K, T, r, q=0.0):
    """No-arbitrage bounds for a European option in the BS model."""
    if option_type not in ("CE", "PE"):
        raise ValueError("option_type must be 'CE' or 'PE'")
    if S <= 0 or K <= 0 or T < 0:
        raise ValueError("S and K must be positive, and T cannot be negative")

    pv_spot = S * np.exp(-q * T)
    pv_strike = K * np.exp(-r * T)
    if option_type == "CE":
        return max(0.0, pv_spot - pv_strike), pv_spot
    return max(0.0, pv_strike - pv_spot), pv_strike


def black_scholes_price(option_type, S, K, T, r, sigma, q=0.0):
    """Return the Black-Scholes European option value."""
    if option_type not in ("CE", "PE"):
        raise ValueError("option_type must be 'CE' or 'PE'")
    if S <= 0 or K <= 0 or T < 0 or sigma < 0:
        raise ValueError("S, K > 0 and T, sigma >= 0 are required")

    if T == 0:
        return max(0.0, S - K) if option_type == "CE" else max(0.0, K - S)

    pv_spot = S * np.exp(-q * T)
    pv_strike = K * np.exp(-r * T)
    if sigma == 0:
        return max(0.0, pv_spot - pv_strike) if option_type == "CE" else max(
            0.0, pv_strike - pv_spot
        )

    x1 = d1(S, K, T, r, sigma, q)
    x2 = x1 - sigma * np.sqrt(T)
    if option_type == "CE":
        return pv_spot * norm.cdf(x1) - pv_strike * norm.cdf(x2)
    return pv_strike * norm.cdf(-x2) - pv_spot * norm.cdf(-x1)


def vega(S, K, T, r, sigma, q=0.0):
    """d(option price)/d(sigma), where sigma is a decimal, not percentage."""
    if T <= 0 or sigma <= 0:
        return 0.0
    x1 = d1(S, K, T, r, sigma, q)
    return S * np.exp(-q * T) * np.sqrt(T) * norm.pdf(x1)
