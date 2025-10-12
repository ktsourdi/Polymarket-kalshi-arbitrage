import asyncio


def test_run_once_returns_nonnegative():
    from app.main import run_once

    async def _run():
        return await run_once()

    result = asyncio.run(_run())
    assert isinstance(result, int)
    assert result >= 0


def test_two_buy_live_stub_executes_without_errors():
    from app.connectors.kalshi import KalshiClient
    from app.connectors.polymarket import PolymarketClient
    from app.core.executor import LiveExecutor
    from app.connectors.demo import fetch_kalshi_demo, fetch_polymarket_demo
    from app.core.arb import detect_two_buy_arbs

    async def _run():
        k = await fetch_kalshi_demo()
        p = await fetch_polymarket_demo()
        opps = detect_two_buy_arbs(k, p)
        kalshi = KalshiClient()
        poly = PolymarketClient()
        execu = LiveExecutor(kalshi, poly)
        fills = await execu.execute_two_buy(opps[:1])
        await kalshi.close()
        await poly.close()
        return fills

    fills = asyncio.run(_run())
    assert isinstance(fills, list)
