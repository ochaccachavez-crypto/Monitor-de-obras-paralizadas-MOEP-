"""ESCALE: abre el portal, recorre cada anio del Censo Educativo y descarga los archivos de local educativo."""
import re
from pathlib import Path

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import config
import utils


def esperar(driver):
    return WebDriverWait(driver, config.ESPERA_ELEMENTO)


def abrir_portal(driver):
    driver.get(config.ESCALE_URL_INICIO)
    esperar(driver).until(EC.presence_of_element_located((By.LINK_TEXT, config.ESCALE_CARPETA_CENSO)))


def elegir_carpeta_censo(driver):
    driver.find_element(By.LINK_TEXT, config.ESCALE_CARPETA_CENSO).click()
    esperar(driver).until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "20")))


def listar_anios(driver):
    """Devuelve {anio: enlace_de_la_carpeta} leyendo las carpetas que hay en el portal."""
    anios = {}
    for enlace in driver.find_elements(By.TAG_NAME, "a"):
        href = enlace.get_attribute("href") or ""
        if re.fullmatch(r"\d{4}", enlace.text.strip()) and "document_library_display" in href:
            anios[int(enlace.text.strip())] = href
    return anios


def elegir_anio(driver, enlace_anio):
    driver.get(enlace_anio)
    esperar(driver).until(EC.presence_of_element_located((By.CSS_SELECTOR, "table")))


def listar_archivos(driver):
    """Recorre todas las paginas de la carpeta y devuelve {nombre_archivo: enlace_de_detalle}."""
    archivos = {}
    for _ in range(config.ESCALE_MAX_PAGINAS):
        for enlace in driver.find_elements(By.CSS_SELECTOR, config.ESCALE_SELECTOR_ARCHIVOS):
            # el texto a veces trae una descripcion pegada: se corta en la extension
            m = re.match(rf"^(.+?{config.EXTENSIONES})\b", enlace.text.strip(), re.I)
            if m:
                archivos.setdefault(m.group(1), enlace.get_attribute("href"))
        siguientes = [a for a in driver.find_elements(By.LINK_TEXT, config.ESCALE_SIGUIENTE) if a.is_displayed()]
        if not siguientes:
            break
        siguientes[0].click()
        esperar(driver).until(EC.staleness_of(siguientes[0]))
    return archivos


def elegir_objetivos(archivos):
    """Se queda solo con los archivos que coinciden con los patrones de config.py."""
    elegidos = {}
    for nombre, enlace in archivos.items():
        for patron in config.ESCALE_PATRONES.values():
            if re.search(patron, nombre):
                elegidos[nombre] = enlace
                break
    return elegidos


def descargar_archivo(driver, carpeta, anio, nombre, enlace_detalle, forzar, resultado):
    filtros = f"Censo Educativo > {anio} > {nombre}"
    if not forzar and utils.ya_descargado("escale", anio, filtros):
        utils.log(f"ESCALE {anio}: {nombre} ya estaba descargado, se omite")
        utils.registrar_omitido("escale", anio, nombre, filtros)
        resultado["omitidos"].append(nombre)
        return
    motivo = ""
    for intento in range(1, config.REINTENTOS + 1):
        try:
            utils.limpiar_parciales(carpeta)
            driver.get(enlace_detalle)
            boton = esperar(driver).until(EC.element_to_be_clickable((By.XPATH, config.ESCALE_BOTON_DESCARGAR)))
            url = boton.get_attribute("href")
            antes = utils.archivos_actuales(carpeta)
            boton.click()
            descargado = utils.esperar_descarga(carpeta, antes, Path(nombre).suffix)
            destino, mb = utils.guardar_descarga(descargado, carpeta, "escale", anio, nombre, url, filtros)
            utils.log(f"ESCALE {anio}: descargado {destino.name} ({mb} MB)")
            resultado["descargados"].append((destino.name, mb))
            return
        except (TimeoutException, TimeoutError, WebDriverException, ValueError) as error:
            motivo = f"{type(error).__name__}"
            utils.log(f"ESCALE {anio}: intento {intento}/{config.REINTENTOS} fallo para {nombre}: {motivo}")
            utils.captura(driver, f"error_escale_{anio}_{utils.nombre_limpio(nombre)}_intento{intento}")
            utils.pausa()
    utils.registrar_error("escale", anio, nombre, filtros, motivo)
    resultado["errores"].append((f"{anio} {nombre}", motivo))


def ejecutar(anio_inicio=config.ANIO_INICIO, forzar=False, headless=False):
    resultado = utils.nuevo_resultado("ESCALE")
    driver = utils.crear_navegador(config.RAW / "escale", headless)
    try:
        try:
            abrir_portal(driver)
            elegir_carpeta_censo(driver)
            anios = listar_anios(driver)
        except (TimeoutException, WebDriverException) as error:
            utils.log(f"ESCALE: el portal no responde o cambio de estructura ({type(error).__name__}). Se omite la fuente.")
            utils.captura(driver, "error_escale_portal")
            resultado["errores"].append(("portal", type(error).__name__))
            return resultado

        disponibles = sorted(a for a in anios if a >= anio_inicio)
        resultado["anios_encontrados"] = disponibles
        if anios:
            resultado["anios_faltantes"] = [a for a in range(anio_inicio, max(anios) + 1) if a not in anios]
        utils.log(f"ESCALE: anios disponibles desde {anio_inicio}: {disponibles}")

        for anio in disponibles:
            try:
                carpeta = config.RAW / "escale" / str(anio)
                utils.cambiar_carpeta_descarga(driver, carpeta)
                elegir_anio(driver, anios[anio])
                archivos = listar_archivos(driver)
                objetivos = elegir_objetivos(archivos)
                utils.log(f"ESCALE {anio}: {len(archivos)} archivos en el portal, {len(objetivos)} seleccionados")
                if not objetivos:
                    resultado["anios_sin_archivos"].append(anio)
                for nombre, enlace in objetivos.items():
                    descargar_archivo(driver, carpeta, anio, nombre, enlace, forzar, resultado)
                    utils.pausa()
            except Exception as error:   # un anio que falla no detiene a los demas
                utils.log(f"ESCALE {anio}: fallo el anio completo: {type(error).__name__} {error}")
                utils.captura(driver, f"error_escale_anio_{anio}")
                resultado["errores"].append((f"{anio} (anio completo)", type(error).__name__))
    finally:
        driver.quit()
    return resultado
