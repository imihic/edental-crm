# Dental CRM

Dental CRM helps clinic staff manage patients, follow up on enquiries, and record consent. The Flask API lives in `backend/`, the React app is in `frontend/`, and `openapi.json` describes the API. The staff app and public enquiry forms use English.

## Run it locally

You'll need Python 3.12, Node 22, and Docker Compose. Compose runs PostgreSQL 16 on port 5433 and Redis 7 on port 6380. If you're on Linux without Docker, use the [Linux setup guide](docs/evaluation.md).

From the project root, install dependencies, generate local configuration, and start the services.

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e "backend[dev]"
python scripts/setup_local.py
docker compose up -d
npm --prefix frontend ci
```

On Windows, activate the environment with `.venv\Scripts\Activate.ps1` in PowerShell. If the project path is long, put the environment in a shorter path outside the checkout. Long paths can cause the `pydantic_core` install to fail.

### Set up the database and a manager

`scripts/setup_local.py` generates fresh database passwords, a session signing key, and an authenticator encryption key. It writes ignored local configuration files for Compose and Flask. It refuses to overwrite existing configuration. Existing databases need their current credentials.

`.env.example` lists the available settings with password-free URLs. Supply credentials through your local configuration or environment.

Replace `<manager-email>` in the commands below with the address of your local test account.

Run the migration and create a manager from `backend/`.

```sh
python -m dotenv run -- alembic upgrade head
flask create-organization --name "Smile" --clinic "Central Clinic" --manager-email '<manager-email>' --manager-name "Demo Manager"
```

The migration command loads your local settings through dotenv. For a different database, set `DATABASE_OWNER_URL` in your shell before running the migration. Alembic reads it from the shell environment.

Enter the manager password at the prompt. Creating another organization with the same email reuses the account. To reset the password, run `flask reset-password --email '<manager-email>'`. Add `--reset-totp` if the manager also needs to set up their authenticator again.

### Start the app

From `backend/`, run `flask run`. In another terminal, run `npm --prefix frontend run dev` from the project root. Open `http://localhost:5173`. Vite forwards API requests to Flask on port 5000.

## Working with patients and enquiries

- **Patients** (`/patients`) is where staff search for patients, link guardians, and record consent. Use **Search by OIB** for an exact lookup. A patient's record includes enquiries carried over from a lead.
- **Leads** (`/leads`) is where staff record enquiries, move leads through stages, and convert them to patients. Managers and receptionists can merge duplicates from a patient's record.
- Clinic managers can import patients, manage staff and invitations, and set up public enquiry forms. Clinic pickers show the clinics in the current organization.

### Import patients from CSV

Download the [patient CSV template](docs/patient-import-template.csv) and replace the sample row. Only `First name` and `Last name` are required. If you include a `Clinic`, use a name from your organization.

The importer accepts commas or semicolons, UTF-8 or Windows-1250, and dates in `DD.MM.YYYY` or `YYYY-MM-DD` format. The limit is 5 MB and 5,000 rows per upload.

In **Imports**, upload the file and review invalid rows and possible duplicates before confirming. The default import skips duplicates and creates no consent records.

### Share a public enquiry form

In **Enquiry Form settings**, choose a clinic and copy its link or iframe snippet. The public frontend must serve `/enquiry/<key>` and forward `/api` to the backend on the same origin.

```html
<iframe src="https://crm.example.org/enquiry/FORM_KEY" title="Clinic enquiry form"
        width="100%" height="680" loading="lazy"></iframe>
```

Visitors can send an enquiry without signing in. Generating a new link invalidates the previous one, so update any links or embeds that use it.

## Tests and smoke checks

Start PostgreSQL and Redis before running the backend tests. From `backend/`, run `pytest -W error` and `lint-imports`. The tests use the `crm_test` database.

From the project root, run the frontend tests and build.

```sh
npm --prefix frontend test
npm --prefix frontend run build
```

`scripts/smoke_api.py` checks sign-in, organization switching, and authenticator enrollment against a running API. For that flow, use a test account in two organizations (`Smile` and `Beta` by default) that hasn't enrolled an authenticator yet.

```sh
python scripts/smoke_api.py http://localhost:5000 '<manager-email>' '<test password>'
```

For the People API smoke test, use a disposable organization with a manager who already uses an authenticator and has at least one assigned clinic. The script uses the manager's first clinic in the organization named by `--first`.

```sh
python scripts/smoke_api.py http://localhost:5000 '<manager-email>' '<password>' --people --first "Smoke"
```

Enter a fresh authenticator code when prompted. For unattended runs, set `SMOKE_TOTP_SECRET` in your shell and use a fresh time step for each run.

The People check creates sample records and audit entries, accepts a receptionist invitation, and rotates the clinic's public enquiry link. It prints `SMOKE OK` after checking that the receptionist receives `403` from `/api/staff` and both accounts sign out. Use a disposable database or organization because the records remain after the run.

## Update the API contract

After changing routes or schemas, run `flask export-openapi ../openapi.json` from `backend/`. Then run `npm --prefix frontend run gen:api` from the project root.

## Test data

Tests generate synthetic email addresses under reserved testing domains and temporary authentication values at runtime. CSV fixtures use explicit test labels, fictional phone numbers, repeated-digit identifiers, and blank optional email fields. Their accented characters and Croatian column aliases exercise import compatibility.

Local configuration files contain environment-specific credentials and are excluded from source control and the upload archive.

## License

This project is released under [the Unlicense](LICENSE). Dependencies retain their own licenses. The frontend build uses lightningcss under MPL-2.0.
