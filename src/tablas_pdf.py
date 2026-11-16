"""Fase 2 del proyecto PDF: extrae el texto y todas las tablas de cada documento a data/interim/pdf/{nombre}/.

Criterios de limpieza (se documentan tambien en docs/hallazgos_pdf.md):
  1. Las celdas combinadas de los PDF llegan como None: se quitan y cada fila queda "compactada".
  2. Solo se guardan tablas con numeros; las demas (vinetas, cuadros de texto) quedan en el catalogo como descartadas.
  3. El titulo es la linea "Tabla N. ..." mas cercana por encima de la tabla.
  4. Una tabla sin titulo que empieza en la pagina siguiente a otra sin fila 'Total' es su continuacion y se une a ella.
  5. Los encabezados no van en el CSV (van en el catalogo); en las celdas se quitan saltos de linea, comas de miles, 'S/' y '%'.
Los PDF originales no se modifican.
"""
import csv
import json
import re
import unicodedata
from pathlib import Path

import pdfplumber
from tqdm import tqdm

import config
import leer_pdf
from leer_pdf import log

COLUMNAS_CATALOGO = ["archivo", "fuente", "anio", "pagina", "pagina_fin", "tabla_n", "titulo", "tipo", "descripcion",
                     "filas", "columnas", "encabezado", "estado", "archivo_csv"]

REGEX_TITULO = re.compile(r"^(tabla|cuadro|gr[aá]fico|figura|mapa)\s*n?[°º.]?\s*(\d+)\s*[.:\-–]?\s*(.*)$", re.I)
REGEX_NUMERO = re.compile(r"^(S/\.?\s*)?-?\d[\d,]*(\.\d+)?\s*%?$")

# (patron sobre el titulo sin tildes y en minusculas, tipo); se usa la primera regla que coincide
REGLAS_TIPO = [
    (r"servicios de control.*departamento", "servicios_control_departamento"),
    (r"servicios de control.*nivel", "servicios_control_nivel_gobierno"),
    (r"servicios de control", "servicios_control_total"),
    (r"principales obras|paralizadas en (?!marcad)(?!el )(?!territorio)", "principales_obras_departamento"),
    (r"ubicacion geografica", "obras_por_departamento"),
    (r"evento registrado", "evento_infobras"),
    (r"nivel de avance", "sectores_avance_alto"),
    (r"nivel de gobierno", "nivel_gobierno"),
    (r"sector(es)? de gobierno", "sector_gobierno"),
    (r"marco normativo (segun|para|que)", "marco_normativo"),
    (r"^modalidades de ejecucion", "definicion_modalidades"),
    (r"modalidad de ejecucion", "modalidad_ejecucion"),
    (r"rango de costo", "rango_costo"),
    (r"rango de avance", "rango_avance_fisico"),
    (r"causal", "causal_paralizacion"),
    (r"asignacion de pim.*departamento", "pim_departamento"),
    (r"asignacion de pim", "pim_sector"),
    (r"estado situacional|resolucion de paralizacion", "estado_situacional"),
    (r"marco normativo|d\.?u\.? n|ley n", "obras_marco_normativo"),
]


def sin_tildes(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()


def clasificar(titulo):
    """Tipo de tabla segun las palabras de su titulo ('sin_titulo' si no tiene)."""
    if not titulo:
        return "sin_titulo"
    limpio = sin_tildes(titulo).lower()
    for patron, tipo in REGLAS_TIPO:
        if re.search(patron, limpio):
            return tipo
    return "otro"


# ---------------- limpieza de celdas y filas ----------------
def convertir_celda(celda):
    """'2,392,448,145' -> '2392448145'; '16.36%' -> '16.36'; 'S/ 1,234.50' -> '1234.5'; el texto solo pierde saltos de linea.

    Los numeros con ceros a la izquierda ('010101', ubigeos o codigos) se dejan como texto.
    """
    texto = re.sub(r"\s+", " ", str(celda)).strip()
    if REGEX_NUMERO.match(texto):
        numero = re.sub(r"^S/\.?\s*|\s*%$", "", texto).replace(",", "")
        if re.match(r"^-?0\d", numero):
            return texto
        valor = float(numero)
        return str(int(valor)) if valor == int(valor) and "." not in numero else numero
    return texto


def compactar(fila):
    """Quita las celdas vacias o None de una fila (vienen de celdas combinadas del PDF)."""
    return [c for c in (convertir_celda(x) for x in fila if x is not None) if c != ""]


def es_numerica(celda):
    return bool(REGEX_NUMERO.match(celda))


def es_fila_de_datos(fila):
    return sum(es_numerica(c) for c in fila) >= 2


def separar_encabezado(filas):
    """Filas compactadas -> (encabezado, datos): el encabezado son las filas antes de la primera fila con >= 2 numeros."""
    for i, fila in enumerate(filas):
        if es_fila_de_datos(fila):
            return filas[:i], filas[i:]
    return filas, []


def texto_del_encabezado(encabezado):
    celdas = []
    for fila in encabezado:
        celdas += [c for c in fila if c not in celdas]
    return " | ".join(celdas)


# ---------------- lectura de una pagina ----------------
def lineas_de_pagina(pagina):
    try:
        return pagina.extract_text_lines(return_chars=False)
    except Exception:
        return []


def titulo_sobre_tabla(lineas, tabla_top, limite_superior):
    """Titulo (Tabla N. ...) mas cercano por encima de la tabla; une la linea siguiente si el titulo continua en otra linea."""
    candidatas = [i for i, l in enumerate(lineas)
                  if l["bottom"] <= tabla_top + 3 and l["top"] >= limite_superior - 3 and REGEX_TITULO.match(l["text"].strip())]
    if not candidatas:
        return None
    i = candidatas[-1]
    partes = [lineas[i]["text"].strip()]
    for siguiente in lineas[i + 1:i + 3]:
        if siguiente["bottom"] <= tabla_top + 3 and not REGEX_TITULO.match(siguiente["text"].strip()):
            partes.append(siguiente["text"].strip())
    return " ".join(partes)


def tablas_de_pagina(pagina, numero):
    """Tablas de una pagina como lista de dicts (titulo, encabezado, filas compactadas, estado)."""
    lineas = lineas_de_pagina(pagina)
    salida, limite = [], 0
    try:
        encontradas = sorted(pagina.find_tables(), key=lambda t: t.bbox[1])
    except Exception as e:
        log(f"AVISO p.{numero}: no se pudieron buscar tablas ({type(e).__name__})")
        return salida
    for t in encontradas:
        try:
            filas = [compactar(f) for f in t.extract()]
        except Exception as e:
            log(f"AVISO p.{numero}: una tabla no se pudo leer ({type(e).__name__})")
            continue
        filas = [f for f in filas if f]
        encabezado, datos = separar_encabezado(filas)
        titulo = titulo_sobre_tabla(lineas, t.bbox[1], limite)
        if not datos:
            # fragmento de encabezado o cuadro de texto: queda anotado pero no se guarda
            salida.append({"pagina": numero, "titulo": titulo, "encabezado": encabezado, "datos": [], "estado": "descartada: sin numeros"})
            continue
        limite = t.bbox[3]
        salida.append({"pagina": numero, "titulo": titulo, "encabezado": encabezado, "datos": datos, "estado": "guardada"})
    return salida


def unir_continuaciones(tablas):
    """Une una tabla sin titulo con la tabla guardada de la pagina anterior si esta no terminaba en 'Total'."""
    resultado = []
    for t in tablas:
        if t["estado"] != "guardada":
            resultado.append(t)
            continue
        previa = next((r for r in reversed(resultado) if r["estado"] == "guardada"), None)
        if (previa and not t["titulo"] and t["pagina"] == previa["pagina_fin"] + 1 and not previa["cerrada"]
                and len(t["datos"][0]) == len(previa["datos"][-1])):
            previa["datos"] += t["datos"]
            previa["paginas_filas"] += [t["pagina"]] * len(t["datos"])
            previa["pagina_fin"] = t["pagina"]
            previa["cerrada"] = any(f[0].lower().startswith("total") for f in t["datos"])
            continue
        t["pagina_fin"] = t["pagina"]
        t["paginas_filas"] = [t["pagina"]] * len(t["datos"])
        t["cerrada"] = any(f[0].lower().startswith("total") for f in t["datos"])
        resultado.append(t)
    return resultado


# ---------------- un documento completo ----------------
def carpeta_de(ruta):
    return config.INTERIM_PDF / Path(ruta).stem


def escribir_tabla(carpeta, t, tabla_n, nombre_pdf):
    """Guarda una tabla como CSV con columnas de procedencia y devuelve el nombre del archivo."""
    ancho = max(len(f) for f in t["datos"])
    nombre = f"tablas_p{t['pagina']:02d}_t{tabla_n}.csv"
    with open(carpeta / nombre, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.writer(f)
        escritor.writerow(["fuente_pdf", "pagina", "tabla_n"] + [f"col_{i}" for i in range(1, ancho + 1)])
        for fila, pagina in zip(t["datos"], t["paginas_filas"]):
            escritor.writerow([nombre_pdf, pagina, tabla_n] + fila + [""] * (ancho - len(fila)))
    return nombre, ancho


def procesar_documento(ruta, fila_inventario):
    """Extrae texto y tablas de un PDF. Devuelve (filas_del_catalogo, paginas_sin_texto)."""
    carpeta = carpeta_de(ruta)
    carpeta.mkdir(parents=True, exist_ok=True)
    for viejo in list(carpeta.glob("tablas_p*.csv")) + list(carpeta.glob("texto_p*.txt")):
        viejo.unlink()
    todas, sin_texto, textos = [], [], []
    with pdfplumber.open(ruta) as pdf:
        for numero, pagina in enumerate(tqdm(pdf.pages, desc=Path(ruta).name[:40], leave=False), 1):
            try:
                texto = pagina.extract_text() or ""
            except Exception:
                texto = leer_pdf.texto_pagina(ruta, numero)   # respaldo con pypdf
            (carpeta / f"texto_p{numero:02d}.txt").write_text(texto, encoding="utf-8")
            textos.append(f"=== pagina {numero} ===\n{texto}\n")
            if len(texto.strip()) < config.MIN_CARACTERES_PAGINA:
                sin_texto.append(numero)
            todas += tablas_de_pagina(pagina, numero)
            pagina.flush_cache()
    (carpeta / "texto_completo.txt").write_text("\n".join(textos), encoding="utf-8")
    filas_catalogo, por_pagina = [], {}
    for t in unir_continuaciones(todas):
        por_pagina[t["pagina"]] = por_pagina.get(t["pagina"], 0) + 1
        n = por_pagina[t["pagina"]]
        if t["estado"] == "guardada":
            nombre_csv, ancho = escribir_tabla(carpeta, t, n, Path(ruta).name)
        else:
            nombre_csv, ancho = "", max([len(f) for f in t["encabezado"]] or [0])
        tipo = clasificar(t["titulo"]) if t["titulo"] else ("continuacion" if t["estado"] == "guardada" else "sin_titulo")
        filas_catalogo.append({
            "archivo": Path(ruta).name, "fuente": fila_inventario["fuente"], "anio": fila_inventario["anio"],
            "pagina": t["pagina"], "pagina_fin": t.get("pagina_fin", t["pagina"]), "tabla_n": n, "titulo": t["titulo"] or "",
            "tipo": tipo, "descripcion": re.sub(r"^\S+\s*N?[°º.]?\s*\d+[.:]?\s*", "", t["titulo"] or "").strip(),
            "filas": len(t["datos"]), "columnas": ancho, "encabezado": texto_del_encabezado(t["encabezado"]),
            "estado": t["estado"], "archivo_csv": nombre_csv})
    with open(carpeta / "catalogo.csv", "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS_CATALOGO)
        escritor.writeheader()
        escritor.writerows(filas_catalogo)
    return filas_catalogo, sin_texto


def extraer_todo(forzar=False):
    """Procesa cada PDF del inventario que no tenga su marca _ok.json (o todos con forzar). Reune docs/catalogo_tablas.csv."""
    inventario = leer_pdf.leer_inventario()
    procesados = omitidos = 0
    for clave, fila in tqdm(sorted(inventario.items()), desc="documentos"):
        ruta = config.RAIZ / clave
        if fila["lectura"] != "ok" or ruta.suffix.lower() != ".pdf":
            continue
        marca = carpeta_de(ruta) / "_ok.json"
        peso = ruta.stat().st_size
        if not forzar and marca.exists() and json.loads(marca.read_text(encoding="utf-8")).get("peso_bytes") == peso:
            omitidos += 1
            continue
        try:
            catalogo, sin_texto = procesar_documento(ruta, fila)
        except Exception as e:
            log(f"ERROR {ruta.name}: {type(e).__name__}: {str(e)[:120]}")
            continue
        guardadas = sum(c["estado"] == "guardada" for c in catalogo)
        log(f"Fase 2: {ruta.name}: {guardadas} tablas guardadas de {len(catalogo)} detectadas; paginas sin texto: {len(sin_texto)}"
            + (f" {sin_texto[:15]}" if sin_texto else ""))
        marca.write_text(json.dumps({"peso_bytes": peso, "tablas_guardadas": guardadas, "paginas_sin_texto": sin_texto}), encoding="utf-8")
        procesados += 1
    return reunir_catalogo(), procesados, omitidos


def reunir_catalogo():
    """Junta los catalogo.csv de cada documento en docs/catalogo_tablas.csv."""
    filas = []
    for archivo in sorted(config.INTERIM_PDF.glob("*/catalogo.csv")):
        with open(archivo, newline="", encoding="utf-8-sig") as f:
            filas += list(csv.DictReader(f))
    with open(config.CATALOGO_TABLAS, "w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS_CATALOGO)
        escritor.writeheader()
        escritor.writerows(filas)
    return filas
