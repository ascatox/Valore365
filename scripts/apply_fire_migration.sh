#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATION_FILE="$ROOT_DIR/database/migrations/20260308_01_fire_settings.sql"

if ! command -v psql >/dev/null 2>&1; then
  echo "psql non trovato nel PATH." >&2
  exit 1
fi

if [[ ! -f "$MIGRATION_FILE" ]]; then
  echo "Migrazione non trovata: $MIGRATION_FILE" >&2
  exit 1
fi

CONNECTION_STRING="${1:-${DATABASE_URL_PSQL:-}}"

if [[ -n "$CONNECTION_STRING" ]]; then
  echo "Applico migrazione FIRE usando la connection string fornita..."
  psql "$CONNECTION_STRING" -v ON_ERROR_STOP=1 -f "$MIGRATION_FILE"
  echo "Migrazione FIRE completata."
  exit 0
fi

if [[ -z "${PGHOST:-}" || -z "${PGDATABASE:-}" || -z "${PGUSER:-}" ]]; then
  cat >&2 <<'EOF'
Fornisci una connessione Postgres in uno di questi modi:

1. Argomento:
   ./scripts/apply_fire_migration.sh "postgresql://USER:PASSWORD@HOST:5432/DBNAME"

2. Variabile d'ambiente:
   export DATABASE_URL_PSQL="postgresql://USER:PASSWORD@HOST:5432/DBNAME"
   ./scripts/apply_fire_migration.sh

3. Variabili PG standard:
   export PGHOST=...
   export PGPORT=5432
   export PGDATABASE=...
   export PGUSER=...
   export PGPASSWORD=...
   ./scripts/apply_fire_migration.sh
EOF
  exit 1
fi

echo "Applico migrazione FIRE usando le variabili PG* dell'ambiente..."
psql -v ON_ERROR_STOP=1 -f "$MIGRATION_FILE"
echo "Migrazione FIRE completata."
