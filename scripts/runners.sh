#!/usr/bin/env bash
# Runners propios del laboratorio (WSL): ~/actions-runner-qa (insis-db,qa) y ~/actions-runner-prd (insis-db,prd).
# Uso: scripts/runners.sh iniciar | detener | estado
set -uo pipefail
accion="${1:-estado}"
for amb in qa prd; do
  dir="$HOME/actions-runner-$amb"
  pid=$(pgrep -f "$dir/bin/Runner.Listener" | head -1 || true)
  case "$accion" in
    iniciar)
      if [ -n "$pid" ]; then echo "$amb: ya corre (pid $pid)"; continue; fi
      (cd "$dir" && setsid nohup ./run.sh >> "$dir/runner.log" 2>&1 < /dev/null &)
      sleep 2; echo "$amb: iniciado (log $dir/runner.log)";;
    detener)
      if [ -n "$pid" ]; then pkill -f "$dir/run.sh"; kill "$pid"; echo "$amb: detenido"; else echo "$amb: no corre"; fi;;
    estado)
      if [ -n "$pid" ]; then echo "$amb: corre (pid $pid)"; else echo "$amb: detenido"; fi;;
  esac
done
