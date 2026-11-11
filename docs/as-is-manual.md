# Proceso manual actual (AS-IS), reproducido

Entrega **B1** aplicada en **QA** el 11-11-2026, siguiendo la *Guía de implementación de pases INSIS v1.7*
paso a paso, con las mismas herramientas que usa hoy el implementador (git + SQLcl) y sin `pases.py`.
La evidencia completa está en [`evidencia-as-is/`](evidencia-as-is/).

| Dato | Valor |
| --- | --- |
| Etiqueta | `rel-QA-B1-20261111` (anotada, creada a mano) |
| Commit | `b2894e50247a2b5caaa68046c57a6b234c323a65` |
| Ambiente | QA · `localhost:1521/FREEPDB1` (contenedor `oracle-qa`) |
| Usuario | `INSIS_DEPLOY` (no `SYS`) |
| Cliente | SQLcl 26.3.1 |
| Resultado | 4 de 4 pases OK · 0 objetos inválidos nuevos · reinicio de INSIS GEN requerido (0003, 0004) |

## 1. Quien libera la entrega (Anexo B)

```bash
git fetch origin --prune --tags
git rev-parse origin/Desa                 # b2894e50247a2b5caaa68046c57a6b234c323a65
git log origin/Desa --oneline -1
python tools/pases/pases.py validar       # equivale a .\compuerta.ps1 origin/Desa -> APROBADA 11/11
git tag -a rel-QA-B1-20261111 b2894e5 -F mensaje-de-la-entrega.txt
git push origin rel-QA-B1-20261111
git ls-remote --tags origin               # dos líneas: objeto de la etiqueta y ^{} -> b2894e5
git show rel-QA-B1-20261111
```

Se entregan juntos: etiqueta + inventario + guía.

## 2. Implementador (secciones 3 a 5)

En una copia propia del repositorio (`~/implementador-qa/pases-insis-lab`), como la PC del implementador.

**Paso 1 — Versión fija.**

```bash
git fetch origin --tags
git checkout -b release/20261111 rel-QA-B1-20261111
git rev-parse HEAD                        # b2894e5... = commit de la guía -> se sigue
```

**Paso 2 — Cada pase existe.** `ls -d DB/Deployments/0001-10001*` … (4 de 4).

**Paso 3 — Carpeta.** `mkdir DB/Releases/20261111`

**Paso 4 — Un script de ejecución por pase**, escrito a mano con el formato de la guía
([`01_0001-10001.sql`](evidencia-as-is/01_0001-10001.sql)):

```sql
/* SEC 01 - Pase 0001-10001 - Ambiente QA */
SET DEFINE OFF
WHENEVER OSERROR EXIT
WHENEVER SQLERROR EXIT SQL.SQLCODE
SPOOL 01_0001-10001.log
PROMPT ===== INICIO PASE 0001-10001 =====
@"../../Deployments/0001-10001-PRODUCTO_SALUD_DATOS_GENERALES-11112026/0001-10001-PRODUCTO_SALUD_DATOS_GENERALES-11112026.sql"
PROMPT ===== FIN PASE 0001-10001 =====
SPOOL OFF
EXIT
```

Y la hoja de seguimiento vacía, una fila por pase.

**Paso 5 — Validación del DBA.** Un script por pase, numerados por SECUENCIA, cada `@` apunta a la carpeta
de su pase (se comprobó que las 4 rutas existen).

**Paso 6 — Foto de inválidos (antes).** `dba_objects` con `status = 'INVALID'` y `owner LIKE 'INSIS%'`:
0 filas ([`FOTO_ANTES.log`](evidencia-as-is/FOTO_ANTES.log), que además guarda los datos de referencia).

**Paso 7 — Ejecutar uno por uno.**

```bash
cd DB/Releases/20261111
export NLS_LANG=AMERICAN_AMERICA.AL32UTF8 && echo $NLS_LANG
sql INSIS_DEPLOY@localhost:1521/FREEPDB1 @01_0001-10001.sql    # la clave se ingresa en el prompt
echo $?                                                         # 0
tail -5 01_0001-10001.log                                       # termina en ===== FIN PASE 0001-10001 =====
grep -n -E "SP2-|ORA-|OS Message" 01_0001-10001.log             # sin líneas
# anotar inicio, fin y resultado en la hoja; repetir con 02, 03, 04
```

| SEC | Pase | Inicio | Fin | Resultado | Log |
| --- | --- | --- | --- | --- | --- |
| 01 | 0001-10001 | 15:28:11 | 15:28:12 | OK | [log](evidencia-as-is/01_0001-10001.log) |
| 02 | 0002-10002 | 15:28:12 | 15:28:14 | OK | [log](evidencia-as-is/02_0002-10002.log) |
| 03 | 0003-10003 | 15:28:14 | 15:28:15 | OK | [log](evidencia-as-is/03_0003-10003.log) |
| 04 | 0004-10004 | 15:28:15 | 15:28:17 | OK | [log](evidencia-as-is/04_0004-10004.log) |

**Paso 8 — Foto de inválidos (después).** 0 filas: ningún inválido nuevo ([`FOTO_DESPUES.log`](evidencia-as-is/FOTO_DESPUES.log)).

| Tabla | Antes | Después | Pase |
| --- | --- | --- | --- |
| `CFG_PRODUCTS` 1101 · NAME | Auxilio Médico | Auxilio Médico - Salud Individual | 0001 |
| `CFG_PRODUCTS` 1101 · RENEWAL_DAYS | (vacío) | 30 | 0003 |
| `CFG_RULES` | 0 filas | `KW_COPAGO_AM`, `KW_VALIDA_COPAGO_AM` | 0002, 0004 |
| `PPX_VALIDATIONS` | 0 filas | `VAL_COPAGO_AM` (ID 7001 de `ALLOCATE_ID`) | 0004 |

**Paso 9 — Reinicio.** El 0003 y el 0004 lo piden: **un** reinicio de INSIS GEN al final (en el laboratorio no aplica).

**Paso 10 — Informe.** Ambiente, fecha, etiqueta y commit, hoja de seguimiento y logs a desarrollo.

## 3. Comprobaciones contra Oracle real

Con la base de QA ya aplicada (y que luego se recrea) se probaron dos supuestos de la guía:

| Prueba | Resultado |
| --- | --- |
| Script con el formato de la guía: `UPDATE` sin COMMIT y luego un error (ORA-00904) | El `UPDATE` **quedó confirmado** (`RENEWAL_DAYS = 99`): `WHENEVER SQLERROR EXIT` hace COMMIT de lo pendiente al salir |
| Mismo script con `WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK` | No quedó nada escrito |
| Código de salida ante ORA-00904 | **136** (= 904 % 256): el código se trunca a 8 bits; un SQLCODE múltiplo de 256 saldría con 0 |

Consecuencia para Pacífico: con el formato actual, todo pase que falla a mitad deja escrito lo que hizo desde
su último COMMIT (no solo los que tienen COMMIT intermedios, como el 0045). Se propone agregar `ROLLBACK` a
las dos líneas `WHENEVER` del script de ejecución. Y `ERRORLEVEL` no alcanza solo: la revisión del log
(FIN PASE + búsqueda de `ORA-`/`SP2-`) es indispensable.

## 4. Lo que el proceso manual no deja (y dónde se puede equivocar una persona)

| Punto | Qué pasa hoy | Riesgo observado en el Bloque 2 |
| --- | --- | --- |
| Registro en la base | `PASE_CONTROL` quedó **vacía**: la base no sabe qué pases tiene ni con qué etiqueta | El Bloque 1 "no está verificado contra la base" |
| Scripts de ejecución | Se escriben a mano, copiando nombres de carpeta | Nombres fuera de patrón (`0026--63894`, `0034-59844_…`) |
| Orden | Se toma del Excel | Reordenamientos (0031/0069, 0032) |
| Verificar commit | Un `git rev-parse` que alguien tiene que mirar | 2.º intento del 0046 con el commit anterior |
| Revisión de cada log | Tres comprobaciones a ojo por pase | Un error que no corta el pase pasa si no se busca |
| Hoja de seguimiento | Se llena a mano | Diferencias entre hoja, Excel y guía |
| Reanudación | Columna nueva en el Excel (`SECUENCIA 0511`) | Saber qué ya corrió con qué etiqueta |
| Dónde corre | En la PC de una persona | Dependencia de una persona y de su equipo |

Tiempo de esta reproducción: unos 5 minutos para 4 pases, con todo preparado; la ejecución en sí fueron 6
segundos. En el Bloque 2 real (41 pases, 4 etiquetas, 45 intentos) el trabajo manual escala con cada pase y cada corte.
