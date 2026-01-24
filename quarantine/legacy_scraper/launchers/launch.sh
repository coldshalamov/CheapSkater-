#!/usr/bin/env bash
# After cloning, grant execute permission: chmod +x launch.sh

set -euo pipefail

LOG_DIR="logs"
LOG_FILE="${LOG_DIR}/launcher.log"
mkdir -p "${LOG_DIR}"
touch "${LOG_FILE}"
PROBE_CACHE_MINUTES="${PROBE_CACHE_MINUTES:-60}"

exec > >(tee -a "${LOG_FILE}") 2>&1

GREEN="\033[32m"
CYAN="\033[36m"
YELLOW="\033[33m"
RED="\033[31m"
RESET="\033[0m"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

cleanup() {
    if [[ -n "${DASHBOARD_PID:-}" ]]; then
        if kill -0 "${DASHBOARD_PID}" 2>/dev/null; then
            log "Stopping dashboard (pid=${DASHBOARD_PID})"
            kill "${DASHBOARD_PID}" >/dev/null 2>&1 || true
            wait "${DASHBOARD_PID}" 2>/dev/null || true
        fi
    fi
    if [[ -n "${SCRAPER_PID:-}" ]]; then
        if kill -0 "${SCRAPER_PID}" 2>/dev/null; then
            log "Stopping scraper (pid=${SCRAPER_PID})"
            kill "${SCRAPER_PID}" >/dev/null 2>&1 || true
            wait "${SCRAPER_PID}" 2>/dev/null || true
        fi
    fi
}

trap cleanup EXIT

PYTHON_DOWNLOAD_URL="https://www.python.org/downloads/"

if ! command -v python3 >/dev/null 2>&1; then
    log "python3 is not installed. Download from ${PYTHON_DOWNLOAD_URL}"
    exit 1
fi

if ! python3 - <<'PY'
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
then
    log "Python 3.11 or newer is required. Download from ${PYTHON_DOWNLOAD_URL}"
    exit 1
fi

if [[ ! -d .venv ]]; then
    log "Creating virtual environment"
    python3 -m venv .venv
fi

# shellcheck source=/dev/null
source .venv/bin/activate

log "Upgrading pip"
pip install --upgrade pip >/dev/null

if [[ -f requirements.txt ]]; then
    log "Installing requirements"
    pip install -r requirements.txt
fi

log "Ensuring Playwright chromium browser is available"
python -m playwright install chromium

CATALOG_FILE="catalog/building_materials.lowes.yml"
ZIP_FILE="catalog/wa_or_stores.yml"

if [[ ! -f "${CATALOG_FILE}" ]]; then
    log "Catalog missing; running discovery"
    python -m app.main --discover-categories
fi

if [[ ! -f "${ZIP_FILE}" ]]; then
    log "ZIP catalog missing; running store discovery"
    python -m app.main --discover-stores
fi

PROBE_FILE=$(mktemp)
log "Running probe check"
if python -m app.main --probe --probe-cache-minutes "${PROBE_CACHE_MINUTES}" >"${PROBE_FILE}"; then
    if ! python - <<'PY'
import json
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
try:
    json.loads(path.read_text(encoding='utf-8'))
except json.JSONDecodeError as exc:
    raise SystemExit(f"Probe output is not valid JSON: {exc}")
PY
        "${PROBE_FILE}"; then
        log "Probe JSON validation failed"
        exit 1
    fi
else
    log "Probe command failed"
    cat "${PROBE_FILE}"
    exit 1
fi
rm -f "${PROBE_FILE}"

SCRAPER_LOG="${LOG_DIR}/scraper.log"
DASHBOARD_LOG="${LOG_DIR}/dashboard.log"

SCRAPER_PID=""
DASHBOARD_PID=""

log "Starting one-time scraper run in background"
nohup python -m app.main --once >>"${SCRAPER_LOG}" 2>&1 &
SCRAPER_PID=$!

log "Starting dashboard"
nohup python -m uvicorn app.dashboard:app --host 0.0.0.0 --port 8000 >>"${DASHBOARD_LOG}" 2>&1 &
DASHBOARD_PID=$!

sleep 2

BROWSER_URL="http://localhost:8000"
case "$(uname)" in
    Darwin)
        log "Opening browser via open ${BROWSER_URL}"
        open "${BROWSER_URL}" >/dev/null 2>&1 || true
        ;;
    Linux)
        if command -v xdg-open >/dev/null 2>&1; then
            log "Opening browser via xdg-open ${BROWSER_URL}"
            xdg-open "${BROWSER_URL}" >/dev/null 2>&1 || true
        fi
        ;;
    *)
        log "Unsupported OS for auto browser launch"
        ;;
esac

while true; do
    echo -e "${GREEN}[R]${RESET} Re-run scrape" \
            "${CYAN}[L]${RESET} View logs" \
            "${YELLOW}[T]${RESET} Run tests" \
            "${RED}[Q]${RESET} Quit"
    read -r -p "Select option [R/L/T/Q]: " choice
    case "${choice^^}" in
        R)
            log "Re-running scraper"
            nohup python -m app.main --once >>"${SCRAPER_LOG}" 2>&1 &
            SCRAPER_PID=$!
            ;;
        L)
            if command -v less >/dev/null 2>&1; then
                less +F "${LOG_FILE}"
            else
                tail -n 200 "${LOG_FILE}"
            fi
            ;;
        T)
            log "Running full pipeline test"
            if python test_full_pipeline.py; then
                log "Pipeline test completed successfully"
            else
                log "Pipeline test failed"
            fi
            ;;
        Q)
            log "Quitting launcher"
            break
            ;;
        *)
            echo "Invalid option"
            ;;
    esac
    echo
 done
