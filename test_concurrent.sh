#!/usr/bin/env bash
# Concurrent multi-user test
# Submits 3 tasks simultaneously, shows queue depth, then streams each result.

API="http://34.44.129.194"
KEY="c6dea99f1b4012500197ee898ed02dc43e8a9a98a04a7d2eb62600f032ca852b"

TASKS=(
  "What is the current CPU temperature of the Pi?"
  "How much free disk space is available?"
  "How many CPUs does this device have and what architecture?"
)

echo "=== Submitting ${#TASKS[@]} tasks simultaneously ==="

IDS=()
for desc in "${TASKS[@]}"; do
  resp=$(curl -s -X POST "$API/tasks" \
    -H "X-API-Key: $KEY" \
    -H "Content-Type: application/json" \
    -d "{\"description\": \"$desc\"}")
  id=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['task_id'])")
  IDS+=("$id")
  echo "  Queued: $id — $desc"
done

echo ""
echo "=== Queue depth after submission ==="
curl -s "$API/health" | python3 -c "
import sys, json
h = json.load(sys.stdin)
q = h['queue']
print(f\"  queued={q['queued']}  running={q['running']}  capacity={q['capacity']}\")
"

echo ""
echo "=== Streaming results (waiting for all tasks to complete) ==="

for i in "${!IDS[@]}"; do
  id="${IDS[$i]}"
  echo ""
  echo "--- Task $((i+1)): $id ---"
  # Poll until done, then print result
  while true; do
    resp=$(curl -s "$API/tasks/$id" -H "X-API-Key: $KEY")
    status=$(echo "$resp" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
    if [[ "$status" == "done" || "$status" == "error" || "$status" == "cancelled" ]]; then
      echo "  Status: $status"
      echo "$resp" | python3 -c "
import sys, json
t = json.load(sys.stdin)
r = t.get('result') or {}
print('  Summary:', r.get('summary', r.get('error', 'n/a')))
cmds = r.get('commands_run', [])
if cmds:
    print('  Commands run:')
    for c in cmds:
        print('   ', c.get('command',''))
"
      break
    fi
    sleep 2
  done
done

echo ""
echo "=== All tasks complete ==="
