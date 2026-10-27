from datetime import date
from math import isfinite
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

class Transaction(BaseModel):
    amount: float = Field(gt=0, allow_inf_nan=False)
    type: Literal["income", "expense"]
    category: str = Field(min_length=1, max_length=50)
    description: str = Field(min_length=1, max_length=200)
    transaction_date: date = Field(default_factory=date.today)

    @field_validator("category", "description")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank.")
        return value

class TransactionResponse(Transaction):
    id: int
    # Old rows can have no date until edited, so keep this nullable for compatibility.
    transaction_date: date | None = None
    model_config = ConfigDict(from_attributes=True)

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    model_config = ConfigDict(from_attributes=True)

class Token(BaseModel):
    access_token: str
    token_type: str

class BudgetCreate(BaseModel):
    category: str = Field(min_length=1, max_length=50)
    monthly_limit: float = Field(gt=0, allow_inf_nan=False)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")

    @field_validator("category")
    @classmethod
    def trim_category(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Category cannot be blank.")
        return value

class BudgetResponse(BudgetCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)
