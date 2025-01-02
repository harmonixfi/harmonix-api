"""
implement a method to build a message for the deposit/withdraw event and send it to the telegram channel

1. Create a new method called `build_message` that takes in the parameters as array like:
(field_name, field_value). Here is example:
[['Event', ''Deposit''], ['Value', '100'], ['Shares', '200'], ['From', '0x1234']]
then render table using rich library like:

| Event | Deposit |
| Value | 100 |
| Shares | 200 |
| From | 0x1234 |

"""

from datetime import datetime, timezone
import html
import io
from typing import List, Optional, Tuple
from rich.table import Table
from rich.console import Console
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


def build_message(
    fields: List[Tuple[str, str]],
    user_position_fields: Optional[List[Tuple[str, str]]] = None,
) -> str:
    # Start the message with the main section title
    message = "<b>Main Section</b>\n<pre>\n"

    # Add main section table header
    message += "| Name               | Value               |\n"
    message += "|--------------------|---------------------|\n"

    # Add rows for the main section
    for field in fields:
        message += f"| {field[0]:<18} | {field[1]:<19} |\n"

    # Close the main section table
    message += "</pre>\n"

    # Check if user_position_fields is provided
    if user_position_fields:
        # Start the User position section with a title
        message += "<b>User Position</b>\n<pre>\n"

        # Add User position table header
        message += "| Name               | Value               |\n"
        message += "|--------------------|---------------------|\n"

        # Add rows for the User position section
        for field in user_position_fields:
            message += f"| {field[0]:<18} | {field[1]:<19} |\n"

        # Close the User position section
        message += "</pre>"

    return message


def build_error_message(
    error: Exception, traceback_details: str, strategy_name: str = None
) -> str:
    error_message = "Strategy: " + strategy_name if strategy_name else "Error"
    error_message += "\n" + str(error)

    # Normalize the traceback details to escape any unsupported HTML characters
    normalized_traceback = html.escape(traceback_details)

    # Format the message using HTML
    message = f"<b>Error:</b> {error_message}\n"
    message += "<pre>\n"
    message += normalized_traceback
    message += "\n</pre>"

    return message


def build_transaction_message(
    fields: List[Tuple[str, str, str, str, str]], pool_amounts: dict = None
) -> str:
    total_requests = len(fields)

    # Start the message
    message = "<pre>\n"
    message += f"Initiated Withdrawal Requests:\n"
    message += f"Total request: {total_requests}\n\n"
    message += f"Transactions:\n"

    # Track vault totals for summary
    vault_totals = {}
    has_pt_amount = False
    # Add transaction details
    for field in fields:
        tx_hash, vault_address, date, amount, age, pt_amount = field
        message += "----------------------\n"
        message += f"tx_hash: {tx_hash}\n"
        message += f"vault_address: {vault_address}\n"
        message += f"date: {date}\n"
        message += f"amount: {amount}\n"
        if pt_amount:
            message += f"pt_amount: {pt_amount}\n"
            has_pt_amount = True

        message += f"age: {age}\n"

        # Accumulate totals for each vault
        try:
            amount_float = float(amount)
            pt_amount_float = float(0.0)

            pt_amount_float += float(pt_amount if pt_amount else 0)
            vault_totals[vault_address] = {
                "total": vault_totals.get(vault_address, {}).get("total", 0)
                + amount_float,
                **({"pt_amount": pt_amount_float} if has_pt_amount else {}),
            }

        except ValueError:
            pass

    # Add summary section
    message += "\nSummary:\n"
    message += "-------\n"
    for vault_address, total_amount in vault_totals.items():
        message += f"Vault address: {vault_address}\n"
        message += "Pending withdrawals:\n"
        message += f"  USDC Amount: {total_amount['total']:.4f}\n"
        if has_pt_amount:
            message += f"  PT Amount: {total_amount['pt_amount']:.4f}\n"

        if pool_amounts and vault_address.lower() in pool_amounts:
            message += (
                f"Withdrawal pool amount: {pool_amounts[vault_address.lower()]:.4f}\n"
            )
        message += "-------\n"

    message += "</pre>"
    return message


def send_telegram_alert(alert_details):
    # Format message
    message = (
        f"🚨 *SYSTEM ALERT: Server Down* 🚨\n\n"
        f"📄 *Details:*\n_{alert_details}_\n\n"
        f"⚠️ *Status:* _Urgent_\n\n"
        f"⏰ *Time:* `{get_current_time()}`\n\n"
        f"🔔 _Immediate attention required to bring the server back online._"
    )
    return message


def build_transaction_page(
    fields: List[Tuple[str, str, str, str, str, str]], page: int, page_size: int = 5
) -> (str, InlineKeyboardMarkup):
    """
    Build a transaction message for the given page with inline keyboard pagination.
    """
    total_requests = len(fields)
    total_pages = (len(fields) + page_size - 1) // page_size  # Calculate total pages

    # Get transactions for the current page
    start = page * page_size
    end = start + page_size
    transactions = fields[start:end]

    # Start the message
    message = [
        f"<b>Page {page + 1}/{total_pages}</b>",
        f"Initiated Withdrawal Requests:",
        f"Total requests: {total_requests}",
        "",
        "Transactions:",
    ]

    # Add transaction details
    for tx_hash, vault_address, date, amount, age, pt_amount in transactions:
        transaction_details = [
            "----------------------",
            f"tx_hash: {tx_hash}",
            f"vault_address: {vault_address}",
            f"date: {date}",
            f"amount: {amount}",
            f"age: {age}",
        ]
        if pt_amount:
            transaction_details.append(f"pt_amount: {pt_amount}")
        message.extend(transaction_details)

    # Inline keyboard buttons
    buttons = []
    if page > 0:
        buttons.append(
            InlineKeyboardButton("⬅️ Previous", callback_data=f"page_{page - 1}")
        )
    if page < total_pages - 1:
        buttons.append(InlineKeyboardButton("➡️ Next", callback_data=f"page_{page + 1}"))

    keyboard = InlineKeyboardMarkup([buttons] if buttons else [])
    return "\n".join(message), keyboard


def get_current_time():
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
