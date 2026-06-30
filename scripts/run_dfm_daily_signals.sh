#!/bin/bash
# Thin launcher for launchd → daily_dfm_signals.py
#
# Refreshes DFM price history from the official API, then runs the daily
# signal runner (EMAAR~EMAARDEV spread + high-volume bearish-reversal scan).
#
# DATA NOTE: the official API feed lacks true share volume (it exposes a
# trade-count proxy), so the high-volume reversal scan is only fully reliable
# when run against a freshly-downloaded DFM *bulletin* export. If
# reports/dfm_bulletin/_all_series.json exists this script prefers it; drop a
# new bulletin there (via ingest_ohlcv.py) to keep the volume signal accurate.
#
# Install as launchd agent (macOS):
#   sed "s|\$HOME|$HOME|g; s|\$PROJECT_DIR|$(pwd)|g" \
#     launchd/com.trade-analysis.dfm-daily-signals.plist \
#     > ~/Library/LaunchAgents/com.trade-analysis.dfm-daily-signals.plist
#   launchctl load ~/Library/LaunchAgents/com.trade-analysis.dfm-daily-signals.plist
#   launchctl list | grep dfm-daily-signals
#
# Manual test:
#   bash scripts/run_dfm_daily_signals.sh

export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:${HOME}/.local/bin:/usr/local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.." || exit 1

command -v python3 >/dev/null 2>&1 || { echo "python3 not found" >&2; exit 1; }

SKILL_SCRIPTS="skills/chart-pattern-scanner/scripts"
BULLETIN="reports/dfm_bulletin/_all_series.json"
API_SERIES="reports/dfm_history/_all_series.json"

# Refresh ~18 months of official API history (best-effort; the signal still runs
# on whatever series is freshest if the network call fails).
FROM_DATE="$(python3 -c 'import datetime as d; print((d.date.today()-d.timedelta(days=550)).isoformat())')"
TO_DATE="$(python3 -c 'import datetime as d; print(d.date.today().isoformat())')"
python3 "${SKILL_SCRIPTS}/fetch_dfm_official.py" \
    --from "${FROM_DATE}" --to "${TO_DATE}" \
    --series-json --output-dir reports/dfm_history/ \
    || echo "warning: API refresh failed; using existing series" >&2

# Prefer the volume-accurate bulletin if present, else the API history.
if [ -f "${BULLETIN}" ]; then
    SERIES="${BULLETIN}"
else
    SERIES="${API_SERIES}"
fi

[ -f "${SERIES}" ] || { echo "no series JSON found at ${SERIES}" >&2; exit 1; }

python3 "${SKILL_SCRIPTS}/daily_dfm_signals.py" \
    --series-json "${SERIES}" --output-dir reports/ "$@"
