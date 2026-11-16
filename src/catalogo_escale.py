"""C2: catalogo de las variables de los archivos de ESCALE que ya estan descargados (sin descargar nada mas).

Lee los .dbf de data/interim/escale/{anio} (nombres, tipo y largo de cada campo) y busca la descripcion de cada campo en el
diccionario de datos oficial (texto del PDF en data/interim/pdf). Marca con palabras clave las variables que podrian servir
para describir la infraestructura de un local. Salida: docs/catalogo_variables_escale.csv
"""
import re

import pandas as pd

import config
import utils

PALABRAS_INFRAESTRUCTURA = ("internet", "conectividad", "aula", "conservaci", "mantenimiento", "riesgo", "terreno", "saneamiento",
                            "servicios higi", "agua", "energ", "electric", "estado de", "techo", "pared", "piso", "biblioteca",
                            "laboratorio", "discapacidad", "rampa", "cerco", "titulo", "propiedad", "inversion", "construcc")
LINEA_CAMPO = re.compile(r"^(?P<campo>[A-Za-z][A-Za-z0-9_]*)\s+(?P<tipo>[CNDL])\s+\((?P<largo>[\d,]+)\)\s*(?P<resto>.*)$")


def descripciones(texto):
    """campo -> descripcion (la primera linea del diccionario mas las siguientes hasta la lista de opciones o el siguiente campo)."""
    lineas = texto.splitlines()
    salida, i = {}, 0
    while i < len(lineas):
        m = LINEA_CAMPO.match(lineas[i].strip())
        if m:
            partes = [m.group("resto").strip()]
            j = i + 1
            while j < len(lineas) and len(partes) < 4:
                s = lineas[j].strip()
                if not s or LINEA_CAMPO.match(s) or re.match(r"^\d+:", s):
                    break
                partes.append(s)
                j += 1
            salida.setdefault(m.group("campo").upper(), re.sub(r"\s+", " ", " ".join(partes)).strip())
            i = j
        else:
            i += 1
    return salida


def construir(anio=None):
    """Escribe docs/catalogo_variables_escale.csv para el anio indicado (por defecto el mas reciente descargado)."""
    anios = sorted(p.name for p in (config.INTERIM / "escale").iterdir() if p.is_dir() and p.name.isdigit())
    anio = str(anio or anios[-1])
    diccionarios = list(config.INTERIM_PDF.glob(f"escale_{anio}_diccionario*/texto_completo.txt"))
    textos = descripciones(diccionarios[0].read_text(encoding="utf-8")) if diccionarios else {}
    usadas = {"CODLOCAL", "CODGEO", "DPTO", "PROV", "DISTRITO", "AREA_CENSO", "GESTION", "D_GESTION", "ESTADO"}   # llaves y filtros
    usadas |= {col for col, _ in config.ESCALE_SERVICIOS_COLUMNAS.values()}
    for campos in config.ESCALE_EDIFICACIONES.values():
        usadas |= {campos["uso"], campos["riesgo"], *campos["estado"]}
    filas = []
    for ruta in sorted((config.INTERIM / "escale" / anio).rglob("*.dbf")):
        n_registros, _, _, _, campos = utils.campos_dbf(ruta)
        for nombre, tipo, largo, _ in campos:
            descripcion = textos.get(nombre.upper(), "")
            clave = f"{nombre} {descripcion}".lower()
            filas.append({"anio": int(anio), "archivo_dbf": ruta.name, "registros": n_registros, "campo": nombre, "tipo": tipo, "largo": largo,
                          "descripcion": descripcion, "se_usa_en_escale_infraestructura": nombre.upper() in usadas,
                          "posible_infraestructura": any(p in clave for p in PALABRAS_INFRAESTRUCTURA)})
    tabla = pd.DataFrame(filas)
    tabla.to_csv(config.DOCS / "catalogo_variables_escale.csv", index=False, encoding="utf-8-sig")
    utils.log(f"CATALOGO ESCALE {anio}: {len(tabla)} variables en {tabla.archivo_dbf.nunique()} archivos; "
              f"{int(tabla.posible_infraestructura.sum())} posibles de infraestructura; {int((tabla.descripcion != '').sum())} con descripcion")
    return tabla
