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

## Fase 1 — Repositorio y estructura (11-11-2026)

Hecho:
- Repositorio `pases-insis-lab` (público: las aprobaciones de environment en repos privados requieren
  GitHub Enterprise; se probó y la API responde 422 con GitHub Pro). Rama por defecto `Desa`.
- Estructura de Pacífico con dos esquemas demo (`INSIS_DEMO_CFG`, `INSIS_DEMO_PPX`) y cuatro pases:
  `0001-10001` (MERGE), `0002-10002` (q-literal + verificación previa ORA-20075), `0003-10003` (filtro de
  versión `'1'`/`'1.00'`, cubre dos US, sin ROLLBACK) y `0004-10004` (escribe en los dos esquemas, usa
  `ALLOCATE_ID`, pide reinicio).
- `releases/B1/manifest.yaml` con las columnas del Inventario.
- `tools/pases/pases.py`: compuerta de 11 chequeos genéricos (incluye el detector léxico del Anexo E),
  plan, ejecutar, revertir, paquete, inventario y siguiente-etiqueta.
- 31 pruebas con SQLcl simulado que cubren E5, E6–E11, E13–E17 sin base de datos.
- Workflows `pr-validacion.yml`, `liberar.yml`, `desplegar.yml`; actionlint sin errores.
- `db/setup/`: usuario `INSIS_DEPLOY` (clave por variable de entorno), esquemas demo, `PASE_CONTROL` y `PASE_ESTADO`.

Decisiones y diferencias con la guía v1.7:
- Los scripts de ejecución usan `WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK` (y `OSERROR EXIT FAILURE ROLLBACK`).
  El `EXIT` de SQL*Plus confirma por defecto lo pendiente: con el formato de la guía, un error a mitad de un
  pase deja grabado lo escrito desde el último COMMIT. **Confirmar el comportamiento con SQLcl en la Fase 4.**
- El código de salida `SQL.SQLCODE` se trunca a 8 bits (un SQLCODE múltiplo de 256 sale con 0): por eso el
  resultado no depende solo del código, también de que el log llegue a `FIN PASE` y no tenga `ORA-`/`SP2-`.
- Además del `<SEC>_<pase>.sql` con el formato de la guía, la ejecución automática usa `<SEC>_<pase>.run.sql`
  (mismo contenido + cabecera de trazabilidad y `SET FEEDBACK ON`), como hacía PASE_INSIS.
- Logs: `<SEC>_<pase>_attempt<n>_<RES>_<etiqueta>.log`. El sufijo `of<m>` de la trazabilidad final de
  Pacífico solo se conoce al cerrar la entrega; queda pendiente un comando que arme ese paquete consolidado.
- Resultado `PARCIAL` cuando el log tiene `Commit complete.` antes del error (caso 0045); `ALERTA` cuando un
  pase termina sin error con sentencias DML y 0 filas (caso `'1'` vs `'1.00'`).
- Un pase que falló no se reintenta con la misma etiqueta (regla del 0046); hace falta la etiqueta nueva
  de la corrección o `--reintentar` por decisión de CTI.
- Promoción a PRD: se verifica con los despliegues del environment `qa` de GitHub sobre el mismo commit. Un
  despliegue de qa solo termina en success si la entrega quedó completa.

Pendiente:
- `CHECK TILDES` posterior a cada pase (hoy el mojibake se detecta solo en la compuerta, sobre el repo).
- Prevuelo de `ALLOCATE_ID` no contempla tablas que registra un pase anterior de la misma entrega.
- (hecho) Protección de `Desa`: PR obligatorio, check *Compuerta* obligatorio y actualizado con Desa, sin revisión obligatoria, también para administradores, sin force push ni borrado.

## Fase 2 — Bases de datos QA y PRD (11-11-2026)

Hecho:
- `docker-compose.yml` con `oracle-qa` (puerto 1521) y `oracle-prd` (1522), imagen fijada
  `gvenzl/oracle-free:23.26.3-slim-faststart`, PDB `FREEPDB1`, volúmenes con nombre y healthcheck.
- Se inicializan solas con `db/setup/` (00 usuario `INSIS_DEPLOY`, 01 esquemas demo y permisos, 02 `PASE_CONTROL` y
  `PASE_ESTADO`). Sin errores en los logs de inicialización de ninguno de los dos.
- Claves en `.env` (no versionado, permisos 600), una por ambiente; `.env.example` como plantilla.
- Aceptación: con `INSIS_DEPLOY` conectan SQLcl y python-oracledb (modo thin) a las dos bases;
  `SELECT * FROM INSIS_DEPLOY.PASE_ESTADO` responde `0 rows selected`. `INSIS_DEPLOY` ve las 5 tablas demo,
  `DBA_OBJECTS` (inválidos: ninguno) y el catálogo `RB_ID_CONTROL`.

Observaciones:
- `CONNECT` por entrada estándar funciona con SQLcl (`sql -S /nolog`): la clave no queda en argv ni en el log.
- En shells no interactivos `~/.bashrc` no carga el PATH de SQLcl/Java: el runner necesitará el PATH en su
  propio archivo `.path` / `.env` (Fase 5).

## Fase 3 — Proceso manual AS-IS (11-11-2026)

Hecho:
- Etiqueta manual `rel-QA-B1-20261111` → `b2894e5` y ejecución en QA siguiendo la guía v1.7, sin `pases.py`,
  en una copia aparte del repositorio. 4 de 4 OK, 0 inválidos nuevos. Detalle en `docs/as-is-manual.md`.
- Confirmado contra Oracle real: con el formato de la guía, `WHENEVER SQLERROR EXIT` confirma lo pendiente
  al salir; con `ROLLBACK`, no. El código de salida se trunca a 8 bits (ORA-00904 → 136).
- `PASE_CONTROL` quedó vacía tras la ejecución manual: la brecha de registro que motiva la automatización.

Pendiente:
- Recrear la base de QA (`docker compose down -v` del servicio) antes de la Fase 5. Requiere confirmación.
