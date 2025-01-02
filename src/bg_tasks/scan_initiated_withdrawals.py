import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import List, Optional
from sqlalchemy import text
from sqlmodel import Session, col, select
from core import constants
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.onchain_transaction_history import OnchainTransactionHistory
from models.vaults import Vault
from notifications import telegram_bot
from notifications.message_builder import (
    build_transaction_message,
    build_transaction_messages_media,
    build_transaction_page,
)
import schemas
from services.market_data import get_price
from services.scan_initiated_withdrawals_base_service import (
    get_pending_initiated_withdrawals_query,
)
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

    def __get_active_vaults(self) -> List[Vault]:
        result = self.session.exec(
            select(Vault)
            .where(Vault.is_active)
            .where(Vault.id == "176a024b-74b9-4390-97c5-066748c088e4")
        ).all()
        return result

    def get_withdrawals_for_current_day(
        self,
    ) -> List[schemas.OnchainTransactionHistory]:
        try:
            vaults = self.__get_active_vaults()
            service = VaultContractService()
            result = []
            pool_amounts = {}  # Track withdrawal pool amounts per vault

            # Complex query to get latest initiated withdrawals without completions
            query = get_pending_initiated_withdrawals_query()

            # Get withdrawal pool amounts for each vault
            for vault in vaults:
                vault_addresses = service.get_vault_address_historical(vault)
                if vault.slug in [
                    constants.HYPE_DELTA_NEUTRAL_SLUG,
                    constants.KELPDAO_VAULT_ARBITRUM_SLUG,
                ]:
                    pool_amount = service.get_withdrawal_pool_amount(vault)
                    pool_amounts[vault.contract_address.lower()] = pool_amount
                    # Define parameters for the query
                    params = {
                        "withdraw_method_id_1": constants.MethodID.WITHDRAW.value,  # First initiate withdrawal method ID
                        "complete_method_id": constants.MethodID.COMPPLETE_WITHDRAWAL.value,  # Complete withdrawal method ID
                        "vault_addresses": vault_addresses,
                        "start_ts": self.start_date_timestamp,
                        "end_ts": self.end_date_timestamp,
                    }
                elif vault.slug == constants.PENDLE_RSETH_26DEC24_SLUG:
                    pool_amount, _ = service.get_withdraw_pool_amount_pendle_vault(
                        vault
                    )
                    pool_amounts[vault.contract_address.lower()] = pool_amount

                    params = {
                        "withdraw_method_id_1": constants.MethodID.WITHDRAW_PENDLE2.value,  # First initiate withdrawal method ID
                        "complete_method_id": constants.MethodID.COMPPLETE_WITHDRAWAL.value,  # Complete withdrawal method ID
                        "vault_addresses": vault_addresses,
                        "start_ts": self.start_date_timestamp,
                        "end_ts": self.end_date_timestamp,
                    }

            # Get all historical vault addresses
            all_vault_addresses = []
            for vault in vaults:
                all_vault_addresses.extend(
                    [
                        addr.lower()
                        for addr in service.get_vault_address_historical(vault)
                    ]
                )

            # Execute raw SQL query with parameters
            init_withdraws = self.session.execute(query, params).all()

            # Process results and calculate additional fields
            for item in init_withdraws:
                try:
                    # Find matching vault for this address
                    matching_vault = next(
                        (
                            v
                            for v in vaults
                            if item.to_address.lower()
                            in [
                                addr.lower()
                                for addr in service.get_vault_address_historical(v)
                            ]
                        ),
                        None,
                    )

                    if matching_vault:
                        input_data = item.input
                        pt_amount: Optional[float] = None

                        if item.method_id in [
                            constants.MethodID.WITHDRAW_PENDLE1.value,
                            constants.MethodID.WITHDRAW_PENDLE2.value,
                        ]:
                            input_data = (
                                service.get_input_data_from_transaction_receipt_event(
                                    matching_vault, item.tx_hash
                                )
                            )
                            amount, pt_amount = service.get_withdraw_amount_pendle(
                                matching_vault, input_data, item.block_number
                            )
                        else:
                            amount = service.get_withdraw_amount(
                                matching_vault,
                                Web3.to_checksum_address(item.to_address),
                                input_data,
                                item.block_number,
                            )

                        date = datetime.fromtimestamp(item.timestamp, tz=timezone.utc)
                        age = convert_timedelta_to_time(self.end_date - date)

                        result.append(
                            schemas.OnchainTransactionHistory(
                                id=item.id,
                                method_id=constants.MethodID.WITHDRAW.value,
                                timestamp=item.timestamp,
                                input=item.input,
                                tx_hash=item.tx_hash,
                                datetime=date,
                                amount=amount,
                                age=age,
                                vault_address=item.to_address,
                                user_address=item.from_address,
                                pt_amount=pt_amount,
                            )
                        )
                except Exception as inner_e:
                    logger.error(
                        f"Error processing withdrawal item {item.id}: {inner_e}",
                        exc_info=True,
                    )
                    continue

            return result, pool_amounts
        except Exception as e:
            logger.error(
                f"Error in get_withdrawals_for_current_day: {e}", exc_info=True
            )
        return [], {}

    async def run(self):
        init_withdraws, pool_amounts = self.get_withdrawals_for_current_day()
        fields = [
            (
                withdrawal.tx_hash,
                withdrawal.vault_address,
                withdrawal.datetime.strftime("%Y-%m-%d %H:%M:%S"),
                str(withdrawal.amount),
                str(withdrawal.age),
                str(withdrawal.pt_amount) if withdrawal.pt_amount else None,
            )
            for withdrawal in init_withdraws
        ]

        await telegram_bot.send_alert_by_media(
            build_transaction_page(fields=fields, pool_amounts=pool_amounts),
            channel="transaction",
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(
        app="scan_initiated_withdrawals", level=logging.INFO, logger=logger
    )

    job = InitiatedWithdrawalWatcherJob(session=session)
    asyncio.run(job.run())
