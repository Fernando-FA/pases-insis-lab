"""Compuerta y analizador léxico (Anexo E de la guía)."""
import pases
from conftest import RAIZ_REAL

Q_CON_BLANCOS = """MERGE INTO T USING (SELECT q'~SELECT CASE
         WHEN 1 = 1 THEN 1

         ELSE 0
       END FROM DUAL~' D FROM DUAL) S ON (1 = 1)
 WHEN MATCHED THEN UPDATE SET X = 1;
"""


def chequeos(h, nivel="ERROR"):
    return sorted({x.chequeo for x in h if x.nivel == nivel})


def test_lexer_linea_en_blanco_dentro_de_q_literal():
    assert pases.analizar_sql(Q_CON_BLANCOS).lineas_en_blanco == [3]


def test_lexer_blanco_entre_sentencias_y_en_plsql_es_inofensivo():
    texto = "UPDATE T SET X = 1;\n\nDECLARE\n  V NUMBER;\n\nBEGIN\n  NULL;\nEND;\n/\n\nCOMMIT;\n"
    assert pases.analizar_sql(texto).lineas_en_blanco == []


def test_lexer_ignora_comillas_en_prompt_y_comentarios():
    texto = "PROMPT it's ok\n-- don't\n/* l'x */\nUPDATE T SET X = 'a''b';\n\nCOMMIT;\n"
    assert pases.analizar_sql(texto).lineas_en_blanco == []


def test_lexer_codigo_sin_literales():
    a = pases.analizar_sql("BEGIN X := 'IDCONTROL.ALLOCATE_ID(1)'; END;\n/\n")
    assert "ALLOCATE_ID" not in a.codigo


def test_repo_real_aprueba():
    h = pases.compuerta(RAIZ_REAL, pases.manifiestos_del_repo(RAIZ_REAL))
    assert chequeos(h) == []


def test_caso_0065_lineas_en_blanco(repo):
    f = repo.archivo("DB/INSIS_DEMO_CFG/Tables/cfg_rules/cfg_rules.10002.MERGE.sql")
    f.write_text(f.read_text(encoding="utf-8").replace("/* 2) Hospitalización: porcentaje */", "   "),
                 encoding="utf-8")
    h = pases.compuerta(repo.raiz, [repo.manifiesto])
    assert chequeos(h) == ["C07"]


def test_caso_0003_mojibake_y_bom(repo):
    f = repo.archivo("DB/INSIS_DEMO_CFG/Tables/cfg_products/cfg_products.10001.MERGE.sql")
    texto = f.read_text(encoding="utf-8").replace("Médico", "MÃ©dico")
    f.write_bytes(b"\xef\xbb\xbf" + texto.encode("utf-8"))
    h = pases.compuerta(repo.raiz, [repo.manifiesto])
    assert chequeos(h) == ["C08"]
    assert len([x for x in h if x.chequeo == "C08"]) == 2


def test_allocate_id_sin_owner(repo):
    f = repo.archivo("DB/INSIS_DEMO_PPX/Tables/ppx_validations/ppx_validations.10004.VALIDATE.sql")
    f.write_text(f.read_text(encoding="utf-8").replace("INSIS_DEMO_CFG.IDCONTROL.ALLOCATE_ID", "IDCONTROL.ALLOCATE_ID"),
                 encoding="utf-8")
    assert chequeos(pases.compuerta(repo.raiz, [repo.manifiesto])) == ["C09"]


def test_referencia_rota_y_exit_en_master(repo):
    master = pases.scripts_instalacion(repo.deployment("0001"))[0]
    master.write_text(master.read_text(encoding="utf-8").replace("10001.MERGE", "10001.MERG") + "EXIT\n",
                      encoding="utf-8")
    assert chequeos(pases.compuerta(repo.raiz, [repo.manifiesto])) == ["C05", "C10"]


def test_dos_scripts_de_instalacion_y_rollback_fuera_de_convencion(repo):
    d = repo.deployment("0002")
    (d / "0002-10002-OTRO.sql").write_text("COMMIT;\n", encoding="utf-8")
    d4 = repo.deployment("0004")
    rb = next(d4.glob("*ROLLBACK*"))
    rb.rename(d4 / "0004-10004-rollback.sql")
    assert chequeos(pases.compuerta(repo.raiz, [repo.manifiesto])) == ["C03", "C04"]


def test_dependencia_fuera_de_orden(repo):
    t = repo.manifiesto.read_text(encoding="utf-8").replace("depende_de: [0002-10002]", "depende_de: [0005-10005]")
    repo.manifiesto.write_text(t, encoding="utf-8")
    assert chequeos(pases.compuerta(repo.raiz, [repo.manifiesto])) == ["C06"]


def test_secuencia_repetida(repo):
    t = repo.manifiesto.read_text(encoding="utf-8").replace("secuencia: 4", "secuencia: 3")
    repo.manifiesto.write_text(t, encoding="utf-8")
    assert "C01" in chequeos(pases.compuerta(repo.raiz, [repo.manifiesto]))


def test_pase_fuera_del_manifiesto_es_aviso(repo):
    d = repo.raiz / "DB" / "Deployments" / "0072-68911-PLAN_TEC_4"
    d.mkdir()
    (d / "0072-68911-PLAN_TEC_4.sql").write_text("COMMIT;\n", encoding="utf-8")
    h = pases.compuerta(repo.raiz, [repo.manifiesto])
    assert chequeos(h) == [] and chequeos(h, "AVISO") == ["C11"]


def test_carpeta_fuera_de_patron_se_encuentra(repo):
    d = repo.deployment("0003")
    d.rename(d.parent / d.name.replace("0003-10003", "0003--10003"))
    h = pases.compuerta(repo.raiz, [repo.manifiesto])
    assert chequeos(h) == [] and "C02" in chequeos(h, "AVISO")


def test_siguiente_etiqueta(repo):
    assert pases.siguiente_etiqueta(repo.raiz, "qa", "B1", "20261111") == "rel-QA-B1-20261111-2"
    repo.etiquetar("rel-QA-B1-20261111-2")
    assert pases.siguiente_etiqueta(repo.raiz, "qa", "B1", "20261111") == "rel-QA-B1-20261111-3"
    assert pases.siguiente_etiqueta(repo.raiz, "prd", "B1", "20261111") == "rel-PRD-B1-20261111"


def test_resumen_marca_nuevos_y_modificados(repo):
    m = pases.manifiesto_o_error(repo.manifiesto)
    t = pases.resumen_entrega(repo.raiz, m, "rel-QA-B1-20261111", "qa", None)
    assert t.count("**nuevo**") == 4
    f = repo.archivo("DB/INSIS_DEMO_CFG/Tables/cfg_products/cfg_products.10003.UPDATE.sql")
    f.write_text(f.read_text(encoding="utf-8") + "-- ajuste\n", encoding="utf-8")
    repo.commit("modifica 0003")
    t = pases.resumen_entrega(repo.raiz, m, "rel-QA-B1-20261111-2", "qa", "rel-QA-B1-20261111")
    assert "| 03 | 0003-10003 |" in t and t.count("**modificado**") == 1 and t.count("sin cambios") == 3
