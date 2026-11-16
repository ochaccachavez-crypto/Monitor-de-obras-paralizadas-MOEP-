"""Exporta cada tabla final a Excel (.xlsx) con una hoja de datos y una hoja de diccionario."""
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import config
import diccionario
import utils

COLUMNAS_LARGAS = {"descripcion": 70, "notas": 70, "fuente": 45}   # ancho de las columnas de texto largo del diccionario


def dar_formato(hoja, tabla, anchos=None):
    """Encabezado en negrita y con color, primera fila fija, filtros y ancho de columna razonable."""
    anchos = anchos or {}
    for celda in hoja[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor="1F4E78")
        celda.alignment = Alignment(vertical="center", wrap_text=True)
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = hoja.dimensions
    for i, columna in enumerate(tabla.columns, start=1):
        ancho = anchos.get(columna) or min(max(len(str(columna)), int(tabla[columna].astype(str).str.len().max())) + 2, 32)
        hoja.column_dimensions[get_column_letter(i)].width = ancho
        if columna in anchos:
            for fila in hoja.iter_rows(min_row=2, min_col=i, max_col=i):
                fila[0].alignment = Alignment(wrap_text=True, vertical="top")


def escribir_excel():
    """Genera data/processed/<tabla>.xlsx: hoja «datos» (números como números, ubigeo como texto) y hoja «diccionario»."""
    dic = diccionario.construir_diccionario()
    for tabla in diccionario.TABLAS:
        ruta_csv = config.PROCESSED / f"{tabla}.csv"
        if not ruta_csv.exists():
            continue
        datos = pd.read_csv(ruta_csv, dtype={"ubigeo": str})
        hoja_dic = dic[dic.tabla == tabla].drop(columns="tabla")
        ruta = config.PROCESSED / f"{tabla}.xlsx"
        with pd.ExcelWriter(ruta, engine="openpyxl") as escritor:
            datos.to_excel(escritor, sheet_name="datos", index=False)
            hoja_dic.to_excel(escritor, sheet_name="diccionario", index=False)
            dar_formato(escritor.sheets["datos"], datos)
            dar_formato(escritor.sheets["diccionario"], hoja_dic, COLUMNAS_LARGAS)
        utils.log(f"EXCEL: escrito {ruta.name} ({len(datos)} filas, {len(hoja_dic)} columnas en el diccionario)")
