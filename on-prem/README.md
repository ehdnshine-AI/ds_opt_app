# On-Prem Runtime

This directory contains local runtime helpers for an on-prem deployment:

- `run.windows.ps1`: Windows launcher for `pulp`, `api`, `cbc`, `highs`
- `run.linux.sh`: Linux launcher for `pulp`, `api`, `cbc`, `highs`
- `postgres.compose.yml`: Docker Compose file for PostgreSQL
- `app.env.example`: example environment values

## Layout

- Python services run directly from the repository source.
- PostgreSQL runs in Docker.
- Runtime pid files and logs are stored under `on-prem/.run` and `on-prem/logs`.

## Quick Start

1. Copy `on-prem/app.env.example` to `on-prem/.env`.
2. Adjust `DATABASE_URL`, ports, and PostgreSQL credentials if needed.
3. Install Python dependencies.
4. Start PostgreSQL with Docker.
5. Start the solver connectors and API.

## Windows

```powershell
Copy-Item .\on-prem\app.env.example .\on-prem\.env
.\on-prem\run.windows.ps1 install
.\on-prem\run.windows.ps1 postgres-up
.\on-prem\run.windows.ps1 start-all
.\on-prem\run.windows.ps1 status
```

## Linux

```bash
cp ./on-prem/app.env.example ./on-prem/.env
chmod +x ./on-prem/run.linux.sh
./on-prem/run.linux.sh install
./on-prem/run.linux.sh postgres-up
./on-prem/run.linux.sh start-all
./on-prem/run.linux.sh status
```

## Commands

Available in both launchers:

- `install`
- `deploy`
- `start-solvers`
- `start-api`
- `start-all`
- `restart-all`
- `stop-solvers`
- `stop-api`
- `stop-all`
- `status`
- `postgres-up`
- `postgres-down`
- `postgres-logs`
- `postgres-ps`
