import asyncio
import html
import logging
import os
import tempfile

from datetime import (
    datetime,
    timedelta,
    timezone,
)

import pandas as pd
import mplfinance as mpf

from dotenv import load_dotenv

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from generator import SignalGenerator


# =========================================================
# ENV
# =========================================================

load_dotenv()


BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "",
)

GROUP_ID = os.getenv(
    "GROUP_ID",
    "",
)

CHANNEL_ID = os.getenv(
    "CHANNEL_ID",
    "",
)


THEOPTION_LINK = os.getenv(
    "THEOPTION_LINK",
    "",
)

JFX_LINK = os.getenv(
    "JFX_LINK",
    "",
)


SEND_ON_STARTUP = (
    os.getenv(
        "SEND_ON_STARTUP",
        "false",
    )
    .lower()
    .strip()
    in (
        "1",
        "true",
        "yes",
        "on",
    )
)


# =========================================================
# TEXT
# =========================================================

DISCLAIMER_EN = (
    "Risk warning: Trading involves risk. "
    "Signals are provided for informational purposes only "
    "and are not investment advice."
)


DISCLAIMER_JP = (
    "リスク警告：取引にはリスクが伴います。"
    "シグナルは情報提供のみを目的としており、"
    "投資助言ではありません。"
)


OFFER_NOTE_EN = (
    "*Promotion subject to eligibility "
    "and campaign terms."
)


OFFER_NOTE_JP = (
    "※キャンペーンの適用には"
    "条件があります。"
)


# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(

    level=logging.INFO,

    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
)


logger = logging.getLogger(
    __name__
)


# =========================================================
# FORMATTERS
# =========================================================

def format_price(
    value: float,
) -> str:

    value = float(value)


    if value >= 1000:

        return (
            f"{value:,.2f}"
        )


    if value >= 100:

        return (
            f"{value:.2f}"
        )


    if value >= 10:

        return (
            f"{value:.3f}"
        )


    if value >= 1:

        return (
            f"{value:.4f}"
        )


    return (
        f"{value:.5f}"
    )


def emoji_for_direction(
    direction: str,
) -> str:

    return (
        "🟢"
        if direction.upper() == "BUY"
        else "🔴"
    )


def japanese_direction(
    direction: str,
) -> str:

    return (
        "買い"
        if direction.upper() == "BUY"
        else "売り"
    )


def format_update_time(
    value: str,
) -> str:

    try:

        dt = datetime.fromisoformat(
            value
        )

        if dt.tzinfo is None:

            dt = dt.replace(
                tzinfo=timezone.utc
            )

        dt = dt.astimezone(
            timezone.utc
        )

        return dt.strftime(
            "%Y-%m-%d %H:%M UTC"
        )

    except Exception:

        return str(value)


# =========================================================
# ENGLISH TELEGRAM MESSAGE
# =========================================================

def format_signal_en(
    signal: dict,
) -> str:

    side = emoji_for_direction(
        signal["direction"]
    )

    asset = html.escape(
        str(signal["asset"])
    )

    direction = html.escape(
        str(signal["direction"])
    )

    timeframe = html.escape(
        str(signal["timeframe"])
    )

    rationale = html.escape(
        str(signal["rationale_en"])
    )

    strength = html.escape(
        str(signal["strength_en"])
    )

    data_time = html.escape(
        format_update_time(
            signal["data_time"]
        )
    )


    return (

        f"{side} "
        f"<b>{asset} — {direction}</b>\n\n"

        f"Entry: "
        f"<b>{format_price(signal['entry'])}</b>\n"

        f"Take Profit: "
        f"<b>{format_price(signal['tp'])}</b> "
        f"(+{signal['tp_pct']:.2f}%)\n"

        f"Stop Loss: "
        f"<b>{format_price(signal['sl'])}</b> "
        f"(-{signal['sl_pct']:.2f}%)\n\n"

        f"Technical Score: "
        f"<b>{signal['strength_score']}/100</b> "
        f"({strength})\n"

        f"Timeframe: "
        f"<b>{timeframe}</b>\n"

        f"RSI(14): "
        f"<b>{signal['rsi']}</b>\n"

        f"Risk / Reward: "
        f"<b>1:{signal['risk_reward']:.2f}</b>\n\n"

        f"📊 <b>Technical Analysis</b>\n"

        f"{rationale}\n\n"

        f"🕐 Data: "
        f"{data_time}\n\n"

        f"🎁 <b>Choose a trading platform</b>\n"

        f"theoption — ¥10,000 registration campaign\n"

        f"JFX.com — ¥10,000 registration campaign\n\n"

        f"<i>{OFFER_NOTE_EN}</i>\n\n"

        f"<i>{DISCLAIMER_EN}</i>"
    )


# =========================================================
# JAPANESE TELEGRAM MESSAGE
# =========================================================

def format_signal_jp(
    signal: dict,
) -> str:

    side = emoji_for_direction(
        signal["direction"]
    )

    asset = html.escape(
        str(signal["asset"])
    )

    direction = (
        japanese_direction(
            signal["direction"]
        )
    )

    timeframe = html.escape(
        str(signal["timeframe"])
    )

    rationale = html.escape(
        str(signal["rationale_jp"])
    )

    strength = html.escape(
        str(signal["strength_jp"])
    )

    data_time = html.escape(
        format_update_time(
            signal["data_time"]
        )
    )


    return (

        f"{side} "
        f"<b>{asset} — {direction}</b>\n\n"

        f"エントリー: "
        f"<b>{format_price(signal['entry'])}</b>\n"

        f"利確目標: "
        f"<b>{format_price(signal['tp'])}</b> "
        f"(+{signal['tp_pct']:.2f}%)\n"

        f"損切り: "
        f"<b>{format_price(signal['sl'])}</b> "
        f"(-{signal['sl_pct']:.2f}%)\n\n"

        f"テクニカルスコア: "
        f"<b>{signal['strength_score']}/100</b> "
        f"（{strength}）\n"

        f"時間足: "
        f"<b>{timeframe}</b>\n"

        f"RSI(14): "
        f"<b>{signal['rsi']}</b>\n"

        f"リスクリワード: "
        f"<b>1:{signal['risk_reward']:.2f}</b>\n\n"

        f"📊 <b>テクニカル分析</b>\n"

        f"{rationale}\n\n"

        f"🕐 データ更新: "
        f"{data_time}\n\n"

        f"🎁 <b>取引プラットフォームを選択</b>\n"

        f"theoption — 登録キャンペーン10,000円\n"

        f"JFX.com — 登録キャンペーン10,000円\n\n"

        f"<i>{OFFER_NOTE_JP}</i>\n\n"

        f"<i>{DISCLAIMER_JP}</i>"
    )


# =========================================================
# BUTTONS
# =========================================================

def build_keyboard_en() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🎁 theoption — ¥10,000",
                url=THEOPTION_LINK,
            )
        ],

        [
            InlineKeyboardButton(
                "🎁 JFX.com — ¥10,000",
                url=JFX_LINK,
            )
        ],
    ])


def build_keyboard_jp() -> InlineKeyboardMarkup:

    return InlineKeyboardMarkup([

        [
            InlineKeyboardButton(
                "🎁 theoption — 10,000円特典",
                url=THEOPTION_LINK,
            )
        ],

        [
            InlineKeyboardButton(
                "🎁 JFX.com — 10,000円特典",
                url=JFX_LINK,
            )
        ],
    ])


# =========================================================
# CHART
# =========================================================

def build_chart(
    signal: dict,
) -> str:

    candles = signal.get(
        "candles",
        [],
    )


    if not candles:

        raise RuntimeError(
            "Signal contains no candles"
        )


    dataframe = pd.DataFrame(
        candles
    )


    dataframe["date"] = (
        pd.to_datetime(
            dataframe["date"],
            utc=True,
        )
    )


    # mplfinance works more reliably
    # with timezone-naive UTC timestamps.

    dataframe["date"] = (
        dataframe["date"]
        .dt.tz_convert(None)
    )


    dataframe = (
        dataframe
        .set_index("date")
    )


    dataframe = (
        dataframe.rename(
            columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
            }
        )
    )


    # Keep chart readable

    dataframe = (
        dataframe.tail(50)
    )


    entry_line = [
        signal["entry"]
    ] * len(dataframe)

    tp_line = [
        signal["tp"]
    ] * len(dataframe)

    sl_line = [
        signal["sl"]
    ] * len(dataframe)


    additional_plots = [

        mpf.make_addplot(
            entry_line,
            linestyle="--",
            width=1.0,
        ),

        mpf.make_addplot(
            tp_line,
            linestyle="--",
            width=1.0,
        ),

        mpf.make_addplot(
            sl_line,
            linestyle="--",
            width=1.0,
        ),
    ]


    temp_file = (
        tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".png",
        )
    )


    temp_path = (
        temp_file.name
    )


    temp_file.close()


    mpf.plot(

        dataframe,

        type="candle",

        style="charles",

        addplot=additional_plots,

        title=(
            f"{signal['asset']} — "
            f"{signal['direction']} — "
            f"{signal['timeframe']}"
        ),

        ylabel="Price",

        volume=False,

        figsize=(10, 6),

        tight_layout=True,

        savefig=dict(

            fname=temp_path,

            dpi=170,

            bbox_inches="tight",
        ),
    )


    return temp_path


# =========================================================
# TELEGRAM DESTINATIONS
# =========================================================

def parse_chat_id(
    value: str,
):

    value = value.strip()


    if not value:

        return None


    if (
        value.startswith("-")
        and value[1:].isdigit()
    ):

        return int(value)


    if value.isdigit():

        return int(value)


    return value


def get_destinations():

    destinations = []


    group = parse_chat_id(
        GROUP_ID
    )

    channel = parse_chat_id(
        CHANNEL_ID
    )


    if group is not None:

        destinations.append(
            group
        )


    if (
        channel is not None
        and channel not in destinations
    ):

        destinations.append(
            channel
        )


    if not destinations:

        raise RuntimeError(
            "GROUP_ID or CHANNEL_ID "
            "must be configured"
        )


    return destinations


# =========================================================
# SEND ONE LANGUAGE
# =========================================================

async def send_photo_message(
    bot: Bot,
    chat_id,
    chart_path: str,
    caption: str,
    keyboard: InlineKeyboardMarkup,
):

    with open(
        chart_path,
        "rb",
    ) as photo:

        await bot.send_photo(

            chat_id=chat_id,

            photo=photo,

            caption=caption,

            parse_mode="HTML",

            reply_markup=keyboard,
        )


# =========================================================
# POST SIGNAL
# =========================================================

async def post_signal(
    bot: Bot,
    generator: SignalGenerator,
    asset_index: int,
) -> bool:

    signal = await generator.get_signal(
        asset_index
    )


    if not signal:

        logger.warning(
            "No valid market signal available. "
            "Nothing will be posted."
        )

        return False


    chart_path = build_chart(
        signal
    )


    english_caption = (
        format_signal_en(
            signal
        )
    )

    japanese_caption = (
        format_signal_jp(
            signal
        )
    )


    english_keyboard = (
        build_keyboard_en()
    )

    japanese_keyboard = (
        build_keyboard_jp()
    )


    destinations = (
        get_destinations()
    )


    try:

        for chat_id in destinations:

            # -----------------------------
            # ENGLISH
            # -----------------------------

            try:

                await send_photo_message(

                    bot=bot,

                    chat_id=chat_id,

                    chart_path=chart_path,

                    caption=english_caption,

                    keyboard=english_keyboard,
                )


                logger.info(

                    "English %s signal "
                    "posted to %s",

                    signal["asset"],

                    chat_id,
                )


            except Exception as exc:

                logger.exception(

                    "English Telegram post failed "
                    "for %s to %s: %s",

                    signal["asset"],

                    chat_id,

                    exc,
                )


            # Tiny gap to keep ordering predictable

            await asyncio.sleep(
                0.75
            )


            # -----------------------------
            # JAPANESE
            # -----------------------------

            try:

                await send_photo_message(

                    bot=bot,

                    chat_id=chat_id,

                    chart_path=chart_path,

                    caption=japanese_caption,

                    keyboard=japanese_keyboard,
                )


                logger.info(

                    "Japanese %s signal "
                    "posted to %s",

                    signal["asset"],

                    chat_id,
                )


            except Exception as exc:

                logger.exception(

                    "Japanese Telegram post failed "
                    "for %s to %s: %s",

                    signal["asset"],

                    chat_id,

                    exc,
                )


        return True


    finally:

        try:

            os.remove(
                chart_path
            )

        except Exception:

            pass


# =========================================================
# HOURLY SCHEDULER
# =========================================================

def get_next_run() -> datetime:

    now = datetime.now(
        timezone.utc
    )


    # Always post on the next exact UTC hour

    return (

        now.replace(

            minute=0,

            second=0,

            microsecond=0,
        )

        + timedelta(
            hours=1
        )
    )


# =========================================================
# VALIDATION
# =========================================================

def validate_config():

    if not BOT_TOKEN:

        raise RuntimeError(
            "BOT_TOKEN is missing"
        )


    if not THEOPTION_LINK:

        raise RuntimeError(
            "THEOPTION_LINK is missing"
        )


    if not JFX_LINK:

        raise RuntimeError(
            "JFX_LINK is missing"
        )


    if not (
        THEOPTION_LINK.startswith("http://")
        or THEOPTION_LINK.startswith("https://")
    ):

        raise RuntimeError(
            "THEOPTION_LINK must be a valid URL"
        )


    if not (
        JFX_LINK.startswith("http://")
        or JFX_LINK.startswith("https://")
    ):

        raise RuntimeError(
            "JFX_LINK must be a valid URL"
        )


    get_destinations()


# =========================================================
# MAIN LOOP
# =========================================================

async def scheduler_loop():

    validate_config()


    destinations = (
        get_destinations()
    )


    logger.info(
        "Configured destinations: %s",
        destinations,
    )


    generator = (
        SignalGenerator()
    )


    asset_index = 0


    async with Bot(
        token=BOT_TOKEN
    ) as bot:


        # =================================================
        # OPTIONAL STARTUP TEST
        # =================================================

        if SEND_ON_STARTUP:

            logger.info(
                "SEND_ON_STARTUP=true. "
                "Sending startup signal."
            )


            try:

                success = await post_signal(

                    bot,

                    generator,

                    asset_index,
                )


                if success:

                    asset_index += 1


            except Exception as exc:

                logger.exception(
                    "Startup signal failed: %s",
                    exc,
                )


        # =================================================
        # HOURLY LOOP
        # =================================================

        while True:

            next_run = (
                get_next_run()
            )


            wait_seconds = max(

                1,

                (
                    next_run
                    - datetime.now(
                        timezone.utc
                    )
                ).total_seconds(),
            )


            logger.info(
                "Next signal: %s",
                next_run.isoformat(),
            )


            await asyncio.sleep(
                wait_seconds
            )


            try:

                success = (
                    await post_signal(

                        bot,

                        generator,

                        asset_index,
                    )
                )


                if success:

                    asset_index += 1


            except Exception as exc:

                logger.exception(
                    "Hourly signal failed: %s",
                    exc,
                )


            # Prevent an accidental instant second iteration

            await asyncio.sleep(
                2
            )


# =========================================================
# ENTRYPOINT
# =========================================================

async def main():

    await scheduler_loop()


if __name__ == "__main__":

    asyncio.run(
        main()
    )