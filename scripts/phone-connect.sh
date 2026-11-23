#!/usr/bin/env bash
# Forbinder telefonen over USB og åbner dashboardet på den.
#
#   ./scripts/phone-connect.sh            # bruger port 8765
#   PORT=9000 ./scripts/phone-connect.sh
#
# Kræver: adb (sudo apt install adb) og USB-fejlfinding slået til på telefonen.
set -euo pipefail
PORT="${PORT:-8765}"

if ! command -v adb >/dev/null; then
  echo "adb mangler – installer med: sudo apt install adb" >&2
  exit 1
fi

echo "Venter på telefonen (godkend 'Tillad USB-fejlfinding' på skærmen) …"
adb wait-for-device

# localhost:$PORT på telefonen -> localhost:$PORT på PC'en (gennem USB-kablet)
adb reverse "tcp:$PORT" "tcp:$PORT"

# Hold skærmen tændt mens den lader (OnePlus/OxygenOS kan nægte det – dashboardet
# holder alligevel skærmen vågen selv, så længe det er åbent)
if ! adb shell settings put global stay_on_while_plugged_in 7 >/dev/null 2>&1; then
  echo "Bemærk: telefonen tillod ikke 'hold skærmen tændt' – slå evt. 'Stay awake' til under Developer options."
fi

# Åbn dashboardet i telefonens standardbrowser
adb shell am start -a android.intent.action.VIEW -d "http://localhost:$PORT" >/dev/null

echo "Klar ✔  Tryk på uret på telefonen for fuld skærm."
