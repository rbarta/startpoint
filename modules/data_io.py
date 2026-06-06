import json
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
HIST_DIR = DATA_DIR / "historical"


def load_csv(filename: str) -> pd.DataFrame:
    return pd.read_csv(HIST_DIR / filename)


def load_json(path: str | Path) -> dict:
    p = Path(path)
    if not p.is_absolute():
        p = DATA_DIR / path
    if not p.exists():
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str | Path, data: dict) -> None:
    p = Path(path)
    if not p.is_absolute():
        p = DATA_DIR / path
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_sp500() -> pd.DataFrame:
    df = load_csv("sp500_total_return.csv")
    return df.set_index("year")


def load_tsx() -> pd.DataFrame:
    df = load_csv("tsx_total_return.csv")
    return df.set_index("year")


def load_cpi() -> pd.DataFrame:
    df = load_csv("canada_cpi.csv")
    return df.set_index("year")


# Assumed annual inflation for years beyond the historical CPI data. The app sets
# this from the user's "Inflation during retirement" value (see set_future_inflation);
# it defaults to 3% to match that setting's default.
FUTURE_INFLATION_PCT = 3.0


def set_future_inflation(pct) -> None:
    """Set the inflation rate used to project CPI past the end of the data."""
    global FUTURE_INFLATION_PCT
    try:
        FUTURE_INFLATION_PCT = float(pct)
    except (TypeError, ValueError):
        pass


def _cpi_index(cpi, year: int) -> float:
    """CPI index for a year, projecting past the data with FUTURE_INFLATION_PCT."""
    lo, hi = int(cpi.index.min()), int(cpi.index.max())
    rate = 1 + FUTURE_INFLATION_PCT / 100.0
    if lo <= year <= hi:
        return float(cpi.loc[year, "cpi_index"])
    if year > hi:                      # project forward to "today" (years past the data)
        return float(cpi.loc[hi, "cpi_index"]) * rate ** (year - hi)
    return float(cpi.loc[lo, "cpi_index"]) / rate ** (lo - year)   # project backward (rare)


def get_cpi_factor(from_year: int, to_year: int) -> float:
    """Return cpi[to_year] / cpi[from_year] — multiply a from_year amount by this to
    get to_year purchasing power. Years beyond the data are projected at
    FUTURE_INFLATION_PCT so conversions to the current year still work."""
    cpi = load_cpi()
    return _cpi_index(cpi, to_year) / _cpi_index(cpi, from_year)


def load_sim_inputs() -> dict:
    return load_json("sim_inputs.json")


def save_sim_inputs(data: dict) -> None:
    save_json("sim_inputs.json", data)
