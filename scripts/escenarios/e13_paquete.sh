#!/usr/bin/env bash
# E13 · Modo paquete: scripts <SEC>_<pase>.sql + LEEME + hoja + inventario, sin tocar la base ni pedir aprobación.
# Uso: e13_paquete.sh <etiqueta>
set -euo pipefail; source "$(dirname "$0")/lib.sh"
ETQ="${1:?etiqueta}"
id=$(lanzar desplegar.yml "$ETQ" -f ambiente=qa -f accion=paquete); esperar "$id"
d=$(mktemp -d); gh run download "$id" -R "$R" -D "$d" >/dev/null && (cd "$d" && find . -type f | sort)
