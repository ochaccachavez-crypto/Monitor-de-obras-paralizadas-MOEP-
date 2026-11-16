"""ESCALE ampliado (Censo Educativo 2025): mas indicadores de infraestructura por distrito, solo locales publicos.

Los indicadores de escale_infraestructura.csv (servicios basicos, ruralidad, riesgo y estado de la estructura) existen para 2022-2025.
Estos son adicionales y se calculan solo para 2025, porque los nombres de las variables cambian cada anio:
  Del cuestionario del local (loc_lineal_1): internet, modulo de conectividad, agua y luz todos los dias, centro poblado con internet, area del terreno.
  De las edificaciones en uso (Loc_P53_Edific): pisos, antiguedad, red interna de agua y luz, rampa de acceso, estado del techo, la cobertura y el tablero electrico.
Salida: data/processed/escale_distrito_ampliado.csv (una fila por distrito).
"""
import numpy as np
import pandas as pd

import config
import extraccion
import utils

ANIO = 2025
SI, NO = config.ESCALE_SI, config.ESCALE_NO
COLUMNAS_LINEAL = ["CODLOCAL", "CODGEO", "P3230", "P3236", "P327", "P3224", "P311_5", "P232"]
COLUMNAS_EDIF = ["CODLOCAL", "P53_3", "P53_6", "P53_8_1", "P53_13_1", "P53_13_3", "P53_14_21", "P53_11_42", "P53_12_12", "P53_18_22"]

DICCIONARIO = [
    ("anio", "entero", "Año del Censo Educativo (2025).", "año"),
    ("ubigeo", "texto de 6 dígitos", "Código de ubigeo del distrito.", "código"),
    ("n_locales_publicos_ampliado", "entero", "Locales públicos del distrito en el Censo 2025 usados para estos indicadores.", "locales"),
    ("pct_internet", "decimal", "% de locales públicos con servicio de internet (de los que respondieron sí o no).", "%"),
    ("pct_modulo_conectividad", "decimal", "% de locales públicos con módulo de conectividad.", "%"),
    ("pct_agua_todos_los_dias", "decimal", "% de locales con agua potable todos los días de la semana (de los que respondieron la pregunta, que solo se hace si hay servicio).", "%"),
    ("pct_energia_todos_los_dias", "decimal", "% de locales con energía eléctrica todos los días de la semana.", "%"),
    ("pct_centro_poblado_internet", "decimal", "% de locales cuyo centro poblado cuenta con internet.", "%"),
    ("area_terreno_mediana_m2", "decimal", "Mediana del área del terreno del local (m²), sin contar los que declaran 0.", "m²"),
    ("n_edificaciones_en_uso", "entero", "Edificaciones en uso de los locales públicos del distrito.", "edificaciones"),
    ("pisos_promedio", "decimal", "Promedio de pisos de las edificaciones en uso.", "pisos"),
    ("antiguedad_mediana_anios", "decimal", "Mediana de años desde el término de la construcción (2025 − año de término; solo años entre 1900 y 2025).", "años"),
    ("pct_edif_red_interna_agua", "decimal", "% de edificaciones con red interna de agua.", "%"),
    ("pct_edif_red_interna_energia", "decimal", "% de edificaciones con red interna de energía eléctrica.", "%"),
    ("pct_edif_rampa_primer_piso", "decimal", "% de edificaciones con rampa de acceso al primer piso (de las que respondieron).", "%"),
    ("pct_edif_techo_mal_estado", "decimal", "% de edificaciones con la estructura de techos en mal estado (de las que informan su estado).", "%"),
    ("pct_edif_cobertura_mal_estado", "decimal", "% de edificaciones con la cobertura de techos en mal estado.", "%"),
    ("pct_edif_tablero_mal_estado", "decimal", "% de edificaciones con el tablero eléctrico en mal estado.", "%"),
]
INDICADORES = [c for c, *_ in DICCIONARIO if c not in ("anio", "ubigeo")]


def _pct_si(serie, validos_si=SI, validos_no=NO):
    """% de 'si' entre los que respondieron si o no (los vacios y '-' no cuentan). Devuelve (porcentaje, respondieron)."""
    respondio = serie.isin(validos_si + validos_no)
    return serie[respondio].isin(validos_si).sum(), respondio.sum()


def _pct_por_distrito(df, columna, validos_si, validos_no):
    """Serie distrito -> % de filas con 'si' entre las que respondieron."""
    marca = df[columna].isin(validos_si + validos_no)
    si = df[columna].isin(validos_si) & marca
    g = pd.DataFrame({"ubigeo": df.ubigeo, "si": si, "resp": marca}).groupby("ubigeo").sum()
    return (100 * g.si / g.resp.replace(0, np.nan)).round(2)


def construir():
    """Calcula y guarda escale_distrito_ampliado.csv; devuelve la tabla."""
    try:
        publicos = extraccion.cargar_locales_padron(ANIO)
    except FileNotFoundError:
        utils.log("ESCALE AMPLIADO: no hay datos crudos de ESCALE; se usa escale_distrito_ampliado.csv ya calculado")
        return pd.read_csv(config.PROCESSED / "escale_distrito_ampliado.csv", dtype={"ubigeo": str}, encoding="utf-8-sig")
    publicos = publicos[publicos.publico].index
    lineal = utils.leer_dbf(extraccion.dbf_de_zip("escale", ANIO, config.ESCALE_ZIP_LINEAL), columnas=COLUMNAS_LINEAL)
    lineal = lineal.drop_duplicates("CODLOCAL")
    lineal = lineal[lineal.CODLOCAL.isin(publicos) & (lineal.CODGEO != "")].rename(columns={"CODGEO": "ubigeo"})
    edif = utils.leer_dbf(extraccion.dbf_de_zip("escale", ANIO, config.ESCALE_ZIP_EDIFICACIONES), columnas=COLUMNAS_EDIF)
    edif = edif[edif.P53_3.isin(SI) & edif.CODLOCAL.isin(publicos)]
    edif = edif.merge(lineal[["CODLOCAL", "ubigeo"]], on="CODLOCAL", how="inner")   # el distrito de cada edificacion es el de su local

    salida = pd.DataFrame(index=sorted(lineal.ubigeo.unique()))
    salida["n_locales_publicos_ampliado"] = lineal.groupby("ubigeo").size()
    salida["pct_internet"] = _pct_por_distrito(lineal, "P3230", ["1"], ["2"])
    salida["pct_modulo_conectividad"] = _pct_por_distrito(lineal, "P3236", ["1"], ["2"])
    salida["pct_agua_todos_los_dias"] = _pct_por_distrito(lineal, "P327", ["1"], ["2"])
    salida["pct_energia_todos_los_dias"] = _pct_por_distrito(lineal, "P3224", ["1"], ["2"])
    salida["pct_centro_poblado_internet"] = _pct_por_distrito(lineal, "P311_5", ["1"], ["2"])
    area = pd.to_numeric(lineal.P232.str.replace(",", "."), errors="coerce")
    salida["area_terreno_mediana_m2"] = area[area > 0].groupby(lineal.ubigeo).median().round(1)

    salida["n_edificaciones_en_uso"] = edif.groupby("ubigeo").size()
    pisos = pd.to_numeric(edif.P53_6, errors="coerce")
    salida["pisos_promedio"] = pisos[pisos.between(1, 20)].groupby(edif.ubigeo).mean().round(2)
    termino = pd.to_numeric(edif.P53_8_1, errors="coerce")
    antig = (ANIO - termino)[termino.between(1900, ANIO)]
    salida["antiguedad_mediana_anios"] = antig.groupby(edif.ubigeo).median().round(1)
    salida["pct_edif_red_interna_agua"] = _pct_por_distrito(edif, "P53_13_1", ["1"], ["2"])
    salida["pct_edif_red_interna_energia"] = _pct_por_distrito(edif, "P53_13_3", ["1"], ["2"])
    salida["pct_edif_rampa_primer_piso"] = _pct_por_distrito(edif, "P53_14_21", ["1"], ["2"])
    for destino, columna in (("pct_edif_techo_mal_estado", "P53_11_42"), ("pct_edif_cobertura_mal_estado", "P53_12_12"), ("pct_edif_tablero_mal_estado", "P53_18_22")):
        salida[destino] = _pct_por_distrito(edif, columna, ["MA"], ["BU", "RE"])
    salida.insert(0, "anio", ANIO)
    salida.index.name = "ubigeo"
    salida = salida.reset_index()
    salida.to_csv(config.PROCESSED / "escale_distrito_ampliado.csv", index=False, encoding="utf-8-sig", na_rep="")
    utils.log(f"ESCALE AMPLIADO {ANIO}: {len(salida)} distritos, {len(lineal)} locales publicos, {len(edif)} edificaciones en uso; escale_distrito_ampliado.csv")
    return salida
