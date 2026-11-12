# pases-insis-lab

Laboratorio que reproduce el procedimiento de pases de base de datos de INSIS con la **misma estructura y
nomenclatura** que se usa hoy (carpetas `DB/Deployments`, script de instalación único, `ROLLBACK`, SECUENCIA,
etiquetas `rel-<AMB>-<BLOQUE>-<AAAAMMDD>[-N]`, `DB/Releases/AAAAMMDD/<SEC>_<pase>.sql`, logs, hoja de
seguimiento y reporte "[Pase con error]") y lo **automatiza** con GitHub Actions.

## Estructura

```
DB/Deployments/{NNNN}-{US}-{DESC}/      un pase = una carpeta (master + ROLLBACK opcional)
DB/INSIS_DEMO_CFG/Tables/...            scripts por tabla, llamados desde el master con ../../
DB/INSIS_DEMO_PPX/Tables/...
DB/Releases/                             local del ejecutor, no se versiona
releases/<entrega>/manifest.yaml         reemplaza al Inventario Excel (mismas columnas; el .xlsx se genera)
tools/pases/pases.py                     la herramienta (validar · plan · ejecutar · revertir · paquete · inventario)
tools/pases/tests/                       pruebas con SQLcl simulado
db/setup/                                esquemas demo, usuario INSIS_DEPLOY y PASE_CONTROL
.github/workflows/                       pr-validacion · liberar · desplegar · revertir · paquete
```

## Flujo

```
PR a Desa ──► Compuerta (pr-validacion.yml) ──► merge
Liberar ──► rel-QA-B1-AAAAMMDD[-N] ──► Desplegar qa (se lanza solo) ──► aprobación ──► runner QA ──► BD QA
                     │ (la MISMA etiqueta, solo si quedó completa en QA)
                     └──────────────► Desplegar prd (número de cambio) ──► aprobación ──► runner PRD ──► BD PRD
```

## Uso local

```bash
python3 -m venv .venv && .venv/bin/pip install -r tools/pases/requirements.txt
.venv/bin/python -m pytest tools/pases -q
.venv/bin/python tools/pases/pases.py validar
.venv/bin/python tools/pases/pases.py paquete --manifiesto releases/B1/manifest.yaml --ambiente qa --etiqueta <etiqueta>
```

`ejecutar`, `revertir` y `plan` leen la conexión de `PASES_DB_USER`, `PASES_DB_PASSWORD` y `PASES_DB_DSN`.
Nunca se ejecuta con `SYS` ni `SYSTEM`.

## Documentación

| Documento | Contenido |
| --- | --- |
| [`docs/as-is-manual.md`](docs/as-is-manual.md) | El proceso manual de la guía, reproducido, y lo que se encontró |
| [`docs/escenarios.md`](docs/escenarios.md) | Los 17 escenarios del Bloque 2 ejecutados en el pipeline, con enlaces a cada ejecución |
| [`docs/diferencias-con-pacifico.md`](docs/diferencias-con-pacifico.md) | Qué no es igual a Pacífico, qué haría falta allá y qué falta confirmar |
| [`docs/bitacora.md`](docs/bitacora.md) | Bitácora por fase y decisiones |

## Bases del laboratorio

```bash
cp .env.example .env      # completar las claves
docker compose up -d      # oracle-qa :1521 y oracle-prd :1522 (FREEPDB1)
```
