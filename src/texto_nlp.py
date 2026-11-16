"""Fase 4 del proyecto PDF (opcional): texto citable y clasificacion de causas por palabras clave.

Solo se usan expresiones regulares y conteos (sin spaCy ni scikit-learn): alcanza para buscar frases con 'educacion',
contar terminos y asignar un grupo de causa por palabras clave, y las reglas se pueden leer y corregir a mano en config.py.
No se afirman relaciones de causa-efecto: solo se describe lo que dice el texto.
"""
import re
import unicodedata
from collections import Counter

import numpy as np
import pandas as pd

import config
import tablas_finales
from leer_pdf import log


def sin_tildes(texto):
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()


# ---------------- texto narrativo de los informes ----------------
def parrafos_de_pagina(texto):
    """Une las lineas de la pagina en un solo texto narrativo, dejando fuera las lineas que son filas de tabla (muchos numeros)."""
    lineas = []
    for linea in texto.splitlines():
        linea = linea.strip()
        letras = sum(c.isalpha() for c in linea)
        digitos = sum(c.isdigit() for c in linea)
        if letras < 8 or digitos > 0.25 * (letras + digitos):
            continue
        lineas.append(linea)
    unido = " ".join(lineas)
    return re.sub(r"(\w)- (\w)", r"\1\2", unido)   # une palabras cortadas con guion al final de linea


def oraciones(texto):
    """Oraciones del texto narrativo: con palabras suficientes y sin ser texto de celdas en mayusculas ni pies de tabla."""
    salida = []
    for o in re.split(r"(?<=[.!?;])\s+(?=[A-ZÁÉÍÓÚÑ•▪])", texto):
        o = o.strip()
        letras = [c for c in o if c.isalpha()]
        if (len(o.split()) >= config.CITAS_MIN_PALABRAS and not o.startswith(("FUENTE", "Fuente", "ELABORACI")) and letras
                and sum(c.isupper() for c in letras) <= 0.3 * len(letras)):
            salida.append(o)
    return salida


def paginas_de_listas():
    """{(archivo, pagina)} de las paginas con listas de obras (tablas de 'principales obras'), cuyo texto no es narrativa."""
    catalogo = pd.read_csv(config.CATALOGO_TABLAS, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    lista = catalogo[catalogo.tipo.isin(["principales_obras_departamento", "continuacion"]) & (catalogo.estado == "guardada")]
    paginas = set()
    for _, f in lista.iterrows():
        paginas |= {(f.archivo, p) for p in range(int(f.pagina), int(f.pagina_fin) + 1)}
    return paginas


def paginas_de_informes():
    """(informe, numero_de_pagina, texto) de las paginas narrativas de los informes de la Contraloria."""
    excluidas = paginas_de_listas()
    for informe in tablas_finales.informes_contraloria():
        for archivo in sorted(informe["carpeta"].glob("texto_p*.txt")):
            pagina = int(archivo.stem.split("_p")[1])
            if (informe["archivo"], pagina) not in excluidas:
                yield informe, pagina, archivo.read_text(encoding="utf-8")


# ---------------- citas de educacion ----------------
def citas_educacion():
    """Oraciones de los informes que mencionan educacion o escuelas, con archivo y pagina para poder citarlas."""
    patron = re.compile(config.CITAS_REGEX, re.I)
    filas, vistas = [], set()
    for informe, pagina, texto in paginas_de_informes():
        for oracion in oraciones(parrafos_de_pagina(texto)):
            m = patron.search(oracion)
            clave = (informe["archivo"], oracion)
            if not m or clave in vistas:
                continue
            vistas.add(clave)
            filas.append({"anio": informe["anio"], "fecha_corte": informe["fecha_corte"], "fuente_pdf": informe["archivo"],
                          "pagina": pagina, "termino": m.group(0).lower(), "cita": oracion[:config.CITAS_MAX_CARACTERES]})
    return pd.DataFrame(filas, columns=["anio", "fecha_corte", "fuente_pdf", "pagina", "termino", "cita"])


# ---------------- frecuencia de terminos ----------------
def frecuencia_terminos():
    """Terminos y pares de terminos mas frecuentes de la narrativa de los informes, por anio."""
    conteos = {}
    for informe, pagina, texto in paginas_de_informes():
        palabras = [p for p in re.findall(r"[a-zñ]{4,}", sin_tildes(parrafos_de_pagina(texto)))]
        utiles = [p if p not in config.STOPWORDS_ES else None for p in palabras]
        por_anio = conteos.setdefault(informe["anio"], {"termino": Counter(), "par": Counter()})
        por_anio["termino"].update(p for p in utiles if p)
        por_anio["par"].update(f"{a} {b}" for a, b in zip(utiles, utiles[1:]) if a and b and a != b)   # sin pares como "costo costo"
    filas = []
    n_anios = len(conteos)
    for tipo in ("termino", "par"):
        # TF-IDF por anio: frecuencia relativa en el anio x log(anios / anios en que aparece). Sube los terminos propios de un anio
        # y baja los que aparecen siempre (gobierno, inversion), que no distinguen un informe de otro.
        en_anios = Counter(t for c in conteos.values() for t in c[tipo])
        for anio, c in sorted(conteos.items()):
            total = sum(c[tipo].values()) or 1
            puntajes = {t: (n / total) * np.log(n_anios / en_anios[t]) for t, n in c[tipo].items() if n >= 3}
            for termino in sorted(puntajes, key=puntajes.get, reverse=True)[:config.TERMINOS_POR_ANIO]:
                filas.append({"anio": anio, "tipo": tipo, "termino": termino, "frecuencia": c[tipo][termino],
                              "tfidf": round(puntajes[termino] * 1000, 3), "anios_con_termino": en_anios[termino]})
    return pd.DataFrame(filas)


# ---------------- clasificacion de causas por palabras clave ----------------
# La clasificacion de causas vive en nlp_causas.py (reglas, combinacion de fuentes y modelo de apoyo); aqui se re-exporta para no romper llamadas.
from nlp_causas import clasificar_causa, sin_contenido   # noqa: E402,F401


# ---------------- Fase 4: ejecutar ----------------
# Causales oficiales de la Contraloria y el grupo que deberian recibir (sirve para comprobar que las reglas funcionan)
PRUEBA_REGLAS = {
    "FALTA DE RECURSOS FINANCIEROS Y LIQUIDEZ": "recursos_financieros", "INCUMPLIMIENTO DE CONTRATO": "incumplimiento_contractual",
    "DISCREPANCIAS, CONTROVERSIAS Y ARBITRAJE": "controversias_arbitraje", "EVENTOS CLIMATICOS": "clima",
    "DEFICIENCIA EN EL EXPEDIENTE TECNICO": "expediente_tecnico", "CONFLICTOS SOCIALES": "conflictos_sociales",
    "DISPONIBILIDAD DE TERRENO": "terreno_saneamiento", "FALTA DE PERMISOS, LICENCIAS Y AUTORIZACIONES": "permisos_licencias",
    "INTERFERENCIAS": "interferencias", "ABANDONO DE OBRA": "incumplimiento_contractual",
    "INCUMPLIMIENTO DEL PAGO DE VALORIZACIONES U OTROS": "recursos_financieros",
    "DESABASTECIMIENTO SOSTENIDO DE MATERIALES": "materiales_logistica", "PANDEMIA COVID-19": "pandemia"}


def clasificar_fichas(fichas):
    """Agrega causa_grupo y causa_grupo_origen a la tabla de fichas de INFOBRAS."""
    comentarios = (fichas.comentario_fisico.fillna("") + " " + fichas.comentario_valorizado.fillna("")).str.strip()
    fichas = fichas.drop(columns=[c for c in ("causa_grupo", "causa_grupo_origen") if c in fichas])
    fichas["causa_grupo"] = [clasificar_causa(c, k) for c, k in zip(fichas.causal_paralizacion, comentarios)]

    def origen(causal, comentario, grupo):
        if grupo in ("otros", "sin_informacion"):
            return grupo
        return "causal" if clasificar_causa(causal, None) not in ("otros", "sin_informacion") else "comentario"

    fichas["causa_grupo_origen"] = [origen(c, k, g) for c, k, g in zip(fichas.causal_paralizacion, comentarios, fichas.causa_grupo)]
    return fichas, comentarios


def ejecutar_fase4():
    """Guarda citas_educacion.csv y frecuencia_terminos.csv, y agrega causa_grupo a fichas_infobras.csv con su validacion."""
    citas = citas_educacion()
    citas.to_csv(config.CITAS_EDUCACION, index=False, encoding="utf-8-sig")
    terminos = frecuencia_terminos()
    terminos.to_csv(config.FRECUENCIA_TERMINOS, index=False, encoding="utf-8-sig")
    log(f"Fase 4: {len(citas)} citas sobre educacion, {len(terminos)} filas de frecuencia de terminos")

    # las reglas deben reproducir el grupo de las causales oficiales
    fallas = [(c, esperado, clasificar_causa(c)) for c, esperado in PRUEBA_REGLAS.items() if clasificar_causa(c) != esperado]
    log(f"Fase 4: prueba de las reglas con {len(PRUEBA_REGLAS)} causales oficiales: {len(PRUEBA_REGLAS) - len(fallas)} correctas"
        + (f"; fallan {fallas}" if fallas else ""))

    if not config.INFOBRAS_SALIDA.exists():
        log("Fase 4: no hay fichas_infobras.csv todavia; se omite la clasificacion de causas")
        return citas, terminos, None
    fichas = pd.read_csv(config.INFOBRAS_SALIDA, dtype={"codigo_infobras": str, "cui": str, "ubigeo": str, "cod_departamento": str}, encoding="utf-8-sig")
    fichas["cod_departamento"] = fichas.cod_departamento.astype(str).str.zfill(2)   # codigo de 2 digitos como texto (se perdia el cero: "1" en vez de "01")
    fichas, comentarios = clasificar_fichas(fichas)
    import ubigeo_obras   # A1: agrega ubigeo y ubigeo_metodo; se recalcula en cada corrida
    fichas = ubigeo_obras.agregar_ubigeo(fichas)
    fichas.to_csv(config.INFOBRAS_SALIDA, index=False, encoding="utf-8-sig")
    porcentaje_otros = round(100 * (fichas.causa_grupo == "otros").mean(), 1)
    porcentaje_sin = round(100 * (fichas.causa_grupo == "sin_informacion").mean(), 1)
    log(f"Fase 4: {len(fichas)} fichas clasificadas; 'otros' = {porcentaje_otros} %, 'sin_informacion' = {porcentaje_sin} %; "
        f"grupos: {fichas.causa_grupo.value_counts().to_dict()}")
    muestra = fichas.assign(comentarios=comentarios.str[:300]).sample(min(30, len(fichas)), random_state=2026)
    muestra[["codigo_infobras", "causal_paralizacion", "comentarios", "causa_grupo", "causa_grupo_origen"]].to_csv(
        config.DOCS / "muestra_validacion_causas.csv", index=False, encoding="utf-8-sig")
    return citas, terminos, fichas
