import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telegram import Bot

from generator import SignalGenerator

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
GROUP_ID = os.getenv("GROUP_ID", "")
AFFILIATE_LINK = os.getenv("AFFILIATE_LINK", "")
SIGNALS_PER_DAY = int(os.getenv("SIGNALS_PER_DAY", "5"))

POST_HOURS = [7, 9, 12, 15, 18]  # UTC
CTA_TEXT = "Open your T4Trade account here"
DISCLAIMER = (
    "Risk warning: Trading involves risk. This content is for informational "
    "purposes only and is not investment advice."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


def format_price(v: float) -> str:
    if v >= 1000:
        return f"{v:,.2f}"
    if v >= 100:
        return f"{v:.2f}"
    if v >= 1:
        return f"{v:.4f}"
    return f"{v:.5f}"


def emoji_for_direction(direction: str) -> str:
    return "🟢" if direction == "BUY" else "🔴"


def format_signal(signal: dict, affiliate_link: str) -> str:
    side = emoji_for_direction(signal["direction"])
    return (
        f"{side} <b>{signal['asset']} — {signal['direction']}</b>\n"
        f"Entry: <b>{format_price(signal['entry'])}</b>\n"
        f"Take Profit: <b>{format_price(signal['tp'])}</b> ({signal['tp_pct']}%)\n"
        f"Stop Loss: <b>{format_price(signal['sl'])}</b> ({signal['sl_pct']}%)\n"
        f"Confidence: <b>{signal['confidence']}%</b>\n"
        f"Timeframe: <b>{signal['timeframe']}</b>\n"
        f"RSI(14): <b>{signal['rsi']}</b>\n"
        f"Reason: {signal['rationale']}\n\n"
        f"👉 <a href=\"{affiliate_link}\">{CTA_TEXT}</a>\n\n"
        f"<i>{DISCLAIMER}</i>"
    )


async def post_signal(bot: Bot, generator: SignalGenerator, asset_index: int):
    signal = await generator.get_signal(asset_index)
    if not signal:
        raise RuntimeError("No signal returned")

    text = format_signal(signal, AFFILIATE_LINK)
    await bot.send_message(
        chat_id=GROUP_ID,
        text=text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    logger.info("Posted signal for %s", signal["asset"])


def get_next_run() -> datetime:
    now = datetime.now(timezone.utc)
    today_runs = []

    for hour in POST_HOURS[:SIGNALS_PER_DAY]:
        run = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if run > now:
            today_runs.append(run)

    if today_runs:
        return min(today_runs)

    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(hour=POST_HOURS[0], minute=0, second=0, microsecond=0)


async def scheduler_loop():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is missing")
    if not GROUP_ID:
        raise RuntimeError("GROUP_ID is missing")
    if not AFFILIATE_LINK:
        raise RuntimeError("AFFILIATE_LINK is missing")
    if not os.getenv("ALPHA_VANTAGE_KEY"):
        raise RuntimeError("ALPHA_VANTAGE_KEY is missing")

    bot = Bot(token=BOT_TOKEN)
    generator = SignalGenerator()
    asset_index = 0

    # Send one signal immediately when the bot starts
    try:
        await post_signal(bot, generator, asset_index)
        logger.info("Startup test signal sent successfully")
        asset_index += 1
    except Exception as e:
        logger.exception("Failed to send startup signal: %s", e)

    while True:
        next_run = get_next_run()
        wait_seconds = max(1, int((next_run - datetime.now(timezone.utc)).total_seconds()))
        logger.info("Next post at %s", next_run.isoformat())
        await asyncio.sleep(wait_seconds)

        try:
            await post_signal(bot, generator, asset_index)
            asset_index += 1
        except Exception as e:
            logger.exception("Failed to post signal: %s", e)

        await asyncio.sleep(2)


async def main():
    await scheduler_loop()


if __name__ == "__main__":
    asyncio.run(main())
