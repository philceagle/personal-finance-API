 Pytest and authentication setup

1. Stop the server and back up `finance.db` outside the project folder.
2. Copy these updated files into your existing `financing` folder: `main.py`, `models.py`, `schemas.py`, `database.py`, `auth.py`, and `requirements.txt`. Copy the `tests` folder too.
3. Activate your existing venv, then run:

   `python -m pip install -r requirements.txt`

4. For local development, set a secret in PowerShell before starting the server:

   `$env:FINANCE_API_SECRET_KEY = "replace-with-a-long-random-local-secret"`

   Never commit real secrets to GitHub.
5. Run `fastapi dev main.py` and open `http://127.0.0.1:8000/docs`.
6. Register at `POST /register`. Log in at `POST /token` using your email in the `username` field and your password. Use **Authorize** in Swagger UI to use the returned bearer token.
7. Run automated tests with `python -m pytest -v`.

The app adds a `user_id` column to an existing SQLite database on startup. Existing transactions are retained but are unassigned, so authenticated users will not see them. New transactions belong to the logged-in user. Tests use a separate in-memory database, not `finance.db`.

This is a learning project, not production-ready financial software. Before deployment, use a strong secret outside source control, HTTPS, rate limiting, reviewed security practices, and a proper database migration system.
