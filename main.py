from datetime import date
from typing import Literal
from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import engine, Base, get_db
from models import TransactionDB, UserDB, BudgetDB
from schemas import (
    Transaction, TransactionResponse, UserCreate, UserResponse, Token,
    BudgetCreate, BudgetResponse,
)
from auth import hash_password, verify_password, create_access_token, get_current_user
import os

limiter = Limiter(
    key_func=get_remote_address,
    enabled=os.getenv("TESTING") != "1",
)
app = FastAPI(
    title="Personal Finance API",
    description="A personal finance API with authentication, transactions, summaries, category reports, and monthly budgets.",
    version="1.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    _rate_limit_exceeded_handler,
)
# Create new tables and safely add the date column to an existing SQLite database.
Base.metadata.create_all(bind=engine)
if engine.dialect.name == "sqlite":
    with engine.begin() as connection:
        existing_tables = set(inspect(connection).get_table_names())
        if "transactions" in existing_tables:
            columns = {column["name"] for column in inspect(connection).get_columns("transactions")}
            if "user_id" not in columns:
                connection.execute(text(
                    "ALTER TABLE transactions ADD COLUMN user_id INTEGER REFERENCES users(id)"
                ))
            if "transaction_date" not in columns:
                connection.execute(text("ALTER TABLE transactions ADD COLUMN transaction_date DATE"))

def validate_month(month: str | None) -> str | None:
    if month is None:
        return None
    try:
        date.fromisoformat(f"{month}-01")
    except ValueError:
        raise HTTPException(status_code=422, detail="month must use YYYY-MM format")
    if len(month) != 7 or month[4] != "-":
        raise HTTPException(status_code=422, detail="month must use YYYY-MM format")
    return month

def month_filter(query, month: str | None):
    if month:
        query = query.filter(func.strftime("%Y-%m", TransactionDB.transaction_date) == month)
    return query

@app.get("/")
def home():
    return {"message": "Personal Finance API is running!", "version": "1.0.0"}

@app.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, db: Session = Depends(get_db)):
    email = str(user_data.email).strip().lower()
    user = UserDB(email=email, hashed_password=hash_password(user_data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Email is already registered")
    db.refresh(user)
    return user

@app.post("/token", response_model=Token)
@app.post("/login")
@limiter.limit("5/minute")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = form_data.username.strip().lower()
    user = db.query(UserDB).filter(UserDB.email == email).first()
    if (
        not user
        or len(form_data.password) > 128
        or not verify_password(form_data.password, user.hashed_password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "access_token": create_access_token(user_id=user.id),
        "token_type": "bearer",
    }

@app.get("/me", response_model=UserResponse)
def read_me(current_user: UserDB = Depends(get_current_user)):
    return current_user

@app.post("/transactions", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
def create_transaction(
    transaction: Transaction,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    record = TransactionDB(
        amount=transaction.amount,
        type=transaction.type,
        category=transaction.category,
        description=transaction.description,
        transaction_date=transaction.transaction_date,
        user_id=current_user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record

@app.get("/transactions", response_model=list[TransactionResponse])
def get_transactions(
    transaction_type: Literal["income", "expense"] | None = None,
    category: str | None = Query(default=None, min_length=1, max_length=50),
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    query = db.query(TransactionDB).filter(TransactionDB.user_id == current_user.id)
    if transaction_type is not None:
        query = query.filter(TransactionDB.type == transaction_type)
    if category is not None:
        query = query.filter(func.lower(TransactionDB.category) == category.strip().lower())
    query = month_filter(query, validate_month(month))
    return query.order_by(TransactionDB.transaction_date.desc(), TransactionDB.id.desc()).offset(offset).limit(limit).all()

@app.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    record = db.query(TransactionDB).filter(
        TransactionDB.id == transaction_id,
        TransactionDB.user_id == current_user.id,
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return record

@app.put("/transactions/{transaction_id}", response_model=TransactionResponse)
def update_transaction(
    transaction_id: int,
    updated_data: Transaction,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    record = db.query(TransactionDB).filter(
        TransactionDB.id == transaction_id,
        TransactionDB.user_id == current_user.id,
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    record.amount = updated_data.amount
    record.type = updated_data.type
    record.category = updated_data.category
    record.description = updated_data.description
    record.transaction_date = updated_data.transaction_date
    db.commit()
    db.refresh(record)
    return record

@app.delete("/transactions/{transaction_id}")
def delete_transaction(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    record = db.query(TransactionDB).filter(
        TransactionDB.id == transaction_id,
        TransactionDB.user_id == current_user.id,
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(record)
    db.commit()
    return {"message": "Transaction deleted successfully", "id": transaction_id}

@app.get("/summary")
def get_summary(
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    month = validate_month(month)
    query = db.query(TransactionDB).filter(TransactionDB.user_id == current_user.id)
    query = month_filter(query, month)
    income = query.filter(TransactionDB.type == "income").with_entities(func.sum(TransactionDB.amount)).scalar() or 0
    expenses = query.filter(TransactionDB.type == "expense").with_entities(func.sum(TransactionDB.amount)).scalar() or 0
    return {
        "month": month,
        "total_income": round(float(income), 2),
        "total_expenses": round(float(expenses), 2),
        "balance": round(float(income - expenses), 2),
    }

@app.get("/reports/categories")
def category_report(
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    month = validate_month(month)
    query = db.query(
        TransactionDB.type,
        TransactionDB.category,
        func.sum(TransactionDB.amount).label("total"),
    ).filter(TransactionDB.user_id == current_user.id)
    query = month_filter(query, month)
    rows = query.group_by(TransactionDB.type, TransactionDB.category).order_by(TransactionDB.type, TransactionDB.category).all()
    return {
        "month": month,
        "categories": [
            {"type": row.type, "category": row.category, "total": round(float(row.total or 0), 2)}
            for row in rows
        ],
    }

@app.post("/budgets", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
def create_budget(
    budget_data: BudgetCreate,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    budget = BudgetDB(
        user_id=current_user.id,
        category=budget_data.category,
        monthly_limit=budget_data.monthly_limit,
        month=budget_data.month,
    )
    db.add(budget)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A budget already exists for this category and month")
    db.refresh(budget)
    return budget

@app.get("/budgets", response_model=list[BudgetResponse])
def get_budgets(
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    query = db.query(BudgetDB).filter(BudgetDB.user_id == current_user.id)
    if month:
        query = query.filter(BudgetDB.month == month)
    return query.order_by(BudgetDB.month.desc(), BudgetDB.category).all()

@app.get("/budgets/status")
def get_budget_status(
    month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    budgets = db.query(BudgetDB).filter(
        BudgetDB.user_id == current_user.id,
        BudgetDB.month == month,
    ).order_by(BudgetDB.category).all()
    result = []
    for budget in budgets:
        spent = db.query(func.sum(TransactionDB.amount)).filter(
            TransactionDB.user_id == current_user.id,
            TransactionDB.type == "expense",
            func.lower(TransactionDB.category) == budget.category.lower(),
            func.strftime("%Y-%m", TransactionDB.transaction_date) == month,
        ).scalar() or 0
        spent = round(float(spent), 2)
        remaining = round(budget.monthly_limit - spent, 2)
        result.append({
            "id": budget.id,
            "category": budget.category,
            "month": budget.month,
            "monthly_limit": round(budget.monthly_limit, 2),
            "spent": spent,
            "remaining": remaining,
            "percent_used": round((spent / budget.monthly_limit) * 100, 2),
            "over_budget": spent > budget.monthly_limit,
        })
    return {"month": month, "budgets": result}

@app.delete("/budgets/{budget_id}")
def delete_budget(
    budget_id: int,
    db: Session = Depends(get_db),
    current_user: UserDB = Depends(get_current_user),
):
    budget = db.query(BudgetDB).filter(
        BudgetDB.id == budget_id,
        BudgetDB.user_id == current_user.id,
    ).first()
    if budget is None:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.delete(budget)
    db.commit()
    return {"message": "Budget deleted successfully", "id": budget_id}
