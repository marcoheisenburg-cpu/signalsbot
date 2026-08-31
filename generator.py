import os
import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import aiohttp


log = logging.getLogger(__name__)


# =========================================================
# CONFIG
# =========================================================

AV_KEY = os.getenv("ALPHA_VANTAGE_KEY", "")

AV_INTERVAL = os.getenv(
    "AV_INTERVAL",
    "60min"
)

ENABLE_AV_INTRADAY = (
    os.getenv("ENABLE_AV_INTRADAY", "true")
    .lower()
    .strip()
    in ("1", "true", "yes", "on")
)

SUPPORTED_AV_INTERVALS = {
    "1min",
    "5min",
    "15min",
    "30min",
    "60min",
}

if AV_INTERVAL not in SUPPORTED_AV_INTERVALS:
    AV_INTERVAL = "60min"


NEW_YORK = ZoneInfo("America/New_York")


# =========================================================
# ASSETS
# =========================================================
#
# IMPORTANT:
# GLD is NOT literally XAU/USD.
# SPY is NOT literally SPX500.
# QQQ is NOT literally NAS100.
#
# So we name the instruments honestly.
# =========================================================

ASSET_POOL = [

    # -------------------------
    # CRYPTO — 24/7
    # -------------------------

    {
        "asset": "BTC/USD",
        "source": "coingecko",
        "market": "crypto",
        "id": "bitcoin",
        "timeframe": "30M",
    },

    {
        "asset": "ETH/USD",
        "source": "coingecko",
        "market": "crypto",
        "id": "ethereum",
        "timeframe": "30M",
    },

    {
        "asset": "BNB/USD",
        "source": "coingecko",
        "market": "crypto",
        "id": "binancecoin",
        "timeframe": "30M",
    },

    {
        "asset": "SOL/USD",
        "source": "coingecko",
        "market": "crypto",
        "id": "solana",
        "timeframe": "30M",
    },

    # -------------------------
    # FOREX
    # -------------------------

    {
        "asset": "EUR/USD",
        "source": "av_fx",
        "market": "fx",
        "from": "EUR",
        "to": "USD",
        "timeframe": AV_INTERVAL.upper(),
    },

    {
        "asset": "GBP/USD",
        "source": "av_fx",
        "market": "fx",
        "from": "GBP",
        "to": "USD",
        "timeframe": AV_INTERVAL.upper(),
    },

    {
        "asset": "USD/JPY",
        "source": "av_fx",
        "market": "fx",
        "from": "USD",
        "to": "JPY",
        "timeframe": AV_INTERVAL.upper(),
    },

    # -------------------------
    # US MARKET PROXIES
    # -------------------------

    {
        "asset": "Gold ETF (GLD)",
        "source": "av_stock",
        "market": "us_stock",
        "symbol": "GLD",
        "timeframe": AV_INTERVAL.upper(),
    },

    {
        "asset": "Oil ETF (USO)",
        "source": "av_stock",
        "market": "us_stock",
        "symbol": "USO",
        "timeframe": AV_INTERVAL.upper(),
    },

    {
        "asset": "S&P 500 ETF (SPY)",
        "source": "av_stock",
        "market": "us_stock",
        "symbol": "SPY",
        "timeframe": AV_INTERVAL.upper(),
    },

    {
        "asset": "Nasdaq 100 ETF (QQQ)",
        "source": "av_stock",
        "market": "us_stock",
        "symbol": "QQQ",
        "timeframe": AV_INTERVAL.upper(),
    },
]


# =========================================================
# MARKET HOURS
# =========================================================

def _fx_market_open(now_utc: datetime) -> bool:
    """
    Approximate global FX market schedule using New York time.

    Opens Sunday ~17:00 ET
    Closes Friday ~17:00 ET
    """

    now_ny = now_utc.astimezone(NEW_YORK)

    weekday = now_ny.weekday()
    current_time = now_ny.time()

    # Saturday
    if weekday == 5:
        return False

    # Sunday before 17:00
    if weekday == 6:
        return current_time >= time(17, 0)

    # Friday after 17:00
    if weekday == 4:
        return current_time < time(17, 0)

    return True


def _us_stock_market_open(now_utc: datetime) -> bool:
    """
    Regular US equity session:
    09:30 - 16:00 New York time.

    Holiday detection is not included.
    """

    now_ny = now_utc.astimezone(NEW_YORK)

    if now_ny.weekday() >= 5:
        return False

    current_time = now_ny.time()

    return (
        time(9, 30)
        <= current_time
        < time(16, 0)
    )


def _asset_available(
    meta: dict,
    now_utc: datetime,
) -> bool:

    market = meta.get("market")

    if market == "crypto":
        return True

    if not ENABLE_AV_INTRADAY:
        return False

    if market == "fx":
        return _fx_market_open(now_utc)

    if market == "us_stock":
        return _us_stock_market_open(now_utc)

    return False


# =========================================================
# INDICATORS
# =========================================================

def _calc_rsi(
    prices: list[float],
    period: int = 14,
) -> float:

    if len(prices) < period + 1:
        raise ValueError(
            "Not enough prices to calculate RSI"
        )

    recent = prices[-(period + 1):]

    gains = []
    losses = []

    for i in range(1, len(recent)):

        diff = recent[i] - recent[i - 1]

        gains.append(
            max(diff, 0)
        )

        losses.append(
            max(-diff, 0)
        )

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0

    if avg_gain == 0:
        return 0.0

    rs = avg_gain / avg_loss

    rsi = 100 - (
        100 / (1 + rs)
    )

    return round(rsi, 2)


def _calc_ema(
    prices: list[float],
    period: int,
) -> float:

    if len(prices) < period:
        raise ValueError(
            f"Not enough prices for EMA{period}"
        )

    multiplier = 2 / (
        period + 1
    )

    ema = sum(
        prices[:period]
    ) / period

    for price in prices[period:]:

        ema = (
            price * multiplier
            + ema * (1 - multiplier)
        )

    return ema


def _calc_atr(
    candles: list[dict],
    period: int = 14,
) -> float:

    if len(candles) < period + 1:
        raise ValueError(
            "Not enough candles to calculate ATR"
        )

    recent = candles[
        -(period + 1):
    ]

    true_ranges = []

    for i in range(
        1,
        len(recent),
    ):

        current = recent[i]
        previous = recent[i - 1]

        high = float(
            current["high"]
        )

        low = float(
            current["low"]
        )

        previous_close = float(
            previous["close"]
        )

        true_range = max(

            high - low,

            abs(
                high
                - previous_close
            ),

            abs(
                low
                - previous_close
            ),
        )

        true_ranges.append(
            true_range
        )

    atr = sum(
        true_ranges
    ) / len(true_ranges)

    return atr


# =========================================================
# SIGNAL GENERATOR
# =========================================================

def _generate_signal(
    asset_meta: dict,
    candles: list[dict],
) -> dict:

    if len(candles) < 25:
        raise ValueError(
            "Not enough candles for signal analysis"
        )

    closes = [
        float(candle["close"])
        for candle in candles
    ]

    price = closes[-1]

    rsi = _calc_rsi(
        closes,
        14,
    )

    ema9 = _calc_ema(
        closes,
        9,
    )

    ema21 = _calc_ema(
        closes,
        21,
    )

    atr = _calc_atr(
        candles,
        14,
    )


    # =====================================================
    # MOMENTUM
    # =====================================================

    if len(closes) >= 4:

        previous_price = closes[-4]

    else:

        previous_price = closes[-2]


    momentum_pct = (
        (
            price
            - previous_price
        )
        / previous_price
    ) * 100


    # =====================================================
    # TECHNICAL COMPONENTS
    # =====================================================

    ema_component = (
        1
        if ema9 > ema21
        else -1
    )


    if rsi <= 45:

        rsi_component = 1

    elif rsi >= 55:

        rsi_component = -1

    else:

        rsi_component = 0


    if momentum_pct > 0:

        momentum_component = 1

    elif momentum_pct < 0:

        momentum_component = -1

    else:

        momentum_component = 0


    # =====================================================
    # WEIGHTED TECHNICAL SCORE
    #
    # This is NOT a probability.
    # =====================================================

    weighted_score = (

        ema_component * 2.0

        + rsi_component * 1.3

        + momentum_component * 1.2
    )

    max_score = 4.5


    if weighted_score >= 0:

        direction = "BUY"

    else:

        direction = "SELL"


    strength_score = round(

        50
        + (
            min(
                abs(weighted_score)
                / max_score,
                1,
            )
            * 45
        )
    )


    if strength_score >= 80:

        strength_en = "Strong"
        strength_jp = "強い"

    elif strength_score >= 65:

        strength_en = "Moderate"
        strength_jp = "中程度"

    else:

        strength_en = "Weak"
        strength_jp = "弱い"


    # =====================================================
    # ATR-BASED TAKE PROFIT / STOP LOSS
    #
    # No random percentages.
    # =====================================================

    market = asset_meta.get(
        "market"
    )


    if market == "crypto":

        stop_atr = 1.25
        target_atr = 2.0

    elif market == "fx":

        stop_atr = 1.0
        target_atr = 1.6

    else:

        stop_atr = 1.1
        target_atr = 1.8


    stop_distance = (
        atr * stop_atr
    )

    target_distance = (
        atr * target_atr
    )


    if direction == "BUY":

        tp = (
            price
            + target_distance
        )

        sl = (
            price
            - stop_distance
        )

    else:

        tp = (
            price
            - target_distance
        )

        sl = (
            price
            + stop_distance
        )


    tp_pct = (
        abs(tp - price)
        / price
        * 100
    )

    sl_pct = (
        abs(sl - price)
        / price
        * 100
    )


    risk_reward = (
        target_distance
        / stop_distance
    )


    # =====================================================
    # HUMAN-READABLE ANALYSIS
    # =====================================================

    if ema9 > ema21:

        ema_en = (
            "EMA9 is above EMA21, "
            "showing positive short-term trend pressure."
        )

        ema_jp = (
            "EMA9がEMA21を上回っており、"
            "短期的な上昇トレンドが確認されています。"
        )

    else:

        ema_en = (
            "EMA9 is below EMA21, "
            "showing negative short-term trend pressure."
        )

        ema_jp = (
            "EMA9がEMA21を下回っており、"
            "短期的な下落トレンドが確認されています。"
        )


    if rsi <= 35:

        rsi_en = (
            f"RSI is {rsi}, indicating "
            "strong oversold conditions."
        )

        rsi_jp = (
            f"RSIは{rsi}で、"
            "強い売られすぎ水準を示しています。"
        )

    elif rsi <= 45:

        rsi_en = (
            f"RSI is {rsi}, approaching "
            "oversold territory."
        )

        rsi_jp = (
            f"RSIは{rsi}で、"
            "売られすぎ水準に近づいています。"
        )

    elif rsi >= 65:

        rsi_en = (
            f"RSI is {rsi}, indicating "
            "strong overbought conditions."
        )

        rsi_jp = (
            f"RSIは{rsi}で、"
            "強い買われすぎ水準を示しています。"
        )

    elif rsi >= 55:

        rsi_en = (
            f"RSI is {rsi}, showing "
            "elevated buying pressure."
        )

        rsi_jp = (
            f"RSIは{rsi}で、"
            "買い圧力が高まっています。"
        )

    else:

        rsi_en = (
            f"RSI is neutral at {rsi}."
        )

        rsi_jp = (
            f"RSIは{rsi}で、"
            "中立圏にあります。"
        )


    if momentum_pct > 0:

        momentum_en = (
            f"Recent momentum is +"
            f"{momentum_pct:.2f}%."
        )

        momentum_jp = (
            f"直近のモメンタムは"
            f"+{momentum_pct:.2f}%です。"
        )

    elif momentum_pct < 0:

        momentum_en = (
            f"Recent momentum is "
            f"{momentum_pct:.2f}%."
        )

        momentum_jp = (
            f"直近のモメンタムは"
            f"{momentum_pct:.2f}%です。"
        )

    else:

        momentum_en = (
            "Recent momentum is flat."
        )

        momentum_jp = (
            "直近のモメンタムは横ばいです。"
        )


    rationale_en = (
        f"{ema_en} "
        f"{rsi_en} "
        f"{momentum_en}"
    )

    rationale_jp = (
        f"{ema_jp}"
        f"{rsi_jp}"
        f"{momentum_jp}"
    )


    # =====================================================
    # RETURN
    # =====================================================

    return {

        "asset":
            asset_meta["asset"],

        "market":
            market,

        "source":
            asset_meta["source"],

        "direction":
            direction,

        "entry":
            round(price, 8),

        "tp":
            round(tp, 8),

        "sl":
            round(sl, 8),

        "tp_pct":
            round(tp_pct, 2),

        "sl_pct":
            round(sl_pct, 2),

        "risk_reward":
            round(risk_reward, 2),

        "strength_score":
            strength_score,

        "strength_en":
            strength_en,

        "strength_jp":
            strength_jp,

        "timeframe":
            asset_meta["timeframe"],

        "rsi":
            rsi,

        "ema9":
            round(ema9, 8),

        "ema21":
            round(ema21, 8),

        "atr":
            round(atr, 8),

        "momentum_pct":
            round(momentum_pct, 2),

        "rationale_en":
            rationale_en,

        "rationale_jp":
            rationale_jp,

        "prices":
            closes[-60:],

        "candles":
            candles[-60:],

        "data_time":
            candles[-1]["date"],
    }


# =========================================================
# ALPHA VANTAGE HELPERS
# =========================================================

def _check_alpha_vantage_response(
    data: dict,
):

    for key in (
        "Error Message",
        "Information",
        "Note",
    ):

        if key in data:

            raise RuntimeError(
                str(data[key])
            )


def _av_timezone(
    data: dict,
):

    meta = data.get(
        "Meta Data",
        {},
    )

    timezone_name = ""

    for key, value in meta.items():

        if "Time Zone" in key:

            timezone_name = str(
                value
            )

            break


    normalized = (
        timezone_name
        .lower()
        .strip()
    )


    if (
        "eastern" in normalized
        or normalized == "us/eastern"
        or normalized
        == "america/new_york"
    ):

        return NEW_YORK


    return timezone.utc


def _convert_av_timestamp(
    value: str,
    source_timezone,
) -> str:

    parsed = datetime.strptime(
        value,
        "%Y-%m-%d %H:%M:%S",
    )

    parsed = parsed.replace(
        tzinfo=source_timezone
    )

    parsed_utc = parsed.astimezone(
        timezone.utc
    )

    return parsed_utc.isoformat()


# =========================================================
# SIGNAL GENERATOR CLASS
# =========================================================

class SignalGenerator:

    def __init__(self):

        self.asset_count = len(
            ASSET_POOL
        )


    def _ordered_assets(
        self,
        slot_index: int,
    ) -> list[dict]:

        """
        Rotates the starting asset every hour.

        If the chosen asset isn't available or its API fails,
        the bot automatically tries the next eligible asset.
        """

        start = (
            slot_index
            % self.asset_count
        )

        return (

            ASSET_POOL[start:]

            + ASSET_POOL[:start]
        )


    async def get_signal(
        self,
        slot_index: int = 0,
    ) -> dict | None:

        now_utc = datetime.now(
            timezone.utc
        )

        candidates = (
            self._ordered_assets(
                slot_index
            )
        )


        async with aiohttp.ClientSession() as session:

            for asset_meta in candidates:

                if not _asset_available(
                    asset_meta,
                    now_utc,
                ):

                    continue


                try:

                    source = asset_meta[
                        "source"
                    ]


                    if source == "coingecko":

                        return await self._from_coingecko(
                            session,
                            asset_meta,
                        )


                    if source == "av_fx":

                        return await self._from_av_fx(
                            session,
                            asset_meta,
                        )


                    if source == "av_stock":

                        return await self._from_av_stock(
                            session,
                            asset_meta,
                        )


                except Exception as exc:

                    log.warning(
                        "Unable to generate signal for %s: %s",
                        asset_meta["asset"],
                        exc,
                    )

                    continue


        log.error(
            "No eligible asset returned usable market data"
        )

        return None


    # =====================================================
    # COINGECKO
    # =====================================================

    async def _from_coingecko(
        self,
        session: aiohttp.ClientSession,
        meta: dict,
    ) -> dict:

        url = (
            "https://api.coingecko.com/api/v3/"
            f"coins/{meta['id']}/ohlc"
            "?vs_currency=usd"
            "&days=1"
        )


        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(
                total=15
            ),
        ) as response:

            if response.status != 200:

                raise RuntimeError(
                    f"CoinGecko HTTP "
                    f"{response.status}"
                )

            data = await response.json()


        if (
            not isinstance(data, list)
            or len(data) < 25
        ):

            raise ValueError(
                "Insufficient CoinGecko OHLC data"
            )


        candles = []


        for row in data:

            if len(row) < 5:
                continue

            ts, o, h, l, c = row


            timestamp = datetime.fromtimestamp(
                ts / 1000,
                tz=timezone.utc,
            )


            candles.append({

                "date":
                    timestamp.isoformat(),

                "open":
                    float(o),

                "high":
                    float(h),

                "low":
                    float(l),

                "close":
                    float(c),
            })


        return _generate_signal(
            meta,
            candles,
        )


    # =====================================================
    # ALPHA VANTAGE FX INTRADAY
    # =====================================================

    async def _from_av_fx(
        self,
        session: aiohttp.ClientSession,
        meta: dict,
    ) -> dict:

        if not AV_KEY:

            raise RuntimeError(
                "ALPHA_VANTAGE_KEY is missing"
            )


        url = (
            "https://www.alphavantage.co/query"
            "?function=FX_INTRADAY"
            f"&from_symbol={meta['from']}"
            f"&to_symbol={meta['to']}"
            f"&interval={AV_INTERVAL}"
            "&outputsize=compact"
            f"&apikey={AV_KEY}"
        )


        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(
                total=15
            ),
        ) as response:

            if response.status != 200:

                raise RuntimeError(
                    f"Alpha Vantage HTTP "
                    f"{response.status}"
                )

            data = await response.json()


        _check_alpha_vantage_response(
            data
        )


        series_key = (
            f"Time Series FX "
            f"({AV_INTERVAL})"
        )


        series = data.get(
            series_key,
            {},
        )


        if not series:

            raise ValueError(
                f"No Alpha Vantage FX data "
                f"for {meta['asset']}"
            )


        source_timezone = (
            _av_timezone(data)
        )


        rows = list(
            series.items()
        )[:80]


        rows.reverse()


        candles = []


        for timestamp, values in rows:

            candles.append({

                "date":
                    _convert_av_timestamp(
                        timestamp,
                        source_timezone,
                    ),

                "open":
                    float(
                        values["1. open"]
                    ),

                "high":
                    float(
                        values["2. high"]
                    ),

                "low":
                    float(
                        values["3. low"]
                    ),

                "close":
                    float(
                        values["4. close"]
                    ),
            })


        return _generate_signal(
            meta,
            candles,
        )


    # =====================================================
    # ALPHA VANTAGE STOCK / ETF INTRADAY
    # =====================================================

    async def _from_av_stock(
        self,
        session: aiohttp.ClientSession,
        meta: dict,
    ) -> dict:

        if not AV_KEY:

            raise RuntimeError(
                "ALPHA_VANTAGE_KEY is missing"
            )


        url = (
            "https://www.alphavantage.co/query"
            "?function=TIME_SERIES_INTRADAY"
            f"&symbol={meta['symbol']}"
            f"&interval={AV_INTERVAL}"
            "&outputsize=compact"
            "&adjusted=true"
            "&extended_hours=false"
            f"&apikey={AV_KEY}"
        )


        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(
                total=15
            ),
        ) as response:

            if response.status != 200:

                raise RuntimeError(
                    f"Alpha Vantage HTTP "
                    f"{response.status}"
                )

            data = await response.json()


        _check_alpha_vantage_response(
            data
        )


        series_key = (
            f"Time Series "
            f"({AV_INTERVAL})"
        )


        series = data.get(
            series_key,
            {},
        )


        if not series:

            raise ValueError(
                f"No Alpha Vantage stock data "
                f"for {meta['asset']}"
            )


        source_timezone = (
            _av_timezone(data)
        )


        rows = list(
            series.items()
        )[:80]


        rows.reverse()


        candles = []


        for timestamp, values in rows:

            candles.append({

                "date":
                    _convert_av_timestamp(
                        timestamp,
                        source_timezone,
                    ),

                "open":
                    float(
                        values["1. open"]
                    ),

                "high":
                    float(
                        values["2. high"]
                    ),

                "low":
                    float(
                        values["3. low"]
                    ),

                "close":
                    float(
                        values["4. close"]
                    ),
            })


        return _generate_signal(
            meta,
            candles,
        )