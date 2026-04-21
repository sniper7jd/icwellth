# WealthManager (Air-Gapped Expense Logger)

WealthManager is a production-ready, multi-user Expense Logger and Dashboard designed for fully air-gapped environments.

## Air-Gapped Design Principles

- No internet dependency at runtime.
- No external CDNs, web fonts, or third-party APIs.
- Static frontend assets are local in `static/`.
- Backend is JSON-only FastAPI and can run behind Nginx load balancing.
- Persistent export files are written only to the SAN mount path via `SAN_MOUNT_PATH`.

## Architecture

- **Backend:** FastAPI + Uvicorn (`main.py`)
- **Database:** PostgreSQL only (SQLite is explicitly blocked)
- **ORM:** SQLAlchemy with connection pooling
- **Auth:** Stateless JWT (OAuth2 password flow)
- **Frontend:** Decoupled offline vanilla HTML/CSS/JS (`static/`)

## Data Model

- `User`: `id`, `username`, `email`, `hashed_password`, `created_at`
- `Category`: `id`, `name`
- `Expense`: `id`, `user_id`, `category_id`, `amount`, `date`, `description`, `created_at`

## API Endpoints

### Public

- `GET /health`
- `GET /`
- `POST /register`
- `POST /token`

### Authenticated (Bearer JWT required)

- `GET /users/me`
- `GET /categories`
- `GET /expenses`
- `POST /expenses`
- `DELETE /expenses/{expense_id}`
- `GET /expenses/summary`
- `POST /expenses/export` (writes CSV to SAN path)

## Required Environment Variables

- `DATABASE_URL`  
  Must be PostgreSQL, for example:  
  `postgresql+psycopg2://wm_user:wm_pass@127.0.0.1:5432/wealthmanager`
- `JWT_SECRET_KEY`
- `SAN_MOUNT_PATH` (absolute path on SAN mount)

Optional:

- `DB_POOL_SIZE` (default: `20`)
- `DB_MAX_OVERFLOW` (default: `40`)
- `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` (default: `60`)
- `CORS_ALLOW_ORIGINS` (default: `http://127.0.0.1:8080,http://localhost:8080`)

## Local Run (Air-Gapped Friendly)

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run backend:

```bash
SAN_MOUNT_PATH="/absolute/san/mount/path" \
JWT_SECRET_KEY="replace-with-strong-secret" \
DATABASE_URL="postgresql+psycopg2://wm_user:wm_pass@127.0.0.1:5432/wealthmanager" \
python -m uvicorn main:app --host 0.0.0.0 --port 8001
```

Run frontend:

```bash
cd static
python3 -m http.server 8080
```

Then open `http://127.0.0.1:8080` and set API base URL to `http://127.0.0.1:8001`.

## Load-Balanced Deployment Notes

- App is stateless; JWT auth works across multiple backend VMs behind Nginx.
- Do not store auth/session state in memory.
- All VMs should use identical pinned dependencies from `requirements.txt`.
- SAN exports are path-restricted by server logic to `SAN_MOUNT_PATH`.

## Security Notes

- `username` and `email` are protected by PostgreSQL unique constraints.
- Registration collisions are handled by `IntegrityError` and returned as HTTP 400.
- Passwords are hashed with `passlib[bcrypt]`.
