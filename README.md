# CyberSec Pipeline

Automated cybersecurity reconnaissance and vulnerability assessment platform. FastAPI backend orchestrates open-source security tools running in Docker containers via Celery task queue. React frontend provides a real-time dashboard with WebSocket-driven live scan progress.

## Architecture

```
Browser (React + TypeScript + Tailwind)
    |
    +--> Nginx (port 80)
           |
           +--> /api/v1/*  --> FastAPI Backend (port 8000)
           +--> /ws/*      --> WebSocket (scan events)
           +--> /*         --> Static frontend files
                                  |
                            Celery Workers (concurrency=4) --> Docker SDK --> Tool Containers
                                  |                                               |
                            PostgreSQL                                   Shared Volume (/results)
                            Redis (broker + pub/sub)
```

### Scan Pipeline

Scans run through 4 sequential phases:

| Phase | Tools | Purpose |
|-------|-------|---------|
| 1. Recon | theHarvester, Amass, dnsx | Subdomain enumeration, DNS resolution |
| 2. Network | Masscan, Nmap, httpx | Port scanning, service detection, HTTP probing |
| 3. VulnScan | Nuclei, ZAP | Vulnerability scanning, web app testing |
| 4. Report | DefectDojo | Findings aggregation, export |

### Real-time State Management

The scan detail page stays accurate across navigation, hard refreshes, and reconnects through a two-layer approach:

**DB persistence (source of truth):** Tool statuses are written to `scan_phases.tool_statuses` on every `tool_started / tool_completed / tool_error / tool_skipped` event — not only at phase completion. A `GET /scans/{id}` therefore always returns the live state of the running phase, so a page load or refresh shows correct tool statuses with no WebSocket history needed.

**Redis live state snapshot (fast reconnect + logs):** Every event also updates a `scan_live_state:{scan_id}` Redis key containing `current_phase`, `phase_statuses`, `tool_statuses`, and a rolling 200-line log buffer. When a WebSocket client connects (including after navigating away and back), the server sends a `state_snapshot` event before starting the pub/sub stream. The frontend merges this snapshot into its local state so tools and logs are populated immediately without waiting for new pipeline events.

**Worker startup cleanup:** On startup the Celery worker queries for any scans left in `running` or `pending` state and marks them `failed`. This prevents zombie scans — scans whose pipeline was killed by a worker restart falling outside the Redis 1-hour visibility timeout. Users can then retry those scans.

## Tech Stack

**Backend:** Python 3.12, FastAPI, Celery 5, SQLAlchemy 2 (async), PostgreSQL 16, Redis 7, Alembic

**Frontend:** React 18, TypeScript, Vite, Tailwind CSS, TanStack React Query, Recharts, Lucide Icons

**Infrastructure:** Docker Compose (21 services), Nginx reverse proxy

## Quick Start

### 1. Clone

```bash
git clone https://github.com/sm-coding-projects/cybersec_pipeline.git
cd cybersec_pipeline
```

### 2. Start with Docker Compose

```bash
docker compose up -d --build
```

Built-in defaults cover all required environment variables, so no `.env` file is needed to get started. This brings up 21 services: nginx, FastAPI backend, Celery worker/beat, frontend builder, PostgreSQL, Redis, 7 security tool containers, DefectDojo stack, and Grafana.

> **For production:** copy `.env.example` to `.env` and replace every `changeme_*` value with strong, unique secrets before deployment.

### 3. Run database migrations

```bash
docker exec backend alembic upgrade head
```

### 4. Bootstrap DefectDojo (first run only)

DefectDojo does not auto-migrate on first start. Run the provided script once:

```bash
bash scripts/init-defectdojo.sh
```

The script waits for the database, runs Django migrations, creates an admin user (`admin` / `admin`), creates the default product type, and prints the API token.

Copy the printed token into your `.env`:

```
DEFECTDOJO_API_KEY=<token printed by the script>
```

Then restart the backend and worker:

```bash
docker compose up -d backend celery-worker
```

> To set a custom admin password: `DD_ADMIN_PASSWORD=yourpassword bash scripts/init-defectdojo.sh`

### 5. Access the application

| Service | URL | Notes |
|---------|-----|-------|
| Web App | http://localhost | Main dashboard |
| API Docs | http://localhost/api/docs | Interactive Swagger UI |
| Grafana | http://localhost:3000 | Metrics and dashboards |

Register a user account at the login page. The first registered user is automatically an admin.

> **Note:** DefectDojo and ZAP are internal services with no host-level port mappings. They communicate with the backend over the internal Docker network only.

## Development Setup

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In a separate terminal:

```bash
celery -A app.tasks.celery_app worker --loglevel=info
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server runs on http://localhost:5173 and proxies `/api` and `/ws` requests to the backend at localhost:8000.

### Database Migrations

```bash
cd backend
alembic upgrade head                              # Apply migrations
alembic revision --autogenerate -m "description"  # Generate new migration
```

## API Endpoints

All REST endpoints are under `/api/v1` and require JWT authentication (except register/login).

| Group | Endpoints | Description |
|-------|-----------|-------------|
| Auth | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | User registration and JWT authentication |
| Scans | `POST /scans`, `GET /scans`, `GET /scans/{id}`, `DELETE /scans/{id}` | Create, list, view, cancel/delete scans |
| Scans | `POST /scans/{id}/retry`, `GET /scans/{id}/logs`, `GET /scans/{id}/export` | Retry failed scans, view logs, export ZIP |
| Targets | `GET /scans/{id}/targets`, `GET /scans/{id}/targets/stats` | Discovered assets per scan |
| Findings | `GET /findings`, `GET /findings/{id}`, `PATCH /findings/{id}` | Browse and update vulnerability findings |
| Findings | `GET /scans/{id}/findings`, `GET /findings/export` | Per-scan findings, CSV export |
| Dashboard | `GET /dashboard/stats`, `GET /dashboard/severity-breakdown` | Aggregate statistics and charts |
| Tools | `GET /tools/status`, `POST /tools/{name}/test` | Container health monitoring |
| WebSocket | `WS /ws/scans/{scan_id}` | Real-time scan progress events |

## Project Structure

```
cybersec-workflow/
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI route handlers
│   │   ├── core/             # Auth, WebSocket manager, exceptions
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   ├── pipeline/         # Scan engine, phase functions, parsers
│   │   ├── services/         # DockerManager, DefectDojo client
│   │   └── tasks/            # Celery task definitions
│   ├── alembic/              # Database migrations
│   └── tests/                # pytest test suite
├── frontend/
│   └── src/
│       ├── api/              # Axios client + React Query hooks
│       ├── components/       # UI components (layout, scans, findings, dashboard)
│       ├── hooks/            # useAuth, useWebSocket
│       ├── pages/            # Dashboard, ScanDetail, Findings, etc.
│       ├── types/            # TypeScript type definitions
│       └── utils/            # Formatters, constants
├── containers/               # Custom Dockerfiles (theHarvester, nmap-scanner)
├── docker-compose.yml        # Full stack (21 services)
└── ARCHITECTURE.md           # Complete technical blueprint
```

## Testing

```bash
cd backend
pytest                             # All tests
pytest tests/test_parsers/ -v      # Parser tests only
pytest tests/test_api/ -v          # API endpoint tests
pytest tests/test_pipeline/ -v     # Pipeline engine tests
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DB_PASSWORD` | Yes | PostgreSQL password for app database |
| `JWT_SECRET_KEY` | Yes | Secret for JWT token signing (min 32 chars) |
| `DEFECTDOJO_API_KEY` | Yes | DefectDojo API token (obtained during first-run bootstrap) |
| `DD_DATABASE_PASSWORD` | Yes | PostgreSQL password for DefectDojo |
| `DD_SECRET_KEY` | Yes | Django secret key for DefectDojo |
| `DD_CREDENTIAL_AES_256_KEY` | Yes | AES key for DefectDojo credentials |
| `GF_SECURITY_ADMIN_PASSWORD` | Yes | Grafana admin password |
| `SHODAN_API_KEY` | No | Improves recon coverage |
| `CENSYS_API_ID` / `CENSYS_API_SECRET` | No | Improves recon coverage |
| `VIRUSTOTAL_API_KEY` | No | Improves recon coverage |

## Known Limitations

**Masscan on macOS Docker Desktop:** Masscan sends SYN packets but receives no responses. Raw socket SYN-ACK replies do not route back through the macOS VM network stack. The pipeline falls back to Nmap automatically. Masscan works normally on Linux hosts.

**OpenVAS disabled:** The OpenVAS/Greenbone services are commented out in `docker-compose.yml`. Their images are hosted on GitHub Container Registry (`ghcr.io/greenbone/`) and require authentication to pull. Re-enable them by logging in with `docker login ghcr.io` and uncommenting the relevant services.

**DefectDojo first-run:** DefectDojo's entrypoint does not run Django migrations automatically. The bootstrap steps in Quick Start section 4 must be run once after the first `docker compose up`.

## Security Notes

- The Docker socket is mounted into backend/worker containers, granting host-level access. Use [docker-socket-proxy](https://github.com/Tecnativa/docker-socket-proxy) in production.
- Change all default passwords in `.env` before any deployment.
- Only scan domains you own or have explicit written authorization to test.
- ZAP API key is disabled for development. Enable it for production.

## License

Private project. Not for redistribution.
