# Diferencias con Pacífico y qué haría falta allá

El laboratorio reproduce el proceso de pases de INSIS con la misma estructura y nomenclatura de Pacífico, pero corre
en una cuenta personal de GitHub, con dos bases Oracle Free en Docker y runners en una PC. Este documento lista lo
que **no** es igual y lo que haría falta para llevarlo al repositorio `dev-cti-inisis`.

## 1. Resumen

| Tema | Laboratorio | Pacífico (propuesta) | Esfuerzo |
| --- | --- | --- | --- |
| Repositorio | `pases-insis-lab`, público, rama `Desa` | `dev-cti-inisis`, rama `Desa` (sin cambios de estructura) | Bajo: se copian `tools/`, `.github/`, `releases/` |
| Bases | Oracle Free 23ai en Docker, `FREEPDB1` | Exadata, PDB `PDBINSIST01` (QA) y la de PRD | — |
| Esquemas | `INSIS_DEMO_CFG`, `INSIS_DEMO_PPX` | `INSIS_GEN_CFG_V10`, `INSIS_PPX_V10`, … | — |
| Runner | Dos runners en una PC (`insis-db,qa` / `insis-db,prd`) | Runners en la red de Pacífico con acceso a Exadata | Medio (sección 3) |
| Usuario de despliegue | `INSIS_DEPLOY` con permisos solo sobre los esquemas demo | Hoy se usa `SYS`: crear un usuario de despliegue | Medio (sección 5) |
| Clave de la base | Secreto `PASES_DB_PASSWORD` por environment | Key Vault leído con OIDC (los pasos ya están en `desplegar.yml`) | Bajo (sección 4) |
| Evidencia | Artefacto del workflow, 90 días | Además Blob Storage (paso ya condicionado en `desplegar.yml`) | Bajo |
| Aprobaciones | Una sola persona aprueba todo y mergea sin revisión | Roles separados (sección 2) | Configuración |
| Identidad del pipeline | `GITHUB_TOKEN` | `GITHUB_TOKEN` alcanza con la decisión "misma etiqueta en QA y PRD" | — |
| Número de cambio | Texto libre (`CHG-0001`) | Número ITSM real; opcionalmente validarlo contra la herramienta ITSM | Opcional |
| Herramienta | `tools/pases/pases.py` (Python + SQLcl) | Reemplaza a PASE_INSIS 6.0.2 y a `compuerta.ps1` | — |

## 2. Aprobaciones: quién hace qué

En el laboratorio todo lo aprueba la misma persona y `Desa` exige PR y Compuerta, pero 0 revisiones, porque no se
puede aprobar un PR propio. En Pacífico cada paso tiene dueño:

| Paso | Laboratorio | Propuesta para Pacífico |
| --- | --- | --- |
| PR a `Desa` | Compuerta obligatoria, 0 revisiones | Compuerta obligatoria **y** 1 revisión del líder técnico de CTI (`CODEOWNERS` sobre `DB/` y `releases/`) |
| Cambios a `tools/` y `.github/` | Igual que el resto | `CODEOWNERS`: responsable de pases (Globant) y plataforma de Pacífico |
| Liberar (`liberacion`) | Yo | Líder técnico de CTI o responsable de pases: fija la versión que se entrega |
| Desplegar en QA (`qa`) | Yo | Responsable de pases (Globant) |
| Desplegar en PRD (`prd`) | Yo, con número de cambio | TI de Pacífico, con número de cambio aprobado; **Prevent self-review** activado |
| Revertir (`qa-rollback`, `prd-rollback`) | Yo | QA: responsable de pases. PRD: TI de Pacífico + número de cambio |

Flujo resultante: CTI abre el PR → la Compuerta valida → el líder técnico revisa y mergea → libera la etiqueta → el
despliegue en QA queda esperando a Globant → con QA completo, Pacífico aprueba la misma etiqueta en PRD.

Lo que el laboratorio mostró sobre aprobar:

- **Quien aprueba ve qué aprueba.** Antes de pedir la aprobación se publica "Qué se instala": pases, reinicio,
  rollback, si cada pase es nuevo o modificado respecto de la etiqueta anterior y, en PRD, el despliegue de QA que
  validó ese commit.
- **Algunos rechazos llegan después de aprobar.** Un pase aplicado con contenido distinto (E10) o una reversión que
  deja dependientes (E11) se detectan cuando la herramienta ya está conectada a la base, después de la aprobación.
  Mejora posible: que el job previo consulte `PASE_ESTADO` en solo lectura y rechace antes de pedir la aprobación.
- **Cada despliegue pide su propia aprobación**, también cuando hay dos en cola para el mismo ambiente (E12).

## 3. Runners en la red de Pacífico

- Un runner (o un grupo) por ambiente, con las etiquetas `insis-db,qa` e `insis-db,prd`. El de PRD solo debe poder
  llegar a la base de PRD.
- Opciones: VM en la red de bases de datos o pod en AKS con Actions Runner Controller, idealmente efímero (un job
  por runner).
- Software: Python 3.12, SQLcl con JDK 17 y `git`. En el laboratorio `run.sh` del runner no toma el `PATH` de
  `.path`; `scripts/runners.sh` exporta `JAVA_HOME` y `PATH` antes de arrancarlo.
- Red: salida HTTPS a GitHub y acceso al listener de Oracle. No necesita puertos de entrada.
- El runner nunca guarda la clave: la recibe por job (secreto del environment o Key Vault).

## 4. Clave de la base: Key Vault con OIDC

`desplegar.yml` ya trae los pasos condicionados a `vars.AZURE_KEYVAULT`. Si la variable no existe, se usa el secreto
del environment. Para activarlos:

1. Registrar una aplicación en Entra ID con una credencial federada por environment, con sujeto
   `repo:<org>/dev-cti-inisis:environment:qa` y `...:environment:prd`. Así solo un job aprobado en ese environment
   obtiene el token.
2. Dar a esa identidad el permiso de lectura de secretos sobre el Key Vault de cada ambiente, y escritura en el
   contenedor `evidencia-pases` si se usa Blob.
3. Definir en cada environment las variables `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`,
   `AZURE_KEYVAULT` y, si aplica, `AZURE_STORAGE_ACCOUNT`. Eliminar el secreto `PASES_DB_PASSWORD`.

Esta parte del laboratorio (Fase 7) no se probó contra Azure.

## 5. Usuario de despliegue en lugar de SYS

- `pases.py` se niega a ejecutar con `SYS` o `SYSTEM`.
- El usuario necesita los permisos que usan los pases sobre los esquemas de INSIS: DML sobre las tablas de
  configuración y `EXECUTE` sobre los generadores de ID (`IDCONTROL.ALLOCATE_ID`). Si algún pase crea o modifica
  objetos (paquetes, vistas), también los privilegios DDL. Conviene revisar los pases del Bloque 2 para dimensionar
  esos permisos.
- La tabla `PASE_CONTROL` y la vista `PASE_ESTADO` (`db/setup/02_pase_control.sql`) se crean una vez por ambiente en
  el esquema del usuario de despliegue o en uno de control.
- El respaldo previo del DBA no está automatizado en el laboratorio. Sigue siendo un paso de Pacífico antes de
  aprobar PRD, o se puede agregar como paso del pipeline (por ejemplo, un *restore point*).

## 6. Hallazgos del laboratorio que aplican al proceso actual

Valen aunque no se adopte el pipeline:

| Hallazgo | Evidencia | Recomendación |
| --- | --- | --- |
| Con el script de la guía (`WHENEVER SQLERROR EXIT SQL.SQLCODE`), un error a mitad de un pase **confirma** lo escrito desde el último COMMIT | Probado contra Oracle: el `UPDATE` previo al ORA-00904 quedó grabado ([AS-IS](as-is-manual.md)) | Agregar `ROLLBACK` a `WHENEVER SQLERROR` y `OSERROR` en la guía |
| El código de salida se trunca a 8 bits (ORA-00904 → 136); un SQLCODE múltiplo de 256 saldría con 0 | Ídem | No confiar solo en `ERRORLEVEL`: revisar el log (`FIN PASE`, `ORA-`, `SP2-`) |
| `PASE_CONTROL` estaba vacía en QA | Trazabilidad del Bloque 2 | Registrar cada intento en la base |
| Una etiqueta de PRD distinta de la de QA puede no poder crearse con `GITHUB_TOKEN` si cambió un workflow | [Bitácora, Fase 6](bitacora.md) | Instalar en PRD la misma etiqueta probada en QA |
| Un pase que termina OK sin afectar filas pasa inadvertido | E14 (`'1'` vs `'1.00'`) | Marcarlo `ALERTA` y detener |

## 7. Revertir o pasar un cambio hacia atrás

`revertir` ejecuta el script `-ROLLBACK-` del pase sobre la misma etiqueta, en orden inverso y sin dejar dependientes
aplicados (sección 7 de la guía). No cambia el repositorio: el pase queda `REVERTIDO` solo en ese ambiente.

| | Revertir | Pase nuevo que deshace el cambio |
| --- | --- | --- |
| Tiempo | Inmediato | Ciclo completo: PR, liberación, QA y PRD |
| Repositorio | No cambia | El estado deseado queda en `Desa` |
| Ambientes | QA y PRD pueden quedar distintos | Siguen iguales |
| Validación | El rollback no se probó en QA | Se prueba en QA como cualquier pase |

Propuesta: revertir solo como contingencia (sobre todo en PRD) y, cuando se decide que un cambio no va, un pase
nuevo por el flujo normal.

## 8. Por confirmar con Pacífico

- Cómo se hace hoy el pase a PRD: la guía v1.7 solo describe QA.
- Quién aprueba cada environment (sección 2) y si `prd` debe exigir dos aprobadores.
- Integración con ITSM: texto libre o validación del número de cambio.
- Retención de la evidencia: 90 días como artefacto o permanente en Blob.
- Quién pide y confirma el reinicio de INSIS GEN: el pipeline solo avisa.
- Respaldo del DBA antes de PRD: manual o automatizado.
- Flyway (en evaluación en Pacífico): no se probó en el laboratorio (Fase 8 opcional).
