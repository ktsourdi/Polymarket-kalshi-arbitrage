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
from app.core.arb import detect_arbs, detect_two_buy_arbs, detect_arbs_with_matcher, compute_edge_bps, compute_arb_percentage, calculate_profit_for_budget
from app.config.settings import settings
from app.core.models import CrossExchangeArb, TwoBuyArb, MarketQuote as MQ
from app.core.matching import EventMatcher
from app.core.embedding_matcher import build_embedding_candidates_async
from app.utils.text import similarity, extract_numbers_window
from app.utils.ml_match import build_tfidf_map
from app.utils.embeddings import build_embedding_map_openai
from app.utils.llm_validate import validate_pairs_openai
from app.utils.timing import TimingTracker, timer
from app.utils.links import get_event_link, polymarket_market_url, kalshi_market_url
from app.utils.date_filter import filter_by_days_until_resolution, format_resolution_date
from app.utils.liquidity_filter import filter_by_liquidity, get_liquidity_summary
from app.utils.slippage_protection import cap_order_by_liquidity


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


def render_cross_arbs(arbs: List[CrossExchangeArb], budget: float = 1000.0):
    if not arbs:
        st.info("No cross-exchange opportunities found.")
        return
    rows = []
    for a in arbs:
        # Calculate profit for given budget
        arb_pct = compute_arb_percentage(a.edge_bps)
        notional, stake_long, stake_short, profit = calculate_profit_for_budget(
            a.edge_bps, a.max_notional, budget
        )
        
        # Generate links
        long_link = kalshi_market_url(a.long.market_id) if a.long.exchange == "kalshi" else polymarket_market_url(a.long.market_id)
        short_link = kalshi_market_url(a.short.market_id) if a.short.exchange == "kalshi" else polymarket_market_url(a.short.market_id)
        
        # Format strategy string with links
        strategy = f"Buy {a.long.outcome} on [{a.long.exchange}]({long_link}) @ ${a.long.price:.3f}\n" \
                   f"Buy {a.short.outcome} on [{a.short.exchange}]({short_link}) @ ${a.short.price:.3f}"
        
        rows.append(
            {
                "event": a.event_key,
                "arb %": f"{arb_pct:.2f}%",
                "profit": f"${profit:.2f}",
                "stake": f"${notional:.2f}",
                "strategy": strategy,
                "view long": long_link,
                "view short": short_link,
            }
        )
    
    # Display as dataframe with clickable links
    df = st.dataframe(rows, width='stretch', hide_index=True, column_config={
        "view long": st.column_config.LinkColumn("Long Market", display_text="🔗 Open"),
        "view short": st.column_config.LinkColumn("Short Market", display_text="🔗 Open"),
    })


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


def build_match_candidate_rows(
    kalshi_quotes: List[MQ],
    poly_quotes: List[MQ],
    threshold: float,
    explicit_map: dict[str, str] | None = None,
):
    """Build a rows list describing fuzzy-matched pairs with price context.

    This is useful to debug whether our event matching works independently of
    arbitrage profitability.
    """
    matcher = EventMatcher(explicit_map=explicit_map or {}, threshold=threshold)
    # Build lightweight quotes for candidate generation
    cands = matcher.build_candidates(
        [MQ("kalshi", "", q.event, "YES", 0.0, 0.0) for q in kalshi_quotes],
        [MQ("polymarket", "", q.event, "YES", 0.0, 0.0) for q in poly_quotes],
    )

    # Build price lookup by event/outcome for quick edge preview
    from collections import defaultdict

    def _by_event(quotes: List[MQ]):
        d = defaultdict(dict)
        for q in quotes:
            d[q.event][q.outcome] = q
        return d

    k_by = _by_event(kalshi_quotes)
    p_by = _by_event(poly_quotes)

    rows = []
    total_bps = settings.fees.taker_bps + settings.risk.slippage_bps
    for c in sorted(cands, key=lambda x: x.similarity, reverse=True):
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
                "K NO": round(kq.get("NO").price, 3) if "NO" in kq else None,
                "P YES": round(pq.get("YES").price, 3) if "YES" in pq else None,
                "P NO": round(pq.get("NO").price, 3) if "NO" in pq else None,
                "edge_bps K_yes+P_no": round(edge_a, 1) if edge_a is not None else None,
                "edge_bps P_yes+K_no": round(edge_b, 1) if edge_b is not None else None,
            }
        )
    if rows:
        return rows, False

    # Lenient fallback: ignore numeric/date guard and entity overlap to surface
    # nearest neighbors by raw similarity so users can see potential pairs.
    from app.utils.text import similarity as _sim

    best_rows = []
    for ek in {q.event for q in kalshi_quotes}:
        best_ep = None
        best_score = -1.0
        for ep in {q.event for q in poly_quotes}:
            s = float(_sim(ek, ep))
            if s > best_score:
                best_score = s
                best_ep = ep
        if best_ep is None:
            continue
        kq = k_by.get(ek, {})
        pq = p_by.get(best_ep, {})
        edge_a = edge_b = None
        if "YES" in kq and "NO" in pq:
            edge_a = compute_edge_bps(kq["YES"].price, pq["NO"].price) - total_bps
        if "YES" in pq and "NO" in kq:
            edge_b = compute_edge_bps(pq["YES"].price, kq["NO"].price) - total_bps
        best_rows.append(
            {
                "pair": f"{ek} <-> {best_ep}",
                "similarity": round(best_score, 3),
                "K YES": round(kq.get("YES").price, 3) if "YES" in kq else None,
                "K NO": round(kq.get("NO").price, 3) if "NO" in kq else None,
                "P YES": round(pq.get("YES").price, 3) if "YES" in pq else None,
                "P NO": round(pq.get("NO").price, 3) if "NO" in pq else None,
                "edge_bps K_yes+P_no": round(edge_a, 1) if edge_a is not None else None,
                "edge_bps P_yes+K_no": round(edge_b, 1) if edge_b is not None else None,
            }
        )
    # Sort and keep a manageable number for the grid
    best_rows.sort(key=lambda r: r["similarity"], reverse=True)
    return best_rows[:20], True


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
    search_until_found = st.checkbox("Keep searching until found", value=True)
    search_time_limit = st.number_input("Search time limit (s)", min_value=2, max_value=60, value=12, step=1)

    st.markdown("### Env status")
    kalshi_key_ok = bool(os.getenv("KALSHI_API_KEY"))
    kalshi_bearer_ok = bool(os.getenv("KALSHI_BEARER") or os.getenv("KALSHI_SESSION_TOKEN"))
    poly_ok = bool(os.getenv("POLYMARKET_PRIVATE_KEY") or os.getenv("POLYMARKET_API_KEY"))
    if kalshi_bearer_ok:
        st.write("Kalshi: OK (full)")
    elif kalshi_key_ok:
        st.write("Kalshi: Limited (elections-only)")
        st.caption("Add KALSHI_BEARER or KALSHI_SESSION_TOKEN to fetch all markets.")
    else:
        st.write("Kalshi: missing")
    st.write(f"Polymarket: {'OK' if poly_ok else 'not found'}")

    st.markdown("### Risk / Fees")
    taker_bps = st.number_input("Taker fee (bps)", min_value=0.0, max_value=200.0, value=float(settings.fees.taker_bps), step=1.0)
    slippage_bps = st.number_input("Slippage buffer (bps)", min_value=0.0, max_value=200.0, value=float(settings.risk.slippage_bps), step=1.0)
    max_notional = st.number_input("Max notional per leg ($)", min_value=10.0, max_value=100000.0, value=float(settings.risk.max_notional_per_leg), step=10.0)
    min_profit = st.number_input("Min profit ($)", min_value=0.0, max_value=1000.0, value=float(settings.risk.min_profit_usd), step=0.5)
    auto_optimize_fees = st.checkbox("Auto-optimize risk/fees", value=True)
    
    st.markdown("### Profit Calculator")
    budget = st.number_input("Budget ($)", min_value=10.0, max_value=100000.0, value=1000.0, step=50.0)
    
    st.markdown("### Date Filter")
    use_date_filter = st.checkbox("Filter by resolution date", value=False)
    if use_date_filter:
        min_days = st.number_input("Min days until resolution", min_value=0, max_value=365, value=0, step=1)
        max_days = st.number_input("Max days until resolution", min_value=0, max_value=365, value=90, step=1)
    else:
        min_days = None
        max_days = None
    
    st.markdown("### Liquidity Filter")
    use_liquidity_filter = st.checkbox("Filter markets without orders", value=True)
    if use_liquidity_filter:
        require_both_outcomes = st.checkbox("Require both YES and NO orders", value=True)
        min_price = st.number_input("Min price", min_value=0.0, max_value=1.0, value=0.0, step=0.01, format="%.2f")
        min_size = st.number_input("Min size", min_value=0.0, max_value=10000.0, value=0.0, step=10.0)
    else:
        require_both_outcomes = True
        min_price = 0.0
        min_size = 0.0
    
    st.markdown("### Slippage Protection")
    use_slippage_protection = st.checkbox("Cap orders by liquidity depth", value=True)
    if use_slippage_protection:
        max_price_impact = st.number_input("Max price impact (%)", min_value=0.0, max_value=10.0, value=1.0, step=0.1, format="%.1f") / 100.0
    else:
        max_price_impact = 0.01  # Default 1%
    
    if st.button("Apply settings"):
        # Apply live settings and clear caches so detection recomputes
        settings.fees.taker_bps = float(taker_bps)
        settings.risk.slippage_bps = float(slippage_bps)
        settings.risk.max_notional_per_leg = float(max_notional)
        settings.risk.min_profit_usd = float(min_profit)
        # Store slippage protection settings in session state
        st.session_state.max_price_impact = max_price_impact if use_slippage_protection else 0.01
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

# Initialize timing tracker
if 'timing_tracker' not in st.session_state:
    st.session_state.timing_tracker = TimingTracker()

if kalshi is None or poly is None:
    st.session_state.timing_tracker.start("fetch_data")
    if data_mode == "Demo data":
        kalshi, poly = load_quotes_sync()
    else:
        if not (kalshi_key_ok or kalshi_bearer_ok):
            st.error("Kalshi credentials not found. For full coverage set KALSHI_BEARER (or KALSHI_SESSION_TOKEN). API key alone may be limited.")
            st.stop()
        if not poly_ok:
            st.warning("Polymarket credentials not found. Proceeding with Kalshi-only live data; cross-exchange results will be empty until you add Polymarket creds.")
        kalshi, poly = load_quotes_live_sync()
    st.session_state.timing_tracker.stop("fetch_data")
    st.session_state[cache_key] = (kalshi, poly)

# Optional keyword filtering to increase overlap
def _kw_ok(q):
    if not keyword:
        return True
    text = q.event.lower()
    # Match if ANY token (>=3 chars) from the keyword exists in the title
    tokens = [t for t in keyword.lower().replace(",", " ").split() if len(t) >= 3]
    if not tokens:
        return True
    return any(t in text for t in tokens)
kalshi = [q for q in kalshi if _kw_ok(q)]
poly = [q for q in poly if _kw_ok(q)]

# Apply date filter if enabled
if use_date_filter:
    kalshi = filter_by_days_until_resolution(kalshi, min_days=min_days, max_days=max_days)
    poly = filter_by_days_until_resolution(poly, min_days=min_days, max_days=max_days)

# Apply liquidity filter if enabled
if use_liquidity_filter:
    kalshi = filter_by_liquidity(kalshi, require_both_outcomes=require_both_outcomes, min_price=min_price, min_size=min_size)
    poly = filter_by_liquidity(poly, require_both_outcomes=require_both_outcomes, min_price=min_price, min_size=min_size)

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
                # Enforce entity/name overlap to avoid mismatching different people
                for s_orig, (tgt, score) in ml_map.items():
                    try:
                        ents_s = set(extract_entity_tokens(s_orig))
                        ents_t = set(extract_entity_tokens(tgt))
                    except Exception:
                        ents_s, ents_t = set(), set()
                    if ents_s and ents_t and not (ents_s & ents_t):
                        continue
                    auto_map[_key(s_orig)] = tgt
            except Exception as e:  # noqa: BLE001
                st.error(f"OpenAI embeddings failed: {e}")
                # No fallback; leave auto_map empty per user preference
        else:
            st.info("OpenAI embeddings disabled — skipping alias map build.")
    if progress_bar is not None:
        progress_bar.progress(30)

explicit_map_for_detection: dict[str, str] = {k: v for k, v in auto_map.items()} if auto_map else {}

# Separate tabs: Matches (fuzzy pairs), Arbitrage (cross-exchange), Two-Buy
tab_matches, tab1, tab2 = st.tabs(["Matches", "Arbitrage (Cross-Exchange)", "Two-Buy"])

with tab_matches:
    if auto_run_match or run_match:
        st.session_state.timing_tracker.start("match_candidates")
        with st.spinner("Building match candidates..."):
            rows, was_fallback = build_match_candidate_rows(
                kalshi_quotes=kalshi,
                poly_quotes=poly,
                threshold=float(sim_thresh),
                explicit_map=explicit_map_for_detection,
            )
        st.session_state.timing_tracker.stop("match_candidates")
        if rows:
            st.dataframe(rows, width='stretch', hide_index=True)
            if was_fallback:
                st.caption("Showing best approximate pairs (lenient mode). Consider lowering threshold or enabling embeddings for stricter matches.")
        else:
            st.info("No candidate pairs found. Try lowering the threshold or enabling ML embeddings.")
    else:
        st.info("Matching not run yet. Click 'Run matching now' or enable auto-run.")

with tab1:
    if auto_run_match or run_match:
        st.session_state.timing_tracker.start("detect_arbs")
        with st.spinner("Running cross-exchange detection..."):
            # Always use fuzzy matching to find cross-exchange opportunities
            cross = detect_arbs_with_matcher(
                kalshi,
                poly,
                similarity_threshold=sim_thresh,
                explicit_map=explicit_map_for_detection,
            )
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
                        explicit_map=explicit_map_for_detection,
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
        if (not cross) and search_until_found:
            import time as _t
            deadline = _t.time() + float(search_time_limit)
            trial_thresholds = [0.9, 0.85, 0.8, 0.78, 0.75, 0.72, 0.7, 0.68, 0.66, 0.64, 0.62, 0.6]
            i = 0
            while _t.time() < deadline and not cross:
                t = trial_thresholds[i % len(trial_thresholds)]
                cand = detect_arbs_with_matcher(
                    kalshi,
                    poly,
                    similarity_threshold=t,
                    explicit_map=explicit_map_for_detection,
                )
                if cand:
                    chosen_thresh = t
                    cross = cand
                    break
                i += 1
                if progress_bar is not None:
                    progress_bar.progress(min(60 + i * 2, 64))
        # Auto-optimize fees/min profit to surface best edge without user tuning
        chosen_fees = (settings.fees.taker_bps, settings.risk.slippage_bps, settings.risk.min_profit_usd)
        if auto_optimize_fees:
            fee_grid = [1.0, 3.0, 5.0, float(settings.fees.taker_bps)]
            slip_grid = [1.0, 3.0, 5.0, float(settings.risk.slippage_bps)]
            profit_grid = [0.0, 0.5, 1.0, float(settings.risk.min_profit_usd)]
            best_profit = -1.0
            best_combo = None
            best_cross = cross
            # Helper to run detect with temp settings
            def _run_with(tb, sb, mp):
                tb0, sb0, mp0 = settings.fees.taker_bps, settings.risk.slippage_bps, settings.risk.min_profit_usd
                try:
                    settings.fees.taker_bps = float(tb)
                    settings.risk.slippage_bps = float(sb)
                    settings.risk.min_profit_usd = float(mp)
                    res = detect_arbs(kalshi, poly)
                    if not res:
                        res = detect_arbs_with_matcher(
                            kalshi,
                            poly,
                            similarity_threshold=chosen_thresh,
                            explicit_map=explicit_map_for_detection,
                        )
                    return res
                finally:
                    settings.fees.taker_bps, settings.risk.slippage_bps, settings.risk.min_profit_usd = tb0, sb0, mp0
            for tb in fee_grid:
                for sb in slip_grid:
                    for mp in profit_grid:
                        cand = _run_with(tb, sb, mp)
                        if cand:
                            m = max(cand, key=lambda a: (a.gross_profit_usd, a.edge_bps))
                            if m.gross_profit_usd > best_profit:
                                best_profit = m.gross_profit_usd
                                best_combo = (tb, sb, mp)
                                best_cross = cand
            if best_combo is not None:
                chosen_fees = best_combo
                cross = best_cross
        st.session_state.timing_tracker.stop("detect_arbs")
        if progress_bar is not None:
            progress_bar.progress(65)
        # Optional LLM validation to filter implausible pairs by title logic
        if use_llm_validation and cross:
            st.session_state.timing_tracker.start("llm_validation")
            pairs = []
            for c in cross:
                # Titles stored in long/short MarketQuote
                pairs.append((c.long.event, c.short.event))
            try:
                verdicts = validate_pairs_openai(pairs, model=llm_model)
                cross = [c for c in cross if verdicts.get((c.long.event, c.short.event), {}).get("same_event") and verdicts.get((c.long.event, c.short.event), {}).get("direction_consistent", True)]
            except Exception as e:  # noqa: BLE001
                st.warning(f"LLM validation failed: {e}")
            finally:
                st.session_state.timing_tracker.stop("llm_validation")
        cap = []
        if auto_threshold and cross:
            cap.append(f"threshold={chosen_thresh:.2f}")
        if auto_optimize_fees and cross:
            tb, sb, mp = chosen_fees
            cap.append(f"fees={tb:.0f}bps, slip={sb:.0f}bps, min_profit=${mp:.2f}")
        if cap:
            st.caption("Auto settings → " + ", ".join(cap))
        render_best_cross_summary(cross)
        render_cross_arbs(cross, budget=budget)
    else:
        st.info("Matching not run yet. Click 'Run matching now' or enable auto-run.")
with tab2:
    if auto_run_match or run_match:
        st.session_state.timing_tracker.start("detect_two_buy")
        with st.spinner("Running two-buy detection..."):
            two = detect_two_buy_arbs(kalshi, poly)
        st.session_state.timing_tracker.stop("detect_two_buy")
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

# Timing Performance Summary
st.markdown("---")
st.markdown("#### Performance Timing")
timing_summary = st.session_state.timing_tracker.summary()
if timing_summary:
    cols = st.columns(len(timing_summary))
    for idx, (name, duration) in enumerate(timing_summary.items()):
        with cols[idx]:
            st.metric(label=name.replace("_", " ").title(), value=duration)
else:
    st.info("No timing data yet. Run matching to see performance metrics.")

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
uniq_k = len(set(kalshi_events))
uniq_p = len(set(poly_events))
col1, col2 = st.columns(2)
with col1:
    st.caption("Kalshi live quotes")
    st.write({"count": len(kalshi_events), "unique_events": uniq_k, "sample": _sample(kalshi_events)})
with col2:
    st.caption("Polymarket live quotes")
    st.write({"count": len(poly_events), "unique_events": uniq_p, "sample": _sample(poly_events)})

st.markdown("#### Top candidate pairs (fuzzy matching)")
if auto_run_match or run_match:
    try:
        # Use chosen threshold if available, else slider
        try:
            th_display = chosen_thresh  # from above scope if set
        except Exception:
            th_display = sim_thresh
        # If external embeddings enabled, use embedding-based matcher for better recall
        if use_openai:
            if progress_bar is None:
                progress_bar = progress_container.progress(5)
            with st.spinner("Building embedding candidates (OpenAI cache)…"):
                async def _run():
                    start_ts = time.time()
                    eta_text = st.empty()
                    def _progress(frac: float):
                        try:
                            if progress_bar is not None:
                                progress_bar.progress(min(98, max(70, int(70 + 25 * frac))))
                            # ETA estimation
                            elapsed = max(0.0, time.time() - start_ts)
                            if frac > 1e-3:
                                rem = elapsed * (1.0 / max(1e-3, frac) - 1.0)
                                eta_text.caption(f"Embedding matcher: {int(frac*100)}% · ~{int(rem)}s remaining")
                        except Exception:
                            pass
                    result = await build_embedding_candidates_async(
                        kalshi, poly, min_cosine=max(0.6, float(th_display)), model=openai_model, progress_cb=_progress
                    )
                    try:
                        eta_text.empty()
                    except Exception:
                        pass
                    return result
                try:
                    cands = asyncio.run(_run())
                except Exception as e:  # noqa: BLE001
                    st.warning(f"Embedding-based matching failed: {e}")
                    cands = []
        else:
            matcher = EventMatcher(explicit_map=explicit_map_for_detection, threshold=th_display)
            # Build lightweight quotes for candidate generation (chunked)
            def _progress(frac: float):
                try:
                    if progress_bar is not None:
                        progress_bar.progress(min(98, max(70, int(70 + 25 * frac))))
                except Exception:
                    pass
            cands = matcher.build_candidates(
                [MQ("kalshi", "", q.event, "YES", 0.0, 0.0) for q in kalshi],
                [MQ("polymarket", "", q.event, "YES", 0.0, 0.0) for q in poly],
                limit_sources=None,
                max_targets_per_source=50,
                progress_cb=_progress,
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


