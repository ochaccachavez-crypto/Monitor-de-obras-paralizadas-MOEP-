"""Contraloria (gob.pe): descarga los informes de obras paralizadas y sus anexos (PDF y Excel)."""
import re
import time
from datetime import date

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

import config
import utils

NOMBRE_MES = {1: "enero", 2: "febrero", 3: "marzo", 4: "abril", 5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
              9: "setiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"}
MESES = "|".join(config.CGR_MESES)

# JavaScript: para cada boton "Descargar" devuelve su enlace y las lineas del bloque (etiqueta, formato, tamano)
JS_ARCHIVOS = """
return Array.from(document.querySelectorAll('main a'))
  .filter(a => (a.textContent || '').trim() === 'Descargar' && (a.href || '').includes('/uploads/'))
  .map(a => {
    let bloque = a;
    for (let i = 0; i < 6; i++) {
      bloque = bloque.parentElement;
      if (!bloque) break;
      const veces = (bloque.innerText.match(/Descargar/g) || []).length;
      const lineas = bloque.innerText.split('\\n').filter(x => x.trim());
      if (veces === 1 && lineas.length >= 3) break;
    }
    const lineas = bloque ? bloque.innerText.split('\\n').map(x => x.trim()).filter(x => x) : [];
    return {url: a.href, lineas: lineas};
  });
"""


def esperar(driver):
    return WebDriverWait(driver, config.ESPERA_ELEMENTO)


# ---------------- ruta de clics y listado ----------------
def abrir_portal(driver):
    driver.get(config.CGR_URL_PORTAL)
    esperar(driver).until(EC.presence_of_element_located((By.LINK_TEXT, config.CGR_TEXTO_CATEGORIA)))


def abrir_compendio(driver):
    """Portal > categoria 'Resultados de la Contraloria' > compendio 'Obras paralizadas - Documentos'."""
    utils.hacer_clic(driver, driver.find_element(By.LINK_TEXT, config.CGR_TEXTO_CATEGORIA))
    compendio = esperar(driver).until(EC.presence_of_element_located((By.LINK_TEXT, config.CGR_TEXTO_COMPENDIO)))
    utils.hacer_clic(driver, compendio)
    esperar(driver).until(EC.presence_of_element_located((By.ID, config.CGR_ID_POR_PAGINA)))


def mostrar_todos(driver):
    """Elige '100 por pagina' para ver la coleccion completa sin pasar a las paginas siguientes.

    Si la coleccion cabe en una pagina (hasta 25 resultados) esa opcion viene desactivada y no hace falta.
    """
    lista = Select(driver.find_element(By.ID, config.CGR_ID_POR_PAGINA))
    opcion = next(o for o in lista.options if o.text.strip() == config.CGR_OPCION_POR_PAGINA)
    if opcion.is_enabled():
        lista.select_by_visible_text(config.CGR_OPCION_POR_PAGINA)
        time.sleep(4)
    else:
        utils.log("CONTRALORIA: la coleccion cabe en una sola pagina; no hace falta cambiar 'por pagina'")
    esperar(driver).until(EC.presence_of_element_located((By.CSS_SELECTOR, f"main a[href*='{config.CGR_HREF_FICHA}']")))


def total_resultados(driver):
    """Numero de resultados que anuncia la pagina ('25 resultados:'); None si no se encuentra."""
    m = re.search(r"([\d.,]+) resultados", driver.find_element(By.TAG_NAME, "main").text)
    return int(re.sub(r"\D", "", m.group(1))) if m else None


def listar_items(driver):
    """Devuelve [(titulo, enlace_de_la_ficha)] de la coleccion, en el orden en que aparecen."""
    items = []
    for a in driver.find_elements(By.CSS_SELECTOR, f"main a[href*='{config.CGR_HREF_FICHA}']"):
        titulo = " ".join((a.text or "").split())
        href = a.get_attribute("href")
        if titulo and (titulo, href) not in items:
            items.append((titulo, href))
    return items


# ---------------- lectura de cada ficha ----------------
def fecha_en_texto(texto):
    """Primera fecha 'D de mes de AAAA' (o 'del AAAA') que aparece en el texto."""
    m = re.search(rf"(\d{{1,2}}) de ({MESES}) de(?:l)? (\d{{4}})", texto, re.I)
    return date(int(m.group(3)), config.CGR_MESES[m.group(2).lower()], int(m.group(1))) if m else None


def fecha_de_corte(titulo, descripcion):
    """Fecha de corte del informe: fin del mes o trimestre que dice el titulo; si no, una fecha 'al D de mes de AAAA' del texto."""
    m = re.search(rf"\ba (?:{MESES}) (?:de )?\d{{4}}", titulo, re.I)
    if m:
        mes, anio = re.search(rf"({MESES}) (?:de )?(\d{{4}})", m.group(0), re.I).groups()
        mes = config.CGR_MESES[mes.lower()]
        return date(int(anio), mes, [31, 29 if int(anio) % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1])
    m = re.search(r"\b(I{1,3}|IV) trimestre (?:de )?(\d{4})", titulo, re.I)
    if m:
        mes, dia = config.CGR_TRIMESTRES[m.group(1).lower()]
        return date(int(m.group(2)), mes, dia)
    m = re.search(rf"\bal (\d{{1,2}}) de ({MESES}) de(?:l)? (\d{{4}})", descripcion, re.I)
    if m:
        return date(int(m.group(3)), config.CGR_MESES[m.group(2).lower()], int(m.group(1)))
    return None


def leer_ficha(driver, enlace):
    """Abre la ficha de un informe y devuelve titulo, fecha de publicacion, fecha de corte y sus archivos."""
    driver.get(enlace)
    esperar(driver).until(EC.presence_of_element_located((By.CSS_SELECTOR, "main h1, main h2")))
    time.sleep(2)
    texto = driver.find_element(By.TAG_NAME, "main").text
    lineas = [l.strip() for l in texto.splitlines() if l.strip()]
    titulo = next((l for l in lineas if re.match(config.CGR_REGEX_INFORME, l)), lineas[1] if len(lineas) > 1 else "")
    archivos = []
    for a in driver.execute_script(JS_ARCHIVOS):
        archivos.append({"url": a["url"], "etiqueta": a["lineas"][0] if a["lineas"] else "",
                         "formato": a["lineas"][1].lower() if len(a["lineas"]) > 1 else "",
                         "tamano": a["lineas"][2] if len(a["lineas"]) > 2 else ""})
    return {"titulo": titulo, "publicacion": fecha_en_texto(texto), "corte": fecha_de_corte(titulo, texto), "archivos": archivos}


def descripcion_archivo(archivo, ficha):
    """Nombre corto del archivo: 'informe' o 'anexo_NN', mas el periodo de corte (ej. informe_obras_paralizadas_junio_2026)."""
    m = re.search(r"anexo\s*n?\.?\s*[°º]?\s*(\d+)", archivo["etiqueta"], re.I)
    base = f"anexo_{int(m.group(1)):02d}" if m else "informe"
    fecha = ficha["corte"] or ficha["publicacion"]
    periodo = f"{NOMBRE_MES[fecha.month]}_{fecha.year}" if fecha else "sin_fecha"
    return f"{base}_obras_paralizadas_{periodo}"


# ---------------- descarga ----------------
def descargar_archivo(driver, ficha, archivo, enlace_ficha, forzar, resultado):
    anio = (ficha["corte"] or ficha["publicacion"]).year
    carpeta = config.RAW / "contraloria" / str(anio)
    carpeta.mkdir(parents=True, exist_ok=True)
    extension = "." + archivo["formato"]
    extensiones = (".xlsx", ".xls") if archivo["formato"] in ("xlsx", "xls") else (extension,)
    nombre = descripcion_archivo(archivo, ficha) + extension
    filtros = f"gob.pe > Contraloría > {config.CGR_TEXTO_COMPENDIO} > {ficha['titulo']} > {archivo['etiqueta']}"
    if not forzar and utils.ya_descargado("contraloria", anio, filtros):
        utils.log(f"CONTRALORIA {anio}: {nombre} ya estaba descargado, se omite")
        utils.registrar_omitido("contraloria", anio, nombre, filtros)
        resultado["omitidos"].append(nombre)
        return
    id_archivo = re.search(r"/file/(\d+)/", archivo["url"]).group(1)
    motivo = ""
    for intento in range(1, config.REINTENTOS + 1):
        try:
            utils.cambiar_carpeta_descarga(driver, carpeta)
            utils.limpiar_parciales(carpeta)
            boton = esperar(driver).until(EC.presence_of_element_located(
                (By.XPATH, f"//main//a[contains(@href, '/file/{id_archivo}/') and normalize-space(.)='Descargar']")))
            antes = utils.archivos_actuales(carpeta)
            utils.hacer_clic(driver, boton)
            descargado = utils.esperar_descarga(carpeta, antes, extensiones)
            nombre_real = descripcion_archivo(archivo, ficha) + utils.extension_real(descargado)
            corte = ficha["corte"].isoformat() if ficha["corte"] else "no confirmado"
            destino, mb = utils.guardar_descarga(
                descargado, carpeta, "contraloria", anio, nombre_real, archivo["url"], filtros, fecha_corte=corte,
                notas=f"publicado {ficha['publicacion']}; ficha {enlace_ficha}")
            utils.log(f"CONTRALORIA {anio}: descargado {destino.name} ({mb} MB)")
            resultado["descargados"].append((destino.name, mb))
            return
        except (TimeoutException, TimeoutError, WebDriverException, ValueError) as error:
            motivo = type(error).__name__
            utils.log(f"CONTRALORIA {anio}: intento {intento}/{config.REINTENTOS} fallo para {nombre}: {motivo}")
            utils.captura(driver, f"error_contraloria_{anio}_{utils.nombre_limpio(nombre)}_intento{intento}")
            utils.pausa()
    utils.registrar_error("contraloria", anio, nombre, filtros, motivo)
    resultado["errores"].append((f"{anio} {nombre}", motivo))


def ejecutar(anio_inicio=config.ANIO_INICIO, forzar=False, headless=False):
    resultado = utils.nuevo_resultado("CONTRALORIA")
    driver = utils.crear_navegador(config.RAW / "contraloria", headless)
    try:
        try:
            abrir_portal(driver)
            abrir_compendio(driver)
            mostrar_todos(driver)
            items = listar_items(driver)
            anunciados = total_resultados(driver)
            if anunciados is not None and anunciados != len(items):
                utils.log(f"AVISO CONTRALORIA: la pagina anuncia {anunciados} resultados y se leyeron {len(items)}; la lista puede estar incompleta")
                resultado["errores"].append(("lista incompleta", f"{anunciados} anunciados, {len(items)} leidos"))
        except (TimeoutException, WebDriverException) as error:
            utils.log(f"CONTRALORIA: el portal no responde o cambio de estructura ({type(error).__name__}). Se omite la fuente.")
            utils.captura(driver, "error_contraloria_portal")
            resultado["errores"].append(("portal", type(error).__name__))
            return resultado

        informes = [i for i in items if re.search(config.CGR_REGEX_INFORME, i[0])]
        otros = [i for i in items if i not in informes]
        utils.log(f"CONTRALORIA: {len(items)} entradas en el compendio: {len(informes)} informes/reportes y {len(otros)} de otro tipo")
        for titulo, enlace in otros:
            utils.registrar_fuente(fuente="contraloria", url=enlace, archivo=titulo, filtros_usados=f"gob.pe > {config.CGR_TEXTO_COMPENDIO} > {titulo}",
                                   fecha_descarga=str(date.today()), estado="omitido", notas="no es un informe de obras paralizadas (infografia, presentacion u otro): no se descarga")

        cortes = set()
        for titulo, enlace in informes:
            try:
                ficha = leer_ficha(driver, enlace)
                fecha_ref = ficha["publicacion"] or ficha["corte"]
                if fecha_ref and fecha_ref.year < anio_inicio:
                    utils.log(f"CONTRALORIA: '{titulo}' es anterior a {anio_inicio}, se omite")
                    continue
                if not ficha["archivos"]:
                    utils.log(f"CONTRALORIA: '{titulo}' no tiene archivos descargables")
                    resultado["errores"].append((titulo, "sin archivos en la ficha"))
                    continue
                if ficha["corte"]:
                    cortes.add(ficha["corte"].year)
                utils.log(f"CONTRALORIA: {titulo} | corte {ficha['corte']} | publicado {ficha['publicacion']} | "
                          f"{', '.join(a['formato'].upper() for a in ficha['archivos'])}")
                for archivo in ficha["archivos"]:
                    descargar_archivo(driver, ficha, archivo, enlace, forzar, resultado)
                    utils.pausa()
            except Exception as error:   # una ficha que falla no detiene a las demas
                utils.log(f"CONTRALORIA: fallo la ficha '{titulo}': {type(error).__name__} {error}")
                utils.captura(driver, f"error_contraloria_ficha_{utils.nombre_limpio(titulo)[:40]}")
                resultado["errores"].append((titulo, type(error).__name__))
        resultado["anios_encontrados"] = sorted(cortes)
        if cortes:
            resultado["anios_faltantes"] = [a for a in range(min(cortes), max(cortes) + 1) if a not in cortes]
    finally:
        driver.quit()
    return resultado
