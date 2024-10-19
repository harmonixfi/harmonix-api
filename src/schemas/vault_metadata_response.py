from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel


class VaultMetadataResponse(BaseModel):
    vault_id: uuid.UUID
    borrow_apr: Optional[float] = None
    health_factor: Optional[float] = None
    leverage: Optional[float] = None
    open_position_size: Optional[float] = None
    last_updated: Optional[datetime] = None
