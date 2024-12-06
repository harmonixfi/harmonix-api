import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import List
from sqlalchemy import text
from sqlmodel import Session, col, select
from core import constants
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.onchain_transaction_history import OnchainTransactionHistory
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
        self.start_date = utc_now - timedelta(days=3*30)
        self.end_date = utc_now
        self.start_date_timestamp = int(self.start_date.timestamp())
        self.end_date_timestamp = int(self.end_date.timestamp())

    def __get_active_vaults(self) -> List[Vault]:
        result = self.session.exec(select(Vault).where(Vault.is_active)).all()
        return result

    def get_withdrawals_for_current_day(
        self,
    ) -> List[schemas.OnchainTransactionHistory]:
        try:
            vaults = self.__get_active_vaults()
            service = VaultContractService()
            result = []
            pool_amounts = {}  # Track withdrawal pool amounts per vault

            # Get withdrawal pool amounts for each vault
            for vault in vaults:
                pool_amount = service.get_withdrawal_pool_amount(vault)
                pool_amounts[vault.contract_address.lower()] = pool_amount

            # Get all historical vault addresses
            all_vault_addresses = []
            for vault in vaults:
                all_vault_addresses.extend(
                    [
                        addr.lower()
                        for addr in service.get_vault_address_historical(vault)
                    ]
                )

            # Complex query to get latest initiated withdrawals without completions
            query = text(
                """
                WITH latest_initiated_withdrawals AS (
                    SELECT 
                        id,
                        from_address,
                        to_address,
                        tx_hash,
                        timestamp,
                        input,
                        block_number,
                        ROW_NUMBER() OVER (PARTITION BY from_address ORDER BY timestamp DESC) AS rn
                    FROM public.onchain_transaction_history
                    WHERE method_id = :withdraw_method_id
                    AND to_address = ANY(:vault_addresses)
                    AND timestamp >= :start_ts
                    AND timestamp <= :end_ts
                ),
                has_later_completion AS (
                    SELECT DISTINCT 
                        i.from_address,
                        i.tx_hash
                    FROM latest_initiated_withdrawals i
                    WHERE i.rn = 1
                    AND EXISTS (
                        SELECT 1
                        FROM public.onchain_transaction_history c
                        WHERE c.from_address = i.from_address
                        AND c.method_id = :complete_method_id
                        AND c.timestamp > i.timestamp
                    )
                )
                SELECT *
                FROM latest_initiated_withdrawals i
                WHERE i.rn = 1
                AND NOT EXISTS (
                    SELECT 1 
                    FROM has_later_completion h 
                    WHERE h.from_address = i.from_address
                );
            """
            )

            # Execute raw SQL query with parameters
            init_withdraws = self.session.execute(
                query,
                {
                    "withdraw_method_id": constants.MethodID.WITHDRAW.value,
                    "complete_method_id": constants.MethodID.COMPPLETE_WITHDRAWAL.value,
                    "vault_addresses": all_vault_addresses,
                    "start_ts": self.start_date_timestamp,
                    "end_ts": self.end_date_timestamp,
                },
            ).all()

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
                        amount = service.get_withdraw_amount(
                            matching_vault,
                            Web3.to_checksum_address(item.to_address),
                            item.input,
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
                                user_address=item.from_address
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
            )
            for withdrawal in init_withdraws
        ]

        await telegram_bot.send_alert(
            build_transaction_message(fields=fields, pool_amounts=pool_amounts),
            channel="transaction",
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(
        app="scan_initiated_withdrawals", level=logging.INFO, logger=logger
    )

    job = InitiatedWithdrawalWatcherJob(session=session)
    asyncio.run(job.run())
