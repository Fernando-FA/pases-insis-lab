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
    datos=$(gh api "repos/${GITHUB_REPOSITORY}/deployments/${id}" --jq '"\(.ref) · \(.created_at[:16] | sub("T"; " ")) UTC · por \(.creator.login)"')
    url=$(gh api "repos/${GITHUB_REPOSITORY}/deployments/${id}/statuses?per_page=1" --jq '.[0].log_url // .[0].target_url // ""')
    echo "Promoción OK: despliegue ${id} exitoso en QA sobre ${sha} (${datos})"
    if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
      {
        echo "### Validado en QA"
        echo
        echo "El commit \`${sha:0:7}\` se desplegó completo en QA: ${datos}${url:+ · [ejecución](${url})}"
        echo
      } >> "$GITHUB_STEP_SUMMARY"
    fi
    exit 0
  fi
done
echo "::error title=Promoción::El commit ${sha} no tiene un despliegue exitoso en QA. PRD solo acepta lo que pasó completo por QA."
exit 1
