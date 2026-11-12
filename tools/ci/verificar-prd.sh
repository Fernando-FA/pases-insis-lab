#!/usr/bin/env bash
# Revertir en QA: un pase solo se revierte en QA si en PRD no está, o ya se revirtió allá. QA siempre tiene al menos
# lo que tiene PRD; si no, el próximo cambio se prueba en QA sobre una base distinta de la de PRD.
# No se conecta a PRD: lee ESTADO_PRD.csv de la evidencia más reciente de PRD (despliegue o reversión).
# Uso: verificar-prd.sh <pase> [<pase> ...]   (requiere GH_TOKEN y GITHUB_REPOSITORY)
set -euo pipefail
dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT

estado=""
while read -r run nombre fecha; do
  [ -n "$run" ] || continue
  rm -rf "$dir/a" && mkdir -p "$dir/a"
  gh run download "$run" -R "$GITHUB_REPOSITORY" -n "$nombre" -D "$dir/a" >/dev/null 2>&1 || continue
  estado=$(find "$dir/a" -name ESTADO_PRD.csv | head -1)
  if [ -n "$estado" ]; then
    origen="${nombre} (${fecha}) · https://github.com/${GITHUB_REPOSITORY}/actions/runs/${run}"
    break
  fi
done < <(gh api --paginate --slurp "repos/${GITHUB_REPOSITORY}/actions/artifacts?per_page=100" | jq -r '
  [.[].artifacts[] | select(.expired | not) | select(.name | test("^evidencia-(rollback-)?prd-"))]
  | sort_by(.created_at) | reverse | .[] | "\(.workflow_run.id) \(.name) \(.created_at[:16])"')

if [ -z "$estado" ]; then
  n=$(gh api "repos/${GITHUB_REPOSITORY}/deployments?environment=prd&per_page=1" --jq 'length')
  if [ "$n" != "0" ]; then
    echo "::error title=Estado de PRD::Hubo despliegues en PRD pero no hay evidencia vigente con ESTADO_PRD.csv; no se puede comprobar PRD"
    exit 1
  fi
  echo "PRD sin despliegues: se puede revertir en QA"
  exit 0
fi

echo "Estado de PRD tomado de ${origen}"
python3 - "$estado" "$origen" "$@" <<'PY'
import csv, os, sys
ruta, origen, pedidos = sys.argv[1], sys.argv[2], sys.argv[3:]
ultimo = {}
with open(ruta, encoding="utf-8-sig", newline="") as f:
    for fila in csv.DictReader(f, delimiter=";"):          # en orden de PASE_CONTROL.ID
        ultimo[fila["Pase"]] = fila
malos = []
for p in pedidos:
    f = ultimo.get(p)
    if f is None or (f["Modo"] == "ROLLBACK" and f["Estado"] == "OK"):
        print(f"[OK] {p}: {'no está en PRD' if f is None else 'revertido en PRD con ' + f['Etiqueta']}")
    else:
        malos.append(f"{p}: en PRD {f['Modo']} {f['Estado']} con {f['Etiqueta']} ({f['Fecha']})")
resumen = os.environ.get("GITHUB_STEP_SUMMARY")
if malos:
    texto = "PRD tiene estos pases; primero se revierten en PRD (o se pasa un cambio que los deshaga):\n" + \
            "\n".join(f"- {m}" for m in malos)
    print("::error title=Revertir en QA::" + texto.replace("\n", "%0A"))
    if resumen:
        open(resumen, "a", encoding="utf-8").write(f"### Rechazado: los pases están en PRD\n\n{texto}\n\nEstado de PRD: {origen}\n")
    sys.exit(1)
if resumen:
    open(resumen, "a", encoding="utf-8").write(f"Ningún pase pedido está aplicado en PRD (estado: {origen}).\n")
PY
