#!/usr/bin/env bash
# Patch the base servo pulse_min from 500 to 600 to symmetrise the +/- range
# around pulse_center, then hot-reload.
set -e
cd /home/rpclaw/frankie
python3 -c '
import json, pathlib
p = pathlib.Path("data/calibration/servos.json")
data = json.loads(p.read_text())
old = data["channels"]["4"]["pulse_min"]
data["channels"]["4"]["pulse_min"] = 600
p.write_text(json.dumps(data, indent=2))
print(f"base pulse_min: {old} -> 600")
'
curl -s -X POST http://127.0.0.1:8000/api/calibration/reload > /dev/null
echo 'reloaded'
echo '--- verify ---'
curl -s -X POST -H 'Content-Type: application/json' --data '{"joint":"base","angle_deg":77.0}' http://127.0.0.1:8000/api/jog | python3 -c 'import sys,json; d=json.load(sys.stdin); print("base=+77 pulse:", d["arm"]["joints"]["base"]["pulse_us"])'
sleep 2
curl -s -X POST -H 'Content-Type: application/json' --data '{"joint":"base","angle_deg":0.0}' http://127.0.0.1:8000/api/jog > /dev/null
sleep 2
curl -s -X POST -H 'Content-Type: application/json' --data '{"joint":"base","angle_deg":-77.0}' http://127.0.0.1:8000/api/jog | python3 -c 'import sys,json; d=json.load(sys.stdin); print("base=-77 pulse:", d["arm"]["joints"]["base"]["pulse_us"])'
sleep 2
curl -s -X POST -H 'Content-Type: application/json' --data '{"joint":"base","angle_deg":0.0}' http://127.0.0.1:8000/api/jog > /dev/null
