"""UN SOLO SCRIPT para reproducir toda la data del proyecto, de principio a fin, hasta las tablas del producto final.

    python src/pipeline_completo.py                        (todo; lo ya descargado o procesado se salta)
    python src/pipeline_completo.py --sin-descarga         (solo procesa lo que ya esta en data/raw)
    python src/pipeline_completo.py --fuentes escale,enla  (descarga solo esas fuentes)
    python src/pipeline_completo.py --forzar               (rehace todo, tarda mucho)
En Jupyter / VS Code: notebooks/proyecto_completo.ipynb llama a ejecutar() paso a paso.

Pasos, en este orden:
  1. Descarga: ESCALE, ENLA (Chrome visible), Contraloria (informes y anexos) y MEF (Formato 12-B, por HTTP). INFOBRAS solo con --fuentes infobras.
  2. Tablas de ESCALE y ENLA (SICRECE), niveles de logro, validacion, Excel y catalogo de variables de ESCALE.
  3. Datos personales: se quitan los nombres de personas de los comentarios ya guardados.
  4. Proyecto PDF, fases 1 a 4: inventario, tablas, cifras oficiales, panel por obra, texto, ubigeo de las obras e INFOBRAS ampliado.
  5. Producto final: NLP de causas, tablas intermedias y el CSV unico del dashboard (data/final/dashboard_obras.csv), con sus comprobaciones.
  6. Diccionario de todas las tablas (docs/diccionario.csv).
  7. Auditoria de datos personales en las tablas finales (falla si encuentra un nombre).
  8. Inventario de datos (docs/inventario_datos.md).
  9. Auditoria de calidad del CSV unico (docs/auditoria_calidad.csv; falla si encuentra algun error).
 10. Dashboard en HTML (resultados/dashboard.html): un solo archivo que se abre en el navegador, sin internet. Al terminar se abre solo (--no-abrir para evitarlo).
Cada paso deja su rastro en docs/log_descargas.txt y docs/log_pdf.txt. Si un paso falla, se avisa y se sigue con el siguiente.
"""
import argparse
import sys
import time
from types import SimpleNamespace

import auditoria_calidad
import catalogo_escale
import config
import dashboard_html
import datos_personales
import diccionario
import inventario_datos
import main
import main_pdf
import producto_final
import utils

FUENTES = ("escale", "enla", "contraloria", "infobras", "mef")      # las que existen
# INFOBRAS es una foto (27-oct y 11-nov-2026): si se volviera a leer, el listado cambiaria (hay obras que dejaron de estar paralizadas)
# y se moverian los numeros del producto. Por eso NO se descarga por defecto: hay que pedirlo con --fuentes infobras.
FUENTES_POR_DEFECTO = ("escale", "enla", "contraloria", "mef")


def leer_argumentos():
    p = argparse.ArgumentParser(description="Reproduce toda la data del proyecto con un solo comando")
    p.add_argument("--fuentes", default=",".join(FUENTES_POR_DEFECTO), help=f"fuentes a descargar, separadas por coma (por defecto: {','.join(FUENTES_POR_DEFECTO)}; INFOBRAS solo si se pide)")
    p.add_argument("--sin-descarga", action="store_true", help="no abrir el navegador ni bajar nada: solo procesar lo ya descargado")
    p.add_argument("--anio-inicio", type=int, default=config.ANIO_INICIO, help="primer año a descargar")
    p.add_argument("--forzar", action="store_true", help="descargar y procesar de nuevo aunque ya este hecho")
    p.add_argument("--headless", action="store_true", help="navegador sin ventana")
    p.add_argument("--desde-tablas", action="store_true", help="solo los pasos 5 a 10 (producto final, diccionario, auditorias y dashboard) con las tablas ya procesadas; no necesita data/raw (es lo que corre GitHub)")
    p.add_argument("--no-abrir", action="store_true", help="no abrir el dashboard en el navegador al terminar")
    args = p.parse_args()
    args.fuentes = [f.strip() for f in args.fuentes.split(",") if f.strip()]
    desconocidas = [f for f in args.fuentes if f not in FUENTES]
    if desconocidas:
        p.error(f"fuente desconocida: {desconocidas}; las validas son {FUENTES}")
    return args


def hay_datos_crudos():
    """True si data/raw existe y tiene archivos (el repositorio de GitHub no los trae: algunos contienen datos personales)."""
    return config.RAW.exists() and any(p.is_file() for p in config.RAW.rglob("*"))


def paso(numero, nombre, funcion):
    """Ejecuta un paso; si falla lo registra y devuelve False, para seguir con el siguiente."""
    utils.log(f"=== PASO {numero}: {nombre} ===")
    inicio = time.time()
    try:
        funcion()
        utils.log(f"=== PASO {numero} terminado en {time.time() - inicio:.0f} s ===")
        return True
    except Exception as error:
        utils.log(f"=== PASO {numero} FALLO ({type(error).__name__}: {error}); se sigue con el siguiente. Los archivos ya descargados siguen en data/raw ===")
        return False


def ejecutar(fuentes=FUENTES_POR_DEFECTO, sin_descarga=False, forzar=False, headless=False, anio_inicio=config.ANIO_INICIO, desde_tablas=False):
    """Corre los 10 pasos. Devuelve la lista de pasos que fallaron (vacia si todo salio bien). Tambien se usa desde Jupyter."""
    utils.log(f"PIPELINE COMPLETO: fuentes={list(fuentes)}, sin_descarga={sin_descarga}, forzar={forzar}, anio_inicio={anio_inicio}")
    # el mismo objeto de argumentos que usa main.py (solo=None significa «todas las fuentes elegidas»)
    a = SimpleNamespace(anio_inicio=anio_inicio, solo=None, forzar=forzar, headless=headless, fuentes=list(fuentes))
    resultados = {}
    if sin_descarga and not desde_tablas and not hay_datos_crudos():
        utils.log("AVISO: no hay datos crudos en data/raw y se pidio no descargar: se usa el modo --desde-tablas (pasos 5 a 10)")
        desde_tablas = True
    if desde_tablas:
        utils.log("MODO DESDE TABLAS: se omiten los pasos 1 a 4 (descarga y datos crudos); se parte de data/processed")
    else:
        if not sin_descarga:
            resultados["descarga"] = paso(1, "descarga de las fuentes", lambda: main.descargar(a))
        resultados["escale_enla"] = paso(2, "tablas de ESCALE y ENLA", lambda: (main.extraer(a), catalogo_escale.construir()))
        resultados["datos_personales"] = paso(3, "limpieza de datos personales en lo ya guardado", datos_personales.limpiar)
        resultados["pdf"] = paso(4, "proyecto PDF (fases 1 a 4; el diccionario de la fase 5 se escribe en el paso 6)", lambda: main_pdf.ejecutar(4, forzar))
    resultados["producto_final"] = paso(5, "producto final (data/final)", producto_final.construir)
    resultados["diccionario"] = paso(6, "diccionario de todas las tablas", diccionario.escribir_diccionario)
    resultados["auditoria"] = paso(7, "auditoria de datos personales", datos_personales.auditoria_o_falla)
    resultados["inventario"] = paso(8, "inventario de datos", inventario_datos.construir)
    resultados["calidad"] = paso(9, "auditoria de calidad del CSV unico (falla si hay algun error)", auditoria_calidad.auditoria_o_falla)
    resultados["dashboard_html"] = paso(10, "dashboard en HTML (resultados/dashboard.html)", dashboard_html.construir)
    fallidos = [k for k, ok in resultados.items() if not ok]
    utils.log("PIPELINE COMPLETO: terminado" + (f", con pasos fallidos: {fallidos}" if fallidos else " sin fallos"))
    return fallidos


def abrir_dashboard():
    """Abre resultados/dashboard.html en el navegador predeterminado (si se genero)."""
    import webbrowser
    if dashboard_html.SALIDA.exists():
        utils.log(f"Abriendo el dashboard: {dashboard_html.SALIDA}")
        webbrowser.open(dashboard_html.SALIDA.resolve().as_uri())
    else:
        utils.log("AVISO: no se encontro resultados/dashboard.html; revise el paso 10")


def main_completo():
    args = leer_argumentos()
    fallidos = ejecutar(args.fuentes, args.sin_descarga, args.forzar, args.headless, args.anio_inicio, args.desde_tablas)
    if not args.no_abrir:
        abrir_dashboard()
    return fallidos


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(1 if main_completo() else 0)
