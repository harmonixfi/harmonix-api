import logging
from datetime import datetime, timezone
import uuid
from sqlmodel import Session
from web3 import Web3

from core import constants
from core.abi_reader import read_abi
from log import setup_logging_to_console, setup_logging_to_file
from core.db import engine
from models.vault_reward_history import VaultRewardHistory
from models.vault_rewards import VaultRewards
from models.vaults import Vault
from services.bsx_service import claim_point, get_list_claim_point
from sqlmodel import Session, select


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


session = Session(engine)


def get_contract(vault: Vault, abi_name="goldlink"):
    web3 = Web3(Web3.HTTPProvider(constants.NETWORK_RPC_URLS[vault.network_chain]))

    abi = read_abi(abi_name)
    return web3.eth.contract(address=vault.contract_address, abi=abi)


def upsert_vault_rewards(
    vault_id: uuid.UUID,
    earned_rewards: float,
    claimed_rewards: float,
    token_address: str = "",
    token_name: str = "ARB",
):
    vault_reward = session.exec(
        select(VaultRewards).where(VaultRewards.vault_id == vault_id)
    ).first()

    unclaimed_rewards = earned_rewards - claimed_rewards
    if not vault_reward:
        vault_reward = VaultRewards(
            vault_id=vault_id,
            earned_rewards=earned_rewards,
            unclaimed_rewards=earned_rewards - claimed_rewards,
            claimed_rewards=claimed_rewards,
            token_address=token_address,
            token_name=token_name,
        )
    else:
        vault_reward.earned_rewards = earned_rewards
        vault_reward.unclaimed_rewards = unclaimed_rewards
        vault_reward.claimed_rewards = claimed_rewards

    vault_reward_history = VaultRewardHistory(
        vault_id=vault_id,
        earned_rewards=earned_rewards,
        unclaimed_rewards=earned_rewards - claimed_rewards,
        claimed_rewards=claimed_rewards,
        token_address=token_address,
        token_name=token_name,
        datetime=datetime.now(tz=timezone.utc),
    )
    session.add(vault_reward)
    session.add(vault_reward_history)
    session.commit()
    return


def gold_link_claim_weelky():
    try:
        logger.info("Starting Gold Link to claim")
        vaults = session.exec(
            select(Vault)
            .where(Vault.strategy_name == constants.GOLD_LINK_STRATEGY)
            .where(Vault.is_active.is_(True))
        ).all()

        logger.info("Starting Gold Link point claiming process")
        for vault in vaults:
            try:
                contract = get_contract(vault)
                earned_rewards = float(
                    contract.functions.rewardsOwed(
                        Web3.to_checksum_address(vault.contract_address)
                    ).call()
                    / 1e18
                )

                claimed_rewards = float(0.0)
                upsert_vault_rewards(vault.id, earned_rewards, float(claimed_rewards))

            except Exception as claim_error:
                logger.error(
                    "Error claiming point for vault %s: %s", vault.id, str(claim_error)
                )  # Fixed logger format

        logger.info("Gold Link point claiming process completed.")
    except Exception as e:
        logger.error(
            "Error occurred during Gold Link  point claiming process: %s", str(e)
        )  # Fixed logger format


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("gold_link_claim_weelky", logger=logger)
    gold_link_claim_weelky()
