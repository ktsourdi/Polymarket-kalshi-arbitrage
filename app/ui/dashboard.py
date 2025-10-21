from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import List
from pathlib import Path
import sys
import os

# Ensure project root is on sys.path when running via Streamlit
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from app.connectors.demo import fetch_kalshi_demo, fetch_polymarket_demo
from app.core.arb import detect_arbs, detect_two_buy_arbs, detect_arbs_with_matcher
from app.config.settings import settings
from app.core.models import CrossExchangeArb, TwoBuyArb


st.set_page_config(page_title="Polymarket–Kalshi Arbitrage", layout="wide")
st.title("Polymarket–Kalshi Arbitrage Dashboard")


@st.cache_data(ttl=5)
def load_quotes_sync():
    # Bridge async demo fetchers into Streamlit
    async def _run():
        return await asyncio.gather(fetch_kalshi_demo(), fetch_polymarket_demo())

    return asyncio.run(_run())


@st.cache_data(ttl=5)
def load_quotes_live_sync():
    async def _run():
        from app.connectors.kalshi import KalshiClient
        from app.connectors.polymarket import PolymarketClient

        kalshi = KalshiClient(
            base_url=os.getenv("KALSHI_BASE_URL"),
            api_key=os.getenv("KALSHI_API_KEY"),
            api_secret=os.getenv("KALSHI_API_SECRET"),
        )
        poly_ok = bool(os.getenv("POLYMARKET_PRIVATE_KEY") or os.getenv("POLYMARKET_API_KEY"))
        poly = None
        if poly_ok:
            poly = PolymarketClient(
                base_url=os.getenv("POLYMARKET_BASE_URL"),
                api_key=os.getenv("POLYMARKET_API_KEY"),
            )
        try:
            k = await kalshi.fetch_quotes()
        finally:
            await kalshi.close()
        if poly:
            try:
                p = await poly.fetch_quotes()
            finally:
                await poly.close()
        else:
            p = []
        return k, p

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
    st.dataframe(rows, width='stretch', hide_index=True)


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
    st.dataframe(rows, width='stretch', hide_index=True)


with st.sidebar:
    st.markdown("### Controls")
    data_mode = st.radio("Data", ["Demo data", "Live data (read-only)"], index=0)
    mode = st.radio("Mode", ["Detect only", "Run demo pipeline", "Run live-skeleton"], index=0)
    refresh = st.button("Refresh data", type="primary")
    st.caption("Demo uses randomized mocked quotes. Live fetch attempts real APIs.")
    st.markdown("### Matching")
    sim_thresh = st.slider("Fuzzy match threshold", min_value=0.6, max_value=0.95, value=0.8, step=0.01)
    keyword = st.text_input("Keyword filter (optional)", value="")

    st.markdown("### Env status")
    kalshi_ok = bool(os.getenv("KALSHI_API_KEY"))
    poly_ok = bool(os.getenv("POLYMARKET_PRIVATE_KEY") or os.getenv("POLYMARKET_API_KEY"))
    st.write(f"Kalshi: {'OK' if kalshi_ok else 'missing'}")
    st.write(f"Polymarket: {'OK' if poly_ok else 'not found'}")

    st.markdown("### Risk / Fees")
    taker_bps = st.number_input("Taker fee (bps)", min_value=0.0, max_value=200.0, value=float(settings.fees.taker_bps), step=1.0)
    slippage_bps = st.number_input("Slippage buffer (bps)", min_value=0.0, max_value=200.0, value=float(settings.risk.slippage_bps), step=1.0)
    max_notional = st.number_input("Max notional per leg ($)", min_value=10.0, max_value=100000.0, value=float(settings.risk.max_notional_per_leg), step=10.0)
    min_profit = st.number_input("Min profit ($)", min_value=0.0, max_value=1000.0, value=float(settings.risk.min_profit_usd), step=0.5)
    if st.button("Apply settings"):
        # Apply live settings and clear caches so detection recomputes
        settings.fees.taker_bps = float(taker_bps)
        settings.risk.slippage_bps = float(slippage_bps)
        settings.risk.max_notional_per_leg = float(max_notional)
        settings.risk.min_profit_usd = float(min_profit)
        load_quotes_sync.clear()
        if 'load_quotes_live_sync' in globals():
            load_quotes_live_sync.clear()

if refresh:
    load_quotes_sync.clear()

if data_mode == "Demo data":
    kalshi, poly = load_quotes_sync()
else:
    if not kalshi_ok:
        st.error("Kalshi credentials not found. Set KALSHI_API_KEY and private key settings in .env.")
        st.stop()
    if not poly_ok:
        st.warning("Polymarket credentials not found. Proceeding with Kalshi-only live data; cross-exchange results will be empty until you add Polymarket creds.")
    kalshi, poly = load_quotes_live_sync()

# Optional keyword filtering to increase overlap
def _kw_ok(q):
    if not keyword:
        return True
    return keyword.lower() in q.event.lower()
kalshi = [q for q in kalshi if _kw_ok(q)]
poly = [q for q in poly if _kw_ok(q)]

tab1, tab2 = st.tabs(["Cross-Exchange", "Two-Buy"])
with tab1:
    cross = detect_arbs(kalshi, poly)
    if not cross:
        cross = detect_arbs_with_matcher(kalshi, poly, similarity_threshold=sim_thresh)
    render_cross_arbs(cross)
with tab2:
    two = detect_two_buy_arbs(kalshi, poly)
    render_two_buy(two)

# Actions
st.markdown("---")
if data_mode == "Demo data" and mode == "Run demo pipeline":
    if st.button("Execute demo pipeline now"):
        async def _run():
            from app.main import run_once
            return await run_once()

        result = asyncio.run(_run())
        st.success(f"Demo executed. Opportunities handled: {result}")
elif data_mode == "Live data (read-only)" and mode == "Run live-skeleton":
    if st.button("Execute live-skeleton now"):
        async def _run():
            from app.main import run_live_once
            return await run_live_once()

        result = asyncio.run(_run())
        st.success(f"Live-skeleton executed. Opportunities handled: {result}")

# Diagnostics
st.markdown("---")
st.markdown("#### Diagnostics")
def _sample(events, n=5):
    seen = []
    for e in events:
        if e not in seen:
            seen.append(e)
        if len(seen) >= n:
            break
    return seen

kalshi_events = [q.event for q in kalshi]
poly_events = [q.event for q in poly]
col1, col2 = st.columns(2)
with col1:
    st.caption("Kalshi live quotes")
    st.write({"count": len(kalshi_events), "sample": _sample(kalshi_events)})
with col2:
    st.caption("Polymarket live quotes")
    st.write({"count": len(poly_events), "sample": _sample(poly_events)})

# TODO: We could add a matched-pairs preview by running the matcher with a high threshold and listing top overlaps.


