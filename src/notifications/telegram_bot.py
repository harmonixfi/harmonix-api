import logging
import traceback
import aiohttp
from telegram import Bot

from core.config import settings

logger = logging.getLogger(__name__)


async def send_alert(message, channel="transaction"):
    try:
        if channel == "transaction":
            g_id = settings.TRANSACTION_ALERTS_GROUP_CHATID
        elif channel == "error":
            g_id = settings.SYSTEM_ERROR_ALERTS_GROUP_CHATID

        await _send(g_id, message)
    except Exception as e:
        logger.error(f"Error sending alert: {e}")
        logger.error(traceback.format_exc())


async def send_photo(chat_id, msg, file_name, file_path):
    files = {"photo": (file_name, open(file_path, "rb"), "image/jpeg")}
    url = (
        f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/sendPhoto"
        f"?chat_id={chat_id}&parse_mode=Markdown&text={msg}"
    )
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=files) as response:
            print(await response.text())


async def _send(chat_id, msg):
    bot = Bot(token=settings.TELEGRAM_TOKEN)
    await bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")


async def get_updates(start_date: int):
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/getUpdates"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            result = await response.json()
    updates = result["result"]
    messages = list(filter(lambda x: x["message"]["date"] >= start_date, updates))
    return sorted(messages, key=lambda x: x["message"]["date"], reverse=True)
