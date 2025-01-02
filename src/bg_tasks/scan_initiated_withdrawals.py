import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Optional, Tuple
import pandas as pd
from sqlalchemy import text
from sqlmodel import Session, col, select
from bg_tasks.utils import (
    get_pending_initiated_withdrawals_query,
    get_pending_initiated_withdrawals_query_pendle_vault,
    get_user_withdrawals,
)
from core import constants
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.vaults import Vault
from notifications import telegram_bot
from notifications.message_builder import build_transaction_message
import schemas
from services.market_data import get_price
from services.vault_contract_service import VaultContractService
from web3 import Web3

from utils.extension_utils import convert_timedelta_to_time

session = Session(engine)


# # Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scan_initiated_withdrawals")
logger.setLevel(logging.INFO)


class InitiatedWithdrawalWatcherJob:
    def __init__(self, session: Session):
        self.session = session

        utc_now = datetime.now(timezone.utc)
        self.start_date = utc_now - timedelta(days=3 * 30)
        self.end_date = utc_now
        self.start_date_timestamp = int(self.start_date.timestamp())
        self.end_date_timestamp = int(self.end_date.timestamp())

    def _get_non_pendle_active_vaults(self) -> List[Vault]:
        result = self.session.exec(
            select(Vault)
            .where(Vault.is_active)
            .where(Vault.strategy_name != constants.PENDLE_HEDGING_STRATEGY)
        ).all()
        return result

    def _get_pendle_active_vaults(self) -> List[Vault]:
        result = self.session.exec(
            select(Vault)
            .where(Vault.is_active)
            .where(Vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY)
        ).all()
        return result

    def get_withdrawals_for_current_day(
        self, vaults: List[Vault]
    ) -> Tuple[List[schemas.OnchainTransactionHistory], dict[str, float]]:
        try:
            service = VaultContractService()
            pool_amounts: dict[str, float] = {}

            # Filter eligible vaults
            eligible_slugs = {
                constants.HYPE_DELTA_NEUTRAL_SLUG,
                constants.KELPDAO_VAULT_ARBITRUM_SLUG,
                constants.OPTIONS_WHEEL_VAULT_VAULT_SLUG,
                constants.DELTA_NEUTRAL_VAULT_VAULT_SLUG,
                # constants.KELPDAO_GAIN_VAULT_SLUG,
            }
            eligible_vaults = [v for v in vaults if v.slug in eligible_slugs]

            # Batch get withdrawal pool amounts
            for vault in eligible_vaults:
                pool_amounts[vault.contract_address.lower()] = (
                    service.get_withdrawal_pool_amount(vault)
                )

            # Complex query to get latest initiated withdrawals without completions
            query = get_pending_initiated_withdrawals_query()

            result = []
            for vault in eligible_vaults:
                vault_addresses = service.get_vault_address_historical(vault)
                params = {
                    "withdraw_method_id_1": constants.MethodID.WITHDRAW.value,
                    "complete_method_id": constants.MethodID.COMPPLETE_WITHDRAWAL.value,
                    "vault_addresses": vault_addresses,
                    "start_ts": self.start_date_timestamp,
                    "end_ts": self.end_date_timestamp,
                }

                init_withdraws = self.session.execute(query, params).all()

                for item in init_withdraws:
                    try:
                        amount = service.get_withdraw_amount(
                            vault,
                            Web3.to_checksum_address(item.to_address),
                            item.input,
                            item.block_number,
                        )

                        date = datetime.fromtimestamp(item.timestamp, tz=timezone.utc)
                        result.append(
                            {
                                "tx_hash": item.tx_hash,
                                "age": convert_timedelta_to_time(self.end_date - date),
                                "date": date.strftime("%Y-%m-%d %H:%M:%S"),
                                "vault_address": item.to_address,
                                "amount": amount,
                                "vault_name": vault.name,
                            }
                        )
                    except Exception as inner_e:
                        logger.error(
                            f"Error processing withdrawal item {item.id}: {inner_e}",
                            exc_info=True,
                        )

            return result, pool_amounts
        except Exception as e:
            logger.error(
                f"Error in get_withdrawals_for_current_day: {e}", exc_info=True
            )
            return [], {}

    def get_pendle_vault_withdrawals_for_current_day(
        self, vaults: List[Vault]
    ) -> List[dict]:
        try:
            reports = []
            for vault in vaults:
                service = VaultContractService()
                abi_name, _ = service.get_vault_abi(vault=vault)
                pendle_vault_contract, w3 = service.get_vault_contract(
                    vault.network_chain, vault.contract_address, abi_name
                )
                query = get_pending_initiated_withdrawals_query_pendle_vault()
                vault_addresses = service.get_vault_address_historical(vault)
                sc_withdraw_pool_amount, pt_withdraw_pool_amount = (
                    service.get_withdraw_pool_amount_pendle_vault(vault)
                )

                params = {
                    "withdraw_method_id_1": constants.MethodID.WITHDRAW_PENDLE2.value,
                    "withdraw_method_id_2": constants.MethodID.WITHDRAW_PENDLE1.value,
                    "complete_method_id": constants.MethodID.COMPPLETE_WITHDRAWAL2.value,
                    "vault_addresses": vault_addresses,
                    "start_ts": self.start_date_timestamp,
                    "end_ts": self.end_date_timestamp,
                }

                # Execute raw SQL query with parameters
                init_withdraws = self.session.execute(query, params).all()
                result = []

                for item in init_withdraws:
                    try:
                        pt_amount, sc_amount, shares = get_user_withdrawals(
                            item.from_address, pendle_vault_contract
                        )

                        result.append(
                            {
                                "pt_amount": pt_amount,
                                "sc_amount": sc_amount,
                                "shares": shares,
                            }
                        )

                    except Exception as inner_e:
                        logger.error(
                            f"Error processing withdrawal item {item.id}: {inner_e}",
                            exc_info=True,
                        )
                        continue
                # Create a DataFrame for the withdrawal details
                df_withdrawal_details = pd.DataFrame(result)

                # Calculate total Pendle withdrawal from df_withdrawal_details
                total_sc_withdrawn = (
                    df_withdrawal_details["sc_amount"].sum()
                    if "sc_amount" in df_withdrawal_details
                    else 0
                )
                total_pt_withdrawn = (
                    df_withdrawal_details["pt_amount"].sum()
                    if "pt_amount" in df_withdrawal_details
                    else 0
                )
                total_shares_withdrawn = (
                    df_withdrawal_details["shares"].sum()
                    if "shares" in df_withdrawal_details
                    else 0
                )
                # Create a report
                reports.append(
                    {
                        "total_sc_withdrawn": total_sc_withdrawn,
                        "total_pt_withdrawn": total_pt_withdrawn,
                        "total_shares_withdrawn": total_shares_withdrawn,
                        "sc_withdraw_pool_amount": sc_withdraw_pool_amount,
                        "pt_withdraw_pool_amount": pt_withdraw_pool_amount,
                        "total_sc_amount_needed": round(
                            total_sc_withdrawn - sc_withdraw_pool_amount, 2
                        ),
                        "total_pt_amount_needed": round(
                            total_pt_withdrawn - pt_withdraw_pool_amount, 2
                        ),
                        "vault": vault.name,
                        "vault_address": vault.contract_address,
                    }
                )

            return reports

        except Exception as e:
            logger.error(
                f"Error in get_pendle_vault_withdrawals_for_current_day: {e}",
                exc_info=True,
            )
            return []

    async def run(self):

        vaults = self._get_non_pendle_active_vaults()
        init_withdraws, pool_amounts = self.get_withdrawals_for_current_day(vaults)
        fields = [
            (
                withdrawal["vault_address"],
                withdrawal["amount"] if str(withdrawal["amount"]) else None,
                withdrawal["vault_name"],
            )
            for withdrawal in init_withdraws
        ]
        reports = self.get_pendle_vault_withdrawals_for_current_day(
            self._get_pendle_active_vaults()
        )

        await telegram_bot.send_alert(
            message=build_transaction_message(
                fields=fields, pool_amounts=pool_amounts, reports_pendle=reports
            ),
            channel="transaction",
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(
        app="scan_initiated_withdrawals", level=logging.INFO, logger=logger
    )

    job = InitiatedWithdrawalWatcherJob(session=session)
    asyncio.run(job.run())
