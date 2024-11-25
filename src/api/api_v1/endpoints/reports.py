import csv
from datetime import datetime, timedelta, timezone
import io
import json
import secrets
from typing import List, Optional
import uuid

from fastapi.responses import StreamingResponse
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func
from sqlmodel import Session, select
from api.api_v1.auth_utils import authenticate
from models.onchain_transaction_history import OnchainTransactionHistory
import schemas
from api.api_v1.deps import SessionDep
from core import constants
from models import Vault
from services.vault_contract_service import VaultContractService
from api.api_v1.deps import SessionDep
from utils.extension_utils import to_amount_pendle, to_tx_aumount

router = APIRouter()


def _get_deposits(
    session: Session,
    wallet_address: str,
    start_date: datetime,
    end_date: Optional[datetime] = None,
):
    start_timestamp = int(start_date.timestamp())
    end_timestamp = int(end_date.timestamp()) if end_date else None
    query = (
        select(OnchainTransactionHistory)
        .where(
            OnchainTransactionHistory.method_id.in_(
                [
                    constants.MethodID.DEPOSIT2.value,
                    constants.MethodID.DEPOSIT.value,
                    constants.MethodID.DEPOSIT3.value,
                    constants.MethodID.DEPOSIT4.value,
                ]
            )
        )
        .where(
            func.lower(OnchainTransactionHistory.from_address) == wallet_address.lower()
        )
        .where(OnchainTransactionHistory.timestamp >= start_timestamp)
    )

    if end_timestamp:
        query = query.where(OnchainTransactionHistory.timestamp <= end_timestamp)

    return session.exec(query).all()


def _get_vault(session: Session, to_address: str):
    vault_address = VaultContractService().get_vault_address_by_contract(
        to_address.lower()
    )
    return session.exec(
        select(Vault).where(
            func.lower(Vault.contract_address).in_(
                [addr.lower() for addr in vault_address]
            )
        )
    ).first()


def _calculate_total_deposit(session: Session, deposits):
    total_deposit = 0
    for deposit in deposits:
        vault = _get_vault(session, deposit.to_address)
        if not vault:
            continue
        if vault.strategy_name == constants.PENDLE_HEDGING_STRATEGY:
            total_deposit += to_amount_pendle(
                deposit.input, deposit.block_number, vault.network_chain
            )
        else:
            total_deposit += to_tx_aumount(deposit.input)
    return total_deposit


def _process_deposit_with_addresses(
    session: Session,
    addresses: list[str],
    start_date: datetime,
    end_date: Optional[datetime],
) -> list[dict]:
    results = []

    for wallet_address in addresses:
        deposits = _get_deposits(session, wallet_address, start_date, end_date)
        if deposits:
            total_deposit = _calculate_total_deposit(session, deposits)
            results.append(
                {
                    "wallet_address": wallet_address,
                    "deposited": True,
                    "total amount": total_deposit,
                }
            )
        else:
            results.append(
                {
                    "wallet_address": wallet_address,
                    "deposited": False,
                    "total amount": 0,
                }
            )
    return results


def _generate_csv(results: list[dict]) -> io.StringIO:
    output = io.StringIO()
    fieldnames = ["wallet_address", "deposited", "total amount"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(results)
    output.seek(0)
    return output


@router.post("/analyze_user_deposit_from_csv")
async def analyze_user_deposit_from_csv(
    session: SessionDep,
    file: UploadFile = File(...),
    username: Optional[str] = Depends(authenticate),
    start_date: datetime = Query(
        None,
        description="The start date for analysis. Format: 2024-11-25T12:00:00+07:00. This field is required.",
        example="2024-11-25T12:00:00+07:00",
    ),
    end_date: Optional[datetime] = Query(
        None,
        description=(
            "The end date for analysis. Format: 2024-11-30T12:00:00+07:00. "
            "This field is optional. If not provided, the analysis will include data up to the current time."
        ),
        example="2024-11-30T12:00:00+07:00",
    ),
):
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    if start_date.tzinfo is None:
        raise ValueError("start_date must include timezone information")
    elif start_date.tzinfo != timezone.utc:
        start_date = start_date.astimezone(timezone.utc)

    if end_date:
        if end_date.tzinfo is None:
            raise ValueError("end_date must include timezone information")
        elif end_date.tzinfo != timezone.utc:
            end_date = end_date.astimezone(timezone.utc)

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        addresses = df["address"].tolist()

        # Process addresses and calculate deposits
        results = _process_deposit_with_addresses(
            session, addresses, start_date, end_date
        )

        # Generate CSV output
        csv_file = _generate_csv(results)

        # Return CSV as a streaming response
        return StreamingResponse(
            csv_file,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=results.csv"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error processing the file: {str(e)}"
        )
