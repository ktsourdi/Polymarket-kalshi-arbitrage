from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import List
from pathlib import Path
import sys

# Ensure project root is on sys.path when running via Streamlit
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app.connectors.demo import fetch_kalshi_demo, fetch_polymarket_demo
from app.core.arb import detect_arbs, detect_two_buy_arbs
from app.core.models import CrossExchangeArb, TwoBuyArb


st.set_page_config(page_title="Polymarket–Kalshi Arbitrage", layout="wide")
st.title("Polymarket–Kalshi Arbitrage Dashboard (Demo)")


@st.cache_data(ttl=5)
def load_quotes_sync():
    # Bridge async demo fetchers into Streamlit
    async def _run():
        return await asyncio.gather(fetch_kalshi_demo(), fetch_polymarket_demo())

    return asyncio.run(_run())


def render_cross_arbs(arbs: List[CrossExchangeArb]):
    if not arbs:
        st.info("No cross-exchange opportunities found.")
        return
    rows = []
    for a in arbs:
        rows.append(
            {
                "event": a.event_key,
                "long_exch": a.long.exchange,
                "long_price": round(a.long.price, 2),
                "short_exch": a.short.exchange,
                "short_price": round(a.short.price, 2),
                "edge_bps": round(a.edge_bps, 1),
                "max_notional": round(a.max_notional, 2),
                "gross_profit_usd": round(a.gross_profit_usd, 2),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def render_two_buy(arbs: List[TwoBuyArb]):
    if not arbs:
        st.info("No two-buy opportunities found.")
        return
    rows = []
    for a in arbs:
        rows.append(
            {
                "event": a.event_key,
                "buy_yes@exch": f"{a.buy_yes.exchange}@{a.buy_yes.price:.2f}",
                "buy_no@exch": f"{a.buy_no.exchange}@{a.buy_no.price:.2f}",
                "sum_price": round(a.sum_price, 2),
                "edge_bps": round(a.edge_bps, 1),
                "contracts": round(a.contracts, 4),
                "gross_profit_usd": round(a.gross_profit_usd, 2),
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


with st.sidebar:
    st.markdown("### Controls")
    mode = st.radio("Mode", ["Demo (detect only)", "Run demo pipeline", "Run live-skeleton"], index=0)
    refresh = st.button("Refresh data", type="primary")
    st.caption("Demo uses randomized mocked quotes.")

if refresh:
    load_quotes_sync.clear()

kalshi, poly = load_quotes_sync()

tab1, tab2 = st.tabs(["Cross-Exchange", "Two-Buy"])
with tab1:
    cross = detect_arbs(kalshi, poly)
    render_cross_arbs(cross)
with tab2:
    two = detect_two_buy_arbs(kalshi, poly)
    render_two_buy(two)

# Actions
st.markdown("---")
if mode == "Run demo pipeline":
    if st.button("Execute demo pipeline now"):
        async def _run():
            from app.main import run_once
            return await run_once()

        result = asyncio.run(_run())
        st.success(f"Demo executed. Opportunities handled: {result}")
elif mode == "Run live-skeleton":
    if st.button("Execute live-skeleton now"):
        async def _run():
            from app.main import run_live_once
            return await run_live_once()

        result = asyncio.run(_run())
        st.success(f"Live-skeleton executed. Opportunities handled: {result}")


