"""Analyze NIFTY CALL option IV using last-traded prices from offline NSE CSVs.

Run from the project root: python analyze_options_ltp.py
Results: plots_ltp/ with PNG charts and CSV diagnostics.
No downloading or scraping is performed.
"""

from datetime import datetime, time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Save charts without requiring a display window.
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from data.fetch_ltp_data import load_ltp_expiries
from black_scholes import vega
from implied_volatility import calculate_implied_volatility

# IMPORTANT: These are snapshot assumptions, NOT live/updating market data.
# Replace with the index level/time matching YOUR downloaded NSE quotes.
SPOT_PRICE = 22753.2
SNAPSHOT_DATETIME = datetime(2026, 10, 26, 15, 30)
EXPIRY_CLOCK_TIME = time(15, 30)  # Verify actual exchange expiry convention.
RISK_FREE_RATE = 0.061  # 6.1% annualized proxy
DIVIDEND_YIELD = 0.0152  # 1.52% continuous annualized proxy

DATA_FOLDER = Path("data")
PLOT_DIR = Path("plots_ltp")
STRIKE_RANGE_PCT = 0.12  # Consider strikes within +/-12% of spot.
MAX_RELATIVE_SPREAD = 0.20  # Diagnostic quality screen, not an exchange rule.
MAX_IV_FOR_PLOT = 1.00  # 100% annualized: plot screen only, NOT solver bound.
MIN_VEGA_FOR_PLOT = 20.0  # Price change per 1.0 change in decimal IV.


def parse_expiry(expiry_label):
    """Parse an explicit expiry year: DD-Mon-YYYY."""
    return datetime.strptime(expiry_label, "%d-%b-%Y").date()


def time_to_expiry(expiry_label):
    """Calendar-years between the quote snapshot and assumed expiry time."""
    expiry = datetime.combine(parse_expiry(expiry_label), EXPIRY_CLOCK_TIME)
    return (expiry - SNAPSHOT_DATETIME).total_seconds() / (365.0 * 24 * 3600)


def prepare_expiry_table(df, expiry_label, T):
    """Calculate ALL in-range IVs and record why a point is or is not plotted."""
    lower_strike = SPOT_PRICE * (1 - STRIKE_RANGE_PCT)
    upper_strike = SPOT_PRICE * (1 + STRIKE_RANGE_PCT)
    sample = df.loc[df["strike"].between(lower_strike, upper_strike)].copy()
    sample = sample.sort_values("strike").reset_index(drop=True)
    if sample.empty:
        return sample, None

    # Choose ATM from the RAW strike grid, before filtering on IV or spreads.
    atm_strike = float(sample.loc[(sample["strike"] - SPOT_PRICE).abs().idxmin(), "strike"])
    sample["market_price"] = sample["call_ltp"]
    sample["expiry"] = expiry_label
    sample["T_years"] = T
    sample["spot"] = SPOT_PRICE
    sample["risk_free_rate"] = RISK_FREE_RATE
    sample["dividend_yield"] = DIVIDEND_YIELD
    sample["atm_strike"] = atm_strike

    sample["iv"] = sample.apply(
        lambda row: calculate_implied_volatility(
            market_price=row["market_price"], option_type="CE",
            S=SPOT_PRICE, K=row["strike"], T=T,
            r=RISK_FREE_RATE, q=DIVIDEND_YIELD,
        ),
        axis=1,
    )
    sample["iv_pct"] = sample["iv"] * 100
    sample["vega"] = sample.apply(
        lambda row: vega(SPOT_PRICE, row["strike"], T, RISK_FREE_RATE,
                         row["iv"], DIVIDEND_YIELD)
        if pd.notna(row["iv"]) else np.nan,
        axis=1,
    )
    sample["relative_spread"] = (
        (sample["call_ask"] - sample["call_bid"])
        / ((sample["call_ask"] + sample["call_bid"]) / 2.0)
    )
    # An LTP outside the CURRENT spread is not proof of an error or stale trade.
    # Keep as an indicator for investigation, not an automatic exclusion.
    sample["ltp_outside_current_quote"] = (
        sample["call_ltp"].notna()
        & sample["call_bid"].notna()
        & sample["call_ask"].notna()
        & ((sample["call_ltp"] < sample["call_bid"])
           | (sample["call_ltp"] > sample["call_ask"]))
    )

    def screening_reason(row):
        if pd.isna(row["market_price"]) or row["market_price"] <= 0:
            return "missing_or_nonpositive_market_price"
        if pd.isna(row["iv"]):
            return "IV_unsolved_or_price_outside_model_bounds"
        if (pd.isna(row["call_bid"]) or pd.isna(row["call_ask"])
                or row["call_bid"] <= 0 or row["call_ask"] <= 0):
            return "invalid_bid_or_ask"
        if row["call_ask"] < row["call_bid"]:
            return "crossed_bid_ask"
        if row["relative_spread"] > MAX_RELATIVE_SPREAD:
            return "wide_bid_ask_spread"
        if row["vega"] < MIN_VEGA_FOR_PLOT:
            return "low_vega"
        if row["iv"] > MAX_IV_FOR_PLOT:
            return "IV_above_plot_limit"
        return "accepted"

    sample["plot_status"] = sample.apply(screening_reason, axis=1)
    return sample, atm_strike


def save_smile(df, expiry_label, T):
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(df["strike"], df["iv_pct"], "o-", linewidth=1.1, markersize=3.5)
    ax.axvline(SPOT_PRICE, color="red", linestyle="--", label=f"Spot: {SPOT_PRICE:,.1f}")
    ax.set(title=f"[LTP] Call IV vs Strike | {expiry_label} (T={T:.3f}y)",
           xlabel="Strike price", ylabel="Annualized IV (%)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(PLOT_DIR / f"iv_smile_{expiry_label}.png", dpi=200)
    plt.close(fig)


def save_combined_smiles(curves):
    if not curves:
        return
    fig, ax = plt.subplots(figsize=(12, 7))
    for label, T, df in curves:
        ax.plot(df["strike"], df["iv_pct"], "o-", markersize=2.5,
                linewidth=1.0, label=f"{label} ({T:.2f}y)")
    ax.axvline(SPOT_PRICE, linestyle="--", color="red", label="Spot")
    ax.set(title="[LTP] NIFTY Call IV Curves by Expiry",
           xlabel="Strike price", ylabel="Annualized IV (%)")
    ax.grid(alpha=0.3)
    ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "combined_iv_smiles.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_term_structure(points):
    if not points:
        return
    table = pd.DataFrame(points).sort_values("expiry_date")
    table.to_csv(PLOT_DIR / "atm_term_structure.csv", index=False)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(table["expiry"], table["atm_iv_pct"], "s-", linewidth=2)
    ax.set(title="[LTP] ATM-Strike Call IV Term Structure",
           xlabel="Expiry date", ylabel="Annualized ATM IV (%)")
    ax.grid(alpha=0.3)
    ax.tick_params(axis="x", labelrotation=45)
    fig.tight_layout()
    fig.savefig(PLOT_DIR / "atm_term_structure.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def save_surface(curves):
    if not curves:
        return
    strikes = np.concatenate([x[2]["strike"].to_numpy(dtype=float) for x in curves])
    times = np.concatenate([np.full(len(x[2]), x[1]) for x in curves])
    ivs = np.concatenate([x[2]["iv_pct"].to_numpy(dtype=float) for x in curves])
    if len(strikes) < 4 or len(np.unique(strikes)) < 2 or len(np.unique(times)) < 2:
        print("[LTP] Not enough distinct data points for 3D surface.")
        return
    try:
        fig = plt.figure(figsize=(12, 8))
        ax = fig.add_subplot(111, projection="3d")
        surface = ax.plot_trisurf(strikes, times, ivs, cmap="viridis", alpha=0.9)
        ax.set(title="[LTP] NIFTY Call IV Surface (screened quotes)",
               xlabel="Strike price", ylabel="Years to expiry", zlabel="Annualized IV (%)")
        fig.colorbar(surface, ax=ax, shrink=0.55, label="IV (%)")
        fig.tight_layout()
        fig.savefig(PLOT_DIR / "volatility_surface_3d.png", dpi=200, bbox_inches="tight")
        plt.close(fig)
    except (ValueError, RuntimeError) as exc:
        plt.close("all")
        print(f"[LTP] Could not triangulate 3D surface: {exc}")


def run_ltp_analysis():
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    expiries = load_ltp_expiries(DATA_FOLDER)
    if not expiries:
        print("No valid NSE option-chain CSV files loaded. See README.md.")
        return

    curves, atm_points, results = [], [], []
    for label in sorted(expiries, key=parse_expiry):
        T = time_to_expiry(label)
        if T <= 0:
            print(f"[LTP] Skipping expired contract {label}.")
            continue
        table, atm_strike = prepare_expiry_table(expiries[label], label, T)
        if table.empty:
            print(f"[LTP] No strikes in range for {label}.")
            continue
        results.append(table)
        screened = table[table["plot_status"] == "accepted"].copy()
        print(f"[LTP] {label}: {len(screened)}/{len(table)} quotes plotted; "
              f"reasons = {table['plot_status'].value_counts().to_dict()}")
        if not screened.empty:
            curves.append((label, T, screened))
            save_smile(screened, label, T)

        # Do NOT replace the closest ATM strike with a farther, surviving one.
        atm_row = table.loc[table["strike"] == atm_strike].iloc[0]
        if atm_row["plot_status"] == "accepted":
            atm_points.append({
                "expiry": label, "expiry_date": parse_expiry(label),
                "T_years": T, "atm_strike": atm_strike,
                "atm_iv_pct": atm_row["iv_pct"],
            })
        else:
            print(f"[LTP] ATM {label} strike {atm_strike:g} excluded: "
                  f"{atm_row['plot_status']}")

    if results:
        full_table = pd.concat(results, ignore_index=True)
        file_path = PLOT_DIR / "calculated_iv_diagnostics.csv"
        full_table.to_csv(file_path, index=False)
        print(f"[LTP] Saved ALL in-range IV calculations and flags: {file_path}")
    save_combined_smiles(curves)
    save_term_structure(atm_points)
    save_surface(curves)
    print(f"[LTP] Finished. Charts/CSVs saved in '{PLOT_DIR}/'.")


if __name__ == "__main__":
    run_ltp_analysis()
