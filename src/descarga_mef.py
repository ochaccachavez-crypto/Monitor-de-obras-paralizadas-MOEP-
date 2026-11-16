"""MEF (Portal de Datos Abiertos): Formato 12-B de inversiones, con el devengado de cada inversion identificada por su CUI.

Es un archivo CSV publico (~180 MB) que se baja con una sola peticion HTTP, sin navegador. Se renueva una vez al mes (el archivo del MEF
se actualiza seguido, pero para este proyecto basta una foto mensual). Solo se guardan en data/processed las inversiones (CUI) que
aparecen en nuestras tablas de obras.
"""
import urllib.request
from datetime import date

import pandas as pd

import config
import utils

COLUMNAS_MEF = {   # columna del MEF -> nombre en nuestra tabla
    "CODIGO_UNICO": "cui", "ESTADO": "estado_mef", "PRIMER_DEVENGADO": "primer_devengado", "ULTIMO_DEVENGADO": "ultimo_devengado",
    "DEVENGADO_ACUMULADO": "devengado_hasta_anio_anterior_soles", "DEV_AÑO_ACTUAL": "devengado_anio_actual_soles",
    "PIM_AÑO_ACTUAL": "pim_anio_actual_soles", "AVANCE_FISICO": "avance_fisico_mef_pct", "AVANCE_EJECUCION": "avance_ejecucion_mef_pct",
    "ULT_PROBLEMA": "ult_problema",
    "FECHA_ULT_ACT_F12B": "fecha_ult_act_f12b", "ULT_PERIODO_REG_F12B": "ult_periodo_reg_f12b",
    "INICIO_EJEC_FISICA": "inicio_ejec_fisica", "CULMINA_EJEC_FISICA": "culmina_ejec_fisica"}


def _bajar(url, destino):
    """Descarga una URL a un archivo, en bloques, con el User-Agent del proyecto. Devuelve los bytes bajados."""
    pedido = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    total = 0
    with urllib.request.urlopen(pedido, timeout=120) as respuesta, open(destino, "wb") as f:
        while True:
            bloque = respuesta.read(1024 * 1024)
            if not bloque:
                break
            f.write(bloque)
            total += len(bloque)
    return total


def _es_f12b_valido(ruta):
    """El archivo debe ser un CSV con la columna CODIGO_UNICO (no una pagina de error)."""
    cabecera = pd.read_csv(ruta, nrows=0, encoding="utf-8-sig").columns
    return "CODIGO_UNICO" in [c.strip() for c in cabecera]


def descargar(forzar=False):
    """Baja FORMATO_12B.csv a data/raw/mef/{anio}/ una vez por mes. Devuelve (ruta del archivo vigente, True si se bajo ahora)."""
    anio = date.today().year
    carpeta = config.RAW / "mef" / str(anio)
    carpeta.mkdir(parents=True, exist_ok=True)
    filtros = f"{config.MEF_FILTROS_TEXTO};mes={date.today():%Y-%m}"
    existentes = sorted(carpeta.glob(f"mef_{anio}_formato_12b_*.csv"))
    if not forzar and utils.ya_descargado("mef", anio, filtros) and existentes:
        utils.log(f"MEF: el Formato 12-B de este mes ya estaba descargado ({existentes[-1].name})")
        utils.registrar_omitido("mef", anio, existentes[-1].name, filtros)
        return existentes[-1], False
    utils.limpiar_parciales(carpeta)
    temporal = carpeta / "descarga_en_curso.crdownload"
    utils.log(f"MEF: descargando {config.MEF_URL_F12B} (unos 180 MB, una sola peticion)")
    bytes_bajados = _bajar(config.MEF_URL_F12B, temporal)
    if not _es_f12b_valido(temporal):
        temporal.unlink(missing_ok=True)
        raise ValueError("el archivo descargado del MEF no tiene la columna CODIGO_UNICO")
    destino = carpeta / utils.nombre_destino("mef", anio, "formato_12b", ".csv")
    destino.unlink(missing_ok=True)
    temporal.rename(destino)
    utils.registrar_fuente(fuente="mef", url=config.MEF_URL_F12B, archivo=destino.name, anio=anio, filtros_usados=filtros,
                           fecha_descarga=str(date.today()), fecha_corte_del_dato=str(date.today()),
                           tamano_mb=round(bytes_bajados / 1024 / 1024, 3), estado="ok",
                           notas="foto del dia de la descarga; el MEF actualiza el archivo con frecuencia")
    # el diccionario de datos del MEF acompana al archivo si esta disponible (el 2026-11-12 su servidor lo tenia vacio: 404)
    dic = carpeta / utils.nombre_destino("mef", anio, "formato_12b_diccionario", ".csv")
    if not dic.exists():
        try:
            _bajar(config.MEF_URL_F12B_DICCIONARIO, dic)
        except Exception as error:
            dic.unlink(missing_ok=True)
            utils.log(f"MEF: aviso, no se pudo bajar el diccionario del MEF ({type(error).__name__}); sus columnas estan en el diccionario de este proyecto")
    utils.log(f"MEF: guardado {destino.name} ({bytes_bajados / 1024 / 1024:.0f} MB)")
    return destino, True


def ejecutar(anio_inicio=None, forzar=False, headless=False):
    """Misma firma que los demas scrapers (main.descargar). anio_inicio y headless no se usan: no hay navegador."""
    resultado = utils.nuevo_resultado("mef")
    try:
        ruta, nuevo = descargar(forzar)
        resultado["descargados" if nuevo else "omitidos"].append(ruta.name)
    except Exception as error:
        utils.log(f"MEF: no se pudo descargar ({type(error).__name__}: {error})")
        resultado["errores"].append(("formato_12b", type(error).__name__))
    return resultado


def construir_tabla(cuis):
    """Filtra el Formato 12-B a los CUI indicados y guarda data/processed/mef_f12b_obras.csv (una fila por CUI)."""
    existentes = sorted((config.RAW / "mef").glob("*/mef_*_formato_12b_*.csv"))
    existentes = [e for e in existentes if "diccionario" not in e.name]
    if not existentes:
        utils.log("MEF: no hay Formato 12-B descargado; se omite mef_f12b_obras.csv")
        return None
    ruta = existentes[-1]
    cuis = {str(c).strip() for c in cuis if str(c).strip() not in ("", "nan")}
    piezas = []
    for bloque in pd.read_csv(ruta, dtype=str, encoding="utf-8-sig", chunksize=100_000, usecols=list(COLUMNAS_MEF)):
        bloque["CODIGO_UNICO"] = bloque["CODIGO_UNICO"].str.strip()
        piezas.append(bloque[bloque.CODIGO_UNICO.isin(cuis)])
    tabla = pd.concat(piezas).rename(columns=COLUMNAS_MEF).drop_duplicates("cui", keep="last")
    for c in ("devengado_hasta_anio_anterior_soles", "devengado_anio_actual_soles", "pim_anio_actual_soles", "avance_fisico_mef_pct", "avance_ejecucion_mef_pct"):
        tabla[c] = pd.to_numeric(tabla[c].str.replace(",", ""), errors="coerce")
    tabla["ult_problema"] = tabla.ult_problema.map(utils.omitir_nombres)   # texto libre de la entidad: sin nombres de personas
    tabla["devengado_total_soles"] = tabla.devengado_hasta_anio_anterior_soles.fillna(0) + tabla.devengado_anio_actual_soles.fillna(0)
    tabla["archivo_mef"] = ruta.name
    tabla = tabla.sort_values("cui").reset_index(drop=True)
    tabla.to_csv(config.PROCESSED / "mef_f12b_obras.csv", index=False, encoding="utf-8-sig")
    utils.log(f"MEF: mef_f12b_obras.csv con {len(tabla)} de {len(cuis)} CUI encontrados en el Formato 12-B")
    return tabla
