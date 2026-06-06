import streamlit as st

st.set_page_config(
    page_title="LifePlan — Retirement Nest Egg Planner",
    page_icon="🌱",
    layout="wide",
)

st.title("🌱 LifePlan — Retirement Nest Egg Planner")
st.caption("A Canadian retirement planning tool — built in stages, starting with historical perspective.")

st.divider()

col1, col2 = st.columns([2, 1])

with col1:
    st.markdown("""
    ### What this app does
    LifePlan helps you understand and plan your path to a retirement nest egg.
    It's built in stages — starting simple and adding complexity as you're ready.

    ---

    ### Stage 1 — Historical Index Fund Simulator
    **Currently available** — see the link in the sidebar.

    The simulator answers a deceptively simple question:
    > *"If I had been investing consistently over the last 40 years, what would I have today?"*

    But it answers it **honestly**, accounting for:
    - **Inflation** — $500/month in 1984 was worth far more than $500/month today.
      Naive simulations ignore this and overstate how much early investors actually contributed.
    - **Life stage balance** — people naturally save more aggressively when young
      (lower expenses), and can ease off once the nest egg is large enough to grow itself.
    - **Real historical returns** — not a smooth 7% average, but the actual ups and downs
      of the S&P 500, TSX, and blended portfolios including crashes, recoveries, and everything in between.

    **Key insight this tool teaches:**
    - Early contributions compound the longest and matter the most.
    - There's a *crossover point* — the year your accumulated gains exceed everything you've put in.
      After that point, more than half the nest egg is growth: the market works harder than you do.
    - Starting 10 years earlier often beats contributing more total dollars starting later.
    """)

with col2:
    st.markdown("### Available Pages")
    st.page_link("pages/1_Historical_Simulator.py", label="📈 Historical Simulator", icon="📈")

    st.divider()
    st.markdown("### Coming in Stage 2")
    st.markdown("""
    - Forward-looking projections
    - RRSP, TFSA, FHSA account modelling
    - CPP + OAS government benefits
    - Ontario + federal tax planning
    - Monte Carlo probability simulations
    - Named scenario save & compare
    """)
    st.caption("Stage 2 begins after Stage 1 review.")

st.divider()
st.caption("Built with Streamlit + Plotly | Canadian accounts & CPI data | Past performance ≠ future results")
