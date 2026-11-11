#!/usr/bin/env python3
"""pases.py - herramienta de pases INSIS.

Automatiza el procedimiento de la "Guía de implementación de pases INSIS" sin cambiar su estructura:
carpetas DB/Deployments, script de instalación único por pase, ROLLBACK, SECUENCIA, etiquetas
rel-<AMB>-<ENTREGA>-<AAAAMMDD>[-N], DB/Releases/AAAAMMDD/<SEC>_<pase>.sql, logs, hoja de seguimiento y
reporte "[Pase con error]".

Comandos:
  validar     compuerta sobre el repositorio (sin base de datos)
  plan        qué pases faltan en un ambiente y en qué orden
  ejecutar    aplica los pases pendientes de una etiqueta, uno por uno, con corte ante el primer error
  revertir    aplica los ROLLBACK de los pases indicados, en orden inverso
  paquete     arma los scripts de ejecución y el LEEME para ejecución manual (no toca la base)
  inventario  genera el Inventario .xlsx desde el manifiesto
  siguiente-etiqueta  calcula el nombre de la próxima etiqueta de una entrega
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

VERSION = "1.0.0"
HERRAMIENTA = "PASES_INSIS"
ZONA = ZoneInfo("America/Lima")
RAIZ_DEFECTO = Path(__file__).resolve().parents[2]
PASE_RE = re.compile(r"^(\d{4})-(\d{4,6})$")
ETIQUETA_RE = re.compile(r"^rel-(?P<amb>[A-Z]+)-(?P<entrega>[A-Z0-9]+)-(?P<fecha>\d{8})(?:-(?P<n>\d+))?$")
USUARIOS_PROHIBIDOS = {"SYS", "SYSTEM"}


class ErrorPases(Exception):
    """Error que detiene la herramienta con un mensaje para el usuario."""


def ahora() -> dt.datetime:
    return dt.datetime.now(ZONA).replace(microsecond=0)


def fmt(t: dt.datetime | None) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S") if t else ""


# =====================================================================================
# Manifiesto
# =====================================================================================

@dataclass
class Prerrequisito:
    descripcion: str
    sql: str
    minimo: int = 1


@dataclass
class Pase:
    pase: str
    secuencia: int | None
    descripcion: str
    estado_task: str
    us: list[int] = field(default_factory=list)
    sprint: int | None = None
    task: int | None = None
    reinicio: bool = False
    depende_de: list[str] = field(default_factory=list)
    prerrequisitos: list[Prerrequisito] = field(default_factory=list)
    renumerado_de: str | None = None
    sin_efecto_permitido: bool = False
    nota: str = ""

    @property
    def ejecutable(self) -> bool:
        return self.estado_task == "Done" and self.secuencia is not None

    @property
    def sec(self) -> str:
        return f"{self.secuencia:02d}" if self.secuencia is not None else "--"


@dataclass
class Generador:
    paquete: str
    catalogo: str
    columna: str


@dataclass
class Manifiesto:
    ruta: Path
    entrega: str
    descripcion: str
    inventario: str
    previos: list[str]
    generadores: list[Generador]
    pases: list[Pase]

    def ejecutables(self) -> list[Pase]:
        return sorted((p for p in self.pases if p.ejecutable), key=lambda p: p.secuencia)

    def buscar(self, pase: str) -> Pase | None:
        return next((p for p in self.pases if p.pase == pase), None)


def cargar_manifiesto(ruta: Path) -> tuple[Manifiesto | None, list[str]]:
    """Devuelve el manifiesto y la lista de errores de formato (vacía si está bien)."""
    errores: list[str] = []
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        return None, [f"{ruta}: no se puede leer: {e}"]

    for clave in ("entrega", "pases"):
        if clave not in datos:
            errores.append(f"falta la clave '{clave}'")
    if errores:
        return None, errores

    pases: list[Pase] = []
    for i, d in enumerate(datos.get("pases") or [], start=1):
        pid = str(d.get("pase", ""))
        if not PASE_RE.match(pid):
            errores.append(f"fila {i}: pase '{pid}' no tiene el formato NNNN-US")
        sec = d.get("secuencia")
        if sec is not None and (not isinstance(sec, int) or sec <= 0):
            errores.append(f"{pid}: secuencia '{sec}' debe ser un entero positivo")
            sec = None
        estado = d.get("estado_task", "")
        if estado not in ("Done", "Doing", "To Do"):
            errores.append(f"{pid}: estado_task '{estado}' debe ser Done, Doing o To Do")
        prer = []
        for pr in d.get("prerrequisitos") or []:
            if not pr.get("sql"):
                errores.append(f"{pid}: prerrequisito sin sql")
                continue
            prer.append(Prerrequisito(pr.get("descripcion", pr["sql"]), pr["sql"], int(pr.get("minimo", 1))))
        pases.append(Pase(
            pase=pid, secuencia=sec, descripcion=str(d.get("descripcion", "")), estado_task=estado,
            us=[int(u) for u in (d.get("us") or [])], sprint=d.get("sprint"), task=d.get("task"),
            reinicio=bool(d.get("reinicio_insis_gen", False)),
            depende_de=[str(x) for x in (d.get("depende_de") or [])], prerrequisitos=prer,
            renumerado_de=str(d["renumerado_de"]) if d.get("renumerado_de") else None,
            sin_efecto_permitido=bool(d.get("sin_efecto_permitido", False)), nota=str(d.get("nota", "") or ""),
        ))

    vistos: dict[str, int] = {}
    secs: dict[int, str] = {}
    for p in pases:
        if p.pase in vistos:
            errores.append(f"{p.pase}: aparece más de una vez (un pase tiene una sola fila con SECUENCIA)")
        vistos[p.pase] = 1
        if p.ejecutable:
            if p.secuencia in secs:
                errores.append(f"SECUENCIA {p.secuencia} repetida: {secs[p.secuencia]} y {p.pase}")
            secs[p.secuencia] = p.pase

    gens = [Generador(g["paquete"].upper(), g["catalogo"].upper(), g.get("columna", "TABLE_NAME").upper())
            for g in (datos.get("generadores_id") or [])]
    m = Manifiesto(ruta, str(datos["entrega"]), str(datos.get("descripcion", "")), str(datos.get("inventario", "")),
                   [str(x) for x in (datos.get("previos") or [])], gens, pases)
    return m, errores


def manifiesto_o_error(ruta: Path) -> Manifiesto:
    m, errores = cargar_manifiesto(ruta)
    if errores or m is None:
        raise ErrorPases("Manifiesto inválido:\n  - " + "\n  - ".join(errores))
    return m


def manifiestos_del_repo(raiz: Path) -> list[Path]:
    return sorted((raiz / "releases").glob("*/manifest.yaml"))


# =====================================================================================
# Repositorio: carpetas, scripts y referencias
# =====================================================================================

def dir_deployments(raiz: Path) -> Path:
    return raiz / "DB" / "Deployments"


def carpetas_pase(raiz: Path, pase: str) -> list[Path]:
    """Carpetas del pase. Tolera nombres fuera de patrón (0026--63894, 0034-59844_...)."""
    nnnn, us = PASE_RE.match(pase).groups()
    patron = re.compile(rf"^{nnnn}-+{us}(?:[-_]|$)")
    base = dir_deployments(raiz)
    return sorted(d for d in base.iterdir() if d.is_dir() and patron.match(d.name)) if base.is_dir() else []


def es_rollback(nombre: str) -> bool:
    return "rollback" in nombre.lower()


def scripts_instalacion(carpeta: Path) -> list[Path]:
    return sorted(f for f in carpeta.glob("*.sql") if not es_rollback(f.name))


def scripts_rollback(carpeta: Path) -> list[Path]:
    return sorted(f for f in carpeta.glob("*.sql") if es_rollback(f.name))


REF_RE = re.compile(r'^\s*(@@?|START\s+)\s*"?([^"\s]+)"?', re.IGNORECASE)


def referencias(archivo: Path, base: Path) -> list[tuple[int, str, Path]]:
    """Referencias @ de un script: (línea, texto, ruta resuelta). @ resuelve desde `base`, @@ desde el archivo."""
    salida = []
    texto = leer_texto(archivo)
    for n, linea in enumerate(texto.splitlines(), start=1):
        m = REF_RE.match(linea)
        if not m:
            continue
        origen = archivo.parent if m.group(1) == "@@" else base
        ruta = (origen / m.group(2)).resolve()
        if not ruta.suffix:
            ruta = ruta.with_suffix(".sql")
        salida.append((n, m.group(2), ruta))
    return salida


def archivos_del_pase(master: Path) -> tuple[list[Path], list[tuple[Path, int, str]]]:
    """Master + todos los archivos referenciados (recursivo). Devuelve (archivos, referencias rotas)."""
    base = master.parent
    archivos: list[Path] = []
    rotas: list[tuple[Path, int, str]] = []
    pendientes = [master.resolve()]
    while pendientes:
        f = pendientes.pop(0)
        if f in archivos:
            continue
        archivos.append(f)
        for n, txt, ruta in referencias(f, base):
            if ruta.is_file():
                pendientes.append(ruta)
            else:
                rotas.append((f, n, txt))
    return archivos, rotas


def leer_texto(archivo: Path) -> str:
    return archivo.read_bytes().decode("utf-8", errors="replace").lstrip("﻿")


def checksum(archivos: list[Path], raiz: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(archivos, key=lambda x: str(x)):
        h.update(str(f.relative_to(raiz.resolve())).replace("\\", "/").encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


@dataclass
class PaseRepo:
    """Un pase del manifiesto resuelto contra el árbol del repositorio."""
    pase: Pase
    carpeta: Path
    master: Path
    archivos: list[Path]
    checksum: str
    rollback: Path | None


def resolver_pase(raiz: Path, p: Pase) -> PaseRepo:
    carpetas = carpetas_pase(raiz, p.pase)
    if len(carpetas) != 1:
        raise ErrorPases(f"{p.pase}: se esperaba una carpeta en DB/Deployments y hay {len(carpetas)}")
    masters = scripts_instalacion(carpetas[0])
    if len(masters) != 1:
        raise ErrorPases(f"{p.pase}: se esperaba un único script de instalación y hay {len(masters)}")
    archivos, rotas = archivos_del_pase(masters[0])
    if rotas:
        raise ErrorPases(f"{p.pase}: referencias @ que no resuelven: {', '.join(t for _, _, t in rotas)}")
    rbs = scripts_rollback(carpetas[0])
    return PaseRepo(p, carpetas[0], masters[0], archivos, checksum(archivos, raiz), rbs[0] if len(rbs) == 1 else None)


# =====================================================================================
# Analizador léxico SQL*Plus (Anexo E): líneas en blanco dentro de sentencias y código sin literales
# =====================================================================================

COMANDOS_SQLPLUS = {
    "SET", "PROMPT", "PRO", "SPOOL", "SPO", "START", "WHENEVER", "EXIT", "QUIT", "REM", "REMARK", "DEFINE",
    "DEF", "UNDEFINE", "UNDEF", "COLUMN", "COL", "TTITLE", "BTITLE", "BREAK", "COMPUTE", "CLEAR", "SHOW", "SHO",
    "PAUSE", "ACCEPT", "HOST", "CONNECT", "CONN", "VARIABLE", "VAR", "PRINT", "EXEC", "EXECUTE", "DESCRIBE",
    "DESC", "TIMING", "SHUTDOWN", "STARTUP", "ARCHIVE", "RECOVER", "PASSWORD", "ATTRIBUTE", "COPY", "SAVE",
    "GET", "EDIT", "ED", "LIST", "INPUT", "APPEND", "CHANGE", "DEL", "RUN", "STORE", "HELP", "REPHEADER",
    "REPFOOTER",
}
INICIO_PLSQL = re.compile(
    r"^\s*(DECLARE|BEGIN|CREATE\s+(OR\s+REPLACE\s+)?((NON)?EDITIONABLE\s+)?"
    r"(PROCEDURE|FUNCTION|PACKAGE|TRIGGER|TYPE|LIBRARY|JAVA))\b", re.IGNORECASE)
CIERRES_Q = {"[": "]", "{": "}", "(": ")", "<": ">"}


@dataclass
class AnalisisSQL:
    lineas_en_blanco: list[int]   # líneas en blanco que cortan una sentencia (SQLBLANKLINES OFF)
    codigo: str                   # texto con literales, comentarios y comandos SQL*Plus en blanco
    comandos: list[tuple[int, str]]  # comandos SQL*Plus fuera de sentencias: (línea, comando)


def analizar_sql(texto: str) -> AnalisisSQL:
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    estado = "N"          # N normal, LC comentario de línea, BC comentario de bloque, S cadena, Q q-literal, D "ident"
    cierre_q = ""
    abierta = False       # hay una sentencia SQL abierta
    plsql = False
    blancos: list[int] = []
    codigo: list[str] = []
    comandos: list[tuple[int, str]] = []

    for n, linea in enumerate(lineas, start=1):
        if estado == "LC":
            estado = "N"
        limpia = linea.strip()
        # Línea en blanco: con SQLBLANKLINES OFF corta la sentencia, salvo dentro de PL/SQL.
        if limpia == "":
            if (abierta or estado in ("S", "Q", "D")) and not plsql:
                blancos.append(n)
            codigo.append("")
            continue
        if estado == "N" and not abierta:
            if limpia == "/":
                codigo.append("")
                continue
            primera = re.split(r"[\s;]", limpia, maxsplit=1)[0].upper()
            if limpia.startswith("@") or primera in COMANDOS_SQLPLUS:
                comandos.append((n, "@" if limpia.startswith("@") else primera))
                codigo.append("")
                continue
        if estado == "N" and abierta and plsql and limpia == "/":
            abierta = plsql = False
            codigo.append("")
            continue

        salida = []
        i = 0
        while i < len(linea):
            c = linea[i]
            sig = linea[i + 1] if i + 1 < len(linea) else ""
            if estado == "N":
                if c == "-" and sig == "-":
                    estado = "LC"
                    salida.append(" " * (len(linea) - i))
                    break
                if c == "/" and sig == "*":
                    estado = "BC"
                    salida.append("  ")
                    i += 2
                    continue
                if not c.isspace() and not abierta:
                    abierta = True
                    plsql = bool(INICIO_PLSQL.match(linea[i:]))
                previo = linea[i - 1] if i > 0 else ""
                ident_previo = previo.isalnum() or previo in "_$#"
                if c in "qQ" and sig == "'" and i + 2 < len(linea) and (not ident_previo or previo in "nN"):
                    cierre_q = CIERRES_Q.get(linea[i + 2], linea[i + 2])
                    estado = "Q"
                    salida.append("   ")
                    i += 3
                    continue
                if c == "'":
                    estado = "S"
                    salida.append(" ")
                    i += 1
                    continue
                if c == '"':
                    estado = "D"
                    salida.append(c)
                    i += 1
                    continue
                if c == ";" and not plsql:
                    abierta = False
                salida.append(c)
                i += 1
            elif estado == "BC":
                if c == "*" and sig == "/":
                    estado = "N"
                    salida.append("  ")
                    i += 2
                else:
                    salida.append(" ")
                    i += 1
            elif estado == "S":
                if c == "'" and sig == "'":
                    salida.append("  ")
                    i += 2
                elif c == "'":
                    estado = "N"
                    salida.append(" ")
                    i += 1
                else:
                    salida.append(" ")
                    i += 1
            elif estado == "Q":
                if c == cierre_q and sig == "'":
                    estado = "N"
                    salida.append("  ")
                    i += 2
                else:
                    salida.append(" ")
                    i += 1
            elif estado == "D":
                salida.append(c)
                if c == '"':
                    estado = "N"
                i += 1
        codigo.append("".join(salida))
    return AnalisisSQL(blancos, "\n".join(codigo), comandos)


# =====================================================================================
# Compuerta (equivalente a compuerta.ps1 + detector de líneas en blanco + reglas de la guía)
# =====================================================================================

@dataclass
class Hallazgo:
    chequeo: str
    nivel: str        # ERROR | AVISO
    pase: str
    detalle: str


CHEQUEOS = {
    "C01": "Manifiesto válido (SECUENCIA única, estados, formato de pase)",
    "C02": "Una carpeta por pase en DB/Deployments",
    "C03": "Un único script de instalación por pase",
    "C04": "Reversión con el nombre de la convención (-ROLLBACK-<fecha>.sql)",
    "C05": "Las referencias @ resuelven",
    "C06": "Dependencias declaradas y en orden de SECUENCIA",
    "C07": "Sin líneas en blanco dentro de sentencias (ORA-01756 del 0065)",
    "C08": "Codificación UTF-8 sin BOM y sin mojibake",
    "C09": "ALLOCATE_ID calificado con su owner y generador declarado",
    "C10": "Sin EXIT / SPOOL / WHENEVER dentro de los scripts del pase",
    "C11": "Pases del árbol fuera del manifiesto (no se ejecutan)",
}
ROLLBACK_RE = re.compile(r"-ROLLBACK-\d{8}\.sql$")
MOJIBAKE_RE = re.compile("Ã[\u0080-¿]|Â[ -¿]|â€")
ALLOC_RE = re.compile(r"(?P<owner>[\w$#]+\s*\.\s*)?(?P<pkg>(?:SYS_)?IDCONTROL)\s*\.\s*ALLOCATE_ID\s*\(", re.IGNORECASE)
ALLOC_TABLA_RE = re.compile(r"([\w$#]+)\s*\.\s*((?:SYS_)?IDCONTROL)\s*\.\s*ALLOCATE_ID\s*\(\s*'([\w$#]+)'", re.IGNORECASE)


def revisar_archivo(f: Path, raiz: Path, pase: str, gens: list[Generador]) -> list[Hallazgo]:
    h: list[Hallazgo] = []
    rel = f.relative_to(raiz.resolve())
    datos = f.read_bytes()
    if datos.startswith(b"\xef\xbb\xbf"):
        h.append(Hallazgo("C08", "ERROR", pase, f"{rel}: tiene BOM (guardar en UTF-8 sin BOM)"))
        datos = datos[3:]
    try:
        texto = datos.decode("utf-8")
    except UnicodeDecodeError as e:
        h.append(Hallazgo("C08", "ERROR", pase, f"{rel}: no es UTF-8 válido (byte {e.start})"))
        texto = datos.decode("utf-8", errors="replace")
    for n, linea in enumerate(texto.splitlines(), start=1):
        if MOJIBAKE_RE.search(linea):
            h.append(Hallazgo("C08", "ERROR", pase, f"{rel}:{n}: texto doblemente codificado (mojibake)"))
            break
    a = analizar_sql(texto)
    if a.lineas_en_blanco:
        lst = ", ".join(map(str, a.lineas_en_blanco[:10])) + ("…" if len(a.lineas_en_blanco) > 10 else "")
        h.append(Hallazgo("C07", "ERROR", pase,
                          f"{rel}: {len(a.lineas_en_blanco)} línea(s) en blanco dentro de una sentencia (líneas {lst})"))
    paquetes = {g.paquete for g in gens}
    for n, linea in enumerate(a.codigo.splitlines(), start=1):
        for m in ALLOC_RE.finditer(linea):
            if not m.group("owner"):
                h.append(Hallazgo("C09", "ERROR", pase, f"{rel}:{n}: {m.group('pkg')}.ALLOCATE_ID sin owner"))
            else:
                pkg = re.sub(r"\s", "", m.group("owner") + m.group("pkg")).upper()
                if paquetes and pkg not in paquetes:
                    h.append(Hallazgo("C09", "AVISO", pase, f"{rel}:{n}: generador {pkg} no declarado en generadores_id"))
    for n, cmd in a.comandos:
        if cmd in ("EXIT", "QUIT", "SPOOL", "SPO", "WHENEVER"):
            h.append(Hallazgo("C10", "ERROR", pase, f"{rel}:{n}: {cmd} lo controla el script de ejecución"))
    return h


def compuerta(raiz: Path, rutas_manifiesto: list[Path]) -> list[Hallazgo]:
    h: list[Hallazgo] = []
    raiz = raiz.resolve()
    conocidos: set[str] = set()
    if not rutas_manifiesto:
        h.append(Hallazgo("C01", "ERROR", "-", "no hay ningún releases/*/manifest.yaml"))
    for ruta in rutas_manifiesto:
        m, errores = cargar_manifiesto(ruta)
        for e in errores:
            h.append(Hallazgo("C01", "ERROR", "-", f"{ruta.relative_to(raiz)}: {e}"))
        if m is None:
            continue
        conocidos.update(m.previos)
        conocidos.update(p.pase for p in m.pases)
        conocidos.update(p.renumerado_de for p in m.pases if p.renumerado_de)
        orden = {p.pase: p.secuencia for p in m.ejecutables()}
        for p in m.ejecutables():
            # C06 dependencias
            for dep in p.depende_de:
                if dep in m.previos:
                    continue
                if dep not in orden:
                    h.append(Hallazgo("C06", "ERROR", p.pase, f"depende de {dep}, que no está en la entrega ni en previos"))
                elif orden[dep] >= p.secuencia:
                    h.append(Hallazgo("C06", "ERROR", p.pase,
                                      f"depende de {dep} (SEC {orden[dep]}) pero tiene SEC {p.secuencia}"))
            if p.renumerado_de and p.renumerado_de in orden:
                h.append(Hallazgo("C06", "ERROR", p.pase, f"renumerado_de {p.renumerado_de}, que también está en la entrega"))
            # C02 carpeta
            carpetas = carpetas_pase(raiz, p.pase)
            if len(carpetas) != 1:
                h.append(Hallazgo("C02", "ERROR", p.pase,
                                  f"{len(carpetas)} carpetas en DB/Deployments" + (f": {[c.name for c in carpetas]}" if carpetas else "")))
                continue
            carpeta = carpetas[0]
            if not re.match(rf"^{p.pase}-[A-Z0-9_]+", carpeta.name):
                h.append(Hallazgo("C02", "AVISO", p.pase, f"carpeta fuera de patrón: {carpeta.name}"))
            # C03 script único
            masters = scripts_instalacion(carpeta)
            if len(masters) != 1:
                h.append(Hallazgo("C03", "ERROR", p.pase, f"{len(masters)} scripts de instalación: {[f.name for f in masters]}"))
                continue
            # C04 reversión
            for rb in scripts_rollback(carpeta):
                if not ROLLBACK_RE.search(rb.name):
                    h.append(Hallazgo("C04", "ERROR", p.pase, f"{rb.name}: no sigue la convención <pase>-<DESC>-ROLLBACK-<fecha>.sql"))
            if len(scripts_rollback(carpeta)) > 1:
                h.append(Hallazgo("C04", "ERROR", p.pase, "más de un script de reversión"))
            # C05 referencias
            archivos, rotas = archivos_del_pase(masters[0])
            for f, n, txt in rotas:
                h.append(Hallazgo("C05", "ERROR", p.pase, f"{f.relative_to(raiz)}:{n}: @{txt} no existe (SP2-0310 en ejecución)"))
            for rb in scripts_rollback(carpeta):
                a2, r2 = archivos_del_pase(rb)
                archivos += [x for x in a2 if x not in archivos]
                for f, n, txt in r2:
                    h.append(Hallazgo("C05", "ERROR", p.pase, f"{f.relative_to(raiz)}:{n}: @{txt} no existe"))
            # C07-C10 por archivo
            for f in archivos:
                h.extend(revisar_archivo(f, raiz, p.pase, m.generadores))
    # C11 fuera del manifiesto
    base = dir_deployments(raiz)
    if base.is_dir():
        for d in sorted(x for x in base.iterdir() if x.is_dir()):
            mm = re.match(r"^(\d{4})-+(\d{4,6})", d.name)
            pid = f"{mm.group(1)}-{mm.group(2)}" if mm else d.name
            if pid not in conocidos:
                h.append(Hallazgo("C11", "AVISO", pid, f"{d.name}: no está en ningún manifiesto; no se ejecuta"))
    return h


def imprimir_compuerta(h: list[Hallazgo]) -> str:
    errores = [x for x in h if x.nivel == "ERROR"]
    lineas = ["# Compuerta de pases", ""]
    lineas.append("| Chequeo | Descripción | Resultado |")
    lineas.append("| --- | --- | --- |")
    for c, desc in CHEQUEOS.items():
        e = sum(1 for x in h if x.chequeo == c and x.nivel == "ERROR")
        a = sum(1 for x in h if x.chequeo == c and x.nivel == "AVISO")
        res = "OK" if not e and not a else (f"ERROR ({e})" if e else f"AVISO ({a})")
        lineas.append(f"| {c} | {desc} | {res} |")
    if h:
        lineas += ["", "| Nivel | Chequeo | Pase | Detalle |", "| --- | --- | --- | --- |"]
        for x in sorted(h, key=lambda x: (x.nivel != "ERROR", x.chequeo, x.pase)):
            lineas.append(f"| {x.nivel} | {x.chequeo} | {x.pase} | {x.detalle} |")
    ok = len(CHEQUEOS) - len({x.chequeo for x in errores})
    lineas += ["", f"Resultado: {'APROBADA' if not errores else 'RECHAZADA'} · {ok} de {len(CHEQUEOS)} chequeos sin errores"]
    return "\n".join(lineas)


# =====================================================================================
# Git: la etiqueta es la única fuente ejecutable
# =====================================================================================

def git(raiz: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(raiz), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise ErrorPases(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout.strip()


def verificar_version(raiz: Path, etiqueta: str, ambiente: str, entrega: str, commit_esperado: str | None) -> str:
    m = ETIQUETA_RE.match(etiqueta)
    if not m:
        raise ErrorPases(f"'{etiqueta}' no es una etiqueta de entrega rel-<AMB>-<ENTREGA>-<AAAAMMDD>[-N]. "
                         "Se ejecuta una etiqueta, nunca una rama")
    if m["amb"] != ambiente.upper():
        raise ErrorPases(f"la etiqueta {etiqueta} es del ambiente {m['amb']}, no de {ambiente.upper()}")
    if m["entrega"] != entrega:
        raise ErrorPases(f"la etiqueta {etiqueta} es de la entrega {m['entrega']}, no de {entrega}")
    if git(raiz, "cat-file", "-t", etiqueta) != "tag":
        raise ErrorPases(f"{etiqueta} es una etiqueta liviana; debe ser anotada (git tag -a)")
    commit_etiqueta = git(raiz, "rev-parse", f"{etiqueta}^{{commit}}")
    head = git(raiz, "rev-parse", "HEAD")
    if head != commit_etiqueta:
        raise ErrorPases(f"la copia local (HEAD {head[:7]}) no es la etiqueta {etiqueta} ({commit_etiqueta[:7]})")
    if commit_esperado and not head.startswith(commit_esperado.lower()):
        raise ErrorPases(f"el commit de la etiqueta ({head[:7]}) no coincide con el indicado ({commit_esperado}). "
                         "No se ejecuta (regla del 2.º intento del 0046)")
    sucio = [l for l in git(raiz, "status", "--porcelain", "--untracked-files=no").splitlines() if l.strip()]
    if sucio:
        raise ErrorPases("la copia local tiene cambios sin versionar en archivos del repositorio; los scripts no se editan")
    return head


def siguiente_etiqueta(raiz: Path, ambiente: str, entrega: str, fecha: str | None = None) -> str:
    fecha = fecha or ahora().strftime("%Y%m%d")
    base = f"rel-{ambiente.upper()}-{entrega}-{fecha}"
    existentes = set(git(raiz, "tag", "-l", f"{base}*").split())
    if base not in existentes:
        return base
    n = 2
    while f"{base}-{n}" in existentes:
        n += 1
    return f"{base}-{n}"


# =====================================================================================
# Registro de control en la base (PASE_CONTROL / PASE_ESTADO)
# =====================================================================================

class ControlOracle:
    """Acceso a PASE_CONTROL con python-oracledb (modo thin)."""

    def __init__(self, usuario: str, clave: str, dsn: str, esquema: str = "INSIS_DEPLOY"):
        import oracledb
        self.cn = oracledb.connect(user=usuario, password=clave, dsn=dsn)
        self.e = esquema

    def _filas(self, sql: str, **binds) -> list[dict]:
        with self.cn.cursor() as cur:
            cur.execute(sql, binds)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def contexto(self) -> dict:
        f = self._filas("SELECT SYS_CONTEXT('USERENV','CON_NAME') CONTENEDOR, USER USUARIO FROM DUAL")[0]
        return {"contenedor": f["CONTENEDOR"], "usuario": f["USUARIO"]}

    def estado(self) -> dict[str, dict]:
        return {f["PASE"]: f for f in self._filas(f"SELECT * FROM {self.e}.PASE_ESTADO")}

    def ultimo(self, pase: str, modo: str) -> dict | None:
        f = self._filas(f"SELECT * FROM {self.e}.PASE_CONTROL WHERE PASE = :p AND MODO = :m "
                        "ORDER BY ID DESC FETCH FIRST 1 ROWS ONLY", p=pase, m=modo)
        return f[0] if f else None

    def intentos(self, pase: str, modo: str) -> int:
        return self._filas(f"SELECT COUNT(*) N FROM {self.e}.PASE_CONTROL WHERE PASE = :p AND MODO = :m",
                           p=pase, m=modo)[0]["N"]

    def iniciar(self, fila: dict) -> int:
        with self.cn.cursor() as cur:
            vid = cur.var(int)
            cols = ", ".join(fila)
            vals = ", ".join(f":{k}" for k in fila)
            cur.execute(f"INSERT INTO {self.e}.PASE_CONTROL ({cols}) VALUES ({vals}) RETURNING ID INTO :vid",
                        {**fila, "vid": vid})
            self.cn.commit()
            return vid.getvalue()[0]

    def terminar(self, ident: int, resultado: str, fin: dt.datetime, log: str, detalle: str) -> None:
        with self.cn.cursor() as cur:
            cur.execute(f"UPDATE {self.e}.PASE_CONTROL SET RESULTADO = :r, FIN = :f, LOG_NOMBRE = :l, "
                        "DETALLE = :d WHERE ID = :i",
                        r=resultado, f=fin.replace(tzinfo=None), l=log, d=detalle[:4000], i=ident)
            self.cn.commit()

    def historial(self) -> list[dict]:
        return self._filas(f"SELECT * FROM {self.e}.PASE_CONTROL ORDER BY ID")

    def invalidos(self) -> set[tuple[str, str, str]]:
        return {(f["OWNER"], f["OBJECT_TYPE"], f["OBJECT_NAME"]) for f in self._filas(
            "SELECT OWNER, OBJECT_TYPE, OBJECT_NAME FROM DBA_OBJECTS WHERE STATUS = 'INVALID' AND OWNER LIKE 'INSIS%'")}

    def escalar(self, sql: str) -> float:
        with self.cn.cursor() as cur:
            cur.execute(sql)
            r = cur.fetchone()
            return float(r[0]) if r and r[0] is not None else 0.0

    def registrado(self, catalogo: str, columna: str, tabla: str) -> bool:
        return self.escalar(f"SELECT COUNT(*) FROM {catalogo} WHERE {columna} = '{tabla.upper()}'") > 0


def control_desde_entorno(args) -> ControlOracle:
    usuario = os.environ.get("PASES_DB_USER", "")
    clave = os.environ.get("PASES_DB_PASSWORD", "")
    dsn = os.environ.get("PASES_DB_DSN", "")
    if not (usuario and clave and dsn):
        raise ErrorPases("faltan PASES_DB_USER, PASES_DB_PASSWORD o PASES_DB_DSN")
    return ControlOracle(usuario, clave, dsn, os.environ.get("PASES_ESQUEMA_CONTROL") or "INSIS_DEPLOY")


# =====================================================================================
# Scripts de ejecución, cliente SQL y revisión de logs (secciones 4 y 5 de la guía)
# =====================================================================================

def script_ejecucion(sec: str, pase: str, ambiente: str, ruta_master: str, modo: str = "PASE",
                     cabecera: list[str] | None = None) -> str:
    """Formato de la guía (sección 4, paso 4). `cabecera` agrega líneas PROMPT de trazabilidad."""
    nombre = f"{sec}_{pase}"
    titulo = "SEC " + sec if modo == "PASE" else "Rollback " + sec
    lineas = [
        f"/* {titulo} - Pase {pase} - Ambiente {ambiente.upper()} */",
        "SET DEFINE OFF",
        "WHENEVER OSERROR EXIT FAILURE ROLLBACK",
        "WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK",
        f"SPOOL {nombre}.log",
    ]
    for c in cabecera or []:
        lineas.append(f"PROMPT {c}")
    if cabecera:
        lineas.append("SET FEEDBACK ON")
    lineas += [
        f"PROMPT ===== INICIO {modo} {pase} =====",
        f'@"{ruta_master}"',
        f"PROMPT ===== FIN {modo} {pase} =====",
        "SPOOL OFF",
        "EXIT",
        "",
    ]
    return "\n".join(lineas)


def correr_cliente(cliente: list[str], usuario: str, clave: str, dsn: str, script: str, cwd: Path,
                   salida: Path, timeout: int = 3600) -> int:
    """Ejecuta el script con SQLcl/SQL*Plus. La clave va por entrada estándar: no aparece en argv ni en el log."""
    entrada = f'CONNECT {usuario}/"{clave}"@{dsn}\n@{script}\nEXIT FAILURE\n'
    env = {**os.environ, "NLS_LANG": "AMERICAN_AMERICA.AL32UTF8", "JAVA_TOOL_OPTIONS": "-Dfile.encoding=UTF-8"}
    env.pop("PASES_DB_PASSWORD", None)
    with salida.open("w", encoding="utf-8") as out:
        try:
            r = subprocess.run([*cliente, "-S", "/nolog"], input=entrada, text=True, cwd=cwd, env=env,
                               stdout=out, stderr=subprocess.STDOUT, timeout=timeout)
            return r.returncode
        except subprocess.TimeoutExpired:
            out.write(f"\n[{HERRAMIENTA}] tiempo de espera agotado ({timeout} s)\n")
            return 124
        except OSError as e:
            out.write(f"\n[{HERRAMIENTA}] no se pudo ejecutar el cliente {cliente[0]}: {e}\n")
            return 127


ERROR_LINEA_RE = re.compile(r"(ORA-\d{5}|SP2-\d{4}|OS Message)")
FILAS_RE = re.compile(r"^\s*(\d+) rows? (merged|updated|inserted|deleted)\.\s*$", re.IGNORECASE)
COMMIT_RE = re.compile(r"^\s*Commit complete\.\s*$", re.IGNORECASE)


@dataclass
class RevisionLog:
    resultado: str      # OK | ERROR | PARCIAL | ALERTA
    detalle: str
    filas: int
    dml: int


def revisar_log(texto: str, pase: str, codigo_salida: int, modo: str = "PASE",
                sin_efecto_permitido: bool = False) -> RevisionLog:
    """Criterio de la sección 5 de la guía + detección de escritura parcial y de pase sin efecto."""
    lineas = texto.splitlines()
    fin = any(l.strip() == f"===== FIN {modo} {pase} =====" for l in lineas)
    idx_error = next((i for i, l in enumerate(lineas) if ERROR_LINEA_RE.search(l)), None)
    filas = dml = 0
    for l in lineas:
        m = FILAS_RE.match(l)
        if m:
            dml += 1
            filas += int(m.group(1))
    if codigo_salida != 0 or not fin or idx_error is not None:
        if idx_error is not None:
            detalle = f"L{idx_error + 1}: {lineas[idx_error].strip()}"
        elif codigo_salida != 0:
            detalle = f"el cliente terminó con código {codigo_salida} y el log no llega a FIN {modo}"
        else:
            detalle = f"El log no llega a FIN {modo}"
        limite = idx_error if idx_error is not None else len(lineas)
        parcial = modo == "PASE" and any(COMMIT_RE.match(l) for l in lineas[:limite])
        return RevisionLog("PARCIAL" if parcial else "ERROR", detalle, filas, dml)
    if modo == "PASE" and dml > 0 and filas == 0 and not sin_efecto_permitido:
        return RevisionLog("ALERTA", f"pase sin efecto: {dml} sentencia(s) DML y 0 filas afectadas", filas, dml)
    return RevisionLog("OK", "", filas, dml)


# =====================================================================================
# Evidencia
# =====================================================================================

class Evidencia:
    def __init__(self, base: Path, ambiente: str, etiqueta: str, inicio: dt.datetime, sufijo: str = ""):
        self.dir = base / f"{ambiente.upper()}_{etiqueta}_{inicio.strftime('%Y%m%d_%H%M%S')}{sufijo}"
        self.logs = self.dir / "01_LOGS_POR_PASE"
        self.controles = self.dir / "02_CONTROLES"
        self.scripts = self.dir / "03_SCRIPTS"
        for d in (self.logs, self.controles, self.scripts):
            d.mkdir(parents=True, exist_ok=True)
        self.ambiente = ambiente.upper()
        self.hoja: list[dict] = []

    def escribir_csv(self, nombre: str, filas: list[dict], columnas: list[str], carpeta: Path | None = None) -> Path:
        ruta = (carpeta or self.dir) / nombre
        with ruta.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=columnas, delimiter=";", extrasaction="ignore")
            w.writeheader()
            w.writerows(filas)
        return ruta


COLS_HOJA = ["Entrega", "SEC", "Pase", "Inicio", "Fin", "Resultado", "Intento", "Etiqueta", "Commit", "Reinicio",
             "Rollback", "Log"]
COLS_ESTADO = ["Fecha", "Pase", "Entrega", "Sec", "Modo", "Estado", "Inicio", "Fin", "Etiqueta", "Commit",
               "Justificacion", "Log", "Ejecutado_por", "Numero_cambio"]


def exportar_estado(control, ev: Evidencia) -> None:
    filas = [{
        "Fecha": fmt(f.get("INICIO")), "Pase": f["PASE"], "Entrega": f["ENTREGA"], "Sec": f.get("SECUENCIA") or "",
        "Modo": f["MODO"], "Estado": f["RESULTADO"], "Inicio": fmt(f.get("INICIO")), "Fin": fmt(f.get("FIN")),
        "Etiqueta": f["ETIQUETA"], "Commit": (f["COMMIT_SHA"] or "")[:7], "Justificacion": f.get("DETALLE") or "",
        "Log": f.get("LOG_NOMBRE") or "", "Ejecutado_por": f.get("EJECUTADO_POR") or "",
        "Numero_cambio": f.get("NUMERO_CAMBIO") or "",
    } for f in control.historial()]
    ev.escribir_csv(f"ESTADO_{ev.ambiente}.csv", filas, COLS_ESTADO)


def reporte_error(ev: Evidencia, contexto: dict, etiqueta: str, commit: str, pr: PaseRepo, script: str,
                  detalle: str, ok: list[str], invalidos: str, log: str, modo: str = "Pase") -> Path:
    t = ahora()
    texto = "\n".join([
        f"Asunto: [{modo} con error] {ev.ambiente} - {pr.pase.pase} - {t.strftime('%Y%m%d')}",
        "",
        f"Ambiente:            {ev.ambiente} ({contexto.get('contenedor', '')})",
        f"Fecha y hora:        {fmt(t)}",
        f"Etiqueta / commit:   {etiqueta} / {commit}",
        f"{modo} que falló:      {pr.pase.sec} - {pr.pase.pase}" if modo == "Pase" else
        f"Rollback que falló:  {pr.pase.pase}",
        f"Script de ejecución: {script}",
        f"Error:               {detalle}",
        f"Pases en OK:         {', '.join(ok)}",
        f"Objetos inválidos:   {invalidos}",
        f"Adjuntos:            {log} y HOJA_SEGUIMIENTO_{ev.ambiente}.csv",
        "",
    ])
    ruta = ev.controles / f"Pases_{t.strftime('%Y%m%d_%H%M%S')}_REPORTE_ERROR_{pr.pase.sec}_{pr.pase.pase}.txt"
    ruta.write_text(texto, encoding="utf-8")
    return ruta


def resumen_github(texto: str) -> None:
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as f:
            f.write(texto + "\n")


# =====================================================================================
# Plan de ejecución
# =====================================================================================

@dataclass
class ItemPlan:
    pr: PaseRepo
    accion: str        # EJECUTAR | APLICADO | BLOQUEADO
    intento: int
    motivo: str = ""


def armar_plan(raiz: Path, m: Manifiesto, control, etiqueta: str, reintentar: set[str]) -> list[ItemPlan]:
    estado = control.estado()
    plan: list[ItemPlan] = []
    for p in m.ejecutables():
        pr = resolver_pase(raiz, p)
        e = estado.get(p.pase)
        previo = estado.get(p.renumerado_de) if p.renumerado_de else None
        intento = control.intentos(p.pase, "DEPLOY") + 1
        if previo and previo["ESTADO"] == "APLICADO" and not e:
            plan.append(ItemPlan(pr, "APLICADO", 0, f"aplicado como {p.renumerado_de} (renumerado)"))
            continue
        if not e or e["ESTADO"] == "REVERTIDO":
            plan.append(ItemPlan(pr, "EJECUTAR", intento))
            continue
        if e["ESTADO"] == "APLICADO":
            if e["CHECKSUM"] != pr.checksum:
                plan.append(ItemPlan(pr, "BLOQUEADO", intento,
                                     f"ya aplicado con {e['ETIQUETA']} y su contenido cambió: requiere decisión de CTI"))
            else:
                plan.append(ItemPlan(pr, "APLICADO", 0, f"con {e['ETIQUETA']}"))
            continue
        if e["ESTADO"] == "EN_CURSO" and p.pase not in reintentar:
            plan.append(ItemPlan(pr, "BLOQUEADO", intento,
                                 "quedó EN_CURSO (ejecución interrumpida): revisar la base y relanzar con --reintentar"))
            continue
        if e["ESTADO"] in ("ERROR", "PARCIAL", "ALERTA") and e["ETIQUETA"] == etiqueta and p.pase not in reintentar:
            plan.append(ItemPlan(pr, "BLOQUEADO", intento,
                                 f"falló ({e['ESTADO']}) con esta misma etiqueta: se reanuda con la etiqueta nueva "
                                 "que trae la corrección de CTI"))
            continue
        if e["ESTADO"] == "ERROR_ROLLBACK":
            plan.append(ItemPlan(pr, "BLOQUEADO", intento, "su último rollback falló: requiere decisión de CTI"))
            continue
        plan.append(ItemPlan(pr, "EJECUTAR", intento, f"reanuda tras {e['ESTADO']} con {e['ETIQUETA']}"))
    return plan


def tablas_allocate(pr: PaseRepo, gens: list[Generador]) -> list[tuple[Generador, str]]:
    salida = []
    por_pkg = {g.paquete: g for g in gens}
    for f in pr.archivos:
        codigo = analizar_sql(leer_texto(f)).codigo
        # Las tablas van en un literal: se buscan en el texto original de las líneas con ALLOCATE_ID en código.
        texto = leer_texto(f).splitlines()
        for n, l in enumerate(codigo.splitlines()):
            if "ALLOCATE_ID" in l.upper():
                for owner, pkg, tabla in ALLOC_TABLA_RE.findall(texto[n]):
                    g = por_pkg.get(f"{owner}.{pkg}".upper())
                    if g and (g, tabla.upper()) not in salida:
                        salida.append((g, tabla.upper()))
    return salida


def imprimir_plan(plan: list[ItemPlan], ambiente: str) -> str:
    lineas = [f"# Plan para {ambiente.upper()}", "", "| SEC | Pase | Acción | Intento | Motivo |", "| --- | --- | --- | --- | --- |"]
    for it in plan:
        lineas.append(f"| {it.pr.pase.sec} | {it.pr.pase.pase} | {it.accion} | {it.intento or ''} | {it.motivo} |")
    return "\n".join(lineas)


# =====================================================================================
# ejecutar
# =====================================================================================

def credenciales() -> tuple[str, str, str]:
    return os.environ.get("PASES_DB_USER", ""), os.environ.get("PASES_DB_PASSWORD", ""), os.environ.get("PASES_DB_DSN", "")


def comprobar_usuario(usuario: str) -> None:
    if usuario.upper() in USUARIOS_PROHIBIDOS or "AS SYSDBA" in usuario.upper():
        raise ErrorPases(f"no se ejecutan pases con {usuario}: usar el usuario de despliegue")


def comprobar_cliente(cliente: list[str]) -> None:
    """Antes de registrar nada en PASE_CONTROL: el cliente SQL tiene que existir en el PATH del ejecutor."""
    if not cliente or not shutil.which(cliente[0]):
        raise ErrorPases(f"no se encuentra el cliente SQL '{cliente[0] if cliente else ''}' en el PATH "
                         "(PASES_CLIENTE / --cliente); no se ejecuta nada")


def cmd_ejecutar(args, control=None, cliente: list[str] | None = None) -> int:
    raiz = Path(args.raiz).resolve()
    m = manifiesto_o_error(Path(args.manifiesto))
    usuario, clave, dsn = credenciales()
    comprobar_usuario(usuario)
    commit = verificar_version(raiz, args.etiqueta, args.ambiente, m.entrega, args.commit)
    control = control or control_desde_entorno(args)
    cliente = cliente or args.cliente.split()
    comprobar_cliente(cliente)
    ctx = control.contexto()
    comprobar_usuario(ctx["usuario"])
    inicio = ahora()
    ev = Evidencia(Path(args.evidencia), args.ambiente, args.etiqueta, inicio)
    amb = args.ambiente.upper()
    reintentar = set(args.reintentar or [])

    plan = armar_plan(raiz, m, control, args.etiqueta, reintentar)
    (ev.controles / "PLAN.md").write_text(imprimir_plan(plan, amb), encoding="utf-8")
    print(imprimir_plan(plan, amb))
    bloqueados = [it for it in plan if it.accion == "BLOQUEADO"]
    if bloqueados:
        msg = "\n".join(f"  - {it.pr.pase.pase}: {it.motivo}" for it in bloqueados)
        (ev.controles / "BLOQUEO.txt").write_text(msg + "\n", encoding="utf-8")
        exportar_estado(control, ev)
        resumen_github(f"## Ejecución bloqueada en {amb}\n\n{msg}")
        raise ErrorPases(f"no se ejecuta nada:\n{msg}")
    pendientes = [it for it in plan if it.accion == "EJECUTAR"]

    # Prevuelo de ALLOCATE_ID (Anexo D): solo lectura, antes de empezar.
    prevuelo = []
    for it in pendientes:
        for g, tabla in tablas_allocate(it.pr, m.generadores):
            ok = control.registrado(g.catalogo, g.columna, tabla)
            prevuelo.append((("OK" if ok else "FALTA"), g.catalogo, tabla, it.pr.pase.pase))
    prevuelo.sort(key=lambda x: x[0] != "FALTA")
    (ev.controles / "PREVUELO_ALLOCATE_ID.txt").write_text(
        "".join(f"{r}\t{c}\t{t}\t{p}\n" for r, c, t, p in prevuelo) or "sin ALLOCATE_ID en los pases pendientes\n",
        encoding="utf-8")
    faltan = [x for x in prevuelo if x[0] == "FALTA"]
    if faltan:
        msg = "\n".join(f"  - {t} no está registrada en {c} (pase {p})" for _, c, t, p in faltan)
        resumen_github(f"## Prevuelo ALLOCATE_ID en {amb}: FALTA\n\n{msg}")
        raise ErrorPases(f"prevuelo de ALLOCATE_ID con tablas en FALTA; no se arranca:\n{msg}")

    inv_antes = control.invalidos()
    ev.escribir_csv("INVALIDOS_ANTES.csv", [dict(zip(("Owner", "Tipo", "Objeto"), x)) for x in sorted(inv_antes)],
                    ["Owner", "Tipo", "Objeto"], ev.controles)
    releases = raiz / "DB" / "Releases" / inicio.strftime("%Y%m%d")
    releases.mkdir(parents=True, exist_ok=True)
    ok_en_corrida: list[str] = []
    fallo = None

    for it in pendientes:
        p, pr = it.pr.pase, it.pr
        nombre = f"{p.sec}_{p.pase}"
        t0 = ahora()
        fila = dict(AMBIENTE=amb, ENTREGA=m.entrega, PASE=p.pase, SECUENCIA=p.secuencia, MODO="DEPLOY",
                    INTENTO=it.intento, ETIQUETA=args.etiqueta, COMMIT_SHA=commit, CHECKSUM=pr.checksum,
                    RESULTADO="EN_CURSO", INICIO=t0.replace(tzinfo=None),
                    EJECUTADO_POR=os.environ.get("GITHUB_ACTOR") or os.environ.get("USER", ""),
                    NUMERO_CAMBIO=args.numero_cambio or None, RUN_URL=run_url())
        ident = control.iniciar(fila)

        # Prerrequisitos declarados en el manifiesto: si no se cumplen, el pase no ejecuta nada.
        falla_prer = None
        for pq in p.prerrequisitos:
            valor = control.escalar(pq.sql)
            if valor < pq.minimo:
                falla_prer = f"Prerrequisito no cumplido: {pq.descripcion} (obtenido {valor:g}, mínimo {pq.minimo})"
                break
        log_final = ""
        if falla_prer:
            rev = RevisionLog("ERROR", falla_prer, 0, 0)
            log_final = f"{nombre}_attempt{it.intento}_ERROR_{args.etiqueta}.log"
            (ev.logs / log_final).write_text(f"{HERRAMIENTA} {VERSION} | {amb} | {m.entrega} | {args.etiqueta} {commit[:7]}\n"
                                             f"{falla_prer}\nEl pase no se ejecutó.\n", encoding="utf-8")
            script = "(no se ejecutó)"
        else:
            ruta_master = os.path.relpath(pr.master, releases).replace("\\", "/")
            cab = [f"{HERRAMIENTA} {VERSION} | {amb} | {m.entrega} | {args.etiqueta} {commit[:7]}",
                   f"Contenedor: {ctx['contenedor']} | Usuario: {ctx['usuario']} | Inicio: {fmt(t0)} | Intento: {it.intento}"]
            (releases / f"{nombre}.sql").write_text(script_ejecucion(p.sec, p.pase, amb, ruta_master), encoding="utf-8")
            script = f"{nombre}.run.sql"
            (releases / script).write_text(script_ejecucion(p.sec, p.pase, amb, ruta_master, cabecera=cab), encoding="utf-8")
            log = releases / f"{nombre}.log"
            log.unlink(missing_ok=True)
            print(f"[{fmt(ahora())}] {nombre}: ejecutando (intento {it.intento})", flush=True)
            codigo = correr_cliente(cliente, usuario, clave, dsn, script, releases,
                                    ev.controles / f"{nombre}_attempt{it.intento}.salida.txt", args.timeout)
            texto = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            rev = revisar_log(texto, p.pase, codigo, sin_efecto_permitido=p.sin_efecto_permitido)
            nuevos = sorted(control.invalidos() - inv_antes)
            texto += f"\n---- CHECK INVALIDOS: nuevos={len(nuevos)}\n" + "".join(f"     {' '.join(x)}\n" for x in nuevos)
            if nuevos and rev.resultado == "OK":
                rev = RevisionLog("ERROR", f"{len(nuevos)} objeto(s) inválido(s) nuevo(s): "
                                  + ", ".join(".".join((o, n)) for o, _, n in nuevos), rev.filas, rev.dml)
            log_final = f"{nombre}_attempt{it.intento}_{rev.resultado}_{args.etiqueta}.log"
            (ev.logs / log_final).write_text(texto, encoding="utf-8")
            log.unlink(missing_ok=True)
            for f in (f"{nombre}.sql", script):
                shutil.copy2(releases / f, ev.scripts / f)
        t1 = ahora()
        control.terminar(ident, rev.resultado, t1, log_final, rev.detalle)
        ev.hoja.append({"Entrega": m.entrega, "SEC": p.sec, "Pase": p.pase, "Inicio": fmt(t0), "Fin": fmt(t1),
                        "Resultado": rev.resultado, "Intento": it.intento, "Etiqueta": args.etiqueta,
                        "Commit": commit[:7], "Reinicio": "Sí" if p.reinicio else "No",
                        "Rollback": "Sí" if pr.rollback else "No", "Log": log_final})
        print(f"[{fmt(t1)}] {nombre}: {rev.resultado} {rev.detalle}", flush=True)
        if rev.resultado != "OK":
            nuevos = sorted(control.invalidos() - inv_antes)
            inval = ", ".join(".".join((o, n)) for o, _, n in nuevos) if nuevos else "ninguno"
            reporte_error(ev, ctx, args.etiqueta, commit, pr, script, rev.detalle, ok_en_corrida, inval, log_final)
            fallo = (pr, rev)
            break
        ok_en_corrida.append(p.pase)

    # Cierre: hoja de seguimiento, inválidos después, verificación final, estado y resumen.
    ev.escribir_csv(f"HOJA_SEGUIMIENTO_{amb}.csv", ev.hoja, COLS_HOJA)
    inv_despues = control.invalidos()
    ev.escribir_csv("INVALIDOS_DESPUES.csv", [dict(zip(("Owner", "Tipo", "Objeto"), x)) for x in sorted(inv_despues)],
                    ["Owner", "Tipo", "Objeto"], ev.controles)
    estado = control.estado()
    verif = [f"VERIFICAR {fmt(ahora())} {amb} {args.etiqueta} HEAD={commit}"]
    completo = True
    for it in plan:
        p = it.pr.pase
        e = estado.get(p.pase) or (estado.get(p.renumerado_de) if p.renumerado_de else None)
        if not e or e["ESTADO"] != "APLICADO":
            completo = False
            verif.append(f"[PENDIENTE] [{p.pase}] {e['ESTADO'] if e else 'sin ejecutar'}")
        elif e["PASE"] == p.pase and e["CHECKSUM"] != it.pr.checksum:
            completo = False
            verif.append(f"[ALERTA] [{p.pase}] aplicado con contenido distinto al de la etiqueta")
        else:
            verif.append(f"[OK] [{p.pase}] APLICADO con {e['ETIQUETA']}")
    (ev.controles / "VERIFICAR.log").write_text("\n".join(verif) + "\n", encoding="utf-8")
    exportar_estado(control, ev)
    reinicio = [it.pr.pase.pase for it in plan if it.pr.pase.reinicio and it.accion == "EJECUTAR"
                and any(h["Pase"] == it.pr.pase.pase and h["Resultado"] == "OK" for h in ev.hoja)]
    resumen = [f"## Pases {m.entrega} en {amb} · {args.etiqueta} ({commit[:7]})", "",
               "| SEC | Pase | Resultado | Intento | Log |", "| --- | --- | --- | --- | --- |"]
    resumen += [f"| {h['SEC']} | {h['Pase']} | {h['Resultado']} | {h['Intento']} | {h['Log']} |" for h in ev.hoja]
    resumen += ["", f"Ya aplicados antes: {sum(1 for it in plan if it.accion == 'APLICADO')} · "
                    f"Ejecutados ahora: {len(ok_en_corrida)} · Entrega completa: {'Sí' if completo else 'No'}"]
    if reinicio:
        resumen.append(f"\n**Requiere un reinicio de INSIS GEN** al terminar (lo piden: {', '.join(reinicio)}).")
    if fallo:
        resumen.append(f"\n**Corte en {fallo[0].pase.sec} - {fallo[0].pase.pase}:** {fallo[1].detalle}")
    (ev.dir / "RESUMEN.md").write_text("\n".join(resumen) + "\n", encoding="utf-8")
    resumen_github("\n".join(resumen))
    print("\n".join(resumen))
    print(f"\nEvidencia: {ev.dir}")
    if fallo:
        return 1
    return 0 if completo else 1


def run_url() -> str | None:
    if os.environ.get("GITHUB_RUN_ID"):
        return f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{os.environ.get('GITHUB_REPOSITORY')}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    return None


# =====================================================================================
# revertir (sección 7 de la guía)
# =====================================================================================

def cmd_revertir(args, control=None, cliente: list[str] | None = None) -> int:
    raiz = Path(args.raiz).resolve()
    m = manifiesto_o_error(Path(args.manifiesto))
    usuario, clave, dsn = credenciales()
    comprobar_usuario(usuario)
    commit = verificar_version(raiz, args.etiqueta, args.ambiente, m.entrega, args.commit)
    control = control or control_desde_entorno(args)
    cliente = cliente or args.cliente.split()
    comprobar_cliente(cliente)
    ctx = control.contexto()
    comprobar_usuario(ctx["usuario"])
    amb = args.ambiente.upper()
    estado = control.estado()
    objetivo = list(dict.fromkeys(args.pases))

    errores = []
    pases: list[PaseRepo] = []
    for pid in objetivo:
        p = m.buscar(pid)
        if not p or not p.ejecutable:
            errores.append(f"{pid}: no es un pase de la entrega {m.entrega}")
            continue
        e = estado.get(pid)
        if not e or e["ESTADO"] != "APLICADO":
            errores.append(f"{pid}: no está APLICADO en {amb} ({e['ESTADO'] if e else 'sin ejecutar'})")
            continue
        pr = resolver_pase(raiz, p)
        if not pr.rollback:
            errores.append(f"{pid}: no tiene script de reversión; su reversión queda por respaldo")
            continue
        pases.append(pr)
    # No dejar dependientes aplicados huérfanos.
    for p in m.ejecutables():
        if p.pase in objetivo:
            continue
        e = estado.get(p.pase)
        if e and e["ESTADO"] == "APLICADO":
            for dep in p.depende_de:
                if dep in objetivo:
                    errores.append(f"{dep}: {p.pase} depende de él y sigue APLICADO; revertir ambos")
    if errores:
        raise ErrorPases("reversión rechazada:\n  - " + "\n  - ".join(errores))

    pases.sort(key=lambda pr: pr.pase.secuencia, reverse=True)
    inicio = ahora()
    ev = Evidencia(Path(args.evidencia), amb, args.etiqueta, inicio, "-ROLLBACK")
    releases = raiz / "DB" / "Releases" / f"{inicio.strftime('%Y%m%d')}-ROLLBACK"
    releases.mkdir(parents=True, exist_ok=True)
    hechos: list[str] = []
    fallo = None
    for n, pr in enumerate(pases, start=1):
        p = pr.pase
        nombre = f"R{n}_{p.pase}"
        intento = control.intentos(p.pase, "ROLLBACK") + 1
        t0 = ahora()
        ident = control.iniciar(dict(AMBIENTE=amb, ENTREGA=m.entrega, PASE=p.pase, SECUENCIA=p.secuencia,
                                     MODO="ROLLBACK", INTENTO=intento, ETIQUETA=args.etiqueta, COMMIT_SHA=commit,
                                     CHECKSUM=pr.checksum, RESULTADO="EN_CURSO", INICIO=t0.replace(tzinfo=None),
                                     EJECUTADO_POR=os.environ.get("GITHUB_ACTOR") or os.environ.get("USER", ""),
                                     NUMERO_CAMBIO=args.numero_cambio or None, RUN_URL=run_url()))
        ruta = os.path.relpath(pr.rollback, releases).replace("\\", "/")
        cab = [f"{HERRAMIENTA} {VERSION} | {amb} | {m.entrega} | {args.etiqueta} {commit[:7]} | ROLLBACK",
               f"Contenedor: {ctx['contenedor']} | Usuario: {ctx['usuario']} | Inicio: {fmt(t0)}"]
        (releases / f"{nombre}.sql").write_text(script_ejecucion(f"R{n}", p.pase, amb, ruta, "ROLLBACK", cab),
                                                encoding="utf-8")
        log = releases / f"{nombre}.log"
        log.unlink(missing_ok=True)
        codigo = correr_cliente(cliente, usuario, clave, dsn, f"{nombre}.sql", releases,
                                ev.controles / f"{nombre}.salida.txt", args.timeout)
        texto = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        rev = revisar_log(texto, p.pase, codigo, modo="ROLLBACK")
        log_final = f"{nombre}_attempt{intento}_{rev.resultado}_{args.etiqueta}.log"
        (ev.logs / log_final).write_text(texto, encoding="utf-8")
        log.unlink(missing_ok=True)
        shutil.copy2(releases / f"{nombre}.sql", ev.scripts / f"{nombre}.sql")
        t1 = ahora()
        control.terminar(ident, rev.resultado, t1, log_final, rev.detalle)
        ev.hoja.append({"Entrega": m.entrega, "SEC": f"R{n}", "Pase": p.pase, "Inicio": fmt(t0), "Fin": fmt(t1),
                        "Resultado": rev.resultado, "Intento": intento, "Etiqueta": args.etiqueta,
                        "Commit": commit[:7], "Reinicio": "Sí" if p.reinicio else "No", "Rollback": "Sí",
                        "Log": log_final})
        print(f"[{fmt(t1)}] {nombre}: {rev.resultado} {rev.detalle}", flush=True)
        if rev.resultado != "OK":
            reporte_error(ev, ctx, args.etiqueta, commit, pr, f"{nombre}.sql", rev.detalle, hechos, "ver CHECK INVALIDOS",
                          log_final, modo="Rollback")
            fallo = rev
            break
        hechos.append(p.pase)
    ev.escribir_csv(f"HOJA_SEGUIMIENTO_{amb}.csv", ev.hoja, COLS_HOJA)
    exportar_estado(control, ev)
    resumen = [f"## Rollback en {amb} · {args.etiqueta}", "", "| Orden | Pase | Resultado | Log |", "| --- | --- | --- | --- |"]
    resumen += [f"| {h['SEC']} | {h['Pase']} | {h['Resultado']} | {h['Log']} |" for h in ev.hoja]
    (ev.dir / "RESUMEN.md").write_text("\n".join(resumen) + "\n", encoding="utf-8")
    resumen_github("\n".join(resumen))
    print("\n".join(resumen))
    return 1 if fallo else 0


# =====================================================================================
# plan · paquete · inventario · validar
# =====================================================================================

def cmd_plan(args, control=None) -> int:
    raiz = Path(args.raiz).resolve()
    m = manifiesto_o_error(Path(args.manifiesto))
    control = control or control_desde_entorno(args)
    plan = armar_plan(raiz, m, control, args.etiqueta or "", set())
    print(imprimir_plan(plan, args.ambiente))
    resumen_github(imprimir_plan(plan, args.ambiente))
    return 1 if any(it.accion == "BLOQUEADO" for it in plan) else 0


LEEME = """# Paquete de ejecución manual · {entrega} · {etiqueta}

Generado por {herr} {ver} el {fecha}. No toca la base: es para ejecutar a mano siguiendo la
Guía de implementación de pases INSIS.

1. `git fetch origin --tags` y `git checkout -b release/{dia} {etiqueta}`.
   `git rev-parse HEAD` tiene que devolver **{commit}**.
2. Copiar la carpeta `{dia}` de este paquete a `DB/Releases/{dia}` (exactamente ahí: los scripts usan rutas `../../`).
3. Foto de objetos inválidos (paso 6 de la guía).
4. `cd DB/Releases/{dia}` · `export NLS_LANG=AMERICAN_AMERICA.AL32UTF8` (Windows: `set NLS_LANG=...`).
5. Ejecutar uno por uno, en este orden, revisando cada log (sección 5 de la guía) y anotando en la hoja de seguimiento:

| SEC | Pase | Script | Reinicio | Rollback |
| --- | --- | --- | --- | --- |
{filas}

6. Ante el primer error: detenerse y reportar con el formato "[Pase con error]" (sección 6.3).
7. Al final: foto de inválidos y {reinicio}.

Diferencia con la guía v1.7: los scripts usan `WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK` para que un
error a mitad de un pase no confirme lo escrito desde el último COMMIT.
"""


def cmd_paquete(args) -> int:
    raiz = Path(args.raiz).resolve()
    m = manifiesto_o_error(Path(args.manifiesto))
    commit = git(raiz, "rev-parse", "HEAD")
    etiqueta = args.etiqueta or git(raiz, "describe", "--tags", "--exact-match", "HEAD")
    dia = ahora().strftime("%Y%m%d")
    salida = Path(args.salida) / f"PAQUETE_{args.ambiente.upper()}_{etiqueta}"
    rel = salida / dia
    rel.mkdir(parents=True, exist_ok=True)
    releases_virtual = raiz / "DB" / "Releases" / dia
    filas, hoja = [], []
    for p in m.ejecutables():
        pr = resolver_pase(raiz, p)
        ruta = os.path.relpath(pr.master, releases_virtual).replace("\\", "/")
        nombre = f"{p.sec}_{p.pase}.sql"
        (rel / nombre).write_text(script_ejecucion(p.sec, p.pase, args.ambiente, ruta), encoding="utf-8")
        filas.append(f"| {p.sec} | {p.pase} | {nombre} | {'Sí' if p.reinicio else 'No'} | {'Sí' if pr.rollback else 'No'} |")
        hoja.append({"Entrega": m.entrega, "SEC": p.sec, "Pase": p.pase, "Etiqueta": etiqueta, "Commit": commit[:7],
                     "Reinicio": "Sí" if p.reinicio else "No", "Rollback": "Sí" if pr.rollback else "No",
                     "Log": f"{p.sec}_{p.pase}.log"})
    reinicio = ("pedir **un** reinicio de INSIS GEN" if any(p.reinicio for p in m.ejecutables())
                else "no se requiere reinicio de INSIS GEN")
    (salida / "LEEME.md").write_text(LEEME.format(entrega=m.entrega, etiqueta=etiqueta, herr=HERRAMIENTA, ver=VERSION,
                                                  fecha=fmt(ahora()), dia=dia, commit=commit, filas="\n".join(filas),
                                                  reinicio=reinicio), encoding="utf-8")
    with (salida / f"HOJA_SEGUIMIENTO_{args.ambiente.upper()}.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS_HOJA, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(hoja)
    generar_inventario(raiz, m, salida / f"Inventario_{m.entrega}.xlsx")
    print(f"Paquete: {salida}")
    return 0


def generar_inventario(raiz: Path, m: Manifiesto, destino: Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventario Final"
    cols = ["Sprint", "US", "Descripción", "Task", "REPO", "SECUENCIA", "Estado Task", "Pase", "Reinicio",
            "Rollback", "Depende de", "Comentarios"]
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True)
    for p in sorted(m.pases, key=lambda x: (x.secuencia is None, x.secuencia or 0, x.pase)):
        carpetas = carpetas_pase(raiz, p.pase)
        rb = bool(carpetas and scripts_rollback(carpetas[0]))
        for us in p.us or [None]:
            ws.append([p.sprint, us, p.descripcion, p.task, p.pase[:4], p.secuencia, p.estado_task, p.pase,
                       "Sí" if p.reinicio else "No", "Sí" if rb else "No", ", ".join(p.depende_de), p.nota])
    ws.freeze_panes = "A2"
    destino.parent.mkdir(parents=True, exist_ok=True)
    wb.save(destino)
    return destino


def cmd_inventario(args) -> int:
    raiz = Path(args.raiz).resolve()
    m = manifiesto_o_error(Path(args.manifiesto))
    print(generar_inventario(raiz, m, Path(args.salida)))
    return 0


def cmd_validar(args) -> int:
    raiz = Path(args.raiz).resolve()
    rutas = [Path(x) for x in args.manifiesto] if args.manifiesto else manifiestos_del_repo(raiz)
    h = compuerta(raiz, rutas)
    texto = imprimir_compuerta(h)
    print(texto)
    resumen_github(texto)
    return 1 if any(x.nivel == "ERROR" for x in h) else 0


def cmd_siguiente_etiqueta(args) -> int:
    print(siguiente_etiqueta(Path(args.raiz), args.ambiente, args.entrega, args.fecha))
    return 0


# =====================================================================================
# CLI
# =====================================================================================

def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="pases.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", default=str(RAIZ_DEFECTO), help="raíz del repositorio")
    sub = ap.add_subparsers(dest="comando", required=True)

    v = sub.add_parser("validar", help="compuerta sobre el repositorio")
    v.add_argument("--manifiesto", action="append", help="por defecto, todos los releases/*/manifest.yaml")

    def comunes(s, etiqueta_requerida=True):
        s.add_argument("--manifiesto", required=True)
        s.add_argument("--ambiente", required=True, choices=["qa", "prd"])
        s.add_argument("--etiqueta", required=etiqueta_requerida)

    def de_bd(s):
        comunes(s)
        s.add_argument("--commit", default=os.environ.get("PASES_COMMIT_ESPERADO"),
                       help="commit esperado de la etiqueta (el de la guía / el del workflow)")
        s.add_argument("--evidencia", default="evidencia")
        s.add_argument("--cliente", default=os.environ.get("PASES_CLIENTE") or "sql")
        s.add_argument("--numero-cambio", default=os.environ.get("PASES_NUMERO_CAMBIO"))
        s.add_argument("--timeout", type=int, default=3600)

    e = sub.add_parser("ejecutar", help="aplica los pases pendientes de la etiqueta")
    de_bd(e)
    e.add_argument("--reintentar", nargs="*", help="pases a reintentar aunque fallaron con esta etiqueta (decisión de CTI)")

    r = sub.add_parser("revertir", help="aplica los ROLLBACK indicados en orden inverso")
    de_bd(r)
    r.add_argument("--pases", nargs="+", required=True)

    p = sub.add_parser("plan", help="pases pendientes en un ambiente")
    comunes(p, etiqueta_requerida=False)

    k = sub.add_parser("paquete", help="scripts y LEEME para ejecución manual (no toca la base)")
    k.add_argument("--manifiesto", required=True)
    k.add_argument("--ambiente", required=True, choices=["qa", "prd"])
    k.add_argument("--etiqueta")
    k.add_argument("--salida", default="paquete")

    i = sub.add_parser("inventario", help="genera el Inventario .xlsx")
    i.add_argument("--manifiesto", required=True)
    i.add_argument("--salida", required=True)

    s = sub.add_parser("siguiente-etiqueta", help="nombre de la próxima etiqueta de una entrega")
    s.add_argument("--ambiente", required=True, choices=["qa", "prd"])
    s.add_argument("--entrega", required=True)
    s.add_argument("--fecha", help="AAAAMMDD (por defecto, hoy en Lima)")
    return ap


COMANDOS = {"validar": cmd_validar, "ejecutar": cmd_ejecutar, "revertir": cmd_revertir, "plan": cmd_plan,
            "paquete": cmd_paquete, "inventario": cmd_inventario, "siguiente-etiqueta": cmd_siguiente_etiqueta}


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        return COMANDOS[args.comando](args)
    except ErrorPases as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
