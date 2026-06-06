"""
Historical Index Fund Simulator — page in the multipage LifePlan app.

Reached from Home.py. Shares its implementation with the standalone app.py via
modules.simulator_view.render(), so improvements land in both places at once.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from modules.simulator_view import render

st.set_page_config(
    page_title="Historical Simulator",
    page_icon="📈",
    layout="wide",
)

render()
