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


def _get_deposits(session: Session, wallet_address: str):
    return session.exec(
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
    ).all()


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
    session: Session, addresses: list[str]
) -> list[dict]:
    results = []

    for wallet_address in addresses:
        deposits = _get_deposits(session, wallet_address)
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
async def upload_csv(
    session: SessionDep,
    file: UploadFile = File(...),
    username: Optional[str] = Depends(authenticate),
):
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    try:
        contents = await file.read()
        df = pd.read_csv(io.BytesIO(contents))
        addresses = df["address"].tolist()

        # Process addresses and calculate deposits
        results = _process_deposit_with_addresses(session, addresses)

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
