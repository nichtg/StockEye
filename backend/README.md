# StockEye backend

FastAPI + MongoDB API for macro and technical analysis of US and SGX stocks. Python 3.13, managed with [uv](https://docs.astral.sh/uv/).

## Setup

```bash
cd backend
uv sync                      # installs runtime and dev dependencies into .venv
cp .env.example .env         # then edit; see the comments in the file
```

The FinBERT sentiment model is not committed. Fetch it once with `uv run python scripts/download_finbert.py` (this script is delivered by a separate task and may not exist yet on your branch).

## MongoDB

Local, for example with Docker:

```bash
docker run -d --name stockeye-mongo -p 27017:27017 mongo:8
```

The default `STOCKEYE_MONGODB_URI=mongodb://127.0.0.1:27017` then works. To use Atlas instead, set `STOCKEYE_MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>/` and allow your IP in Atlas. Indexes are created automatically at startup.

## Create the first admin

Registration only ever creates regular users. Create an admin from the command line:

```bash
uv run python -m app.cli create-admin --email you@example.com
```

The password is read from `STOCKEYE_ADMIN_PASSWORD` if set, otherwise you are prompted. It must follow the password policy (12-128 characters, not blank, not your email). If the email already exists, that user is promoted to admin.

## Run the API

```bash
uv run uvicorn app.main:create_app --factory --reload
```

Interactive docs are at http://127.0.0.1:8000/docs. All routes live under `/api`. For plain-http local development set `STOCKEYE_COOKIE_SECURE=false`, otherwise browsers drop the auth cookies.

### Auth model

- Cookies: `se_access` (JWT, httpOnly), `se_refresh` (httpOnly, scoped to `/api/auth`, rotated on every use; reuse revokes the whole token family) and `se_csrf` (readable by the SPA).
- Every POST/PUT/PATCH/DELETE must send `X-CSRF-Token` equal to the `se_csrf` cookie. Call `GET /api/auth/csrf` first.
- The user is re-read from the database on every request, so disabling a user or changing a role takes effect immediately.
- Errors always look like `{"error": {"code", "message", "request_id", "details"}}`.

## Tests and quality gates

Integration tests need MongoDB (they skip if it is unreachable; set `STOCKEYE_MONGODB_URI` to point elsewhere). Each test uses its own throwaway database.

```bash
uv run pytest --cov --cov-report=term-missing
uv run ruff check app tests
uv run ruff format --check app tests
uv run mypy app
uv run lint-imports          # architecture contracts (layering, admin cannot reach watchlists)
```
