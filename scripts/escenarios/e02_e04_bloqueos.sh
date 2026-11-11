#!/usr/bin/env bash
# E2 · PRD con una etiqueta que no pasó completa por QA · E3 · PRD sin número de cambio · E4 · desplegar desde una rama.
# Ninguno debe llegar a pedir aprobación. Uso: e02_e04_bloqueos.sh <etiqueta_qa_completa>
set -euo pipefail; source "$(dirname "$0")/lib.sh"
ETQ_OK="${1:?etiqueta rel-QA-... desplegada completa en QA (para E3)}"

echo "== E2 · desplegar en PRD la etiqueta manual de la Fase 3 (nunca pasó por el pipeline de QA)"
id=$(lanzar desplegar.yml rel-QA-B1-20261111 -f ambiente=prd -f accion=ejecutar -f numero_cambio=CHG-E2); esperar "$id"

echo "== E3 · desplegar en PRD sin número de cambio"
id=$(lanzar desplegar.yml "$ETQ_OK" -f ambiente=prd -f accion=ejecutar); esperar "$id"

echo "== E4 · desplegar en QA lanzado desde la rama Desa"
id=$(lanzar desplegar.yml Desa -f ambiente=qa -f accion=ejecutar); esperar "$id"
