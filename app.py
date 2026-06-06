"""
Historical Index Fund Simulator — standalone app.

Run with:  streamlit run app.py

This is the simulator on its own. The same view also appears as a page inside the
multipage LifePlan app (see Home.py); both call modules.simulator_view.render(),
so they never drift out of sync.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st

from modules.simulator_view import render

st.set_page_config(
    page_title="Historical Index Fund Simulator",
    page_icon="📈",
    layout="wide",
)

render()
