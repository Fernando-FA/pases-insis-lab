#!/usr/bin/env bash
# E2 · PRD con una etiqueta que no pasó por QA · E3 · PRD sin número de cambio · E4 · desplegar desde una rama.
# Ninguno debe llegar a pedir aprobación. Uso: e02_e04_bloqueos.sh <etiqueta_prd_valida>
set -euo pipefail; source "$(dirname "$0")/lib.sh"
ETQ_PRD_OK="${1:?etiqueta rel-PRD-... válida (para E3)}"

echo "== E2a · liberar prd desde la etiqueta manual de la Fase 3 (nunca pasó por el pipeline)"
id=$(lanzar liberar.yml Desa -f ambiente=prd -f entrega=B1 -f etiqueta_qa=rel-QA-B1-20261111); esperar "$id"

echo "== E2b · alguien crea a mano una rel-PRD sobre ese commit y lanza desplegar prd"
git fetch -q --tags origin
etq=rel-PRD-B1-20261111-90
git tag -a "$etq" rel-QA-B1-20261111^{commit} -m "E2: etiqueta PRD creada a mano, sin pasar por liberar.yml" && git push -q origin "refs/tags/$etq"
id=$(lanzar desplegar.yml "$etq" -f ambiente=prd -f accion=ejecutar -f numero_cambio=CHG-E2); esperar "$id"
git push -q origin --delete "refs/tags/$etq"; git tag -d "$etq" >/dev/null

echo "== E3 · desplegar prd sin número de cambio"
id=$(lanzar desplegar.yml "$ETQ_PRD_OK" -f ambiente=prd -f accion=ejecutar); esperar "$id"

echo "== E4 · desplegar qa lanzado desde la rama Desa"
id=$(lanzar desplegar.yml Desa -f ambiente=qa -f accion=ejecutar); esperar "$id"
