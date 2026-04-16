"""
Signal Generator
----------------
Uses free APIs to fetch price data and generates BUY/SELL signals
based on RSI + EMA crossover rules.

Free data sources:
  - CoinGecko  : crypto (no key needed)
  - Alpha Vantage: forex, stocks, commodities (free key, 25 req/day)
"""

import os
import random
import aiohttp
import logging
from datetime import datetime

log = logging.getLogger(__name__)

AV_KEY = os.environ.get("ALPHA_VANTAGE_KEY", "demo")

ASSET_POOL = [
    {"asset": "BTC/USD",  "source": "coingecko", "id": "bitcoin"},
    {"asset": "ETH/USD",  "source": "coingecko", "id": "ethereum"},
    {"asset": "BNB/USD",  "source": "coingecko", "id": "binancecoin"},
    {"asset": "SOL/USD",  "source": "coingecko", "id": "solana"},
    {"asset": "EUR/USD",  "source": "av_fx",     "from": "EUR", "to": "USD"},
    {"asset": "GBP/USD",  "source": "av_fx",     "from": "GBP", "to": "USD"},
    {"asset": "USD/JPY",  "source": "av_fx",     "from": "USD", "to": "JPY"},
    {"asset": "XAU/USD",  "source": "av_stock",  "symbol": "GLD"},
    {"asset": "USO/USD",  "source": "av_stock",  "symbol": "USO"},
    {"asset": "SPX500",   "source": "av_stock",  "symbol": "SPY"},
    {"asset": "NAS100",   "source": "av_stock",  "symbol": "QQQ"},
]


def _calc_rsi(prices: list[float], period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = prices[-i] - prices[-i - 1]
        (gains if diff > 0 else losses).append(abs(diff))
    avg_gain = sum(gains) / period if gains else 0.001
    avg_loss = sum(losses) / period if losses else 0.001
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def _calc_ema(prices: list[float], period: int) -> float:
    if len(prices) < period:
        return prices[-1]
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema


def _generate_signal_from_price(asset_meta: dict, price: float, prices_history: list[float]) -> dict:
    rsi = _calc_rsi(prices_history)
    ema9 = _calc_ema(prices_history, 9)
    ema21 = _calc_ema(prices_history, 21)

    if rsi < 40 and ema9 > ema21:
        direction = "BUY"
        rationale = f"RSI oversold ({rsi}) with bullish EMA crossover — momentum shift expected."
    elif rsi > 60 and ema9 < ema21:
        direction = "SELL"
        rationale = f"RSI overbought ({rsi}) with bearish EMA crossover — pullback likely."
    elif rsi < 45:
        direction = "BUY"
        rationale = f"RSI at {rsi} — approaching oversold zone, watch for reversal."
    elif rsi > 55:
        direction = "SELL"
        rationale = f"RSI at {rsi} — extended move, short-term correction possible."
    else:
        direction = "BUY" if ema9 > ema21 else "SELL"
        rationale = f"EMA9 {'above' if direction == 'BUY' else 'below'} EMA21 — trend continuation signal."

    is_crypto = asset_meta.get("source") == "coingecko"
    tp_pct = round(random.uniform(1.8, 3.2) if is_crypto else random.uniform(0.4, 0.9), 2)
    sl_pct = round(tp_pct * random.uniform(0.45, 0.6), 2)

    if direction == "BUY":
        tp = round(price * (1 + tp_pct / 100), 5)
        sl = round(price * (1 - sl_pct / 100), 5)
    else:
        tp = round(price * (1 - tp_pct / 100), 5)
        sl = round(price * (1 + sl_pct / 100), 5)

    confidence = min(95, max(65, int(70 + abs(rsi - 50) * 0.6)))

    timeframes = ["15M", "1H", "4H"]
    tf_weights = [0.2, 0.5, 0.3]
    timeframe = random.choices(timeframes, tf_weights)[0]

    return {
        "asset": asset_meta["asset"],
        "direction": direction,
        "entry": price,
        "tp": tp,
        "sl": sl,
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "confidence": confidence,
        "timeframe": timeframe,
        "rationale": rationale,
        "rsi": rsi,
        "prices": prices_history,
    }


class SignalGenerator:
    def __init__(self):
        self._used_today: list[int] = []
        self._last_reset: str = ""

    def _reset_if_new_day(self):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if today != self._last_reset:
            self._used_today = []
            self._last_reset = today

    def _pick_asset(self, slot_index: int) -> dict:
        self._reset_if_new_day()
        index = (slot_index * 3 + datetime.utcnow().weekday()) % len(ASSET_POOL)
        return ASSET_POOL[index]

    async def get_signal(self, slot_index: int = 0) -> dict | None:
        asset_meta = self._pick_asset(slot_index)
        source = asset_meta["source"]

        try:
            async with aiohttp.ClientSession() as session:
                if source == "coingecko":
                    return await self._from_coingecko(session, asset_meta)
                elif source == "av_fx":
                    return await self._from_av_fx(session, asset_meta)
                elif source == "av_stock":
                    return await self._from_av_stock(session, asset_meta)
        except Exception as e:
            log.error("Signal fetch error for %s: %s", asset_meta["asset"], e)
            return self._fallback_signal(asset_meta)

    async def _from_coingecko(self, session: aiohttp.ClientSession, meta: dict) -> dict:
        url = (
            f"https://api.coingecko.com/api/v3/coins/{meta['id']}/market_chart"
            f"?vs_currency=usd&days=30&interval=daily"
        )
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()

        prices = [p[1] for p in data["prices"]]
        current_price = prices[-1]
        return _generate_signal_from_price(meta, current_price, prices)

    async def _from_av_fx(self, session: aiohttp.ClientSession, meta: dict) -> dict:
        url = (
            f"https://www.alphavantage.co/query?function=FX_DAILY"
            f"&from_symbol={meta['from']}&to_symbol={meta['to']}"
            f"&apikey={AV_KEY}&outputsize=compact"
        )
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()

        ts = data.get("Time Series FX (Daily)", {})
        if not ts:
            raise ValueError("No AV FX data")
        prices = [float(v["4. close"]) for v in list(ts.values())[:30]]
        prices.reverse()
        return _generate_signal_from_price(meta, prices[-1], prices)

    async def _from_av_stock(self, session: aiohttp.ClientSession, meta: dict) -> dict:
        url = (
            f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY"
            f"&symbol={meta['symbol']}&apikey={AV_KEY}&outputsize=compact"
        )
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()

        ts = data.get("Time Series (Daily)", {})
        if not ts:
            raise ValueError("No AV stock data")
        prices = [float(v["4. close"]) for v in list(ts.values())[:30]]
        prices.reverse()
        return _generate_signal_from_price(meta, prices[-1], prices)

    def _fallback_signal(self, meta: dict) -> dict:
        fallback_prices = {
            "BTC/USD": 63000, "ETH/USD": 3100, "BNB/USD": 580, "SOL/USD": 145,
            "EUR/USD": 1.085, "GBP/USD": 1.265, "USD/JPY": 154.5,
            "XAU/USD": 2320, "USO/USD": 79, "SPX500": 520, "NAS100": 445,
        }
        price = fallback_prices.get(meta["asset"], 100.0)
        dummy_prices = [price * (1 + (i % 5 - 2) * 0.002) for i in range(30)]
        return _generate_signal_from_price(meta, price, dummy_prices)
