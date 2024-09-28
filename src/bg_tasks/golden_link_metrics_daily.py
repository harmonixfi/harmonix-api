from datetime import datetime, timezone
import logging
import uuid

from sqlmodel import Session, select
from core import constants
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models import Vault
from models.vaults import VaultMetadata
from services.gold_link_service import get_borrow_apr, get_health_factor_score

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("golden_link_metrics_daily")

session = Session(engine)

LEVERAGE: float = 4
OPEN_POSITIONS: float = 435.55


def save_or_update_vault_metadata(
    vault_id: uuid.UUID,
    borrow_apr: float,
    health_factor: float,
    leverage: float,
    open_position: float,
):
    vault_metadata = session.exec(
        select(VaultMetadata).where(VaultMetadata.vault_id == vault_id)
    ).first()
    now = datetime.now(timezone.utc)

    if vault_metadata:
        # Update existing vault metadata
        vault_metadata.borrow_apr = borrow_apr
        vault_metadata.health_factor = health_factor
        vault_metadata.leverage = leverage  # Corrected leverage assignment
        vault_metadata.open_position = open_position
        vault_metadata.last_updated = now
    else:
        # Create new vault metadata
        vault_metadata = VaultMetadata(
            vault_id=vault_id,
            borrow_apr=borrow_apr,
            health_factor=health_factor,
            leverage=leverage,
            open_position=open_position,
            last_updated=now,
        )
        session.add(vault_metadata)

    session.commit()


# Main Execution
def main():
    try:
        logger.info(
            "Start calculating Gold Link metrics daily for vaults..."
        )  # Updated log message
        vaults = session.exec(
            select(Vault)
            .where(Vault.strategy_name == constants.GOLD_LINK_STRATEGY)
            .where(Vault.is_active == True)
        ).all()

        for vault in vaults:
            try:
                health_factor_score = get_health_factor_score() * 100
                borrow_apr = get_borrow_apr() * 100
                save_or_update_vault_metadata(
                    vault.id,
                    borrow_apr=borrow_apr,
                    health_factor=health_factor_score,
                    leverage=LEVERAGE,
                    open_position=OPEN_POSITIONS,
                )
            except Exception as vault_error:
                logger.error(
                    "An error occurred while processing vault %s: %s",
                    vault.id,
                    vault_error,
                    exc_info=True,
                )

    except Exception as e:
        logger.error(
            "An error occurred during Gold Link metrics calculation: %s",
            e,
            exc_info=True,  # Updated error message
        )


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("golden_link_metrics_daily", logger=logger)
    main()
