#!/usr/bin/env bash
# E2 · PRD con una etiqueta liberada que NO pasó por QA · E3 · PRD sin número de cambio · E4 · desplegar desde una rama.
# Ninguno debe llegar a pedir aprobación.
# Uso: e02_e04_bloqueos.sh <etiqueta_sin_QA> <etiqueta_completa_en_QA>
#   <etiqueta_sin_QA>: liberada pero cuyo despliegue en QA se rechazó o no se aprobó (commit nunca instalado en QA).
set -euo pipefail; source "$(dirname "$0")/lib.sh"
ETQ_SIN_QA="${1:?etiqueta liberada que no pasó por QA}"; ETQ_OK="${2:?etiqueta completa en QA}"

echo "== E2 · desplegar en PRD una etiqueta que no pasó por QA"
id=$(lanzar desplegar.yml "$ETQ_SIN_QA" -f ambiente=prd -f numero_cambio=CHG-E2); esperar "$id"

echo "== E3 · desplegar en PRD sin número de cambio"
id=$(lanzar desplegar.yml "$ETQ_OK" -f ambiente=prd); esperar "$id"

echo "== E4 · desplegar en QA lanzado desde la rama Desa"
id=$(lanzar desplegar.yml Desa -f ambiente=qa); esperar "$id"
