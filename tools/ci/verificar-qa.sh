#!/usr/bin/env bash
# Promoción a PRD: el commit tiene que tener un despliegue exitoso en el environment qa.
# Un despliegue de qa solo termina en success si pases.py dejó la entrega completa (todos APLICADO).
# Uso: verificar-qa.sh <sha>   (requiere GH_TOKEN y GITHUB_REPOSITORY)
set -euo pipefail
sha="$1"
ids=$(gh api "repos/${GITHUB_REPOSITORY}/deployments?environment=qa&sha=${sha}&per_page=100" --jq '.[].id')
for id in $ids; do
  estado=$(gh api "repos/${GITHUB_REPOSITORY}/deployments/${id}/statuses?per_page=1" --jq '.[0].state // ""')
  if [ "$estado" = "success" ]; then
    echo "Promoción OK: despliegue ${id} exitoso en QA sobre ${sha}"
    exit 0
  fi
done
echo "::error title=Promoción::El commit ${sha} no tiene un despliegue exitoso en QA. PRD solo acepta lo que pasó completo por QA."
exit 1
