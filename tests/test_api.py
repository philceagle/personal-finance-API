import os

os.environ["TESTING"] = "1"
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=test_engine)

def register_and_login(client, email="test@example.com", password="safe-password-123"):
    response = client.post("/register", json={"email": email, "password": password})
    assert response.status_code == 201
    response = client.post("/token", data={"username": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

def test_register_login_and_me(client):
    headers = register_and_login(client)
    response = client.get("/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"

def test_duplicate_email_rejected(client):
    register_and_login(client)
    response = client.post("/register", json={
        "email": "test@example.com", "password": "another-password-123"
    })
    assert response.status_code == 409

def test_transaction_crud_and_summary(client):
    headers = register_and_login(client)
    created = client.post("/transactions", json={
        "amount": 5000, "type": "income", "category": "Salary", "description": "Pay",
        "transaction_date": "2026-10-01",
    }, headers=headers)
    assert created.status_code == 201
    tid = created.json()["id"]
    assert len(client.get("/transactions", headers=headers).json()) == 1
    updated = client.put(f"/transactions/{tid}", json={
        "amount": 450, "type": "expense", "category": "Food", "description": "Lunch",
        "transaction_date": "2026-10-02",
    }, headers=headers)
    assert updated.status_code == 200
    assert client.get("/summary", headers=headers).json() == {
        "month": None, "total_income": 0.0, "total_expenses": 450.0, "balance": -450.0
    }
    assert client.delete(f"/transactions/{tid}", headers=headers).status_code == 200
    assert client.get("/transactions", headers=headers).json() == []

def test_transactions_require_authentication(client):
    assert client.get("/transactions").status_code == 401

def test_users_cannot_access_each_others_transactions(client):
    a = register_and_login(client, "a@example.com")
    b = register_and_login(client, "b@example.com")
    created = client.post("/transactions", json={
        "amount": 100, "type": "expense", "category": "Food", "description": "Private"
    }, headers=a)
    tid = created.json()["id"]
    assert client.get("/transactions", headers=b).json() == []
    assert client.get(f"/transactions/{tid}", headers=b).status_code == 404

def test_invalid_transaction_is_rejected(client):
    headers = register_and_login(client)
    response = client.post("/transactions", json={
        "amount": -10, "type": "banana", "category": "Food", "description": "Invalid"
    }, headers=headers)
    assert response.status_code == 422

def test_wrong_password_returns_generic_error(client):
    client.post("/register", json={
        "email": "security@example.com", "password": "correct-password-123"
    })
    response = client.post("/token", data={
        "username": "security@example.com", "password": "wrong-password-123"
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"

def test_unknown_email_returns_same_login_error(client):
    response = client.post("/token", data={
        "username": "unknown@example.com", "password": "wrong-password-123"
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_nan_and_infinite_amounts_rejected(client):
    headers = register_and_login(client)

    for amount in ["NaN", "Infinity", "-Infinity"]:
        response = client.post(
            "/transactions",
            json={
                "amount": amount,
                "type": "expense",
                "category": "Food",
                "description": "bad",
            },
            headers=headers,
        )

        assert response.status_code == 422


def test_transaction_text_is_trimmed_and_blank_rejected(client):
    headers = register_and_login(client)
    ok = client.post("/transactions", json={
        "amount": 5, "type": "expense", "category": " Food ", "description": " snack "
    }, headers=headers)
    assert ok.status_code == 201
    assert ok.json()["category"] == "Food"
    bad = client.post("/transactions", json={
        "amount": 5, "type": "expense", "category": "   ", "description": "snack"
    }, headers=headers)
    assert bad.status_code == 422

def test_transaction_filters_pagination_and_monthly_summary(client):
    headers = register_and_login(client)
    client.post("/transactions", json={
        "amount": 3000, "type": "income", "category": "Salary", "description": "Pay",
        "transaction_date": "2026-10-01",
    }, headers=headers)
    client.post("/transactions", json={
        "amount": 250, "type": "expense", "category": "Food", "description": "Lunch",
        "transaction_date": "2026-10-02",
    }, headers=headers)
    client.post("/transactions", json={
        "amount": 100, "type": "expense", "category": "Food", "description": "Snack",
        "transaction_date": "2026-09-30",
    }, headers=headers)
    assert len(client.get("/transactions?month=2026-10&limit=1", headers=headers).json()) == 1
    assert len(client.get("/transactions?category=food", headers=headers).json()) == 2
    assert client.get("/summary?month=2026-10", headers=headers).json() == {
        "month": "2026-10", "total_income": 3000.0, "total_expenses": 250.0, "balance": 2750.0
    }

def test_category_report(client):
    headers = register_and_login(client)
    client.post("/transactions", json={
        "amount": 75, "type": "expense", "category": "Food", "description": "Lunch",
        "transaction_date": "2026-10-01",
    }, headers=headers)
    result = client.get("/reports/categories?month=2026-10", headers=headers).json()
    assert result["categories"] == [{"type": "expense", "category": "Food", "total": 75.0}]

def test_budget_create_status_and_delete(client):
    headers = register_and_login(client)
    response = client.post("/budgets", json={
        "category": "Food", "monthly_limit": 200, "month": "2026-10"
    }, headers=headers)
    assert response.status_code == 201
    client.post("/transactions", json={
        "amount": 75, "type": "expense", "category": "food", "description": "Lunch",
        "transaction_date": "2026-10-04",
    }, headers=headers)
    status_response = client.get("/budgets/status?month=2026-10", headers=headers)
    item = status_response.json()["budgets"][0]
    assert item["spent"] == 75
    assert item["remaining"] == 125
    assert item["over_budget"] is False
    duplicate = client.post("/budgets", json={
        "category": "Food", "monthly_limit": 300, "month": "2026-10"
    }, headers=headers)
    assert duplicate.status_code == 409
    assert client.delete(f"/budgets/{response.json()['id']}", headers=headers).status_code == 200

def test_budget_data_is_private(client):
    a = register_and_login(client, "a@example.com")
    b = register_and_login(client, "b@example.com")
    created = client.post("/budgets", json={
        "category": "Food", "monthly_limit": 200, "month": "2026-10"
    }, headers=a)
    assert client.get("/budgets", headers=b).json() == []
    assert client.delete(f"/budgets/{created.json()['id']}", headers=b).status_code == 404
