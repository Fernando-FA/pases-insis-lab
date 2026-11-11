# Funciones comunes de los escenarios (requiere gh autenticado). Uso: source scripts/escenarios/lib.sh
R="${R:-Fernando-FA/pases-insis-lab}"

# lanzar <workflow> <ref> [-f clave=valor ...] -> imprime el id del run nuevo
lanzar() {
  local wf="$1" ref="$2"; shift 2
  local antes; antes=$(gh run list -R "$R" --workflow "$wf" --limit 1 --json databaseId --jq '.[0].databaseId // 0')
  gh workflow run "$wf" -R "$R" --ref "$ref" "$@" >/dev/null || return 1
  for _ in $(seq 1 40); do
    local id; id=$(gh run list -R "$R" --workflow "$wf" --limit 1 --json databaseId --jq '.[0].databaseId // 0')
    if [ "$id" != "$antes" ]; then echo "$id"; return 0; fi
    sleep 3
  done
  echo "no apareció el run de $wf" >&2; return 1
}

# estado <run> -> resumen: conclusión, url, jobs y anotaciones de error
estado() {
  gh run view "$1" -R "$R" --json status,conclusion,url,displayTitle,jobs \
    --jq '"\(.displayTitle) · \(.status) \(.conclusion // "") · \(.url)", (.jobs[] | "   \(.name): \(.status) \(.conclusion // "")")'
  gh api "repos/$R/check-runs/$(gh run view "$1" -R "$R" --json jobs --jq '[.jobs[] | select(.conclusion=="failure")][0].databaseId // empty')/annotations" \
    --jq '.[] | select(.annotation_level=="failure") | "   ✗ \(.message)"' 2>/dev/null | grep -v "Process completed with exit code" || true
}

# esperar <run> -> espera a que termine (incluye el tiempo de aprobación) y muestra el estado
esperar() { gh run watch "$1" -R "$R" --interval 10 >/dev/null 2>&1; estado "$1"; }
