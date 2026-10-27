 Personal Finance API

A FastAPI portfolio project with JWT authentication, per-user transaction isolation, validation, transaction filtering, monthly summaries, category reports, and monthly spending budgets.

Features

- Register and log in with hashed passwords (Argon2 through `pwdlib`)
- JWT access tokens with a 30-minute expiry
- Protected endpoints; users can only access their own transactions and budgets
- Create, list, view, update, and delete transactions
- Transaction date, type/category filters, month filters, and pagination
- Overall and month-specific income, expense, and balance summaries
- Grouped category report
- Create/list/delete monthly budgets and check spend/remaining/over-budget status
- Input validation for amounts, category/description length, blank text, dates, and month format
- Tests using an isolated in-memory SQLite database
Setup (Windows PowerShell)

Open PowerShell in the project directory and activate your existing virtual environment:

powershell
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

If PowerShell blocks activation, run this once for your current Windows user, then open a new terminal:

powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser


Secret key

For development, `auth.py` generates a temporary secret if `FINANCE_API_SECRET_KEY` is not set. This means tokens become invalid when the server restarts. Set a stable secret for your local session:

```powershell
$env:FINANCE_API_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
```

For production, set `ENVIRONMENT=production` and configure `FINANCE_API_SECRET_KEY` through your hosting provider's secret manager. Never commit a real secret to GitHub. This project is portfolio/demo quality and should receive a deployment review before handling real financial data.

Run the API

```powershell
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/docs` to try the endpoints. Use `POST /register`, then `POST /token` with form fields `username` (your email) and `password`. Click Authorize in Swagger UI and enter the bearer token if needed.

Run tests

powershell
python -m pytest -v


Endpoint overview

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/` | Health/message |
| POST | `/register` | Register account |
| POST | `/token` | Log in and get JWT |
| GET | `/me` | Current user |
| POST | `/transactions` | Create transaction |
| GET | `/transactions` | List/filter/paginate transactions |
| GET | `/transactions/{id}` | Get one owned transaction |
| PUT | `/transactions/{id}` | Replace an owned transaction |
| DELETE | `/transactions/{id}` | Delete an owned transaction |
| GET | `/summary` | Overall or `?month=YYYY-MM` totals |
| GET | `/reports/categories` | Income/expense totals grouped by category |
| POST | `/budgets` | Create a monthly category budget |
| GET | `/budgets` | List budgets, optionally `?month=YYYY-MM` |
| GET | `/budgets/status?month=YYYY-MM` | Spending vs budget |
| DELETE | `/budgets/{id}` | Delete an owned budget |

Example transaction

```json
{
  "amount": 125.50,
  "type": "expense",
  "category": "Food",
  "description": "Lunch",
  "transaction_date": "2026-10-26"
}
```

Existing database note

The app adds the `transaction_date` column to an existing SQLite `transactions` table without deleting existing data. Historical rows may have a null date and won't be included in month-specific reports until updated. Back up `finance.db` before changing project versions.

## Important limitations

- `Float` is retained for compatibility with the current database. For production accounting, use decimal-safe storage and formal database migrations.
- No password reset, email verification, rate limiting, refresh tokens, or deployment-specific HTTPS configuration is included.
- The SQLite date functions used in reports are intended for the included SQLite setup.
