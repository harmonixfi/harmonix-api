import asyncio
from datetime import datetime, timedelta, timezone
import logging
from typing import List
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
        self.start_date = utc_now + timedelta(hours=-8)
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

            for vault in vaults:
                contract_address = [
                    address.lower()
                    for address in service.get_vault_address_historical(vault)
                ]
                init_withdraw_query = (
                    select(OnchainTransactionHistory)
                    .where(
                        OnchainTransactionHistory.method_id.in_(
                            [
                                constants.MethodID.WITHDRAW.value,
                            ]
                        )
                    )
                    .where(OnchainTransactionHistory.to_address.in_(contract_address))
                    .where(
                        OnchainTransactionHistory.timestamp <= self.end_date_timestamp
                    )
                    .where(
                        OnchainTransactionHistory.timestamp >= self.start_date_timestamp
                    )
                )
                init_withdraws = self.session.exec(init_withdraw_query).all()
                for item in init_withdraws:
                    try:
                        amount = service.get_withdraw_amount(
                            vault,
                            Web3.to_checksum_address(item.to_address),
                            item.input,
                            item.block_number,
                        )
                        date = datetime.fromtimestamp(item.timestamp, tz=timezone.utc)
                        age = convert_timedelta_to_time(self.end_date - date)

                        result.append(
                            schemas.OnchainTransactionHistory(
                                id=item.id,
                                method_id=item.method_id,
                                timestamp=item.timestamp,
                                input=item.input,
                                tx_hash=item.tx_hash,
                                datetime=date,
                                amount=amount,
                                age=age,
                            )
                        )
                    except Exception as inner_e:
                        logger.error(
                            f"Error processing scan withdrawal for vault {vault}, item {item.id}: {inner_e}",
                            exc_info=True,
                        )
                    continue

            return result
        except Exception as e:
            logger.error(
                f"Error in get_withdrawals_for_current_day: {e}", exc_info=True
            )
        return []

    async def run(self):
        init_withdraws = self.get_withdrawals_for_current_day()
        fields = [
            (
                withdrawal.tx_hash,
                withdrawal.datetime.strftime("%H:%M:%S"),
                str(withdrawal.amount),
                str(withdrawal.age),
            )
            for withdrawal in init_withdraws
        ]

        await telegram_bot.send_alert(
            build_transaction_message(fields=fields),
            channel="transaction",
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file(
        app="scan_initiated_withdrawals", level=logging.INFO, logger=logger
    )

    job = InitiatedWithdrawalWatcherJob(session=session)
    asyncio.run(job.run())
