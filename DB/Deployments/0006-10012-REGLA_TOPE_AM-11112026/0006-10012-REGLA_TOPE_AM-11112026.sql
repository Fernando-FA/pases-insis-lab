/* Pase 0006-10012 - AM · Regla de tope anual
   Esquemas: INSIS_DEMO_CFG
   Requiere reinicio del servidor de INSIS GEN: No */
PROMPT Actualizando Tabla Insis_Demo_Cfg.Cfg_Rules
PROMPT Rule [KW_TOPE_AM]
@"../../INSIS_DEMO_CFG/Tables/cfg_rules/cfg_rules.10012.MERGE.sql"
COMMIT;
