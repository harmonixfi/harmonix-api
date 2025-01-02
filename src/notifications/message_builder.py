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
    fields: List[Tuple[str, str, str, str, str]],
    pool_amounts: dict = None,
    reports_pendle: List[dict] = None,
) -> str:

    # Start the message
    message = "<pre>\n"
    message += f"Initiated Withdrawal Requests:\n"
    # Track vault totals for summary
    vault_totals = {}
    # Add transaction details
    for field in fields:
        (vault_address, amount, vault_name) = field
        # Accumulate totals for each vault
        try:
            amount_float = float(amount)
            if vault_address in vault_totals:
                vault_totals[vault_address]["total"] += amount_float
            else:
                vault_totals[vault_address] = {
                    "total": amount_float,
                    "vault_name": vault_name,
                }

        except ValueError:
            pass
    # Add summary section
    for vault_address, vault_data in vault_totals.items():
        total_amount = vault_data["total"]
        vault_name = vault_data["vault_name"]
        message += "======================\n"
        message += f"Vault: {vault_name}\n"
        message += f"Vault address: {vault_address}\n"
        message += f"Total need to withdraw : {total_amount:.4f}\n"
        if pool_amounts and vault_address.lower() in pool_amounts:
            message += (
                f"Withdrawal pool amount: {pool_amounts[vault_address.lower()]:.4f}\n"
            )

    message += "</pre>"

    message = "<pre>\n"
    for report in reports_pendle:
        # Start the message
        message += "======================\n"

        # Add summary section
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
