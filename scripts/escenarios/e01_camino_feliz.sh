#!/usr/bin/env bash
# E1 · Camino feliz: la etiqueta de QA desplegada con éxito se promueve a PRD (mismo commit) y se despliega con número de cambio.
# Uso: e01_camino_feliz.sh <etiqueta_qa> <numero_cambio>     Requiere aprobar `liberacion` y `prd`.
set -euo pipefail; source "$(dirname "$0")/lib.sh"
ETQ_QA="${1:?etiqueta rel-QA-... desplegada en QA}"; CHG="${2:?número de cambio, ej. CHG-0001}"
id=$(lanzar liberar.yml Desa -f ambiente=prd -f entrega=B1 -f etiqueta_qa="$ETQ_QA" -f alcance="Promoción de ${ETQ_QA}")
echo "1) liberar prd: aprobar 'liberacion' en $(gh run view "$id" -R "$R" --json url --jq .url)"; esperar "$id"
git fetch -q --tags origin
ETQ_PRD=$(git tag -l 'rel-PRD-B1-*' --points-at "$(git rev-parse "${ETQ_QA}^{commit}")" | sort -V | tail -1)
echo "   etiqueta PRD: ${ETQ_PRD} -> $(git rev-parse --short "${ETQ_PRD}^{commit}") (QA: $(git rev-parse --short "${ETQ_QA}^{commit}"))"
id=$(lanzar desplegar.yml "$ETQ_PRD" -f ambiente=prd -f accion=ejecutar -f numero_cambio="$CHG")
echo "2) desplegar prd: aprobar 'prd' en $(gh run view "$id" -R "$R" --json url --jq .url)"; esperar "$id"
