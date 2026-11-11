#!/usr/bin/env python3
"""SQLcl simulado para las pruebas. Imita el comportamiento que importa a pases.py:

- lee los comandos por entrada estándar (CONNECT, @script, EXIT);
- SPOOL / PROMPT / SET / WHENEVER / @"ruta" (relativa al directorio actual, como SQL*Plus);
- SQLBLANKLINES OFF: una línea en blanco dentro de una sentencia SQL la corta;
- salida de DML con el formato de SQLcl ("1 row merged.", "Commit complete.") y errores con
  "Error report -" / "SQL Error: ORA-xxxxx";
- WHENEVER SQLERROR EXIT SQL.SQLCODE: sale con SQLCODE % 256.

Directivas en comentarios del SQL (solo para pruebas):
  -- FAKE_ERROR: ORA-00904: "X": invalid identifier   la sentencia falla con ese error
  -- FAKE_FILAS: 0                                     filas afectadas (por defecto 1)
"""
import re
import sys
from pathlib import Path

spool = None
salir_en_error = False


class Salida(Exception):
    def __init__(self, codigo):
        self.codigo = codigo


def out(texto=""):
    sys.stdout.write(texto + "\n")
    if spool:
        spool.write(texto + "\n")


def ejecutar_sentencia(texto, plsql):
    m = re.search(r"FAKE_ERROR:\s*(ORA-(\d{5}).*)", texto)
    if m:
        out("")
        out("Error report -")
        out(f"SQL Error: {m.group(1).strip()}")
        out("")
        if salir_en_error:
            raise Salida(int(m.group(2)) % 256 or 1)
        return
    if plsql:
        out("")
        out("PL/SQL procedure successfully completed.")
        out("")
        return
    sin_comentarios = re.sub(r"--[^\n]*|/\*.*?\*/", " ", texto, flags=re.S).strip()
    palabra = sin_comentarios.split(None, 1)[0].upper().rstrip(";") if sin_comentarios else ""
    filas = int(re.search(r"FAKE_FILAS:\s*(\d+)", texto).group(1)) if "FAKE_FILAS" in texto else 1
    verbos = {"MERGE": "merged", "UPDATE": "updated", "INSERT": "inserted", "DELETE": "deleted"}
    if palabra in verbos:
        out("")
        out(f"{filas} row{'s' if filas != 1 else ''} {verbos[palabra]}.")
        out("")
    elif palabra == "COMMIT":
        out("")
        out("Commit complete.")
        out("")


def ejecutar_archivo(ruta: Path):
    if not ruta.is_file():
        out(f'SP2-0310: unable to open file "{ruta}"')
        return
    ejecutar_lineas(ruta.read_text(encoding="utf-8").splitlines())


def comando(linea):
    global spool, salir_en_error
    l = linea.strip()
    u = l.upper()
    if l.startswith("@"):
        ejecutar_archivo(Path(l.lstrip("@").strip().strip('"')))
    elif u.startswith("PROMPT"):
        out(l[6:].strip())
    elif u.startswith("SPOOL"):
        arg = l[5:].strip()
        if spool:
            spool.close()
            spool = None
        if arg.upper() != "OFF":
            spool = open(arg, "w", encoding="utf-8")
    elif u.startswith("WHENEVER SQLERROR"):
        salir_en_error = "EXIT" in u
    elif u.startswith("EXIT") or u.startswith("QUIT"):
        raise Salida(1 if "FAILURE" in u else 0)
    # SET, CONNECT, WHENEVER OSERROR, REM: sin efecto


COMANDOS = ("SET", "PROMPT", "SPOOL", "WHENEVER", "EXIT", "QUIT", "REM", "CONNECT", "DEFINE")
INICIO_PLSQL = re.compile(r"^\s*(DECLARE|BEGIN|CREATE\s+(OR\s+REPLACE\s+)?(PROCEDURE|FUNCTION|PACKAGE|TRIGGER))\b", re.I)


def ejecutar_lineas(lineas):
    buffer, plsql, en_comentario = [], False, False
    for linea in lineas:
        l = linea.strip()
        if not buffer:
            if en_comentario:
                en_comentario = "*/" not in l
                continue
            if l.startswith("/*"):
                en_comentario = "*/" not in l
                continue
            if not l or l.startswith("--"):
                continue
            if l.startswith("@") or l.split(None, 1)[0].upper().rstrip(";") in COMANDOS:
                comando(linea)
                continue
            plsql = bool(INICIO_PLSQL.match(l))
            buffer.append(linea)
            if not plsql and re.search(r";\s*(--.*)?$", l):
                ejecutar_sentencia("\n".join(buffer), False)
                buffer = []
            continue
        if plsql:
            if l == "/":
                ejecutar_sentencia("\n".join(buffer), True)
                buffer = []
            else:
                buffer.append(linea)
            continue
        if not l:  # SQLBLANKLINES OFF: la línea en blanco corta la sentencia
            texto = "\n".join(buffer)
            abierto = texto.count("q'~") > texto.count("~'")
            out("")
            out("Error report -")
            out("SQL Error: ORA-01756: quoted string not properly terminated" if abierto
                else "SQL Error: ORA-00933: SQL command not properly ended")
            out("")
            buffer = []
            if salir_en_error:
                raise Salida(1756 % 256 if abierto else 933 % 256)
            continue
        buffer.append(linea)
        if re.search(r";\s*(--.*)?$", l) and l.count("'") % 2 == 0:
            ejecutar_sentencia("\n".join(buffer), False)
            buffer = []


def main():
    try:
        ejecutar_lineas(sys.stdin.read().splitlines())
        raise Salida(0)
    except Salida as s:
        if spool:
            spool.close()
        return s.codigo


if __name__ == "__main__":
    sys.exit(main())
