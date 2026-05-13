# Agent Instructions for Cloud Native Platform (CNP)

This repository is a multi-component monorepo:

- `backend/` contains the FastAPI API, async SQLAlchemy, Alembic, and cloud provider adapters.
- `frontend/` contains the Vite + React + TypeScript UI.
- `cli/` contains the Typer-based CLI.
- `shared/` contains models shared by backend and CLI.

## Product context

- This project targets an internal enterprise Cloud Native Platform (CNP), not a generic demo app.
- The platform must support multi-cloud operations (at least AWS, GCP, and OpenStack, and be extensible to other providers).
- Design choices should favor enterprise platform capabilities expected from a CNP:
  - central resource lifecycle management across clouds;
  - environment management (dev, staging, prod) with clear separation and promotion paths;
  - application scaffolding and templating workflows;
  - automated deployment workflows and repeatable delivery pipelines;
  - observability and monitoring foundations (metrics, logs, health, auditability);
  - secure-by-default operations (authn/authz, key handling, tenant/user isolation);
  - operational governance (traceability, policy enforcement, controlled change).
- When implementing features, prefer patterns that keep these platform-level goals reachable, even for incremental changes.

## Work style

- Prefer small, local changes that preserve the existing layering: routes handle HTTP concerns, services handle business logic, providers handle cloud SDK calls, and DB code stays in the persistence layer.
- Treat `shared/models.py` as the source of truth for backend/CLI shared enums and data structures.
- This platform has two user-facing fronts: the React web app (`frontend/`) and the CLI (`cli/`).
- When adding a feature, propagate it to both fronts when the capability is relevant to both interfaces.
- When backend API behavior, contracts, or shared models change, adjust both fronts accordingly (API client calls, payloads, validation, UX flows, and CLI command behavior).
- Do not duplicate setup or architecture docs here; link to the relevant docs instead.

## Useful entry points

- Root setup and local bootstrapping: [README.md](README.md)
- Backend-specific architecture and API details: [backend/README.md](backend/README.md)
- Project architecture docs: [docs/architecture/](docs/architecture/)
- Architecture decisions: [docs/adr/](docs/adr/)

## Build and validation

- Full local stack: `./start.sh`
- Frontend dev: `cd frontend && npm run dev`
- Frontend validation: `cd frontend && npm run build` and `cd frontend && npm run lint`
- Backend and shared packages install in editable mode: `python3 -m pip install -e ./shared` and `python3 -m pip install -e ./backend`
- CLI install in editable mode: `python3 -m pip install -e ./cli`
- Alembic migrations in containers must use the backend config file, for example `alembic -c backend/alembic.ini upgrade head`

## Conventions and pitfalls

- `.env` at the repo root is required for local work; `SECRET_KEY` must be at least 32 characters.
- Authentication order matters in the backend: API key auth is checked before JWT Bearer auth.
- Backend database access is async; keep `await` boundaries intact.
- Preserve the API contract around refresh cookies, API keys, and shared enums when editing auth or resource flows.
- When adding or changing cloud functionality, update the provider abstraction rather than hard-coding provider-specific behavior in routes or services.

## When editing code

- If a change affects setup, auth, migrations, or architecture boundaries, check the linked docs first and update them only if the behavior has changed.
- Prefer validating the touched area with the narrowest relevant command, usually a frontend build/lint or a focused backend run path.
