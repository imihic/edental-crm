# Run on Linux without Docker

Run these commands from the project root on Ubuntu with Bash, Python 3.12, and the PostgreSQL 16 server tools. Use the Python package mirror configured in the environment.

```sh
bash scripts/eval.sh install-backend
bash scripts/eval.sh migrate
bash scripts/eval.sh python -m alembic current
```

The last command should show `0015 (head)` for this version. The setup script starts a private PostgreSQL cluster under `/tmp` for your user and checkout. It applies migrations to `crm` and `crm_test`. The app connects as `crm_app`, and migrations use `crm_owner`.

Run `bash scripts/eval.sh stop` to stop the cluster. The database files stay under `/tmp` until the environment clears them.

## Backend tests

The starting backend uses Redis for server-side sessions. PostgreSQL setup and migrations can run on their own. Run the backend suite when Redis is available or after replacing the session store.

```sh
bash scripts/eval.sh python -m pytest -W error
```

The test fixtures clear `crm_test`. Use fictional records for manual checks.

## Try the app

When the backend is ready, start Flask on port 5000.

```sh
bash scripts/eval.sh python -m flask --app app run --host 127.0.0.1 --no-reload
```

Replace `<manager-email>` with your local test account address. For a test manager, run the following from a second terminal and enter a fresh local password when prompted.

```sh
bash scripts/eval.sh python -m flask --app app create-organization --name Demo --clinic Demo --manager-email '<manager-email>' --manager-name 'Demo Manager'
```

If your checkout includes the frontend, use Node 22 and the environment's npm mirror. Run these commands from the project root.

```sh
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173` to use the app.
