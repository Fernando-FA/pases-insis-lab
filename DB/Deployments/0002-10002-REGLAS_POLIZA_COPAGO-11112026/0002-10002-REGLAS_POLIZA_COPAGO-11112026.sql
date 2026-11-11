/* Pase 0002-10002 - AM · Reglas de póliza copago
   Esquemas: INSIS_DEMO_CFG
   Requiere reinicio del servidor de INSIS GEN: No */
-- Verificación previa: el riesgo HEALTH es configuración base y este pase no la crea.
DECLARE
  V_N NUMBER;
BEGIN
  SELECT COUNT(*) INTO V_N FROM INSIS_DEMO_CFG.CPR_RISKS WHERE RISK_CODE = 'HEALTH';
  IF V_N = 0 THEN
    RAISE_APPLICATION_ERROR(-20075, 'US10002: no existe el riesgo HEALTH en INSIS_DEMO_CFG.CPR_RISKS. Es configuracion base del producto de salud y este pase no la crea. Cargarla antes de aplicar.');
  END IF;
END;
/
PROMPT Actualizando Tabla Insis_Demo_Cfg.Cfg_Rules
PROMPT Rule [KW_COPAGO_AM]
@"../../INSIS_DEMO_CFG/Tables/cfg_rules/cfg_rules.10002.MERGE.sql"
COMMIT;
