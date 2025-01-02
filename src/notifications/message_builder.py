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
    # Add transaction details
    for field in fields:
        tx_hash, vault_address, date, amount, age, vault_name = field
        message += "----------------------\n"
        message += f"tx_hash: {tx_hash}\n"
        message += f"vault: {vault_name}\n"
        message += f"vault_address: {vault_address}\n"
        message += f"date: {date}\n"
        message += f"amount: {amount}\n"

        message += f"age: {age}\n"

        # Accumulate totals for each vault
        try:
            amount_float = float(amount)
            vault_totals[vault_address] = {
                "total": vault_totals.get(vault_address, {}).get("total", 0)
                + amount_float
            }

        except ValueError:
            pass

    # Add summary section
    message += "\nSummary:\n"
    message += "-------\n"
    for vault_address, total_amount in vault_totals.items():
        message += f"Vault address: {vault_address}\n"
        message += f"Total need to withdraw : {total_amount['total']:.4f}\n"
        if pool_amounts and vault_address.lower() in pool_amounts:
            message += (
                f"Withdrawal pool amount: {pool_amounts[vault_address.lower()]:.4f}\n"
            )
        message += "-------\n"

    message += "</pre>"
    return message


def build_transaction_message_pendle_vault(
    fields: List[Tuple[str, str, str, str, str]], report: dict = None
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
        tx_hash, vault_address, date, age, pt_amount, sc_amount, shares = field
        message += "----------------------\n"
        message += f"tx_hash: {tx_hash}\n"
        message += f"vault_address: {vault_address}\n"
        message += f"date: {date}\n"
        message += f"pt_amount: {pt_amount}\n"
        message += f"sc_amount: {sc_amount}\n"
        message += f"shares: {shares}\n"
        message += f"age: {age}\n"

    # Add summary section
    message += "\nSummary:\n"
    message += "-------\n"
    message += f"Vault: {report['vault']}\n"
    message += f"Vault address: {report['vault_address']}\n"
    message += f"Total SC Withdrawn: {report['total_sc_withdrawn']}\n"
    message += f"Total PT Withdrawn: {report['total_pt_withdrawn']}\n"
    message += f"Total Shares Withdrawn: {report['total_shares_withdrawn']}\n"
    message += f"Withdraw Pool SC Amount: {report['sc_withdraw_pool_amount']}\n"
    message += f"Withdraw Pool PT Amount: {report['pt_withdraw_pool_amount']}\n"
    message += "-------\n"
    message += f"Total SC Needed to Withdraw: {report['total_sc_amount_needed']}\n"
    message += f"Total PT Needed to Withdraw: {report['total_pt_amount_needed']}\n"

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


def get_current_time():
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
