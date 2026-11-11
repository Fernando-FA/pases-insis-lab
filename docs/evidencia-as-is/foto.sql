SET FEEDBACK ON
SET SQLFORMAT ansiconsole
PROMPT ---- Objetos invalidos
SELECT owner, object_type, object_name FROM dba_objects WHERE status = 'INVALID' AND owner LIKE 'INSIS%' ORDER BY owner, object_type, object_name;
PROMPT ---- Datos
SELECT product_code, product_version, name, renewal_days FROM insis_demo_cfg.cfg_products ORDER BY 1;
SELECT rule_id, rule_code, rule_type FROM insis_demo_cfg.cfg_rules ORDER BY 1;
SELECT validation_id, validation_code, rule_code FROM insis_demo_ppx.ppx_validations ORDER BY 1;
SELECT table_name, last_id FROM insis_demo_cfg.rb_id_control ORDER BY 1;
