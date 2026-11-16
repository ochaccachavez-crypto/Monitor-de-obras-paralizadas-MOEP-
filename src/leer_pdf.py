"""Fase 1 del proyecto PDF: inventario de los PDF/PPT descargados y lectura segura de paginas.

Nunca se modifica un PDF original: solo se abre en modo lectura.
"""
import csv
from datetime import date
from pathlib import Path

import pdfplumber
import pypdf
from tqdm import tqdm

import config
import utils

COLUMNAS_INVENTARIO = ["archivo", "fuente", "anio", "fecha_corte", "paginas", "tipo_texto", "escaneado",
                       "n_tablas", "peso_mb", "ruta", "lectura", "fecha_inventario"]


def log(mensaje):
    utils.log(mensaje, config.LOG_PDF)


# ---------------- lectura de paginas (pdfplumber y, si falla, pypdf) ----------------
def texto_pagina(ruta, numero):
    """Texto de una pagina (1 = primera). Usa pdfplumber y, si falla, pypdf. Devuelve '' si no hay texto."""
    try:
        with pdfplumber.open(ruta) as pdf:
            return pdf.pages[numero - 1].extract_text() or ""
    except Exception as e:
        log(f"AVISO {Path(ruta).name} p.{numero}: pdfplumber fallo ({type(e).__name__}); se usa pypdf")
        try:
            return pypdf.PdfReader(str(ruta)).pages[numero - 1].extract_text() or ""
        except Exception as e2:
            log(f"ERROR {Path(ruta).name} p.{numero}: pypdf tambien fallo ({type(e2).__name__})")
            return ""


def numero_de_paginas(ruta):
    try:
        with pdfplumber.open(ruta) as pdf:
            return len(pdf.pages)
    except Exception:
        return len(pypdf.PdfReader(str(ruta)).pages)


# ---------------- datos de cada documento ----------------
def fuente_y_anio(ruta):
    """data/raw/{fuente}/{anio}/archivo.pdf -> ('contraloria', '2023'); fuera de ese esquema -> ('otro', '')."""
    partes = Path(ruta).relative_to(config.RAW).parts
    return (partes[0], partes[1]) if len(partes) >= 3 else ("otro", "")


def fechas_de_corte():
    """archivo -> fecha de corte del dato, leida del registro de fuentes."""
    if not config.REGISTRO.exists():
        return {}
    with open(config.REGISTRO, newline="", encoding="utf-8-sig") as f:
        return {fila["archivo"]: fila["fecha_corte_del_dato"] for fila in csv.DictReader(f) if fila["estado"] == "ok"}


def clasificar_texto(ruta, paginas):
    """'seleccionable', 'escaneado' o 'mixto', probando las primeras paginas y una del medio.

    Un PDF escaneado es una imagen: no tiene letras que se puedan copiar y necesitaria OCR.
    """
    muestra = sorted({*range(1, min(config.PAGINAS_PRUEBA_TEXTO, paginas) + 1), (paginas + 1) // 2})
    con_texto = sum(len(texto_pagina(ruta, n).strip()) >= config.MIN_CARACTERES_PAGINA for n in muestra)
    if con_texto == len(muestra):
        return "seleccionable"
    return "escaneado" if con_texto == 0 else "mixto"


def contar_tablas(ruta):
    """Numero de tablas que detecta pdfplumber en todo el documento."""
    total = 0
    with pdfplumber.open(ruta) as pdf:
        for pagina in pdf.pages:
            try:
                total += len(pagina.find_tables())
            except Exception:
                pass
    return total


def describir(ruta, cortes):
    ruta = Path(ruta)
    fuente, anio = fuente_y_anio(ruta)
    fila = {"archivo": ruta.name, "fuente": fuente, "anio": anio, "fecha_corte": cortes.get(ruta.name, ""),
            "peso_mb": round(ruta.stat().st_size / 1024 / 1024, 3), "ruta": str(ruta.relative_to(config.RAIZ)),
            "fecha_inventario": str(date.today())}
    if ruta.suffix.lower() != ".pdf":
        fila.update(paginas="", tipo_texto="no analizado", escaneado="", n_tablas="", lectura="presentacion: sin lector")
        return fila
    try:
        paginas = numero_de_paginas(ruta)
        tipo = clasificar_texto(ruta, paginas)
        fila.update(paginas=paginas, tipo_texto=tipo, escaneado=(tipo != "seleccionable"),
                    n_tablas=contar_tablas(ruta) if tipo != "escaneado" else 0, lectura="ok")
    except Exception as e:
        fila.update(paginas="", tipo_texto="ilegible", escaneado="", n_tablas="", lectura=f"error: {type(e).__name__}")
        log(f"ERROR inventario {ruta.name}: {type(e).__name__}: {str(e)[:100]}")
    return fila


# ---------------- inventario ----------------
def leer_inventario():
    if not config.INVENTARIO_PDF.exists():
        return {}
    with open(config.INVENTARIO_PDF, newline="", encoding="utf-8-sig") as f:
        return {fila["ruta"]: fila for fila in csv.DictReader(f)}


def listar_documentos():
    return sorted(p for p in config.RAW.rglob("*") if p.is_file() and p.suffix.lower() in config.EXTENSIONES_DOCUMENTO)


def construir_inventario(forzar=False):
    """Crea o completa docs/inventario_pdf.csv. Un documento ya inventariado (misma ruta y mismo peso) no se vuelve a analizar."""
    previo = {} if forzar else leer_inventario()
    cortes = fechas_de_corte()
    filas, nuevos = [], 0
    for ruta in tqdm(listar_documentos(), desc="inventario PDF"):
        clave = str(ruta.relative_to(config.RAIZ))
        peso = round(ruta.stat().st_size / 1024 / 1024, 3)
        if clave in previo and float(previo[clave]["peso_mb"]) == peso and previo[clave]["lectura"] != "":
            filas.append(previo[clave])
            continue
        filas.append(describir(ruta, cortes))
        nuevos += 1
    filas.sort(key=lambda f: (f["fuente"], f["anio"], f["archivo"]))
    config.INVENTARIO_PDF.parent.mkdir(parents=True, exist_ok=True)
    with open(config.INVENTARIO_PDF, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS_INVENTARIO)
        escritor.writeheader()
        escritor.writerows(filas)
    escaneados = [f["archivo"] for f in filas if str(f["escaneado"]) == "True"]
    log(f"Fase 1: {len(filas)} documentos en el inventario ({nuevos} analizados ahora, {len(filas) - nuevos} ya estaban); "
        f"escaneados o mixtos: {len(escaneados)}")
    return filas
