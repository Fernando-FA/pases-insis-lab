"""ejecutar · revertir · paquete con SQLcl simulado y PASE_CONTROL en memoria (escenarios del Bloque 2)."""
import csv

import pases
from conftest import checkout, correr, ultimo_error

TODOS = ["0001-10001", "0002-10002", "0003-10003", "0004-10004"]


def estados(control):
    return {p: e["ESTADO"] for p, e in control.estado().items()}


def evidencias(repo):
    return sorted((repo.raiz.parent / "evidencia").iterdir())


ERROR_0046 = ' -- FAKE_ERROR: ORA-00904: "ORL"."RULE_TYPE_LINK_ID": invalid identifier'
ANCLA_0003 = "SET RENEWAL_DAYS = 30"


def reemplazar(repo, rel, viejo, nuevo):
    f = repo.archivo(rel)
    t = f.read_text(encoding="utf-8")
    assert viejo in t
    f.write_text(t.replace(viejo, nuevo), encoding="utf-8")


ARCH_0003 = "DB/INSIS_DEMO_CFG/Tables/cfg_products/cfg_products.10003.UPDATE.sql"


def test_camino_feliz(repo, control):
    assert correr(repo, control, "ejecutar") == 0
    assert estados(control) == {p: "APLICADO" for p in TODOS}
    ev = evidencias(repo)[0]
    logs = sorted(x.name for x in (ev / "01_LOGS_POR_PASE").iterdir())
    assert logs[0] == "01_0001-10001_attempt1_OK_rel-QA-B1-20261111.log"
    texto = (ev / "01_LOGS_POR_PASE" / logs[0]).read_text(encoding="utf-8")
    assert "===== FIN PASE 0001-10001 =====" in texto and "PASES_INSIS" in texto
    assert "clave-de-prueba" not in texto
    hoja = list(csv.DictReader((ev / "HOJA_SEGUIMIENTO_QA.csv").open(encoding="utf-8-sig"), delimiter=";"))
    assert [h["Resultado"] for h in hoja] == ["OK"] * 4
    assert "Requiere un reinicio de INSIS GEN" in (ev / "RESUMEN.md").read_text(encoding="utf-8")
    assert (ev / "03_SCRIPTS" / "01_0001-10001.sql").read_text(encoding="utf-8").startswith(
        "/* SEC 01 - Pase 0001-10001 - Ambiente QA */")
    # Segunda corrida: nada pendiente, no repite
    assert correr(repo, control, "ejecutar") == 0
    assert len(control.filas) == 4


def test_e6_e7_corte_y_reanudacion_con_etiqueta_nueva(repo, control):
    """Caso 0046: corta en el pase con error y reanuda desde ahí con la etiqueta de la corrección."""
    reemplazar(repo, ARCH_0003, ANCLA_0003, ANCLA_0003 + ERROR_0046)
    repo.commit("pase con error")
    repo.etiquetar("rel-QA-B1-20261111-2")
    checkout(repo, "rel-QA-B1-20261111-2")
    assert correr(repo, control, "ejecutar", etiqueta="rel-QA-B1-20261111-2") == 1
    assert estados(control) == {"0001-10001": "APLICADO", "0002-10002": "APLICADO", "0003-10003": "ERROR"}
    ev = evidencias(repo)[-1]
    reporte = next((ev / "02_CONTROLES").glob("Pases_*_REPORTE_ERROR_03_0003-10003.txt")).read_text(encoding="utf-8")
    assert "Asunto: [Pase con error] QA - 0003-10003" in reporte
    assert "ORA-00904" in reporte and "Pases en OK:         0001-10001, 0002-10002" in reporte

    # Misma etiqueta: no se reintenta (hace falta la corrección de CTI)
    assert correr(repo, control, "ejecutar", etiqueta="rel-QA-B1-20261111-2") == 2

    # Corrección por PR + etiqueta -3: retoma en 0003 (intento 2) sin repetir 0001 y 0002
    checkout(repo, "Desa")
    reemplazar(repo, ARCH_0003, ERROR_0046, "")
    repo.commit("corrige 0003")
    repo.etiquetar("rel-QA-B1-20261111-3")
    assert correr(repo, control, "ejecutar", etiqueta="rel-QA-B1-20261111-3") == 0
    assert estados(control) == {p: "APLICADO" for p in TODOS}
    assert [f["PASE"] for f in control.filas] == TODOS[:3] + ["0003-10003", "0004-10004"]
    assert control.filas[3]["INTENTO"] == 2


def test_e8_prerrequisito_no_cumplido_no_ejecuta(repo, control):
    """Caso 0045 (variante declarada en el manifiesto): falla antes de ejecutar el pase."""
    m = pases.manifiesto_o_error(repo.manifiesto)
    control.escalares[m.buscar("0002-10002").prerrequisitos[0].sql] = 0
    assert correr(repo, control, "ejecutar") == 1
    assert estados(control)["0002-10002"] == "ERROR"
    assert "Prerrequisito no cumplido" in control.filas[1]["DETALLE"]
    ev = evidencias(repo)[-1]
    assert not (ev / "03_SCRIPTS" / "02_0002-10002.run.sql").exists()


def test_e8b_escritura_parcial(repo, control):
    """Caso 0045 real: escribió y confirmó parte antes de abortar -> PARCIAL."""
    f = repo.archivo(ARCH_0003)
    f.write_text(f.read_text(encoding="utf-8") + "COMMIT;\nUPDATE X SET Y = 1 -- FAKE_ERROR: ORA-20075: falta HEALTH\n;\n",
                 encoding="utf-8")
    repo.commit("0003 parcial")
    repo.etiquetar("rel-QA-B1-20261111-2")
    assert correr(repo, control, "ejecutar", etiqueta="rel-QA-B1-20261111-2") == 1
    assert estados(control)["0003-10003"] == "PARCIAL"


def test_e9_commit_distinto_se_niega(repo, control):
    assert correr(repo, control, "ejecutar", "--commit", "deadbeef") == 2
    assert control.filas == []


def test_no_ejecuta_desde_rama_ni_etiqueta_de_otro_ambiente(repo, control):
    assert correr(repo, control, "ejecutar", etiqueta="Desa") == 2
    repo.etiquetar("rel-PRD-B1-20261111")
    assert correr(repo, control, "ejecutar", etiqueta="rel-PRD-B1-20261111", ambiente="prd") == 2
    assert "liberada en QA" in ultimo_error()
    assert control.filas == []


def test_prd_instala_la_misma_etiqueta_de_qa(repo, control):
    assert correr(repo, control, "ejecutar", ambiente="prd") == 0
    assert {f["AMBIENTE"] for f in control.filas} == {"PRD"}
    assert {f["ETIQUETA"] for f in control.filas} == {"rel-QA-B1-20261111"}


def test_no_ejecuta_con_sys(repo, control, monkeypatch):
    monkeypatch.setenv("PASES_DB_USER", "SYS")
    assert correr(repo, control, "ejecutar") == 2 and "SYS" in ultimo_error()


def test_e10_contenido_cambiado_de_pase_aplicado(repo, control):
    assert correr(repo, control, "ejecutar") == 0
    f = repo.archivo("DB/INSIS_DEMO_CFG/Tables/cfg_products/cfg_products.10001.MERGE.sql")
    f.write_text(f.read_text(encoding="utf-8").replace("Salud Individual", "Salud"), encoding="utf-8")
    repo.commit("modifica 0001 ya aplicado")
    repo.etiquetar("rel-QA-B1-20261111-2")
    assert correr(repo, control, "ejecutar", etiqueta="rel-QA-B1-20261111-2") == 2
    assert "contenido cambió" in ultimo_error()
    assert len(control.filas) == 4


def test_e14_pase_sin_efecto(repo, control):
    """Caso '1' vs '1.00': termina sin error pero no afecta filas."""
    f = repo.archivo(ARCH_0003)
    f.write_text(f.read_text(encoding="utf-8").replace("IN ('1', '1.00');", "= '1'; -- FAKE_FILAS: 0"), encoding="utf-8")
    repo.commit("0003 con filtro '1'")
    repo.etiquetar("rel-QA-B1-20261111-2")
    assert correr(repo, control, "ejecutar", etiqueta="rel-QA-B1-20261111-2") == 1
    assert estados(control)["0003-10003"] == "ALERTA"
    assert "sin efecto" in control.filas[2]["DETALLE"]


def test_e15_prevuelo_allocate_id(repo, control):
    control.no_registradas.add("PPX_VALIDATIONS")
    assert correr(repo, control, "ejecutar") == 2 and "PPX_VALIDATIONS" in ultimo_error()
    assert control.filas == []


def test_e17_pase_renumerado_ya_aplicado(repo, control):
    control.filas.append(dict(ID=1, PASE="0009-10004", MODO="DEPLOY", RESULTADO="OK", ETIQUETA="rel-QA-B0-20261001",
                              CHECKSUM="x", ENTREGA="B0", INTENTO=1, COMMIT_SHA="abc1234"))
    t = repo.manifiesto.read_text(encoding="utf-8").replace(
        "    depende_de: [0002-10002]", "    depende_de: [0002-10002]\n    renumerado_de: 0009-10004")
    repo.manifiesto.write_text(t, encoding="utf-8")
    repo.commit("0004 renumerado")
    repo.etiquetar("rel-QA-B1-20261111-2")
    assert correr(repo, control, "ejecutar", etiqueta="rel-QA-B1-20261111-2") == 0
    assert "0004-10004" not in estados(control)


def test_objeto_invalido_nuevo_es_error(repo, control):
    orig = control.invalidos
    llamadas = {"n": 0}

    def invalidos():
        llamadas["n"] += 1
        return orig() | ({("INSIS_DEMO_CFG", "PACKAGE BODY", "IDCONTROL")} if llamadas["n"] > 1 else set())

    control.invalidos = invalidos
    assert correr(repo, control, "ejecutar") == 1
    assert estados(control)["0001-10001"] == "ERROR"


def test_e11_revertir_con_dependiente_aplicado_se_rechaza(repo, control):
    assert correr(repo, control, "ejecutar") == 0
    assert correr(repo, control, "revertir", "--pases", "0002-10002") == 2
    assert "0004-10004 depende" in ultimo_error()
    assert correr(repo, control, "revertir", "--pases", "0002-10002", "0004-10004") == 0
    rb = [f["PASE"] for f in control.filas if f["MODO"] == "ROLLBACK"]
    assert rb == ["0004-10004", "0002-10002"]
    assert estados(control)["0002-10002"] == "REVERTIDO"
    # Se vuelve a aplicar lo revertido
    repo.etiquetar("rel-QA-B1-20261111-2")
    assert correr(repo, control, "ejecutar", etiqueta="rel-QA-B1-20261111-2") == 0
    assert estados(control) == {p: "APLICADO" for p in TODOS}


def test_revertir_pase_sin_rollback(repo, control):
    assert correr(repo, control, "ejecutar") == 0
    assert correr(repo, control, "revertir", "--pases", "0003-10003") == 2
    assert "no tiene script de reversión" in ultimo_error()


def test_e13_paquete(repo, tmp_path):
    args = pases.parser().parse_args(["--raiz", str(repo.raiz), "paquete", "--manifiesto", str(repo.manifiesto),
                                      "--ambiente", "qa", "--salida", str(tmp_path / "paq")])
    assert pases.cmd_paquete(args) == 0
    paq = tmp_path / "paq" / "PAQUETE_QA_rel-QA-B1-20261111"
    dia = next(d for d in paq.iterdir() if d.is_dir())
    assert sorted(x.name for x in dia.iterdir()) == [f"{i:02d}_{p}.sql" for i, p in enumerate(TODOS, start=1)]
    s = (dia / "04_0004-10004.sql").read_text(encoding="utf-8")
    assert '@"../../Deployments/0004-10004-VALIDACIONES_PPX_COPAGO-11112026/' in s
    assert (paq / "LEEME.md").exists() and (paq / "Inventario_B1.xlsx").exists()


def test_revisar_log_formatos_sqlcl():
    log = "===== INICIO PASE 0046-53372 =====\nError starting at line : 2\nError report -\n" \
          "SQL Error: ORA-00904: \"ORL\".\"RULE_TYPE_LINK_ID\": invalid identifier\n"
    r = pases.revisar_log(log, "0046-53372", 136)
    assert r.resultado == "ERROR" and r.detalle.startswith("L4: SQL Error: ORA-00904")
    ok = "===== INICIO PASE X =====\n\n3 rows merged.\n\nCommit complete.\n===== FIN PASE X =====\n"
    assert pases.revisar_log(ok, "X", 0).resultado == "OK"
    # Código de salida 0 pero sin FIN (WHENEVER OSERROR / SQLCODE múltiplo de 256)
    assert pases.revisar_log("===== INICIO PASE X =====\n", "X", 0).resultado == "ERROR"


def test_cliente_inexistente_no_registra_nada(repo, control):
    """Fase 5: el runner no tenía SQLcl en el PATH y el pase quedaba EN_CURSO."""
    args = pases.parser().parse_args(["--raiz", str(repo.raiz), "ejecutar", "--manifiesto", str(repo.manifiesto),
                                      "--ambiente", "qa", "--etiqueta", "rel-QA-B1-20261111",
                                      "--evidencia", str(repo.raiz.parent / "evidencia")])
    try:
        pases.cmd_ejecutar(args, control=control, cliente=["cliente-que-no-existe"])
        assert False, "debió rechazar"
    except pases.ErrorPases as e:
        assert "no se encuentra el cliente SQL" in str(e)
    assert control.filas == []


def test_en_curso_bloquea_y_se_reintenta(repo, control):
    """Un pase que quedó EN_CURSO (ejecución interrumpida) bloquea hasta que se reintente a propósito."""
    control.filas.append(dict(ID=1, PASE="0001-10001", MODO="DEPLOY", RESULTADO="EN_CURSO", INTENTO=1,
                              ETIQUETA="rel-QA-B1-20261111", CHECKSUM="x", ENTREGA="B1", COMMIT_SHA="abc"))
    assert correr(repo, control, "ejecutar") == 2 and "EN_CURSO" in ultimo_error()
    assert correr(repo, control, "ejecutar", "--reintentar", "0001-10001") == 0
    assert control.filas[1]["INTENTO"] == 2 and estados(control) == {p: "APLICADO" for p in TODOS}
