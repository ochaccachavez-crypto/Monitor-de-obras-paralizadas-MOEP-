"""Anexo 03 de la Contraloria: servicios de control (control simultaneo, previo y posterior) que se hicieron a cada obra paralizada.

El anexo trae una fila por servicio de control y obra. Se usa el anexo mas reciente (marzo de 2026; el de junio de 2026 no publica anexo 03)
y se cuenta por obra. Salida: data/processed/contraloria_servicios_control_obra.csv (una fila por codigo de INFOBRAS).
No se guardan titulos ni direcciones de los informes: solo conteos y el ultimo anio de emision.
"""
import re

import pandas as pd

import config
import utils

MESES = {m: i for i, m in enumerate("enero febrero marzo abril mayo junio julio agosto setiembre octubre noviembre diciembre".split(), 1)}

DICCIONARIO = [
    ("codigo_infobras", "texto", "Código de la obra en INFOBRAS.", "código"),
    ("corte_anexo03", "fecha AAAA-MM-DD", "Corte del anexo 03 de donde salen los conteos (el más reciente publicado).", "fecha"),
    ("n_servicios_control", "entero", "Servicios de control que la Contraloría registra para la obra (todos los tipos).", "servicios"),
    ("n_control_simultaneo", "entero", "Servicios de control simultáneo (concurrente, visitas, orientación de oficio).", "servicios"),
    ("n_control_previo", "entero", "Servicios de control previo.", "servicios"),
    ("n_control_posterior", "entero", "Servicios de control posterior (auditorías).", "servicios"),
    ("n_servicios_concluidos", "entero", "Servicios de control con estado «Concluida».", "servicios"),
    ("ultimo_anio_informe_control", "entero", "Año de emisión del informe más reciente.", "año"),
]


def _archivo_mas_reciente():
    candidatos = []
    for ruta in config.RAW.glob("contraloria/*/*anexo_03*.xlsx"):
        m = re.search(r"obras_paralizadas_([a-z]+)_(\d{4})_", ruta.name)
        if m and m.group(1) in MESES:
            candidatos.append(((int(m.group(2)), MESES[m.group(1)]), ruta))
    return max(candidatos) if candidatos else (None, None)


def construir():
    """Cuenta los servicios de control por obra y guarda contraloria_servicios_control_obra.csv; devuelve la tabla."""
    clave, ruta = _archivo_mas_reciente()
    if ruta is None:
        utils.log("ANEXO 03: no hay archivos de anexo 03 en data/raw/contraloria; se omite")
        return None
    anio, mes = clave
    t = pd.read_excel(ruta, dtype=str).rename(columns=lambda c: re.sub(r"\s+", "_", str(c).strip().upper().replace("Ñ", "N")))
    columna = lambda *opciones: next(c for c in opciones if c in t.columns)
    codigo, tipo = columna("CODIGO_INFOBRAS"), columna("TIPO_CONTROL")
    estado, emision = columna("ESTADO_SERVICIO_DE_CONTROL"), columna("ANO_EMISION_DE_INFORME")
    t = t[t[codigo].fillna("").str.fullmatch(r"\d+")].copy()
    tipo_norm = t[tipo].fillna("").str.lower()
    t["simultaneo"] = tipo_norm.str.contains("simult")
    t["previo"] = tipo_norm.str.contains("previo")
    t["posterior"] = tipo_norm.str.contains("posterior")
    t["concluido"] = t[estado].fillna("").str.lower().str.startswith("concluid")
    t["anio_informe"] = pd.to_numeric(t[emision], errors="coerce")
    g = t.groupby(codigo)
    salida = pd.DataFrame({"corte_anexo03": pd.Timestamp(anio, mes, 1).to_period("M").to_timestamp("M").strftime("%Y-%m-%d"),
                           "n_servicios_control": g.size(), "n_control_simultaneo": g.simultaneo.sum(), "n_control_previo": g.previo.sum(),
                           "n_control_posterior": g.posterior.sum(), "n_servicios_concluidos": g.concluido.sum(),
                           "ultimo_anio_informe_control": g.anio_informe.max().astype("Int64")}).reset_index().rename(columns={codigo: "codigo_infobras"})
    for c in ("n_control_simultaneo", "n_control_previo", "n_control_posterior", "n_servicios_concluidos"):
        salida[c] = salida[c].astype(int)
    salida.to_csv(config.PROCESSED / "contraloria_servicios_control_obra.csv", index=False, encoding="utf-8-sig")
    utils.log(f"ANEXO 03 ({anio}-{mes:02d}): {len(t)} servicios de control en {len(salida)} obras; contraloria_servicios_control_obra.csv")
    return salida
