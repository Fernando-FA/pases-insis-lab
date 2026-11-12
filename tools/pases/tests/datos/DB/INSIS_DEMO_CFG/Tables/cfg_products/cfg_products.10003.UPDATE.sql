-- La versión puede estar grabada como '1' o '1.00' según el ambiente.
UPDATE INSIS_DEMO_CFG.CFG_PRODUCTS
   SET RENEWAL_DAYS = 30
 WHERE PRODUCT_CODE = '1101'
   AND PRODUCT_VERSION IN ('1', '1.00');
