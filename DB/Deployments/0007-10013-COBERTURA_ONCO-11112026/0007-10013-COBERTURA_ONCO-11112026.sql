/* Pase 0007-10013 - ONCO · Cobertura oncológica
   Esquemas: INSIS_DEMO_CFG
   Requiere reinicio del servidor de INSIS GEN: No */
PROMPT Actualizando Tabla Insis_Demo_Cfg.Cfg_Rules
PROMPT Rule [KW_COBERTURA_ONCO]
@"../../INSIS_DEMO_CFG/Tables/cfg_rules/cfg_rules.10013.MERGE.sql"
COMMIT;
