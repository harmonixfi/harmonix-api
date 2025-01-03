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

        await _send_v2(g_id, message)
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


async def _send_v2(chat_id, msg, parse_mode="HTML"):
    """
    Send message via Telegram API, automatically split if message is too long
    Args:
        chat_id: Chat ID to send message to
        msg: Message content
        parse_mode: "HTML" or "MarkdownV2"
    """
    max_length = 4000  # Safe limit for each message
    base_url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/sendMessage"

    # If message is short enough, send it normally
    if len(msg) <= max_length:
        payload = {"chat_id": chat_id, "text": msg, "parse_mode": parse_mode}
        async with aiohttp.ClientSession() as session:
            async with session.post(base_url, json=payload) as response:
                if response.status != 200:
                    logger.error(f"Failed to send message: {await response.text()}")
        return

    # If message is too long, split and send in parts
    messages = []
    while msg:
        if len(msg) > max_length:
            # Find the last complete transaction before max_length
            transaction_marker = "----------------------"
            split_index = msg[:max_length].rfind(transaction_marker)

            if split_index == -1:
                # If no transaction marker found, try to split at newline
                split_index = msg[:max_length].rfind("\n\n")
                if split_index == -1:
                    split_index = max_length
            else:
                # Move split point to before the transaction marker
                split_index = msg[:split_index].rstrip().rfind("\n") + 1

            # Handle HTML tags properly
            if parse_mode == "HTML":
                current_msg = msg[:split_index]
                if current_msg.count("<pre>") > current_msg.count("</pre>"):
                    current_msg += "</pre>"
                    msg = "<pre>" + msg[split_index:].lstrip()
                else:
                    msg = msg[split_index:].lstrip()
            else:
                current_msg = msg[:split_index]
                msg = msg[split_index:].lstrip()

            # Add continuation indicator
            if parse_mode == "MarkdownV2":
                current_msg += "\n\n_(Continued in next message...)_"
            else:
                current_msg += "\n\n<i>(Continued in next message...)</i>"
        else:
            current_msg = msg
            msg = ""

        messages.append(current_msg)

    # Send each part
    async with aiohttp.ClientSession() as session:
        for i, message_part in enumerate(messages, 1):
            # Add continuation indicator from previous message
            if i > 1:
                if parse_mode == "MarkdownV2":
                    message_part = (
                        f"_(Continued from previous message...)_\n\n{message_part}"
                    )
                else:
                    message_part = (
                        f"<i>(Continued from previous message...)</i>\n\n{message_part}"
                    )

            payload = {
                "chat_id": chat_id,
                "text": message_part,
                "parse_mode": parse_mode,
            }

            async with session.post(base_url, json=payload) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to send message part {i}: {error_text}")


async def get_updates(start_date: int):
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_TOKEN}/getUpdates"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            result = await response.json()
    updates = result["result"]
    messages = list(filter(lambda x: x["message"]["date"] >= start_date, updates))
    return sorted(messages, key=lambda x: x["message"]["date"], reverse=True)
