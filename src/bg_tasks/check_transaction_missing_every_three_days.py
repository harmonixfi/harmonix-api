import logging
from datetime import datetime, time, timedelta, timezone

import pendulum
import requests
import seqlog
from dateutil.relativedelta import FR, relativedelta
from sqlmodel import Session, select

from core.config import settings
from core.db import engine
from log import setup_logging_to_file
from models import (PositionStatus, PricePerShareHistory, Transaction,
                    UserPortfolio, Vault)
from models.pps_history import PricePerShareHistory
from models.vault_performance import VaultPerformance
from models.vaults import NetworkChain
from utils.calculate_price import calculate_avg_entry_price

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
START_BLOCK = 0
END_BLOCK = 99999999
OFFSET = 100
THREE_DAYS_AGO = 3 * 24 * 60 * 60

api_key = settings.ARBISCAN_API_KEY
url = settings.ARBISCAN_GET_TRANSACTIONS_URL

session = Session(engine)


def decode_transaction_input(transaction):
    transaction_amount = int(transaction["input"][10:74], 16)
    transaction_amount = transaction_amount / 1e6
    return transaction_amount


def get_transactions(vault_address, page):
    query_params = {
        "address": vault_address,
        "startblock": START_BLOCK,
        "endblock": END_BLOCK,
        "page": page,
        "offset": OFFSET,
        "sort": "desc",
        "apikey": api_key,
    }
    api_url = (
        f"{url}&{'&'.join(f'{key}={value}' for key, value in query_params.items())}"
    )
    response = requests.get(api_url)
    response_json = response.json()
    transactions = response_json["result"]
    return transactions


def check_missing_transactions():

    # query all active vaults
    vaults = session.exec(
        select(Vault)
        .where(Vault.is_active == True)
        .where(Vault.network_chain == NetworkChain.arbitrum_one)
    ).all()

    timestamp_three_days_ago = float(datetime.now().timestamp()) - THREE_DAYS_AGO
    flag = True

    for vault in vaults:
        page = 1

        while flag:
            transactions = get_transactions(vault.contract_address, page)
            if transactions == "Max rate limit reached":
                time.sleep(60)
                break
            if not transactions:
                break
            for transaction in transactions:
                transaction_timestamp = float(transaction["timeStamp"])
                if transaction_timestamp > timestamp_three_days_ago:
                    from_address = transaction["from"]

                    transaction_date = pendulum.from_timestamp(
                        int(transaction["timeStamp"]), tz=pendulum.UTC
                    )
                    transaction_date = datetime(
                        transaction_date.year,
                        transaction_date.month,
                        transaction_date.day,
                    )
                    # get price per share from range friday to friday
                    last_friday = transaction_date + relativedelta(weekday=FR(-1))
                    this_thursday = last_friday + timedelta(days=6)

                    history_pps = session.exec(
                        select(PricePerShareHistory)
                        .where(PricePerShareHistory.vault_id == vault.id)
                        .where(PricePerShareHistory.datetime >= last_friday)
                        .where(PricePerShareHistory.datetime <= this_thursday)
                        .order_by(PricePerShareHistory.datetime.desc())
                    ).first()

                    if history_pps is not None:
                        history_pps = history_pps[0].price_per_share
                    else:
                        history_pps = 1

                    user_portfolio = session.exec(
                        select(UserPortfolio)
                        .where(UserPortfolio.user_address == from_address)
                        .where(UserPortfolio.vault_id == vault.id)
                        .where(UserPortfolio.status == PositionStatus.ACTIVE)
                    ).first()

                    if (
                        transaction["functionName"]
                        == "deposit(uint256 visrDeposit, address from, address to)"
                    ):
                        transaction_hash = transaction["hash"]
                        existing_transaction = session.exec(
                            select(Transaction).where(
                                Transaction.txhash == transaction_hash
                            )
                        ).first()
                        if existing_transaction is None:
                            trx = Transaction(
                                txhash=transaction_hash,
                            )
                            session.add(trx)
                            value = decode_transaction_input(transaction)
                            if user_portfolio is None:
                                # Create new user_portfolio for this user address
                                user_portfolio = UserPortfolio(
                                    vault_id=vault.id,
                                    user_address=from_address,
                                    total_balance=value,
                                    init_deposit=value,
                                    entry_price=history_pps,
                                    pnl=0,
                                    status=PositionStatus.ACTIVE,
                                    trade_start_date=datetime.now(timezone.utc),
                                    total_shares=value / history_pps,
                                )
                                session.add(user_portfolio)
                                logger.info(
                                    f"User with address {from_address} added to user_portfolio table"
                                )
                            else:
                                # Update the user_portfolio
                                user_portfolio = user_portfolio[0]
                                user_portfolio.total_balance += value
                                user_portfolio.init_deposit += value
                                user_portfolio.entry_price = calculate_avg_entry_price(
                                    user_portfolio, history_pps, value
                                )
                                user_portfolio.total_shares += value / history_pps
                                session.add(user_portfolio)
                                logger.info(
                                    f"User with address {from_address} updated in user_portfolio table"
                                )
                        else:
                            logger.info(
                                f"Transaction with txhash {transaction_hash} already exists"
                            )
                else:
                    flag = False
                    break
            page += 1
            if not flag:
                break
    session.commit()


if __name__ == "__main__":
    setup_logging_to_file(
        app="check_transaction_missing_every_three_days", level=logging.INFO, logger=logger
    )
    
    check_missing_transactions()
