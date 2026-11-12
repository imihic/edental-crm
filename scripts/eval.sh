#!/usr/bin/env bash
set -euo pipefail
umask 077

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
root_id=$(printf '%s' "$root" | sha256sum | cut -c1-16)
state="/tmp/dental-crm-$(id -u)-$root_id"
data="$state/postgres"
python="$state/venv/bin/python"

fail() { printf '%s\n' "$*" >&2; exit 1; }

prepare_state() {
    [[ $(id -u) != 0 ]] || fail 'Run this script as an unprivileged user.'
    mkdir -m 700 -- "$state" 2>/dev/null || true
    [[ -d $state && ! -L $state && -O $state && $(stat -c '%a' "$state") == 700 ]] ||
        fail "Expected a private runtime directory owned by this user: $state"
}

find_postgres() {
    local bin
    for bin in /usr/lib/postgresql/16/bin "$(pg_config --bindir 2>/dev/null || true)"; do
        if [[ -n $bin && -x $bin/initdb && -x $bin/pg_ctl && -x $bin/psql ]]; then
            pg=$bin
            return
        fi
    done
    fail 'PostgreSQL server tools are missing. This setup expects PostgreSQL 16.'
}

psql_local() {
    "$pg/psql" -X -v ON_ERROR_STOP=1 -h "$state" -p 5432 "$@"
}

start_db() (
    prepare_state
    find_postgres
    flock 9
    if [[ ! -f $data/PG_VERSION ]]; then
        "$pg/initdb" -D "$data" -U crm_owner --auth-local=trust --auth-host=reject \
            --encoding=UTF8 --locale=C.UTF-8 >/dev/null
    fi
    if ! "$pg/pg_ctl" -D "$data" status >/dev/null; then
        "$pg/pg_ctl" -D "$data" -l "$state/postgres.log" \
            -o "-c listen_addresses='' -c unix_socket_directories=$state -p 5432" -w start 9>&- >/dev/null
    fi
    psql_local -q -U crm_owner -d postgres <<'SQL'
SELECT 'CREATE ROLE crm_app LOGIN NOBYPASSRLS'
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'crm_app') \gexec
SELECT format('CREATE DATABASE %I OWNER crm_owner', name)
FROM (VALUES ('crm'), ('crm_test')) AS databases(name)
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = name) \gexec
GRANT CONNECT ON DATABASE crm, crm_test TO crm_app;
SQL
) 9>"$state/db.lock"

database_env() {
    prepare_state
    start_db
    export DATABASE_URL="postgresql://crm_app@/crm?host=$state"
    export DATABASE_OWNER_URL="postgresql://crm_owner@/crm?host=$state"
    export CRM_TEST_DATABASE_URL="postgresql://crm_app@/crm_test?host=$state"
    export CRM_TEST_DATABASE_OWNER_URL="postgresql://crm_owner@/crm_test?host=$state"
}

install_backend() {
    prepare_state
    if [[ ! -x $python ]]; then
        if command -v uv >/dev/null; then
            uv venv --python 3.12 --no-python-downloads "$state/venv"
        else
            python3.12 -m venv "$state/venv"
        fi
    fi
    if "$python" -m pip --version >/dev/null 2>&1; then
        "$python" -m pip install -e "$root/backend[dev]"
    else
        UV_INDEX_URL="${UV_INDEX_URL:-${PIP_INDEX_URL:-https://pypi.org/simple}}" \
            uv pip install --python "$python" -e "$root/backend[dev]"
    fi
}

require_python() {
    [[ -x $python ]] || fail 'Run bash scripts/eval.sh install-backend first.'
}

case "${1:-help}" in
    db)
        database_env
        printf '%s\n' 'PostgreSQL is ready on a private Unix socket (databases: crm, crm_test).'
        ;;
    stop)
        if [[ -e $state ]]; then
            prepare_state
            find_postgres
            (
                flock 9
                if "$pg/pg_ctl" -D "$data" status >/dev/null; then
                    "$pg/pg_ctl" -D "$data" -w stop
                fi
            ) 9>"$state/db.lock"
        fi
        ;;
    install-backend)
        install_backend
        ;;
    migrate)
        require_python
        database_env
        cd -- "$root/backend"
        "$python" -m alembic upgrade head
        DATABASE_OWNER_URL="$CRM_TEST_DATABASE_OWNER_URL" "$python" -m alembic upgrade head
        ;;
    python)
        shift
        require_python
        database_env
        (
            flock 9
            if [[ ! -s $state/app.keys ]]; then
                "$python" -c 'import base64, secrets; print(secrets.token_hex(32)); print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())' > "$state/app.keys.new"
                mv -- "$state/app.keys.new" "$state/app.keys"
            fi
        ) 9>"$state/app.lock"
        { read -r SECRET_KEY; read -r TOTP_ENCRYPTION_KEY; } < "$state/app.keys"
        export SECRET_KEY TOTP_ENCRYPTION_KEY SESSION_COOKIE_SECURE=false FLASK_SKIP_DOTENV=1
        cd -- "$root/backend"
        exec "$python" "$@"
        ;;
    help|-h|--help)
        printf '%s\n' 'Usage: bash scripts/eval.sh {install-backend|db|migrate|python [args...]|stop}'
        ;;
    *) fail "Unknown command: $1 (see bash scripts/eval.sh help)" ;;
esac
