import shutil
import subprocess
import sys
from pathlib import Path

import pytest

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
# Copia fija de una entrega B1 para las pruebas: no depende de los pases que se agreguen al repositorio.
DATOS = AQUI / "datos"
FAKE_SQL = [sys.executable, str(AQUI / "fake_sql.py")]

import pases  # noqa: E402


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


class Repo:
    """Copia del repositorio en un directorio temporal, con git y etiquetas propias."""

    def __init__(self, raiz: Path):
        self.raiz = raiz
        self.manifiesto = raiz / "releases" / "B1" / "manifest.yaml"

    def commit(self, mensaje: str = "cambio") -> str:
        git(self.raiz, "add", "-A")
        git(self.raiz, "commit", "-qm", mensaje)
        return git(self.raiz, "rev-parse", "HEAD")

    def etiquetar(self, nombre: str) -> str:
        git(self.raiz, "tag", "-a", nombre, "-m", f"Entrega {nombre}")
        return nombre

    def archivo(self, rel: str) -> Path:
        return self.raiz / rel

    def deployment(self, prefijo: str) -> Path:
        return next((self.raiz / "DB" / "Deployments").glob(f"{prefijo}*"))


@pytest.fixture
def repo(tmp_path) -> Repo:
    raiz = tmp_path / "repo"
    raiz.mkdir()
    for d in ("DB", "releases"):
        shutil.copytree(DATOS / d, raiz / d)
    (raiz / ".gitignore").write_text("DB/Releases/\n", encoding="utf-8")
    git(raiz, "init", "-q", "-b", "Desa")
    git(raiz, "config", "user.name", "Pruebas")
    git(raiz, "config", "user.email", "pruebas@example.com")
    r = Repo(raiz)
    r.commit("inicial")
    r.etiquetar("rel-QA-B1-20261111")
    return r


class ControlMemoria:
    """PASE_CONTROL en memoria, con la misma lógica de la vista PASE_ESTADO."""

    def __init__(self):
        self.filas: list[dict] = []
        self.invalidos_actuales: set = set()
        self.escalares: dict[str, float] = {}
        self.no_registradas: set[str] = set()
        self.usuario = "INSIS_DEPLOY"

    def contexto(self):
        return {"contenedor": "FREEPDB1", "usuario": self.usuario}

    def estado(self):
        salida = {}
        for f in self.filas:
            p = f["PASE"]
            intentos = sum(1 for x in self.filas if x["PASE"] == p and x["MODO"] == "DEPLOY")
            r, modo = f["RESULTADO"], f["MODO"]
            if r == "EN_CURSO":
                est = "EN_CURSO"
            elif modo == "DEPLOY" and r == "OK":
                est = "APLICADO"
            elif modo == "ROLLBACK" and r == "OK":
                est = "REVERTIDO"
            elif modo == "ROLLBACK":
                est = "ERROR_ROLLBACK"
            else:
                est = r
            salida[p] = {**f, "ESTADO": est, "INTENTOS": intentos}
        return salida

    def ultimo(self, pase, modo):
        f = [x for x in self.filas if x["PASE"] == pase and x["MODO"] == modo]
        return f[-1] if f else None

    def intentos(self, pase, modo):
        return sum(1 for x in self.filas if x["PASE"] == pase and x["MODO"] == modo)

    def iniciar(self, fila):
        self.filas.append({**fila, "ID": len(self.filas) + 1, "FIN": None, "LOG_NOMBRE": None, "DETALLE": None})
        return len(self.filas)

    def terminar(self, ident, resultado, fin, log, detalle):
        self.filas[ident - 1].update(RESULTADO=resultado, FIN=fin, LOG_NOMBRE=log, DETALLE=detalle)

    def historial(self):
        return list(self.filas)

    def invalidos(self):
        return set(self.invalidos_actuales)

    def escalar(self, sql):
        return self.escalares.get(sql, 1)

    def registrado(self, catalogo, columna, tabla):
        return tabla.upper() not in self.no_registradas


@pytest.fixture
def control() -> ControlMemoria:
    return ControlMemoria()


@pytest.fixture(autouse=True)
def credenciales(monkeypatch):
    monkeypatch.setenv("PASES_DB_USER", "INSIS_DEPLOY")
    monkeypatch.setenv("PASES_DB_PASSWORD", "clave-de-prueba")
    monkeypatch.setenv("PASES_DB_DSN", "localhost:1521/FREEPDB1")
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)


def correr(repo: Repo, control, comando: str, *extra: str, etiqueta="rel-QA-B1-20261111", ambiente="qa"):
    """Ejecuta un comando de pases.py contra el repo temporal con el control en memoria y el SQLcl simulado."""
    evid = repo.raiz.parent / "evidencia"
    argv = ["--raiz", str(repo.raiz), comando, "--manifiesto", str(repo.manifiesto), "--ambiente", ambiente,
            "--etiqueta", etiqueta, "--evidencia", str(evid), *extra]
    args = pases.parser().parse_args(argv)
    fn = pases.cmd_ejecutar if comando == "ejecutar" else pases.cmd_revertir
    try:
        return fn(args, control=control, cliente=FAKE_SQL)
    except pases.ErrorPases as e:   # igual que main(): mensaje y código 2
        ERRORES.append(str(e))
        return 2


ERRORES: list[str] = []


def ultimo_error() -> str:
    return ERRORES[-1] if ERRORES else ""


def checkout(repo: Repo, ref: str):
    git(repo.raiz, "checkout", "-q", ref)
