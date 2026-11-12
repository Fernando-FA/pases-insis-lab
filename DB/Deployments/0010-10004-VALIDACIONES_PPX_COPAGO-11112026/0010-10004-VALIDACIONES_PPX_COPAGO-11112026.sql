/* Pase 0010-10004 (antes 0004-10004) - AM · Validaciones PPX de copago
   Esquemas: INSIS_DEMO_CFG, INSIS_DEMO_PPX
   Requiere reinicio del servidor de INSIS GEN: Sí */
PROMPT Actualizando Tabla Insis_Demo_Cfg.Cfg_Rules
@"../../INSIS_DEMO_CFG/Tables/cfg_rules/cfg_rules.10004.MERGE.sql"
PROMPT Actualizando Tabla Insis_Demo_Ppx.Ppx_Validations
@"../../INSIS_DEMO_PPX/Tables/ppx_validations/ppx_validations.10004.VALIDATE.sql"
COMMIT;
