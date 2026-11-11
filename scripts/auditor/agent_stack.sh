#!/usr/bin/env bash
# Auditor dei calcoli — stack locale usa e getta per l'agente settimanale (TASK-82).
#
#   scripts/auditor/agent_stack.sh start    # Postgres 16 + schema + migrazioni + seed; ultima riga: DATABASE_URL=...
#   scripts/auditor/agent_stack.sh url      # stampa solo il DATABASE_URL (per $(...))
#   scripts/auditor/agent_stack.sh env      # stampa "export DATABASE_URL=..." (per eval)
#   scripts/auditor/agent_stack.sh status   # cluster attivo? portafogli del seed presenti?
#   scripts/auditor/agent_stack.sh reseed   # riapplica solo il seed (cluster già avviato)
#   scripts/auditor/agent_stack.sh stop     # ferma il cluster e cancella la cartella
#
# Idempotente: "start" su un cluster già avviato non crea un secondo server; ricrea il database
# (drop + create) e riapplica schema, migrazioni e seed, così ogni sessione parte dagli stessi dati.
# Nessun processo resta agganciato allo stdout dello script: pg_ctl scrive nel log del cluster e
# ha stdin/stdout/stderr rediretti, quindi "agent_stack.sh start | tail -1" o "$(agent_stack.sh url)"
# ritornano (vedi la nota sui processi in background in scripts/e2e/README.md).
#
# Nessun server applicativo: l'Auditor e scripts/auditor/mcp_call.py lavorano in processo con il
# DATABASE_URL stampato. Il cluster ascolta solo sul socket Unix in $AGENT_DIR (nessun TCP).
#
# Variabili:
#   PG_BIN     cartella con initdb e pg_ctl. Default: /usr/lib/postgresql/16/bin se esiste,
#              altrimenti `pg_config --bindir`, altrimenti la cartella di `initdb` nel PATH.
#   AGENT_DIR  cartella del cluster, dei log e del socket (default /tmp/valore365-auditor-agent;
#              tenerla corta: il percorso del socket non può superare 107 byte).
#   PG_PORT    porta del socket (default 55450, diversa dagli stack E2E 55440).
#   DB_NAME    nome del database (default valore365_auditor).
#   PSQL       client psql (default psql nel PATH, altrimenti $PG_BIN/psql).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AGENT_DIR="${AGENT_DIR:-/tmp/valore365-auditor-agent}"
PG_PORT="${PG_PORT:-55450}"
DB_NAME="${DB_NAME:-valore365_auditor}"
SEED="$ROOT/scripts/auditor/audit_seed.sql"
SEED_USER="auditor-seed-user"

die() { echo "agent_stack: $*" >&2; exit 1; }
log() { echo "- $*" >&2; }

resolve_pg_bin() {
  if [[ -n "${PG_BIN:-}" ]]; then
    [[ -x "$PG_BIN/initdb" && -x "$PG_BIN/pg_ctl" ]] || die "PG_BIN=$PG_BIN non contiene initdb e pg_ctl"
    return
  fi
  local candidate
  for candidate in /usr/lib/postgresql/16/bin "$(pg_config --bindir 2>/dev/null || true)" \
      "$(dirname "$(command -v initdb 2>/dev/null || echo /nonexistent/initdb)")"; do
    if [[ -n "$candidate" && -x "$candidate/initdb" && -x "$candidate/pg_ctl" ]]; then
      PG_BIN="$candidate"
      return
    fi
  done
  die "binari di Postgres non trovati: impostare PG_BIN (es. PG_BIN=/usr/lib/postgresql/16/bin) o installare Postgres 16 (apt-get install -y postgresql-16)"
}

resolve_psql() {
  if [[ -n "${PSQL:-}" ]]; then return; fi
  if command -v psql >/dev/null 2>&1; then PSQL="$(command -v psql)"
  elif [[ -x "$PG_BIN/psql" ]]; then PSQL="$PG_BIN/psql"
  else die "psql non trovato: impostare PSQL"; fi
}

# Da root il cluster gira come utente postgres (initdb rifiuta root), come la fixture pg_engine.
as_pg() {
  if [[ "$(id -u)" == "0" ]]; then
    id postgres >/dev/null 2>&1 || die "da root serve l'utente di sistema 'postgres'"
    runuser -u postgres -- "$@"
  else
    "$@"
  fi
}

database_url() {
  echo "postgresql+psycopg://postgres@/${DB_NAME}?host=${AGENT_DIR}&port=${PG_PORT}"
}

psql_cmd() {
  # PGOPTIONS: niente NOTICE delle migrazioni ("relation already exists, skipping") nell'output.
  PGOPTIONS='-c client_min_messages=warning' "$PSQL" -q -X -h "$AGENT_DIR" -p "$PG_PORT" -U postgres -v ON_ERROR_STOP=1 "$@"
}

is_running() {
  [[ -d "$AGENT_DIR/data" ]] && as_pg "$PG_BIN/pg_ctl" -D "$AGENT_DIR/data" status >/dev/null 2>&1 </dev/null
}

apply_seed() {
  log "seed dell'Auditor ($SEED)"
  psql_cmd -d "$DB_NAME" -f "$SEED" >/dev/null </dev/null
}

check_seed() {
  local count
  count="$(psql_cmd -d "$DB_NAME" -tA -c "select count(*) from portfolios where owner_user_id = '${SEED_USER}'" </dev/null)"
  [[ "$count" == "7" ]] || die "attesi 7 portafogli di ${SEED_USER}, trovati ${count:-0}"
  log "7 portafogli di prova di ${SEED_USER} (9101…9107)"
}

start() {
  resolve_pg_bin
  resolve_psql
  mkdir -p "$AGENT_DIR"
  [[ "$(id -u)" == "0" ]] && chown postgres "$AGENT_DIR"
  chmod 755 "$AGENT_DIR"
  if [[ ! -d "$AGENT_DIR/data" ]]; then
    log "initdb in $AGENT_DIR/data ($PG_BIN)"
    as_pg "$PG_BIN/initdb" -D "$AGENT_DIR/data" -U postgres -A trust -E UTF8 --locale=C.UTF-8 >/dev/null 2>&1 </dev/null \
      || as_pg "$PG_BIN/initdb" -D "$AGENT_DIR/data" -U postgres -A trust -E UTF8 >/dev/null </dev/null
  fi
  if is_running; then
    log "Postgres già attivo (socket $AGENT_DIR, porta $PG_PORT)"
  else
    log "avvio Postgres (socket $AGENT_DIR, porta $PG_PORT, log $AGENT_DIR/postgres.log)"
    as_pg "$PG_BIN/pg_ctl" -D "$AGENT_DIR/data" -l "$AGENT_DIR/postgres.log" -w -t 60 \
      -o "-p $PG_PORT -k $AGENT_DIR -c listen_addresses='' -c fsync=off -c synchronous_commit=off" \
      start >/dev/null 2>&1 </dev/null || die "Postgres non parte: vedi $AGENT_DIR/postgres.log"
  fi
  log "database $DB_NAME: drop + create"
  psql_cmd -d postgres -c "drop database if exists ${DB_NAME} with (force)" -c "create database ${DB_NAME}" >/dev/null </dev/null
  log "schema + migrazioni"
  psql_cmd -d "$DB_NAME" -f "$ROOT/database/schema.sql" >/dev/null </dev/null
  local migration
  while IFS= read -r migration; do
    psql_cmd -d "$DB_NAME" -f "$migration" >/dev/null </dev/null
  done < <(find "$ROOT/database/migrations" -maxdepth 1 -name '*.sql' | LC_ALL=C sort)
  apply_seed
  check_seed
  database_url >"$AGENT_DIR/database_url"
  log "pronto; per i comandi successivi: eval \"\$($0 env)\""
  echo "DATABASE_URL=$(database_url)"
}

reseed() {
  resolve_pg_bin
  resolve_psql
  is_running || die "cluster non attivo: eseguire prima '$0 start'"
  apply_seed
  check_seed
  echo "DATABASE_URL=$(database_url)"
}

status() {
  resolve_pg_bin
  resolve_psql
  if is_running; then
    echo "postgres: attivo (socket $AGENT_DIR, porta $PG_PORT)"
    local count
    count="$(psql_cmd -d "$DB_NAME" -tA -c "select count(*) from portfolios where owner_user_id = '${SEED_USER}'" </dev/null 2>/dev/null || echo 0)"
    echo "portafogli di ${SEED_USER}: ${count:-0}"
    echo "DATABASE_URL=$(database_url)"
  else
    echo "postgres: fermo"
    return 3
  fi
}

stop() {
  resolve_pg_bin
  if [[ -d "$AGENT_DIR/data" ]]; then
    as_pg "$PG_BIN/pg_ctl" -D "$AGENT_DIR/data" -m fast -w stop >/dev/null 2>&1 </dev/null \
      || as_pg "$PG_BIN/pg_ctl" -D "$AGENT_DIR/data" -m immediate stop >/dev/null 2>&1 </dev/null || true
  fi
  rm -rf "$AGENT_DIR"
  echo "Stack dell'Auditor fermato, $AGENT_DIR cancellata."
}

case "${1:-}" in
  start) start ;;
  url) database_url ;;
  env) echo "export DATABASE_URL='$(database_url)'" ;;
  status) status ;;
  reseed) reseed ;;
  stop) stop ;;
  *) echo "uso: $0 start|url|env|status|reseed|stop" >&2; exit 2 ;;
esac
