"""Producto final: arma las tablas del tablero con todo lo que extrajo el proyecto y las une en UN SOLO CSV (dashboard.py -> data/final/dashboard_obras.csv).

Las cinco tablas intermedias (y producto_final.xlsx, una hoja por tabla + diccionario) quedan en data/interim/componentes:
  obras_maestra          una fila por obra de Educacion/Cultura (429): INFOBRAS + ubicacion con ubigeo + Contraloria + MEF + ESCALE
  resumen_region         una fila por region ENLA (26): obras paralizadas, causas, Contraloria, ESCALE (distritos) y ENLA
  serie_pais_educacion   cifras oficiales por corte: pais y sector Educacion (con la cifra corregida donde el PDF estaba mal)
  serie_educacion_departamento  obras de Educacion por departamento y corte (anexos Excel de la Contraloria)
  causales_por_corte     causales oficiales por corte, con el grupo de causa del proyecto
Cada tabla se valida (docs/validacion_final.csv) y su diccionario esta en DICCIONARIO_FINAL (se agrega a docs/diccionario.csv).
Nada de aqui inventa datos: todo sale de las tablas de data/processed; los campos derivados estan descritos.
"""
import re
import unicodedata

import numpy as np
import pandas as pd

import config
import contraloria_anexo03
import dashboard
import descarga_mef
import escale_ampliado
import escale_obras
import nlp_causas
import texto_nlp
import utils

GRUPOS_CAUSA = list(config.CAUSAS_REGLAS) + ["otros", "sin_informacion"]
MACROS_CAUSA = sorted(set(config.CAUSAS_MACRO.values()))
ULTIMO_CORTE = "2026-06-30"   # se recalcula en tiempo de ejecucion; esta constante solo documenta el valor actual
FUENTE_FINAL = "Producto final (derivado de las tablas de data/processed)"


def leer(nombre, carpeta=None):
    return pd.read_csv((carpeta or config.PROCESSED) / f"{nombre}.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")


def num(serie):
    return pd.to_numeric(serie, errors="coerce")


def booleano(serie):
    return serie.astype(str).str.lower().isin(["true", "1", "si", "sí"])


def sin_tildes(texto):
    return unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().upper().strip()


def region_enla(departamento, provincia):
    """Region como la usa ENLA: Lima se parte en Lima Metropolitana (provincia de Lima) y Lima Provincias."""
    if departamento == "LIMA":
        return "LIMA METROPOLITANA" if provincia == "LIMA" else "LIMA PROVINCIAS"
    return departamento


# ======================================================================================================
# Diccionario de las tablas finales: (columna, tipo, descripcion, unidad)
# ======================================================================================================
GRADOS_ENLA_EXTRA = [("2p", "2.° primaria"), ("6p", "6.° primaria")]   # ademas de 4.° primaria y 2.° secundaria (5.° secundaria: SICRECE no devuelve datos)
DICCIONARIO_ENLA_EXTRA = [fila for suf, gr in GRADOS_ENLA_EXTRA for fila in (
    (f"enla_{suf}_anio", "entero", f"Último año de la ENLA de {gr} disponible para la región.", "año"),
    (f"enla_{suf}_lectura_satisfactorio", "decimal", f"% en nivel Satisfactorio en Lectura, {gr}.", "%"),
    (f"enla_{suf}_matematica_satisfactorio", "decimal", f"% en nivel Satisfactorio en Matemática, {gr}.", "%"))]
DICCIONARIO_ANEXO03 = [(c, t, d + " Vacío = la obra no figura en el anexo 03 (corte mar-2026).", u) for c, t, d, u in contraloria_anexo03.DICCIONARIO
                       if c not in ("codigo_infobras", "corte_anexo03")]
DICCIONARIO_ESCALE_AMPLIADO = [("escale_" + c, t, d + " (distrito, Censo 2025)", u) for c, t, d, u in escale_ampliado.DICCIONARIO
                               if c not in ("anio", "ubigeo", "n_locales_publicos_ampliado")]
DICCIONARIO_FINAL = {
    "dashboard_obras": dashboard.DICCIONARIO,
    "escale_distrito_ampliado": escale_ampliado.DICCIONARIO,
    "escale_coordenadas_apoyo": [
        ("tipo", "texto", "local_obra (coordenada del local de ESCALE 2025 que declara el CUI de una obra) o centro_distrito (mediana de las coordenadas de los colegios del distrito, Padrón 2025).", "categoría"),
        ("clave", "texto", "CUI de la obra (si tipo = local_obra) o ubigeo de 6 dígitos del distrito (si tipo = centro_distrito).", "código"),
        ("lat", "decimal", "Latitud (grados decimales).", "grados"),
        ("lon", "decimal", "Longitud (grados decimales).", "grados"),
    ],
    "contraloria_servicios_control_obra": contraloria_anexo03.DICCIONARIO,
    "obras_maestra": [
        ("codigo_infobras", "texto", "Código de la obra en INFOBRAS (llave de la tabla).", "código"),
        ("cui", "texto", "Código Único de Inversiones.", "código"),
        ("nombre_obra", "texto", "Nombre de la obra.", "texto"),
        ("entidad", "texto", "Entidad pública responsable de la obra.", "texto"),
        ("origen", "texto", "Por qué la obra está en la tabla: infobras_paralizada_2026-10-27 (paralizada en INFOBRAS el 27-oct) o contraloria_educacion_2026-06 (Educación/Cultura en la lista de la Contraloría de jun-2026 y no paralizada en INFOBRAS el 27-oct).", "categoría"),
        ("cod_departamento", "texto de 2 dígitos", "Código INEI del departamento del ubigeo.", "código"),
        ("departamento", "texto", "Departamento del ubigeo, en mayúsculas y sin tildes (corregido: 2 obras que INFOBRAS publica en Huancavelica son de Ica).", "texto"),
        ("provincia", "texto", "Provincia como la publica INFOBRAS (mayúsculas, sin tildes). Para el nombre oficial usar el ubigeo.", "texto"),
        ("distrito", "texto", "Distrito como lo publica INFOBRAS (mayúsculas, sin tildes). Para el nombre oficial usar el ubigeo.", "texto"),
        ("ubigeo", "texto de 6 dígitos", "Ubigeo INEI del distrito de la obra (asignado por nombre contra ESCALE; 4 obras a mano).", "código"),
        ("ubigeo_metodo", "texto", "Cómo se asignó el ubigeo: exacto, normalizado o manual.", "categoría"),
        ("region_enla", "texto", "Región ENLA de la obra (Lima se parte en LIMA METROPOLITANA, la provincia de Lima, y LIMA PROVINCIAS). Llave para unir con resumen_region.", "texto"),
        ("latitud", "decimal", "Latitud de la obra según INFOBRAS (vacía en las obras sin coordenadas).", "grados"),
        ("longitud", "decimal", "Longitud de la obra según INFOBRAS.", "grados"),
        ("latitud_mapa", "decimal", "Latitud para el mapa: la de INFOBRAS; si INFOBRAS no la tiene, la del local de ESCALE que declara el CUI de la obra o, si no, el centro de los colegios del distrito (Padrón ESCALE 2025). Ver coordenada_origen.", "grados"),
        ("longitud_mapa", "decimal", "Longitud para el mapa (mismo criterio que latitud_mapa).", "grados"),
        ("coordenada_origen", "texto", "De dónde sale latitud_mapa/longitud_mapa: infobras (exacta), escale_local_obra (aproximada: local escolar que declara el CUI de la obra), centro_distrito_escale (aproximada: mediana de los colegios del distrito; en las obras que sí tienen coordenadas queda a ~3 km de mediana de la real) o vacío.", "categoría"),
        ("estado_infobras", "texto", "Estado de la obra en su ficha de INFOBRAS el día de la lectura (PARALIZADA, EN EJECUCIÓN, FINALIZADO, SIN EJECUCIÓN).", "categoría"),
        ("paralizada_hoy", "lógico", "TRUE si estado_infobras es PARALIZADA.", "lógico"),
        ("fecha_lectura_infobras", "fecha AAAA-MM-DD", "Día en que se leyó la ficha (2026-11-11).", "fecha"),
        ("modalidad", "texto", "Modalidad de ejecución según INFOBRAS.", "texto"),
        ("naturaleza", "texto", "Naturaleza de la obra según INFOBRAS.", "texto"),
        ("tipo_obra", "texto", "Tipo de obra según INFOBRAS.", "texto"),
        ("tipo_infraestructura", "texto", "Tipo de infraestructura según el nombre de la obra (reglas; si el nombre no lo dice, el tipo de obra de INFOBRAS): educacion_basica (colegios, inicial, CEBA, CETPRO), educacion_superior (universidades e institutos), deportiva_recreativa, cultural_patrimonio u otra. INFOBRAS agrupa Educación y Cultura.", "categoría"),
        ("monto_expediente_tecnico", "decimal", "Monto del expediente técnico (listado de INFOBRAS).", "soles"),
        ("monto_ejecucion_acumulado", "decimal", "Monto de ejecución acumulado según INFOBRAS.", "soles"),
        ("avance_fisico_pct", "decimal", "Avance físico del encabezado de la ficha de INFOBRAS.", "%"),
        ("fecha_inicio", "fecha AAAA-MM-DD", "Fecha de inicio de la obra.", "fecha"),
        ("fecha_fin_prevista", "fecha AAAA-MM-DD", "Fecha de fin prevista de la obra.", "fecha"),
        ("n_avances_infobras", "entero", "Número de avances mensuales registrados en INFOBRAS.", "avances"),
        ("meses_paralizado", "entero", "Meses en estado Paralizado en la tabla de avances de INFOBRAS.", "meses"),
        ("n_tramos_paralizacion", "entero", "Número de tramos seguidos de meses paralizados (más de uno = se reactivó y volvió a paralizar).", "tramos"),
        ("primer_mes_paralizado", "texto AAAA-MM", "Primer mes en estado Paralizado.", "mes"),
        ("ultimo_mes_paralizado", "texto AAAA-MM", "Último mes en estado Paralizado.", "mes"),
        ("fecha_paralizacion", "fecha AAAA-MM-DD", "Fecha de paralización del último avance paralizado.", "fecha"),
        ("dias_paralizado", "entero", "Valor «días paralizado» del detalle del último avance paralizado de INFOBRAS. OJO: en casi todas las obras vale 30 o 31 (los días de ese mes del informe), no el tiempo total; para el tiempo total usar dias_desde_paralizacion.", "días"),
        ("dias_desde_paralizacion", "entero", "Días entre fecha_paralizacion y la lectura de INFOBRAS (11-nov-2026), solo en las obras paralizadas hoy: cuánto tiempo lleva detenida la obra en su paralización actual.", "días"),
        ("causa_grupo_infobras", "texto", "Grupo de causa de los comentarios de INFOBRAS de la obra (todos los meses paralizados leídos; los del último tramo pesan más). sin_informacion si no hay comentario útil.", "categoría"),
        ("causal_oficial_contraloria", "texto", "Causal de paralización de la Contraloría en el último corte en que aparece la obra (puede ser antigua).", "texto"),
        ("causa_grupo_contraloria", "texto", "Grupo de causa asignado a la causal oficial con las mismas reglas (la causal «OTROS» queda en otros).", "categoría"),
        ("causa_grupo_mef", "texto", "Grupo de causa asignado al texto de la última problemática registrada en el MEF (mef_ult_problema), con las mismas reglas.", "categoría"),
        ("causa_grupo_final", "texto", "Causa principal de la obra (NLP): se suman los puntajes de las tres fuentes con pesos (causal oficial 3, comentarios del último tramo 2, problemática del MEF 1.5, comentarios de tramos anteriores 0.5). Los grupos de estado (obra_concluida_o_en_marcha, sin_restricciones) solo se asignan si no hay ninguna causa real. otros = hay texto sin causa reconocible o la causal oficial es «OTROS»; sin_informacion = no hay texto.", "categoría"),
        ("causa_macro", "texto", "Agrupación de causa_grupo_final en 8 categorías para el tablero: financiera, contractual_y_legal, tecnica, logistica, entorno_social_y_territorial, fuerza_mayor, sin_causa_de_paralizacion, sin_clasificar.", "categoría"),
        ("causas_secundarias", "texto", "Hasta 2 causas más que también aparecen en los textos (con al menos la mitad del puntaje de la principal), separadas por «|». Vacío si no hay.", "categoría"),
        ("causa_fuente", "texto", "Fuente que más aportó a la causa principal: infobras_comentario, contraloria_causal, mef_problema, texto_libre (modelo) o sin_causa_clara.", "categoría"),
        ("causa_confianza", "texto", "alta = al menos dos fuentes distintas apuntan a la misma causa; media = una sola fuente; baja = solo la sugirió el modelo; vacío = sin causa.", "categoría"),
        ("causa_metodo", "texto", "reglas = palabras clave; modelo = TF-IDF + regresión logística (solo cuando las reglas no encontraron nada y la probabilidad es ≥ 0.60).", "categoría"),
        ("en_ultimo_corte_contraloria", "lógico", "TRUE si la obra está en la lista de la Contraloría del último corte (jun-2026).", "lógico"),
        ("primer_corte_contraloria", "fecha AAAA-MM-DD", "Primer corte (entre los 13 con base obra por obra, sep-2023 a jun-2026) en que aparece la obra.", "fecha"),
        ("ultimo_corte_contraloria", "fecha AAAA-MM-DD", "Último corte en que aparece la obra.", "fecha"),
        ("n_cortes_contraloria", "entero", "Cantidad de cortes (de 13) en que aparece la obra.", "cortes"),
        ("reingresos_contraloria", "entero", "Veces que la obra salió de la lista y volvió a entrar.", "veces"),
        ("primer_corte_censurado", "lógico", "TRUE si la obra ya estaba en el primer corte (sep-2023): su fecha de entrada real es anterior y no se conoce.", "lógico"),
        ("nivel_gobierno", "texto", "Nivel de gobierno de la entidad según la Contraloría (último corte).", "categoría"),
        ("sector_agrupado", "texto", "Sector agrupado según la Contraloría (último corte).", "categoría"),
        ("evento_contraloria", "texto", "Evento registrado en INFOBRAS según la Contraloría (último corte).", "categoría"),
        ("costo_actualizado_soles", "decimal", "Costo actualizado de la inversión (Invierte.pe) en el último corte.", "soles"),
        ("saldo_inversion_soles", "decimal", "Saldo de inversión por ejecutar en el último corte.", "soles"),
        ("estado_mef", "texto", "Estado de la inversión en el Formato 12-B del MEF.", "categoría"),
        ("ultimo_devengado", "texto AAAAMM", "Periodo del último devengado de la inversión registrado en el SIAF (MEF).", "periodo"),
        ("devengado_total_soles", "decimal", "Devengado acumulado hasta el año anterior más el del año actual (MEF).", "soles"),
        ("devengado_anio_actual_soles", "decimal", "Devengado del año actual (MEF).", "soles"),
        ("pim_anio_actual_soles", "decimal", "Presupuesto Institucional Modificado del año actual (MEF).", "soles"),
        ("pct_devengado_del_costo", "decimal", "devengado_total_soles / costo_actualizado_soles. Puede pasar de 100 si los costos no son comparables.", "%"),
        ("avance_fisico_mef_pct", "decimal", "Avance físico declarado en el Formato 12-B (MEF).", "%"),
        ("mef_ult_problema", "texto", "Última problemática registrada en el Formato 12-B (texto libre de la entidad).", "texto"),
        ("escale_anio", "entero", "Año del Censo Educativo usado para los indicadores del distrito.", "año"),
        ("escale_locales_publicos", "entero", "Locales educativos públicos del distrito (ESCALE).", "locales"),
        ("escale_pct_3_servicios", "decimal", "% de locales públicos del distrito con agua, desagüe y electricidad de red pública.", "%"),
        ("escale_pct_rural", "decimal", "% de locales públicos del distrito en zona rural.", "%"),
        ("escale_pct_riesgo_estructural", "decimal", "% de locales con al menos una edificación en riesgo estructural.", "%"),
        ("escale_pct_estructura_mal_estado", "decimal", "% de locales con estructura en mal estado.", "%"),
        ("escale_n_locales_obra", "entero", "Locales que declaran en el Censo 2025 estar en construcción con el CUI de esta obra (0 = ninguno).", "locales"),
        ("escale_codlocal", "texto", "Código del primer local de ESCALE que declara el CUI de esta obra.", "código"),
        *DICCIONARIO_ESCALE_AMPLIADO,
        *DICCIONARIO_ANEXO03,
    ],
    "resumen_region": [
        ("region_enla", "texto", "Región ENLA (26: los 24 departamentos sin Lima + Callao + LIMA METROPOLITANA + LIMA PROVINCIAS). Llave.", "texto"),
        ("cod_departamento", "texto de 2 dígitos", "Código INEI del departamento (Lima Metropolitana y Provincias = 15).", "código"),
        ("obras_en_tabla", "entero", "Obras de obras_maestra en la región.", "obras"),
        ("obras_paralizadas_hoy", "entero", "Obras con estado PARALIZADA en INFOBRAS el 2026-11-11.", "obras"),
        ("monto_expediente_paralizadas", "decimal", "Suma del expediente técnico de las obras paralizadas hoy.", "soles"),
        ("monto_ejecutado_paralizadas", "decimal", "Suma del monto de ejecución acumulado de las obras paralizadas hoy.", "soles"),
        ("dias_paralizado_mediana", "decimal", "Mediana de días paralizada de las obras paralizadas hoy.", "días"),
        ("avance_fisico_mediano", "decimal", "Mediana del avance físico de las obras paralizadas hoy.", "%"),
        *[(f"paralizadas_causa_{g}", "entero", f"Obras paralizadas hoy cuyo causa_grupo_final es {g}.", "obras") for g in GRUPOS_CAUSA],
        ("contraloria_obras_educacion", "entero", "Obras del sector Educación en la lista de la Contraloría del último corte.", "obras"),
        ("contraloria_costo_educacion_soles", "decimal", "Costo actualizado de esas obras.", "soles"),
        ("escale_anio", "entero", "Año del Censo Educativo usado (el más reciente).", "año"),
        ("escale_locales_publicos", "entero", "Locales educativos públicos de la región.", "locales"),
        ("escale_pct_3_servicios", "decimal", "% de locales con agua, desagüe y electricidad de red pública (ponderado por locales con dato).", "%"),
        ("escale_pct_rural", "decimal", "% de locales rurales (ponderado por locales).", "%"),
        ("escale_pct_riesgo_estructural", "decimal", "% de locales con riesgo estructural (ponderado por locales con dato de edificaciones).", "%"),
        ("escale_pct_estructura_mal_estado", "decimal", "% de locales con estructura en mal estado (ponderado igual).", "%"),
        ("enla_4p_anio", "entero", "Último año de la ENLA de 4.° primaria disponible para la región.", "año"),
        ("enla_4p_lectura_satisfactorio", "decimal", "% en nivel Satisfactorio en Lectura, 4.° primaria.", "%"),
        ("enla_4p_matematica_satisfactorio", "decimal", "% en nivel Satisfactorio en Matemática, 4.° primaria.", "%"),
        ("enla_2s_anio", "entero", "Último año de la ENLA de 2.° secundaria disponible para la región.", "año"),
        ("enla_2s_lectura_satisfactorio", "decimal", "% en nivel Satisfactorio en Lectura, 2.° secundaria.", "%"),
        ("enla_2s_matematica_satisfactorio", "decimal", "% en nivel Satisfactorio en Matemática, 2.° secundaria.", "%"),
        *DICCIONARIO_ENLA_EXTRA,
    ],
    "serie_pais_educacion": [
        ("fecha_corte", "fecha AAAA-MM-DD", "Fecha de corte del informe de la Contraloría.", "fecha"),
        ("anio", "entero", "Año de la fecha de corte.", "año"),
        ("obras_pais", "entero", "Obras paralizadas en el país.", "obras"),
        ("costo_pais_soles", "decimal", "Costo actualizado de las obras paralizadas del país.", "soles"),
        ("saldo_pais_soles", "decimal", "Saldo de inversión por ejecutar del país.", "soles"),
        ("obras_educacion_pdf", "entero", "Obras del sector Educación según la tabla de sectores del PDF.", "obras"),
        ("costo_educacion_pdf_soles", "decimal", "Costo actualizado del sector Educación según el PDF.", "soles"),
        ("obras_educacion", "entero", "Obras del sector Educación a usar: la del anexo Excel donde el PDF está mal (set-2023 y set-2025) y la del PDF en el resto.", "obras"),
        ("educacion_corregida", "lógico", "TRUE si obras_educacion difiere de la cifra del PDF porque el PDF está mal (set-2023 y set-2025).", "lógico"),
        ("fuente_obras_educacion", "texto", "De dónde sale obras_educacion: el anexo Excel de la Contraloría o el informe PDF (cuando no hay Excel para contrastar).", "texto"),
        ("pct_educacion_obras", "decimal", "obras_educacion / obras_pais.", "%"),
        ("fuente_pdf", "texto", "PDF del informe.", "texto"),
    ],
    "serie_educacion_departamento": [
        ("fecha_corte", "fecha AAAA-MM-DD", "Fecha de corte del informe.", "fecha"),
        ("anio", "entero", "Año de la fecha de corte.", "año"),
        ("cod_departamento", "texto de 2 dígitos", "Código INEI del departamento.", "código"),
        ("departamento", "texto", "Departamento en mayúsculas y sin tildes.", "texto"),
        ("obras_educacion", "entero", "Obras paralizadas del sector Educación (agrupación del informe).", "obras"),
        ("costo_educacion_soles", "decimal", "Costo actualizado de esas obras.", "soles"),
        ("obras_educacion_estricto", "entero", "Obras cuyo sector es exactamente EDUCACION (sin Cultura).", "obras"),
        ("costo_educacion_estricto_soles", "decimal", "Costo actualizado de esas obras.", "soles"),
        ("fuente_excel", "texto", "Anexo Excel de la Contraloría del que se calcula.", "texto"),
    ],
    "causales_por_corte": [
        ("fecha_corte", "fecha AAAA-MM-DD", "Fecha de corte del informe.", "fecha"),
        ("anio", "entero", "Año de la fecha de corte.", "año"),
        ("causal", "texto", "Causal de paralización declarada por la entidad (el catálogo cambió entre informes).", "texto"),
        ("causa_grupo", "texto", "Grupo de causa del proyecto asignado a esa causal (mismas reglas que las obras).", "categoría"),
        ("causa_macro", "texto", "Macro-categoría del grupo de causa (financiera, contractual_y_legal, tecnica, logistica, entorno_social_y_territorial, fuerza_mayor, sin_causa_de_paralizacion, sin_clasificar).", "categoría"),
        ("obras_paralizadas", "entero", "Obras con esa causal.", "obras"),
        ("pct_obras", "decimal", "Porcentaje de las obras del corte, como lo publica el informe.", "%"),
        ("costo_actualizado_soles", "decimal", "Costo actualizado de esas obras.", "soles"),
        ("saldo_inversion_soles", "decimal", "Saldo de inversión de esas obras.", "soles"),
        ("fuente_pdf", "texto", "PDF del informe.", "texto"),
        ("pagina", "entero", "Página del PDF.", "página"),
    ],
}


# ======================================================================================================
# Construccion
# ======================================================================================================
# ---- tipo de infraestructura (INFOBRAS mezcla colegios, universidades, estadios y sitios arqueologicos en "Educacion/Cultura") ----
def _sin_tildes(t): return unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode().upper()
REGLAS_INFRAESTRUCTURA = [
    ("educacion_superior", r"UNIVERSID|UNIVERSITARI|\bFACULTAD|\bUNI\b|\bUNMSM\b|\bUNFV\b|\bUNSAAC\b|EDUCACION SUPERIOR|\bIEST?P\b|\bISTP?\b|INSTITUTO (DE EDUCACION SUPERIOR|SUPERIOR|PEDAGOGICO|TECNOLOGICO)|PEDAGOGICA|CEPREUNI|SENCICO|ESCUELAS? (DE FORMACION )?PROFESIONAL|ESCUELA SUPERIOR|CARRERA PROFESIONAL|\bI\.?\s?E\.?\s?S\.?\s?T\.?\s?P"),
    ("educacion_basica", r"INSTITUCI\w* EDUCATIV|\bI\.\s?E\b\.?|\bI\.E\.[IPS]\b|\bIE[IPS]?\b|\bI\.?E\.?\s?N[°ºRO.]*\s*\d|IEGECOM|\bCEI\b|\bPRONOEI|COLEGIO|CENTRO EDUCATIVO|LOCAL ESCOLAR|CODIGO (DE )?LOCAL|ESCUELA|JARDIN (DE NINOS|INFANTIL|N)|\bCUNA|\bCEBA\b|\bCETPRO|INFRAESTRUCTURA EDUCATIVA|SERVICIOS? EDUCATIVO|SERVICIO DE EDUCACION (INICIAL|PRIMARIA|SECUNDARIA|BASICA)|EDUCACION (INICIAL|PRIMARIA|SECUNDARIA|BASICA)|\bINICIAL\b|\bPRIMARIA\b|\bSECUNDARIA\b|AULAS? (PEDAGOGIC|EDUCATIV)"),
    ("deportiva_recreativa", r"DEPORT|ESTADIO|COLISEO|\bLOSA|\bLOZA|POLIDEPORTIV|GRAS+ SINTETIC|PISCINA|RECREA|PARQUE ZONAL|PARQUE RECREATIV|PLAZA DE TOROS|CANCHA|CAMPO MENOR|AREAS VERDES|ESPACIOS? PUBLICOS?"),
    ("cultural_patrimonio", r"CULTUR|MUSEO|BIBLIOTECA|ARQUEOLOG|MONUMENT|\bHUACA|PREHISPANIC|SITIO HISTORICO|ANFITEATRO|TEATRO|INTERPRETACION|PATRIMONIO|PUESTA EN VALOR"),
]
INFRAESTRUCTURA_POR_TIPO_OBRA = {"CENTRO EDUCATIVO/COLEGIO": "educacion_basica", "AULAS": "educacion_basica", "CUNA/JARDIN": "educacion_basica",
                 "INSTITUTO": "educacion_superior", "ESCUELA PROFESIONAL": "educacion_superior", "COMPLEJO DEPORTIVO": "deportiva_recreativa",
                 "ESTADIO": "deportiva_recreativa", "LOSA DEPORTIVA": "deportiva_recreativa", "COLISEO": "deportiva_recreativa",
                 "POLIDEPORTIVO": "deportiva_recreativa", "COMPLEJO RECREACIONAL": "deportiva_recreativa", "CASA Y CENTRO DE CULTURA": "cultural_patrimonio"}
def tipo_infraestructura(nombre, tipo_obra=""):
    """Clasifica la obra por su nombre (reglas en orden; la primera que coincide gana) y, si el nombre no dice nada, por el tipo de obra de
    INFOBRAS. INFOBRAS agrupa Educacion y Cultura: aqui se separa lo escolar de lo universitario, deportivo y cultural."""
    t = _sin_tildes(nombre)
    for tipo, patron in REGLAS_INFRAESTRUCTURA:
        if re.search(patron, t):
            return tipo
    return INFRAESTRUCTURA_POR_TIPO_OBRA.get(_sin_tildes(tipo_obra).strip(), "otra")


def coordenadas_mapa(m, con_cui):
    """Agrega latitud_mapa, longitud_mapa y coordenada_origen. No toca latitud/longitud (son las de INFOBRAS).

    Orden: 1) INFOBRAS; 2) local(es) de ESCALE 2025 que declaran el CUI de la obra (mediana de sus coordenadas, loc_lineal_1);
    3) centro del distrito = mediana de las coordenadas de los colegios del distrito (Padron 2025). Lee data/raw sin modificarlo.
    """
    import extraccion
    dentro = lambda t: t[t.lat.between(-18.6, 0.1) & t.lon.between(-81.4, -68.4)]
    la, lo = num(m.latitud), num(m.longitud)
    origen = pd.Series(np.where(la.notna() & lo.notna(), "infobras", ""), index=m.index)
    try:
        loc = utils.leer_dbf(extraccion.dbf_de_zip("escale", 2025, config.ESCALE_ZIP_LINEAL), columnas=["CODLOCAL", "LATITUD", "LONGITUD"])
        loc = dentro(loc.assign(lat=num(loc.LATITUD), lon=num(loc.LONGITUD)))
        loc = con_cui.merge(loc, left_on="codlocal", right_on="CODLOCAL").groupby("cui")[["lat", "lon"]].median()
        pad = utils.leer_dbf(extraccion.dbf_de_zip("escale", 2025, config.ESCALE_ZIP_PADRON), columnas=["CODGEO", "NLAT_IE", "NLONG_IE"])
        cen = dentro(pad.assign(lat=num(pad.NLAT_IE), lon=num(pad.NLONG_IE))).groupby("CODGEO")[["lat", "lon"]].median()
        apoyo = pd.concat([loc.reset_index().rename(columns={"cui": "clave"}).assign(tipo="local_obra"),
                           cen.reset_index().rename(columns={"CODGEO": "clave"}).assign(tipo="centro_distrito")])[["tipo", "clave", "lat", "lon"]]
        apoyo[["lat", "lon"]] = apoyo[["lat", "lon"]].round(6)
        apoyo.to_csv(config.PROCESSED / "escale_coordenadas_apoyo.csv", index=False, encoding="utf-8-sig")   # se reusa si no hay datos crudos
    except (FileNotFoundError, KeyError, ValueError) as e:
        ruta_apoyo = config.PROCESSED / "escale_coordenadas_apoyo.csv"
        if ruta_apoyo.exists():
            utils.log(f"COORDENADAS: no hay datos crudos de ESCALE ({type(e).__name__}); se usa escale_coordenadas_apoyo.csv ya calculado")
            apoyo = pd.read_csv(ruta_apoyo, dtype={"tipo": str, "clave": str}, encoding="utf-8-sig")
            loc = apoyo[apoyo.tipo == "local_obra"].set_index("clave")[["lat", "lon"]]
            cen = apoyo[apoyo.tipo == "centro_distrito"].set_index("clave")[["lat", "lon"]]
        else:
            utils.log(f"AVISO COORDENADAS: no se pudo leer ESCALE ({type(e).__name__}: {e}); el mapa usa solo las coordenadas de INFOBRAS")
            loc = cen = pd.DataFrame(columns=["lat", "lon"])
    for nombre, tabla, clave in (("escale_local_obra", loc, "cui"), ("centro_distrito_escale", cen, "ubigeo")):
        la2, lo2 = m[clave].map(tabla.lat), m[clave].map(tabla.lon)
        usar = (la.isna() | lo.isna()) & la2.notna() & lo2.notna()
        la, lo, origen = la.where(~usar, la2), lo.where(~usar, lo2), origen.where(~usar, nombre)
    m["latitud_mapa"], m["longitud_mapa"] = la.round(6), lo.round(6)
    m["coordenada_origen"] = origen.replace("", np.nan)
    utils.log(f"COORDENADAS: {origen.replace('', 'sin_coordenadas').value_counts().to_dict()}")
    return m


def tabla_maestra():
    fi = leer("infobras_fichas_ampliadas")
    pan = leer("contraloria_obras_panel")
    oc = leer("contraloria_obras_corte")
    par = leer("infobras_paralizaciones")
    f198 = leer("fichas_infobras")
    mef = leer("mef_f12b_obras") if (config.PROCESSED / "mef_f12b_obras.csv").exists() else pd.DataFrame(columns=["cui"])
    esc = leer("escale_infraestructura")
    eobra = leer("escale_obras_en_local") if (config.PROCESSED / "escale_obras_en_local.csv").exists() else pd.DataFrame(columns=["cui", "codlocal"])

    m = fi.rename(columns={"estado": "estado_infobras", "fecha_lectura": "fecha_lectura_infobras", "n_avances": "n_avances_infobras",
                           "n_paralizados": "meses_paralizado"}).copy()
    m["paralizada_hoy"] = m.estado_infobras.str.upper() == "PARALIZADA"
    m["region_enla"] = [region_enla(d, p) for d, p in zip(m.departamento, m.provincia)]

    # tramos de paralizacion (de la tabla de avances paralizados de INFOBRAS)
    par = par.assign(mes_txt=par.anio + "-" + par.mes.str.zfill(2))
    tramos = par.groupby("codigo_infobras").agg(n_tramos_paralizacion=("tramo", "nunique"), primer_mes_paralizado=("mes_txt", "min"),
                                                ultimo_mes_paralizado=("mes_txt", "max"))
    m = m.join(tramos, on="codigo_infobras")

    # Contraloria: panel (cuantos cortes, reingresos) + ultimo registro de cada obra
    pan = pan.rename(columns={"primer_corte": "primer_corte_contraloria", "ultimo_corte": "ultimo_corte_contraloria",
                              "n_cortes": "n_cortes_contraloria", "reingresos": "reingresos_contraloria",
                              "sigue_en_ultimo_corte": "en_ultimo_corte_contraloria", "causal_paralizacion_ultimo": "causal_oficial_contraloria",
                              "nivel_gobierno_ultimo": "nivel_gobierno", "sector_agrupado_ultimo": "sector_agrupado"})
    m = m.merge(pan[["codigo_infobras", "primer_corte_contraloria", "ultimo_corte_contraloria", "n_cortes_contraloria", "reingresos_contraloria",
                     "en_ultimo_corte_contraloria", "primer_corte_censurado", "causal_oficial_contraloria", "nivel_gobierno", "sector_agrupado"]],
                on="codigo_infobras", how="left")
    ultimo = oc.sort_values("corte").groupby("codigo_infobras").tail(1)[["codigo_infobras", "evento", "costo_actualizado_soles", "saldo_inversion_soles"]]
    m = m.merge(ultimo.rename(columns={"evento": "evento_contraloria"}), on="codigo_infobras", how="left")


    # MEF (devengado por CUI)
    columnas_mef = ["cui", "estado_mef", "ultimo_devengado", "devengado_total_soles", "devengado_anio_actual_soles", "pim_anio_actual_soles",
                    "avance_fisico_mef_pct", "ult_problema"]
    for c in columnas_mef:
        if c not in mef:
            mef[c] = ""
    m = m.merge(mef[columnas_mef].rename(columns={"ult_problema": "mef_ult_problema"}), on="cui", how="left")
    # causas: NLP sobre los tres textos (comentarios de INFOBRAS de todas las obras, causal oficial y problematica del MEF)
    m, metricas_nlp = nlp_causas.clasificar_maestra(m, par, mef)
    metricas_nlp.to_csv(config.DOCS / "nlp_causas_metricas.csv", index=False, encoding="utf-8-sig")
    costo = num(m.costo_actualizado_soles)
    m["pct_devengado_del_costo"] = np.where(costo > 0, (100 * num(m.devengado_total_soles) / costo).round(2), np.nan)

    # ESCALE: indicadores del distrito (anio mas reciente de cada distrito) y local que declara el CUI
    esc = esc.assign(anio_n=num(esc.anio)).sort_values("anio_n").drop_duplicates("ubigeo", keep="last")
    esc = esc.rename(columns={"anio": "escale_anio", "n_locales_publicos": "escale_locales_publicos", "pct_3_servicios": "escale_pct_3_servicios",
                              "pct_rural": "escale_pct_rural", "pct_riesgo_estructural": "escale_pct_riesgo_estructural",
                              "pct_estructura_mal_estado": "escale_pct_estructura_mal_estado"})
    m = m.merge(esc[["ubigeo", "escale_anio", "escale_locales_publicos", "escale_pct_3_servicios", "escale_pct_rural",
                     "escale_pct_riesgo_estructural", "escale_pct_estructura_mal_estado"]], on="ubigeo", how="left")
    amp = leer("escale_distrito_ampliado").drop(columns=["anio", "n_locales_publicos_ampliado"])   # indicadores extra de ESCALE 2025 por distrito
    m = m.merge(amp.rename(columns={c: "escale_" + c for c in amp.columns if c != "ubigeo"}), on="ubigeo", how="left")
    sc = leer("contraloria_servicios_control_obra").drop(columns="corte_anexo03")   # servicios de control por obra (anexo 03 de la Contraloria)
    m = m.merge(sc, on="codigo_infobras", how="left")
    con_cui = eobra[eobra.cui != ""]
    por_cui = con_cui.groupby("cui").agg(escale_n_locales_obra=("codlocal", "nunique"), escale_codlocal=("codlocal", "first"))
    m = m.join(por_cui, on="cui")
    m["escale_n_locales_obra"] = m.escale_n_locales_obra.fillna(0)
    m = coordenadas_mapa(m, con_cui)
    # Tiempo total paralizada: el campo "dias paralizado" de INFOBRAS es casi siempre 30/31 (dias del mes del informe), no el total
    lectura, desde = pd.to_datetime(m.fecha_lectura_infobras, errors="coerce"), pd.to_datetime(m.fecha_paralizacion, errors="coerce")
    m["dias_desde_paralizacion"] = (lectura - desde).dt.days.where(m.paralizada_hoy & desde.notna() & (desde <= lectura))
    m["tipo_infraestructura"] = [tipo_infraestructura(n, t) for n, t in zip(m.nombre_obra, m.tipo_obra)]
    utils.log(f"TIPO DE INFRAESTRUCTURA: {m.tipo_infraestructura.value_counts().to_dict()}")

    columnas = [c for c, *_ in DICCIONARIO_FINAL["obras_maestra"]]
    faltan = [c for c in columnas if c not in m]
    if faltan:
        raise KeyError(f"obras_maestra: faltan columnas {faltan}")
    m = m[columnas].copy()
    for c in ("latitud", "longitud", "latitud_mapa", "longitud_mapa", "monto_expediente_tecnico", "monto_ejecucion_acumulado", "avance_fisico_pct", "costo_actualizado_soles",
              "saldo_inversion_soles", "devengado_total_soles", "devengado_anio_actual_soles", "pim_anio_actual_soles", "avance_fisico_mef_pct",
              "escale_pct_3_servicios", "escale_pct_rural", "escale_pct_riesgo_estructural", "escale_pct_estructura_mal_estado"):
        m[c] = num(m[c])
    for c, *_ in DICCIONARIO_ESCALE_AMPLIADO + DICCIONARIO_ANEXO03:
        m[c] = num(m[c])
    for c in ("n_avances_infobras", "meses_paralizado", "n_tramos_paralizacion", "dias_paralizado", "dias_desde_paralizacion", "n_cortes_contraloria", "reingresos_contraloria",
              "escale_locales_publicos", "escale_anio", "escale_n_locales_obra"):
        m[c] = num(m[c]).round().astype("Int64")
    for c in ("en_ultimo_corte_contraloria", "primer_corte_censurado"):
        m[c] = booleano(m[c])
    return m.sort_values(["origen", "codigo_infobras"]).reset_index(drop=True)


def _ponderado(grupo, columna, peso):
    w = grupo[peso].astype(float)
    ok = grupo[columna].notna() & (w > 0)
    return round(float((grupo.loc[ok, columna] * w[ok]).sum() / w[ok].sum()), 2) if w[ok].sum() > 0 else np.nan


def resumen_region(m):
    niveles = leer("enla_niveles_logro")
    regiones = niveles[["region_clave", "cod_departamento"]].drop_duplicates().rename(columns={"region_clave": "region_enla"})
    out = regiones.copy().set_index("region_enla")
    g = m.groupby("region_enla")
    out["obras_en_tabla"] = g.size()
    hoy = m[m.paralizada_hoy]
    gh = hoy.groupby("region_enla")
    out["obras_paralizadas_hoy"] = gh.size()
    out["monto_expediente_paralizadas"] = gh.monto_expediente_tecnico.sum()
    out["monto_ejecutado_paralizadas"] = gh.monto_ejecucion_acumulado.sum()
    out["dias_paralizado_mediana"] = gh.dias_paralizado.apply(lambda s: s.astype(float).median())
    out["avance_fisico_mediano"] = gh.avance_fisico_pct.median()
    por_causa = hoy.groupby(["region_enla", "causa_grupo_final"]).size().unstack(fill_value=0)
    for grupo in GRUPOS_CAUSA:
        out[f"paralizadas_causa_{grupo}"] = por_causa[grupo] if grupo in por_causa else 0
    # Contraloria: Educacion en el ultimo corte (de la base obra por obra)
    oc = leer("contraloria_obras_corte")
    oc = oc[(oc.corte == oc.corte.max()) & (oc.sector_agrupado == "EDUCACION")].copy()
    oc["region_enla"] = [region_enla(d, p) for d, p in zip(oc.departamento, oc.provincia)]
    out["contraloria_obras_educacion"] = oc.groupby("region_enla").size()
    out["contraloria_costo_educacion_soles"] = oc.assign(c=num(oc.costo_actualizado_soles)).groupby("region_enla").c.sum()
    # ESCALE: distritos del anio mas reciente agregados a la region
    esc = leer("escale_infraestructura")
    esc = esc[esc.anio == esc.anio.max()].copy()
    for c in ("n_locales_publicos", "n_locales_sin_dato", "pct_3_servicios", "pct_rural", "n_locales_con_dato_edif", "pct_riesgo_estructural", "pct_estructura_mal_estado"):
        esc[c] = num(esc[c])
    esc["con_dato"] = esc.n_locales_publicos - esc.n_locales_sin_dato
    esc["region_enla"] = [region_enla(d, p) for d, p in zip(esc.departamento, esc.provincia)]
    ge = esc.groupby("region_enla")
    out["escale_anio"] = int(esc.anio.max())
    out["escale_locales_publicos"] = ge.n_locales_publicos.sum()
    out["escale_pct_3_servicios"] = ge.apply(lambda x: _ponderado(x, "pct_3_servicios", "con_dato"))
    out["escale_pct_rural"] = ge.apply(lambda x: _ponderado(x, "pct_rural", "n_locales_publicos"))
    out["escale_pct_riesgo_estructural"] = ge.apply(lambda x: _ponderado(x, "pct_riesgo_estructural", "n_locales_con_dato_edif"))
    out["escale_pct_estructura_mal_estado"] = ge.apply(lambda x: _ponderado(x, "pct_estructura_mal_estado", "n_locales_con_dato_edif"))
    # ENLA: ultimo anio de cada grado
    for sufijo, grado in (("2p", "2.° primaria"), ("4p", "4.° primaria"), ("6p", "6.° primaria"), ("2s", "2.° secundaria")):
        n = niveles[niveles.grado == grado].assign(anio_n=lambda d: num(d.anio))
        ultimo = n[n.anio_n == n.anio_n.max()]
        out[f"enla_{sufijo}_anio"] = int(n.anio_n.max())
        for area in ("lectura", "matematica"):
            out[f"enla_{sufijo}_{area}_satisfactorio"] = ultimo[ultimo.area == area].set_index("region_clave").satisfactorio.pipe(num)
    columnas = [c for c, *_ in DICCIONARIO_FINAL["resumen_region"]]
    out = out.reset_index()
    for c in columnas:
        if c not in out:
            raise KeyError(f"resumen_region: falta {c}")
    out = out[columnas]
    cuentas = [c for c in columnas if c.startswith(("obras_", "paralizadas_causa_"))] + ["contraloria_obras_educacion"]
    out[cuentas] = out[cuentas].fillna(0).astype(int)
    return out.sort_values("region_enla").reset_index(drop=True)


def serie_pais_educacion():
    c = leer("cifras_oficiales_contraloria")
    nac = c[c.ambito == "nacional"].set_index("fecha_corte")
    edu = c[(c.ambito == "sector") & (c.categoria == "EDUCACION")].set_index("fecha_corte")
    s = pd.DataFrame({"anio": nac.anio, "obras_pais": num(nac.obras_paralizadas), "costo_pais_soles": num(nac.costo_actualizado_soles),
                      "saldo_pais_soles": num(nac.saldo_inversion_soles), "obras_educacion_pdf": num(edu.obras_paralizadas),
                      "costo_educacion_pdf_soles": num(edu.costo_actualizado_soles), "fuente_pdf": nac.fuente_pdf})
    corregida = num(edu.obras_educacion_corregida)
    s["obras_educacion"] = corregida.fillna(s.obras_educacion_pdf)
    s["educacion_corregida"] = s.obras_educacion != s.obras_educacion_pdf
    s["fuente_obras_educacion"] = edu.fuente_educacion_corregida
    s["pct_educacion_obras"] = (100 * s.obras_educacion / s.obras_pais).round(2)
    s = s.reset_index()
    s["anio"] = num(s.anio).astype(int)
    for col in ("obras_pais", "obras_educacion_pdf", "obras_educacion"):
        s[col] = s[col].astype(int)
    return s[[c for c, *_ in DICCIONARIO_FINAL["serie_pais_educacion"]]].sort_values("fecha_corte").reset_index(drop=True)


def serie_educacion_departamento():
    d = leer("contraloria_educacion_departamento")
    for c in ("obras_educacion", "obras_educacion_estricto"):
        d[c] = num(d[c]).astype(int)
    for c in ("costo_educacion_soles", "costo_educacion_estricto_soles"):
        d[c] = num(d[c])
    d["anio"] = num(d.anio).astype(int)
    return d[[c for c, *_ in DICCIONARIO_FINAL["serie_educacion_departamento"]]].sort_values(["fecha_corte", "cod_departamento"]).reset_index(drop=True)


def causales_por_corte():
    c = leer("contraloria_causales")
    c["causa_grupo"] = [texto_nlp.clasificar_causa(x) for x in c.causal]
    c["causa_macro"] = c.causa_grupo.map(nlp_causas.macro)
    c["anio"] = num(c.anio).astype(int)
    c["obras_paralizadas"] = num(c.obras_paralizadas).astype(int)
    for col in ("pct_obras", "costo_actualizado_soles", "saldo_inversion_soles"):
        c[col] = num(c[col])
    c["pagina"] = num(c.pagina).astype(int)
    return c[[x for x, *_ in DICCIONARIO_FINAL["causales_por_corte"]]].sort_values(["fecha_corte", "causal"]).reset_index(drop=True)


# ======================================================================================================
# Validacion
# ======================================================================================================
def validar(m, r, serie, edu, causales):
    checks = []

    def agregar(nombre, valor, esperado, ok=None, tolerancia=0.0):
        diferencia = None if valor is None or esperado is None else float(valor) - float(esperado)
        paso = bool(ok) if ok is not None else (diferencia is not None and abs(diferencia) <= tolerancia)
        checks.append({"tabla": nombre.split(":")[0], "comprobacion": nombre.split(":", 1)[1].strip(), "valor": valor, "esperado": esperado, "ok": paso})

    fi = leer("infobras_fichas_ampliadas")
    f198 = leer("fichas_infobras")
    agregar("obras_maestra: filas = fichas ampliadas de INFOBRAS", len(m), len(fi))
    agregar("obras_maestra: codigo_infobras sin repetidos", int(m.codigo_infobras.duplicated().sum()), 0)
    agregar("obras_maestra: contiene las 198 obras paralizadas del 27-oct", int(m.codigo_infobras.isin(f198.codigo_infobras).sum()), len(f198))
    agregar("obras_maestra: ubigeo de 6 digitos en todas", int(m.ubigeo.astype(str).str.fullmatch(r"\d{6}").sum()), len(m))
    agregar("obras_maestra: cod_departamento de 2 digitos y = ubigeo[:2]", int((m.cod_departamento.astype(str) == m.ubigeo.astype(str).str[:2]).sum()), len(m))
    agregar("obras_maestra: region_enla es una de las 26 regiones ENLA", int(m.region_enla.isin(r.region_enla).sum()), len(m))
    agregar("obras_maestra: suma del expediente tecnico = fichas ampliadas", round(m.monto_expediente_tecnico.sum(), 2), round(num(fi.monto_expediente_tecnico).sum(), 2), tolerancia=0.01)
    agregar("obras_maestra: obras paralizadas hoy = estado PARALIZADA en las fichas", int(m.paralizada_hoy.sum()), int((fi.estado.str.upper() == "PARALIZADA").sum()))
    agregar("obras_maestra: todas las obras tienen causal oficial o grupo de causa", int(m.causa_grupo_final.notna().sum()), len(m))
    agregar("obras_maestra: grupos de causa y macro-categorias validos", int((m.causa_grupo_final.isin(GRUPOS_CAUSA) & m.causa_macro.isin(MACROS_CAUSA)).sum()), len(m))
    sin_causa = int(m.causa_grupo_final.isin(["otros", "sin_informacion"]).sum())
    agregar("obras_maestra: obras sin causa reconocible (otros + sin_informacion), como maximo 10 %", sin_causa, int(0.10 * len(m)), ok=sin_causa <= 0.10 * len(m))
    tipos = {"educacion_basica", "educacion_superior", "deportiva_recreativa", "cultural_patrimonio", "otra"}
    agregar("obras_maestra: tipo de infraestructura asignado y valido en todas", int(m.tipo_infraestructura.isin(tipos).sum()), len(m))
    agregar("obras_maestra: obras paralizadas hoy con fecha de paralizacion (para dias_desde_paralizacion)", int(m.dias_desde_paralizacion.notna().sum()),
            int(m.paralizada_hoy.sum()), ok=m.dias_desde_paralizacion.notna().sum() >= 0.9 * m.paralizada_hoy.sum())
    agregar("obras_maestra: obras de educacion basica (informativo)", int((m.tipo_infraestructura == "educacion_basica").sum()), len(m), ok=True)
    mayor = m.causa_macro.value_counts(normalize=True).max()
    agregar("obras_maestra: ninguna macro-categoria de causa supera el 50 % de las obras", round(float(mayor), 3), 0.5, ok=mayor <= 0.5)
    metricas_nlp = pd.read_csv(config.DOCS / "nlp_causas_metricas.csv", encoding="utf-8-sig")
    f1 = float(metricas_nlp.loc[metricas_nlp.clase == "macro avg", "f1"].iloc[0])
    agregar("NLP causas: macro-F1 del modelo de apoyo (validacion cruzada) de al menos 0.75", f1, 0.75, ok=f1 >= 0.75)
    agregar("obras_maestra: avance fisico entre 0 y 100", int(m.avance_fisico_pct.between(0, 100).sum()), int(m.avance_fisico_pct.notna().sum()))
    validas = m.cui.astype(str).str.fullmatch(r"\d+")   # 15 obras tienen CUI "NO ASOCIADO": no se pueden cruzar
    con_mef = int((validas & m.estado_mef.notna()).sum())
    agregar("obras_maestra: obras con CUI valido que aparecen en el Formato 12-B del MEF (informativo: al menos 80 %)", con_mef, int(validas.sum()), ok=con_mef >= 0.8 * validas.sum())
    agregar("resumen_region: 26 regiones", len(r), 26)
    agregar("resumen_region: obras_en_tabla suma = obras_maestra", int(r.obras_en_tabla.sum()), len(m))
    agregar("resumen_region: obras paralizadas hoy suma = obras_maestra", int(r.obras_paralizadas_hoy.sum()), int(m.paralizada_hoy.sum()))
    causas = [c for c in r.columns if c.startswith("paralizadas_causa_")]
    agregar("resumen_region: causas de las paralizadas suman las paralizadas", int(r[causas].sum().sum()), int(r.obras_paralizadas_hoy.sum()))
    ultimo_edu = int(serie.sort_values("fecha_corte").obras_educacion.iloc[-1])
    agregar("resumen_region: obras de Educacion de la Contraloria suman las del ultimo corte de la serie oficial", int(r.contraloria_obras_educacion.sum()), ultimo_edu)
    esc = leer("escale_infraestructura")
    esc = esc[esc.anio == esc.anio.max()]
    agregar("resumen_region: locales publicos de ESCALE suman el total del censo mas reciente", int(r.escale_locales_publicos.sum()), int(num(esc.n_locales_publicos).sum()))
    pcts = [c for c in r.columns if c.endswith(("_pct_3_servicios", "_pct_rural", "_pct_riesgo_estructural", "_pct_estructura_mal_estado", "_satisfactorio"))]
    agregar("resumen_region: porcentajes entre 0 y 100", int(((r[pcts] >= 0) & (r[pcts] <= 100)).sum().sum()), int(r[pcts].notna().sum().sum()))
    agregar("serie_pais_educacion: 21 cortes", len(serie), 21)
    agregar("serie_pais_educacion: Educacion corregida solo en set-2023 y set-2025", int(serie.educacion_corregida.sum()), 2)
    agregar("serie_pais_educacion: obras de Educacion <= obras del pais", int((serie.obras_educacion <= serie.obras_pais).sum()), len(serie))
    agregar("serie_educacion_departamento: 13 cortes", edu.fecha_corte.nunique(), 13)
    por_corte = edu.groupby("fecha_corte").obras_educacion.sum()
    base = serie.set_index("fecha_corte").obras_educacion.reindex(por_corte.index)
    coinciden = int((por_corte == base).sum())
    agregar("serie_educacion_departamento: la suma por corte coincide con la serie del pais (informativo: al menos 11 de 13 cortes)", coinciden, len(por_corte), ok=coinciden >= 11)
    agregar("causales_por_corte: 21 cortes", causales.fecha_corte.nunique(), 21)
    sumas = causales.groupby("fecha_corte").obras_paralizadas.sum()
    agregar("causales_por_corte: suma de causales = obras del pais en cada corte (cortes que cuadran)", int((sumas.reindex(serie.fecha_corte).values == serie.obras_pais.values).sum()), 21, ok=int((sumas.reindex(serie.fecha_corte).values == serie.obras_pais.values).sum()) >= 19)
    return pd.DataFrame(checks)


# ======================================================================================================
# Orquestacion
# ======================================================================================================
def escribir_excel(tablas):
    ruta = config.COMPONENTES / "producto_final.xlsx"
    filas_dic = [(t, c, tipo, desc, unidad) for t, cols in DICCIONARIO_FINAL.items() for c, tipo, desc, unidad in cols]
    dic = pd.DataFrame(filas_dic, columns=["tabla", "columna", "tipo", "descripcion", "unidad"])
    leeme = pd.DataFrame({"contenido": [
        "Producto final del proyecto «Monitor de obras de infraestructura educativa paralizadas» (USMP, Data Analytics).",
        "Hojas: obras_maestra (una fila por obra), resumen_region (26 regiones ENLA), serie_pais_educacion, serie_educacion_departamento, causales_por_corte y diccionario.",
        "INFOBRAS se leyó el 2026-11-11 (y 2026-10-27 para los comentarios); Contraloría hasta el corte 2026-06-30; MEF el día de la descarga; ESCALE y ENLA hasta 2025.",
        "Los códigos (ubigeo, CUI, cod_departamento) son texto: en Excel, no convertirlos a número. Limitaciones: docs/hallazgos_pdf.md y docs/producto_final.md."]})
    with pd.ExcelWriter(ruta, engine="openpyxl") as escritor:
        leeme.to_excel(escritor, sheet_name="LEEME", index=False)
        for nombre, tabla in tablas.items():
            tabla.to_excel(escritor, sheet_name=nombre[:31], index=False)
        dic.to_excel(escritor, sheet_name="diccionario", index=False)
        for hoja in escritor.book.worksheets:
            for columna in hoja.columns:
                ancho = max(len(str(c.value)) if c.value is not None else 0 for c in list(columna)[:200])
                hoja.column_dimensions[columna[0].column_letter].width = min(max(ancho + 2, 10), 60)
            hoja.freeze_panes = "A2"
    return ruta


def construir():
    """Arma y guarda las tablas finales; devuelve (tablas, validacion). Lanza un error si falla alguna comprobacion obligatoria."""
    config.FINAL.mkdir(parents=True, exist_ok=True)
    config.COMPONENTES.mkdir(parents=True, exist_ok=True)
    escale_obras.construir()
    escale_ampliado.construir()
    contraloria_anexo03.construir()
    cuis = set(leer("infobras_fichas_ampliadas").cui) | set(leer("contraloria_obras_corte").cui)
    descarga_mef.construir_tabla(cuis)
    m = tabla_maestra()
    r = resumen_region(m)
    serie, edu, causales = serie_pais_educacion(), serie_educacion_departamento(), causales_por_corte()
    tablas = {"obras_maestra": m, "resumen_region": r, "serie_pais_educacion": serie, "serie_educacion_departamento": edu, "causales_por_corte": causales}
    validacion = validar(m, r, serie, edu, causales)
    for nombre, tabla in tablas.items():
        tabla.round(4).to_csv(config.COMPONENTES / f"{nombre}.csv", index=False, encoding="utf-8-sig", na_rep="")
    # el entregable: un solo CSV para el dashboard con todas las tablas anteriores
    unico = dashboard.construir(m, r, serie, edu, causales, region_enla)
    extra = pd.DataFrame(dashboard.validar(unico, m, serie, edu), columns=["comprobacion", "valor", "esperado", "ok"])
    extra.insert(0, "tabla", "dashboard_obras")
    extra["comprobacion"] = extra.comprobacion.str.replace("dashboard: ", "", regex=False)
    validacion = pd.concat([validacion, extra], ignore_index=True)
    dashboard.escribir(unico)
    tablas["dashboard_obras"] = unico
    validacion.to_csv(config.DOCS / "validacion_final.csv", index=False, encoding="utf-8-sig")
    ruta = escribir_excel(tablas)
    malas = validacion[~validacion.ok]
    utils.log(f"PRODUCTO FINAL: obras_maestra {len(m)} filas, resumen_region {len(r)}, serie_pais {len(serie)}, serie_educacion_departamento {len(edu)}, "
              f"causales {len(causales)}; {len(validacion)} comprobaciones ({len(malas)} fallan); Excel {ruta.name}")
    for _, f in malas.iterrows():
        utils.log(f"AVISO PRODUCTO FINAL: no pasa '{f.tabla}: {f.comprobacion}' (valor {f.valor}, esperado {f.esperado})")
    if len(malas):
        raise ValueError(f"{len(malas)} comprobaciones del producto final no pasan (docs/validacion_final.csv)")
    return tablas, validacion
