"""Punto de entrada. Ejemplo: python src/main.py --anio-inicio 2022 --solo escale

Orden: descarga (ESCALE, ENLA, Contraloria e INFOBRAS) -> extraccion a tablas -> validacion -> diccionario de datos -> Excel.
"""
import argparse

import config
import descarga_mef
import diccionario
import exportar
import extraccion
import scraper_contraloria
import scraper_enla
import scraper_escale
import scraper_infobras
import utils


def leer_argumentos():
    p = argparse.ArgumentParser(description="Descarga automatizada de ESCALE y ENLA y extraccion a tablas")
    p.add_argument("--anio-inicio", type=int, default=config.ANIO_INICIO, help="primer anio a descargar")
    p.add_argument("--solo", choices=["escale", "enla", "contraloria", "infobras", "mef"], help="ejecutar solo una fuente")
    p.add_argument("--forzar", action="store_true", help="descargar de nuevo aunque ya exista")
    p.add_argument("--headless", action="store_true", help="navegador sin ventana (por defecto es visible)")
    return p.parse_args()


def descargar(args):
    """Corre los scrapers. Si una fuente falla, se registra y se sigue con la otra."""
    fuentes = {"escale": scraper_escale, "enla": scraper_enla, "contraloria": scraper_contraloria,
               "infobras": scraper_infobras, "mef": descarga_mef}
    resultados = []
    for nombre, modulo in fuentes.items():
        if args.solo and args.solo != nombre:
            continue
        if getattr(args, "fuentes", None) and nombre not in args.fuentes:
            continue
        try:
            resultados.append(modulo.ejecutar(args.anio_inicio, args.forzar, args.headless))
        except Exception as error:
            utils.log(f"{nombre.upper()}: error inesperado, se continua con la siguiente fuente: {type(error).__name__} {error}")
            resultado = utils.nuevo_resultado(nombre.upper())
            resultado["errores"].append(("fuente completa", type(error).__name__))
            resultados.append(resultado)
    utils.imprimir_resumen(resultados)


def extraer(args):
    """Convierte lo descargado en data/processed y valida las tablas."""
    if args.solo in ("contraloria", "infobras"):
        return   # esas fuentes se procesan con src/main_pdf.py
    escale = enla = None
    try:
        if args.solo in (None, "escale"):
            escale, _ = extraccion.construir_escale(args.anio_inicio)
        if args.solo in (None, "enla"):
            enla = extraccion.construir_enla()
            extraccion.construir_enla_niveles()
        extraccion.validar(escale, enla)
        diccionario.escribir_diccionario()
        exportar.escribir_excel()
    except Exception as error:
        utils.log(f"EXTRACCION: fallo ({type(error).__name__}: {error}). Los archivos descargados siguen en data/raw.")


def main():
    args = leer_argumentos()
    utils.log(f"Inicio de corrida: anio_inicio={args.anio_inicio}, solo={args.solo}, forzar={args.forzar}, headless={args.headless}")
    descargar(args)
    extraer(args)
    utils.log("Fin de corrida")


if __name__ == "__main__":
    main()
