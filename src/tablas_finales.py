"""Fase 3 del proyecto PDF: tablas finales de los informes de la Contraloria (cifras oficiales, causales, distribuciones).

De donde sale cada dato:
  * Informes 2023-2026: las tablas que extrajo tablas_pdf.py (data/interim/pdf/.../tablas_pNN_tM.csv).
  * Informes de 2022: pdfplumber no detecta bien sus tablas, asi que se lee el texto de la pagina (texto_pNN.txt).
Criterios (tambien en docs/hallazgos_pdf.md):
  * Las filas partidas en dos lineas fisicas se unen (la segunda fila empieza con un numero).
  * El orden de las columnas obras / costo / saldo cambia entre informes: se asigna por magnitud
    (obras = la suma mas pequena, costo = la mas grande, saldo = la restante).
  * Cada cifra lleva fuente_pdf, pagina y tabla_n para poder volver al PDF.
"""
import re
import unicodedata
from pathlib import Path

import pandas as pd

import config
import leer_pdf
import tablas_pdf
from leer_pdf import log

COLUMNAS_PROCEDENCIA = ["fuente_pdf", "pagina", "tabla_n"]


# ---------------- utilidades ----------------
def normalizar(texto):
    """'Áncash ' -> 'ANCASH' (mayusculas, sin tildes, sin espacios repetidos)."""
    sin = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin).strip().upper()


def departamento_canonico(nombre):
    n = re.sub(r"[\d*]+$", "", normalizar(nombre)).strip()
    if "CALLAO" in n:
        return "CALLAO"
    return n if n in config.DEPARTAMENTOS else None


def a_numero(celda):
    """'1,234.5' -> 1234.5; '2,849,716 ,176' (espacio suelto del PDF) -> 2849716176; '-' (sin monto) -> 0."""
    texto = str(celda).replace(",", "").replace(" ", "")
    if texto == "-":
        return 0.0
    try:
        return float(texto)
    except ValueError:
        return None


def informes_contraloria():
    """Informes PDF de la Contraloria con su fecha de corte (leida del registro de fuentes)."""
    filas = []
    for fila in leer_pdf.leer_inventario().values():
        if fila["fuente"] == "contraloria" and fila["archivo"].endswith(".pdf"):
            filas.append({"archivo": fila["archivo"], "fecha_corte": fila["fecha_corte"], "anio": int(fila["fecha_corte"][:4]),
                          "carpeta": config.INTERIM_PDF / Path(fila["archivo"]).stem})
    return sorted(filas, key=lambda f: f["fecha_corte"])


def tablas_de(informe, tipo):
    """Tablas guardadas de un tipo en un informe: lista de (meta, filas) con las columnas de procedencia ya quitadas."""
    catalogo = pd.read_csv(config.CATALOGO_TABLAS, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    seleccion = catalogo[(catalogo.archivo == informe["archivo"]) & (catalogo.tipo == tipo) & (catalogo.estado == "guardada")]
    resultado = []
    for _, meta in seleccion.iterrows():
        tabla = pd.read_csv(informe["carpeta"] / meta.archivo_csv, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        filas = [[c for c in fila[3:] if c != ""] for fila in tabla.values.tolist()]
        resultado.append((meta, filas))
    return resultado


def procedencia(informe, meta):
    return {"fuente_pdf": informe["archivo"], "pagina": int(meta["pagina"]), "tabla_n": int(meta["tabla_n"])}


# ---------------- tablas de pdfplumber (2023-2026) ----------------
def reparar_filas(filas):
    """Une las filas partidas: si una fila empieza con un numero y la anterior quedo corta, es su continuacion."""
    ancho = max(len(f) for f in filas)
    salida = []
    for fila in filas:
        if salida and tablas_pdf.es_numerica(fila[0]) and len(salida[-1]) < ancho:
            salida[-1] = salida[-1] + fila
        else:
            salida.append(list(fila))
    return salida


def asignar_bloques(registros):
    """registros: lista de (etiqueta, [5 o 6 numeros]) -> DataFrame con obras, costo y saldo (y sus porcentajes).

    Los numeros vienen como [A, %A, B, %B, C, (%C)]. Cual es obras, costo y saldo se decide por la suma de cada columna.
    """
    arreglados = []
    for etiqueta, n in registros:
        if len(n) == 6 and n[4] <= 100 < n[5]:   # a veces el porcentaje y el monto del saldo vienen intercambiados
            n = n[:4] + [n[5], n[4]]
        arreglados.append((etiqueta, n))
    cuerpo = [n for e, n in arreglados if not e.lower().startswith("total")] or [n for e, n in arreglados]
    sumas = [sum(n[i] for n in cuerpo) for i in (0, 2, 4)]
    i_obras = sumas.index(min(sumas))
    resto = [i for i in range(3) if i != i_obras]
    i_costo, i_saldo = (resto[0], resto[1]) if sumas[resto[0]] >= sumas[resto[1]] else (resto[1], resto[0])
    filas = []
    for etiqueta, n in arreglados:
        pct = lambda i: n[2 * i + 1] if 2 * i + 1 < len(n) else None
        filas.append({"etiqueta": etiqueta, "obras": n[2 * i_obras], "pct_obras": pct(i_obras), "costo": n[2 * i_costo],
                      "pct_costo": pct(i_costo), "saldo": n[2 * i_saldo], "pct_saldo": pct(i_saldo)})
    return pd.DataFrame(filas)


ETIQUETA_FALSO_TOTAL = "FILA ROTULADA TOTAL EN EL PDF (NO ES EL TOTAL)"


def bloques_de_filas(filas, obras_nacional=None):
    """Filas de una tabla -> DataFrame con obras, costo y saldo.

    Si una fila 'Total' es menor que la suma de las demas filas hay dos casos (se distinguen con el total nacional):
      * las demas filas ya suman el total nacional -> el 'Total' del PDF esta mal (p. ej. copiado de otro informe): se descarta;
      * no suman                                    -> esa fila es otra categoria mal rotulada 'Total': se conserva aparte.
    """
    registros = []
    for fila in reparar_filas(filas):
        numeros = [a_numero(c) for c in fila[1:]]
        if len(numeros) in (5, 6) and None not in numeros:
            registros.append((fila[0], numeros))
    if not registros:
        return pd.DataFrame()
    tabla = asignar_bloques(registros)
    es_t = tabla.etiqueta.map(lambda e: str(e).strip().lower().startswith("total"))
    if es_t.any() and obras_nacional is not None and tabla[es_t].obras.iloc[0] < tabla[~es_t].obras.sum():
        if tabla[~es_t].obras.sum() == obras_nacional:
            log("AVISO Fase 3: el 'Total' de una tabla no coincide con la suma de sus filas (que si suma el total nacional); se descarta")
            tabla = tabla[~es_t].reset_index(drop=True)
        else:
            log("AVISO Fase 3: una fila rotulada 'Total' no es el total; se conserva como categoria aparte")
            tabla.loc[es_t, "etiqueta"] = ETIQUETA_FALSO_TOTAL
    return tabla


def sector_de_filas(filas):
    """Tabla por sector: [nacional, regional, local, total, % obras, costo, % costo]."""
    registros = []
    for fila in filas:
        n = [a_numero(c) for c in fila[1:]]
        if len(n) == 7 and None not in n:
            registros.append({"etiqueta": fila[0], "obras_nacional": n[0], "obras_regional": n[1], "obras_local": n[2],
                              "obras": n[3], "pct_obras": n[4], "costo": n[5], "pct_costo": n[6]})
    return pd.DataFrame(registros)


# ---------------- texto de los informes de 2022 ----------------
def pagina_con(informe, patron, desde=8):
    """(numero, texto) de la primera pagina cuyo texto cumple el patron."""
    for archivo in sorted(informe["carpeta"].glob("texto_p*.txt")):
        numero = int(archivo.stem.split("_p")[1])
        texto = archivo.read_text(encoding="utf-8")
        if numero >= desde and re.search(patron, texto):
            return numero, texto
    return None, ""


def es_porcentaje(token):
    return "%" in token or "." in token


def partir_en_dos(grupos):
    """['258','824','516','136','132','368'] -> (258824516, 136132368): se elige el corte donde costo >= saldo y los largos se parecen."""
    mejor = None
    for k in range(1, len(grupos)):
        izq, der = grupos[:k], grupos[k:]
        if len(izq[0]) > 3 or len(der[0]) > 3 or any(len(g) != 3 for g in izq[1:] + der[1:]):
            continue
        a, b = int("".join(izq)), int("".join(der))
        if a >= b:
            diferencia = abs(len("".join(izq)) - len("".join(der)))
            if mejor is None or diferencia < mejor[0]:
                mejor = (diferencia, a, b)
    return (mejor[1], mejor[2]) if mejor else (None, None)


def numeros_de_tokens(tokens):
    """Tokens de una fila de 2022 -> (enteros, porcentajes). Los montos usan espacio como separador de miles.

    Un grupo de 1 o 2 digitos siempre inicia un numero nuevo (los demas grupos tienen 3 digitos). Si quedan solo 2 enteros
    (obras + un bloque con costo y saldo pegados y todos de 3 digitos) se parte el bloque donde costo >= saldo.
    """
    corridas, porcentajes, actual = [], [], []
    for t in tokens:
        limpio = t.replace(",", "")
        if es_porcentaje(t):
            if actual:
                corridas.append(actual)
                actual = []
            try:
                porcentajes.append(float(limpio.rstrip("%")))
            except ValueError:
                pass
        elif limpio.isdigit():
            actual.append(limpio)
    if actual:
        corridas.append(actual)
    enteros = []
    for grupos in corridas:
        piezas = [[grupos[0]]]
        for g in grupos[1:]:
            (piezas[-1].append(g) if len(g) == 3 else piezas.append([g]))
        enteros.append([int("".join(p)) for p in piezas])
    planos = [n for lista in enteros for n in lista]
    if len(planos) == 2:
        larga = max(range(len(corridas)), key=lambda i: len(corridas[i]))
        a, b = partir_en_dos(corridas[larga])
        if a is not None:
            enteros[larga] = [a, b]
            planos = [n for lista in enteros for n in lista]
    return planos, porcentajes


def fila_2022(linea):
    """'Incumplimiento de contrato 314 13.4 9 568 323 713 4 840 583 487 33.0' -> (etiqueta, [3 enteros], porcentajes) o None."""
    linea = re.sub(r"(?<=\d),(?=\d{3})", " ", linea.strip())   # '5,788 631 244' es 5 788 631 244
    linea = re.sub(r"^\d+\s+(?=\D)", "", linea)                    # numero suelto de pie de pagina delante de la etiqueta
    m = re.match(r"^(\D+?(?:-\d+)?)\s+(\d.*)$", linea)              # la etiqueta puede terminar en '-19' (Covid-19)
    if not m:
        return None
    tokens = m.group(2).split()
    for _ in range(2):
        enteros, porcentajes = numeros_de_tokens(tokens)
        if len(enteros) == 3 and porcentajes and max(enteros) < 10 ** 12:
            return m.group(1).strip(" ."), enteros, porcentajes
        if not tokens[-1].isdigit():
            break
        tokens = tokens[:-1]   # a veces el ultimo porcentaje viene sin punto ('780' es 78.0%): se descarta
    return None


def tabla_de_texto(texto, titulo, fin=r"^(\(\*\)|\*|FUENTE|Total)"):
    """Filas (etiqueta, [obras, costo, saldo]) entre la linea del titulo y la fila Total (incluida)."""
    lineas = texto.splitlines()
    inicio = next((i for i, l in enumerate(lineas) if re.search(titulo, l, re.I)), None)
    if inicio is None:
        return []
    salida = []
    for linea in lineas[inicio + 1:]:
        fila = fila_2022(linea)
        if fila:
            salida.append(fila)
            if fila[0].lower().startswith("total"):
                break
    return salida


def bloques_de_texto(texto, titulo):
    """Tabla de 2022 como DataFrame (etiqueta, obras, costo, saldo); roles por magnitud (obras < saldo <= costo)."""
    filas = tabla_de_texto(texto, titulo)
    registros = []
    for etiqueta, enteros, porcentajes in filas:
        ordenados = sorted(enteros)
        registros.append({"etiqueta": etiqueta, "obras": ordenados[0], "saldo": ordenados[1], "costo": ordenados[2]})
    return pd.DataFrame(registros)


def sector_de_texto(texto):
    """Tabla 4 de 2022: 'Educacion 44 55 132 231 9.8 1 376 070 230 [3.5]' -> nacional, regional, local, total, costo."""
    lineas = texto.splitlines()
    inicio = next((i for i, l in enumerate(lineas) if re.search(r"TABLA 4", l)), None)
    registros = []
    for linea in lineas[inicio + 1:] if inicio is not None else []:
        m = re.match(r"^(\D+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\S+)\s+(.*)$", linea.strip())
        if not m or "Cantidad" in linea:
            continue
        nac, reg, loc, total = (int(m.group(i)) for i in range(2, 6))
        if nac + reg + loc != total:
            continue
        resto = m.group(7).split()
        if resto and es_porcentaje(resto[-1]):
            resto = resto[:-1]
        if not all(t.isdigit() for t in resto):
            continue
        registros.append({"etiqueta": m.group(1).strip(), "obras_nacional": nac, "obras_regional": reg, "obras_local": loc,
                          "obras": total, "pct_obras": float(m.group(6).rstrip("%")), "costo": float("".join(resto)) if resto else None})
        if m.group(1).strip().lower().startswith("total"):
            break
    return pd.DataFrame(registros)


NOMBRES_MAPA = sorted([*config.DEPARTAMENTOS, "P. C. DEL CALLAO", "PROVINCIA CONSTITUCIONAL DEL CALLAO"], key=len, reverse=True)


def nombres_en_linea(linea):
    """Nombres de departamento de una linea del mapa de 2022; None si la linea trae otras cosas."""
    resto = normalizar(linea)
    encontrados = []
    while resto:
        for nombre in NOMBRES_MAPA:
            if resto.startswith(nombre):
                encontrados.append(departamento_canonico(nombre))
                resto = resto[len(nombre):].strip()
                break
        else:
            return None
    return encontrados


def montos_en_millones(linea):
    """'S/ 18 656 3 S/ 40.7' -> [18656.3, 40.7]: se lee cada tramo 'S/ ...' por separado; un token con punto cierra el numero
    y '18 656 3' es una errata de 18 656.3."""
    montos = []
    for tramo in linea.split("S/"):
        acumulado = []
        for token in tramo.split():
            if "." in token:
                montos.append(float("".join(acumulado) + token))
                acumulado = []
            else:
                acumulado.append(token)
        if acumulado:
            if len(acumulado) >= 2 and len(acumulado[-1]) == 1:
                montos.append(float("".join(acumulado[:-1]) + "." + acumulado[-1]))
            else:
                montos.append(float("".join(acumulado)))
    return montos


def departamentos_de_texto(texto):
    """Figura 1 de 2022 (mapa): bloques de nombres + linea de costo con % + linea de obras con % + linea de saldo.

    En junio los montos vienen en soles; en setiembre y diciembre vienen en millones con un decimal (precision de 100 mil soles).
    """
    lineas = [l.strip() for l in texto.splitlines()]
    registros = []
    for i, linea in enumerate(lineas[:-3]):
        nombres = nombres_en_linea(linea)
        if not nombres:
            continue
        costos = re.findall(r"((?:S/)?\s*\d[\d ]*(?:\.\d+)?)\s*\(?([\d.]+)%\)", lineas[i + 1])   # a veces falta el '('  
        obras = re.findall(r"(\d+)\s*\(([\d.]+)%\)", lineas[i + 2])
        en_millones = bool(costos) and "." in costos[0][0]
        saldos = montos_en_millones(lineas[i + 3]) if en_millones else [s for s in re.split(r"S/", lineas[i + 3]) if s.strip()]
        if not (len(nombres) == len(costos) == len(obras) == len(saldos)):
            continue
        for nombre, (c, pc), (o, po), s in zip(nombres, costos, obras, saldos):
            monto = (lambda x: round(float(re.sub(r"[^\d.]", "", x)) * 1_000_000)) if en_millones else (lambda x: float(re.sub(r"\D", "", x)))
            registros.append({"etiqueta": nombre, "obras": int(o), "pct_obras": float(po), "costo": monto(c), "pct_costo": float(pc),
                              "saldo": round(s * 1_000_000) if en_millones else monto(s), "pct_saldo": None, "unidad_original": "millones de soles (1 decimal)" if en_millones else "soles"})
    return pd.DataFrame(registros)


# ---------------- ensamblado de las tablas finales ----------------
COLUMNAS_CIFRAS = ["anio", "fecha_corte", "ambito", "categoria", "cod_departamento", "obras_paralizadas", "pct_obras",
                   "costo_actualizado_soles", "pct_costo", "saldo_inversion_soles", "obras_g_nacional", "obras_g_regional",
                   "obras_g_local", "unidad_original", "fuente_pdf", "pagina", "tabla_n"]
COLUMNAS_CAUSALES = ["anio", "fecha_corte", "causal", "obras_paralizadas", "pct_obras", "costo_actualizado_soles", "pct_costo",
                     "saldo_inversion_soles", "pct_saldo", "fuente_pdf", "pagina", "tabla_n"]
COLUMNAS_DISTRIBUCIONES = ["anio", "fecha_corte", "dimension", "categoria", "obras_paralizadas", "pct_obras",
                           "costo_actualizado_soles", "pct_costo", "saldo_inversion_soles", "pct_saldo", "fuente_pdf", "pagina", "tabla_n"]


def es_total(etiqueta):
    return str(etiqueta).strip().lower().startswith("total")


def tabla_unica(informe, tipo, convertir):
    """Primera tabla del tipo que se pueda convertir; devuelve (DataFrame, procedencia) o (vacio, None)."""
    for meta, filas in tablas_de(informe, tipo):
        tabla = convertir(filas)
        if len(tabla):
            return tabla, procedencia(informe, meta)
    return pd.DataFrame(), None


def nivel_2023_en_adelante(informe, obras_nacional):
    """La tabla de nivel de gobierno es la que tiene filas Nacional/Regional/Local y un Total igual al total nacional."""
    for meta, filas in tablas_de(informe, "nivel_gobierno"):
        tabla = bloques_de_filas(filas)
        if len(tabla) and any("nacional" in e.lower() for e in tabla.etiqueta) and es_total(tabla.etiqueta.iloc[-1]) \
                and tabla.obras.iloc[-1] == obras_nacional:
            return tabla, procedencia(informe, meta)
    return pd.DataFrame(), None


def leer_informe(informe):
    """Todas las tablas finales de un informe: dict con departamentos, sector, causales, nivel, rangos y su procedencia (_p)."""
    r = {"informe": informe}
    if informe["anio"] >= 2023:
        meta, filas = tablas_de(informe, "obras_por_departamento")[0]
        r["dep"], r["dep_p"] = bloques_de_filas(recuperar_departamentos(informe, meta, filas)), procedencia(informe, meta)
        total = r["dep"][r["dep"].etiqueta.map(es_total)]
        obras_nacional = total.obras.iloc[0] if len(total) else r["dep"].obras.sum()
        con_nacional = lambda filas: bloques_de_filas(filas, obras_nacional)
        r["sector"], r["sector_p"] = tabla_unica(informe, "sector_gobierno", sector_de_filas)
        r["causal"], r["causal_p"] = tabla_unica(informe, "causal_paralizacion", con_nacional)
        r["rango_costo"], r["rango_costo_p"] = tabla_unica(informe, "rango_costo", con_nacional)
        r["rango_avance_fisico"], r["rango_avance_fisico_p"] = tabla_unica(informe, "rango_avance_fisico", con_nacional)
        r["nivel"], r["nivel_p"] = nivel_2023_en_adelante(informe, obras_nacional)
        return r

    def desde_texto(patron, numero_tabla, convertir):
        n, texto = pagina_con(informe, patron)
        return convertir(texto), {"fuente_pdf": informe["archivo"], "pagina": n, "tabla_n": numero_tabla}

    r["nivel"], r["nivel_p"] = desde_texto(r"TABLA 3\.", 3, lambda t: bloques_de_texto(t, r"TABLA 3\."))
    r["sector"], r["sector_p"] = desde_texto(r"TABLA 4\.", 4, sector_de_texto)
    r["causal"], r["causal_p"] = desde_texto(r"TABLA 8\.", 8, lambda t: bloques_de_texto(t, r"TABLA 8\."))
    r["dep"], r["dep_p"] = desde_texto(r"FIGURA 1\.", 1, departamentos_de_texto)
    rangos = rangos_2022(informe)   # B5: rangos de costo y de avance fisico, leidos por posicion de las palabras
    r["rango_costo"], r["rango_costo_p"] = rangos["rango_costo"]
    r["rango_avance_fisico"], r["rango_avance_fisico_p"] = rangos["rango_avance_fisico"]
    return r


def nacional_de(r):
    """(obras, costo, saldo) nacionales y su procedencia: fila Total de la tabla por departamento (en 2022, de nivel de gobierno)."""
    tabla, prov = (r["dep"], r["dep_p"]) if r["informe"]["anio"] >= 2023 else (r["nivel"], r["nivel_p"])
    total = tabla[tabla.etiqueta.map(es_total)]
    if len(total):
        t = total.iloc[0]
        return {"obras": t.obras, "costo": t.costo, "saldo": t.saldo}, prov
    return {"obras": tabla.obras.sum(), "costo": tabla.costo.sum(), "saldo": tabla.saldo.sum()}, prov   # sin fila Total (febrero 2023)


def construir_tablas_finales():
    """Devuelve (cifras, causales, distribuciones, avisos, lecturas); lecturas guarda lo leido de cada informe para validar."""
    cifras, causales, distribuciones, avisos, lecturas = [], [], [], [], []
    for informe in informes_contraloria():
        r = leer_informe(informe)
        lecturas.append(r)
        base = {"anio": informe["anio"], "fecha_corte": informe["fecha_corte"]}
        nac, prov = nacional_de(r)
        cifras.append({**base, "ambito": "nacional", "categoria": "NACIONAL", "obras_paralizadas": nac["obras"], "pct_obras": 100.0,
                       "costo_actualizado_soles": nac["costo"], "pct_costo": 100.0, "saldo_inversion_soles": nac["saldo"],
                       "unidad_original": "soles", **prov})
        for _, f in r["dep"][~r["dep"].etiqueta.map(es_total)].iterrows():
            dep = departamento_canonico(f.etiqueta)
            if dep is None:
                avisos.append(f"{informe['fecha_corte']}: departamento no reconocido '{f.etiqueta}'")
                continue
            cifras.append({**base, "ambito": "departamento", "categoria": dep, "cod_departamento": config.DEPARTAMENTOS[dep],
                           "obras_paralizadas": f.obras, "pct_obras": f.pct_obras, "costo_actualizado_soles": f.costo,
                           "pct_costo": f.pct_costo, "saldo_inversion_soles": f.saldo,
                           "unidad_original": f.get("unidad_original", "soles"), **r["dep_p"]})
        for _, f in r["sector"][~r["sector"].etiqueta.map(es_total)].iterrows():
            cifras.append({**base, "ambito": "sector", "categoria": normalizar(f.etiqueta), "obras_paralizadas": f.obras,
                           "pct_obras": f.pct_obras, "costo_actualizado_soles": f.costo, "pct_costo": f.get("pct_costo"),
                           "obras_g_nacional": f.obras_nacional, "obras_g_regional": f.obras_regional,
                           "obras_g_local": f.obras_local, "unidad_original": "soles", **r["sector_p"]})
        for _, f in r["causal"][~r["causal"].etiqueta.map(es_total)].iterrows():
            causales.append({**base, "causal": re.sub(r"\s*(\(\*\)|\*)", "", normalizar(f.etiqueta)), "obras_paralizadas": f.obras, "pct_obras": f.get("pct_obras"),
                             "costo_actualizado_soles": f.costo, "pct_costo": f.get("pct_costo"), "saldo_inversion_soles": f.saldo,
                             "pct_saldo": f.get("pct_saldo"), **r["causal_p"]})
        for dimension in ("nivel", "rango_costo", "rango_avance_fisico"):
            tabla = r[dimension]
            if not len(tabla):
                if informe["anio"] >= 2023:
                    avisos.append(f"{informe['fecha_corte']}: no se encontro la tabla '{dimension}'")
                continue
            for _, f in tabla[~tabla.etiqueta.map(es_total)].iterrows():
                distribuciones.append({**base, "dimension": "nivel_gobierno" if dimension == "nivel" else dimension,
                                       "categoria": normalizar(f.etiqueta), "obras_paralizadas": f.obras, "pct_obras": f.get("pct_obras"),
                                       "costo_actualizado_soles": f.costo, "pct_costo": f.get("pct_costo"),
                                       "saldo_inversion_soles": f.saldo, "pct_saldo": f.get("pct_saldo"), **r[dimension + "_p"]})
    return (pd.DataFrame(cifras).reindex(columns=COLUMNAS_CIFRAS), pd.DataFrame(causales).reindex(columns=COLUMNAS_CAUSALES),
            pd.DataFrame(distribuciones).reindex(columns=COLUMNAS_DISTRIBUCIONES), avisos, lecturas)


# ---------------- recuperacion de filas que pdfplumber no incluyo ----------------
def recuperar_departamentos(informe, meta, filas):
    """Si a la tabla por departamento le falta alguno, busca su linea en el texto de las paginas de la tabla y la agrega."""
    presentes = {departamento_canonico(f[0]) for f in filas}
    faltan = [d for d in config.DEPARTAMENTOS if d not in presentes]
    if not faltan:
        return filas
    nuevas = []
    for pagina in range(int(meta["pagina"]), int(meta["pagina_fin"]) + 1):
        texto = (informe["carpeta"] / f"texto_p{pagina:02d}.txt").read_text(encoding="utf-8")
        for linea in texto.splitlines():
            partes = linea.split()
            for dep in faltan:
                nombre = dep.split()
                if [normalizar(p) for p in partes[:len(nombre)]] == nombre:
                    numeros = [t.rstrip("%") for t in partes[len(nombre):]]
                    if len(numeros) in (5, 6) and all(a_numero(n) is not None for n in numeros):
                        nuevas.append([linea.split(numeros[0])[0].strip()] + numeros)
    if nuevas:
        log(f"Fase 3: {informe['fecha_corte']}: se recuperaron del texto {len(nuevas)} fila(s) de departamento que faltaban en la tabla")
    # la fila Total debe quedar al final
    cuerpo = [f for f in filas if not es_total(f[0])]
    total = [f for f in filas if es_total(f[0])]
    return cuerpo + nuevas + total


def validar(cifras, causales, distribuciones, lecturas):
    """Comprobaciones por informe. Devuelve un DataFrame (una fila por comprobacion) con diferencia y si pasa."""
    checks = []

    def agregar(corte, nombre, a, b, tolerancia):
        diferencia = None if a is None or b is None else float(a) - float(b)
        checks.append({"fecha_corte": corte, "comprobacion": nombre, "valor_a": a, "valor_b": b, "diferencia": diferencia,
                       "tolerancia": tolerancia, "ok": diferencia is not None and abs(diferencia) <= tolerancia})

    for corte, c in cifras.groupby("fecha_corte"):
        nac = c[c.ambito == "nacional"].iloc[0]
        dep = c[c.ambito == "departamento"]
        sec = c[c.ambito == "sector"]
        tol_costo = 1_500_000 if (dep.unidad_original.astype(str).str.startswith("millones").any()) else config.TOLERANCIA_SOLES
        agregar(corte, "departamentos presentes (25)", len(dep), 25, 0)
        agregar(corte, "suma obras departamentos = total nacional", dep.obras_paralizadas.sum(), nac.obras_paralizadas, 0)
        agregar(corte, "suma costo departamentos = total nacional", dep.costo_actualizado_soles.sum(), nac.costo_actualizado_soles, tol_costo)
        agregar(corte, "suma saldo departamentos = total nacional", dep.saldo_inversion_soles.sum(), nac.saldo_inversion_soles, tol_costo)
        agregar(corte, "suma obras sectores = total nacional", sec.obras_paralizadas.sum(), nac.obras_paralizadas, 0)
        agregar(corte, "suma costo sectores = total nacional", sec.costo_actualizado_soles.sum(), nac.costo_actualizado_soles, config.TOLERANCIA_SOLES * 100)
        cs = causales[causales.fecha_corte == corte]
        agregar(corte, "suma obras causales = total nacional", cs.obras_paralizadas.sum(), nac.obras_paralizadas, 0)
        agregar(corte, "suma costo causales = total nacional", cs.costo_actualizado_soles.sum(), nac.costo_actualizado_soles, config.TOLERANCIA_SOLES * 100)
        ds = distribuciones[distribuciones.fecha_corte == corte]
        for dimension, grupo in ds.groupby("dimension"):
            agregar(corte, f"suma obras {dimension} = total nacional", grupo.obras_paralizadas.sum(), nac.obras_paralizadas, 0)
    return pd.DataFrame(checks)


# ---------------- validacion independiente con los anexos Excel de la Contraloria ----------------
def hoja_base(ruta):
    """(nombre de hoja, fila del encabezado) de la hoja obra por obra del anexo, o None si no tiene (la hoja trae SECTOR y DEPARTAMENTO)."""
    import openpyxl
    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    for hoja in libro.worksheets:
        if hoja.max_row < 1500:
            continue
        for i, fila in enumerate(hoja.iter_rows(min_row=1, max_row=8, values_only=True)):
            columnas = [normalizar(c) for c in fila if c is not None]
            if "SECTOR" in columnas and any(c.startswith("DEPARTAMENTO") for c in columnas):
                return hoja.title, i
    return None


def leer_base_excel(ruta):
    """Base obra por obra con columnas simples: codigo, departamento, sector, sector_agrupado, costo. None si el anexo no la trae.

    El informe agrupa los sectores (columna 'SECTOR 2' / 'SECTOR2'; en jun-2026 'EDUCACION' + 'EDUCACION/CULTURA'),
    por eso se guardan el sector estricto y el agrupado.
    """
    ubicada = hoja_base(ruta)
    if ubicada is None:
        return None
    hoja, fila_encabezado = ubicada
    base = pd.read_excel(ruta, sheet_name=hoja, header=fila_encabezado, dtype=str)
    base.columns = [normalizar(c) for c in base.columns]
    col = lambda patron: next(c for c in base.columns if re.match(patron, c))
    sector = base[col(r"SECTOR$")].map(normalizar)
    agrupada = next((c for c in base.columns if re.fullmatch(r"SECTOR ?2", c)), None)
    sector_agrupado = base[agrupada].map(normalizar) if agrupada else sector.replace({"EDUCACION/CULTURA": "EDUCACION"})
    salida = pd.DataFrame({
        "codigo": base[col(r"CODIGO INFOBRAS")], "departamento": base[col(r"DEPARTAMENTO")].map(departamento_canonico),
        "sector": sector, "sector_agrupado": sector_agrupado,
        "costo": pd.to_numeric(base[col(r"COSTO ACTUALIZADO")], errors="coerce")})
    return salida[salida.codigo.notna() & (salida.codigo.str.strip() != "")].assign(hoja=hoja)


def validar_con_excel(cifras):
    """Compara las cifras del PDF con el anexo Excel del mismo corte.

    Devuelve (comparacion, educacion_por_departamento, detalle); detalle tiene una fila por cifra comparada (nacional, cada
    departamento y la fila Educacion) para marcar en las cifras cuales coinciden con el Excel.
    """
    cortes = leer_pdf.fechas_de_corte()
    comparacion, educacion, detalle = [], [], []
    for ruta in sorted(config.RAW.glob("contraloria/*/*.xlsx")):
        if "anexo_03" in ruta.name or ruta.name not in cortes:
            continue
        base = leer_base_excel(ruta)
        if base is None:
            continue
        corte = cortes[ruta.name]
        pdf = cifras[cifras.fecha_corte == corte]
        if pdf.empty:
            continue
        nac = pdf[pdf.ambito == "nacional"].iloc[0]
        edu_pdf = pdf[(pdf.ambito == "sector") & (pdf.categoria == "EDUCACION")]
        edu = base[base.sector_agrupado == "EDUCACION"]
        for nombre, v_pdf, v_xls in [
                ("obras nacional", nac.obras_paralizadas, len(base)),
                ("costo actualizado nacional (S/)", nac.costo_actualizado_soles, base.costo.sum()),
                ("obras sector Educacion", edu_pdf.obras_paralizadas.iloc[0] if len(edu_pdf) else None, len(edu)),
                ("costo sector Educacion (S/)", edu_pdf.costo_actualizado_soles.iloc[0] if len(edu_pdf) else None, edu.costo.sum())]:
            dif = None if v_pdf is None or not v_pdf else (v_xls - v_pdf) / v_pdf * 100
            comparacion.append({"fecha_corte": corte, "anexo_excel": ruta.name, "hoja": base.hoja.iloc[0], "comprobacion": nombre,
                                "valor_pdf": v_pdf, "valor_excel": v_xls, "diferencia_pct": None if dif is None else round(dif, 3),
                                "ok_10pct": dif is not None and abs(dif) <= config.UMBRAL_DIFERENCIA_PCT})
        # detalle por cifra (para la columna coincide_excel)
        detalle.append({"fecha_corte": corte, "ambito": "nacional", "categoria": "NACIONAL", "obras_excel": len(base)})
        for dep, grupo in base.groupby("departamento"):
            detalle.append({"fecha_corte": corte, "ambito": "departamento", "categoria": dep, "obras_excel": len(grupo)})
        detalle.append({"fecha_corte": corte, "ambito": "sector", "categoria": "EDUCACION", "obras_excel": len(edu)})
        # educacion por departamento: la del informe (agrupada) y la estricta (solo SECTOR = EDUCACION)
        estricta = base[base.sector == "EDUCACION"]
        por_dep = edu.groupby("departamento").agg(obras_educacion=("codigo", "count"), costo_educacion_soles=("costo", "sum"))
        por_dep = por_dep.join(estricta.groupby("departamento").agg(obras_educacion_estricto=("codigo", "count"),
                                                                    costo_educacion_estricto_soles=("costo", "sum")), how="outer").fillna(0).reset_index()
        por_dep["anio"], por_dep["fecha_corte"] = int(corte[:4]), corte
        por_dep["cod_departamento"] = por_dep.departamento.map(config.DEPARTAMENTOS)
        por_dep["fuente_excel"], por_dep["hoja"] = ruta.name, base.hoja.iloc[0]
        educacion.append(por_dep)
    columnas = ["anio", "fecha_corte", "cod_departamento", "departamento", "obras_educacion", "costo_educacion_soles",
                "obras_educacion_estricto", "costo_educacion_estricto_soles", "fuente_excel", "hoja"]
    return (pd.DataFrame(comparacion), pd.concat(educacion)[columnas] if educacion else pd.DataFrame(columns=columnas),
            pd.DataFrame(detalle))


def marcar_coincidencia(cifras, detalle):
    """Agrega coincide_excel a las cifras: True/False si el anexo Excel del corte confirma (o no) el numero de obras; vacio si no hay Excel."""
    cifras = cifras.merge(detalle, on=["fecha_corte", "ambito", "categoria"], how="left")
    cifras["coincide_excel"] = (cifras.obras_excel == cifras.obras_paralizadas).where(cifras.obras_excel.notna())
    return cifras.drop(columns="obras_excel")


# ---------------- cruce de la base propia (INFOBRAS) con la lista oficial de la Contraloria ----------------
def cruzar_infobras_con_contraloria():
    """Compara las fichas de INFOBRAS con el anexo Excel mas reciente de la Contraloria que trae la base obra por obra.

    Devuelve una tabla de comprobaciones (cuantas obras hay en cada lado, cuantas en comun, si coinciden monto y departamento).
    """
    if not config.INFOBRAS_SALIDA.exists():
        return pd.DataFrame()
    fichas = pd.read_csv(config.INFOBRAS_SALIDA, dtype={"codigo_infobras": str}, encoding="utf-8-sig", parse_dates=["fecha_paralizacion"])
    cortes = leer_pdf.fechas_de_corte()
    anexos = [(cortes[r.name], r) for r in config.RAW.glob("contraloria/*/*.xlsx") if r.name in cortes and "anexo_03" not in r.name
              and hoja_base(r) is not None]
    if not anexos:
        return pd.DataFrame()
    corte, ruta = max(anexos, key=lambda a: a[0])
    hoja, fila = hoja_base(ruta)
    x = pd.read_excel(ruta, sheet_name=hoja, header=fila, dtype=str)
    x.columns = [normalizar(c) for c in x.columns]
    x["codigo"] = x[next(c for c in x.columns if c.startswith("CODIGO INFOBRAS"))].str.strip()
    tipo = x[next(c for c in x.columns if c.startswith("TIPO DE OBRA") and "NIVEL" not in c)].map(normalizar)
    educacion = x[tipo.str.contains("EDUC")]
    comunes = fichas.merge(x[["codigo", next(c for c in x.columns if c.startswith("COSTO DE OBRA")),
                              next(c for c in x.columns if c.startswith("DEPARTAMENTO"))]], left_on="codigo_infobras", right_on="codigo")
    costo_xlsx = pd.to_numeric(comunes[next(c for c in comunes.columns if c.startswith("COSTO DE OBRA"))], errors="coerce")
    dep_xlsx = comunes[next(c for c in comunes.columns if c.startswith("DEPARTAMENTO"))].map(departamento_canonico)
    n_comunes = len(comunes)
    fuera = fichas[~fichas.codigo_infobras.isin(x.codigo)]
    filas = [
        ("obras Educacion/Cultura en la lista de la Contraloria", len(educacion), f"{ruta.name} (corte {corte})"),
        ("obras paralizadas de Educacion/Cultura en INFOBRAS", len(fichas), f"fichas leidas el {fichas.fecha_lectura.iloc[0]}"),
        ("diferencia INFOBRAS vs Contraloria (%)", round((len(fichas) - len(educacion)) / len(educacion) * 100, 1), "supera el 10 %: son poblaciones distintas (ver hallazgos)"),
        ("obras presentes en ambas", n_comunes, "mismo codigo INFOBRAS"),
        ("de las comunes, monto del expediente tecnico igual (<=0.5 %)", int((((comunes.monto_expediente_tecnico - costo_xlsx).abs() / costo_xlsx) <= 0.005).sum()), f"de {n_comunes}"),
        ("de las comunes, mismo departamento", int((comunes.departamento == dep_xlsx).sum()), f"de {n_comunes}"),
        ("obras de INFOBRAS que no estan en la lista de la Contraloria", len(fuera), "motivo no verificado; hipotesis: la lista de la Contraloria sigue su propio criterio (inventario MEF / Invierte.pe) y no el estado de INFOBRAS"),
        ("  de ellas, paralizadas despues del corte", int((fuera.fecha_paralizacion > corte).sum()), f"fecha_paralizacion > {corte}"),
        ("obras de la lista de la Contraloria que INFOBRAS ya no marca Paralizada", int((~educacion.codigo.isin(fichas.codigo_infobras)).sum()), "motivo no verificado (reactivadas, concluidas u otro estado en INFOBRAS)"),
    ]
    return pd.DataFrame(filas, columns=["comprobacion", "valor", "detalle"])


# ---------------- Fase 3: guardar ----------------
def a_enteros(tabla, columnas):
    for c in columnas:
        if c in tabla:
            tabla[c] = pd.to_numeric(tabla[c], errors="coerce").round().astype("Int64")
    return tabla


def guardar_csv(tabla, ruta):
    """Guarda en UTF-8; los decimales se redondean a 4 cifras para que 56.91 no salga como 56.910000000000004."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tabla = tabla.copy()
    for columna in tabla.select_dtypes("float").columns:
        tabla[columna] = tabla[columna].round(4)
    tabla.to_csv(ruta, index=False, encoding="utf-8-sig", na_rep="")


def ejecutar_fase3():
    """Construye y guarda cifras_oficiales_contraloria, contraloria_causales, contraloria_distribuciones y
    contraloria_educacion_departamento (data/processed), y docs/validacion_pdf.csv y docs/validacion_excel.csv."""
    cifras, causales, distribuciones, avisos, lecturas = construir_tablas_finales()
    for aviso in avisos:
        log(f"AVISO Fase 3: {aviso}")
    comparacion, educacion, detalle = validar_con_excel(cifras)
    cifras = marcar_coincidencia(cifras, detalle)
    cifras["observacion"] = ""
    cifras.loc[cifras.coincide_excel == False, "observacion"] = "no coincide con el anexo Excel del mismo corte (ver docs/hallazgos_pdf.md)"
    cifras.loc[cifras.unidad_original.astype(str).str.startswith("millones"), "observacion"] = \
        "monto leido de un mapa en millones de soles con 1 decimal (precision de 100 mil soles)"
    checks = validar(cifras, causales, distribuciones, lecturas)
    enla = construir_enla_pdf()
    checks = pd.concat([checks, validar_enla_pdf(enla).assign(fecha_corte="ENLA")], ignore_index=True)

    enteros = ["obras_paralizadas", "obras_g_nacional", "obras_g_regional", "obras_g_local"]
    guardar_csv(a_enteros(cifras, enteros + ["pagina", "tabla_n"]), config.CIFRAS_OFICIALES)
    guardar_csv(a_enteros(causales, ["obras_paralizadas", "pagina", "tabla_n"]), config.CAUSALES_CGR)
    guardar_csv(a_enteros(distribuciones, ["obras_paralizadas", "pagina", "tabla_n"]), config.DISTRIBUCIONES_CGR)
    guardar_csv(a_enteros(educacion, ["obras_educacion", "obras_educacion_estricto"]), config.PROCESSED / "contraloria_educacion_departamento.csv")
    guardar_csv(a_enteros(enla, ["pagina", "tabla_n"]), config.PROCESSED / "enla_pdf.csv")
    cruce = cruzar_infobras_con_contraloria()
    if len(cruce):
        guardar_csv(cruce, config.DOCS / "validacion_infobras.csv")
    guardar_csv(checks, config.DOCS / "validacion_pdf.csv")
    guardar_csv(comparacion, config.DOCS / "validacion_excel.csv")
    log(f"Fase 3: cifras {len(cifras)} filas, causales {len(causales)}, distribuciones {len(distribuciones)}, "
        f"educacion por departamento {len(educacion)}, enla_pdf {len(enla)}; comprobaciones internas {len(checks)} (fallan {(~checks.ok).sum()}); "
        f"comparaciones con Excel {len(comparacion)} (fuera de 10%: {(~comparacion.ok_10pct).sum()})")
    return cifras, causales, distribuciones, checks, comparacion


# ---------------- ENLA por region desde los PDF ----------------
COLUMNAS_ENLA = ["region", "cod_departamento", "anio", "grado", "area", "pct_satisfactorio", "fuente_pdf", "pagina", "tabla_n"]


def construir_enla_pdf():
    """% de estudiantes en nivel satisfactorio por region, leido de las tablas regionales de los PDF de ENLA/EM.

    Solo el reporte nacional de la EM 2022 trae esas tablas; compara 2019 con 2022 (ambos anios se guardan).
    Los demas PDF solo traen tablas de cobertura (instituciones y estudiantes evaluados) y no se usan aqui.
    """
    import extraccion
    filas = []
    for ficha in leer_pdf.leer_inventario().values():
        if ficha["fuente"] != "enla" or not ficha["archivo"].endswith(".pdf"):
            continue
        carpeta = config.INTERIM_PDF / Path(ficha["archivo"]).stem
        for archivo in sorted(carpeta.glob("texto_p*.txt")):
            resultado = extraccion.leer_pagina_regional(archivo.read_text(encoding="utf-8"), ambos_anios=True)
            if not resultado:
                continue
            area, grado, por_anio = resultado
            for anio, valores in por_anio.items():
                for region, valor in valores.items():
                    nombre = normalizar(region)
                    cod = config.DEPARTAMENTOS.get("LIMA" if nombre.startswith("LIMA") else nombre)
                    filas.append({"region": nombre, "cod_departamento": cod, "anio": anio, "grado": grado, "area": area,
                                  "pct_satisfactorio": valor, "fuente_pdf": ficha["archivo"],
                                  "pagina": int(archivo.stem.split("_p")[1]), "tabla_n": 1})   # una tabla por pagina
    tabla = pd.DataFrame(filas, columns=COLUMNAS_ENLA)
    return tabla.sort_values(["anio", "grado", "area", "region"]).reset_index(drop=True)


def validar_enla_pdf(tabla):
    """Comprobaciones de enla_pdf: 26 regiones por anio/grado/area, valores entre 0 y 100, sin nulos y igual a SICRECE en 2022."""
    checks = []
    for (anio, grado, area), grupo in tabla.groupby(["anio", "grado", "area"]):
        checks.append({"comprobacion": f"{anio} {grado} {area}: 26 regiones", "valor_a": len(grupo), "valor_b": 26, "ok": len(grupo) == 26})
        checks.append({"comprobacion": f"{anio} {grado} {area}: valores entre 0 y 100 y sin nulos", "valor_a": grupo.pct_satisfactorio.isna().sum(),
                       "valor_b": 0, "ok": grupo.pct_satisfactorio.between(0, 100).all()})
    ruta = config.PROCESSED / "enla_regiones.csv"
    if ruta.exists():
        sicrece = pd.read_csv(ruta, encoding="utf-8")
        sicrece["region"] = sicrece.region.map(normalizar)
        largo = sicrece.melt(id_vars=["region", "anio", "grado"], value_vars=["lectura_satisfactorio", "matematica_satisfactorio"],
                             var_name="area", value_name="sicrece")
        largo["area"] = largo.area.str.replace("_satisfactorio", "")
        union = tabla.merge(largo, on=["region", "anio", "grado", "area"], how="inner")
        diferencias = (union.pct_satisfactorio - union.sicrece).abs()
        checks.append({"comprobacion": f"PDF vs SICRECE ({len(union)} valores comparables, diferencia maxima en puntos)",
                       "valor_a": round(diferencias.max(), 3) if len(union) else None, "valor_b": 0.0, "ok": len(union) > 0 and diferencias.max() <= 0.15})
    return pd.DataFrame(checks)


# ---------------- B5: rangos de costo y de avance fisico de 2022, leidos por posicion de las palabras ----------------
# En 2022 pdfplumber no detecta las tablas y el texto plano mezcla los grupos de miles con las columnas ('946 408 258 969 194 409 594'
# son tres numeros). Cada columna esta alineada a la derecha, asi que se leen las palabras con su posicion: los grupos de una cifra
# estan separados por menos de 10 puntos y las columnas por mas.
HUECO_MISMA_CIFRA = 10     # puntos PDF: separacion maxima entre dos grupos de la misma cifra
HUECO_ETIQUETA = 15        # separacion minima entre la etiqueta de la fila y su primera cifra
RANGO_COSTO_2022 = {"HASTA 1 MILLON": "HASTA 1 MILLON", "1 - 3 MILLONES": "1 - 3 MILLONES", "3 - 10 MILLONES": "3 - 10 MILLONES",
                    "10 A 100 MILLONES": "10 A 100 MILLONES", "100 A 1000 MILLONES": "100 A 1000 MILLONES",
                    "MAS DE 1000 MILLONES": "DE MAS DE 1000 MILLONES"}   # misma etiqueta que usan los informes de 2023


def _cifra(texto):
    t = texto.replace(",", "").replace("%", "")
    try:
        return float(t) if "." in t else int(t)
    except ValueError:
        return None


ESQUEMAS_RANGOS_2022 = {   # numero de cifras por fila -> sus nombres (junio trae menos porcentajes que setiembre y diciembre)
    "rango_costo": {3: ["obras", "costo", "saldo"], 6: ["obras", "pct_obras", "costo", "pct_costo", "saldo", "pct_saldo"]},
    "rango_avance_fisico": {5: ["obras", "pct_obras", "costo", "saldo", "pct_saldo"],
                            6: ["obras", "pct_obras", "costo", "pct_costo", "saldo", "pct_saldo"]},
}


def filas_por_posicion(ruta_pdf, pagina, patron_titulo, esquemas):
    """Filas de una tabla de 2022 como (etiqueta, {columna: cifra}); parte de la linea del titulo y termina en la fila 'Total' (incluida).

    esquemas = {numero de cifras de la fila: [nombres de columna]}. Las filas con otro numero de cifras no se guardan (se avisa en el log).
    """
    import pdfplumber
    with pdfplumber.open(ruta_pdf) as pdf:
        palabras = pdf.pages[pagina - 1].extract_words()
    lineas = {}
    for w in palabras:
        lineas.setdefault(round(w["top"] / 3), []).append(w)
    ordenadas = [sorted(lineas[k], key=lambda w: w["x0"]) for k in sorted(lineas)]
    inicio = next((i for i, l in enumerate(ordenadas) if re.search(patron_titulo, " ".join(w["text"] for w in l), re.I)), None)
    if inicio is None:
        return []
    filas = []
    for linea in ordenadas[inicio + 1:]:
        if not any(ch.isdigit() for w in linea for ch in w["text"]):
            if linea and linea[0]["text"].upper().startswith("FUENTE"):
                break
            continue
        corte = next((i for i in range(1, len(linea)) if linea[i]["x0"] - linea[i - 1]["x1"] > HUECO_ETIQUETA), None)
        if corte is None:
            continue
        etiqueta = " ".join(w["text"] for w in linea[:corte])
        cifras, actual, previo = [], [], None
        for w in linea[corte:]:
            if previo is not None and w["x0"] - previo["x1"] > HUECO_MISMA_CIFRA:
                cifras.append(actual)
                actual = []
            actual.append(w["text"])
            previo = w
        cifras.append(actual)
        valores = [_cifra("".join(grupo)) for grupo in cifras]
        if len(valores) not in esquemas or None in valores:
            log(f"AVISO B5: {Path(ruta_pdf).name} p.{pagina}: fila '{etiqueta}' con {len(valores)} cifras (se esperaban {sorted(esquemas)}); no se guarda")
            continue
        filas.append((etiqueta, dict(zip(esquemas[len(valores)], valores))))
        if etiqueta.strip().lower().startswith("total"):
            break
    return filas


def rangos_2022(informe):
    """Rangos de costo y de avance fisico de un informe de 2022: {nombre: (DataFrame con etiqueta, obras, costo, saldo y porcentajes, procedencia)}."""
    ruta = config.RAW / "contraloria" / str(informe["anio"]) / informe["archivo"]
    resultado = {}
    for nombre, patron_titulo, tabla_n in (("rango_costo", r"TABLA 6\.", 6), ("rango_avance_fisico", r"TABLA 7\.", 7)):
        pagina, _ = pagina_con(informe, patron_titulo)
        filas = filas_por_posicion(ruta, pagina, patron_titulo, ESQUEMAS_RANGOS_2022[nombre]) if pagina else []
        registros = []
        for etiqueta, v in filas:
            clave = normalizar(etiqueta)
            if nombre == "rango_costo":
                etiqueta = "Total" if es_total(clave) else RANGO_COSTO_2022.get(clave, clave)
            registros.append({"etiqueta": etiqueta, **v})
        resultado[nombre] = (pd.DataFrame(registros), {"fuente_pdf": informe["archivo"], "pagina": pagina, "tabla_n": tabla_n})
    return resultado
