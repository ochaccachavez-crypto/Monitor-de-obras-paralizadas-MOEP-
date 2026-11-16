"""INFOBRAS (Contraloria): listado de obras educativas paralizadas y lectura de la ficha publica de cada obra.

No se leen los datos de preparacion (residente e inspector) para no guardar nombres de personas.
"""
import re
import time
from datetime import date

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

import config
import utils


def esperar(driver, segundos=None):
    return WebDriverWait(driver, segundos or config.ESPERA_ELEMENTO)


# ---------------- listado: buscador avanzado y exportacion a CSV ----------------
def abrir_buscador(driver):
    """Abre el buscador avanzado y espera a que el sistema llene las listas del formulario (a veces tarda)."""
    driver.get(config.INFOBRAS_URL_BUSCADOR)
    esperar(driver, 90).until(lambda d: len(Select(d.find_element(By.ID, config.INFOBRAS_ID_NIVEL1)).options) > 1)
    time.sleep(3)


JS_FILTRAR = """
const [filtros] = arguments;
const resultado = {};
for (const [id, texto] of Object.entries(filtros)) {
  const lista = document.getElementById(id);
  const opcion = Array.from(lista.options).find(o => o.text.trim().toLowerCase().includes(texto));
  if (!opcion) { resultado[id] = null; continue; }
  lista.value = opcion.value;
  lista.dispatchEvent(new Event('change', {bubbles: true}));
  if (window.jQuery) { jQuery(lista).val(opcion.value).trigger('change'); if (jQuery(lista).selectpicker) jQuery(lista).selectpicker('refresh'); }
  resultado[id] = opcion.text.trim();
}
return resultado;
"""

JS_BUSCAR = """
const boton = Array.from(document.querySelectorAll('button')).find(b =>
  /^buscar$/i.test((b.innerText || '').trim()) && b.offsetParent !== null && b.id !== arguments[0]);
boton.scrollIntoView({block: 'center'}); boton.click();
"""


def aplicar_filtros_y_buscar(driver, filtros=None):
    elegidos = driver.execute_script(JS_FILTRAR, filtros or config.INFOBRAS_FILTROS)
    if None in elegidos.values():
        raise LookupError(f"no se encontro alguna opcion del filtro: {elegidos}")
    utils.log(f"INFOBRAS: filtros aplicados {elegidos}")
    time.sleep(3)
    driver.execute_script(JS_BUSCAR, config.INFOBRAS_ID_BOTON_BASICO)
    esperar(driver, 60).until(EC.presence_of_element_located((By.ID, config.INFOBRAS_ID_EXPORTAR_CSV)))
    time.sleep(3)


# ---------------- lectura de una ficha ----------------
def lineas_de_pagina(driver):
    return [l.strip() for l in driver.find_element(By.TAG_NAME, "body").text.splitlines() if l.strip()]


def esperar_carga(driver, segundos=12):
    """La ficha dice «Cargando coordenadas...» y las rellena con JavaScript 1 a 3 s despues: se espera a que desaparezca."""
    limite = time.time() + segundos
    while time.time() < limite:
        if "cargando" not in driver.find_element(By.TAG_NAME, "body").text.lower():
            return
        time.sleep(0.5)


def abrir_pagina(driver, nombre, parametro, codigo):
    driver.get(f"{config.INFOBRAS_BASE}/Mapa/{nombre}?{parametro}={codigo}")
    esperar(driver).until(lambda d: d.execute_script("return document.readyState") == "complete")
    esperar(driver).until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'FICHA DE OBRA')]")))
    esperar_carga(driver)
    return lineas_de_pagina(driver)


def avance_fisico_estable(driver):
    """El porcentaje de avance del encabezado es un contador animado (sube de 0 al valor final):
    se espera a que dos lecturas seguidas den lo mismo antes de guardarlo."""
    anterior, actual = None, None
    for _ in range(15):
        actual = numero(valor(lineas_de_pagina(driver), "PORCENTAJE DE AVANCE FÍSICO"))
        if actual is not None and actual == anterior:
            return actual
        anterior = actual
        time.sleep(1.2)
    return actual


def valor(lineas, etiqueta):
    """Texto de la linea que sigue a la etiqueta (las fichas escriben 'ETIQUETA' y debajo su valor)."""
    for i, linea in enumerate(lineas[:-1]):
        if linea.upper() == etiqueta.upper():
            return lineas[i + 1]
    return None


def numero(texto):
    """'S/ 1,213,383.66' -> 1213383.66 ; '5.32%' -> 5.32 ; vacio o sin dato -> None."""
    if not isinstance(texto, str) or not texto.strip():   # vacio, None o NaN (celda vacia del CSV exportado)
        return None
    m = re.search(r"-?\d[\d,]*\.?\d*", texto)
    return float(m.group(0).replace(",", "")) if m else None


def fecha(texto):
    """'01/09/2026' -> '2026-09-01' ; sin fecha -> None."""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", (texto or "").strip())
    return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}" if m else None


def periodo(texto):
    """'2026 / SEPTIEMBRE' -> (2026, 9); no reconocido -> (0, 0)."""
    m = re.match(r"(\d{4})\s*/\s*([A-Za-zÁÉÍÓÚáéíóú]+)", (texto or "").strip())
    return (int(m.group(1)), config.INFOBRAS_MESES.get(m.group(2).lower(), 0)) if m else (0, 0)


def leer_avances(driver):
    """Tabla 'Avances de obra' de la pagina de ejecucion: lista de dicts con periodo, avances, estado y enlace al detalle."""
    avances = []
    for tabla in driver.find_elements(By.TAG_NAME, "table"):
        if "AVANCE FÍSICO" not in tabla.text.upper():
            continue
        for fila in tabla.find_elements(By.CSS_SELECTOR, "tbody tr"):
            celdas = [c.text.strip() for c in fila.find_elements(By.TAG_NAME, "td")]
            enlaces = [a.get_attribute("href") for a in fila.find_elements(By.TAG_NAME, "a") if "Avance?codigo=" in (a.get_attribute("href") or "")]
            enlaces += [f"{config.INFOBRAS_BASE}/Mapa/Avance?codigo={b.get_attribute('data-codigo')}"   # otras fichas usan un boton
                        for b in fila.find_elements(By.CSS_SELECTOR, "button[data-codigo]")]
            if len(celdas) >= 9 and periodo(celdas[1]) != (0, 0):
                avances.append({"periodo": celdas[1], "fisico_programado": numero(celdas[2]), "fisico_real": numero(celdas[3]),
                                "estado": celdas[8], "enlace": enlaces[0] if enlaces else None})
    return avances


def leer_detalle_avance(driver, enlace):
    """Pagina de detalle de un avance: causal, fecha de paralizacion, dias paralizado y comentarios."""
    driver.get(enlace)
    esperar(driver).until(EC.presence_of_element_located((By.XPATH, "//*[contains(text(),'DETALLE DE AVANCE')]")))
    lineas = [l.strip() for l in driver.find_element(By.TAG_NAME, "body").text.splitlines() if l.strip()]
    comentario = lambda inicio: next((l.split(":", 1)[1].strip() for l in lineas if l.lower().startswith(inicio)), None)
    return {"causal_paralizacion": valor(lineas, "CAUSAL"), "fecha_paralizacion": fecha(valor(lineas, "FECHA DE PARALIZACIÓN")),
            "dias_paralizado": numero(valor(lineas, "DÍAS PARALIZADO")),
            "comentario_fisico": utils.omitir_nombres(comentario("comentario físico")),
            "comentario_valorizado": utils.omitir_nombres(comentario("comentario valorizado"))}


def leer_ficha(driver, codigo):
    """Lee las paginas Datos generales, Datos de ejecucion y el detalle del ultimo avance paralizado de una obra."""
    return _leer_ficha(driver, codigo)[0]


def _leer_ficha(driver, codigo):
    """Lo mismo que leer_ficha, pero devuelve tambien lo que la pasada ampliada reutiliza:
    (fila, todos los avances, avance paralizado elegido, su detalle). Asi no se abre dos veces la misma pagina."""
    generales = abrir_pagina(driver, "DatosGenerales", "obraId", codigo)
    utils.pausa()
    ubicacion = (valor(generales, "UBICACIÓN GEOGRÁFICA") or "").split(" - ")   # DEPARTAMENTO - PROVINCIA - DISTRITO
    coordenadas = valor(generales, "COORDENADAS GEOGRÁFICAS") or ""
    lat = re.search(r"Latitud:\s*(-?[\d.]+)", coordenadas)
    lon = re.search(r"Longitud:\s*(-?[\d.]+)", coordenadas)
    fila = {
        "codigo_infobras": valor(generales, "CÓDIGO INFOBRAS"), "cui": valor(generales, "CÓDIGO ÚNICO DE INVERSIÓN"),
        "nombre_obra": valor(generales, "NOMBRE DE OBRA"), "entidad": valor(generales, "ENTIDAD RESPONSABLE DE LA OBRA"),
        "estado": valor(generales, "ESTADO DE OBRA"), "avance_fisico_pct": avance_fisico_estable(driver),
        "modalidad": valor(generales, "MODALIDAD DE EJECUCIÓN"), "naturaleza": valor(generales, "NATURALEZA"),
        "tipo_obra": valor(generales, "TIPO DE OBRA"),
        "departamento": ubicacion[0] if len(ubicacion) == 3 else None, "provincia": ubicacion[1] if len(ubicacion) == 3 else None,
        "distrito": ubicacion[2] if len(ubicacion) == 3 else None,
        "latitud": float(lat.group(1)) if lat else None, "longitud": float(lon.group(1)) if lon else None,
    }
    ejecucion = abrir_pagina(driver, "DatosEjecucion", "obraId", codigo)
    fila["monto_ejecucion_acumulado"] = numero(valor(ejecucion, "MONTO DE EJECUCIÓN ACUMULADO"))
    fila["fecha_inicio"] = fecha(valor(ejecucion, "FECHA DE INICIO DE LA OBRA"))
    fila["fecha_fin_prevista"] = fecha(valor(ejecucion, "FECHA DE FIN DE LA OBRA"))
    avances = leer_avances(driver)
    fila["n_avances"] = len(avances)
    ultimo = max(avances, key=lambda a: periodo(a["periodo"])) if avances else None
    fila["periodo_ultimo_avance"] = ultimo["periodo"] if ultimo else None
    fila["avance_fisico_tabla"] = ultimo["fisico_real"] if ultimo else None   # para cruzar con el del encabezado
    if ultimo and fila["avance_fisico_pct"] is not None and ultimo["fisico_real"] is not None \
            and abs(fila["avance_fisico_pct"] - ultimo["fisico_real"]) > 0.01:
        utils.log(f"AVISO INFOBRAS {codigo}: avance del encabezado {fila['avance_fisico_pct']} y de la tabla {ultimo['fisico_real']} no coinciden")
    paralizados = [a for a in avances if a["estado"].lower().startswith("paraliz") and a["enlace"]]
    elegido = max(paralizados, key=lambda a: periodo(a["periodo"])) if paralizados else None
    fila["periodo_avance_paralizado"] = elegido["periodo"] if elegido else None
    detalle = {"causal_paralizacion": None, "fecha_paralizacion": None, "dias_paralizado": None,
               "comentario_fisico": None, "comentario_valorizado": None}
    if elegido:
        utils.pausa()
        detalle = leer_detalle_avance(driver, elegido["enlace"])
    fila.update(detalle)
    fila["url_ficha"] = f"{config.INFOBRAS_BASE}/Mapa/Sumario?ObraId={codigo}"
    fila["fecha_lectura"] = str(date.today())
    return fila, avances, elegido, detalle


# ---------------- listado de las obras (CSV exportado) ----------------
def descargar_listado(driver, forzar=False, filtros_buscador=None, filtros_texto=None, nombre="listado_obras.csv"):
    """Busca Educacion + Paralizada (o los filtros indicados) y baja el CSV del buscador a data/raw/infobras/{anio}.
    Devuelve la ruta del CSV.

    El listado cambia con el tiempo (una obra se reanuda o se paraliza), por eso la fecha de hoy va en los filtros:
    el mismo dia no se vuelve a bajar; otro dia, si.
    """
    filtros_buscador = filtros_buscador or config.INFOBRAS_FILTROS
    filtros_texto = filtros_texto or config.INFOBRAS_FILTROS_TEXTO
    anio = date.today().year
    carpeta = config.RAW / "infobras" / str(anio)
    carpeta.mkdir(parents=True, exist_ok=True)
    filtros = f"{filtros_texto};{date.today()}"
    if not forzar and utils.ya_descargado("infobras", anio, filtros):
        csvs = sorted(carpeta.glob(f"infobras_{anio}_{utils.nombre_limpio(nombre)}_{date.today():%Y-%m-%d}.csv"))
        if csvs:
            utils.log(f"INFOBRAS: el listado de hoy ya estaba descargado ({csvs[-1].name})")
            utils.registrar_omitido("infobras", anio, csvs[-1].name, filtros)
            return csvs[-1]
    utils.cambiar_carpeta_descarga(driver, carpeta)
    utils.limpiar_parciales(carpeta)
    abrir_buscador(driver)
    aplicar_filtros_y_buscar(driver, filtros_buscador)
    antes = utils.archivos_actuales(carpeta)
    utils.hacer_clic(driver, driver.find_element(By.ID, config.INFOBRAS_ID_EXPORTAR_CSV))
    descargado = utils.esperar_descarga(carpeta, antes, ".csv")
    destino, mb = utils.guardar_descarga(descargado, carpeta, "infobras", anio, nombre,
                                         config.INFOBRAS_URL_BUSCADOR, filtros, fecha_corte=str(date.today()),
                                         notas="fecha de corte = dia de la descarga (INFOBRAS muestra el estado actual)")
    utils.log(f"INFOBRAS: listado descargado {destino.name} ({mb} MB)")
    return destino


def leer_listado(ruta):
    """Lee el CSV exportado: codigos INFOBRAS (texto) y el monto del expediente tecnico de cada obra."""
    import pandas as pd
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            tabla = pd.read_csv(ruta, dtype=str, encoding=codificacion)
            break
        except UnicodeDecodeError:
            continue
    tabla.columns = [c.strip().lower() for c in tabla.columns]
    col_codigo = next(c for c in tabla.columns if "infobras" in c)
    col_monto = next((c for c in tabla.columns if "monto" in c), None)
    col_estado = next((c for c in tabla.columns if "estado" in c), None)
    salida = pd.DataFrame({"codigo_infobras": tabla[col_codigo].str.strip()})
    salida["monto_listado"] = tabla[col_monto].map(numero) if col_monto else None
    salida["estado_listado"] = tabla[col_estado].str.strip() if col_estado else None
    salida = salida[salida.codigo_infobras.notna() & (salida.codigo_infobras != "")]   # filas sin codigo (vacias o de pie)
    return salida.drop_duplicates("codigo_infobras")


# ---------------- lectura de todas las fichas ----------------
def codigos_leidos():
    """Codigos con una ficha leida hace menos de config.INFOBRAS_DIAS_VIGENCIA dias (las mas viejas se vuelven a leer)."""
    if not config.INFOBRAS_FICHAS.exists():
        return set()
    import json
    from datetime import timedelta
    limite = str(date.today() - timedelta(days=config.INFOBRAS_DIAS_VIGENCIA))
    vigentes = set()
    with open(config.INFOBRAS_FICHAS, encoding="utf-8") as f:
        for linea in f:
            if linea.strip():
                ficha = json.loads(linea)
                if str(ficha.get("fecha_lectura", "")) >= limite:
                    vigentes.add(str(ficha["codigo_infobras"]))
    return vigentes


def guardar_ficha(fila):
    import json
    config.INFOBRAS_FICHAS.parent.mkdir(parents=True, exist_ok=True)
    with open(config.INFOBRAS_FICHAS, "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def leer_todas(driver, codigos, forzar=False):
    """Lee la ficha de cada codigo con pausas y hasta 3 intentos. Devuelve (leidas, omitidas, errores)."""
    if forzar:
        config.INFOBRAS_FICHAS.unlink(missing_ok=True)
    hechos = codigos_leidos()
    leidas, omitidas, errores = 0, 0, []
    from tqdm import tqdm
    for codigo in tqdm(codigos, desc="fichas INFOBRAS"):
        if str(codigo) in hechos:
            omitidas += 1
            continue
        for intento in range(1, config.REINTENTOS + 1):
            try:
                guardar_ficha(leer_ficha(driver, codigo))
                leidas += 1
                break
            except (TimeoutException, WebDriverException, ValueError) as e:
                utils.log(f"INFOBRAS {codigo}: intento {intento} fallo ({type(e).__name__}: {str(e)[:80]})")
                if intento == config.REINTENTOS:
                    errores.append((codigo, type(e).__name__))
                    utils.registrar_error("infobras", date.today().year, f"ficha_{codigo}", "ficha", e)
                else:
                    time.sleep(5 * intento)
        utils.pausa()
    return leidas, omitidas, errores


def sin_tildes_mayusculas(texto):
    import unicodedata
    if texto is None:
        return None
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().upper().strip()


def construir_csv(listado):
    """Une las fichas leidas con el listado, valida y guarda data/processed/fichas_infobras.csv (UTF-8)."""
    import json
    import pandas as pd
    with open(config.INFOBRAS_FICHAS, encoding="utf-8") as f:
        filas = [json.loads(l) for l in f if l.strip()]
    fichas = pd.DataFrame(filas).drop_duplicates("codigo_infobras", keep="last")
    fichas["codigo_infobras"] = fichas["codigo_infobras"].astype(str)
    for col in ("departamento", "provincia", "distrito"):
        fichas[col] = fichas[col].map(sin_tildes_mayusculas)
    fichas["departamento"] = fichas.departamento.map(lambda d: "CALLAO" if d and "CALLAO" in d else d)   # 'P. C. DEL CALLAO' -> CALLAO
    fichas["cod_departamento"] = fichas.departamento.map(config.DEPARTAMENTOS)   # codigo INEI de 2 digitos, como texto
    fichas = fichas[fichas.codigo_infobras.isin(listado.codigo_infobras)]   # solo las obras del listado vigente (otras ya no estan paralizadas)
    fichas = fichas.merge(listado, on="codigo_infobras", how="left")
    fichas = fichas.rename(columns={"monto_listado": "monto_expediente_tecnico"})
    fichas["fecha_corte"] = fichas["fecha_lectura"]
    orden = ["codigo_infobras", "cui", "nombre_obra", "entidad", "cod_departamento", "departamento", "provincia", "distrito", "estado",
             "modalidad", "naturaleza", "tipo_obra", "monto_expediente_tecnico", "monto_ejecucion_acumulado",
             "avance_fisico_pct", "fecha_inicio", "fecha_fin_prevista", "periodo_ultimo_avance", "n_avances",
             "periodo_avance_paralizado", "causal_paralizacion", "fecha_paralizacion", "dias_paralizado",
             "comentario_fisico", "comentario_valorizado", "latitud", "longitud", "avance_fisico_tabla",
             "estado_listado", "url_ficha", "fecha_lectura", "fecha_corte"]
    fichas = fichas[orden].sort_values("codigo_infobras")
    config.INFOBRAS_SALIDA.parent.mkdir(parents=True, exist_ok=True)
    fichas.to_csv(config.INFOBRAS_SALIDA, index=False, encoding="utf-8-sig")
    return fichas


def ejecutar(anio_inicio=None, forzar=False, headless=False):
    """(anio_inicio no se usa: INFOBRAS muestra solo el estado actual.) Descarga el listado, lee las fichas de las obras y arma fichas_infobras.csv. Devuelve el resultado de la corrida."""
    resultado = utils.nuevo_resultado("infobras")
    driver = utils.crear_navegador(config.RAW / "infobras", headless=headless)
    try:
        ruta = descargar_listado(driver, forzar)
        listado = leer_listado(ruta)
        utils.log(f"INFOBRAS: {len(listado)} obras en el listado")
        leidas, omitidas, errores = leer_todas(driver, list(listado["codigo_infobras"]), forzar)
    finally:
        driver.quit()
    fichas = construir_csv(listado)
    utils.log(f"INFOBRAS: fichas leidas {leidas}, omitidas {omitidas}, con error {len(errores)}; filas en el CSV final {len(fichas)}")
    resultado["descargados"] = [f"ficha_{c}" for c in fichas["codigo_infobras"]][:leidas]
    resultado["omitidos"] = ["ficha"] * omitidas
    resultado["errores"] = errores
    return resultado


# =====================================================================================================
# Pasada ampliada: A4 + B1 + B2 en UNA sola lectura de las fichas
#   A4  listado de Educacion/Cultura con todos los estados + ficha de las obras de la Contraloria que ya no estan
#       como Paralizada en INFOBRAS
#   B1  todos los avances mensuales de cada obra           -> data/processed/infobras_avances.csv
#   B2  detalle de los avances en estado Paralizado         -> data/processed/infobras_paralizaciones.csv
# No modifica infobras_fichas.jsonl ni fichas_infobras.csv (datos del 2026-10-27): usa su propio cache
# (config.INFOBRAS_AMPLIADAS) y escribe tablas nuevas. Se corre como proceso aparte:
#   .venv\Scripts\python.exe src\scraper_infobras.py --ampliado --codigos 561092        (prueba con 1 obra)
#   .venv\Scripts\python.exe src\scraper_infobras.py --ampliado --primeras 5            (prueba con 5)
#   .venv\Scripts\python.exe src\scraper_infobras.py --ampliado                         (todas)
# Si se corta, al volver a lanzarlo retoma: las obras ya guardadas en el cache no se vuelven a leer.
# =====================================================================================================
def codigo_avance(enlace):
    m = re.search(r"codigo=(\d+)", enlace or "")
    return m.group(1) if m else None


def tramos_paralizados(avances):
    """Avances en estado Paralizado, en orden cronologico, con su tramo (meses paralizados seguidos en la tabla) y su
    posicion en el tramo: unico, inicio, medio o fin."""
    ordenados = sorted(avances, key=lambda a: periodo(a["periodo"]))
    salida, tramo, anterior_paralizado = [], 0, False
    for i, a in enumerate(ordenados):
        paralizado = (a.get("estado") or "").lower().startswith("paraliz")
        if paralizado and not anterior_paralizado:
            tramo += 1
        if paralizado:
            sigue = i + 1 < len(ordenados) and (ordenados[i + 1].get("estado") or "").lower().startswith("paraliz")
            empieza = not anterior_paralizado
            posicion = "unico" if empieza and not sigue else "inicio" if empieza else "fin" if not sigue else "medio"
            salida.append((a, tramo, posicion))
        anterior_paralizado = paralizado
    return salida


def leer_ficha_ampliada(driver, codigo, modo=None):
    """Ficha + todos los avances + detalle de los avances paralizados de una obra (dict listo para el cache)."""
    modo = modo or config.INFOBRAS_DETALLE_PARALIZACIONES
    fila, avances, elegido, detalle_elegido = _leer_ficha(driver, codigo)
    paralizaciones = []
    for a, tramo, posicion in tramos_paralizados(avances):
        base = {"periodo": a["periodo"], "codigo_avance": codigo_avance(a["enlace"]), "tramo": tramo, "posicion_tramo": posicion,
                "detalle_leido": False, "causal_paralizacion": None, "fecha_paralizacion": None, "dias_paralizado": None,
                "comentario_fisico": None, "comentario_valorizado": None}
        if a["enlace"] and (modo == "todas" or posicion != "medio"):
            if elegido is not None and a["enlace"] == elegido["enlace"]:
                detalle = detalle_elegido          # ya se leyo en _leer_ficha
            else:
                utils.pausa()
                detalle = leer_detalle_avance(driver, a["enlace"])
            base.update(detalle)
            base["detalle_leido"] = True
        paralizaciones.append(base)
    avances_guardar = [{"periodo": a["periodo"], "fisico_programado": a["fisico_programado"], "fisico_real": a["fisico_real"],
                        "estado": a["estado"], "codigo_avance": codigo_avance(a["enlace"])} for a in avances]
    return {"codigo_infobras": str(fila["codigo_infobras"] or codigo), "codigo_pedido": str(codigo), "fecha_lectura": fila["fecha_lectura"],
            "modo_detalle": modo, "ficha": fila, "avances": avances_guardar, "paralizaciones": paralizaciones}


# ---------------- candado: una sola lectura de INFOBRAS a la vez ----------------
def tomar_candado():
    import os
    config.INFOBRAS_CANDADO.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(config.INFOBRAS_CANDADO, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError(f"ya hay una lectura de INFOBRAS en curso (existe {config.INFOBRAS_CANDADO}). Si estas seguro de que no "
                           "hay otra ventana leyendo INFOBRAS (revisa el Administrador de tareas), borra ese archivo y vuelve a lanzar.")
    with os.fdopen(fd, "w") as f:
        f.write(f"pid={os.getpid()} inicio={date.today()}\n")


def soltar_candado():
    config.INFOBRAS_CANDADO.unlink(missing_ok=True)


# ---------------- cache de la pasada ampliada ----------------
def leer_cache_ampliado():
    import json
    if not config.INFOBRAS_AMPLIADAS.exists():
        return []
    with open(config.INFOBRAS_AMPLIADAS, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def guardar_ampliada(registro):
    import json
    config.INFOBRAS_AMPLIADAS.parent.mkdir(parents=True, exist_ok=True)
    with open(config.INFOBRAS_AMPLIADAS, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def codigos_pasada():
    """Obras a leer: (codigo, origen). Primero las 198 de fichas_infobras.csv (paralizadas al 2026-10-27); luego las obras de
    Educacion/Cultura del anexo de la Contraloria de junio de 2026 que no estan en esa lista (A4, ~231)."""
    import glob
    import pandas as pd
    import tablas_finales
    fichas = pd.read_csv(config.INFOBRAS_SALIDA, dtype={"codigo_infobras": str}, encoding="utf-8-sig")
    actuales = list(fichas.codigo_infobras)
    x = pd.read_excel(glob.glob(str(config.RAW / "contraloria/2026/*anexo_01*junio*.xlsx"))[0], sheet_name="Data", dtype=str)
    x.columns = [tablas_finales.normalizar(c) for c in x.columns]
    tipo = x[next(c for c in x.columns if c.startswith("TIPO DE OBRA") and "NIVEL" not in c)].map(tablas_finales.normalizar)
    cgr = [c for c in x.loc[tipo.str.contains("EDUC"), "CODIGO INFOBRAS"].str.strip().drop_duplicates() if c not in set(actuales)]
    return [(c, "infobras_paralizada_2026-10-27") for c in actuales] + [(c, "contraloria_educacion_2026-06") for c in cgr]


def leer_todas_ampliadas(driver, codigos, forzar=False):
    """Lee la ficha ampliada de cada (codigo, origen) con pausas y hasta 3 intentos; guarda cada obra al terminarla.
    Devuelve (leidas, omitidas, errores)."""
    if forzar:
        config.INFOBRAS_AMPLIADAS.unlink(missing_ok=True)
    hechos = {r["codigo_pedido"] for r in leer_cache_ampliado()}
    leidas, omitidas, errores = 0, 0, []
    from tqdm import tqdm
    for codigo, origen in tqdm(codigos, desc="fichas INFOBRAS (ampliada)"):
        if str(codigo) in hechos:
            omitidas += 1
            continue
        for intento in range(1, config.REINTENTOS + 1):
            try:
                registro = leer_ficha_ampliada(driver, codigo)
                registro["origen"] = origen
                guardar_ampliada(registro)
                leidas += 1
                break
            except (TimeoutException, WebDriverException, ValueError) as e:
                utils.log(f"INFOBRAS ampliada {codigo}: intento {intento} fallo ({type(e).__name__}: {str(e)[:80]})")
                if intento == config.REINTENTOS:
                    errores.append((codigo, type(e).__name__))
                    utils.registrar_error("infobras", date.today().year, f"ficha_ampliada_{codigo}", "ficha ampliada", e)
                else:
                    time.sleep(5 * intento)
        utils.pausa()
    return leidas, omitidas, errores


def listado_todos_mas_reciente():
    """Ruta del ultimo listado de Educacion con todos los estados en data/raw/infobras, o None."""
    rutas = sorted(config.RAW.glob(f"infobras/*/infobras_*_{utils.nombre_limpio(config.INFOBRAS_NOMBRE_LISTADO_TODOS)}_*.csv"))
    return rutas[-1] if rutas else None


# ---------------- tablas finales de la pasada ampliada ----------------
def construir_csv_ampliados():
    """Arma infobras_avances.csv, infobras_paralizaciones.csv, infobras_fichas_ampliadas.csv y la validacion,
    solo con el cache (sin navegador). Si no hay cache, no hace nada. Devuelve (avances, paralizaciones, fichas) o None."""
    import pandas as pd
    import ubigeo_obras
    registros = leer_cache_ampliado()
    if not registros:
        utils.log("INFOBRAS ampliada: todavia no hay fichas ampliadas leidas; se omite")
        return None
    ultimos = {}
    for r in registros:                       # si una obra se leyo dos veces, vale la ultima lectura
        ultimos[r["codigo_pedido"]] = r
    registros = list(ultimos.values())
    coordenadas = leer_coordenadas_cache()   # las completadas despues (la ficha las cargaba con retraso)
    for r in registros:
        c = coordenadas.get(str(r["codigo_pedido"]))
        if c and r["ficha"].get("latitud") in (None, ""):
            r["ficha"]["latitud"], r["ficha"]["longitud"] = c.get("latitud"), c.get("longitud")

    def con_periodo(fila, extra):
        anio, mes = periodo(fila["periodo"])
        return {"codigo_infobras": extra["codigo_infobras"], "cui": extra["cui"], "periodo": fila["periodo"],
                "anio": anio or None, "mes": mes or None}

    filas_av, filas_par, filas_fi = [], [], []
    for r in registros:
        ficha = r["ficha"]
        extra = {"codigo_infobras": r["codigo_infobras"], "cui": ficha.get("cui")}
        for a in r["avances"]:
            filas_av.append({**con_periodo(a, extra), "fisico_programado": a["fisico_programado"], "fisico_real": a["fisico_real"],
                             "estado": a["estado"], "codigo_avance": a["codigo_avance"], "fecha_lectura": r["fecha_lectura"]})
        for p in r["paralizaciones"]:
            filas_par.append({**con_periodo(p, extra), "codigo_avance": p["codigo_avance"], "tramo": p["tramo"],
                              "posicion_tramo": p["posicion_tramo"], "detalle_leido": p["detalle_leido"],
                              "causal_paralizacion": p["causal_paralizacion"], "fecha_paralizacion": p["fecha_paralizacion"],
                              "dias_paralizado": p["dias_paralizado"], "comentario_fisico": p["comentario_fisico"],
                              "comentario_valorizado": p["comentario_valorizado"], "fecha_lectura": r["fecha_lectura"]})
        filas_fi.append({**{k: v for k, v in ficha.items() if not k.startswith("comentario")},
                         "origen": r.get("origen"), "n_paralizados": len(r["paralizaciones"])})

    texto = ["codigo_infobras", "cui", "codigo_avance"]
    avances = pd.DataFrame(filas_av).sort_values(["codigo_infobras", "anio", "mes"])
    paral = pd.DataFrame(filas_par, columns=["codigo_infobras", "cui", "periodo", "anio", "mes", "codigo_avance", "tramo", "posicion_tramo",
                                             "detalle_leido", "causal_paralizacion", "fecha_paralizacion", "dias_paralizado",
                                             "comentario_fisico", "comentario_valorizado", "fecha_lectura"]).sort_values(["codigo_infobras", "anio", "mes"])
    for t in (avances, paral):
        for c in texto:
            t[c] = t[c].astype("string")
        for c in ("anio", "mes", "tramo"):
            if c in t:
                t[c] = t[c].astype("Int64")
    paral["dias_paralizado"] = paral.dias_paralizado.astype("Float64").round().astype("Int64")
    # con el detalle "por_tramo" solo el primer y el ultimo mes de cada tramo traen causal y fecha: se repiten en los meses del medio
    for c in ("causal_paralizacion", "fecha_paralizacion"):
        paral[c + "_tramo"] = paral.groupby(["codigo_infobras", "tramo"])[c].transform(lambda s: s.ffill().bfill())

    fichas = pd.DataFrame(filas_fi)
    fichas["codigo_infobras"] = fichas.codigo_infobras.astype(str)
    for col in ("departamento", "provincia", "distrito"):
        fichas[col] = fichas[col].map(sin_tildes_mayusculas)
    fichas["departamento"] = fichas.departamento.map(lambda d: "CALLAO" if d and "CALLAO" in d else d)
    fichas["cod_departamento"] = fichas.departamento.map(config.DEPARTAMENTOS)
    ruta_todos = listado_todos_mas_reciente()
    if ruta_todos is not None:
        todos = leer_listado(ruta_todos).rename(columns={"monto_listado": "monto_expediente_tecnico", "estado_listado": "estado_listado_todos"})
        fichas = fichas.merge(todos, on="codigo_infobras", how="left")
    else:
        fichas["monto_expediente_tecnico"], fichas["estado_listado_todos"] = None, None
    fichas = ubigeo_obras.asignar_ubigeo(fichas)
    orden = ["codigo_infobras", "cui", "origen", "nombre_obra", "entidad", "cod_departamento", "departamento", "provincia", "distrito",
             "ubigeo", "ubigeo_metodo", "departamento_infobras", "estado", "estado_listado_todos", "modalidad", "naturaleza", "tipo_obra", "monto_expediente_tecnico",
             "monto_ejecucion_acumulado", "avance_fisico_pct", "fecha_inicio", "fecha_fin_prevista", "periodo_ultimo_avance", "n_avances",
             "n_paralizados", "periodo_avance_paralizado", "causal_paralizacion", "fecha_paralizacion", "dias_paralizado",
             "latitud", "longitud", "avance_fisico_tabla", "url_ficha", "fecha_lectura"]
    fichas = fichas[orden].sort_values(["origen", "codigo_infobras"])

    for tabla, ruta in ((avances, config.INFOBRAS_AVANCES), (paral, config.INFOBRAS_PARALIZACIONES), (fichas, config.INFOBRAS_FICHAS_AMPLIADAS)):
        tabla.to_csv(ruta, index=False, encoding="utf-8-sig")
    validar_ampliados(avances, paral, fichas, ruta_todos)
    utils.log(f"INFOBRAS ampliada: {len(fichas)} fichas, {len(avances)} avances, {len(paral)} avances paralizados "
              f"({int(paral.detalle_leido.sum())} con detalle leido); estados: {fichas.estado.value_counts().to_dict()}")
    return avances, paral, fichas


def validar_ampliados(avances, paral, fichas, ruta_todos):
    """Comprobaciones de la pasada ampliada -> docs/validacion_infobras_ampliada.csv (comprobacion, valor, esperado, ok, detalle)."""
    import pandas as pd
    filas = []

    def agregar(nombre, valor, esperado, detalle=""):
        ok = None if esperado is None else bool(valor == esperado)
        filas.append({"comprobacion": nombre, "valor": valor, "esperado": esperado, "ok": ok, "detalle": detalle})

    pedidos = codigos_pasada()
    agregar("obras pedidas (198 paralizadas + Contraloria jun-2026)", len(pedidos), None)
    agregar("obras leidas en el cache", len(fichas), len(pedidos), "si falta alguna: ver errores en docs/log_descargas.txt y relanzar")
    n_ficha = pd.to_numeric(fichas.set_index("codigo_infobras").n_avances, errors="coerce")
    n_tabla = avances.groupby("codigo_infobras").size().reindex(n_ficha.index, fill_value=0)
    agregar("obras cuyo numero de avances guardados = n_avances de la ficha", int((n_tabla == n_ficha).sum()), len(fichas))
    n_par = avances[avances.estado.str.lower().str.startswith("paraliz", na=False)].groupby("codigo_infobras").size()
    agregar("avances en estado Paralizado (tabla de avances) = filas de infobras_paralizaciones", len(paral), int(n_par.sum()))
    ultimo = avances.sort_values(["anio", "mes"]).groupby("codigo_infobras").fisico_real.last()
    enc = pd.to_numeric(fichas.set_index("codigo_infobras").avance_fisico_pct, errors="coerce")
    agregar("obras con avance fisico del encabezado = ultimo avance de la tabla (±0.01)",
            int(((enc - ultimo.reindex(enc.index)).abs() <= 0.01).sum()), int(enc.notna().sum()))
    agregar("obras con ubigeo", int(fichas.ubigeo.notna().sum()), len(fichas), "las que no: ubigeo_metodo = sin_ubigeo")
    if ruta_todos is not None:
        en_listado = fichas.estado_listado_todos.notna()
        agregar("obras leidas que aparecen en el listado de Educacion con todos los estados", int(en_listado.sum()), len(fichas), ruta_todos.name)
        distinto = (fichas.estado_listado_todos.map(sin_tildes_mayusculas) != fichas.estado.map(sin_tildes_mayusculas)) & en_listado
        agregar("obras con estado del listado distinto al de la ficha", int(distinto.sum()), 0, "el listado y la ficha se leen en momentos distintos")
    else:
        agregar("listado de Educacion con todos los estados", "no descargado", None)
    for origen, grupo in fichas.groupby("origen"):
        agregar(f"estados en la ficha ({origen})", "; ".join(f"{k}: {v}" for k, v in grupo.estado.value_counts().items()), None)
    pd.DataFrame(filas).to_csv(config.INFOBRAS_VALIDACION_AMPLIADA, index=False, encoding="utf-8-sig")


def ejecutar_ampliado(codigos=None, primeras=None, forzar=False, headless=False, modo=None):
    """Pasada ampliada completa: listado con todos los estados (A4) + fichas con avances (B1) y paralizaciones (B2)."""
    if modo:
        config.INFOBRAS_DETALLE_PARALIZACIONES = modo
    pedidos = codigos_pasada()
    if codigos:
        origen = dict(pedidos)
        pedidos = [(str(c), origen.get(str(c), "prueba")) for c in codigos]
    if primeras:
        pedidos = pedidos[:primeras]
    utils.log(f"INFOBRAS ampliada: inicio con {len(pedidos)} obras (detalle de paralizaciones: {config.INFOBRAS_DETALLE_PARALIZACIONES})")
    tomar_candado()
    try:
        driver = utils.crear_navegador(config.RAW / "infobras", headless=headless)
        try:
            ruta = descargar_listado(driver, forzar=False, filtros_buscador=config.INFOBRAS_FILTROS_TODOS,
                                     filtros_texto=config.INFOBRAS_FILTROS_TODOS_TEXTO, nombre=config.INFOBRAS_NOMBRE_LISTADO_TODOS)
            listado = leer_listado(ruta)
            estados = listado.estado_listado.value_counts().to_dict()
            utils.log(f"INFOBRAS ampliada: listado con todos los estados: {len(listado)} obras; {estados}")
            if len(estados) < 2:
                utils.log("AVISO INFOBRAS ampliada: el listado trae un solo estado; revisar que el filtro de estado quedo en 'todos'")
            utils.pausa()
            leidas, omitidas, errores = leer_todas_ampliadas(driver, pedidos, forzar)
        finally:
            driver.quit()
    finally:
        soltar_candado()
    utils.log(f"INFOBRAS ampliada: leidas {leidas}, omitidas (ya en el cache) {omitidas}, con error {len(errores)} {errores[:10]}")
    construir_csv_ampliados()
    return leidas, omitidas, errores


# ---------------- coordenadas: la ficha las rellena con JavaScript unos segundos despues de cargar ----------------
def leer_coordenadas_cache():
    """codigo -> registro del cache de coordenadas (data/interim/infobras_coordenadas.jsonl); vale el ultimo de cada obra."""
    import json
    if not config.INFOBRAS_COORDENADAS.exists():
        return {}
    with open(config.INFOBRAS_COORDENADAS, encoding="utf-8") as f:
        return {str(r["codigo_infobras"]): r for r in (json.loads(l) for l in f if l.strip())}


def guardar_coordenadas(registro):
    import json
    config.INFOBRAS_COORDENADAS.parent.mkdir(parents=True, exist_ok=True)
    with open(config.INFOBRAS_COORDENADAS, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")


def completar_coordenadas(headless=False):
    """Completa latitud y longitud de las obras de la pasada ampliada que no las tienen.

    1) Primero copia las de fichas_infobras.csv (lectura del 27-oct) cuando existen: no abre el navegador.
    2) Para las que siguen sin coordenadas abre SOLO la pagina de datos generales (esperando a que termine de cargar) y las lee.
    Un registro con latitud vacia despues de esperar significa que INFOBRAS no tiene coordenadas de esa obra.
    """
    import pandas as pd
    registros = {r["codigo_pedido"]: r for r in leer_cache_ampliado()}
    hechos = leer_coordenadas_cache()
    sin = [c for c, r in registros.items() if r["ficha"].get("latitud") in (None, "") and c not in hechos]
    if not sin:
        utils.log("INFOBRAS coordenadas: no falta ninguna")
        return 0, 0
    octubre = pd.read_csv(config.INFOBRAS_SALIDA, dtype=str, keep_default_na=False, encoding="utf-8-sig").set_index("codigo_infobras")
    copiadas = 0
    for c in list(sin):
        if c in octubre.index and octubre.loc[c, "latitud"] != "":
            guardar_coordenadas({"codigo_infobras": c, "latitud": float(octubre.loc[c, "latitud"]), "longitud": float(octubre.loc[c, "longitud"]),
                                 "fuente": "fichas_infobras_2026-10-27", "fecha_lectura": str(date.today())})
            sin.remove(c)
            copiadas += 1
    utils.log(f"INFOBRAS coordenadas: {copiadas} copiadas de fichas_infobras.csv; {len(sin)} por leer en la web")
    leidas = 0
    if sin:
        tomar_candado()
        try:
            driver = utils.crear_navegador(config.RAW / "infobras", headless=headless)
            try:
                from tqdm import tqdm
                for codigo in tqdm(sin, desc="coordenadas INFOBRAS"):
                    for intento in range(1, config.REINTENTOS + 1):
                        try:
                            lineas = abrir_pagina(driver, "DatosGenerales", "obraId", codigo)
                            texto = valor(lineas, "COORDENADAS GEOGRÁFICAS") or ""
                            if "cargando" in texto.lower():
                                raise TimeoutException("las coordenadas siguen cargando")
                            lat = re.search(r"Latitud:\s*(-?[\d.]+)", texto)
                            lon = re.search(r"Longitud:\s*(-?[\d.]+)", texto)
                            guardar_coordenadas({"codigo_infobras": codigo, "latitud": float(lat.group(1)) if lat else None,
                                                 "longitud": float(lon.group(1)) if lon else None, "fuente": "web",
                                                 "texto_coordenadas": texto[:60], "fecha_lectura": str(date.today())})
                            leidas += 1
                            break
                        except (TimeoutException, WebDriverException) as e:
                            utils.log(f"INFOBRAS coordenadas {codigo}: intento {intento} fallo ({type(e).__name__})")
                            time.sleep(5 * intento)
                    utils.pausa()
            finally:
                driver.quit()
        finally:
            soltar_candado()
    utils.log(f"INFOBRAS coordenadas: {leidas} leidas en la web, {copiadas} copiadas")
    construir_csv_ampliados()
    return leidas, copiadas


if __name__ == "__main__":
    import argparse
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(description="Pasada ampliada por INFOBRAS (A4 + B1 + B2). Abre Chrome: solo una persona a la vez.")
    p.add_argument("--ampliado", action="store_true", help="obligatorio: confirma que se quiere abrir el navegador")
    p.add_argument("--codigos", help="solo estos codigos INFOBRAS, separados por coma (para probar)")
    p.add_argument("--primeras", type=int, help="solo las N primeras obras de la lista (para probar)")
    p.add_argument("--modo", choices=["por_tramo", "todas"], help="detalle de paralizaciones (por defecto, el de config.py)")
    p.add_argument("--solo-tablas", action="store_true", help="no abre el navegador: rearma los CSV con lo que ya esta en el cache")
    p.add_argument("--coordenadas", action="store_true", help="completa las coordenadas que faltan (abre Chrome solo para las que no estaban en octubre)")
    p.add_argument("--headless", action="store_true", help="navegador sin ventana")
    a = p.parse_args()
    if a.coordenadas:
        completar_coordenadas(headless=a.headless)
    elif a.solo_tablas:
        construir_csv_ampliados()
    elif a.ampliado:
        ejecutar_ampliado([c.strip() for c in a.codigos.split(",")] if a.codigos else None, a.primeras, headless=a.headless, modo=a.modo)
    else:
        p.error("usa --ampliado para leer INFOBRAS, --coordenadas para completar coordenadas o --solo-tablas para rearmar los CSV")
