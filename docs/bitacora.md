# Bitácora

## Fase 0 — Preparar la máquina (11-11-2026)

Hecho:
- WSL2 Ubuntu 26.04 sobre Windows con Docker Desktop (integración WSL activada). Docker 29.9.3, Compose v5.7.0.
- git 2.53, gh 2.92 (cuenta `Fernando-FA`, protocolo SSH), Python 3.14.4.
- Instalados en `~/.local` sin sudo: Temurin JDK 17.0.21, SQLcl 26.3.1, actionlint 1.7.12.
- Aceptación: `gh auth status` OK, `docker run hello-world` OK, `sql -V` OK.

Decisiones:
- El prototipo `pases-insis-pipeline.zip` no está disponible: se construye desde cero.
- Se conserva la nomenclatura de Pacífico: etiquetas `rel-QA-B<n>-AAAAMMDD[-N]` y `rel-PRD-B<n>-AAAAMMDD[-N]` sobre el mismo commit.
- Fuente del alcance: `releases/<entrega>/manifest.yaml` con las columnas del Inventario; el `.xlsx` se genera.
- Repositorio privado (GitHub Pro).

## Fase 1 — Repositorio y estructura

En curso.
