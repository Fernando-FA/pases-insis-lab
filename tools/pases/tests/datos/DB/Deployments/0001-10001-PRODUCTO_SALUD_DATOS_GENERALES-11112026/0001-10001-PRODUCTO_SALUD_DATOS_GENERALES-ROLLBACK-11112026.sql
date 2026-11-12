/* Rollback pase 0001-10001: vuelve el producto 1101 a su configuración base */
PROMPT Revirtiendo Tabla Insis_Demo_Cfg.Cfg_Products
UPDATE INSIS_DEMO_CFG.CFG_PRODUCTS
   SET NAME = 'Auxilio Médico',
       RENEWAL_DAYS = NULL
 WHERE PRODUCT_CODE = '1101';
COMMIT;
