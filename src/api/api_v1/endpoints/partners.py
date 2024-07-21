from typing import List, Optional
from fastapi import APIRouter, Query
from sqlmodel import select

from api.api_v1.deps import SessionDep
from models.user_assets_history import UserHoldingAssetHistory
from models.vaults import NetworkChain
from schemas.user_assets import UserAssetAmount

router = APIRouter()


@router.get("/kelpdao/all-users", response_model=List[UserAssetAmount])
def get_user_asset_amounts(
    session: SessionDep,
    chain: NetworkChain,
    block_number: Optional[int] = Query(
        None, description="The block number to fetch the asset amounts for"
    ),
    user_address: Optional[str] = Query(
        None, description="The user address to filter the asset amounts for"
    ),
):

    # Build the base query
    query = select(
        UserHoldingAssetHistory.user_address, UserHoldingAssetHistory.asset_amount
    )

    # Apply the user_address filter if provided
    if user_address:
        query = query.where(UserHoldingAssetHistory.user_address == user_address)

    if block_number:
        query = query.where(UserHoldingAssetHistory.block_number <= block_number)

    query = query.where(UserHoldingAssetHistory.chain == chain)

    # Subquery to get the latest block_number less than or equal to the specified block_number for each user
    subquery = query.order_by(
        UserHoldingAssetHistory.user_address,
        UserHoldingAssetHistory.block_number.desc(),
    ).distinct(UserHoldingAssetHistory.user_address)

    # Main query to get the latest asset_amount for each user
    latest_assets = session.exec(subquery).all()

    data = []
    for user, amount in latest_assets:
        data.append(
            UserAssetAmount(
                user_address=user,
                asset_amount=amount,
                asset_amount_in_uint256=int(amount * 1e18),
            )
        )

    return data
