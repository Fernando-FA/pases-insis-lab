"""Pruebas de integración contra un Oracle real (pytest -m oracle). No escriben datos.

Se ejecutan solo si están definidas PASES_TEST_DSN, PASES_TEST_USER y PASES_TEST_PASSWORD y hay un cliente SQL
(PASES_CLIENTE, por defecto `sql`). En la Compuerta de GitHub no hay base: se saltan.
"""
import os
import shutil

import pytest

import pases

DSN = os.environ.get("PASES_TEST_DSN")
USUARIO = os.environ.get("PASES_TEST_USER", "INSIS_DEPLOY")
CLAVE = os.environ.get("PASES_TEST_PASSWORD")
CLIENTE = (os.environ.get("PASES_CLIENTE") or "sql").split()

pytestmark = [
    pytest.mark.oracle,
    pytest.mark.skipif(not (DSN and CLAVE), reason="sin base de datos de prueba (PASES_TEST_DSN / PASES_TEST_PASSWORD)"),
]


@pytest.fixture(scope="module")
def control():
    return pases.ControlOracle(USUARIO, CLAVE, DSN)


def test_conexion_thin_y_usuario_de_despliegue(control):
    ctx = control.contexto()
    assert ctx["usuario"] == USUARIO.upper()
    assert ctx["usuario"] not in pases.USUARIOS_PROHIBIDOS


def test_vistas_de_control_e_invalidos(control):
    assert isinstance(control.estado(), dict)
    assert isinstance(control.invalidos(), set)
    assert control.registrado("INSIS_DEMO_CFG.RB_ID_CONTROL", "TABLE_NAME", "CFG_RULES")


def _correr(tmp_path, cuerpo: str):
    if not shutil.which(CLIENTE[0]):
        pytest.skip(f"no está el cliente {CLIENTE[0]}")
    (tmp_path / "master.sql").write_text(cuerpo, encoding="utf-8")
    script = pases.script_ejecucion("01", "9999-99999", "QA", "master.sql", cabecera=["prueba de integración"])
    (tmp_path / "01_9999-99999.run.sql").write_text(script, encoding="utf-8")
    codigo = pases.correr_cliente(CLIENTE, USUARIO, CLAVE, DSN, "01_9999-99999.run.sql", tmp_path, tmp_path / "salida.txt")
    log = (tmp_path / "01_9999-99999.log").read_text(encoding="utf-8")
    assert CLAVE not in log and CLAVE not in (tmp_path / "salida.txt").read_text(encoding="utf-8")
    return codigo, log


def test_sqlcl_pase_ok_sin_efecto(tmp_path):
    codigo, log = _correr(tmp_path, "UPDATE INSIS_DEMO_CFG.CFG_PRODUCTS SET NAME = NAME WHERE 1 = 0;\nROLLBACK;\n")
    r = pases.revisar_log(log, "9999-99999", codigo)
    assert codigo == 0 and r.resultado == "ALERTA" and r.dml == 1 and r.filas == 0


def test_sqlcl_error_formato_real(tmp_path):
    codigo, log = _correr(tmp_path, "SELECT COLUMNA_INEXISTENTE FROM DUAL;\n")
    r = pases.revisar_log(log, "9999-99999", codigo)
    assert codigo == 904 % 256
    assert r.resultado == "ERROR" and "SQL Error: ORA-00904" in r.detalle


def test_sqlcl_error_plsql(tmp_path):
    codigo, log = _correr(tmp_path, "BEGIN\n  RAISE_APPLICATION_ERROR(-20075, 'falta dato base');\nEND;\n/\n")
    r = pases.revisar_log(log, "9999-99999", codigo)
    assert codigo != 0 and r.resultado == "ERROR" and "ORA-20075" in r.detalle


def test_sqlcl_linea_en_blanco_en_q_literal(tmp_path):
    codigo, log = _correr(tmp_path, "SELECT q'~A\n   \nB~' FROM DUAL;\n")
    r = pases.revisar_log(log, "9999-99999", codigo)
    assert r.resultado == "ERROR" and "ORA-01756" in r.detalle
