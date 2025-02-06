from sqlmodel import SQLModel, Field
from uuid import UUID, uuid4
from datetime import datetime as dt, timezone

import sqlmodel

class ConfigQuotation(SQLModel, table=True):
    __tablename__ = "config.quotation"
    
    key : str = Field(primary_key=True)
    value : str
    updated_at : dt = Field(default=dt.now(timezone.utc), index=True)
    created_at : dt = Field(default=dt.now(timezone.utc), index=True)