#!/usr/bin/env bash
# Hindsight provider-specific health checks (ADR-036 check 8).
#
# Called by /opt/agentic/memory/doctor's ProviderSpecificCheck. Reports
# JSON to stdout describing findings; exit 0 = pass, exit 1 = fail.
#
# Checks:
#   - bank_reachable: GET /v1/default/banks/<bank>
#       200 = bank exists (good)
#       404 = bank does not exist yet — fine, hindsight lazy-creates on
#             first retain. Still considered pass.
#       other = fail.
#   - dynamic_bank_id_consistent: if ~/.hindsight/claude-code.json exists
#       and has dynamicBankId !== false, the HINDSIGHT_BANK_ID env var
#       the adapter set is silently ignored by the hindsight plugin
#       (verified in hindsight bank.py:97). Auto-fix: rewrite the file
#       with dynamicBankId: false. This is a stale-state issue, not an
#       operator decision.

set -e

emit_json() {
    local status="$1"
    local details="$2"
    printf '{"hindsight_provider_check":"%s","details":%s}\n' "$status" "$details"
}

# --- Check 1: bank_reachable --------------------------------------------------
# Hindsight 0.6.x does not expose `GET /v1/default/banks/<id>` (returns 405).
# Use the list endpoint and filter — "not in list" is fine because hindsight
# lazy-creates banks on first retain.
LIST_URL="${HINDSIGHT_API_URL}/v1/default/banks"
HTTP_STATUS=$(curl -sS -o /tmp/hindsight-doctor-body -w "%{http_code}" \
    --max-time 5 \
    ${HINDSIGHT_API_TOKEN:+-H "Authorization: Bearer ${HINDSIGHT_API_TOKEN}"} \
    "${LIST_URL}" || echo "000")

if [ "${HTTP_STATUS}" != "200" ]; then
    emit_json "fail" "$(printf '{"check":"bank_reachable","url":"%s","http_status":"%s","body_preview":"%s"}' \
        "${LIST_URL}" "${HTTP_STATUS}" "$(head -c 200 /tmp/hindsight-doctor-body 2>/dev/null | tr '\n' ' ')")"
    exit 1
fi

# Check membership. If the bank is in the list, status=exists; otherwise
# lazy-create-pending (both pass).
bank_status=$(python3 -c "
import json, sys
try:
    with open('/tmp/hindsight-doctor-body') as f:
        data = json.load(f)
    banks = data.get('banks', [])
    bank_ids = [b.get('bank_id') for b in banks if isinstance(b, dict)]
    print('exists' if '${HINDSIGHT_BANK_ID}' in bank_ids else 'lazy_create_pending')
except Exception:
    print('lazy_create_pending')
" 2>/dev/null || echo "lazy_create_pending")

# --- Check 2: dynamic_bank_id_consistent (with auto-fix) ----------------------
HINDSIGHT_CONFIG="${HOME}/.hindsight/claude-code.json"
config_action="no_config_file"

if [ -f "${HINDSIGHT_CONFIG}" ]; then
    # Parse dynamicBankId field; default to false if file is malformed or key
    # absent. Use python3 (always present in this image) for robust JSON parsing.
    dyn_bank_id=$(python3 -c "
import json, sys
try:
    with open('${HINDSIGHT_CONFIG}') as f:
        cfg = json.load(f)
    print('true' if cfg.get('dynamicBankId') else 'false')
except Exception:
    print('parse-error')
" 2>/dev/null || echo "parse-error")

    case "${dyn_bank_id}" in
        false)
            config_action="config_consistent"
            ;;
        true)
            # Auto-fix: rewrite with dynamicBankId: false. The contract's intent
            # is explicit bank-id; a stale config saying otherwise is wrong.
            python3 -c "
import json
with open('${HINDSIGHT_CONFIG}') as f:
    cfg = json.load(f)
cfg['dynamicBankId'] = False
with open('${HINDSIGHT_CONFIG}', 'w') as f:
    json.dump(cfg, f, indent=2)
" 2>/dev/null
            config_action="auto_fixed_dynamic_bank_id"
            ;;
        parse-error)
            emit_json "fail" "$(printf '{"check":"dynamic_bank_id_consistent","error":"config_file_unreadable","path":"%s"}' "${HINDSIGHT_CONFIG}")"
            exit 1
            ;;
    esac
fi

# Success: emit a single JSON object with both check results.
emit_json "ok" "$(printf '{"bank":"%s","bank_status":"%s","config_action":"%s"}' \
    "${HINDSIGHT_BANK_ID}" "${bank_status}" "${config_action}")"
exit 0
