"""C2: locales educativos que declaran estar en construccion/reconstruccion (ESCALE 2025), con el CUI de la obra.

ESCALE le pregunta a cada local si se encuentra en construccion (P211), desde y hasta cuando (P212_FI, P212_FC; no se usan: vienen cortadas) y el CUI de la obra
(P212_CUI). Solo el Censo Educativo 2025 trae el CUI. Sirve para vincular una obra con su local exacto (CODLOCAL) y su distrito.
Salida: data/processed/escale_obras_en_local.csv (una fila por local que declara estar en construccion).
"""
import glob

import pandas as pd

import config
import utils

COLUMNAS = {"CODLOCAL": "codlocal", "CODGEO": "ubigeo", "DPTO": "departamento", "PROV": "provincia", "DISTRITO": "distrito",
            "P211_SI": "tipo_construccion", "P212_CUI": "cui"}
# Las fechas de la obra (P212_FI y P212_FC) vienen cortadas en el propio archivo del Censo ('25-08-2'): no se usan.


def sin_tildes_conservando_enie(texto):
    """'Junín' -> 'JUNIN'; la Ñ se conserva (CAÑETE) porque es una letra del alfabeto, no una tilde."""
    import unicodedata
    texto = unicodedata.normalize("NFD", str(texto).upper())
    salida = []
    for i, ch in enumerate(texto):
        if unicodedata.combining(ch) and not (ch == "\u0303" and i > 0 and texto[i - 1] == "N"):
            continue
        salida.append(ch)
    return unicodedata.normalize("NFC", "".join(salida)).strip()


def construir(anio=2025):
    """Genera escale_obras_en_local.csv a partir del archivo de local (Loc_Lineal_1) del censo indicado."""
    rutas = sorted(glob.glob(str(config.INTERIM / "escale" / str(anio) / "*lineal*" / "*.dbf")))
    if not rutas:
        utils.log(f"ESCALE OBRAS: no hay archivo de local de {anio} en data/interim/escale; se omite")
        return None
    locales = utils.leer_dbf(rutas[0])
    if "P212_CUI" not in locales:
        utils.log(f"ESCALE OBRAS: el censo {anio} no trae P212_CUI; se omite")
        return None
    en_obra = locales[locales["P211"].astype(str).str.strip() == "1"].copy()   # 1 = si, el local esta en construccion/reconstruccion
    tabla = en_obra[list(COLUMNAS)].rename(columns=COLUMNAS)
    for c in tabla.columns:
        tabla[c] = tabla[c].astype(str).str.strip()
    tabla["cui"] = tabla.cui.str.replace(r"\.0$", "", regex=True)
    tabla["tipo_construccion"] = tabla.tipo_construccion.map({"1": "TOTAL", "2": "PARCIAL"}).fillna("")
    for c in ("departamento", "provincia", "distrito"):
        tabla[c] = tabla[c].map(sin_tildes_conservando_enie)
    tabla.insert(0, "anio", anio)
    tabla = tabla.sort_values(["ubigeo", "codlocal"]).reset_index(drop=True)
    tabla.to_csv(config.PROCESSED / "escale_obras_en_local.csv", index=False, encoding="utf-8-sig")
    con_cui = int((tabla.cui != "").sum())
    utils.log(f"ESCALE OBRAS: {len(tabla)} locales en construccion en {anio}, {con_cui} con CUI de la obra ({tabla.loc[tabla.cui != '', 'cui'].nunique()} CUI distintos)")
    return tabla
