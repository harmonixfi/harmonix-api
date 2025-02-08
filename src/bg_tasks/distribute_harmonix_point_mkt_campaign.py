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
from models.reward_sessions import RewardSessions
from models.user import User
from models.user_points import UserPointAudit, UserPoints
from models.user_portfolio import PositionStatus, UserPortfolio
from models.vaults import Vault

session = Session(engine)


# # Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("distribute_harmonix_point_mkt_campaign")
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

    hype_vault = session.exec(
        select(Vault).where(Vault.slug == constants.HYPE_DELTA_NEUTRAL_SLUG)
    ).first()

    reward_session_query = (
        select(RewardSessions)
        .where(RewardSessions.partner_name == constants.HARMONIX)
        .where(RewardSessions.end_date == None)
    )
    reward_session = session.exec(reward_session_query).first()
    if reward_session is None:
        logger.error(
            "No active reward session found for partner: %s", constants.HARMONIX
        )
        raise ValueError("No active reward session found.")

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

            # Set default vault_id to user's active portfolio vault, fallback to hype vault
            vault_id = user_portfolio.vault_id if user_portfolio else hype_vault.id
            if user_portfolio is None:
                logger.warning("No active portfolio found %s", wallet)

            # Check if user points record exists
            user_points = session.exec(
                select(UserPoints)
                .where(func.lower(UserPoints.wallet_address) == wallet)
                .where(UserPoints.partner_name == constants.HARMONIX_MKT)
                .where(UserPoints.session_id == reward_session.session_id)
            ).first()

            if user_points:
                old_point_value = user_points.points
                user_points.points += points
            else:
                old_point_value = 0
                user_points = UserPoints(
                    wallet_address=wallet,
                    points=points,
                    partner_name=constants.HARMONIX_MKT,
                    vault_id=vault_id,
                    session_id=reward_session.session_id,
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

    session.commit()


def update_distribution_history_for_vaults(current_time):
    logger.info("Processing update distribution history for vaults...")
    active_vaults_query = select(Vault).where(Vault.is_active == True)
    active_vaults = session.exec(active_vaults_query).all()

    for vault in active_vaults:
        try:
            # get all earned points for the vault
            total_points_query = (
                select(func.sum(UserPoints.points))
                .where(UserPoints.vault_id == vault.id)
                .where(UserPoints.partner_name == constants.HARMONIX_MKT)
            )
            total_points = session.exec(total_points_query).one()
            logger.info(
                f"Vault {vault.name} has earned {total_points} points from Harmonix."
            )
            # insert points distribution history
            point_distribution_history = PointDistributionHistory(
                vault_id=vault.id,
                partner_name=constants.HARMONIX_MKT,
                point=total_points if total_points else 0,
                created_at=current_time,
            )
            session.add(point_distribution_history)
            session.commit()
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
        update_distribution_history_for_vaults(current_time)

    except Exception as e:
        logger.error("Failed to process Excel points: %s", str(e), exc_info=True)
        raise


if __name__ == "__main__":
    setup_logging_to_console()
    setup_logging_to_file("distribute_harmonix_point_mkt_campaign", logger=logger)
    main()
