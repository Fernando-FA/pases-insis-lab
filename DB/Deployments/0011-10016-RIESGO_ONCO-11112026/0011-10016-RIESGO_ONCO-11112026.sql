/* Pase 0011-10016 - ONCO · Riesgo base del producto oncológico
   Esquemas: INSIS_DEMO_CFG
   Requiere reinicio del servidor de INSIS GEN: No */
PROMPT Actualizando Tabla Insis_Demo_Cfg.Cpr_Risks
PROMPT Risk [ONCO]
@"../../INSIS_DEMO_CFG/Tables/cpr_risks/cpr_risks.10016.MERGE.sql"
COMMIT;
