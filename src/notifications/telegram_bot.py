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
            # g_id = settings.SYSTEM_ERROR_ALERTS_GROUP_CHATID
        elif channel == "error":
            g_id = settings.SYSTEM_ERROR_ALERTS_GROUP_CHATID

        await _send(g_id, message)
    except Exception as e:
        logger.error(f"Error sending alert: {e}")
        logger.error(traceback.format_exc())


async def send_alert_by_media(message, channel="transaction"):
    try:
        if channel == "transaction":
            g_id = settings.TRANSACTION_ALERTS_GROUP_CHATID
            # g_id = settings.SYSTEM_ERROR_ALERTS_GROUP_CHATID
        elif channel == "error":
            g_id = settings.SYSTEM_ERROR_ALERTS_GROUP_CHATID

        await _send_media_group(g_id, message)
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
    # await bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            if response.status != 200:
                logger.error(f"Failed to send message: {await response.text()}")


async def _send_media_group(chat_id, media_group):
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/sendMediaGroup"

    # Phân nhóm media_group thành các phần nhỏ, tối đa 10 mục mỗi nhóm
    max_items = 10
    for i in range(0, len(media_group), max_items):
        batch = media_group[i : i + max_items]
        payload = {"chat_id": chat_id, "media": batch}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    error_message = await response.text()
                    print(f"Failed to send media group: {error_message}")
                else:
                    print(
                        f"Media group sent successfully (batch {i // max_items + 1})!"
                    )


async def get_updates(start_date: int):
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/getUpdates"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            result = await response.json()
    updates = result["result"]
    messages = list(filter(lambda x: x["message"]["date"] >= start_date, updates))
    return sorted(messages, key=lambda x: x["message"]["date"], reverse=True)
