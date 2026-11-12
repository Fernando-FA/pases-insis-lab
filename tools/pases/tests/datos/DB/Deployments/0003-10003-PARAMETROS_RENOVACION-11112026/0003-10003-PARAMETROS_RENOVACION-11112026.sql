/* Pase 0003-10003 - AM · Parámetros de renovación del producto 1101
   Esquemas: INSIS_DEMO_CFG
   Requiere reinicio del servidor de INSIS GEN: Sí
   Sin script de reversión: se revierte por respaldo. */
PROMPT Actualizando Tabla Insis_Demo_Cfg.Cfg_Products (renovacion)
@"../../INSIS_DEMO_CFG/Tables/cfg_products/cfg_products.10003.UPDATE.sql"
COMMIT;
