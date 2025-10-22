from __future__ import annotations

import asyncio
from dataclasses import asdict
from typing import List
import json
from pathlib import Path
import sys
import os

# Ensure project root is on sys.path when running via Streamlit
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import time

from app.connectors.demo import fetch_kalshi_demo, fetch_polymarket_demo
from app.core.arb import detect_arbs, detect_two_buy_arbs, detect_arbs_with_matcher, compute_edge_bps
from app.config.settings import settings
from app.core.models import CrossExchangeArb, TwoBuyArb, MarketQuote as MQ
from app.core.matching import EventMatcher
from app.utils.text import similarity, extract_numbers_window
from app.utils.ml_match import build_tfidf_map
from app.utils.embeddings import build_embedding_map_openai
from app.utils.llm_validate import validate_pairs_openai


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


def render_best_cross_summary(arbs: List[CrossExchangeArb]):
    if not arbs:
        return
    best = max(arbs, key=lambda a: (a.gross_profit_usd, a.edge_bps))
    spread_pct = (1.0 - (best.long.price + best.short.price)) * 100.0
    edge_pct = best.edge_bps / 100.0
    st.markdown("#### Best opportunity (cross-exchange)")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Spread (gross)", f"{spread_pct:.2f}%")
    c2.metric("Edge (net)", f"{edge_pct:.2f}%")
    c3.metric("Potential Profit", f"${best.gross_profit_usd:.2f}")
    c4.metric("Max Notional", f"${best.max_notional:.0f}")
    st.caption(
        f"Buy YES on {best.long.exchange} @ {best.long.price:.3f} and Buy NO on {best.short.exchange} @ {best.short.price:.3f}."
    )

with st.sidebar:
    st.markdown("### Controls")
    data_mode = st.radio("Data", ["Demo data", "Live data (read-only)"], index=1)
    mode = st.radio("Mode", ["Detect only", "Run demo pipeline", "Run live-skeleton"], index=0)
    refresh = st.button("Refresh data", type="primary")
    st.caption("Demo uses randomized mocked quotes. Live fetch attempts real APIs.")
    st.markdown("### Matching")
    auto_threshold = st.checkbox("Auto-select threshold", value=True)
    if not auto_threshold:
        sim_thresh = st.slider("Fuzzy match threshold", min_value=0.6, max_value=0.95, value=0.8, step=0.01)
    else:
        # Placeholder default; an automatic sweep later selects the actual threshold
        sim_thresh = 0.8
    keyword = st.text_input("Keyword filter (optional)", value="")
    auto_alias = st.checkbox("Auto-build alias from titles", value=True)
    use_openai = st.checkbox("Use external embeddings (OpenAI)", value=True)
    openai_model = st.text_input("OpenAI embedding model", value="text-embedding-3-small")
    strict_numbers = st.checkbox("Strict numeric/date match", value=True)
    auto_run_match = st.checkbox("Auto-run matching on changes", value=False)
    use_llm_validation = st.checkbox("LLM logical validation (OpenAI)", value=True)
    llm_model = st.text_input("LLM model for validation", value="gpt-4o-mini")

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
        # Also clear in-memory session caches
        for k in ["data_demo", "data_live"]:
            if k in st.session_state:
                del st.session_state[k]

if refresh:
    load_quotes_sync.clear()
    if 'load_quotes_live_sync' in globals():
        load_quotes_live_sync.clear()
    for k in ["data_demo", "data_live"]:
        if k in st.session_state:
            del st.session_state[k]

cache_key = "data_demo" if data_mode == "Demo data" else "data_live"
kalshi = None
poly = None
if cache_key in st.session_state:
    try:
        kalshi, poly = st.session_state[cache_key]
    except Exception:
        kalshi, poly = None, None

if kalshi is None or poly is None:
    if data_mode == "Demo data":
        kalshi, poly = load_quotes_sync()
    else:
        if not kalshi_ok:
            st.error("Kalshi credentials not found. Set KALSHI_API_KEY and private key settings in .env.")
            st.stop()
        if not poly_ok:
            st.warning("Polymarket credentials not found. Proceeding with Kalshi-only live data; cross-exchange results will be empty until you add Polymarket creds.")
        kalshi, poly = load_quotes_live_sync()
    st.session_state[cache_key] = (kalshi, poly)

# Optional keyword filtering to increase overlap
def _kw_ok(q):
    if not keyword:
        return True
    return keyword.lower() in q.event.lower()
kalshi = [q for q in kalshi if _kw_ok(q)]
poly = [q for q in poly if _kw_ok(q)]

# Step 2: Matching trigger
run_match = st.button("Run matching now", type="primary")

# Progress bar placeholder for matching routine
progress_container = st.empty()
progress_bar = None

# Optional auto-built alias map using current data
auto_map: dict[str, str] = {}
if auto_alias and (auto_run_match or run_match):
    if progress_bar is None:
        progress_bar = progress_container.progress(5)
    with st.spinner("Building alias map (titles → titles)..."):
        unique_k_events = list({q.event for q in kalshi})
        unique_p_events = list({q.event for q in poly})
        def _key(e: str) -> str:
            return e.lower().strip()
        if use_openai:
            try:
                ml_map = build_embedding_map_openai(
                    unique_k_events,
                    unique_p_events,
                    min_similarity=float(sim_thresh),
                    strict_numbers=bool(strict_numbers),
                    model=openai_model,
                    progress_cb=(lambda f: progress_bar.progress(max(6, int(25 * max(0.0, min(1.0, f))))) if progress_bar else None),
                )
                for s_orig, (tgt, score) in ml_map.items():
                    auto_map[_key(s_orig)] = tgt
            except Exception as e:  # noqa: BLE001
                st.error(f"OpenAI embeddings failed: {e}")
                # No fallback; leave auto_map empty per user preference
        else:
            st.info("OpenAI embeddings disabled — skipping alias map build.")
    if progress_bar is not None:
        progress_bar.progress(30)

explicit_map_for_detection: dict[str, str] = {k: v for k, v in auto_map.items()} if auto_map else {}

tab1, tab2 = st.tabs(["Cross-Exchange", "Two-Buy"])
with tab1:
    if auto_run_match or run_match:
        with st.spinner("Running cross-exchange detection..."):
            cross = detect_arbs(kalshi, poly)
        chosen_thresh = sim_thresh
        if not cross:
            if auto_threshold:
                trial_thresholds = [0.9, 0.85, 0.8, 0.75, 0.72, 0.7, 0.68, 0.66, 0.64, 0.62, 0.6]
                best = []
                for t in trial_thresholds:
                    cand = detect_arbs_with_matcher(
                        kalshi,
                        poly,
                        similarity_threshold=t,
                        explicit_map={},
                    )
                    if cand:
                        # pick best by max gross profit
                        m = max(cand, key=lambda a: (a.gross_profit_usd, a.edge_bps))
                        best.append((t, m.gross_profit_usd, cand))
                if best:
                    best.sort(key=lambda x: x[1], reverse=True)
                    chosen_thresh, _, cross = best[0]
                else:
                    cross = []
            else:
                cross = detect_arbs_with_matcher(
                    kalshi,
                    poly,
                    similarity_threshold=sim_thresh,
                    explicit_map=explicit_map_for_detection,
                )
        if progress_bar is not None:
            progress_bar.progress(65)
        # Optional LLM validation to filter implausible pairs by title logic
        if use_llm_validation and cross:
            pairs = []
            for c in cross:
                # Titles stored in long/short MarketQuote
                pairs.append((c.long.event, c.short.event))
            try:
                verdicts = validate_pairs_openai(pairs, model=llm_model)
                cross = [c for c in cross if verdicts.get((c.long.event, c.short.event), {}).get("same_event") and verdicts.get((c.long.event, c.short.event), {}).get("direction_consistent", True)]
            except Exception as e:  # noqa: BLE001
                st.warning(f"LLM validation failed: {e}")
        if auto_threshold and cross:
            st.caption(f"Auto-selected fuzzy threshold: {chosen_thresh:.2f}")
        render_best_cross_summary(cross)
        render_cross_arbs(cross)
    else:
        st.info("Matching not run yet. Click 'Run matching now' or enable auto-run.")
with tab2:
    if auto_run_match or run_match:
        with st.spinner("Running two-buy detection..."):
            two = detect_two_buy_arbs(kalshi, poly)
        if progress_bar is not None:
            progress_bar.progress(85)
        render_two_buy(two)
    else:
        st.info("Matching not run yet. Click 'Run matching now' or enable auto-run.")

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

st.markdown("#### Top candidate pairs (fuzzy matching)")
if auto_run_match or run_match:
    try:
        # Use chosen threshold if available, else slider
        try:
            th_display = chosen_thresh  # from above scope if set
        except Exception:
            th_display = sim_thresh
        matcher = EventMatcher(explicit_map=explicit_map_for_detection, threshold=th_display)
        # Build lightweight quotes for candidate generation
        cands = matcher.build_candidates(
            [MQ("kalshi", "", q.event, "YES", 0.0, 0.0) for q in kalshi],
            [MQ("polymarket", "", q.event, "YES", 0.0, 0.0) for q in poly],
        )
        # Build price lookup by event/outcome for quick edge preview
        from collections import defaultdict
        def _by_event(quotes: List[MQ]):
            d = defaultdict(dict)
            for q in quotes:
                d[q.event][q.outcome] = q
            return d
        k_by = _by_event(kalshi)
        p_by = _by_event(poly)

        # Compute simple edge preview for each candidate if outcomes available
        rows = []
        total_bps = settings.fees.taker_bps + settings.risk.slippage_bps
        for c in sorted(cands, key=lambda x: x.similarity, reverse=True)[:20]:
            try:
                ek, ep = c.event_key.split(" <-> ", 1)
            except ValueError:
                ek, ep = c.event_key, ""
            kq = k_by.get(ek, {})
            pq = p_by.get(ep, {})
            edge_a = None
            edge_b = None
            if "YES" in kq and "NO" in pq:
                edge_a = compute_edge_bps(kq["YES"].price, pq["NO"].price) - total_bps
            if "YES" in pq and "NO" in kq:
                edge_b = compute_edge_bps(pq["YES"].price, kq["NO"].price) - total_bps
            rows.append(
                {
                    "pair": c.event_key,
                    "similarity": round(float(c.similarity), 3),
                    "K YES": round(kq.get("YES").price, 3) if "YES" in kq else None,
                    "P NO": round(pq.get("NO").price, 3) if "NO" in pq else None,
                    "edge_bps K_yes+P_no": round(edge_a, 1) if edge_a is not None else None,
                    "P YES": round(pq.get("YES").price, 3) if "YES" in pq else None,
                    "K NO": round(kq.get("NO").price, 3) if "NO" in kq else None,
                    "edge_bps P_yes+K_no": round(edge_b, 1) if edge_b is not None else None,
                }
            )
        if rows:
            st.dataframe(rows, width='stretch', hide_index=True)
        else:
            st.info("No candidate pairs found at current threshold. Try lowering the threshold or enabling ML embeddings.")
        if progress_bar is not None:
            progress_bar.progress(100)
    except Exception as e:  # noqa: BLE001
        st.warning(f"Diagnostics error: {e}")
else:
    st.info("Matching not run yet. Click 'Run matching now' or enable auto-run.")

# Auto-alias mapping preview and download
if auto_map:
    st.markdown("#### Auto-built alias mapping (applied)")
    preview = [{"Kalshi": k, "Polymarket": v} for k, v in list(auto_map.items())[:20]]
    st.caption(f"Total pairs: {len(auto_map)} (showing up to 20)")
    st.dataframe(preview, width='stretch', hide_index=True)
    try:
        # Normalize to original casing where possible
        orig_map = {}
        k_index = {q.event.lower().strip(): q.event for q in kalshi}
        for k_lc, v in auto_map.items():
            orig_map[k_index.get(k_lc, k_lc)] = v
        data = json.dumps(orig_map, indent=2)
        st.download_button("Download auto alias JSON", data=data, file_name="alias_map.auto.json", mime="application/json")
    except Exception:
        pass


