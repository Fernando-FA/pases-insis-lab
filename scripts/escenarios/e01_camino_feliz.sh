#!/usr/bin/env bash
# E1 · Camino feliz: la etiqueta ya desplegada completa en QA se instala tal cual en PRD, con número de cambio.
# Uso: e01_camino_feliz.sh <etiqueta_qa> <numero_cambio>     Requiere aprobar `prd`.
set -euo pipefail; source "$(dirname "$0")/lib.sh"
ETQ="${1:?etiqueta rel-QA-... desplegada completa en QA}"; CHG="${2:?número de cambio, ej. CHG-0001}"
id=$(lanzar desplegar.yml "$ETQ" -f ambiente=prd -f numero_cambio="$CHG")
echo "desplegar prd: aprobar 'prd' en $(gh run view "$id" -R "$R" --json url --jq .url)"; esperar "$id"
