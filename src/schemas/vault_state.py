from pydantic import BaseModel


class OldVaultState(BaseModel):
    performance_fee: float = 0
    management_fee: float = 0
    current_round_fee: float = 0
    withdrawal_pool: float = 0
    pending_deposit: float = 0
    total_share: float = 0
    last_locked: float = 0


class VaultState(BaseModel):
    withdraw_pool_amount: float = 0
    pending_deposit: float = 0
    total_share: float = 0
    total_fee_pool_amount: float = 0
    last_update_management_fee_date: int = 0


class VaultStatePendle(BaseModel):
    old_pt_token_address: str = None
    pps: float = 0
    pt_withdraw_pool_amount: float = 0
    sc_withdraw_pool_amount: float = 0
    total_pt_amount: float = 0
    total_shares: float = 0
    total_fee_pool_amount: float = 0
    last_update_management_fee_date: float = 0


class DepositReceiptPendle(BaseModel):
    shares: float | None = 0
    deposit_amount: float | None = 0
    deposit_pt_amount: float | None = 0
    deposit_sc_amount: float | None = 0
