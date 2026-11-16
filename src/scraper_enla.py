"""ENLA (UMC): descubre las paginas de resultados de cada anio y descarga los PDF de reportes."""
import json
import os
import re
import time
from urllib.parse import unquote, urlparse

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

import config
import utils


def esperar(driver):
    return WebDriverWait(driver, config.ESPERA_ELEMENTO)


def abrir_portal(driver):
    driver.get(config.ENLA_URL_INICIO)
    esperar(driver).until(EC.presence_of_element_located((By.TAG_NAME, "a")))


def listar_anios(driver):
    """Devuelve {anio: (etiqueta, enlace)} leyendo los enlaces 'Resultados ...' del portal."""
    anios = {}
    for enlace in driver.find_elements(By.TAG_NAME, "a"):
        m = re.search(config.ENLA_REGEX_PAGINA_ANIO, enlace.get_attribute("href") or "")
        if m:
            anio = int(m.group(2))
            anios.setdefault(anio, (f"{m.group(1).upper()} {anio}", enlace.get_attribute("href")))
    return anios


def elegir_anio(driver, enlace_anio):
    driver.get(enlace_anio)
    esperar(driver).until(EC.presence_of_element_located((By.TAG_NAME, "a")))


def listar_pdfs(driver):
    """Devuelve {nombre_pdf: enlace} con los PDF de la pagina, sin catalogo, infografias ni normas."""
    pdfs = {}
    for enlace in driver.find_elements(By.TAG_NAME, "a"):
        href = enlace.get_attribute("href") or ""
        if re.search(config.ENLA_REGEX_PDF, href, re.I) and not re.search(config.ENLA_EXCLUIR, href):
            pdfs.setdefault(unquote(os.path.basename(urlparse(href).path)), href)
    return pdfs


def descargar_pdf(driver, carpeta, anio, etiqueta, nombre, href, forzar, resultado):
    filtros = f"Resultados {etiqueta} > {nombre}"
    if not forzar and utils.ya_descargado("enla", anio, filtros):
        utils.log(f"ENLA {anio}: {nombre} ya estaba descargado, se omite")
        utils.registrar_omitido("enla", anio, nombre, filtros)
        resultado["omitidos"].append(nombre)
        return
    nombre_en_url = os.path.basename(urlparse(href).path)   # tal como aparece en el enlace (con %)
    motivo = ""
    for intento in range(1, config.REINTENTOS + 1):
        try:
            utils.limpiar_parciales(carpeta)
            xpath = config.ENLA_XPATH_ENLACE_PDF.format(codificado=nombre_en_url, decodificado=nombre)
            enlace = esperar(driver).until(EC.presence_of_element_located((By.XPATH, xpath)))
            antes = utils.archivos_actuales(carpeta)
            utils.hacer_clic(driver, enlace)
            descargado = utils.esperar_descarga(carpeta, antes, ".pdf")
            destino, mb = utils.guardar_descarga(descargado, carpeta, "enla", anio, nombre, href, filtros)
            utils.log(f"ENLA {anio}: descargado {destino.name} ({mb} MB)")
            resultado["descargados"].append((destino.name, mb))
            return
        except (TimeoutException, TimeoutError, WebDriverException, ValueError) as error:
            motivo = f"{type(error).__name__}"
            utils.log(f"ENLA {anio}: intento {intento}/{config.REINTENTOS} fallo para {nombre}: {motivo}")
            utils.captura(driver, f"error_enla_{anio}_{utils.nombre_limpio(nombre)}_intento{intento}")
            utils.pausa()
    utils.registrar_error("enla", anio, nombre, filtros, motivo)
    resultado["errores"].append((f"{anio} {nombre}", motivo))


def ejecutar_umc(resultado, anio_inicio, forzar, headless):
    """PDF de reportes de la UMC."""
    driver = utils.crear_navegador(config.RAW / "enla", headless, origen_http=config.ENLA_ORIGEN_HTTP)
    try:
        try:
            abrir_portal(driver)
            anios = listar_anios(driver)
        except (TimeoutException, WebDriverException) as error:
            utils.log(f"ENLA: el portal no responde o cambio de estructura ({type(error).__name__}). Se omite la fuente.")
            utils.captura(driver, "error_enla_portal")
            resultado["errores"].append(("portal", type(error).__name__))
            return

        disponibles = sorted(a for a in anios if a >= anio_inicio)
        resultado["anios_encontrados"] = disponibles
        if anios:
            resultado["anios_faltantes"] = [a for a in range(anio_inicio, max(anios) + 1) if a not in anios]
        utils.log(f"ENLA: anios con pagina de resultados desde {anio_inicio}: {disponibles}")

        for anio in disponibles:
            try:
                etiqueta, enlace_anio = anios[anio]
                carpeta = config.RAW / "enla" / str(anio)
                utils.cambiar_carpeta_descarga(driver, carpeta)
                elegir_anio(driver, enlace_anio)
                pdfs = listar_pdfs(driver)
                utils.log(f"ENLA {anio} ({etiqueta}): {len(pdfs)} PDF de reportes encontrados")
                if not pdfs:
                    resultado["anios_sin_archivos"].append(anio)
                for nombre, href in pdfs.items():
                    descargar_pdf(driver, carpeta, anio, etiqueta, nombre, href, forzar, resultado)
                    utils.pausa()
            except Exception as error:   # un anio que falla no detiene a los demas
                utils.log(f"ENLA {anio}: fallo el anio completo: {type(error).__name__} {error}")
                utils.captura(driver, f"error_enla_anio_{anio}")
                resultado["errores"].append((f"{anio} (anio completo)", type(error).__name__))
    finally:
        driver.quit()


# ---------------- SICRECE (acceso publico): resultados por region ----------------
def abrir_sicrece(driver):
    """Entra por ACCESO PUBLICO con el rol autorizado (sin credenciales) y abre la Busqueda avanzada."""
    driver.get(config.SICRECE_URL)
    esperar(driver).until(EC.element_to_be_clickable((By.XPATH, config.SICRECE_XPATH_ACCESO_PUBLICO))).click()
    esperar(driver).until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, f"{config.SICRECE_SELECT_ROL} option[value='{config.SICRECE_ROL_VALOR}']")))
    Select(driver.find_element(By.CSS_SELECTOR, config.SICRECE_SELECT_ROL)).select_by_value(config.SICRECE_ROL_VALOR)
    esperar(driver).until(EC.element_to_be_clickable((By.ID, config.SICRECE_BOTON_INGRESAR))).click()
    pestana = esperar(driver).until(EC.presence_of_element_located(
        (By.XPATH, f"//*[normalize-space(text())='{config.SICRECE_PESTANA_BUSQUEDA}']")))
    utils.hacer_clic(driver, pestana)
    esperar(driver).until(lambda d: len(selects_formulario(d)) >= 2)


def cuerpo_activo(driver):
    return [c for c in driver.find_elements(By.CSS_SELECTOR, "mat-tab-body")
            if "mat-tab-body-active" in (c.get_attribute("class") or "")][0]


def selects_formulario(driver):
    """Listas desplegables visibles del formulario (sin la lista de anios de la tarjeta del grafico)."""
    return [s for s in cuerpo_activo(driver).find_elements(By.TAG_NAME, "select")
            if s.is_displayed() and not driver.execute_script("return !!arguments[0].closest('app-horizontal-bar-chart')", s)]


def elegir_opcion(driver, campo, texto):
    """Espera a que la opcion exista (se carga despues del filtro anterior) y la elige. False si no existe."""
    posicion = config.SICRECE_ORDEN_SELECTS[campo]
    try:
        WebDriverWait(driver, 10).until(lambda d: len(selects_formulario(d)) > posicion and texto in
                                        [o.text.strip() for o in Select(selects_formulario(d)[posicion]).options])
    except TimeoutException:
        return False
    Select(selects_formulario(driver)[posicion]).select_by_visible_text(texto)
    time.sleep(1.5)
    return True


def opciones_de(driver, campo):
    posicion = config.SICRECE_ORDEN_SELECTS[campo]
    esperar(driver).until(lambda d: len(selects_formulario(d)) > posicion)
    time.sleep(1.5)
    return [o.text.strip() for o in Select(selects_formulario(driver)[posicion]).options if o.text.strip() != "SELECCIONAR"]


def marcar_casilla(driver, texto):
    """Marca la casilla con ese texto si no esta marcada (idempotente)."""
    esperar(driver).until(lambda d: any(" ".join(c.text.split()) == texto
                                        for c in cuerpo_activo(d).find_elements(By.TAG_NAME, "mat-checkbox")))
    casilla = [c for c in cuerpo_activo(driver).find_elements(By.TAG_NAME, "mat-checkbox") if " ".join(c.text.split()) == texto][0]
    if not casilla.find_element(By.CSS_SELECTOR, "input").is_selected():
        utils.hacer_clic(driver, casilla.find_element(By.CSS_SELECTOR, "label"))
        time.sleep(0.5)


def elegir_todas_las_dre(driver):
    desplegable = esperar(driver).until(lambda d: next(iter([m for m in cuerpo_activo(d).find_elements(By.TAG_NAME, "mat-select")
                                                             if m.is_displayed()][-1:]), False))
    utils.hacer_clic(driver, desplegable)
    opcion = esperar(driver).until(EC.presence_of_element_located(
        (By.XPATH, f"//div[contains(@class,'cdk-overlay-container')]//mat-option[normalize-space(.)='{config.SICRECE_DRE_TODAS}']")))
    if opcion.get_attribute("aria-selected") != "true":   # si ya estaba marcada, pulsarla la desmarcaria
        utils.hacer_clic(driver, opcion)
    time.sleep(1)
    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
    time.sleep(1)
    esperar(driver).until(lambda d: "(+" in " ".join(" ".join(m.text for m in cuerpo_activo(d).find_elements(By.TAG_NAME, "mat-select")).split()))   # "DRE Amazonas (+25)" = las 26 DRE


def consultar(driver, tipo, anio, nivel, grado):
    """Rellena el formulario, pulsa Buscar y devuelve el JSON que recibe la pagina (texto)."""
    elegir_opcion(driver, "tipo", tipo)
    elegir_opcion(driver, "anio", str(anio))
    elegir_opcion(driver, "nivel", nivel)
    elegir_opcion(driver, "grado", grado)
    for area in config.SICRECE_AREAS:
        marcar_casilla(driver, area)
    marcar_casilla(driver, config.SICRECE_AMBITO)
    elegir_todas_las_dre(driver)
    utils.limpiar_registro_red(driver)
    boton = driver.find_element(By.XPATH, config.SICRECE_BOTON_BUSCAR)
    utils.hacer_clic(driver, boton)
    return utils.respuesta_post(driver, config.SICRECE_API_REPORTE[tipo])


def combinaciones_sicrece(driver, anio_inicio):
    """Recorre tipo > anio > nivel > grado y devuelve las combinaciones de (tipo, anio, nivel, grado) que interesan."""
    encontradas, anios_vistos = [], set()
    for tipo in config.SICRECE_TIPOS:
        elegir_opcion(driver, "tipo", tipo)
        for anio in [int(a) for a in opciones_de(driver, "anio") if a.isdigit() and int(a) >= anio_inicio]:
            anios_vistos.add(anio)
            elegir_opcion(driver, "anio", str(anio))
            for nivel in opciones_de(driver, "nivel"):
                elegir_opcion(driver, "nivel", nivel)
                for grado in opciones_de(driver, "grado"):
                    if (nivel, grado) in config.SICRECE_GRADOS and (tipo, anio, nivel, grado) not in config.SICRECE_SIN_RESPUESTA:
                        encontradas.append((tipo, anio, nivel, grado))
    return encontradas, sorted(anios_vistos)


def guardar_respuesta(texto, carpeta, anio, tipo, nivel, grado, filtros):
    """Guarda el JSON recibido como archivo crudo y lo registra."""
    json.loads(texto)   # debe ser JSON valido
    temporal = carpeta / "_sicrece_temporal.json"
    temporal.write_text(texto, encoding="utf-8")
    nombre_logico = f"sicrece_{tipo}_{nivel}_{grado}.json".lower()
    destino, mb = utils.guardar_descarga(temporal, carpeta, "enla", anio, nombre_logico, config.SICRECE_API_REPORTE[tipo], filtros)
    return destino, mb


def ejecutar_sicrece(resultado, anio_inicio, forzar, headless):
    carpeta_base = config.RAW / "enla"
    driver = utils.crear_navegador(carpeta_base, headless, registrar_red=True)
    try:
        try:
            abrir_sicrece(driver)
            combinaciones, anios = combinaciones_sicrece(driver, anio_inicio)
        except (TimeoutException, WebDriverException) as error:
            utils.log(f"SICRECE: el portal no responde o cambio de estructura ({type(error).__name__}). Se omite.")
            utils.captura(driver, "error_sicrece_portal")
            resultado["errores"].append(("SICRECE portal", type(error).__name__))
            return
        utils.log(f"SICRECE: anios {anios}; {len(combinaciones)} combinaciones de interes: {combinaciones}")
        for tipo, anio, nivel, grado in combinaciones:
            filtros = f"SICRECE > {tipo} > {anio} > {nivel} > {grado} > {'+'.join(config.SICRECE_AREAS)} > {config.SICRECE_AMBITO} {config.SICRECE_DRE_TODAS}"
            nombre = f"sicrece_{tipo}_{nivel}_{grado}".lower()
            carpeta = carpeta_base / str(anio)
            carpeta.mkdir(parents=True, exist_ok=True)
            if not forzar and utils.ya_descargado("enla", anio, filtros):
                utils.log(f"SICRECE {anio}: {tipo} {nivel} {grado} ya estaba descargado, se omite")
                utils.registrar_omitido("enla", anio, nombre, filtros)
                resultado["omitidos"].append(nombre)
                continue
            motivo = ""
            for intento in range(1, config.REINTENTOS + 1):
                try:
                    texto = consultar(driver, tipo, anio, nivel, grado)
                    destino, mb = guardar_respuesta(texto, carpeta, anio, tipo, nivel, grado, filtros)
                    utils.log(f"SICRECE {anio}: guardado {destino.name} ({mb} MB)")
                    resultado["descargados"].append((destino.name, mb))
                    break
                except Exception as error:
                    motivo = type(error).__name__
                    utils.log(f"SICRECE {anio}: intento {intento}/{config.REINTENTOS} fallo para {tipo} {nivel} {grado}: {motivo} {str(error)[:120]}")
                    utils.captura(driver, f"error_sicrece_{anio}_{tipo}_{nivel}_{grado}_intento{intento}".lower())
                    utils.pausa()
            else:
                utils.registrar_error("enla", anio, nombre, filtros, motivo)
                resultado["errores"].append((f"{anio} SICRECE {tipo} {nivel} {grado}", motivo))
            utils.pausa()
    finally:
        driver.quit()


def ejecutar(anio_inicio=config.ANIO_INICIO, forzar=False, headless=False):
    resultado = utils.nuevo_resultado("ENLA")
    for paso in (ejecutar_umc, ejecutar_sicrece):
        try:
            paso(resultado, anio_inicio, forzar, headless)
        except Exception as error:   # si un paso falla se sigue con el otro
            utils.log(f"ENLA: {paso.__name__} fallo: {type(error).__name__} {error}")
            resultado["errores"].append((paso.__name__, type(error).__name__))
    return resultado
