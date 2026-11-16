"""Auditoria de calidad del CSV unico del dashboard (data/final/dashboard_obras.csv).

Revisa: estructura (columnas = diccionario, sin filas repetidas), texto (espacios, caracteres raros, nulos disfrazados, nombres de lugares en
MAYUSCULAS sin tildes), codigos (departamento de 2 digitos, ubigeo de 6), rangos (sin negativos, porcentajes de 0 a 100, coordenadas dentro del Peru),
fechas (formato, coherencia), consistencia entre campos y entre tipos de registro, campos obligatorios por tipo y posibles nombres de personas.
Resultado: docs/auditoria_calidad.csv con nivel «ERROR» (el proceso se detiene) o «aviso» (dato dudoso que viene de la fuente y ya esta marcado
en la columna alertas_calidad).
"""
import re
import unicodedata

import numpy as np
import pandas as pd

import config
import utils

MARCAS_NULAS = ["nan", "none", "null", "n/a", "na", "-", "--", "s/d", "#n/a"]
OBLIGATORIOS = {
    "obra_infobras": ["codigo_infobras", "cui", "nombre_obra", "entidad", "cod_departamento", "departamento", "provincia", "distrito", "ubigeo", "region_enla",
                      "estado_infobras", "paralizada_hoy", "fecha_corte", "n_obras", "causa_grupo_final", "causa_macro", "avance_fisico_pct", "escale_locales_publicos"],
    "obra_corte_contraloria": ["codigo_infobras", "fecha_corte", "departamento", "region_enla", "causal_oficial", "causa_grupo_final", "nivel_gobierno"],
    "departamento_corte": ["fecha_corte", "cod_departamento", "departamento", "n_obras", "costo_actualizado_soles"],
    "pais_total_corte": ["fecha_corte", "n_obras", "costo_actualizado_soles", "saldo_inversion_soles"],
    "pais_educacion_corte": ["fecha_corte", "n_obras", "costo_actualizado_soles", "pct_obras"],
    "causal_corte": ["fecha_corte", "causal_oficial", "causa_grupo_final", "causa_macro", "n_obras", "costo_actualizado_soles"],
}
PATRON_NOMBRE = re.compile(r"\b(ing|arq|abog|econ|lic|sr|sra|srta|cpc|dr|dra)\.?\s+[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}\s+[A-Za-zÁÉÍÓÚÑáéíóúñ]{3,}", re.I)


def auditar(escribir=True):
    """Devuelve un DataFrame con los hallazgos (nivel, tema, detalle); lo guarda en docs/auditoria_calidad.csv."""
    d = pd.read_csv(config.FINAL / "dashboard_obras.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    dic = pd.read_csv(config.FINAL / "dashboard_obras_diccionario.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    num = lambda s: pd.to_numeric(s, errors="coerce")
    hall = []
    nota = lambda nivel, tema, detalle: hall.append((nivel, tema, detalle))
    tipo = lambda t: d[d.tipo_registro == t]

    # 1) estructura
    if list(d.columns) != list(dic.columna):
        nota("ERROR", "estructura", "las columnas del CSV no coinciden con el diccionario")
    if d.duplicated().any():
        nota("ERROR", "estructura", f"{int(d.duplicated().sum())} filas repetidas")
    for c in d.columns:
        if (d[c] == "").all():
            nota("ERROR", "columna vacia", c)

    # 2) texto
    for c in d.columns:
        v = d[c][d[c] != ""]
        if v.str.contains(r"^\s|\s$").any():
            nota("ERROR", "espacios", f"{c}: valores con espacios al inicio o al final")
        if v.str.contains(r"[\x00-\x08\x0b\x0c\x0e-\x1f�]").any():
            nota("ERROR", "caracteres de control", c)
        if v.str.contains("Ã.|â€").any():
            nota("ERROR", "mojibake", c)
        if v.str.lower().isin(MARCAS_NULAS).any():
            nota("ERROR", "nulo disfrazado", c)
    for c in ("departamento", "provincia", "distrito", "region_enla"):
        v = d[c][d[c] != ""].drop_duplicates()
        mal = v[v.map(lambda x: x != x.upper() or any(unicodedata.combining(ch) for ch in unicodedata.normalize("NFD", x)))]
        if len(mal):
            nota("ERROR", "nombres de lugares", f"{c}: {mal.head(5).tolist()}")

    # 3) codigos
    cod = d[d.cod_departamento != ""]
    if (~cod.cod_departamento.str.fullmatch(r"\d{2}")).any():
        nota("ERROR", "cod_departamento", "no tiene 2 digitos")
    ub = d[d.ubigeo != ""]
    if (~ub.ubigeo.str.fullmatch(r"\d{6}")).any() or (ub.ubigeo.str[:2] != ub.cod_departamento).any():
        nota("ERROR", "ubigeo", "no tiene 6 digitos o su inicio no es el cod_departamento")
    mapa = d[(d.cod_departamento != "") & (d.departamento != "")][["cod_departamento", "departamento"]].drop_duplicates()
    if mapa.cod_departamento.duplicated().any() or mapa.departamento.duplicated().any():
        nota("ERROR", "cod_departamento", "un codigo con varios nombres o al reves")
    reg = d[(d.cod_departamento != "") & (d.region_enla != "")][["cod_departamento", "region_enla"]].drop_duplicates().groupby("cod_departamento").size()
    if (reg[reg > 1].index != "15").any():
        nota("ERROR", "region_enla", "un departamento (que no es Lima) cae en mas de una region")

    # 4) rangos
    for c in d.columns:
        if d[c].str.fullmatch(r"-?\d+(\.\d+)?").sum() > 0 and c not in ("latitud", "longitud", "latitud_mapa", "longitud_mapa") and not c.startswith(("cod_", "ubigeo", "codigo_", "cui", "escale_codlocal")):
            x = num(d[c]).dropna()
            if (x < 0).any():
                nota("ERROR", "negativos", c)
            if ("pct" in c or c.endswith("satisfactorio")) and c != "pct_devengado_del_costo" and ((x < 0) | (x > 100)).any():
                nota("ERROR", "porcentaje fuera de 0-100", c)
    ob, oc = tipo("obra_infobras"), tipo("obra_corte_contraloria")
    lat, lon = num(ob.latitud).dropna(), num(ob.longitud).dropna()
    if ((lat > 0.1) | (lat < -18.6)).any() or ((lon > -68.4) | (lon < -81.4)).any():
        nota("ERROR", "coordenadas", "fuera del Peru")
    if ((ob.latitud == "") != (ob.longitud == "")).any():
        nota("ERROR", "coordenadas", "obras con solo latitud o solo longitud")
    lat_m, lon_m = num(ob.latitud_mapa).dropna(), num(ob.longitud_mapa).dropna()   # coordenadas para el mapa (INFOBRAS o aproximadas de ESCALE)
    if ((lat_m > 0.1) | (lat_m < -18.6)).any() or ((lon_m > -68.4) | (lon_m < -81.4)).any():
        nota("ERROR", "coordenadas", "latitud_mapa/longitud_mapa fuera del Peru")
    if ((ob.latitud_mapa == "") != (ob.longitud_mapa == "")).any():
        nota("ERROR", "coordenadas", "obras con solo latitud_mapa o solo longitud_mapa")

    # 5) fechas
    for c in ("fecha_corte", "fecha_inicio", "fecha_fin_prevista", "fecha_paralizacion"):
        v = d[c][d[c] != ""]
        f = pd.to_datetime(v, errors="coerce", format="%Y-%m-%d")
        if f.isna().any():
            nota("ERROR", "fechas", f"{c}: valores que no son AAAA-MM-DD")
        elif (f.dt.year < 1990).any() or (f.dt.year > 2030).any():
            nota("ERROR", "fechas", f"{c}: fuera de 1990-2030")
    con_f = d[d.fecha_corte != ""]
    if (con_f.anio != con_f.fecha_corte.str[:4]).any():
        nota("ERROR", "anio", "distinto del ano de fecha_corte")
    fi, ff = pd.to_datetime(ob.fecha_inicio.replace("", np.nan)), pd.to_datetime(ob.fecha_fin_prevista.replace("", np.nan))
    if (ff < fi).any():
        nota("aviso", "fechas de obra", f"{int((ff < fi).sum())} obras con fecha_fin_prevista anterior al inicio")

    # 6) consistencia
    if ((ob.estado_infobras.str.upper() == "PARALIZADA") != (ob.paralizada_hoy == "True")).any():
        nota("ERROR", "estado", "paralizada_hoy no coincide con estado_infobras")
    if (num(ob.n_obras_paralizadas) != (ob.paralizada_hoy == "True").astype(int)).any():
        nota("ERROR", "n_obras_paralizadas", "no coincide con paralizada_hoy")
    if (ob.causa_grupo_final == "").any() or (ob.causa_macro == "").any():
        nota("ERROR", "causa", "obras sin causa")
    tot, edu = tipo("pais_total_corte").set_index("fecha_corte"), tipo("pais_educacion_corte").set_index("fecha_corte")
    if (num(edu.n_obras) > num(tot.n_obras).reindex(edu.index)).any():
        nota("ERROR", "pais", "Educacion mayor que el total del pais")
    suma = tipo("causal_corte").groupby("fecha_corte").n_obras.apply(lambda s: num(s).sum())
    dif = (suma - num(tot.n_obras).reindex(suma.index)).abs()
    for corte in dif[dif > 0].index:
        nota("aviso", "causales vs total", f"{corte}: la suma de causales difiere del total del pais en {int(dif[corte])} obras (error del propio informe)")
    if tipo("departamento_corte").duplicated(["fecha_corte", "cod_departamento"]).any() or oc.duplicated(["fecha_corte", "codigo_infobras"]).any() or ob.duplicated("codigo_infobras").any():
        nota("ERROR", "llaves", "obra o departamento repetido dentro de un corte")
    por_corte = oc.groupby("fecha_corte").size()
    por_dep = tipo("departamento_corte").groupby("fecha_corte").n_obras.apply(lambda s: num(s).sum())
    for corte in por_corte.index:
        if abs(int(por_corte[corte]) - int(por_dep.get(corte, -999))) > 2:
            nota("ERROR", "obras por corte", f"{corte}: {por_corte[corte]} obras por obra vs {por_dep.get(corte)} en la serie por departamento")
    # avisos que vienen de la fuente (ya marcados en alertas_calidad)
    if (num(oc.costo_actualizado_soles) <= 0).any() or oc.costo_actualizado_soles.eq("").any():
        nota("aviso", "costos", f"{int((~(num(oc.costo_actualizado_soles) > 0)).sum())} filas de la Contraloria con costo 0 o vacio en la fuente")
    if (num(oc.saldo_inversion_soles) > num(oc.costo_actualizado_soles) * 1.0001).any():
        nota("aviso", "saldo > costo", f"{int((num(oc.saldo_inversion_soles) > num(oc.costo_actualizado_soles) * 1.0001).sum())} filas de la Contraloria")
    sin_alerta = int((ob.alertas_calidad == "").sum())
    nota("aviso", "alertas_calidad", f"{len(ob) - sin_alerta} de {len(ob)} obras de INFOBRAS tienen al menos una alerta (ver columna alertas_calidad)")

    # 7) obligatorios
    for t, cols in OBLIGATORIOS.items():
        g = tipo(t)
        for c in cols:
            n = int((g[c] == "").sum())
            if n:
                nota("aviso", "obligatorio vacio", f"{t}.{c}: {n} de {len(g)}")
    ctx = tipo("contexto_region")
    if (ctx[["region_enla", "cod_departamento"] + [c for c in d.columns if c.startswith("region_")]] == "").any().any():
        nota("ERROR", "contexto_region", "campos vacios en las 26 regiones")

    # 8) posibles nombres de personas
    for c in ("nombre_obra", "entidad", "mef_ult_problema", "causal_oficial"):
        marca = d[c].map(lambda t: bool(PATRON_NOMBRE.search(t)) and "[NOMBRE OMITIDO]" not in t)
        if marca.any():
            nota("ERROR", "posible nombre de persona", f"{c}: {int(marca.sum())} textos")

    h = pd.DataFrame(hall, columns=["nivel", "tema", "detalle"])
    if escribir:
        h.to_csv(config.DOCS / "auditoria_calidad.csv", index=False, encoding="utf-8-sig")
    utils.log(f"AUDITORIA DE CALIDAD: {len(d)} filas x {d.shape[1]} columnas; {int((h.nivel == 'ERROR').sum())} errores, {int((h.nivel == 'aviso').sum())} avisos (docs/auditoria_calidad.csv)")
    return h


def auditoria_o_falla():
    """Falla (para que el pipeline lo avise) si hay algun hallazgo de nivel ERROR."""
    h = auditar()
    errores = h[h.nivel == "ERROR"]
    if len(errores):
        raise ValueError(f"{len(errores)} errores en el CSV unico: {errores[['tema', 'detalle']].head(5).values.tolist()}")
    return h
