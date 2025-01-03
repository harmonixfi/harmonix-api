from asyncio.log import logger
from datetime import timedelta
import uuid
import numpy as np
import pandas as pd
import pendulum
from sqlalchemy import text
from sqlmodel import Session, select
from web3 import Web3
from models.pps_history import PricePerShareHistory
from empyrical import sortino_ratio, downside_risk


def get_before_price_per_shares(
    session: Session, vault_id: uuid.UUID, days: int
) -> PricePerShareHistory:
    target_date = pendulum.now(tz=pendulum.UTC) - timedelta(days=days)

    # Get the PricePerShareHistory records before the target date and order them by datetime in descending order

    pps_history = session.exec(
        select(PricePerShareHistory)
        .where(PricePerShareHistory.vault_id == vault_id)
        .where(PricePerShareHistory.datetime <= target_date)
        .order_by(PricePerShareHistory.datetime.desc())
        .limit(3)
    ).all()

    # If there are any records, return the price per share of the most recent one
    if pps_history:
        return pps_history[0]

    pps_history = session.exec(
        select(PricePerShareHistory)
        .where(PricePerShareHistory.vault_id == vault_id)
        .order_by(PricePerShareHistory.datetime.asc())
    ).first()
    # If there are no records before the target date, return None
    # and the first record of pps_history datetime
    return pps_history


def calculate_roi(after: float, before: float, days: int) -> float:
    # calculate our annualized return for a vault
    pps_delta = (after - before) / (before or 1)
    annualized_roi = (1 + pps_delta) ** (365.2425 / days) - 1
    return annualized_roi


def calculate_risk_factor(returns):
    # Filter out positive returns
    negative_returns = [r for r in returns if r < 0]

    # Calculate standard deviation of negative returns
    risk_factor = np.std(negative_returns)

    if np.isnan(risk_factor) or np.isinf(risk_factor):
        risk_factor = 0
    return risk_factor


def calculate_pps_statistics(session, vault_id):
    statement = (
        select(PricePerShareHistory)
        .where(PricePerShareHistory.vault_id == vault_id)
        .order_by(PricePerShareHistory.datetime.asc())
    )
    pps = session.exec(statement).all()

    list_pps = []
    for p in pps:
        list_pps.append({"datetime": p.datetime, "price_per_share": p.price_per_share})
    df = pd.DataFrame(list_pps)
    df.set_index("datetime", inplace=True)
    df.sort_index(inplace=True)
    df["pct_change"] = df["price_per_share"].pct_change()

    all_time_high_per_share = df["price_per_share"].max()

    sortino = float(sortino_ratio(df["pct_change"], period="weekly"))
    if np.isnan(sortino) or np.isinf(sortino):
        sortino = 0
    downside = float(downside_risk(df["pct_change"], period="weekly"))
    if np.isnan(downside) or np.isinf(downside):
        downside = 0
    returns = df["pct_change"].values.flatten()
    risk_factor = calculate_risk_factor(returns)
    return all_time_high_per_share, sortino, downside, risk_factor


def get_pps_by_blocknumber(vault_contract, block_number: int) -> float:
    pps = vault_contract.functions.pricePerShare().call(block_identifier=block_number)
    return pps / 1e6


def get_pending_initiated_withdrawals_query():
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
            method_id,
            ROW_NUMBER() OVER (PARTITION BY from_address ORDER BY timestamp DESC) AS rn
        FROM public.onchain_transaction_history
        WHERE method_id IN (:withdraw_method_id_1)
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
            AND to_address = ANY(:vault_addresses)
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
    return query


def get_pending_initiated_withdrawals_query_pendle_vault():
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
            method_id,
            ROW_NUMBER() OVER (PARTITION BY from_address ORDER BY timestamp DESC) AS rn
        FROM public.onchain_transaction_history
        WHERE method_id IN (:withdraw_method_id_1, :withdraw_method_id_2)
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
            AND to_address = ANY(:vault_addresses)
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
    return query


def get_user_withdrawals(user_address: str, pendle_vault):
    try:
        # Call the getUserWithdraw function
        result = pendle_vault.functions.getUserWithdraw().call(
            {"from": Web3.to_checksum_address(user_address)}
        )

        # Extract ptWithdrawAmount and scWithdrawAmount
        withdrawalShares = result[0]
        ptWithdrawAmount = result[2]  # Assuming ptWithdrawAmount is the third element
        scWithdrawAmount = result[3]  # Assuming scWithdrawAmount is the fourth element

        # Convert to float
        ptWithdrawAmount_float = ptWithdrawAmount / 1e18
        scWithdrawAmount_float = scWithdrawAmount / 1e6
        withdrawalShares_float = withdrawalShares / 1e6

        return (
            ptWithdrawAmount_float,
            scWithdrawAmount_float,
            withdrawalShares_float,
        )
    except Exception as e:
        logger.error(f"Error fetching withdrawal details for {user_address}: {e}")
    return 0.0, 0.0, 0.0
