"""Implied volatility from the Black-Scholes model.

Newton-Raphson is attempted first. A bracketed Brent solver is used when
Newton's step would leave the allowed positive-volatility interval.
Failed or impossible inversions return np.nan, never a made-up 0% IV.
"""

import numpy as np
from scipy.optimize import brentq

from black_scholes import black_scholes_price, price_bounds, vega


def calculate_implied_volatility(
    market_price,
    option_type,
    S,
    K,
    T,
    r,
    initial_guess=0.2,
    max_iter=100,
    tol=1e-6,
    q=0.0,
    max_sigma=5.0,
):
    """Return decimal IV (0.20 = 20%) or np.nan when it cannot be solved.

    max_sigma=5 means search only up to 500% annualized volatility. This is a
    numerical search limit, not a judgement that every IV below it is valid.
    """
    try:
        vals = np.asarray([market_price, S, K, T, r, q, initial_guess], dtype=float)
        if not np.all(np.isfinite(vals)):
            return np.nan
        market_price, S, K, T, r, q, initial_guess = vals
    except (TypeError, ValueError):
        return np.nan

    if option_type not in ("CE", "PE"):
        raise ValueError("option_type must be 'CE' or 'PE'")
    if (
        market_price <= 0 or S <= 0 or K <= 0 or T <= 0
        or max_sigma <= 0 or max_iter < 1 or tol <= 0
    ):
        return np.nan

    low_price, high_price = price_bounds(option_type, S, K, T, r, q)
    # Reject prices indistinguishable from the zero-volatility bound.
    # Near that bound, IV is not numerically identifiable from the quote.
    if market_price - low_price <= max(1e-5, 1e-8 * S) or market_price >= high_price:
        return np.nan

    low_sigma = 1e-8
    f_low = black_scholes_price(option_type, S, K, T, r, low_sigma, q) - market_price
    f_high = black_scholes_price(option_type, S, K, T, r, max_sigma, q) - market_price
    if f_low > 0 or f_high < 0:
        return np.nan  # Root outside the chosen [low_sigma, max_sigma] range.

    sigma = float(np.clip(initial_guess, low_sigma, max_sigma))
    for _ in range(max_iter):
        difference = black_scholes_price(option_type, S, K, T, r, sigma, q) - market_price
        if abs(difference) <= tol:
            return sigma

        derivative = vega(S, K, T, r, sigma, q)
        if derivative <= 1e-10:
            break  # Low vega: Newton is not numerically safe.

        candidate = sigma - difference / derivative
        if not np.isfinite(candidate) or not (low_sigma < candidate < max_sigma):
            break  # Do not clamp and falsely call it convergence.
        sigma = candidate

    # Brent's method stays inside the bracket and handles difficult options.
    try:
        solution = brentq(
            lambda volatility: black_scholes_price(
                option_type, S, K, T, r, volatility, q
            ) - market_price,
            low_sigma,
            max_sigma,
            xtol=1e-12,
            maxiter=max_iter,
        )
        residual = abs(
            black_scholes_price(option_type, S, K, T, r, solution, q) - market_price
        )
        return solution if residual <= tol else np.nan
    except (ValueError, RuntimeError):
        return np.nan
