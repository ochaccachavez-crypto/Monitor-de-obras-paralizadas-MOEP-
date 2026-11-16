"""Funciones de apoyo: navegador, log, registro de fuentes, descargas, lectura de .dbf y resumen."""
import csv
import json
import random
import re
import shutil
import struct
import time
import unicodedata
import zipfile
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from selenium import webdriver
from selenium.common.exceptions import ElementClickInterceptedException, ElementNotInteractableException

import config

COLUMNAS_REGISTRO = [
    "fuente", "url", "archivo", "anio", "filtros_usados", "fecha_descarga",
    "fecha_corte_del_dato", "tamano_mb", "estado", "notas",
]


# ---------------- log y pausas ----------------
def log(mensaje, archivo=None):
    """Escribe un evento con fecha y hora en pantalla y en el log (por defecto el de descargas; las fases de PDF usan el suyo)."""
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {mensaje}"
    print(linea)
    with open(archivo or config.LOG, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def pausa():
    """Pausa aleatoria entre acciones de descarga."""
    time.sleep(random.uniform(config.PAUSA_MIN, config.PAUSA_MAX))


# ---------------- navegador ----------------
def crear_navegador(carpeta_descarga, headless=False, origen_http=None, registrar_red=False):
    """Abre Chrome (visible por defecto) y lo configura para descargar sin preguntar.

    origen_http: sitio que solo funciona por http y del que se confia para poder descargar.
    registrar_red: guarda el trafico de red para poder leer las respuestas que recibe la pagina.
    """
    carpeta_descarga = Path(carpeta_descarga)
    carpeta_descarga.mkdir(parents=True, exist_ok=True)
    opciones = webdriver.ChromeOptions()
    opciones.add_argument(f"--user-agent={config.USER_AGENT}")
    opciones.add_argument("--window-size=1400,1000")
    # evita que Chrome (perfil nuevo) descargue componentes internos dentro de la carpeta de descargas
    opciones.add_argument("--disable-component-update")
    opciones.add_argument("--disable-background-networking")
    if headless:
        opciones.add_argument("--headless=new")
    if origen_http:
        opciones.add_argument(f"--unsafely-treat-insecure-origin-as-secure={origen_http}")
    if registrar_red:
        opciones.set_capability("goog:loggingPrefs", {"performance": "ALL"})
    opciones.add_experimental_option("prefs", {
        "download.default_directory": str(carpeta_descarga),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "plugins.always_open_pdf_externally": True,   # los PDF se descargan, no se abren
    })
    return webdriver.Chrome(options=opciones)


def cambiar_carpeta_descarga(driver, carpeta):
    """Cambia la carpeta de descarga del navegador abierto (una carpeta por anio)."""
    Path(carpeta).mkdir(parents=True, exist_ok=True)
    driver.execute_cdp_cmd("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": str(carpeta)})


def hacer_clic(driver, elemento):
    """Clic normal; si el elemento esta oculto o tapado, clic por JavaScript."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", elemento)
        elemento.click()
    except (ElementNotInteractableException, ElementClickInterceptedException):
        driver.execute_script("arguments[0].click();", elemento)


def limpiar_registro_red(driver):
    """Vacia el registro de red acumulado (cada lectura de get_log lo borra)."""
    driver.get_log("performance")


def respuesta_post(driver, fragmento_url):
    """Espera la respuesta de un POST cuya URL contenga el fragmento y devuelve su cuerpo (texto)."""
    ids_post, vistos = set(), set()
    limite = time.time() + config.SICRECE_ESPERA_RESPUESTA
    while time.time() < limite:
        for entrada in driver.get_log("performance"):
            m = json.loads(entrada["message"])["message"]
            p = m["params"]
            if m["method"] == "Network.requestWillBeSent" and fragmento_url in p["request"]["url"] and p["request"]["method"] == "POST":
                ids_post.add(p["requestId"])
            elif m["method"] == "Network.loadingFinished" and p["requestId"] in ids_post:
                vistos.add(p["requestId"])
        for rid in vistos:
            try:
                return driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": rid})["body"]
            except Exception:
                pass   # la respuesta todavia no esta disponible: se reintenta
        time.sleep(0.5)
    raise TimeoutError("no llego la respuesta de la API")


def captura(driver, nombre):
    """Guarda una captura de pantalla en docs\\capturas."""
    ruta = config.CAPTURAS / f"{nombre}.png"
    try:
        driver.save_screenshot(str(ruta))
        log(f"captura guardada: {ruta.name}")
    except Exception as error:
        log(f"no se pudo guardar la captura {nombre}: {error}")


# ---------------- descargas ----------------
def archivos_actuales(carpeta):
    return {p.name for p in Path(carpeta).iterdir() if p.is_file()}


def limpiar_parciales(carpeta):
    """Borra descargas interrumpidas (.crdownload) que quedaron de un intento anterior."""
    for parcial in Path(carpeta).glob("*.crdownload"):
        parcial.unlink(missing_ok=True)


def esperar_descarga(carpeta, antes, extension):
    """Espera un archivo nuevo con esa extension (ej. '.pdf') y a que termine su .crdownload.

    Se ignoran los demas archivos nuevos: Chrome puede dejar archivos propios en la carpeta.
    """
    extensiones = (extension,) if isinstance(extension, str) else tuple(extension)   # una o varias (ej. .xlsx y .xls)
    terminaciones = tuple(e.lower() for e in extensiones) + tuple(e.lower() + ".crdownload" for e in extensiones)
    limite = time.time() + config.ESPERA_DESCARGA
    while time.time() < limite:
        nuevos = [n for n in archivos_actuales(carpeta) - antes if n.lower().endswith(terminaciones)]
        en_curso = [n for n in nuevos if n.lower().endswith(".crdownload")]
        terminados = [n for n in nuevos if n not in en_curso]
        if terminados and not en_curso:
            return Path(carpeta) / terminados[0]
        time.sleep(1)
    raise TimeoutError("la descarga no termino a tiempo")


def extension_real(ruta):
    """Extension segun el contenido: Chrome a veces guarda un .xlsx con la extension .xls."""
    ruta = Path(ruta)
    if ruta.suffix.lower() in (".xls", ".xlsx"):
        with open(ruta, "rb") as f:
            return ".xlsx" if f.read(2) == b"PK" else ".xls"   # un .xlsx es un zip; el .xls antiguo no
    return ruta.suffix.lower()


def archivo_valido(ruta):
    """Comprueba que un PDF, ZIP o JSON sea de verdad de ese tipo (otros tipos se aceptan)."""
    ruta = Path(ruta)
    tipo = ruta.suffix.lower()
    try:
        if tipo == ".pdf":
            with open(ruta, "rb") as f:
                return f.read(5) == b"%PDF-"
        if tipo in (".zip", ".xlsx"):   # un .xlsx es un zip por dentro
            return zipfile.is_zipfile(ruta)
        if tipo == ".json":
            json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return True


def nombre_limpio(nombre_original):
    """'51_Loc_lineal_1.zip' -> 'loc_lineal_1' (sin tildes, sin numero inicial, en minusculas)."""
    base = Path(nombre_original).stem
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "_", base.lower()).strip("_")
    return re.sub(r"^\d+_", "", base)[:60]


def nombre_destino(fuente, anio, descripcion, extension):
    """Formato: {fuente}_{anio}_{descripcion}_{AAAA-MM-DD}.{ext}"""
    return f"{fuente}_{anio}_{descripcion}_{date.today():%Y-%m-%d}.{extension.lstrip('.')}"


def ya_descargado(fuente, anio, filtros):
    """True si el registro tiene esa descarga como 'ok' y el archivo sigue en disco y es valido."""
    if not config.REGISTRO.exists():
        return False
    with open(config.REGISTRO, newline="", encoding="utf-8-sig") as f:
        for fila in csv.DictReader(f):
            if (fila["fuente"] == fuente and fila["anio"] == str(anio) and fila["estado"] == "ok"
                    and fila["filtros_usados"] == filtros):
                ruta = config.RAW / fuente / str(anio) / fila["archivo"]
                if ruta.exists() and archivo_valido(ruta):
                    return True
    return False


def registrar_fuente(**campos):
    """Agrega una fila a docs\\registro_fuentes.csv."""
    existe = config.REGISTRO.exists()
    fila = {c: campos.get(c, "") for c in COLUMNAS_REGISTRO}
    with open(config.REGISTRO, "a", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=COLUMNAS_REGISTRO)
        if not existe:
            escritor.writeheader()
        escritor.writerow(fila)


def guardar_descarga(descargado, carpeta, fuente, anio, nombre_original, url, filtros, fecha_corte="no confirmado", notas=""):
    """Renombra el archivo descargado, lo registra y devuelve (ruta_final, tamano_mb)."""
    if not archivo_valido(descargado):
        raise ValueError(f"el archivo descargado no es un {Path(nombre_original).suffix} valido")
    destino = Path(carpeta) / nombre_destino(
        fuente, anio, nombre_limpio(nombre_original), Path(nombre_original).suffix)
    destino.unlink(missing_ok=True)   # solo existe si se uso --forzar el mismo dia
    shutil.move(str(descargado), str(destino))
    mb = round(destino.stat().st_size / 1024 / 1024, 3)
    registrar_fuente(fuente=fuente, url=url, archivo=destino.name, anio=anio, filtros_usados=filtros,
                     fecha_descarga=str(date.today()), fecha_corte_del_dato=fecha_corte,
                     tamano_mb=mb, estado="ok", notas=notas)
    return destino, mb


def registrar_omitido(fuente, anio, nombre_original, filtros):
    registrar_fuente(fuente=fuente, archivo=nombre_original, anio=anio, filtros_usados=filtros,
                     fecha_descarga=str(date.today()), estado="omitido", notas="ya estaba descargado")


def registrar_error(fuente, anio, nombre_original, filtros, motivo):
    registrar_fuente(fuente=fuente, archivo=nombre_original, anio=anio, filtros_usados=filtros,
                     fecha_descarga=str(date.today()), estado="error", notas=str(motivo)[:200])


# ---------------- resumen ----------------
def nuevo_resultado(fuente):
    return {"fuente": fuente, "descargados": [], "omitidos": [], "errores": [],
            "anios_encontrados": [], "anios_faltantes": [], "anios_sin_archivos": []}


def imprimir_resumen(resultados):
    """Imprime y guarda en el log el resumen final de la corrida."""
    log("=" * 60)
    log("RESUMEN DE LA CORRIDA")
    total_mb = 0.0
    for r in resultados:
        mb = sum(m for _, m in r["descargados"])
        total_mb += mb
        log(f"[{r['fuente']}] descargados={len(r['descargados'])} ({mb:.2f} MB) | "
            f"omitidos (ya existian)={len(r['omitidos'])} | errores={len(r['errores'])}")
        log(f"[{r['fuente']}] anios encontrados desde el inicio: {r['anios_encontrados']}")
        if r["anios_faltantes"]:
            log(f"[{r['fuente']}] anios SIN carpeta en el portal: {r['anios_faltantes']}")
        if r["anios_sin_archivos"]:
            log(f"[{r['fuente']}] anios sin archivos que coincidan con la seleccion: {r['anios_sin_archivos']}")
        for nombre, motivo in r["errores"]:
            log(f"[{r['fuente']}] ERROR {nombre}: {motivo}")
    log(f"Peso total descargado en esta corrida: {total_mb:.2f} MB")
    log("=" * 60)


# ---------------- lectura de .dbf ----------------
def campos_dbf(ruta):
    """Lee la cabecera de un .dbf: devuelve (n_registros, largo_registro, inicio_datos, codigo_idioma, campos)."""
    with open(ruta, "rb") as f:
        cab = f.read(32)
        n_reg = struct.unpack("<I", cab[4:8])[0]
        largo_cab, largo_reg = struct.unpack("<HH", cab[8:12])
        campos = []
        while True:
            d = f.read(32)
            if d[:1] == b"\r":
                break
            nombre = d[:11].split(b"\x00")[0].decode("ascii")
            campos.append((nombre, chr(d[11]), d[16], d[17]))   # nombre, tipo, largo, decimales
    return n_reg, largo_reg, largo_cab, cab[29], campos


# byte de idioma de la cabecera del .dbf -> pagina de codigos (0x03 y otros: UTF-8 o cp1252, se prueba)
CODIFICACION_DBF = {0x01: "cp437", 0x02: "cp850", 0x57: "cp1252", 0xC8: "cp1250"}


def _decodificar(columna, codificacion):
    """Con codificacion=None prueba UTF-8 y, si falla, cp1252 (los archivos de ESCALE mezclan ambas)."""
    if codificacion:
        return np.char.decode(columna, codificacion, "replace")
    try:
        return np.char.decode(columna, "utf-8")
    except UnicodeDecodeError:
        # columna con valores mezclados: cada valor distinto se decodifica como UTF-8 si se puede y si no como cp1252
        unicos, posicion = np.unique(columna, return_inverse=True)
        textos = np.array([_texto(valor) for valor in unicos])
        return textos[posicion]


def _texto(valor):
    try:
        return valor.decode("utf-8")
    except UnicodeDecodeError:
        return valor.decode("cp1252", "replace")


def leer_dbf(ruta, columnas=None, max_filas=None, codificacion="auto"):
    """Lee un .dbf como texto (conserva ceros a la izquierda). columnas=None lee todas."""
    n_reg, largo_reg, largo_cab, idioma, campos = campos_dbf(ruta)
    if codificacion == "auto":
        codificacion = CODIFICACION_DBF.get(idioma)
    dtipo = np.dtype([("_borrado", "S1")] + [(n, f"S{largo}") for n, _, largo, _ in campos])
    assert dtipo.itemsize == largo_reg, "el largo de registro no coincide con la cabecera"
    filas = n_reg if max_filas is None else min(max_filas, n_reg)
    datos = np.fromfile(ruta, dtype=dtipo, count=filas, offset=largo_cab)
    datos = datos[datos["_borrado"] != b"*"]
    nombres = columnas or [n for n, *_ in campos]
    tabla = {n: np.char.strip(_decodificar(datos[n], codificacion)) for n in nombres}
    return pd.DataFrame(tabla)


# ---------------- datos personales ----------------
OMITIDO = "[NOMBRE OMITIDO]"
# una palabra de nombre nunca puede ser un cargo ni «consorcio»: asi un nombre no se come al cargo que le sigue
_NO_NOMBRE = r"(?!(?i:residente|supervisor|supervisora|inspector|inspectora|proyectista|consorcio|contratista|tipo|obra)\b)"
_PALABRA_MAYUS = _NO_NOMBRE + r"[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'’]{1,}"
_PALABRA_TITULO = _NO_NOMBRE + r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ'’]{1,}"
_NOMBRE_MAYUS = rf"{_PALABRA_MAYUS}(?:\s+(?:de|del|de\s+la|DE|DEL|DE\s+LA)\s+{_PALABRA_MAYUS}|\s+{_PALABRA_MAYUS}){{1,4}}"
_NOMBRE_TITULO = rf"{_PALABRA_TITULO}(?:\s+(?:de|del|de\s+la)\s+{_PALABRA_TITULO}|\s+{_PALABRA_TITULO}){{1,4}}"
_NOMBRE_SOLO_MAYUS = _NO_NOMBRE + r"[A-ZÁÉÍÓÚÑ]{3,}(?:\s+" + _NO_NOMBRE + r"[A-ZÁÉÍÓÚÑ]{2,}){1,3}"
_TITULOS = r"(?:ing|arq|abog|econ|lic|sr|sra|srta|cpc|bach)"   # el punto es opcional; «Dr.» y «Dra.» llevan punto obligatorio (DRA = Direccion Regional de Agricultura)
_CARGOS = r"(?:residente|supervisor|supervisora|inspector|inspectora|proyectista)(?:\s+de\s+obra)?"
_NO_ES_NOMBRE = ("consorcio", "empresa", "municipalidad", "gobierno", "unidad", "proyecto", "obra", "entidad", "contratista", "sociedad",
                 "universidad", "comunica", "presenta", "informa", "solicita", "indica", "cuenta", "no", "se", "el", "la", "de", "del", "y")


def omitir_nombres(texto):
    """Reemplaza nombres de personas naturales en un comentario libre por [NOMBRE OMITIDO].

    Reglas: (1) un titulo (Ing., Arq., Lic., Sr., Dr., ...) seguido de un nombre; (2) un cargo (residente, supervisor, inspector)
    seguido de un nombre con inicial mayuscula (no si va despues de «Consorcio»); (3) un cargo seguido de dos puntos y un nombre en
    mayusculas. Es una barrera simple: ante la duda borra de mas. datos_personales.auditar() la vigila con patrones propios.
    """
    if not isinstance(texto, str) or not texto:
        return texto
    texto = re.sub(rf"\b(?i:{_TITULOS})\.?\s+{_NOMBRE_MAYUS}", OMITIDO, texto)
    texto = re.sub(rf"\b(?i:dra?)\.\s+{_NOMBRE_MAYUS}", OMITIDO, texto)

    def por_cargo(m):
        primera = m.group("nombre").split()[0].lower()
        return m.group(0) if primera in _NO_ES_NOMBRE else f"{m.group('cargo')}{m.group('sep')}{OMITIDO}"

    texto = re.sub(rf"(?<!(?i:consorcio) )(?P<cargo>\b(?i:{_CARGOS}))(?P<sep>[,:]?\s+)(?P<nombre>{_NOMBRE_TITULO})", por_cargo, texto)
    return re.sub(rf"(?P<cargo>\b(?i:{_CARGOS}))(?P<sep>\s*:\s*)(?P<nombre>{_NOMBRE_SOLO_MAYUS})", por_cargo, texto)
