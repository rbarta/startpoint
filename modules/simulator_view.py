"""
Shared view for the Historical Index Fund Simulator.

`render()` builds the entire simulator UI. It is called by:
  - app.py                          (standalone app:  streamlit run app.py)
  - pages/1_Historical_Simulator.py (page in the multipage LifePlan app)

The caller is responsible for st.set_page_config() before calling render().

Inputs are stored in st.session_state under the keys in DEFAULTS so that a
configuration can be saved to / loaded from a JSON file. Two input modes share
those keys:
  - a Guided step-by-step wizard (friendly for first-time users), and
  - the full sidebar controls (toggle the wizard off with a checkbox).
"""
import json

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from modules.calculator import (
    run_historical_sim,
    run_comparison_sim,
    calc_retirement_income,
    CURRENT_YEAR,
    DATA_END_YEAR,
)
from modules.data_io import load_sim_inputs, save_sim_inputs, get_cpi_factor, set_future_inflation
from modules.charts import (
    dark_layout, format_cad, PHASE_COLORS,
    _PRIMARY, _SECONDARY, _WARN, _DANGER, _BG, _BG2, _GRID, _TEXT,
)

# ── Friendly labels ─────────────────────────────────────────────────────────────
INDEX_LABELS = {
    "SP500": "US Stocks — S&P 500",
    "TSX": "Canadian Stocks — TSX",
    "50/50 CA/US": "Half-and-half — 50% Canadian / 50% US",
    "60/40 Blend": "Balanced — 60% stocks / 40% bonds",
}
INDEX_KEYS = list(INDEX_LABELS.keys())

MODEL_LABELS = {
    "inflation_adjusted": "Keep the same buying power (recommended)",
    "nominal_fixed": "Same dollar amount every year",
    "career_growth": "Grows as my career grows",
    "life_stage": "Changes with life stage",
}
MODEL_KEYS = list(MODEL_LABELS.keys())
MODEL_SHORT = {
    "inflation_adjusted": "Inflation-adjusted",
    "nominal_fixed": "Same dollars",
    "career_growth": "Career growth",
    "life_stage": "Life stage",
}
MODEL_HELP = {
    "inflation_adjusted": "Each year is scaled so your contribution always has the same buying power. Realistic and recommended.",
    "nominal_fixed": "The exact same dollar amount every year. This overstates how much you really put in during the early years.",
    "career_growth": "Start lower and grow each year as your income rises.",
    "life_stage": "Save hard early, balance during peak-expense years, then ease off once the nest egg can carry itself.",
}

# ── Guided-mode fixed defaults (for the questions the wizard no longer asks) ─────
RETIRE_AGE = 65                 # guided mode plans contributions until this age
GUIDED_INDEX = "50/50 CA/US"    # guided mode invests 50% Canadian / 50% US by default
DURATION_BOUNDS = (5, 50)       # allowed range for "years invested"
# Latest start year offered: a minimum-length plan whose history still ends at the data end.
START_YEAR_MAX = DATA_END_YEAR - DURATION_BOUNDS[0] + 1

# ── Config schema (also the st.session_state keys) ───────────────────────────────
DEFAULTS = {
    "current_age": 25,
    "monthly_contribution_today_cad": 500,
    "index": "50/50 CA/US",
    "start_year": DATA_END_YEAR - 40 + 1,   # 40-yr plan ending at the latest data year
    "duration_years": 40,
    "initial_balance_today_cad": 0,
    "nest_egg_age": 25,
    "contribution_model": "inflation_adjusted",
    "income_growth_rate_pct": 2.0,
    "build_monthly": 600,
    "balance_monthly": 800,
    "ease_monthly": 400,
    "build_end_age": 35,
    "balance_end_age": 55,
    "depletion_age": 95,
    "post_ret_return_pct": 5.0,
    "inflation_rate_pct": 3.0,
    "early_years": 20,
}
LIFE_KEYS = ["build_monthly", "balance_monthly", "ease_monthly", "build_end_age", "balance_end_age"]

# Static bounds (dynamic-bound fields are clamped just before their widget instead)
NUM_BOUNDS = {
    "current_age": (18, 70),
    "monthly_contribution_today_cad": (50, 10_000),
    "start_year": (1960, START_YEAR_MAX),
    "initial_balance_today_cad": (0, 10_000_000),
    "income_growth_rate_pct": (0.0, 8.0),
    "post_ret_return_pct": (0.0, 10.0),
    "inflation_rate_pct": (0.0, 8.0),
    "build_monthly": (50, 5000),
    "balance_monthly": (50, 5000),
    "ease_monthly": (0, 5000),
}

_LAST_STEP = 3  # wizard step index that shows the results
WIZ_TITLES = {
    0: "About you",
    1: "How much you invest",
    2: "Any savings already?",
}


# ════════════════════════════════════════════════════════════════════════════════
#  Config helpers (save / load / seed)
# ════════════════════════════════════════════════════════════════════════════════
def _coerce(key, val):
    """Validate / clamp a single config value to its type and static bounds."""
    try:
        if key == "index":
            return val if val in INDEX_KEYS else "50/50 CA/US"
        if key == "contribution_model":
            return val if val in MODEL_KEYS else "inflation_adjusted"
        if key == "duration_years":
            lo, hi = DURATION_BOUNDS
            return max(lo, min(int(val), hi))
        default = DEFAULTS[key]
        v = float(val) if isinstance(default, float) else int(val)
        if key in NUM_BOUNDS:
            lo, hi = NUM_BOUNDS[key]
            v = max(lo, min(v, hi))
        return v
    except (TypeError, ValueError):
        return DEFAULTS[key]


def _read_saved_flat() -> dict:
    """Load the persisted config, flattening any nested life_stage_params block."""
    raw = load_sim_inputs() or {}
    flat = {k: raw[k] for k in DEFAULTS if k in raw}
    lsp = raw.get("life_stage_params")
    if isinstance(lsp, dict):
        for sub in LIFE_KEYS:
            if sub in lsp:
                flat[sub] = lsp[sub]
    return flat


def _seed_state(flat: dict):
    """Seed session_state once from the saved config (and sensible defaults)."""
    for k, default in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = _coerce(k, flat.get(k, default))
    # Guided step-by-step setup is on by default for everyone.
    st.session_state.setdefault("_guided", True)
    st.session_state.setdefault("_wizard_step", 0)


def _apply_config(data: dict):
    """Write an uploaded config into session_state (so the widgets pick it up)."""
    for k in DEFAULTS:
        if k in data:
            st.session_state[k] = _coerce(k, data[k])
    lsp = data.get("life_stage_params")
    if isinstance(lsp, dict):
        for sub in LIFE_KEYS:
            if sub in lsp:
                st.session_state[sub] = _coerce(sub, lsp[sub])


def _current_config() -> dict:
    """Snapshot the current settings as a JSON-serialisable config dict."""
    cfg = {k: st.session_state.get(k, DEFAULTS[k]) for k in DEFAULTS}
    cfg["life_stage_params"] = {s: cfg[s] for s in LIFE_KEYS}
    return cfg


def _clamp(key, lo, hi):
    """Clamp an int session value into [lo, hi] before a dynamically-bounded widget."""
    try:
        cur = int(st.session_state.get(key, lo))
    except (TypeError, ValueError):
        cur = lo
    st.session_state[key] = max(lo, min(cur, hi))


def _guided_duration(age) -> int:
    """Years invested so the person retires at RETIRE_AGE (65), clamped to range."""
    lo, hi = DURATION_BOUNDS
    return max(lo, min(RETIRE_AGE - int(age), hi))


def _guided_window(age):
    """Start year + duration so the whole plan to age 65 runs on real history.

    The window ends at the latest available data year (DATA_END_YEAR), and the
    start year is backed up by the full duration — so every contribution year up
    to retirement uses actual historical returns (no truncation, no projection).
    """
    dur = _guided_duration(age)
    start = DATA_END_YEAR - dur + 1
    return start, dur


# ── Wizard navigation callbacks ──────────────────────────────────────────────────
def _wiz_go(to):
    st.session_state["_wizard_step"] = max(0, min(int(to), _LAST_STEP))


def _wiz_next():
    _wiz_go(st.session_state.get("_wizard_step", 0) + 1)


def _wiz_back():
    _wiz_go(st.session_state.get("_wizard_step", 0) - 1)


# ════════════════════════════════════════════════════════════════════════════════
#  Sidebar: guided toggle + save / load
# ════════════════════════════════════════════════════════════════════════════════
def _sidebar_top():
    with st.sidebar:
        st.checkbox(
            "🧭 Guided step-by-step setup",
            key="_guided",
            help="Walks you through a few simple questions. Uncheck it any time for the full controls.",
        )

        with st.expander("💾 Save / load my setup", expanded=False):
            st.download_button(
                "⬇️ Save setup to a file",
                data=json.dumps(_current_config(), indent=2),
                file_name="lifeplan_simulator_setup.json",
                mime="application/json",
                width="stretch",
                help="Downloads your current settings as a small JSON file you can keep or share.",
            )
            up = st.file_uploader(
                "⬆️ Load a setup — drag & drop a .json here",
                type=["json"],
                key="_cfg_upload",
            )
            if up is not None:
                uid = getattr(up, "file_id", None) or f"{up.name}:{getattr(up, 'size', 0)}"
                if st.session_state.get("_last_upload_id") != uid:
                    try:
                        data = json.load(up)
                        if not isinstance(data, dict):
                            raise ValueError
                    except (json.JSONDecodeError, ValueError):
                        st.error("That file isn't a valid setup (couldn't read JSON).")
                    else:
                        _apply_config(data)
                        st.session_state["_last_upload_id"] = uid
                        st.success("Setup loaded ✓")
                        st.rerun()


# ════════════════════════════════════════════════════════════════════════════════
#  Guided wizard (writes into the same session_state keys as the sidebar)
# ════════════════════════════════════════════════════════════════════════════════
def _wizard() -> bool:
    """Render the step-by-step setup. Returns True once it's time to show results."""
    step = int(st.session_state.get("_wizard_step", 0))
    ready = step >= _LAST_STEP

    st.progress(min(step, _LAST_STEP) / _LAST_STEP)
    if not ready:
        st.markdown(f"#### Step {step + 1} of {_LAST_STEP} — {WIZ_TITLES[step]}")

    with st.container(border=True):
        if step == 0:
            st.write("👋 Let's see what steady investing could have done. Just two quick questions.")
            st.number_input(
                "How old were you when you started investing?",
                min_value=18, max_value=70, key="current_age",
            )
            st.caption(
                f"We'll invest in a **50/50 mix of Canadian & US stocks** using **real market "
                f"history** through {DATA_END_YEAR}, so the plan runs right up to age **{RETIRE_AGE}**. "
                f"Uncheck guided mode any time to change this."
            )
        elif step == 1:
            st.number_input(
                "How much could you invest each month? (in today's dollars)",
                min_value=50, max_value=10_000, step=50,
                key="monthly_contribution_today_cad",
                help="Don't worry about past dollars — the app converts this for each year automatically.",
            )
        elif step == 2:
            st.number_input(
                "Did you already have some savings to start with? (today's $, 0 if none)",
                min_value=0, max_value=10_000_000, step=1000,
                key="initial_balance_today_cad",
            )
            if int(st.session_state["initial_balance_today_cad"]) > 0:
                _age = int(st.session_state["current_age"])
                _start, _dur = _guided_window(_age)
                _ey = min(_start + _dur - 1, DATA_END_YEAR)
                _ret = _age + (_ey - _start + 1)
                _clamp("nest_egg_age", _age, max(_age, _ret - 1))
                st.number_input(
                    "…and you had that saved up by what age?",
                    min_value=_age, max_value=max(_age, _ret - 1), step=1,
                    key="nest_egg_age",
                )
        else:  # step == _LAST_STEP — review
            st.markdown("##### ✅ All set — here's your setup")
            _age = int(st.session_state["current_age"])
            _ib = int(st.session_state["initial_balance_today_cad"])
            _start, _dur = _guided_window(_age)
            _end = min(_start + _dur - 1, DATA_END_YEAR)
            st.markdown(
                f"- **Age at start:** {_age}  (contributing until age {RETIRE_AGE})\n"
                f"- **Monthly contribution:** ${int(st.session_state['monthly_contribution_today_cad']):,} (today's $)\n"
                f"- **Invested in:** {INDEX_LABELS[GUIDED_INDEX]}\n"
                f"- **Window:** {_start} → {_end}  ({_dur} years of real market history)\n"
                + (f"- **Starting savings:** ${_ib:,} by age {int(st.session_state['nest_egg_age'])}\n" if _ib > 0 else "")
            )
            st.caption(
                "Want more control — different index, start year, contribution style, retirement "
                "assumptions? Just **uncheck “Guided step-by-step setup”** in the sidebar."
            )

    # ── navigation ──
    cols = st.columns([1, 1, 1, 3])
    if step > 0:
        cols[0].button("← Back", on_click=_wiz_back, width="stretch")
    if step < _LAST_STEP:
        cols[1].button("Next →", type="primary", on_click=_wiz_next, width="stretch")
        if step == 0:
            cols[2].button(
                "Skip ⏭", on_click=_wiz_go, args=(_LAST_STEP,), width="stretch",
                help="Use sensible defaults and jump straight to the results.",
            )
    else:
        cols[1].button("↺ Start over", on_click=_wiz_go, args=(0,), width="stretch")

    return ready


# ════════════════════════════════════════════════════════════════════════════════
#  Full sidebar controls (when the wizard is turned off)
# ════════════════════════════════════════════════════════════════════════════════
def _sidebar_inputs():
    with st.sidebar:
        st.header("Your plan")

        current_age = st.number_input(
            "How old were you when you started?",
            min_value=18, max_value=70, key="current_age",
            help="Your age in the start year you pick below.",
        )
        st.number_input(
            "How much can you invest each month?",
            min_value=50, max_value=10_000, step=50,
            key="monthly_contribution_today_cad",
            help="In today's dollars. The app figures out the right amount for each past year for you.",
        )
        st.selectbox(
            "What did you invest in?",
            options=INDEX_KEYS, format_func=lambda k: INDEX_LABELS[k],
            key="index",
        )

        st.markdown("**The time window**")
        duration_years = st.slider(
            "How many years did you invest?",
            min_value=DURATION_BOUNDS[0], max_value=DURATION_BOUNDS[1], key="duration_years",
            help=f"The window is anchored to end at the latest market data ({DATA_END_YEAR}), "
                 f"so the start year is set for you. Tip: to retire at {RETIRE_AGE}, "
                 f"use {RETIRE_AGE} − your age.",
        )
        # Auto-anchor: the plan always ends at the latest year of historical data,
        # so the start year is derived from the duration (matches guided mode).
        start_year = DATA_END_YEAR - duration_years + 1
        st.session_state["start_year"] = start_year
        retirement_age = current_age + duration_years
        st.caption(
            f"📅 Investing **{start_year} → {DATA_END_YEAR}** "
            f"(age **{current_age} → {retirement_age}**) — ending at the latest market data."
        )

        with st.expander("⚙️ More options", expanded=False):
            st.markdown("##### 💰 Already have some savings?")
            initial_balance = st.number_input(
                "Starting amount (today's $)",
                min_value=0, max_value=10_000_000, step=1000,
                key="initial_balance_today_cad",
                help="Leave at 0 if you're starting from scratch.",
            )
            if initial_balance > 0:
                _clamp("nest_egg_age", current_age, max(current_age, retirement_age - 1))
                st.number_input(
                    "…that you had by age",
                    min_value=current_age, max_value=max(current_age, retirement_age - 1), step=1,
                    key="nest_egg_age",
                    help="We'll start the simulation at this age with this amount already invested.",
                )

            st.markdown("##### 📈 How do your contributions change over time?")
            model = st.radio(
                "Contribution style",
                options=MODEL_KEYS, format_func=lambda k: MODEL_LABELS[k],
                key="contribution_model", label_visibility="collapsed",
            )
            st.caption(MODEL_HELP[model])

            if model == "career_growth":
                st.slider(
                    "How fast do contributions grow each year? (%)",
                    min_value=0.0, max_value=8.0, step=0.5,
                    key="income_growth_rate_pct",
                    help="Above inflation — mimics rising income over a career.",
                )

            if model == "life_stage":
                nea = int(st.session_state.get("nest_egg_age", current_age))
                st.markdown("**Build** — save hard early (low expenses)")
                st.number_input(
                    "Monthly while building (today's $)", min_value=50, max_value=5000, step=50,
                    key="build_monthly",
                )
                _clamp("build_end_age", nea + 1, 60)
                build_end_age = st.slider(
                    "Build phase ends at age", min_value=nea + 1, max_value=60, key="build_end_age",
                )
                st.markdown("**Balance** — peak expenses, keep saving")
                st.number_input(
                    "Monthly while balancing (today's $)", min_value=50, max_value=5000, step=50,
                    key="balance_monthly",
                )
                _clamp("balance_end_age", build_end_age + 1, 70)
                st.slider(
                    "Balance phase ends at age", min_value=build_end_age + 1, max_value=70,
                    key="balance_end_age",
                )
                st.markdown("**Ease** — let the nest egg do the work")
                st.number_input(
                    "Monthly while easing off (today's $)", min_value=0, max_value=5000, step=50,
                    key="ease_monthly",
                )

            st.markdown("##### 🏖️ Turning it into retirement income")
            _clamp("depletion_age", retirement_age + 1, 110)
            st.slider(
                "Make the money last until age",
                min_value=retirement_age + 1, max_value=110, key="depletion_age",
                help="The nest egg is drawn down to zero by this age.",
            )
            st.slider(
                "Return during retirement (%)",
                min_value=0.0, max_value=10.0, step=0.25, key="post_ret_return_pct",
                help="A conservative return while you're drawing the money down.",
            )
            st.slider(
                "Inflation during retirement (%)",
                min_value=0.0, max_value=8.0, step=0.25, key="inflation_rate_pct",
                help="Withdrawals grow at this rate so your spending power stays steady.",
            )


# ════════════════════════════════════════════════════════════════════════════════
#  Responsive styling (phone + computer)
# ════════════════════════════════════════════════════════════════════════════════
def _inject_responsive_css():
    """Inject CSS media queries so the layout adapts to small (phone) screens.

    Pure CSS — it reacts to the browser's real viewport width, so the same app
    looks right on a computer and reflows sensibly on a phone.
    """
    st.markdown(
        """
<style>
/* ── Phones / narrow screens ─────────────────────────────────────────────── */
@media (max-width: 640px) {
    /* Reclaim horizontal space taken by the wide-layout margins */
    .block-container,
    [data-testid="stMainBlockContainer"] {
        padding: 1rem 0.75rem 3rem 0.75rem !important;
    }

    /* KPI rows and button rows: stack one-per-line at full width on phones */
    div[data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
        gap: 0.4rem !important;
    }
    div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
    div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {
        flex: 1 1 100% !important;
        min-width: 100% !important;
    }

    /* Metrics: keep numbers readable but not huge */
    div[data-testid="stMetricValue"] { font-size: 1.25rem !important; }
    div[data-testid="stMetricLabel"] p { font-size: 0.72rem !important; }

    /* Smaller headings so titles don't wrap awkwardly */
    h1 { font-size: 1.4rem !important; line-height: 1.25 !important; }
    h2 { font-size: 1.15rem !important; }
    h3 { font-size: 1.0rem !important; }

    /* Let the tab bar scroll sideways rather than crushing the labels */
    div[data-testid="stTabs"] div[data-baseweb="tab-list"] {
        overflow-x: auto !important;
        flex-wrap: nowrap !important;
    }
    div[data-testid="stTabs"] button[data-baseweb="tab"] { white-space: nowrap !important; }

    /* Keep charts inside the viewport (no sideways scrolling) */
    div[data-testid="stPlotlyChart"] { width: 100% !important; overflow-x: hidden; }

    /* Wide tables scroll within their own box instead of stretching the page */
    div[data-testid="stMarkdown"] table { display: block; overflow-x: auto; white-space: nowrap; }
}
</style>
""",
        unsafe_allow_html=True,
    )


def _is_mobile() -> bool:
    """Best-effort phone detection from the request User-Agent (server-side).

    Used to show the results sections as a dropdown on phones vs. tabs on desktop.
    Falls back to False (desktop) if headers aren't available (e.g. in tests).
    """
    try:
        ua = (st.context.headers.get("User-Agent", "") or "").lower()
    except Exception:
        return False
    return any(t in ua for t in ("mobile", "android", "iphone", "ipod", "ipad", "windows phone"))


def _show_chart(fig, mobile=False):
    """Render a Plotly chart full-width.

    On phones the legend is moved to a horizontal row *below* the plot (instead of
    Plotly's default right-hand column), so it no longer squeezes the chart width.
    """
    if mobile:
        fig.update_layout(
            legend=dict(
                orientation="h", yanchor="top", y=-0.25,
                xanchor="left", x=0, font=dict(size=10),
            ),
            margin=dict(l=10, r=10, t=30, b=100),
        )
    st.plotly_chart(fig, width="stretch", config={"responsive": True, "displaylogo": False})


# ════════════════════════════════════════════════════════════════════════════════
#  Main entry point
# ════════════════════════════════════════════════════════════════════════════════
def render():
    _inject_responsive_css()
    st.title("📈 Historical Index Fund Simulator")
    st.caption(
        "See what steady investing would *actually* have done — using real historical "
        "returns, with inflation handled honestly so the numbers don't lie to you."
    )

    # Streamlit clears a keyed widget's stored value on any run where that widget
    # isn't rendered (e.g. moving between wizard steps that show different inputs).
    # Re-assigning each key keeps the user's entered values alive across steps.
    for _k in DEFAULTS:
        if _k in st.session_state:
            st.session_state[_k] = st.session_state[_k]

    _seed_state(_read_saved_flat())
    _sidebar_top()

    guided = st.session_state.get("_guided", False)
    if guided:
        # Guided mode fixes the questions the wizard no longer asks: invest in US
        # stocks and contribute until age 65. The window is chosen so the whole
        # plan up to retirement runs on real history — it ends at the latest data
        # year (DATA_END_YEAR) and the start year is backed up by the full duration.
        st.session_state["index"] = GUIDED_INDEX
        ready = _wizard()
        if not ready:
            return  # still collecting answers — don't show results yet
        start, dur = _guided_window(st.session_state["current_age"])
        st.session_state["start_year"] = start
        st.session_state["duration_years"] = dur
        st.divider()
    else:
        _sidebar_inputs()

    # ── Resolve inputs from session_state ───────────────────────────────────────
    current_age = int(st.session_state["current_age"])
    monthly_today = int(st.session_state["monthly_contribution_today_cad"])
    index_choice = st.session_state["index"]
    start_year = int(st.session_state["start_year"])
    duration_years = int(st.session_state["duration_years"])
    end_year = min(start_year + duration_years - 1, DATA_END_YEAR)
    actual_duration = end_year - start_year + 1
    retirement_age = current_age + actual_duration

    initial_balance = int(st.session_state["initial_balance_today_cad"])
    nest_egg_age = (
        max(current_age, min(int(st.session_state["nest_egg_age"]), retirement_age - 1))
        if initial_balance > 0 else current_age
    )
    model = st.session_state["contribution_model"]
    income_growth_rate = float(st.session_state["income_growth_rate_pct"])
    depletion_age = max(int(st.session_state["depletion_age"]), retirement_age + 1)
    post_ret_return = float(st.session_state["post_ret_return_pct"])
    inflation_rate = float(st.session_state["inflation_rate_pct"])
    life_stage_params = {k: int(st.session_state[k]) for k in LIFE_KEYS}

    if actual_duration < duration_years:
        st.caption(
            f"ℹ️ History only goes to {DATA_END_YEAR}, so showing {actual_duration} years "
            f"(age {current_age} → {retirement_age})."
        )

    # ── Effective window (shifts forward if a nest egg starts at a later age) ────
    if initial_balance > 0 and nest_egg_age > current_age:
        skip_years = nest_egg_age - current_age
        eff_start_year = start_year + skip_years
        eff_end_year = min(eff_start_year + actual_duration - skip_years - 1, DATA_END_YEAR)
        eff_duration = max(1, eff_end_year - eff_start_year + 1)
        eff_age = nest_egg_age
    else:
        eff_start_year = start_year
        eff_end_year = end_year
        eff_duration = actual_duration
        eff_age = current_age

    # Project CPI past the data end up to today using the retirement-inflation rate,
    # so every "today's $" figure is expressed in CURRENT_YEAR dollars.
    set_future_inflation(inflation_rate)

    # ── Run the simulation (live — no button needed) ────────────────────────────
    df = run_historical_sim(
        start_year=eff_start_year,
        duration_years=eff_duration,
        index=index_choice,
        contribution_model=model,
        monthly_today_cad=monthly_today,
        income_growth_rate=income_growth_rate,
        current_age=eff_age,
        life_stage_params=life_stage_params,
        initial_balance_today_cad=initial_balance,
    )

    # Persist settings silently so they're remembered next time
    save_sim_inputs(_current_config())

    # ── Derived figures ─────────────────────────────────────────────────────────
    df_accum = df.iloc[:-1]                      # accumulation rows (drop final snapshot)
    final_row = df.iloc[-1]
    initial_balance_nominal = initial_balance / get_cpi_factor(eff_start_year, CURRENT_YEAR)
    new_contributions = df_accum["annual_contribution"].sum()
    total_committed = new_contributions + initial_balance_nominal
    final_nominal = final_row["portfolio_value"]
    final_real = final_row["real_portfolio_value"]
    multiple = final_nominal / total_committed if total_committed > 0 else 0

    tipping_rows = df[df["tipping_point"] == True]
    tipping_year = int(tipping_rows.iloc[0]["year"]) if len(tipping_rows) > 0 else None
    tipping_age = int(tipping_rows.iloc[0]["age"]) if len(tipping_rows) > 0 else None

    retirement_year = eff_end_year + 1
    ri = calc_retirement_income(
        portfolio_at_retirement=final_nominal,
        retirement_age=retirement_age,
        depletion_age=depletion_age,
        retirement_year=retirement_year,
        # "Today's money" = CURRENT_YEAR dollars: convert the retirement-year payment
        # by the gap between today and retirement (negative if retirement is already
        # in the past relative to today), NOT by the full investing duration.
        years_to_retirement=retirement_year - CURRENT_YEAR,
        post_retirement_return_pct=post_ret_return,
        inflation_rate_pct=inflation_rate,
    )

    # ════════════════════════════════════════════════════════════════════════════
    #  Headline numbers
    # ════════════════════════════════════════════════════════════════════════════
    if initial_balance > 0:
        c0, c1, c2, c3 = st.columns(4)
        c0.metric("You put in", format_cad(total_committed),
                  help=f"{format_cad(initial_balance)} starting + {format_cad(new_contributions)} contributed.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("You put in", format_cad(new_contributions),
                  help="Total contributed over the whole period (nominal dollars).")

    c2.metric("It grew to", format_cad(final_nominal),
              help=f"Portfolio value at the end of {eff_end_year}.")
    c3.metric("Monthly income", format_cad(ri["monthly_today"]) + "/mo",
              help=f"What you could draw each month in today's ({CURRENT_YEAR}) buying power, "
                   f"making the money last to age {depletion_age}.")

    # Second row — the "wow" framing
    d1, d2, d3 = st.columns(3)
    d1.metric("In today's dollars", format_cad(final_real),
              help="The final nest egg adjusted back to today's buying power.")
    d2.metric("Money multiplier", f"{multiple:.1f}×",
              help="Final value ÷ everything you put in.")
    if tipping_year:
        d3.metric("Compounding took over", f"Age {tipping_age}",
                  help=f"In {tipping_year}, your accumulated investment gains grew larger than "
                       f"everything you'd contributed — from here, more than half the nest egg is "
                       f"pure growth, not your own money.")
    else:
        d3.metric("Compounding took over", "—",
                  help="Your gains never grew past the total you contributed within this window — "
                       "try a longer time period.")

    st.success(
        f"💡 You contributed **{format_cad(total_committed if initial_balance > 0 else new_contributions)}** "
        f"and ended with **{format_cad(final_nominal)}** — that's **{multiple:.1f}×** your money. "
        f"It could pay you about **{format_cad(ri['monthly_today'])}/month** in today's ({CURRENT_YEAR}) dollars through age {depletion_age}."
    )

    # ── Plain-language inflation explainer (dynamic to the chosen year) ──────────
    _infl_factor = get_cpi_factor(start_year, CURRENT_YEAR)
    _past_monthly = monthly_today / _infl_factor
    _past_500 = 500 / _infl_factor
    _years_ago = CURRENT_YEAR - start_year
    with st.expander("💡 Wait — why is $500 not always $500? (how inflation works here)", expanded=False):
        st.markdown(
            f"""
**Money loses buying power over time.** Prices climb year after year, so the same dollar
bought *more* in the past than it does today. Economists measure this with the **Consumer
Price Index (CPI)** — the average price of the things households actually buy.

Since **{start_year}** ({_years_ago} years ago), Canadian prices have risen about
**{_infl_factor:.1f}×**. Run that backwards and:

- **$500 today** had the buying power of only about **${_past_500:,.0f}** back in **{start_year}**.
- Your **${monthly_today:,}/month today** is the same as about **${_past_monthly:,.0f}/month** in {start_year} money.

So if someone in {start_year} wanted to live like you do on ${monthly_today:,}/month, they'd
only have needed ${_past_monthly:,.0f}/month back then — the rest is just prices going up.

---

**Why this app cares.** A naïve simulator assumes you stuffed a flat ${monthly_today:,} into the
market every month, even decades ago. But ${monthly_today:,} back then was a *huge* slice of
income — it would have **overstated your early contributions by about {_infl_factor:.1f}×**.

Instead, this tool keeps your **buying power** constant: it quietly dials each past year's
contribution down to what ${monthly_today:,} today was really worth that year. That's why the
contribution line looks smaller in the early years — those smaller numbers represent the *same
real sacrifice*. It's the honest, apples-to-apples way to look back.

*The "% of typical income" chart on the **🔍 The Details** tab shows the same idea from the
other direction — how big a bite your contribution took out of a normal paycheque each year.*
"""
        )
        if abs(_infl_factor - 3.38) < 0.6:
            st.caption(
                f"(Roughly the famous \"$500 today ≈ $148 back then\" rule of thumb — here it works "
                f"out to about ${_past_500:,.0f} for {start_year} using real Canadian CPI.)"
            )

    # ── What retirement costs in a major city (reference) ───────────────────────
    _income = ri["monthly_today"]
    with st.expander("🏙️ What does retirement cost in a major Canadian city? (for a couple)", expanded=False):
        st.caption(
            f"Rough estimates for a retired **couple** in a high-cost city like Toronto or "
            f"Vancouver, in today's ({CURRENT_YEAR}) dollars. These are planning benchmarks, not "
            f"exact figures — your costs will vary, and other cities run lower."
        )
        st.markdown(
            """
**Monthly spending — a comfortable lifestyle**

| Category | Own home (paid off) | Renting |
|---|---|---|
| Housing (taxes / upkeep / fees, or rent) | $700 – $1,200 | $2,500 – $3,500 |
| Food & groceries | $900 – $1,200 | $900 – $1,200 |
| Transportation (car or transit) | $500 – $900 | $500 – $900 |
| Utilities, internet, phone | $400 – $600 | $300 – $500 |
| Health, dental, drugs, insurance | $400 – $700 | $400 – $700 |
| Recreation, dining, travel | $700 – $1,500 | $700 – $1,500 |
| Misc / clothing / gifts | $300 – $500 | $300 – $500 |
| **Total** | **≈ $4,500 – $6,500 / mo** | **≈ $6,000 – $8,500 / mo** |

**Quick tiers (couple, major city):**
- 🟢 **Modest** — ~$3,500–$4,500/mo if you own outright · ~$5,000–$6,000 renting
- 🔵 **Comfortable** — ~$5,000–$6,500 (own) · ~$6,500–$8,000 (rent)
- 🟠 **Affluent** (frequent travel, two cars) — $8,000–$12,000+/mo

A common rule of thumb: **$60,000–$80,000/year** ($5,000–$6,700/mo) for a comfortable
retirement for a home-owning couple — higher in Toronto or Vancouver.
"""
        )
        st.info(
            "**Government benefits help.** A couple typically receives roughly "
            "**$2,500–$3,500/month combined** from CPP + OAS, so your savings only need to cover the "
            "gap above that. (CPP/OAS modelling is planned for a later stage of this app.)"
        )
        st.markdown(
            f"💡 **Your plan projects about ${_income:,.0f}/month** (today's dollars) from this nest egg "
            f"alone, before CPP/OAS. Compare that to the tiers above. Note the benchmarks are for a "
            f"**couple** — if both partners save similarly, your combined nest-egg income would be "
            f"roughly double this figure."
        )

    st.divider()

    # ════════════════════════════════════════════════════════════════════════════
    #  Results organised into tabs (instead of one long scroll)
    # ════════════════════════════════════════════════════════════════════════════
    mobile = _is_mobile()

    # Each section is a function so it can render as a desktop tab or, on phones,
    # one-at-a-time behind a dropdown selector (see dispatch below). On phones the
    # charts also get a horizontal legend above the plot so it isn't squeezed.

    # ─────────────────────────────────────────────────────────────────────────────
    #  SECTION 1 — Your Results: portfolio over time + drawdown
    # ─────────────────────────────────────────────────────────────────────────────
    def _section_results():
        st.subheader("Your nest egg over time")
        st.caption(
            f"Growing from {eff_start_year} to {eff_end_year}, then paying you an income "
            f"until age {depletion_age}."
        )

        fig1 = go.Figure(layout=dark_layout(x_title="Year", y_title="Value (CAD)"))
        fig1.add_trace(go.Scatter(
            x=df["year"], y=df["cumulative_invested"],
            name="What you put in", fill="tozeroy",
            fillcolor="rgba(74,158,255,0.15)",
            line=dict(color=_SECONDARY, width=1, dash="dot"), mode="lines",
            hovertemplate="$%{y:,.0f}<extra></extra>",
        ))
        fig1.add_trace(go.Scatter(
            x=df["year"], y=df["portfolio_value"],
            name="Nest egg", fill="tonexty",
            fillcolor="rgba(0,196,154,0.20)",
            line=dict(color=_PRIMARY, width=2), mode="lines",
            hovertemplate="$%{y:,.0f}<extra></extra>",
        ))
        fig1.add_trace(go.Scatter(
            x=df["year"], y=df["real_portfolio_value"],
            name="Nest egg (today's $)",
            line=dict(color=_WARN, width=2, dash="dash"), mode="lines",
            hovertemplate="$%{y:,.0f}<extra></extra>",
        ))

        if not ri["drawdown_df"].empty:
            dd = ri["drawdown_df"]
            stitch_year = [retirement_year] + dd["year"].tolist()
            stitch_val = [final_nominal] + dd["portfolio_value"].tolist()
            fig1.add_trace(go.Scatter(
                x=stitch_year, y=stitch_val,
                name=f"Retirement income (→ age {depletion_age})",
                fill="tozeroy", fillcolor="rgba(244,162,97,0.15)",
                line=dict(color=_WARN, width=2), mode="lines",
                hovertemplate="$%{y:,.0f}<extra></extra>",
            ))
            fig1.add_vline(
                x=eff_end_year, line=dict(color=_WARN, width=1, dash="dot"),
                annotation_text=f"Retire (age {retirement_age})",
                annotation_font_color=_WARN, annotation_position="top left",
            )

        if initial_balance > 0:
            fig1.add_hline(
                y=initial_balance_nominal,
                line=dict(color=_SECONDARY, width=1, dash="dot"),
                annotation_text=f"Starting savings ({format_cad(initial_balance_nominal)})",
                annotation_font_color=_SECONDARY, annotation_position="bottom right",
            )

        if tipping_year and tipping_year in df["year"].values:
            tp_val = df.loc[df["year"] == tipping_year, "portfolio_value"].values[0]
            fig1.add_annotation(
                x=tipping_year, y=tp_val,
                text=f"⚡ Gains > everything<br>you put in · {tipping_year}",
                showarrow=True, arrowhead=2,
                arrowcolor=_PRIMARY, font=dict(color=_PRIMARY, size=11),
                bgcolor=_BG2, bordercolor=_PRIMARY,
            )

        _show_chart(fig1, mobile)

        st.info(
            f"**About {format_cad(ri['monthly_today'])}/month in today's money ({CURRENT_YEAR})** "
            f"(or {format_cad(ri['monthly_nominal'])}/month in {retirement_year} dollars). "
            f"Your withdrawals rise {inflation_rate:.1f}%/year to keep up with inflation, the "
            f"portfolio earns {post_ret_return:.1f}%/year, and it runs to $0 right at age {depletion_age}."
        )

    # ─────────────────────────────────────────────────────────────────────────────
    #  SECTION 2 — The Details: growth-vs-contributions, the ride, contribution context
    # ─────────────────────────────────────────────────────────────────────────────
    def _section_details():
        st.subheader("How much was growth vs. your own money?")
        st.caption("The green gap above the blue is pure compounding — money your money made.")

        fig4 = go.Figure(layout=dark_layout(x_title="Year", y_title="Value (CAD)"))
        fig4.add_trace(go.Scatter(
            x=df["year"], y=df["cumulative_invested"],
            name="Your contributions", fill="tozeroy",
            fillcolor="rgba(74,158,255,0.25)",
            line=dict(color=_SECONDARY, width=2), mode="lines",
            hovertemplate="$%{y:,.0f}<extra></extra>",
        ))
        fig4.add_trace(go.Scatter(
            x=df["year"], y=df["portfolio_value"],
            name="Total nest egg", fill="tonexty",
            fillcolor="rgba(0,196,154,0.30)",
            line=dict(color=_PRIMARY, width=2), mode="lines",
            hovertemplate="$%{y:,.0f}<extra></extra>",
        ))
        _show_chart(fig4, mobile)

        st.subheader("The ride — year-by-year returns")
        st.caption("Real history isn't a smooth 7%. Bad years early hurt more than bad years late.")
        colors = [_PRIMARY if r >= 0 else _DANGER for r in df_accum["annual_return_pct"]]
        fig3 = go.Figure(layout=dark_layout(x_title="Year", y_title="Annual Return (%)"))
        fig3.add_trace(go.Bar(
            x=df_accum["year"], y=df_accum["annual_return_pct"],
            marker_color=colors, name="Annual Return",
            text=df_accum["annual_return_pct"].apply(lambda v: f"{v:.0f}%"),
            textposition="outside", textfont=dict(size=9),
            hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
        ))
        fig3.add_hline(y=0, line_color=_GRID, line_width=1)
        fig3.update_layout(showlegend=False)
        _show_chart(fig3, mobile)

        st.subheader("Your monthly contribution, in context")
        st.caption(
            "The dollar amount each year, alongside what that was as a share of a typical "
            "Canadian household income — so you can see how 'heavy' it really felt."
        )
        fig2 = go.Figure(layout=dark_layout(x_title="Year", y_title="Monthly Contribution (CAD)"))
        fig2.update_layout(yaxis2=dict(
            title="% of typical income", overlaying="y", side="right",
            gridcolor=_GRID, tickfont=dict(color=_WARN),
        ))
        fig2.add_trace(go.Scatter(
            x=df_accum["year"], y=df_accum["monthly_contribution"],
            name="Monthly $", line=dict(color=_PRIMARY, width=2),
            mode="lines", yaxis="y1",
            hovertemplate="$%{y:,.0f}/mo<extra></extra>",
        ))
        fig2.add_trace(go.Scatter(
            x=df_accum["year"], y=df_accum["contribution_pct_of_median_income"],
            name="% of income", line=dict(color=_WARN, width=2, dash="dash"),
            mode="lines", yaxis="y2",
            hovertemplate="%{y:.1f}% of income<extra></extra>",
        ))
        _show_chart(fig2, mobile)

        if model == "inflation_adjusted":
            st.info(
                f"**Why early contributions look smaller:** ${monthly_today:,}/month today had the "
                f"buying power of about ${monthly_today / get_cpi_factor(start_year, CURRENT_YEAR):,.0f}/month "
                f"in {start_year}. Assuming a flat ${monthly_today:,}/month back then would overstate what "
                f"you really put in by {get_cpi_factor(start_year, CURRENT_YEAR):.1f}×."
            )

    # ─────────────────────────────────────────────────────────────────────────────
    #  SECTION 3 — Why Timing Matters: early vs late + contribution schedule
    # ─────────────────────────────────────────────────────────────────────────────
    def _section_timing():
        st.subheader("Start early, or contribute more later?")
        st.caption(
            "All three investors put in the **same total dollars** — only the timing differs. "
            "Top: how the nest egg grows. Bottom: when each one was actually contributing."
        )

        with st.expander("Adjust the comparison"):
            _clamp("early_years", 1, max(2, eff_duration - 1))
            early_years = st.slider(
                "The early starter invests for the first… (years)",
                min_value=1, max_value=max(2, eff_duration - 1),
                key="early_years",
                help="Then they stop and let it ride. The late starter invests the same total, but only afterwards.",
            )

        comp = run_comparison_sim(
            start_year=eff_start_year,
            duration_years=eff_duration,
            index=index_choice,
            total_contributions_today_cad=monthly_today,
            early_years=early_years,
            initial_balance_today_cad=initial_balance,
        )

        ey = comp["early_years"]
        ly = eff_duration - ey
        split_yr = eff_start_year + ey

        fig5 = make_subplots(
            rows=2, cols=1, shared_xaxes=True,
            row_heights=[0.62, 0.38], vertical_spacing=0.07,
            subplot_titles=("Nest egg value", "When they were contributing (monthly $)"),
        )
        fig5.add_trace(go.Scatter(
            x=comp["early"]["year"], y=comp["early"]["portfolio_value"],
            name=f"Early starter (first {ey} yrs, then coasts)",
            line=dict(color=_PRIMARY, width=2), mode="lines",
            hovertemplate="$%{y:,.0f}<extra></extra>",
        ), row=1, col=1)
        fig5.add_trace(go.Scatter(
            x=comp["late"]["year"], y=comp["late"]["portfolio_value"],
            name=f"Late starter (last {ly} yrs)",
            line=dict(color=_DANGER, width=2), mode="lines",
            hovertemplate="$%{y:,.0f}<extra></extra>",
        ), row=1, col=1)
        fig5.add_trace(go.Scatter(
            x=comp["steady"]["year"], y=comp["steady"]["portfolio_value"],
            name="Steady (spread evenly)",
            line=dict(color=_SECONDARY, width=2, dash="dash"), mode="lines",
            hovertemplate="$%{y:,.0f}<extra></extra>",
        ), row=1, col=1)
        fig5.add_trace(go.Bar(
            x=comp["early"]["year"], y=comp["early"]["monthly_contribution"],
            name="Early", marker_color=_PRIMARY, opacity=0.85, showlegend=False,
            hovertemplate="Early: $%{y:,.0f}/mo<extra></extra>",
        ), row=2, col=1)
        fig5.add_trace(go.Bar(
            x=comp["late"]["year"], y=comp["late"]["monthly_contribution"],
            name="Late", marker_color=_DANGER, opacity=0.85, showlegend=False,
            hovertemplate="Late: $%{y:,.0f}/mo<extra></extra>",
        ), row=2, col=1)
        fig5.add_trace(go.Bar(
            x=comp["steady"]["year"], y=comp["steady"]["monthly_contribution"],
            name="Steady", marker_color=_SECONDARY, opacity=0.60, showlegend=False,
            hovertemplate="Steady: $%{y:,.0f}/mo<extra></extra>",
        ), row=2, col=1)
        for row in (1, 2):
            fig5.add_vline(x=split_yr - 0.5, line=dict(color=_WARN, width=1, dash="dot"), row=row, col=1)

        fig5.update_layout(
            barmode="overlay", paper_bgcolor=_BG, plot_bgcolor=_BG2,
            font=dict(color=_TEXT, family="sans-serif"),
            legend=dict(bgcolor=_BG2, bordercolor=_GRID, font=dict(color=_TEXT),
                        orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
            margin=dict(l=60, r=20, t=70, b=50), height=580,
            hovermode="x unified",
            hoverlabel=dict(bgcolor=_BG2, bordercolor=_GRID, font=dict(color=_TEXT, size=12), namelength=-1),
        )
        fig5.update_xaxes(gridcolor=_GRID, zerolinecolor=_GRID, tickfont=dict(color=_TEXT))
        fig5.update_yaxes(gridcolor=_GRID, zerolinecolor=_GRID, tickfont=dict(color=_TEXT))
        for ann in fig5.layout.annotations:
            ann.font.color = _TEXT

        _show_chart(fig5, mobile)

        early_final = comp["early"]["portfolio_value"].iloc[-1]
        late_final = comp["late"]["portfolio_value"].iloc[-1]
        advantage = ((early_final - late_final) / late_final * 100) if late_final > 0 else 0
        st.info(
            f"**The early starter finishes with {format_cad(early_final)}** vs "
            f"**{format_cad(late_final)}** for the late starter — a **{advantage:.0f}% head start**, "
            f"even though both invested the same total. Those first dollars had the most time to compound."
        )

        st.divider()

        st.subheader("Your contribution schedule")
        st.caption(
            f"How much you put in each year under the **{MODEL_SHORT.get(model, model)}** style."
            + (" Phases are colour-coded." if model == "life_stage" else "")
        )
        fig6 = go.Figure(layout=dark_layout(x_title="Year", y_title="Monthly Contribution (CAD)"))
        if model == "life_stage":
            for phase, color in PHASE_COLORS.items():
                phase_df = df_accum[df_accum["life_phase"] == phase]
                if phase_df.empty:
                    continue
                fig6.add_trace(go.Bar(
                    x=phase_df["year"], y=phase_df["monthly_contribution"],
                    name=f"{phase}", marker_color=color,
                    hovertemplate=f"{phase}: $%{{y:,.0f}}/mo<extra></extra>",
                ))
            fig6.update_layout(barmode="stack")
        else:
            label = MODEL_SHORT.get(model, model)
            fig6.add_trace(go.Bar(
                x=df_accum["year"], y=df_accum["monthly_contribution"],
                name=label, marker_color=_PRIMARY,
                hovertemplate=f"{label}: $%{{y:,.0f}}/mo<extra></extra>",
            ))
        if tipping_year:
            fig6.add_vline(
                x=tipping_year, line_color=_WARN, line_dash="dash",
                annotation_text=f"⚡ {tipping_year}",
                annotation_font_color=_WARN, annotation_position="top right",
            )
        _show_chart(fig6, mobile)

        if tipping_year:
            st.info(
                f"**At age {tipping_age} ({tipping_year}), compounding took over.** "
                f"That's the year your accumulated market gains grew larger than every dollar you'd "
                f"contributed — from here on, more than half your nest egg is growth, not your own "
                f"money. The earlier this happens, the more the market is doing the work for you."
            )

    # ── Show as tabs (computer) or a dropdown selector (phone) ───────────────────
    _sections = {
        "📊 Your Results": _section_results,
        "🔍 The Details": _section_details,
        "⏱️ Why Timing Matters": _section_timing,
    }
    if mobile:
        choice = st.selectbox("Show section", list(_sections), key="_mobile_section")
        _sections[choice]()
    else:
        _t1, _t2, _t3 = st.tabs(list(_sections))
        with _t1:
            _section_results()
        with _t2:
            _section_details()
        with _t3:
            _section_timing()

    # ════════════════════════════════════════════════════════════════════════════
    #  Footer
    # ════════════════════════════════════════════════════════════════════════════
    st.divider()
    with st.expander("ℹ️ Notes & assumptions"):
        st.markdown("""
- **US Stocks (S&P 500)** uses USD total return (price + reinvested dividends). No CAD/USD conversion is applied.
- **Canadian Stocks (TSX)** is the S&P/TSX Composite total return in CAD. Pre-1977 data uses academic reconstructions.
- **Half-and-half (50/50 CA/US)** is 50% S&P 500 + 50% S&P/TSX Composite, rebalanced each year.
- **Balanced** is 60% S&P 500 + 40% bonds (bonds approximated at a flat 4%).
- Inflation uses Statistics Canada CPI (All-items). It scales contributions back in time and portfolio values to today's dollars.
- The "% of income" line uses approximate median Canadian household income — context only.
- Monthly compounding is applied to annual returns: `monthly = (1 + annual)^(1/12) − 1`.
- **Past performance does not predict future returns.** This tool is educational only.
""")
