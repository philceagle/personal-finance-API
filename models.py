from sqlalchemy import (
    Column, Integer, Float, String, ForeignKey, Date, UniqueConstraint
)
from database import Base
from datetime import date

class UserDB(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

class TransactionDB(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    amount = Column(Float, nullable=False)
    type = Column(String, nullable=False)
    category = Column(String, nullable=False)
    description = Column(String, nullable=False)
    # Nullable for compatibility with older records in existing databases.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    transaction_date = Column(Date, nullable=True, default=date.today, index=True)

class BudgetDB(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "category", "month", name="uq_budget_user_category_month"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    category = Column(String(50), nullable=False)
    monthly_limit = Column(Float, nullable=False)
    # ISO year-month, e.g. "2026-10"
    month = Column(String(7), nullable=False, index=True)
