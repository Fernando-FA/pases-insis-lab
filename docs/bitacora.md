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
- (hecho) Base de QA recreada limpia al terminar la fase.

## Fase 4 — Herramienta contra Oracle real (11-11-2026)

Hecho (desde la terminal, contra `oracle-qa`, sin GitHub):
- `plan` y `ejecutar` de la etiqueta `rel-QA-B1-20261111`: 4 de 4 OK, `PASE_ESTADO` con los 4 `APLICADO`,
  evidencia completa (logs, scripts, hoja, ESTADO, VERIFICAR, inválidos antes/después). La clave no aparece en ningún archivo.
- Reejecución sin pendientes; `revertir 0002` rechazado (0004 depende); `revertir 0002 0004` en orden inverso;
  volver a aplicar lo revertido (intento 2). `paquete` genera scripts, LEEME, hoja e Inventario .xlsx.
- Escenarios con commits y etiquetas locales (no publicados) sobre la base real:

| Caso | Resultado contra Oracle real |
| --- | --- |
| 0046 · columna inexistente a mitad de pase | ERROR `L14: SQL Error: ORA-00904…`; el UPDATE previo se deshizo (SQLcl imprime `Rollback`) |
| 0046 · misma etiqueta otra vez | Bloqueado: "se reanuda con la etiqueta nueva" |
| 0046 · corrección + etiqueta nueva | Retoma en ese pase, intento 2, sin repetir los aplicados |
| 0045 · COMMIT y luego ORA-20075 en PL/SQL | PARCIAL; log idéntico al real (`DECLARE * ERROR at line 1: ORA-20075`) |
| 0045 · pase BASE antes en la secuencia + etiqueta nueva | BASE OK y el pase retoma (intento 2) OK |
| 0031/0068/0069 · filtro `'1'` con `'1.00'` en la base | ALERTA "pase sin efecto: 1 sentencia DML y 0 filas" |
| 0065 · línea en blanco en q-literal | La compuerta lo rechaza (C07, línea exacta); ejecutado igual, SQLcl da el mismo ORA-01756 del Bloque 2 |
| Prerrequisito del manifiesto no cumplido | ERROR sin generar ni ejecutar el script |
| Commit distinto al indicado | Se niega a ejecutar |
| Pase aplicado cuyo contenido cambió | Se detiene: "requiere decisión de CTI" |
| Tabla fuera de `RB_ID_CONTROL` | El prevuelo da FALTA y no arranca |
| Usuario SYS | Se niega a ejecutar |

- Pruebas de integración `pytest -m oracle` (`tests/test_oracle.py`, 6): conexión thin, vistas de control y la
  lectura de la salida real de SQLcl (OK sin efecto, ORA-00904 con código 136, ORA-20075 en PL/SQL, ORA-01756).
  No escriben datos y se saltan si no hay `PASES_TEST_DSN`/`PASES_TEST_PASSWORD` (como en la Compuerta).

Hallazgos:
- No hizo falta corregir `pases.py`: la detección escrita para la salida de SQLcl de los logs reales del Bloque 2
  coincide con la salida de SQLcl 26.3.
- SQLcl escribe `Picked up JAVA_TOOL_OPTIONS` en la consola por `-Dfile.encoding=UTF-8`; queda en la salida de
  consola (02_CONTROLES), no en el log del pase.

## Fase 5 — GitHub: environments, runners y workflows (11-11-2026)

Hecho:
- Environments con revisor obligatorio (yo, sin *prevent self-review*) y restricción de referencias:
  `liberacion` (rama `Desa`), `qa` y `qa-rollback` (etiquetas `rel-QA-*`), `prd` y `prd-rollback` (`rel-PRD-*`).
- Variables por environment (`PASES_DB_USER`, `PASES_DB_DSN`, `PASES_ESQUEMA_CONTROL`, `PASES_CLIENTE=sql`) y
  secreto `PASES_DB_PASSWORD` cargado desde `.env` por entrada estándar.
- Aprobación obligatoria de workflows para PRs de forks (el repo es público y tiene runners propios).
- Runners propios v2.338.2 (checksum verificado) en `~/actions-runner-qa` (`insis-db,qa`) y
  `~/actions-runner-prd` (`insis-db,prd`), en segundo plano con `scripts/runners.sh iniciar|detener|estado`.
  Requirió `libicu78` (`sudo apt-get install -y libicu78`).
- `liberar.yml` (qa) aprobado → etiqueta anotada `rel-QA-B1-20261111-2` con alcance y resultado de la compuerta.

Problemas y correcciones:
- Primer `desplegar.yml` en QA falló: el runner no tenía SQLcl en el PATH. `config.sh` reescribe `.path`/`.env`
  con el entorno del momento; hay que escribirlos **después** de configurar el runner (y sin rutas de Windows).
- Ese fallo mostró un defecto de `pases.py`: si el cliente SQL no existe se caía con traceback dejando el pase
  `EN_CURSO` en `PASE_CONTROL`. Corregido: se verifica el cliente antes de registrar nada y un error al lanzar el
  cliente se trata como error del pase. La fila `EN_CURSO` bloquea la reejecución hasta un `--reintentar`
  explícito (protección para ejecuciones interrumpidas), que es lo que pasó y cómo se retoma.
- Segundo intento (`rel-QA-B1-20261111-3`, con la corrección): `pases.py` se negó limpiamente ("no se encuentra el
  cliente SQL"), sin registrar nada. Causa: con `run.sh` el runner **no lee `.path`** (eso es solo para el
  servicio); el job hereda el entorno del proceso que lanza el runner. `scripts/runners.sh` ahora exporta
  `JAVA_HOME` y `PATH` antes de lanzar. Se relanzó el mismo job (sin etiqueta nueva: el defecto era del ejecutor,
  no del repositorio).
- Tercer intento: **OK**. Corrió en `lab-qa`, retomó el 0001 en el intento 2 ("reanuda tras EN_CURSO con
  rel-QA-B1-20261111-2") por el `reintentar` pedido, y aplicó 0002 a 0004. Entrega completa; evidencia publicada
  como artefacto `evidencia-qa-rel-QA-B1-20261111-3-2`; pide un reinicio de INSIS GEN (0003, 0004).
- Promoción: `tools/ci/verificar-qa.sh` reconoce el commit `9cba96e` (despliegue exitoso en QA) y rechaza
  `b2894e5` (la etiqueta manual de la Fase 3, que nunca pasó por el pipeline).

Aceptación de la fase: un PR a `Desa` corre la Compuerta; `liberar.yml` crea `rel-QA-B1-AAAAMMDD[-N]`;
`desplegar.yml` sobre la etiqueta pide aprobación, corre en el runner QA y publica la evidencia. Cumplida.

## Fase 6 — Decisión: PRD instala la misma etiqueta de QA (11-11-2026)

Al promover a PRD, `liberar.yml` no pudo crear `rel-PRD-B1-20261111` sobre el commit de la `-3`: GitHub rechaza que
el `GITHUB_TOKEN` cree una referencia sobre un commit cuyos workflows difieren de los actuales ("refusing to allow a
GitHub App to create or update workflow ... without `workflows` permission"). Pasaría cada vez que cambie un workflow
mientras una entrega espera en QA. Crear la etiqueta de PRD exigiría una identidad con permisos de workflows
(GitHub App o deploy key) o un paso manual.

Decisión: **QA y PRD instalan la misma etiqueta `rel-QA-…`**. Lo instalado en PRD es lo probado en QA por
construcción. PRD exige que ese commit tenga un despliegue completo y exitoso en QA, número de cambio y aprobación.
El hito "se instaló en PRD" queda en el despliegue de GitHub (aprobador, fecha, número de cambio) y en `PASE_CONTROL`.
- `liberar.yml` solo libera para QA. `desplegar.yml` y `pases.py` aceptan solo `rel-QA-*`; los environments
  `prd` y `prd-rollback` restringen a `rel-QA-*`.
- Pendiente confirmar con Pacífico cómo se hace hoy el pase a PRD (la guía v1.7 solo describe QA).

## Fase 6 — Ajustes del flujo tras E1–E4 y E13 (11-11-2026)

- **Sin cambios no hay etiqueta nueva:** `liberar.yml` falla en "Verificar entrega" si el HEAD de `Desa` ya tiene
  una etiqueta de la entrega (pasó con `-4`, `-5` y `-6`, las tres sobre `3767800`).
- **Liberar lanza QA:** al publicar la etiqueta, `liberar.yml` lanza `desplegar.yml` en QA, que queda esperando la
  aprobación de `qa`. PRD sigue lanzándose a mano porque requiere el número de cambio.
- **Resumen para quien aprueba** (`pases.py resumen`, en el job previo a la aprobación): pases de la etiqueta,
  reinicio, rollback y si son nuevos, modificados o sin cambios respecto de la etiqueta anterior; en PRD, el
  despliegue de QA que validó el commit (con enlace) y el número de cambio. El plan contra la base (qué ya está
  aplicado) sigue viéndose recién en el log; mostrarlo antes de aprobar requiere leer `PASE_CONTROL` con un
  usuario de solo lectura (pendiente para la revisión del modelo de aprobaciones).
- **Workflows separados:** `desplegar.yml` (ambiente, número de cambio, reintentar), `revertir.yml` (environment
  `<amb>-rollback`, pases obligatorios) y `paquete.yml` (sin environment ni base). Comparten el grupo de concurrencia
  `pases-bd-<amb>`, así que una reversión y un despliegue al mismo ambiente no corren a la vez.
