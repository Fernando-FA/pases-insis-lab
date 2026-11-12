#!/usr/bin/env bash
# E5 y E16: un desarrollador abre un PR con un pase defectuoso y la Compuerta lo rechaza (no se puede mergear).
#   E5  - línea en blanco dentro de un q'~...~' (caso 0065: ORA-01756 en QA)
#   E16 - texto con mojibake "PÃ³liza" (caso 0003: archivo guardado dos veces en UTF-8)
# Cada PR agrega a B1 un pase 0005-10006 nuevo. Los PR quedan abiertos como evidencia y no se mergean.
# Uso: scripts/escenarios/e05_e16_compuerta.sh e05|e16
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
caso="${1:?e05|e16}"
rama="escenario/${caso}-compuerta"
pase=0005-10006
carpeta="DB/Deployments/${pase}-REGLA_DEDUCIBLE_AM-11112026"
merge=DB/INSIS_DEMO_CFG/Tables/cfg_rules/cfg_rules.10006.MERGE.sql

git fetch -q origin Desa
git switch -q -c "$rama" origin/Desa

case "$caso" in
  e05) descripcion='Deducible según tipo de atención'; blanco=$'\n'
       titulo="E5: pase 0005-10006 con línea en blanco dentro de un q'~...~'" ;;
  e16) descripcion='Deducible de la PÃ³liza segÃºn atenciÃ³n'; blanco=''
       titulo="E16: pase 0005-10006 con mojibake" ;;
  *) echo "caso desconocido: $caso" >&2; exit 2 ;;
esac

cat > "$merge" <<SQL
MERGE INTO INSIS_DEMO_CFG.CFG_RULES R
USING (SELECT '1101' PRODUCT_CODE,
              'KW_DEDUCIBLE_AM' RULE_CODE,
              'KEYWORD' RULE_TYPE,
              '${descripcion}' DESCRIPTION,
              q'~SELECT CASE
         WHEN :ATTENTION_TYPE = 'AMB' THEN 50
${blanco}         WHEN :ATTENTION_TYPE = 'HOS' THEN 200
         ELSE 0
       END AS DATA
  FROM DUAL~' DEFINITION
         FROM DUAL) S
   ON (R.RULE_CODE = S.RULE_CODE)
 WHEN MATCHED THEN UPDATE SET R.DESCRIPTION = S.DESCRIPTION, R.DEFINITION = S.DEFINITION
 WHEN NOT MATCHED THEN INSERT (RULE_ID, PRODUCT_CODE, RULE_CODE, RULE_TYPE, DESCRIPTION, DEFINITION)
      VALUES (INSIS_DEMO_CFG.CFG_RULES_SEQ.NEXTVAL, S.PRODUCT_CODE, S.RULE_CODE, S.RULE_TYPE, S.DESCRIPTION, S.DEFINITION);
SQL

mkdir -p "$carpeta"
cat > "$carpeta/${pase}-REGLA_DEDUCIBLE_AM-11112026.sql" <<'SQL'
/* Pase 0005-10006 - AM · Regla de deducible
   Esquemas: INSIS_DEMO_CFG
   Requiere reinicio del servidor de INSIS GEN: No */
PROMPT Actualizando Tabla Insis_Demo_Cfg.Cfg_Rules
PROMPT Rule [KW_DEDUCIBLE_AM]
@"../../INSIS_DEMO_CFG/Tables/cfg_rules/cfg_rules.10006.MERGE.sql"
COMMIT;
SQL
cat > "$carpeta/${pase}-REGLA_DEDUCIBLE_AM-ROLLBACK-11112026.sql" <<'SQL'
/* Reversión del pase 0005-10006 */
DELETE FROM INSIS_DEMO_CFG.CFG_RULES WHERE RULE_CODE = 'KW_DEDUCIBLE_AM';
COMMIT;
SQL

cat >> releases/B1/manifest.yaml <<'YAML'

  - secuencia: 5
    pase: 0005-10006
    sprint: 3
    us: [10006]
    task: 20006
    descripcion: AM · Regla de deducible
    estado_task: Done
    reinicio_insis_gen: false
    depende_de: [0001-10001]
    prerrequisitos: []
YAML

git add -A DB releases
git commit -q -m "$titulo"
git push -q -u origin "$rama"
gh pr create --base Desa --head "$rama" --draft --title "$titulo" \
  --body "Escenario ${caso^^} del Bloque 2: la Compuerta debe fallar y el PR no se puede mergear. No mergear."
git switch -q Desa
