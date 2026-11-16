"""Proyecto PDF: inventario, extraccion de tablas y texto de los PDF descargados.

Uso (desde la carpeta del proyecto):  .venv/Scripts/python.exe src/main_pdf.py [--forzar] [--hasta N]
Un documento ya procesado no se vuelve a procesar salvo con --forzar.
"""
import argparse
import sys

import contraloria_excel
import leer_pdf
import diccionario
import tablas_finales
import tablas_pdf
import texto_nlp
from leer_pdf import log


def ejecutar(hasta=5, forzar=False):
    """Corre las fases 1 a `hasta` del proyecto PDF (usado tambien por pipeline_completo.py)."""
    log("=" * 60)
    log(f"main_pdf: inicio (forzar={forzar}, hasta fase {hasta})")
    leer_pdf.construir_inventario(forzar)
    if hasta >= 2:
        catalogo, procesados, omitidos = tablas_pdf.extraer_todo(forzar)
        log(f"Fase 2: documentos procesados {procesados}, omitidos (ya hechos) {omitidos}; filas en el catalogo {len(catalogo)}")
    if hasta >= 3:
        tablas_finales.ejecutar_fase3()
        contraloria_excel.ejecutar_anexos_excel()   # A2, A3, B3, B4, B6 y B7: tablas por obra, panel, PIM, modalidad/evento/servicios y principales obras
    if hasta >= 4:
        texto_nlp.ejecutar_fase4()
        import scraper_infobras   # (A4+B1+B2): rearma las tablas de la pasada ampliada desde su cache; sin cache no hace nada
        scraper_infobras.construir_csv_ampliados()
    if hasta >= 5:
        diccionario.escribir_diccionario()
    log("main_pdf: fin")


def main():
    parser = argparse.ArgumentParser(description="Inventario y extraccion de tablas de los PDF")
    parser.add_argument("--forzar", action="store_true", help="volver a procesar todo aunque ya este hecho")
    parser.add_argument("--hasta", type=int, default=5, help="ultima fase a ejecutar (1 inventario, 2 tablas, 3 tablas finales, 4 texto, 5 diccionario)")
    argumentos = parser.parse_args()
    ejecutar(argumentos.hasta, argumentos.forzar)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
