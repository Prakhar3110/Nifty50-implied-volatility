"""Load the *call* LTP and accompanying quote fields from NSE CSV downloads.

Assumes the same 23/24-column NSE option-chain layout as the original code:
strike=column 11, call LTP=5, call bid=8, call ask=9, call volume=3.
CSV files must be stored inside ./data (not inside ./plots_*).
"""

from pathlib import Path
import re
import numpy as np
import pandas as pd


EXPIRY_IN_FILENAME = re.compile(
    r"(?<!\d)(\d{1,2})[-_ ]([A-Za-z]{3})[-_ ](20\d{2})(?!\d)",
    re.IGNORECASE,
)


def clean_numeric(value):
    if pd.isna(value):
        return np.nan
    try:
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return np.nan


def load_ltp_expiries(data_folder="data"):
    all_data = {}
    paths = sorted(Path(data_folder).glob("*.csv"))
    if not paths:
        print(f"No NSE CSV files found in '{data_folder}/'.")

    for path in paths:
        match = EXPIRY_IN_FILENAME.search(path.stem)
        if not match:
            print(f"Skipping '{path.name}': no DD-Mon-YYYY expiry in filename.")
            continue
        parsed = pd.to_datetime("-".join(match.groups()), format="%d-%b-%Y", errors="coerce")
        if pd.isna(parsed):
            print(f"Skipping '{path.name}': invalid expiry date.")
            continue
        expiry_label = parsed.strftime("%d-%b-%Y")

        try:
            raw = pd.read_csv(path, header=None, skiprows=2, engine="python")
            if raw.shape[1] < 12:
                raise ValueError(f"expected at least 12 columns, found {raw.shape[1]}")
            result = pd.DataFrame({
                "strike": raw.iloc[:, 11].map(clean_numeric),
                "call_ltp": raw.iloc[:, 5].map(clean_numeric),
                "call_bid": raw.iloc[:, 8].map(clean_numeric),
                "call_ask": raw.iloc[:, 9].map(clean_numeric),
                "call_volume": raw.iloc[:, 3].map(clean_numeric),
            })
            result = result.loc[result["strike"].gt(0)].copy()
            result = result.drop_duplicates(subset="strike").sort_values("strike")
            if result.empty:
                raise ValueError("no valid strike rows after reading")
            if expiry_label in all_data:
                raise ValueError(f"duplicate expiry {expiry_label}; use one snapshot per expiry")
            all_data[expiry_label] = result.reset_index(drop=True)
            print(f"[LTP] Loaded {len(result)} strikes from {path.name}")
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            print(f"[LTP] Could not load {path.name}: {exc}")
    return all_data
