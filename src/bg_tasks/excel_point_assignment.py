from datetime import datetime, timezone
import logging
import traceback
from uuid import UUID
import pandas as pd
from sqlalchemy import func
from sqlmodel import Session, col, select

from core import constants
from core.db import engine
from log import setup_logging_to_console, setup_logging_to_file
from models.point_distribution_history import PointDistributionHistory
from models.user import User
from models.user_points import UserPointAudit, UserPoints
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vaults import Vault

session = Session(engine)


# # Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("excel_point_assignment")
logger.setLevel(logging.INFO)


def process_excel_points(df: pd.DataFrame):
    """
    Process points from Excel file and distribute to users

    Args:
        df: DataFrame containing Wallet and Points columns
    """
    logger.info(f"Processing points for {len(df)} users")

    # Validate data
    if not all(col in df.columns for col in ["Wallet", "Points"]):
        raise ValueError("CSV must contain 'Wallet' and 'Points' columns")

    df["Wallet"] = df["Wallet"].str.lower()

    # Process each wallet-points pair
    for _, row in df.iterrows():
        wallet = row["Wallet"]
        points = float(row["Points"])

        try:
            user_portfolio = session.exec(
                select(UserPortfolio)
                .where(UserPortfolio.user_address == wallet)
                .where(UserPortfolio.status == PositionStatus.ACTIVE)
            ).first()

            if user_portfolio is None:
                logger.error(f"Active portfolio not found for wallet address: {wallet}")
                continue

            user = session.exec(
                select(User).where(func.lower(User.wallet_address) == wallet)
            ).first()

            if user is None:
                logger.error(f"User not found for wallet address: {wallet}")
                continue

            # Check if user points record exists
            user_points = session.exec(
                select(UserPoints)
                .where(func.lower(UserPoints.wallet_address) == wallet)
                .where(UserPoints.partner_name == constants.HARMONIX)
            ).first()

            if user_points:
                old_point_value = user_points.points
                user_points.points += points
            else:
                old_point_value = 0
                user_points = UserPoints(
                    wallet_address=wallet,
                    points=points,
                    partner_name=constants.HARMONIX,
                    vault_id=user_portfolio.vault_id,
                )

            session.add(user_points)
            session.flush()
            # Add audit record
            audit = UserPointAudit(
                user_points_id=user_points.id,
                old_value=old_point_value,
                new_value=user_points.points,
            )
            session.add(audit)

            logger.info(
                "Processed points for wallet %s: %s -> %s",
                wallet,
                old_point_value,
                user_points.points,
            )

        except Exception as e:
            logger.error(
                "Error processing points for wallet %s: %s",
                wallet,
                str(e),
                exc_info=True,
            )
            continue

    # session.commit()


def update_vault_points(current_time):
    active_vaults_query = select(Vault).where(Vault.is_active == True)
    active_vaults = session.exec(active_vaults_query).all()

    for vault in active_vaults:
        try:
            # get all earned points for the vault
            total_points_query = (
                select(func.sum(UserPoints.points))
                .where(UserPoints.vault_id == vault.id)
                .where(UserPoints.partner_name == constants.HARMONIX)
            )
            total_points = session.exec(total_points_query).one()
            logger.info(
                f"Vault {vault.name} has earned {total_points} points from Harmonix."
            )
            # insert points distribution history
            point_distribution_history = PointDistributionHistory(
                vault_id=vault.id,
                partner_name=constants.HARMONIX,
                point=total_points if total_points else 0,
                created_at=current_time,
            )
            session.add(point_distribution_history)
            # session.commit()
        except Exception as e:
            logger.error(
                f"An error occurred while updating points distribution history for vault {vault.name}: {e}",
                exc_info=True,
            )
            logger.error(traceback.format_exc())

    logger.info("Points distribution history updated.")


def main():
    try:
        # Read and process the Excel file
        file_path = "./data/input/excel_point_assignment.csv"
        df = pd.read_csv(file_path, encoding="ISO-8859-1")
        extracted_data = df[["Wallet", "Points"]]

        # Process the points
        process_excel_points(extracted_data)
        current_time = datetime.now(tz=timezone.utc)
        update_vault_points(current_time)

    except Exception as e:
        logger.error("Failed to process Excel points: %s", str(e), exc_info=True)
        raise


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("excel_point_assignment", logger=logger)
    main()
