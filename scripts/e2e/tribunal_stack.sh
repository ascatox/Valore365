#!/usr/bin/env bash
# Tribunale del portafoglio — stack E2E reale e usa-e-getta (TASK-71).
#
#   scripts/e2e/tribunal_stack.sh start   # Postgres 16 + seed, LLM finto del Tribunale, backend :8000, backend flag OFF :8001, Vite :5173
#   scripts/e2e/tribunal_stack.sh stop    # ferma tutto e cancella il cluster
#   scripts/e2e/tribunal_stack.sh status
#
# Stesso impianto di doctor2_stack.sh (stesso seed scripts/e2e/doctor2_seed.sql: utente dev-user,
# portafogli EUR «Parent» e «Wealth»), con il finto LLM scripts/e2e/tribunal_fake_llm.py: il
# backend usa COPILOT_PROVIDER=openai con OPENAI_BASE_URL verso di lui, quindi la chiamata
# strutturata, il verificatore, l'orchestratore, lo stream SSE e il salvataggio delle sedute
# sono quelli reali. Nessuna rete esterna (HTTP(S)_PROXY verso una porta chiusa).
# Il finto LLM risponde con ritardi diversi per voce (comparsa progressiva) e aggiunge a ogni
# risposta elementi avversi (numeri nel testo, acquisti, strumenti estranei) che il verificatore
# deve scartare.
# Variabili: E2E_DIR (default /tmp/valore365-tribunal-e2e), PG_BIN, PG_PORT (55441),
# BACKEND_PORT (8000, fisso: è il target del proxy Vite), FLAGS_OFF_PORT (8001), VITE_PORT (5173),
# LLM_PORT (8766), LLM_DELAYS (indicizzatore=0.6,fattoriale=1.6,prudente=2.6),
# LLM_ADVERSARIAL (numeri,acquisto,strumenti), DAILY_LIMIT (20).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
E2E_DIR="${E2E_DIR:-/tmp/valore365-tribunal-e2e}"
PG_BIN="${PG_BIN:-/usr/lib/postgresql/16/bin}"
PG_PORT="${PG_PORT:-55441}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FLAGS_OFF_PORT="${FLAGS_OFF_PORT:-8001}"
VITE_PORT="${VITE_PORT:-5173}"
LLM_PORT="${LLM_PORT:-8766}"
LLM_DELAYS="${LLM_DELAYS:-indicizzatore=0.6,fattoriale=1.6,prudente=2.6}"
LLM_ADVERSARIAL="${LLM_ADVERSARIAL:-numeri,acquisto,strumenti}"
DAILY_LIMIT="${DAILY_LIMIT:-20}"
PYTHON="${PYTHON:-python3}"

as_pg() {
  if [[ "$(id -u)" == "0" ]]; then runuser -u postgres -- "$@"; else "$@"; fi
}

wait_http() {
  local url="$1" name="$2"
  for _ in $(seq 1 120); do
    if curl -sf -o /dev/null --noproxy '*' "$url"; then echo "  $name pronto ($url)"; return 0; fi
    sleep 0.5
  done
  echo "  $name non risponde: $url (log in $E2E_DIR)" >&2
  return 1
}

backend_env() {
  # $1 = 'on' | 'off' (DOCTOR_TRIBUNAL_ENABLED)
  local enabled=true; [[ "$1" == "off" ]] && enabled=false
  env -i PATH="$PATH" HOME="${HOME:-/root}" LANG=C.UTF-8 \
    APP_ENV=dev CLERK_AUTH_ENABLED=false \
    DATABASE_URL="postgresql+psycopg://postgres@/valore365?host=${E2E_DIR}&port=${PG_PORT}" \
    PRICE_SCHEDULER_ENABLED=false DAILY_BARS_SCHEDULER_ENABLED=false PAC_SCHEDULER_ENABLED=false \
    MARKET_DATA_SYNC_ON_STARTUP=false JUSTETF_ENABLED=false JUSTETF_XRAY_AUTO_ENRICH_ENABLED=false \
    FINANCE_MAX_RETRIES=0 FINANCE_REQUEST_TIMEOUT_SECONDS=2 \
    AUTHENTICATED_RATE_LIMIT_REQUESTS=100000 \
    DOCTOR_POLICY_ENABLED=true DOCTOR_SIMULATOR_ENABLED=true \
    DOCTOR_TRIBUNAL_ENABLED="$enabled" DOCTOR_TRIBUNAL_DAILY_LIMIT="$DAILY_LIMIT" \
    COPILOT_PROVIDER=openai COPILOT_MODEL=fake-tribunal OPENAI_API_KEY=sk-fake-e2e \
    OPENAI_BASE_URL="http://127.0.0.1:${LLM_PORT}/v1" OPENAI_MAX_RETRIES=0 \
    HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 \
    http_proxy=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 \
    NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
    "${@:2}"
}

start() {
  mkdir -p "$E2E_DIR"
  [[ "$(id -u)" == "0" ]] && chown postgres "$E2E_DIR"
  chmod 755 "$E2E_DIR"
  if [[ ! -d "$E2E_DIR/data" ]]; then
    echo "- initdb in $E2E_DIR/data"
    as_pg "$PG_BIN/initdb" -D "$E2E_DIR/data" -U postgres -A trust -E UTF8 >/dev/null
  fi
  echo "- avvio Postgres (socket $E2E_DIR, porta $PG_PORT)"
  as_pg "$PG_BIN/pg_ctl" -D "$E2E_DIR/data" -l "$E2E_DIR/postgres.log" -w \
    -o "-p $PG_PORT -k $E2E_DIR -c listen_addresses='' -c fsync=off" start >/dev/null 2>&1 </dev/null
  export PGOPTIONS='-c client_min_messages=warning'
  local psql=(psql -q -h "$E2E_DIR" -p "$PG_PORT" -U postgres -v ON_ERROR_STOP=1)
  "${psql[@]}" -d postgres -c "drop database if exists valore365" -c "create database valore365" >/dev/null
  echo "- schema + migrazioni + seed"
  "${psql[@]}" -d valore365 -f "$ROOT/database/schema.sql" >/dev/null
  for migration in "$ROOT"/database/migrations/*.sql; do
    "${psql[@]}" -d valore365 -f "$migration" >/dev/null
  done
  "${psql[@]}" -d valore365 -f "$ROOT/scripts/e2e/doctor2_seed.sql" >/dev/null

  echo "- LLM finto del Tribunale :$LLM_PORT (ritardi $LLM_DELAYS; avversi $LLM_ADVERSARIAL)"
  nohup "$PYTHON" "$ROOT/scripts/e2e/tribunal_fake_llm.py" --port "$LLM_PORT" \
    --delays "$LLM_DELAYS" --adversarial "$LLM_ADVERSARIAL" >"$E2E_DIR/fake_llm.log" 2>&1 </dev/null &
  echo $! >"$E2E_DIR/fake_llm.pid"

  echo "- backend :$BACKEND_PORT (Tribunale ON) e :$FLAGS_OFF_PORT (Tribunale OFF)"
  (cd "$ROOT/src/backend" && backend_env on nohup "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT" \
    >"$E2E_DIR/backend.log" 2>&1 </dev/null & echo $! >"$E2E_DIR/backend.pid")
  (cd "$ROOT/src/backend" && backend_env off nohup "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$FLAGS_OFF_PORT" \
    >"$E2E_DIR/backend_flags_off.log" 2>&1 </dev/null & echo $! >"$E2E_DIR/backend_flags_off.pid")

  echo "- Vite :$VITE_PORT (proxy /api -> localhost:8000)"
  (cd "$ROOT/src/frontend/valore-frontend" && VITE_API_BASE_URL= VITE_CLERK_PUBLISHABLE_KEY= \
    nohup npx vite --host 127.0.0.1 --port "$VITE_PORT" --strictPort >"$E2E_DIR/vite.log" 2>&1 </dev/null & echo $! >"$E2E_DIR/vite.pid")

  wait_http "http://127.0.0.1:$LLM_PORT/__state" "LLM finto"
  wait_http "http://127.0.0.1:$BACKEND_PORT/api/health" "backend"
  wait_http "http://127.0.0.1:$FLAGS_OFF_PORT/api/health" "backend Tribunale OFF"
  wait_http "http://127.0.0.1:$VITE_PORT/" "Vite"
  echo "Stack pronto. Log in $E2E_DIR"
}

stop() {
  for name in vite backend backend_flags_off fake_llm; do
    if [[ -f "$E2E_DIR/$name.pid" ]]; then
      pid="$(cat "$E2E_DIR/$name.pid")"
      pkill -TERM -P "$pid" 2>/dev/null || true
      kill "$pid" 2>/dev/null || true
      rm -f "$E2E_DIR/$name.pid"
    fi
  done
  if [[ -d "$E2E_DIR/data" ]]; then
    as_pg "$PG_BIN/pg_ctl" -D "$E2E_DIR/data" -m immediate stop >/dev/null 2>&1 || true
  fi
  rm -rf "$E2E_DIR"
  echo "Stack fermato."
}

status() {
  for name in fake_llm backend backend_flags_off vite; do
    if [[ -f "$E2E_DIR/$name.pid" ]] && kill -0 "$(cat "$E2E_DIR/$name.pid")" 2>/dev/null; then
      echo "$name: attivo"
    else
      echo "$name: fermo"
    fi
  done
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) echo "uso: $0 start|stop|status" >&2; exit 2 ;;
esac
