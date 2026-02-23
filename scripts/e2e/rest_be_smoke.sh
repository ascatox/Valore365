#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
PORTFOLIO_ID="${PORTFOLIO_ID:-}"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

PASS_COUNT=0
FAIL_COUNT=0

LAST_STATUS=""
LAST_BODY_FILE=""

run_request() {
  local method="$1"
  local path="$2"
  local body="${3:-}"
  local headers_file="${TMP_DIR}/headers.txt"
  local body_file="${TMP_DIR}/body.json"

  rm -f "${headers_file}" "${body_file}"

  if [[ -n "${body}" ]]; then
    LAST_STATUS="$(curl -sS -X "${method}" \
      -H 'Content-Type: application/json' \
      -D "${headers_file}" \
      -o "${body_file}" \
      -w '%{http_code}' \
      "${BASE_URL}${path}" \
      --data "${body}")"
  else
    LAST_STATUS="$(curl -sS -X "${method}" \
      -D "${headers_file}" \
      -o "${body_file}" \
      -w '%{http_code}' \
      "${BASE_URL}${path}")"
  fi

  LAST_BODY_FILE="${body_file}"
}

record_ok() {
  local name="$1"
  PASS_COUNT=$((PASS_COUNT + 1))
  printf 'PASS %-45s\n' "${name}"
}

record_fail() {
  local name="$1"
  local msg="$2"
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf 'FAIL %-45s %s\n' "${name}" "${msg}"
  if [[ -f "${LAST_BODY_FILE}" ]]; then
    printf '     body: %s\n' "$(cat "${LAST_BODY_FILE}")"
  fi
}

assert_status() {
  local name="$1"
  local expected="$2"
  if [[ "${LAST_STATUS}" == "${expected}" ]]; then
    record_ok "${name}"
  else
    record_fail "${name}" "expected status ${expected}, got ${LAST_STATUS}"
  fi
}

assert_jq() {
  local name="$1"
  local expr="$2"
  shift 2
  if jq -e "$@" "${expr}" "${LAST_BODY_FILE}" >/dev/null 2>&1; then
    record_ok "${name}"
  else
    record_fail "${name}" "jq assertion failed: ${expr}"
  fi
}

UNIQ_SUFFIX="$(date +%s)"

if [[ -z "${PORTFOLIO_ID}" ]]; then
  CREATE_PORTFOLIO_JSON="$(jq -nc --arg name "E2E REST Smoke ${UNIQ_SUFFIX}" \
    '{name:$name,base_currency:"EUR",timezone:"Europe/Rome"}')"
  run_request POST "/api/portfolios" "${CREATE_PORTFOLIO_JSON}"
  assert_status "POST /api/portfolios create test portfolio" "200"
  assert_jq "POST /api/portfolios returns id" '.id > 0 and .base_currency == "EUR"'
  PORTFOLIO_ID="$(jq -r '.id' "${LAST_BODY_FILE}")"
fi

echo "Running REST E2E smoke tests against ${BASE_URL} (portfolio_id=${PORTFOLIO_ID})"

run_request GET "/api/health"
assert_status "GET /api/health status" "200"
assert_jq "GET /api/health payload" '.status == "ok"'

run_request GET "/api/portfolios/999999/summary"
assert_status "GET /api/portfolios/999999/summary 404" "404"
assert_jq "error model uniform on 404" '.error.code == "not_found"'

run_request GET "/api/portfolios/${PORTFOLIO_ID}/summary"
assert_status "GET /api/portfolios/{id}/summary status" "200"
assert_jq "summary has expected portfolio id" ".portfolio_id == ${PORTFOLIO_ID}"

ASSET_SYMBOL="E2E${UNIQ_SUFFIX}"
ASSET_JSON="$(jq -nc \
  --arg symbol "${ASSET_SYMBOL}" \
  '{symbol:$symbol,name:"E2E Test Asset",asset_type:"stock",exchange_code:"XTST",exchange_name:"Test Exchange",quote_currency:"EUR",active:true}')"

run_request POST "/api/assets" "${ASSET_JSON}"
assert_status "POST /api/assets create asset" "200"
assert_jq "POST /api/assets returns id" '.id > 0'
ASSET_ID="$(jq -r '.id' "${LAST_BODY_FILE}")"

run_request POST "/api/assets" "${ASSET_JSON}"
assert_status "POST /api/assets duplicate conflict" "409"
assert_jq "duplicate asset error code" '.error.code == "conflict"'

run_request GET "/api/assets/${ASSET_ID}"
assert_status "GET /api/assets/{id}" "200"
assert_jq "GET /api/assets returns created symbol" '.id > 0 and .symbol == $sym' --arg sym "${ASSET_SYMBOL}"

PROVIDER_SYMBOL="e2e_map_${UNIQ_SUFFIX}"
APS_JSON="$(jq -nc --argjson aid "${ASSET_ID}" --arg ps "${PROVIDER_SYMBOL}" '{asset_id:$aid,provider:"twelvedata",provider_symbol:$ps}')"
run_request POST "/api/asset-provider-symbols" "${APS_JSON}"
assert_status "POST /api/asset-provider-symbols create" "200"
assert_jq "provider symbol normalized" '.provider == "twelvedata" and .provider_symbol == $ps' --arg ps "${PROVIDER_SYMBOL^^}"

run_request POST "/api/asset-provider-symbols" "${APS_JSON}"
assert_status "POST /api/asset-provider-symbols duplicate" "409"
assert_jq "duplicate mapping error code" '.error.code == "conflict"'

BUY_JSON="$(jq -nc --argjson pid "${PORTFOLIO_ID}" --argjson aid "${ASSET_ID}" '
  {
    portfolio_id:$pid,
    asset_id:$aid,
    side:"buy",
    trade_at:"2026-02-20T10:00:00Z",
    quantity:10,
    price:100,
    fees:0,
    taxes:0,
    trade_currency:"EUR",
    notes:"e2e smoke buy"
  }')"
run_request POST "/api/transactions" "${BUY_JSON}"
assert_status "POST /api/transactions buy" "200"
assert_jq "POST /api/transactions returns id" '.id > 0 and .side == "buy"'

SELL_TOO_MUCH_JSON="$(jq -nc --argjson pid "${PORTFOLIO_ID}" --argjson aid "${ASSET_ID}" '
  {
    portfolio_id:$pid,
    asset_id:$aid,
    side:"sell",
    trade_at:"2026-02-20T12:00:00Z",
    quantity:99999,
    price:100,
    fees:0,
    taxes:0,
    trade_currency:"EUR"
  }')"
run_request POST "/api/transactions" "${SELL_TOO_MUCH_JSON}"
assert_status "POST /api/transactions sell too much" "400"
assert_jq "sell too much error code" '.error.code == "bad_request"'

run_request GET "/api/portfolios/${PORTFOLIO_ID}/positions"
assert_status "GET /api/portfolios/{id}/positions" "200"
assert_jq "positions contains created asset" 'map(select(.asset_id == $aid and .quantity == 10 and .avg_cost == 100 and .market_price == 100)) | length == 1' --argjson aid "${ASSET_ID}"

run_request GET "/api/portfolios/${PORTFOLIO_ID}/summary"
assert_status "GET /api/portfolios/{id}/summary after tx" "200"
assert_jq "summary deterministic values" '.market_value == 1000 and .cost_basis == 1000 and .unrealized_pl == 0'

run_request GET "/api/portfolios/${PORTFOLIO_ID}/allocation"
assert_status "GET /api/portfolios/{id}/allocation" "200"
assert_jq "allocation contains created asset" 'map(select(.asset_id == $aid and .weight_pct == 100)) | length == 1' --argjson aid "${ASSET_ID}"

run_request GET "/api/portfolios/${PORTFOLIO_ID}/timeseries?range=1y&interval=1d"
assert_status "GET /api/portfolios/{id}/timeseries" "200"
assert_jq "timeseries length 365" 'length == 365'
assert_jq "timeseries shape" '.[0] | has("date") and has("market_value")'

run_request POST "/api/prices/backfill-daily?portfolio_id=${PORTFOLIO_ID}&days=10"
assert_status "POST /api/prices/backfill-daily validation" "422"
assert_jq "validation error model" '.error.code == "validation_error"'

run_request POST "/api/prices/refresh?portfolio_id=999999"
assert_status "POST /api/prices/refresh invalid portfolio" "400"
assert_jq "refresh invalid portfolio error model" '.error.code == "bad_request"'

echo
echo "Result: PASS=${PASS_COUNT} FAIL=${FAIL_COUNT}"

if [[ "${FAIL_COUNT}" -gt 0 ]]; then
  exit 1
fi
