"""Extraccion: de los archivos crudos (data\\raw) a tablas limpias (data\\processed)."""
import json
import re
import unicodedata
import zipfile

import numpy as np
import pandas as pd
import pdfplumber

import config
import utils


# ---------------- utilidades de archivos ----------------
def dbf_de_zip(fuente, anio, patron_zip):
    """Busca el zip mas reciente del anio que coincida con el patron, lo descomprime en interim y devuelve su .dbf."""
    carpeta = config.RAW / fuente / str(anio)
    candidatos = sorted(p for p in carpeta.glob("*.zip") if re.search(patron_zip, p.name, re.I))
    if not candidatos:
        raise FileNotFoundError(f"no hay zip '{patron_zip}' en {carpeta}")
    ruta_zip = candidatos[-1]
    destino = config.INTERIM / fuente / str(anio) / ruta_zip.stem
    if not destino.exists():
        with zipfile.ZipFile(ruta_zip) as z:
            z.extractall(destino)
    return sorted(destino.rglob("*.dbf"))[0]


# ---------------- ESCALE: lectura por anio ----------------
def cargar_lineal(anio):
    """Una fila por local que respondio el censo: codigo, ubigeo y nombres (y servicios si el anio los trae en columnas)."""
    columnas = ["CODLOCAL", "CODGEO", "DPTO", "PROV", "DISTRITO"]
    if anio not in config.ESCALE_SERVICIOS_TABLA:
        columnas += [c for c, _ in config.ESCALE_SERVICIOS_COLUMNAS.values()]
    lineal = utils.leer_dbf(dbf_de_zip("escale", anio, config.ESCALE_ZIP_LINEAL), columnas=columnas)
    lineal = lineal.drop_duplicates("CODLOCAL")
    vacios = lineal.CODGEO == ""
    if vacios.any():   # algun local viene sin ubigeo: se toma el de otro local con el mismo departamento/provincia/distrito
        clave = ["DPTO", "PROV", "DISTRITO"]
        mapa = lineal[~vacios].drop_duplicates(clave).set_index(clave).CODGEO
        lineal.loc[vacios, "CODGEO"] = [mapa.get(k, "") for k in lineal.loc[vacios, clave].itertuples(index=False, name=None)]
        sin_ubigeo = int((lineal.CODGEO == "").sum())
        utils.log(f"ESCALE {anio}: {int(vacios.sum())} local(es) sin ubigeo, {int(vacios.sum()) - sin_ubigeo} recuperado(s) por nombre, {sin_ubigeo} excluido(s)")
        lineal = lineal[lineal.CODGEO != ""]
    return lineal


def cargar_locales_padron(anio):
    """Del padron (una fila por servicio educativo) saca, por local: si es publico y si es rural."""
    padron = utils.leer_dbf(dbf_de_zip("escale", anio, config.ESCALE_ZIP_PADRON),
                            columnas=["CODLOCAL", "GESTION", "AREA_CENSO"])
    padron = padron[padron.CODLOCAL != ""]   # los programas no escolarizados no tienen local
    padron["publico"] = padron.GESTION.isin(config.ESCALE_GESTION_PUBLICA)
    padron["rural"] = padron.AREA_CENSO == config.ESCALE_AREA_RURAL
    # un local es publico si tiene al menos un servicio publico (coincide con GES_LOC del Padlocal 2025)
    return padron.groupby("CODLOCAL").agg(publico=("publico", "any"), rural=("rural", "first"))


def _es_red(codigos, validos):
    """Serie de codigos -> booleano con NA cuando no hay dato ('' o '-')."""
    return codigos.isin(validos).astype("boolean").mask(codigos.isin(["", "-"]))


def servicios_por_local(anio, lineal):
    """Devuelve (tabla, notas): por local, agua/desague/luz de red publica (True/False/NA)."""
    notas = {}
    if anio in config.ESCALE_SERVICIOS_TABLA:
        cfg = config.ESCALE_SERVICIOS_TABLA[anio]
        t = utils.leer_dbf(dbf_de_zip("escale", anio, cfg["zip"]), columnas=["CODLOCAL", "CUADRO", "NUMERO", cfg["marca"]])
        t = t[t[cfg["marca"]].str.upper() == "X"]   # solo la fila predominante
        columnas = {}
        for servicio, cuadro in cfg["cuadros"].items():
            s = t[t.CUADRO == cuadro]
            repetidos = s.CODLOCAL.value_counts()
            notas[f"{servicio}_con_varias_predominantes"] = int((repetidos > 1).sum())
            s = s[~s.CODLOCAL.isin(repetidos[repetidos > 1].index)]   # ambiguas: se tratan como sin dato
            codigo = s.set_index("CODLOCAL").NUMERO.reindex(lineal.CODLOCAL)
            codigo.index = lineal.index
            columnas[servicio] = _es_red(codigo.fillna(""), config.ESCALE_RED_PUBLICA_TABLA)
        return pd.DataFrame(columnas), notas
    if anio != 2025:
        utils.log(f"AVISO: el anio {anio} no tiene formato configurado; se usa el formato de columnas de 2025")
    return pd.DataFrame({servicio: _es_red(lineal[columna], validos)
                         for servicio, (columna, validos) in config.ESCALE_SERVICIOS_COLUMNAS.items()}), notas


def edificaciones_por_local(anio):
    """Por local: si hay dato de edificaciones, si alguna en uso declara riesgo y si alguna tiene estructura en mal estado."""
    cfg = config.ESCALE_EDIFICACIONES.get(anio)
    if cfg is None:
        utils.log(f"AVISO: el anio {anio} no tiene campos de edificaciones configurados; se usan los de 2025")
        cfg = config.ESCALE_EDIFICACIONES[2025]
    t = utils.leer_dbf(dbf_de_zip("escale", anio, config.ESCALE_ZIP_EDIFICACIONES),
                       columnas=["CODLOCAL", cfg["uso"], cfg["riesgo"]] + cfg["estado"])
    t = t[t[cfg["uso"]].isin(config.ESCALE_SI)].copy()   # solo edificaciones en uso
    t["dato"] = t[cfg["riesgo"]].isin(config.ESCALE_SI + config.ESCALE_NO)
    t["riesgo"] = t[cfg["riesgo"]].isin(config.ESCALE_SI)
    t["mal"] = t[cfg["estado"]].isin(config.ESCALE_ESTADO_MALO).any(axis=1)
    return t.groupby("CODLOCAL").agg(edif_dato=("dato", "any"), edif_riesgo=("riesgo", "any"), edif_mal=("mal", "any"))


def tabla_escale_anio(anio):
    """Una fila por distrito para un anio, mas un diccionario con el recuento de depuracion."""
    lineal = cargar_lineal(anio)
    locales = cargar_locales_padron(anio)
    servicios, notas = servicios_por_local(anio, lineal)
    df = pd.concat([lineal[["CODLOCAL", "CODGEO", "DPTO", "PROV", "DISTRITO"]], servicios], axis=1)
    df = df.merge(locales, left_on="CODLOCAL", right_index=True, how="left")
    df = df.merge(edificaciones_por_local(anio), left_on="CODLOCAL", right_index=True, how="left")
    for columna in ["edif_dato", "edif_riesgo", "edif_mal"]:
        df[columna] = df[columna].fillna(False).astype(bool)
    depuracion = {"anio": anio, "locales_censo": len(df), "sin_padron": int(df.publico.isna().sum()),
                  "privados_excluidos": int((df.publico == False).sum())}   # noqa: E712
    df = df[df.publico == True].copy()   # noqa: E712  (solo gestion publica y locales activos del padron)
    df["tres"] = df.agua & df.desague & df.luz   # logica de tres valores: False si ya falta un servicio con certeza
    df["rural"] = df.rural.astype(bool)
    df["riesgo_si"] = df.edif_dato & df.edif_riesgo
    df["mal_si"] = df.edif_dato & df.edif_mal
    depuracion.update(publicos=len(df), tres_sin_dato=int(df.tres.isna().sum()),
                      con_dato_edif=int(df.edif_dato.sum()), **notas)

    grupos = df.groupby("CODGEO")
    con_dato = grupos.tres.apply(lambda s: s.notna().sum())
    tres_si = grupos.tres.apply(lambda s: (s == True).sum())   # noqa: E712
    con_edif = grupos.edif_dato.sum()
    salida = pd.DataFrame({
        "anio": anio,
        "departamento": grupos.DPTO.agg(lambda s: s.mode().iat[0]),
        "provincia": grupos.PROV.agg(lambda s: s.mode().iat[0]),
        "distrito": grupos.DISTRITO.agg(lambda s: s.mode().iat[0]),
        "n_locales_publicos": grupos.size(),
        "n_locales_sin_dato": grupos.tres.apply(lambda s: s.isna().sum()),
        "pct_3_servicios": (100 * tres_si / con_dato.replace(0, np.nan)).round(2),
        "pct_rural": (100 * grupos.rural.mean()).round(2),
        "n_locales_con_dato_edif": con_edif,
        "pct_riesgo_estructural": (100 * grupos.riesgo_si.sum() / con_edif.replace(0, np.nan)).round(2),
        "pct_estructura_mal_estado": (100 * grupos.mal_si.sum() / con_edif.replace(0, np.nan)).round(2),
    })
    salida["pct_sin_3_servicios"] = (100 - salida.pct_3_servicios).round(2)
    salida.index.name = "ubigeo"
    return salida.reset_index(), depuracion


NOMBRE_VALIDO = re.compile(r"^[A-ZÁÉÍÓÚÑÜ0-9 .,'\-/()_]+$")   # mayusculas, tildes, Ñ y signos normales (sin caracteres daniados)


def reparar_texto(texto):
    """Revierte el texto doblemente codificado de la fuente ('CONSTITUCIÃ\x93N' -> 'CONSTITUCIÓN'); si no aplica, lo deja igual."""
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


def armonizar_nombres(tabla):
    """Cada ubigeo conserva el mismo nombre en todos los anios.

    La fuente de 2023 trae nombres cortados ("MADRE DE DIO") y con la Ñ daniada. Para cada codigo se elige,
    entre sus nombres sin caracteres daniados, el mas largo (el mas reciente si empatan).
    """
    tabla = tabla.sort_values("anio", ascending=False).copy()   # primero el anio mas reciente
    for columna in ("departamento", "provincia", "distrito"):
        tabla[columna] = tabla[columna].map({n: reparar_texto(n) for n in tabla[columna].unique()})

    def mejor(nombres):
        distintos = list(dict.fromkeys(nombres))
        limpios = [n for n in distintos if NOMBRE_VALIDO.match(n)] or distintos
        return max(limpios, key=len)

    cambios = 0
    for columna, digitos in (("departamento", 2), ("provincia", 4), ("distrito", 6)):
        clave = tabla.ubigeo.str[:digitos]
        canonico = tabla.groupby(clave)[columna].agg(mejor)
        nuevo = clave.map(canonico)
        cambios += int((nuevo != tabla[columna]).sum())
        tabla[columna] = nuevo
    if cambios:
        utils.log(f"EXTRACCION ESCALE: nombres armonizados por ubigeo ({cambios} valores corregidos)")
    return tabla.sort_values(["anio", "ubigeo"])


def anios_escale_disponibles(anio_inicio):
    carpetas = [int(p.name) for p in (config.RAW / "escale").iterdir() if p.is_dir() and p.name.isdigit()]
    return sorted(a for a in carpetas if a >= anio_inicio)


def construir_escale(anio_inicio=config.ANIO_INICIO):
    """Genera data\\processed\\escale_infraestructura.csv"""
    tablas, resumen = [], []
    for anio in anios_escale_disponibles(anio_inicio):
        try:
            tabla, depuracion = tabla_escale_anio(anio)
            tablas.append(tabla)
            resumen.append(depuracion)
            utils.log(f"EXTRACCION ESCALE {anio}: {len(tabla)} distritos, {depuracion['publicos']} locales publicos")
        except Exception as error:   # un anio con problemas no detiene a los demas
            utils.log(f"EXTRACCION ESCALE {anio}: fallo ({type(error).__name__}: {error})")
    if not tablas:
        utils.log("EXTRACCION ESCALE: no hubo datos para procesar")
        return None, resumen
    final = armonizar_nombres(pd.concat(tablas))
    columnas = ["anio", "ubigeo", "departamento", "provincia", "distrito", "n_locales_publicos",
                "n_locales_sin_dato", "pct_3_servicios", "pct_sin_3_servicios", "pct_rural",
                "n_locales_con_dato_edif", "pct_riesgo_estructural", "pct_estructura_mal_estado"]
    ruta = config.PROCESSED / "escale_infraestructura.csv"
    final[columnas].to_csv(ruta, index=False, encoding="utf-8")
    utils.log(f"EXTRACCION ESCALE: guardado {ruta.name} ({len(final)} filas)")
    return final[columnas], resumen


# ---------------- ENLA: tablas regionales dentro de los PDF ----------------
def _sin_tildes(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower().strip()


REGIONES_NORMALIZADAS = {_sin_tildes(r): r for r in config.ENLA_REGIONES}
FILA_REGION = re.compile(r"^(?P<region>[^\d\n]+?)\s+(?P<numeros>\d+(?:,\d+)?\*?(?:\s+\d+(?:,\d+)?\*?)+)\s*$")


def leer_pagina_regional(texto, ambos_anios=False):
    """Si la pagina es una tabla regional (titulo conocido) devuelve (area, grado, anio, {region: satisfactorio}).

    Con ambos_anios=True devuelve (area, grado, {anio: {region: satisfactorio}}) con los dos anios que compara la tabla.

    La tabla trae pares 2019/2022 (o los dos anios que se comparan) para cada nivel de logro y la medida promedio:
    4.o primaria y 2.o secundaria tienen 5 columnas por par (previo, inicio, proceso, satisfactorio, medida).
    """
    if not re.search(config.ENLA_TITULO_TABLA, texto):
        return None
    lineas = [l.strip() for l in texto.splitlines()]
    area = next((config.ENLA_AREAS[l] for l in lineas if l in config.ENLA_AREAS), None)
    m = re.search(r"(\d)\.\S\s*grado de (primaria|secundaria)", texto)
    grado = config.ENLA_GRADOS.get((m.group(1), m.group(2))) if m else None
    if not area or not grado:
        return None
    anios = [int(a) for l in lineas if re.fullmatch(r"(?:(?:19|20)\d\d\s*){4,10}", l) for a in l.split()]
    if not anios:
        return None
    valores, previos, niveles_suman = {}, {}, True
    for linea in lineas:
        f = FILA_REGION.match(linea)
        region = REGIONES_NORMALIZADAS.get(_sin_tildes(f.group("region"))) if f else None
        if not region:
            continue
        nums = [float(n.replace("*", "").replace(",", ".")) for n in f.group("numeros").split()]
        if len(nums) != 10:   # previo, inicio, proceso, satisfactorio, medida; cada uno con dos anios
            return None
        niveles = [nums[1], nums[3], nums[5], nums[7]]   # columnas del anio mas reciente
        niveles_suman &= abs(sum(niveles) - 100) <= 0.6
        valores[region] = nums[7]
        previos[region] = nums[6]   # satisfactorio del anio anterior (los pares son anio anterior / anio reciente)
    if len(valores) != len(config.ENLA_REGIONES) or not niveles_suman:
        utils.log(f"AVISO ENLA: tabla {area} {grado} descartada ({len(valores)} regiones, niveles suman 100: {niveles_suman})")
        return None
    if ambos_anios:
        return area, grado, {max(anios): valores, min(anios): previos}
    return area, grado, max(anios), valores


ARCHIVO_SICRECE = re.compile(r"^enla_(\d{4})_sicrece_(muestral|censal)_.+_(\d{4}-\d{2}-\d{2})\.json$")


def region_de_sicrece(descripcion):
    """'Dre La libertad' o 'La Libertad' -> nombre de region de config.ENLA_REGIONES (None si no se reconoce)."""
    nombre = re.sub(r"^dre\s+", "", _sin_tildes(descripcion))
    return REGIONES_NORMALIZADAS.get(nombre)


def leer_json_sicrece(ruta):
    """De un JSON de SICRECE devuelve {(area, grado): {region: satisfactorio}} y una lista de problemas."""
    resultados, problemas = {}, []
    for entrada in json.loads(ruta.read_text(encoding="utf-8")):
        grado = config.SICRECE_GRADOS.get((entrada["nivel_educativo"].upper(), entrada["grado"].upper()))
        area = next((v for k, v in config.ENLA_AREAS.items() if _sin_tildes(k) == _sin_tildes(entrada["competencia"])), None)
        if not grado or not area:
            continue   # grados o areas que no se piden
        valores = {}
        for ambito in entrada["ambito"]:
            descripcion = ambito.get("descripcion_nivel_resultado") or ambito.get("descripcion_sede") or ""
            region = region_de_sicrece(descripcion)
            if not region:
                problemas.append(f"{ruta.name}: region no reconocida '{descripcion}'")
                continue
            niveles = {d["logro"]: d["porcentaje"] for d in ambito["detalle"]}
            if abs(sum(niveles.values()) - 100) > 0.6:
                problemas.append(f"{ruta.name}: {region} {area} niveles suman {sum(niveles.values()):.1f}")
            valores[region] = niveles.get("Satisfactorio", np.nan)
        if len(valores) != len(config.ENLA_REGIONES):
            problemas.append(f"{ruta.name}: {area} {grado} trae {len(valores)} regiones en vez de {len(config.ENLA_REGIONES)}")
        resultados[(area, grado)] = valores
    return resultados, problemas


def verificar_contra_pdf(tabla):
    """Compara los valores de SICRECE de 2022 con las tablas en texto del reporte nacional EM 2022 (si esta descargado)."""
    pdfs = sorted((config.RAW / "enla" / "2022").glob("*reporte_nacional*.pdf"))
    if not pdfs:
        return
    comparados, distintos = 0, []
    with pdfplumber.open(pdfs[-1]) as pdf:
        for pagina in pdf.pages:
            resultado = leer_pagina_regional(pagina.extract_text() or "")
            if not resultado:
                continue
            area, grado, anio, valores = resultado
            columna = f"{area}_satisfactorio"
            for region, valor_pdf in valores.items():
                fila = tabla[(tabla.anio == anio) & (tabla.grado == grado) & (tabla.region == region) & (tabla.evaluacion == "MUESTRAL")]
                if len(fila):
                    comparados += 1
                    if abs(fila.iloc[0][columna] - valor_pdf) > 0.05:
                        distintos.append((region, grado, area, fila.iloc[0][columna], valor_pdf))
    utils.log(f"VERIFICACION ENLA 2022 contra el PDF: {comparados} valores comparados, {len(distintos)} distintos {distintos[:5]}")


def construir_enla(verificar_pdf=False):
    """Genera data/processed/enla_regiones.csv con los resultados por region (DRE) que se obtuvieron de SICRECE."""
    encontrados, problemas = {}, []
    for ruta in sorted((config.RAW / "enla").glob("*/enla_*_sicrece_*.json")):
        m = ARCHIVO_SICRECE.match(ruta.name)
        if not m:
            continue
        anio, tipo = int(m.group(1)), m.group(2).upper()
        resultados, p = leer_json_sicrece(ruta)
        problemas += p
        for (area, grado), valores in resultados.items():
            encontrados[(anio, tipo, grado, area)] = valores   # si hay varias fechas gana la mas reciente (orden alfabetico)
    for problema in problemas:
        utils.log(f"AVISO ENLA: {problema}")
    filas = []
    for anio, tipo, grado in sorted({(a, t, g) for a, t, g, _ in encontrados}):
        lectura = encontrados.get((anio, tipo, grado, "lectura"), {})
        matematica = encontrados.get((anio, tipo, grado, "matematica"), {})
        for region in config.ENLA_REGIONES:
            filas.append({"region": region, "anio": anio, "grado": grado, "evaluacion": tipo,
                          "lectura_satisfactorio": lectura.get(region, np.nan),
                          "matematica_satisfactorio": matematica.get(region, np.nan)})
    if not filas:
        utils.log("EXTRACCION ENLA: no hay respuestas de SICRECE en data/raw/enla")
        return None
    tabla = pd.DataFrame(filas)
    ruta = config.PROCESSED / "enla_regiones.csv"
    tabla.to_csv(ruta, index=False, encoding="utf-8")
    utils.log(f"EXTRACCION ENLA: guardado {ruta.name} ({len(tabla)} filas)")
    if verificar_pdf:
        verificar_contra_pdf(tabla)
    return tabla


def construir_enla_niveles():
    """Genera data/processed/enla_niveles_logro.csv: los 4 niveles de logro por region (no solo Satisfactorio).

    Sale de los mismos JSON de SICRECE que enla_regiones.csv. Cada fila suma 100 (con tolerancia de 0.6 por el redondeo).
    """
    filas = []
    for ruta in sorted((config.RAW / "enla").glob("*/enla_*_sicrece_*.json")):
        m = ARCHIVO_SICRECE.match(ruta.name)
        if not m:
            continue
        anio, tipo = int(m.group(1)), m.group(2).upper()
        for entrada in json.loads(ruta.read_text(encoding="utf-8")):
            grado = config.SICRECE_GRADOS.get((entrada["nivel_educativo"].upper(), entrada["grado"].upper()))
            area = next((v for k, v in config.ENLA_AREAS.items() if _sin_tildes(k) == _sin_tildes(entrada["competencia"])), None)
            if not grado or not area:
                continue
            for ambito in entrada["ambito"]:
                region = region_de_sicrece(ambito.get("descripcion_nivel_resultado") or ambito.get("descripcion_sede") or "")
                if not region:
                    continue
                niveles = {d["logro"]: d["porcentaje"] for d in ambito["detalle"]}
                clave = unicodedata.normalize("NFKD", region).encode("ascii", "ignore").decode().upper()
                filas.append({"region": region, "region_clave": clave,
                              "cod_departamento": config.DEPARTAMENTOS.get("LIMA" if clave.startswith("LIMA") else clave),
                              "anio": anio, "evaluacion": tipo, "grado": grado, "area": area,
                              "previo_al_inicio": niveles.get("Previo al inicio", np.nan), "en_inicio": niveles.get("En inicio", np.nan),
                              "en_proceso": niveles.get("En proceso", np.nan), "satisfactorio": niveles.get("Satisfactorio", np.nan),
                              "archivo_json": ruta.name})
    if not filas:
        utils.log("EXTRACCION ENLA NIVELES: no hay respuestas de SICRECE en data/raw/enla")
        return None
    tabla = pd.DataFrame(filas).drop_duplicates(["region", "anio", "evaluacion", "grado", "area"], keep="last")
    tabla = tabla.sort_values(["anio", "grado", "area", "region"]).reset_index(drop=True)
    suma = tabla[["previo_al_inicio", "en_inicio", "en_proceso", "satisfactorio"]].sum(axis=1)
    malas = tabla[(suma - 100).abs() > 0.6]
    if len(malas):
        utils.log(f"AVISO ENLA NIVELES: {len(malas)} fila(s) no suman 100")
    tabla.to_csv(config.PROCESSED / "enla_niveles_logro.csv", index=False, encoding="utf-8-sig")
    utils.log(f"EXTRACCION ENLA NIVELES: guardado enla_niveles_logro.csv ({len(tabla)} filas; {len(malas)} que no suman 100)")
    return tabla


# ---------------- validacion ----------------
def validar(escale, enla):
    """Imprime filas por anio, nulos por columna, rangos 0-100 y 10 filas de ejemplo de cada tabla."""
    pd.set_option("display.width", 250, "display.max_columns", 30)
    for nombre, tabla, columnas_pct in [
        ("escale_infraestructura", escale, ["pct_3_servicios", "pct_sin_3_servicios", "pct_rural",
                                            "pct_riesgo_estructural", "pct_estructura_mal_estado"]),
        ("enla_regiones", enla, ["lectura_satisfactorio", "matematica_satisfactorio"]),
    ]:
        utils.log(f"VALIDACION {nombre}")
        if tabla is None:
            print("   (no se genero en esta corrida)")
            continue
        clave = ["anio"] if nombre.startswith("escale") else ["anio", "evaluacion", "grado"]
        print("filas por", "/".join(clave), ":", tabla.groupby(clave).size().to_dict())
        print("nulos por columna:", tabla.isna().sum().to_dict())
        fuera = {c: int(((tabla[c] < 0) | (tabla[c] > 100)).sum()) for c in columnas_pct}
        print("valores fuera de 0-100:", fuera, "| minimo/maximo:", {c: (tabla[c].min(), tabla[c].max()) for c in columnas_pct})
        print(tabla.sample(min(10, len(tabla)), random_state=1).sort_index().to_string(index=False))
    if enla is not None:
        por_anio = enla.groupby(["anio", "evaluacion", "grado"]).region.nunique()
        print("\nENLA regiones por anio, evaluacion y grado (deben ser 26):", por_anio.to_dict())


if __name__ == "__main__":
    escale, _ = construir_escale()
    enla = construir_enla()
    validar(escale, enla)
