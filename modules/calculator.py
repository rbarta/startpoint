import datetime

import numpy as np
import pandas as pd

from modules.data_io import load_sp500, load_tsx, load_cpi, get_cpi_factor

# Last year of bundled historical return/CPI data (the accumulation window ends here).
DATA_END_YEAR = 2024
# The real "today" used for purchasing-power ("today's $") conversions. Years between
# DATA_END_YEAR and this are projected via the inflation rate (see data_io.get_cpi_factor).
CURRENT_YEAR = max(DATA_END_YEAR, datetime.date.today().year)

# Approximate Canadian median household income by year (CAD, nominal).
# Source: Statistics Canada surveys + estimates.
_MEDIAN_INCOME = {
    1960: 4500, 1961: 4600, 1962: 4800, 1963: 5000, 1964: 5300,
    1965: 5600, 1966: 6000, 1967: 6400, 1968: 6900, 1969: 7400,
    1970: 7900, 1971: 8400, 1972: 9100, 1973: 10200, 1974: 12000,
    1975: 13500, 1976: 15000, 1977: 16500, 1978: 17800, 1979: 19500,
    1980: 21500, 1981: 24000, 1982: 25000, 1983: 26000, 1984: 27500,
    1985: 29000, 1986: 30500, 1987: 32000, 1988: 34000, 1989: 36000,
    1990: 37500, 1991: 38000, 1992: 38500, 1993: 39000, 1994: 40000,
    1995: 41500, 1996: 42500, 1997: 44000, 1998: 45500, 1999: 47000,
    2000: 50000, 2001: 52000, 2002: 53500, 2003: 55000, 2004: 57000,
    2005: 59000, 2006: 61500, 2007: 64000, 2008: 66000, 2009: 65000,
    2010: 67000, 2011: 70000, 2012: 73000, 2013: 75000, 2014: 77000,
    2015: 78000, 2016: 79500, 2017: 82000, 2018: 85000, 2019: 88000,
    2020: 87000, 2021: 92000, 2022: 97000, 2023: 102000, 2024: 106000,
}


def _get_returns(index: str, years: list[int]) -> dict[int, float]:
    """Return dict of year -> annual_return_pct/100 for the requested index."""
    if index == "SP500":
        df = load_sp500()
    elif index == "TSX":
        df = load_tsx()
    elif index == "50/50 CA/US":  # 50% S&P/TSX Composite + 50% S&P 500, rebalanced yearly
        sp = load_sp500()
        tsx = load_tsx()
        result = {}
        for y in years:
            sp_r = float(sp.loc[y, "annual_return_pct"]) / 100 if y in sp.index else 0.07
            tsx_r = float(tsx.loc[y, "annual_return_pct"]) / 100 if y in tsx.index else 0.07
            result[y] = 0.50 * sp_r + 0.50 * tsx_r
        return result
    else:  # 60/40 blend: 60% S&P500, 40% bonds (bonds approximated at 4% real + CPI)
        sp = load_sp500()
        cpi = load_cpi()
        result = {}
        for y in years:
            sp_r = float(sp.loc[y, "annual_return_pct"]) / 100 if y in sp.index else 0.07
            # approximate bond return: 4% nominal average over period
            bond_r = 0.04
            result[y] = 0.60 * sp_r + 0.40 * bond_r
        return result

    result = {}
    for y in years:
        if y in df.index:
            result[y] = float(df.loc[y, "annual_return_pct"]) / 100
        else:
            result[y] = 0.07  # fallback average
    return result


def _monthly_contribution(
    year: int,
    current_age_at_start: int,
    start_year: int,
    model: str,
    monthly_today_cad: float,
    income_growth_rate: float,
    life_stage_params: dict,
) -> tuple[float, str]:
    """Return (monthly_contribution_nominal_cad, phase_label)."""
    age = current_age_at_start + (year - start_year)

    if model == "inflation_adjusted":
        factor = get_cpi_factor(year, CURRENT_YEAR)
        return monthly_today_cad / factor, "inflation_adjusted"

    if model == "nominal_fixed":
        return monthly_today_cad, "nominal_fixed"

    if model == "career_growth":
        elapsed = year - start_year
        rate = income_growth_rate / 100
        # Start from an inflation-adjusted base so year-0 feels right
        base = monthly_today_cad / get_cpi_factor(start_year, CURRENT_YEAR)
        return base * (1 + rate) ** elapsed, "career_growth"

    if model == "life_stage":
        p = life_stage_params
        build_end = p.get("build_end_age", 35)
        balance_end = p.get("balance_end_age", 55)
        if age < build_end:
            phase = "Build"
            amt_today = p.get("build_monthly", 600)
        elif age < balance_end:
            phase = "Balance"
            amt_today = p.get("balance_monthly", 800)
        else:
            phase = "Ease"
            amt_today = p.get("ease_monthly", 400)
        # Adjust to nominal for the simulation year
        nominal = amt_today / get_cpi_factor(year, CURRENT_YEAR)
        return nominal, phase

    return monthly_today_cad, "unknown"


def run_historical_sim(
    start_year: int,
    duration_years: int,
    index: str,
    contribution_model: str,
    monthly_today_cad: float,
    income_growth_rate: float,
    current_age: int,
    life_stage_params: dict | None = None,
    initial_balance_today_cad: float = 0.0,
) -> pd.DataFrame:
    """
    Simulate month-by-month portfolio growth using real historical index returns.
    Returns a DataFrame with one row per year.

    `initial_balance_today_cad` is entered in today's purchasing power and is
    CPI-scaled back to `start_year` nominal dollars so it is consistent with
    how monthly contributions are handled.
    """
    if life_stage_params is None:
        life_stage_params = {
            "build_monthly": 600, "balance_monthly": 800, "ease_monthly": 400,
            "build_end_age": 35, "balance_end_age": 55,
        }

    end_year = start_year + duration_years - 1
    years = list(range(start_year, end_year + 1))
    returns = _get_returns(index, years)

    # Scale initial balance from today's dollars to start_year nominal dollars
    initial_balance_nominal = initial_balance_today_cad / get_cpi_factor(start_year, CURRENT_YEAR)

    rows = []
    balance = initial_balance_nominal
    cumulative_invested = initial_balance_nominal   # track all money committed
    last_phase = "Build"

    for i, year in enumerate(years):
        age = current_age + i
        annual_r = returns.get(year, 0.07)
        monthly_r = (1 + annual_r) ** (1 / 12) - 1

        monthly_contrib, phase = _monthly_contribution(
            year, current_age, start_year, contribution_model,
            monthly_today_cad, income_growth_rate, life_stage_params,
        )
        last_phase = phase
        annual_contribution = monthly_contrib * 12

        # ── Record state at the BEGINNING of this year ────────────────────────
        # At start_year this equals the initial balance (portfolio == invested).
        cpi_to_today = get_cpi_factor(year, CURRENT_YEAR)
        median_income = _MEDIAN_INCOME.get(year, max(annual_contribution, 1.0))
        contrib_pct_median = (annual_contribution / median_income * 100) if median_income > 0 else 0

        rows.append({
            "year": year,
            "age": age,
            "monthly_contribution": round(monthly_contrib, 2),
            "annual_contribution": round(annual_contribution, 2),
            "cumulative_invested": round(cumulative_invested, 2),
            "portfolio_value": round(balance, 2),
            "real_portfolio_value": round(balance * cpi_to_today, 2),
            "annual_return_pct": round(annual_r * 100, 2),
            "annual_portfolio_growth": 0.0,   # filled in after compounding below
            "tipping_point": False,
            "contribution_pct_of_median_income": round(contrib_pct_median, 1),
            "life_phase": phase,
        })

        # ── Compound this year's returns and add contributions ─────────────────
        balance_start = balance
        for _ in range(12):
            balance = balance * (1 + monthly_r) + monthly_contrib

        annual_growth = balance - balance_start - annual_contribution
        cumulative_invested += annual_contribution

        # Patch this year's growth back into the row we just appended
        rows[-1]["annual_portfolio_growth"] = round(annual_growth, 2)

    # ── Final row: state AFTER the last year's compounding (= retirement day) ──
    final_year = end_year + 1
    final_cpi = get_cpi_factor(min(final_year, CURRENT_YEAR), CURRENT_YEAR)
    rows.append({
        "year": final_year,
        "age": current_age + len(years),
        "monthly_contribution": 0.0,
        "annual_contribution": 0.0,
        "cumulative_invested": round(cumulative_invested, 2),
        "portfolio_value": round(balance, 2),
        "real_portfolio_value": round(balance * final_cpi, 2),
        "annual_return_pct": 0.0,
        "annual_portfolio_growth": 0.0,
        "tipping_point": False,
        "contribution_pct_of_median_income": 0.0,
        "life_phase": last_phase,
    })

    # ── Crossover ("compounding took over") ───────────────────────────────────
    # The first year where accumulated market gains exceed everything you have
    # put in — i.e. growth is now more than half the nest egg. This is the
    # classic "crossover point": stable, meaningful, and genuinely sensitive to
    # the return history and contribution timing (unlike a single-year spike).
    for r in rows:
        invested = r["cumulative_invested"]
        if invested > 0 and (r["portfolio_value"] - invested) > invested:
            r["tipping_point"] = True
            break

    return pd.DataFrame(rows)


def calc_retirement_income(
    portfolio_at_retirement: float,
    retirement_age: int,
    depletion_age: int,
    retirement_year: int,
    years_to_retirement: int,
    post_retirement_return_pct: float,
    inflation_rate_pct: float,
) -> dict:
    """
    Compute the first monthly withdrawal for a growing annuity that:
    - Starts at `retirement_year`
    - Grows each month by the monthly inflation rate
    - Depletes the portfolio to zero by `depletion_age`
    - Portfolio earns `post_retirement_return_pct` annually while drawing down

    Returns monthly_nominal (retirement-year dollars), monthly_today (today's dollars),
    annual equivalents, and a year-by-year drawdown DataFrame.
    """
    n_years = max(depletion_age - retirement_age, 1)
    n_months = n_years * 12

    r_m = (1 + post_retirement_return_pct / 100) ** (1 / 12) - 1
    g_m = (1 + inflation_rate_pct / 100) ** (1 / 12) - 1

    if portfolio_at_retirement <= 0:
        return {
            "monthly_nominal": 0.0, "monthly_today": 0.0,
            "annual_nominal": 0.0, "annual_today": 0.0,
            "n_years": n_years, "drawdown_df": pd.DataFrame(),
        }

    if abs(r_m - g_m) < 1e-10:
        pmt_nominal = portfolio_at_retirement / n_months
    else:
        pmt_nominal = (
            portfolio_at_retirement
            * (r_m - g_m)
            / (1 - ((1 + g_m) / (1 + r_m)) ** n_months)
        )

    # Deflate back to today's purchasing power using the forward inflation rate
    pmt_today = pmt_nominal / (1 + inflation_rate_pct / 100) ** years_to_retirement

    # Build year-by-year drawdown trajectory
    balance = portfolio_at_retirement
    payment = pmt_nominal
    rows = []
    for month in range(n_months):
        balance = balance * (1 + r_m) - payment
        balance = max(0.0, balance)
        payment *= (1 + g_m)
        if month % 12 == 11:
            rows.append({
                "year": retirement_year + month // 12 + 1,
                "portfolio_value": round(balance, 2),
            })

    return {
        "monthly_nominal": round(pmt_nominal, 2),
        "monthly_today": round(pmt_today, 2),
        "annual_nominal": round(pmt_nominal * 12, 2),
        "annual_today": round(pmt_today * 12, 2),
        "n_years": n_years,
        "drawdown_df": pd.DataFrame(rows),
    }


def run_comparison_sim(
    start_year: int,
    duration_years: int,
    index: str,
    total_contributions_today_cad: float,
    early_years: int | None = None,
    initial_balance_today_cad: float = 0.0,
) -> dict[str, pd.DataFrame]:
    """
    Run three scenarios with the same total lifetime contribution pool:
    - early_starter: contributes first `early_years` years only, then coasts
    - late_starter: contributes remaining years only
    - steady: spreads evenly over full duration
    `early_years` defaults to half of duration_years.
    All three scenarios start from the same `initial_balance_today_cad` nest egg.
    Returns dict with keys 'early', 'late', 'steady', 'early_years'.
    """
    if early_years is None:
        early_years = duration_years // 2
    early_years = max(1, min(early_years, duration_years - 1))
    late_years = duration_years - early_years

    end_year = start_year + duration_years - 1
    years = list(range(start_year, end_year + 1))
    returns = _get_returns(index, years)

    total_nominal = total_contributions_today_cad * 12  # annual today-dollars
    initial_balance_nominal = initial_balance_today_cad / get_cpi_factor(start_year, CURRENT_YEAR)

    def _sim(contrib_fn):
        balance = initial_balance_nominal
        rows = []
        for year in years:
            annual_r = returns.get(year, 0.07)
            monthly_r = (1 + annual_r) ** (1 / 12) - 1
            monthly_contrib = contrib_fn(year) / 12
            for _ in range(12):
                balance = balance * (1 + monthly_r) + monthly_contrib
            cpi_to_today = get_cpi_factor(year, CURRENT_YEAR)
            rows.append({
                "year": year,
                "monthly_contribution": round(monthly_contrib, 2),
                "portfolio_value": round(balance, 2),
                "real_portfolio_value": round(balance * cpi_to_today, 2),
            })
        return pd.DataFrame(rows)

    def _nominal_for_year(year, today_annual):
        return today_annual / get_cpi_factor(year, CURRENT_YEAR)

    early_end = start_year + early_years
    late_start = start_year + early_years

    early = _sim(
        lambda y: _nominal_for_year(y, total_nominal / early_years) if y < early_end else 0
    )
    late = _sim(
        lambda y: _nominal_for_year(y, total_nominal / late_years) if y >= late_start else 0
    )
    steady = _sim(
        lambda y: _nominal_for_year(y, total_nominal / duration_years)
    )

    return {"early": early, "late": late, "steady": steady, "early_years": early_years}
