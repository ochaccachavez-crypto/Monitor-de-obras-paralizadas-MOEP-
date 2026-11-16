"""A1: ubigeo de distrito (INEI, 6 digitos, como texto) de cada obra de fichas_infobras.csv.

Como se asigna, en este orden:
  1. exacto: departamento, provincia y distrito iguales a los de escale_infraestructura.csv.
  2. normalizado: iguales despues de quitar tildes y enies, guiones bajos y el nombre alterno entre parentesis
     (ESCALE escribe 'LOS BAÑOS DEL INCA', 'ANCO_HUALLO', 'QUISQUI (KICHKI)'; INFOBRAS 'LOS BANOS DEL INCA', 'ANCO HUALLO', 'QUISQUI')
     y de llevar la provincia del Callao a 'CALLAO'.
  3. manual: obras cuya ubicacion en INFOBRAS es incoherente (departamento o distrito equivocado). Se revisaron a mano con el
     nombre de la obra, la entidad y las coordenadas; cada una con su motivo en CORRECCIONES.
Las obras que no se resuelven quedan con ubigeo vacio. Todas las que no coinciden exacto se listan en docs/nombres_sin_ubigeo.csv
con el metodo usado, para revisarlas.

Ademas corrige la ubicacion: el departamento pasa a ser el del ubigeo (hay 2 obras que INFOBRAS publica en Huancavelica y
son de Ica) y lo que publica INFOBRAS queda en departamento_infobras. Provincia y distrito no se tocan: para el nombre oficial
de la ubicacion usar el ubigeo (por ejemplo con escale_infraestructura).
"""
import re
import unicodedata

import pandas as pd

import config
import utils

SALIDA_REVISION = config.DOCS / "nombres_sin_ubigeo.csv"

# provincia como la escribe INFOBRAS -> como la escribe ESCALE (ya normalizadas)
PROVINCIAS_EQUIVALENTES = {"PROV. CONST. DEL CALLAO": "CALLAO", "P. C. DEL CALLAO": "CALLAO"}

# codigo_infobras -> (ubigeo, motivo). Revisado a mano el 2026-11-08 con las fichas leidas el 2026-10-27.
CORRECCIONES = {
    "543835": ("110401", "INFOBRAS dice HUANCAVELICA-PALPA-PALPA, pero Palpa es provincia de Ica: el nombre de la obra dice "
                         "'DISTRITO DE PALPA ... DEPARTAMENTO DE ICA', la entidad es la Municipalidad Provincial de Palpa y las "
                         "coordenadas caen en Ica"),
    "135083": ("110111", "INFOBRAS dice HUANCAVELICA-HUANCAVELICA-RIO SANTIAGO (Rio Santiago es de Amazonas), pero la obra es "
                         "'DISTRITO DE SANTIAGO - ICA - ICA', la entidad es la Municipalidad Distrital de Santiago-Ica y las "
                         "coordenadas caen en Ica"),
    "510315": ("050401", "INFOBRAS dice distrito CHAVIN DE HUANTAR (es de Ancash); el nombre de la obra dice 'DISTRITO DE HUANTA, "
                         "PROVINCIA HUANTA' y las coordenadas caen en Huanta"),
    "156196": ("050401", "INFOBRAS dice distrito CHAVIN DE HUANTAR (es de Ancash); la obra abarca los distritos de Huanta e Iguain "
                         "(provincia de Huanta). Se asigna Huanta: la mayoria de las I.E. y las coordenadas estan en Huanta"),
}


def normalizar(texto):
    """Mayusculas, sin tildes ni enies, sin guion bajo, sin el nombre alterno entre parentesis y sin espacios dobles."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return None
    t = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().upper()
    t = re.sub(r"\(.*?\)", " ", t.replace("_", " "))
    return re.sub(r"\s+", " ", t).strip()


def maestro_distritos():
    """Una fila por ubigeo con sus nombres en ESCALE (el anio mas reciente) y los nombres normalizados."""
    escale = pd.read_csv(config.PROCESSED / "escale_infraestructura.csv", dtype={"ubigeo": str}, encoding="utf-8")
    maestro = (escale.sort_values("anio").drop_duplicates("ubigeo", keep="last")[["ubigeo", "departamento", "provincia", "distrito"]])
    for col in ("departamento", "provincia", "distrito"):
        maestro[f"{col}_n"] = maestro[col].map(normalizar)
    repetidos = maestro.duplicated(["departamento_n", "provincia_n", "distrito_n"], keep=False)
    if repetidos.any():   # dos ubigeos con el mismo nombre normalizado: no se podria decidir cual
        raise ValueError(f"nombres normalizados repetidos en ESCALE: {maestro[repetidos].ubigeo.tolist()}")
    return maestro


def asignar_ubigeo(fichas, maestro=None):
    """Devuelve una copia de fichas con ubigeo (texto de 6 digitos) y ubigeo_metodo (exacto, normalizado, manual o sin_ubigeo)."""
    maestro = maestro_distritos() if maestro is None else maestro
    fichas = fichas.drop(columns=[c for c in ("ubigeo", "ubigeo_metodo") if c in fichas], errors="ignore").copy()
    if "departamento_infobras" in fichas:   # volver a lo que publica INFOBRAS antes de emparejar (asi repetir la corrida da lo mismo)
        fichas["departamento"] = fichas["departamento_infobras"]
        fichas = fichas.drop(columns="departamento_infobras")
    fichas["codigo_infobras"] = fichas["codigo_infobras"].astype(str)
    claves = ["departamento", "provincia", "distrito"]

    exacto = fichas[["codigo_infobras"] + claves].merge(maestro[["ubigeo"] + claves], on=claves, how="left")
    ubigeo = dict(zip(exacto.codigo_infobras, exacto.ubigeo))
    metodo = {c: "exacto" for c, u in ubigeo.items() if isinstance(u, str)}

    norm = fichas[["codigo_infobras"] + claves].copy()
    for col in claves:
        norm[f"{col}_n"] = norm[col].map(normalizar)
    norm["provincia_n"] = norm.provincia_n.replace(PROVINCIAS_EQUIVALENTES)
    norm = norm.merge(maestro[["ubigeo", "departamento_n", "provincia_n", "distrito_n"]],
                      on=["departamento_n", "provincia_n", "distrito_n"], how="left")
    for c, u in zip(norm.codigo_infobras, norm.ubigeo):
        if c not in metodo and isinstance(u, str):
            ubigeo[c], metodo[c] = u, "normalizado"

    validos = set(maestro.ubigeo)
    for c, (u, _) in CORRECCIONES.items():
        if u not in validos:
            raise ValueError(f"correccion manual de {c}: el ubigeo {u} no existe en ESCALE")
        if c in ubigeo and c not in metodo:
            ubigeo[c], metodo[c] = u, "manual"

    fichas["ubigeo"] = fichas.codigo_infobras.map(lambda c: ubigeo.get(c) if c in metodo else None)
    fichas["ubigeo_metodo"] = fichas.codigo_infobras.map(lambda c: metodo.get(c, "sin_ubigeo"))
    # columnas nuevas justo despues de distrito
    orden = list(fichas.columns.drop(["ubigeo", "ubigeo_metodo"]))
    pos = orden.index("distrito") + 1 if "distrito" in orden else len(orden)
    return corregir_departamento(fichas[orden[:pos] + ["ubigeo", "ubigeo_metodo"] + orden[pos:]])


def corregir_departamento(fichas):
    """departamento y cod_departamento = los del ubigeo; el departamento que publica INFOBRAS queda en departamento_infobras."""
    por_codigo = {codigo: nombre for nombre, codigo in config.DEPARTAMENTOS.items()}
    fichas = fichas.copy()
    fichas["departamento_infobras"] = fichas["departamento"]
    del_ubigeo = fichas["ubigeo"].str[:2].map(por_codigo)
    fichas["departamento"] = del_ubigeo.fillna(fichas["departamento_infobras"])
    fichas["cod_departamento"] = fichas["departamento"].map(config.DEPARTAMENTOS)
    # departamento_infobras va justo despues de ubigeo_metodo
    orden = [c for c in fichas.columns if c != "departamento_infobras"]
    pos = orden.index("ubigeo_metodo") + 1
    return fichas[orden[:pos] + ["departamento_infobras"] + orden[pos:]]


def tabla_revision(fichas, maestro):
    """Obras que no coincidieron exacto: como se resolvieron y con que nombres de ESCALE."""
    revisar = fichas[fichas.ubigeo_metodo != "exacto"][["codigo_infobras", "departamento_infobras", "provincia", "distrito", "ubigeo", "ubigeo_metodo"]]
    revisar = revisar.rename(columns={"departamento_infobras": "departamento"})
    nombres = maestro.set_index("ubigeo")[["departamento", "provincia", "distrito"]].add_suffix("_escale")
    revisar = revisar.join(nombres, on="ubigeo")
    motivo = {"normalizado": "difiere solo en tildes, enie, guion bajo, nombre alterno entre parentesis o provincia del Callao",
              "sin_ubigeo": "no se encontro el distrito: revisar a mano"}
    revisar["motivo"] = [CORRECCIONES[c][1] if m == "manual" else motivo[m] for c, m in zip(revisar.codigo_infobras, revisar.ubigeo_metodo)]
    return revisar.sort_values(["ubigeo_metodo", "codigo_infobras"])


def agregar_ubigeo(fichas):
    """Asigna el ubigeo a la tabla de fichas, escribe docs/nombres_sin_ubigeo.csv y devuelve la tabla con las columnas nuevas."""
    maestro = maestro_distritos()
    fichas = asignar_ubigeo(fichas, maestro)
    tabla_revision(fichas, maestro).to_csv(SALIDA_REVISION, index=False, encoding="utf-8-sig")
    conteo = fichas.ubigeo_metodo.value_counts().to_dict()
    utils.log(f"UBIGEO: {fichas.ubigeo.notna().sum()} de {len(fichas)} obras con ubigeo {conteo}; revision en {SALIDA_REVISION.name}")
    if (fichas.ubigeo_metodo == "sin_ubigeo").any():
        utils.log(f"AVISO UBIGEO: obras sin ubigeo: {fichas.loc[fichas.ubigeo_metodo == 'sin_ubigeo', 'codigo_infobras'].tolist()}")
    return fichas
