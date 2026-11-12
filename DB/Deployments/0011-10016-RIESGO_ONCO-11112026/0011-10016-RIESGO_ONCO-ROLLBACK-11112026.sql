/* Rollback pase 0011-10016 */
PROMPT Revirtiendo Tabla Insis_Demo_Cfg.Cpr_Risks
DELETE FROM INSIS_DEMO_CFG.CPR_RISKS WHERE RISK_CODE = 'ONCO';
COMMIT;
