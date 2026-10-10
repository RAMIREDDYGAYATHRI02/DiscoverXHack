# ShiftSwap — CityCare Clinic Shift Management System

A responsive shift exchange dashboard for the CityCare Clinic roster. Staff can post a shift, review and claim eligible open listings, or release a pending claim. Managers can review requests, recheck the roster rules, and approve or reject. A shared activity history records completed actions and rule-based claim refusals.

## Stack

- React 18 and Vite frontend
- Django 4.2 and Django REST Framework API
- MongoDB persistence through PyMongo
- The checked-in `seed.json` is the source of the original 10 staff and 61 shifts

The backend stores the roster, listings, and history in one MongoDB document. Updates use an atomic compare-and-set revision, so simultaneous claims or manager actions retry against the latest roster state. `python manage.py seed_data` initializes the document with `$setOnInsert`; running it again never replaces an existing roster or user changes.

## Run locally

Requirements: Python 3.10+, Node.js 18+, and MongoDB (local or Atlas).

1. Create a virtual environment and install backend requirements:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set a MongoDB connection string. For Atlas, create a database user and allow the development machine's IP in Atlas Network Access. Keep `.env` private; it is ignored by Git.

   ```powershell
   Copy-Item .env.example .env
   ```

3. Initialize the roster once and start the API:

   ```powershell
   python manage.py seed_data
   python manage.py runserver 127.0.0.1:8000
   ```

4. In another terminal, install frontend dependencies and start Vite:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

Open `http://localhost:5173`. Vite forwards `/api` requests to Django. The Django root (`http://localhost:8000/`) redirects to the frontend; the API is also available at `http://localhost:8000/api/state`. Set `FRONTEND_URL` to the deployed frontend URL in production. The Django bind address (`127.0.0.1:8000`) is for the API; do not enter `0.0.0.0:8000` in the browser. Choose an existing person on the role-selection page; no login is used. The top-right selector can switch between seeded staff and managers.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `MONGODB_URI` | Local MongoDB URI or Atlas connection string; credentials belong here, never in source code |
| `MONGODB_DATABASE` | Database name, defaults to `shiftswap` |
| `DJANGO_SECRET_KEY` | Django secret for deployment |
| `DJANGO_DEBUG` | `true` for local development; set `false` in production |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated Django hostnames; include the deployed API hostname(s) |
| `CORS_ALLOWED_ORIGINS` | Comma-separated browser origins allowed to call the API |
| `FRONTEND_URL` | Optional destination for the Django root redirect; defaults to the local Vite URL and is not needed for Vercel Services routing |

## REST API

All routes use the `/api` prefix and return JSON. The app uses an actor ID in action requests because this exercise has profile selection but no authentication.

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/state` | Full roster, listings, and action history |
| `GET` | `/api/staff` | Seeded staff and managers |
| `GET` | `/api/shifts` | Current assignments |
| `GET` | `/api/listings` | Listing lifecycle records |
| `GET` | `/api/history` | Shared action history |
| `POST` | `/api/listings` | Post a shift; body includes `actor_id` and `shift_id` |
| `POST` | `/api/listings/{id}/claim` | Claim an open listing; body includes `actor_id` |
| `POST` | `/api/listings/{id}/unclaim` | Release a claim; body includes `actor_id` |
| `POST` | `/api/listings/{id}/withdraw` | Withdraw an open listing; body includes `actor_id` |
| `POST` | `/api/listings/{id}/approve` | Approve a claim; body includes `actor_id` |
| `POST` | `/api/listings/{id}/reject` | Reject a claim; body includes `actor_id` |
| `POST` | `/api/actions` | Validated state transition |

Action body examples:

```json
{"actor_id":"S2","action":"POST","shift_id":"SH001"}
{"actor_id":"S7","action":"CLAIM","listing_id":"<listing-id>"}
{"actor_id":"M1","action":"APPROVE","listing_id":"<listing-id>"}
```

Actions are `POST`, `WITHDRAW`, `CLAIM`, `UNCLAIM`, `APPROVE`, and `REJECT`. A stale claim returns HTTP 409 and the exact message `no longer available` without calculating other claim rules. Rule failures include every relevant violation in `violations` and are written to history. Managers' approvals recheck the claimer's current assignments; a failed approval leaves the listing `CLAIMED`.

The clinic's timestamp strings are timezone-free local wall time. Calculations use UTC as a timezone-neutral arithmetic representation; the browser and machine timezone do not change overlap, rest, or week calculations. A week starts Monday at 00:00, and shifts belong to the week in which they start. All shifts are considered upcoming.

## Tests and build

Backend tests use Django's runner and an in-memory MongoDB-compatible test collection:

```powershell
python manage.py test
```

Build the frontend:

```powershell
cd frontend
npm run build
```

## Deployment

### Vercel Services (single deployment and domain)

The root `vercel.json` defines two services. Set the Vercel project Framework Preset to **Services** and keep the repository root as the project root. Vercel Services availability is controlled by the current Vercel account/feature access.

| Service | Root | Entrypoint | Public routing |
| --- | --- | --- | --- |
| `app` | `.` | `shiftswap_project.wsgi:application` | `/api/...` |
| `frontend` | `frontend` | Vite auto-detected | `/` and all non-API paths |

The `/api/(.*)` rewrite is intentionally before the frontend catch-all. Both services have public paths; there are no internal-only services and no service bindings. The browser uses relative `/api/...` requests, so it stays on the shared deployment origin and does not need a cross-service binding or `VITE_API_BASE_URL`.

Configure these variables for the Django `app` service only (never expose them as `VITE_` variables):

| Variable | Required value |
| --- | --- |
| `DJANGO_SECRET_KEY` | A new, long random production secret |
| `DJANGO_DEBUG` | `false` |
| `DJANGO_ALLOWED_HOSTS` | The assigned Vercel deployment hostname(s), plus any custom domain(s) |
| `MONGODB_URI` | MongoDB Atlas connection URI for a dedicated database user |
| `MONGODB_DATABASE` | Production database name (for example `shiftswap`) |

The app uses a same-origin API on Vercel, so `CORS_ALLOWED_ORIGINS` is not required for this deployment. It remains available for local development or an independently hosted frontend. Do not seed on every request or build; run `python manage.py seed_data` only when intentionally initializing an empty production database, using a controlled one-off environment with Atlas access.

The `frontend` service needs no environment variables for same-domain API requests. Do not add MongoDB credentials, Django secrets, or any other server-only variables to Vercel frontend build variables. For a separately hosted backend, set `VITE_API_BASE_URL` to its public origin as a frontend build variable and configure the backend CORS origin accordingly.

### Separate Netlify frontend and Render backend

- **Netlify frontend:** set the base directory to `frontend`, build with `npm run build`, and publish `dist`. Set `VITE_API_BASE_URL` to the public Render API origin as a Netlify build variable.
- **Render backend:** deploy the repository as a Python web service, install `requirements.txt`, and run `gunicorn shiftswap_project.wsgi:application --bind 0.0.0.0:$PORT`. Configure `MONGODB_URI`, `MONGODB_DATABASE`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=false`, `DJANGO_ALLOWED_HOSTS`, and `CORS_ALLOWED_ORIGINS` in Render's environment settings. Run `python manage.py seed_data` once after the service can reach MongoDB. Use MongoDB Atlas with a narrow network allowlist and a dedicated database user.

## Assumptions and limitations

- The only identity control is selecting a seeded profile, as specified; it is not authentication.
- The backend keeps a single clinic state document to make related roster, listing, and history changes atomic. This is appropriate for the supplied clinic roster and avoids multi-document transaction requirements.
- Shift checks never compare against the real current date/time. History timestamps reflect when actions were recorded.
- A separate production hosting configuration and live Atlas credentials were not supplied. Deployment requires those account-specific values and a configured production API URL.
