"""Load call bid/ask quotes and calculate their midpoints from NSE CSV files.

Column positions match the CSV format used in the original project.
Invalid/missing quotes remain in the output so the analysis can report them.
"""

from pathlib import Path
import numpy as np
import pandas as pd

from data.fetch_ltp_data import EXPIRY_IN_FILENAME, clean_numeric


def load_mid_expiries(data_folder="data"):
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
                "call_bid": raw.iloc[:, 8].map(clean_numeric),
                "call_ask": raw.iloc[:, 9].map(clean_numeric),
                "call_volume": raw.iloc[:, 3].map(clean_numeric),
                "call_ltp": raw.iloc[:, 5].map(clean_numeric),
            })
            result = result.loc[result["strike"].gt(0)].copy()
            result["mid_price"] = (result["call_bid"] + result["call_ask"]) / 2.0
            result = result.drop_duplicates(subset="strike").sort_values("strike")
            if result.empty:
                raise ValueError("no valid strike rows after reading")
            if expiry_label in all_data:
                raise ValueError(f"duplicate expiry {expiry_label}; use one snapshot per expiry")
            all_data[expiry_label] = result.reset_index(drop=True)
            print(f"[MID] Loaded {len(result)} strikes from {path.name}")
        except (OSError, ValueError, pd.errors.ParserError) as exc:
            print(f"[MID] Could not load {path.name}: {exc}")
    return all_data
