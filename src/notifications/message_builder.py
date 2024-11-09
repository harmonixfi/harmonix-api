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


def build_transaction_message(fields: List[Tuple[str, str]]) -> str:
    # Start with the HTML preformatted block
    total_requests = len(fields)

    # Start the message with the header and total request count
    message = "<pre>\n"
    message += f"Initiated  Withdrawal Requests:\n\n"
    message += f"Total request: {total_requests}\n"
    message += f"Transactions:\n"

    # Add table header with new columns
    message += "| tx_hash                                                            | date       | amount  | age    |\n"
    message += "|--------------------------------------------------------------------|------------|---------|--------|\n"

    # Add table rows
    for field in fields:
        message += (
            f"| {field[0]:<61} | {field[1]:<10} | {field[2]:<7} | {field[3]:<6} |\n"
        )

    # Close the HTML preformatted block
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
