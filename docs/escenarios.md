# Escenarios del Bloque 2 en el pipeline

Cada escenario provoca una situación (normal o equivocada) y comprueba que el proceso la maneja. Los scripts
están en [`scripts/escenarios/`](../scripts/escenarios/). Las aprobaciones de environment las hace una persona.

| Tipo | Escenarios |
| --- | --- |
| Camino feliz | E1 |
| Camino alternativo | E13 |
| Pedidos indebidos que se bloquean | E2, E3, E4, E9 |
| Defectos del pase detectados antes (Compuerta en el PR) | E5, E16 |
| Errores en la base y su manejo | E6, E7, E8, E14, E15 |
| Protecciones de estado | E10, E11, E17 |
| Operación | E12 |

## Resultados

| # | Escenario | Esperado | Obtenido | Ejecución |
| --- | --- | --- | --- | --- |
| E1 | Camino feliz: B1 en QA y la misma etiqueta en PRD con número de cambio | QA y PRD completos; `PASE_ESTADO` coincide | ✅ `rel-QA-B1-20261111-4` en PRD con `CHG-0001`: 4/4 OK al primer intento en el runner PRD. Pase, estado y checksum iguales en QA y PRD; mismos datos | [QA](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43118519148) · [PRD](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43118997577) |
| E2 | PRD con una etiqueta que no pasó por QA | Bloqueado en "Promoción" sin pedir aprobación | ✅ `rel-QA-B1-20261111-7` (commit nuevo `521ac4c`): su despliegue en QA se rechazó en la aprobación y PRD con `CHG-0002` se detuvo en "Promoción": "no tiene un despliegue exitoso en QA". Sin pedir aprobación ni tocar la base. (Un intento previo con `-5` no aplicaba: era el mismo commit que `-4`, ya completo en QA) | [liberación](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43132451463) · [QA rechazado](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43132564875) · [PRD](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43132687201) |
| E3 | PRD sin número de cambio | Bloqueado | ✅ "PRD exige número de cambio ITSM", sin pedir aprobación | [run](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43119654285) |
| E4 | Desplegar desde `Desa` (no etiqueta) | Bloqueado | ✅ "Se ejecuta una etiqueta, nunca una rama", sin pedir aprobación | [run](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43119704688) |
| E5 | PR con líneas en blanco dentro de un `q'~...~'` (caso 0065) | La Compuerta falla; no se puede mergear | ✅ PR #10: "Compuerta sobre todos los manifiestos" rechaza con C07 (línea 8 del MERGE); el PR queda bloqueado | [PR #10](https://github.com/Fernando-FA/pases-insis-lab/pull/10) |
| E6 | Error a mitad de la entrega (caso 0046) | Corta en ese pase, reporte de la guía, anteriores `APLICADO` | ✅ B2 ciclo 2 (`-2`): 0005-10011 `APLICADO`; 0006-10012 cortó con `ORA-00904: "ORL"."RULE_TYPE_LINK_ID": invalid identifier` y quedó `ERROR`, su MERGE se deshizo (rollback). Reporte "[Pase con error] QA - 0006-10012" con pases en OK y log adjunto | [run](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43135286515) |
| E7 | Corrección de E6 por PR, etiqueta nueva | Retoma en el pase que falló (intento 2) | ✅ B2 ciclo 3 (`-3`): 0005-10011 figura `APLICADO` con `-2` y no se repite; 0006-10012 reanuda en el intento 2 y queda OK | [run](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43135871779) |
| E8 | Prerrequisito no cumplido (caso 0045) | Falla por prerrequisito sin ejecutar; variante parcial | ✅ B2 ciclo 3: 0007-10013 "Prerrequisito no cumplido: Riesgo ONCO del producto 1201 en CPR_RISKS (obtenido 0, mínimo 1)"; el pase no se ejecutó. CTI agrega el pase 0011-10016 con el riesgo antes de 0007. La variante parcial (escritura confirmada antes del error → `PARCIAL`) está probada en local | [run](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43135871779) |
| E9 | `pases.py` con `--commit` distinto | Se niega a ejecutar | ⏳ (probado en local contra Oracle, Fase 4) | |
| E10 | Modificar un pase ya aplicado y relanzar | "Contenido cambió, requiere decisión de CTI" | ⏳ (probado en local, Fase 4) | |
| E11 | Revertir un pase del que depende otro aplicado | Rechazado; ambos en orden inverso funciona | ⏳ (probado en local, Fase 4) | |
| E12 | Dos despliegues simultáneos al mismo ambiente | El segundo espera | ⏳ | |
| E13 | Paquete manual | Artefacto con scripts y LEEME, sin tocar la base | ✅ 4 scripts `<SEC>_<pase>.sql`, LEEME, hoja e Inventario .xlsx; sin aprobación ni base | [run](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43119753928) |
| E14 | Pase sin efecto (`'1'` vs `'1.00'`) | `ALERTA` y se detiene | ⏳ (probado en local, Fase 4) | |
| E15 | Tabla fuera del catálogo de `ALLOCATE_ID` | Prevuelo `FALTA`, no arranca | ✅ B2 ciclo 1 (`rel-QA-B2-20261111`): "PPX_VALIDATION no está registrada en INSIS_DEMO_CFG.RB_ID_CONTROL (pase 0009-10015)"; no se ejecutó ningún pase ni se escribió en `PASE_CONTROL` | [run](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43134603553) |
| E16 | PR con mojibake (caso 0003) | La Compuerta falla | ✅ PR #11: rechazado con C08 ("texto doblemente codificado"); el PR queda bloqueado | [PR #11](https://github.com/Fernando-FA/pases-insis-lab/pull/11) |
| E17 | Pase renumerado ya aplicado | No se reejecuta | ✅ B2 ciclo 1: el plan muestra `0010-10004` como "aplicado como 0004-10004 (renumerado)" y no lo programa | [run](https://github.com/Fernando-FA/pases-insis-lab/actions/runs/43134603553) |

## Entrega B2: ciclos de corrección

[`releases/B2/manifest.yaml`](../releases/B2/manifest.yaml) trae seis pases, y cinco tienen a propósito un defecto
del Bloque 2. Cada ciclo es un PR de corrección, una liberación y un despliegue en QA:

| Ciclo | Cambio en `Desa` | Qué debe pasar en QA | Escenarios |
| --- | --- | --- | --- |
| 1 | Entrega B2 con los defectos | Prevuelo `FALTA` por `PPX_VALIDATION` (0009): no arranca ningún pase. 0010 figura aplicado como 0004 | E15, E17 |
| 2 | 0009 usa `PPX_VALIDATIONS` | 0005 OK; 0006 corta con ORA-00904; reporte de error de la guía | E6 |
| 3 | 0006 sin la columna inexistente | 0006 intento 2 OK sin repetir 0005; 0007 falla por prerrequisito sin ejecutar | E7, E8 |
| 4 | Pase nuevo con el riesgo ONCO antes de 0007 | 0007 OK; 0008 `ALERTA` (0 filas) | E14 |
| 5 | 0008 con `IN ('1', '1.00')` y, a la vez, cambio en 0005 ya aplicado | No se ejecuta nada: "contenido cambió, requiere decisión de CTI" | E10 |
| 6 | Se deshace el cambio en 0005 | 0008 y 0009 OK; B2 completa en QA. Después la misma etiqueta va a PRD | E1 (B2) |

## Lo que dejaron los escenarios hasta ahora

- **Cada ejecución usa los workflows de la etiqueta.** La `-3` no pudo ir a PRD tras cambiar las reglas porque traía
  el `desplegar.yml` anterior. Un cambio de pipeline aplica a las etiquetas que se liberen después.
- **La promoción se verifica por commit, no por nombre de etiqueta.** Dos etiquetas sobre el mismo commit son la
  misma versión; por eso `liberar.yml` ya no crea una etiqueta si `Desa` no cambió.
- **Quien aprueba necesita ver qué aprueba.** El job previo publica "Qué se instala": pases de la etiqueta, cuáles
  son nuevos o modificados respecto de la anterior y, en PRD, el despliegue de QA que validó ese commit.
- **Las pruebas de la herramienta no deben depender de los pases del repositorio.** El primer intento de E5/E16
  falló en "Pruebas" y no en "Validar pases": las pruebas copiaban `DB/` y `releases/` reales, así que cualquier pase
  nuevo en B1, aunque fuera correcto, las rompía. Ahora usan una copia fija en `tools/pases/tests/datos/`.
