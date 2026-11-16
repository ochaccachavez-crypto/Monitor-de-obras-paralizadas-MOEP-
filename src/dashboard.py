"""CSV unico del proyecto (lo usa el dashboard HTML): data/final/dashboard_obras.csv

Una sola tabla en formato largo. La columna `tipo_registro` dice que representa cada fila; hay que filtrar por ella al armar cada grafico
(si no, se mezclan niveles distintos y se cuenta dos veces):

  obra_infobras           429 obras de Educacion/Cultura leidas en INFOBRAS (foto de nov-2026): una fila por obra, todos los datos
  obra_corte_contraloria  obras de Educacion en cada corte de la Contraloria (anexos Excel, sep-2023 a jun-2026): una fila por obra y corte
  departamento_corte      Educacion por departamento y corte (13 cortes, sep-2023 a jun-2026, anexos Excel): cifras ya sumadas
  pais_total_corte        total nacional (todos los sectores) por corte (21 cortes, jun-2022 a jun-2026), segun el informe PDF
  pais_educacion_corte    sector Educacion a nivel pais por corte (con la cifra corregida con los anexos Excel)
  causal_corte            causales oficiales de paralizacion por corte (cantidad de obras y monto), con su grupo de causa
  contexto_region         una fila por region ENLA con ESCALE y ENLA (datos de contexto)

Medidas comunes a todos los tipos: n_obras, n_obras_paralizadas, costo_actualizado_soles, saldo_inversion_soles.
"""
import numpy as np
import pandas as pd

import config
import contraloria_anexo03
import escale_ampliado
import nlp_causas
import utils

TIPOS = ["obra_infobras", "obra_corte_contraloria", "departamento_corte", "pais_total_corte", "pais_educacion_corte", "causal_corte", "contexto_region"]

# (columna, tipo, descripcion, unidad)
DICCIONARIO = [
    ("tipo_registro", "texto", "Qué representa la fila: obra_infobras, obra_corte_contraloria, departamento_corte, pais_total_corte, pais_educacion_corte, causal_corte o contexto_region. Filtrar siempre por este campo.", "categoría"),
    ("fecha_corte", "fecha AAAA-MM-DD", "Fecha del dato: corte del informe de la Contraloría, o fecha de lectura de INFOBRAS (2026-11-11) para obra_infobras. Vacía en contexto_region.", "fecha"),
    ("anio", "entero", "Año de fecha_corte.", "año"),
    ("fuente_dato", "texto", "Archivo o fuente de donde sale la fila (PDF, Excel, INFOBRAS, ENLA/ESCALE).", "texto"),
    ("alertas_calidad", "texto", "Avisos sobre el dato de esa fila, separados por «|»; vacío = sin avisos. Los valores NO se corrigen (vienen así de la fuente): se marcan para filtrarlos o explicarlos. obra_infobras: sin_coordenadas, sin_expediente_tecnico, cui_no_asociado, cui_sin_datos_mef, cui_en_varias_obras, paralizacion_anterior_al_inicio, avance_infobras_vs_mef_difiere_30_puntos, devengado_mayor_al_costo, ejecucion_mayor_al_expediente, causa_sin_clasificar. obra_corte_contraloria: costo_cero_o_vacio_en_fuente, saldo_mayor_que_costo, sin_provincia_ni_distrito.", "texto"),
    ("codigo_infobras", "texto", "Código de la obra en INFOBRAS (como texto).", "código"),
    ("cui", "texto", "Código Único de Inversión; «NO ASOCIADO» si la obra no tiene.", "código"),
    ("nombre_obra", "texto", "Nombre de la obra (solo obra_infobras).", "texto"),
    ("entidad", "texto", "Entidad ejecutora.", "texto"),
    ("cod_departamento", "texto", "Código INEI del departamento, 2 dígitos como texto (Callao = 07).", "código"),
    ("departamento", "texto", "Departamento en MAYÚSCULAS sin tildes.", "texto"),
    ("provincia", "texto", "Provincia en MAYÚSCULAS sin tildes.", "texto"),
    ("distrito", "texto", "Distrito en MAYÚSCULAS sin tildes.", "texto"),
    ("ubigeo", "texto", "Ubigeo de 6 dígitos como texto (solo obra_infobras).", "código"),
    ("region_enla", "texto", "Región según la ENLA (Lima se divide en LIMA METROPOLITANA y LIMA PROVINCIAS; Callao aparte).", "categoría"),
    ("latitud", "decimal", "Latitud (grados decimales) de la ficha de INFOBRAS; vacía si INFOBRAS no tiene coordenadas de la obra.", "grados"),
    ("longitud", "decimal", "Longitud (grados decimales) de la ficha de INFOBRAS.", "grados"),
    ("latitud_mapa", "decimal", "Latitud para el mapa (solo obra_infobras): la de INFOBRAS o, si falta, una aproximada de ESCALE. Es la que usa el mapa del dashboard, junto con coordenada_origen.", "grados"),
    ("longitud_mapa", "decimal", "Longitud para el mapa (mismo criterio que latitud_mapa).", "grados"),
    ("coordenada_origen", "texto", "infobras (exacta), escale_local_obra (local escolar que declara el CUI de la obra) o centro_distrito_escale (mediana de los colegios del distrito): estas dos son aproximadas.", "categoría"),
    ("sector", "texto", "Sector: EDUCACION para las obras de INFOBRAS y de la Contraloría; TODOS en pais_total_corte.", "categoría"),
    ("nivel_gobierno", "texto", "Nivel de gobierno de la entidad (Contraloría).", "categoría"),
    ("origen", "texto", "Por qué la obra está en obra_infobras: paralizada en INFOBRAS el 27-oct, o en la lista de la Contraloría de jun-2026 y no paralizada en esa fecha.", "categoría"),
    ("estado_infobras", "texto", "Estado de la obra en INFOBRAS (PARALIZADA, EN EJECUCIÓN, FINALIZADO, SIN EJECUCIÓN).", "categoría"),
    ("paralizada_hoy", "lógico", "TRUE si el estado en INFOBRAS es PARALIZADA (solo obra_infobras).", "lógico"),
    ("modalidad", "texto", "Modalidad de ejecución (INFOBRAS o Contraloría).", "categoría"),
    ("tipo_obra", "texto", "Tipo de obra.", "categoría"),
    ("tipo_infraestructura", "texto", "Solo obra_infobras. Tipo de infraestructura según el nombre de la obra (reglas; si el nombre no lo dice, el tipo de obra de INFOBRAS): educacion_basica (colegios, inicial, CEBA, CETPRO), educacion_superior (universidades e institutos), deportiva_recreativa, cultural_patrimonio u otra. INFOBRAS agrupa Educación y Cultura. Para el objetivo del proyecto (instituciones educativas) filtrar educacion_basica.", "categoría"),
    ("evento_contraloria", "texto", "Evento de la obra en el corte de la Contraloría (p. ej. PROCESO NORMAL, REINICIO).", "categoría"),
    ("causal_oficial", "texto", "Causal de paralización declarada: la del corte en obra_corte_contraloria, la del último corte en obra_infobras, el texto de la causal en causal_corte.", "texto"),
    ("causa_grupo_final", "texto", "Causa principal (NLP) en 14 grupos: recursos_financieros, incumplimiento_contractual, expediente_tecnico, controversias_arbitraje, clima, conflictos_sociales, terreno_saneamiento, permisos_licencias, interferencias, materiales_logistica, personal_clave, pandemia, obra_concluida_o_en_marcha, sin_restricciones (más otros y sin_informacion). En las filas de la Contraloría se deduce de la causal oficial.", "categoría"),
    ("causa_macro", "texto", "Causa en 8 macro-categorías para gráficos: financiera, contractual_y_legal, tecnica, logistica, entorno_social_y_territorial, fuerza_mayor, sin_causa_de_paralizacion, sin_clasificar.", "categoría"),
    ("causas_secundarias", "texto", "Hasta 2 causas adicionales detectadas en los textos de la obra, separadas por «|» (solo obra_infobras).", "categoría"),
    ("causa_fuente", "texto", "Fuente que más aportó a la causa principal: infobras_comentario, contraloria_causal, mef_problema, texto_libre o sin_causa_clara (solo obra_infobras).", "categoría"),
    ("causa_confianza", "texto", "alta (2 o más fuentes coinciden), media (una fuente), baja (solo modelo) o vacío (solo obra_infobras).", "categoría"),
    ("causa_metodo", "texto", "reglas o modelo (solo obra_infobras).", "categoría"),
    ("causa_grupo_infobras", "texto", "Causa según solo los comentarios de INFOBRAS (solo obra_infobras).", "categoría"),
    ("causa_grupo_contraloria", "texto", "Causa según solo la causal oficial de la Contraloría (solo obra_infobras).", "categoría"),
    ("causa_grupo_mef", "texto", "Causa según solo la problemática registrada en el MEF (solo obra_infobras).", "categoría"),
    ("n_obras", "entero", "Medida: cantidad de obras que representa la fila (1 en las filas por obra; la cifra del informe en las agregadas). En pais_total_corte son todas las obras del país.", "obras"),
    ("n_obras_paralizadas", "entero", "Medida: obras paralizadas que representa la fila (en obra_infobras es 1 solo si paralizada_hoy; en los demás tipos es igual a n_obras porque las listas de la Contraloría son de obras paralizadas).", "obras"),
    ("costo_actualizado_soles", "decimal", "Medida: costo actualizado de la inversión (soles).", "soles"),
    ("saldo_inversion_soles", "decimal", "Medida: saldo por invertir (soles).", "soles"),
    ("monto_expediente_tecnico", "decimal", "Monto del expediente técnico (INFOBRAS, soles).", "soles"),
    ("monto_ejecucion_acumulado", "decimal", "Monto de ejecución acumulado (INFOBRAS, soles).", "soles"),
    ("avance_fisico_pct", "decimal", "Avance físico % (INFOBRAS para obra_infobras; Contraloría para obra_corte_contraloria).", "%"),
    ("pct_obras", "decimal", "% de las obras que representa la causal (causal_corte) o % de Educación sobre el país (pais_educacion_corte).", "%"),
    ("n_obras_estricto", "entero", "Obras de Educación con la definición estricta del anexo (departamento_corte).", "obras"),
    ("costo_estricto_soles", "decimal", "Costo de las obras con la definición estricta (departamento_corte).", "soles"),
    ("educacion_corregida", "lógico", "TRUE si la cifra de Educación del PDF se corrigió con los anexos Excel (pais_educacion_corte).", "lógico"),
    ("fuente_obras_educacion", "texto", "De dónde sale la cifra de obras de Educación del país: pdf o excel (pais_educacion_corte).", "categoría"),
    ("fecha_inicio", "fecha AAAA-MM-DD", "Fecha de inicio de la obra (INFOBRAS).", "fecha"),
    ("fecha_fin_prevista", "fecha AAAA-MM-DD", "Fecha de fin prevista (INFOBRAS).", "fecha"),
    ("fecha_paralizacion", "fecha AAAA-MM-DD", "Fecha de paralización del último tramo (INFOBRAS).", "fecha"),
    ("dias_paralizado", "entero", "Valor «días paralizado» del detalle del último avance paralizado de INFOBRAS. OJO: en casi todas las obras vale 30 o 31 (los días de ese mes del informe), no el tiempo total; para el tiempo total usar dias_desde_paralizacion.", "días"),
    ("dias_desde_paralizacion", "entero", "Solo obra_infobras. Días entre fecha_paralizacion y la lectura de INFOBRAS (11-nov-2026), solo en las obras paralizadas hoy: cuánto tiempo lleva detenida la obra en su paralización actual.", "días"),
    ("meses_paralizado", "entero", "Meses con estado paralizado en el historial de avances.", "meses"),
    ("n_tramos_paralizacion", "entero", "Cantidad de tramos de paralización distintos.", "tramos"),
    ("n_cortes_contraloria", "entero", "Cantidad de cortes (de los 13 con base obra por obra) en que aparece la obra.", "cortes"),
    ("reingresos_contraloria", "entero", "Veces que la obra salió y volvió a entrar a la lista de la Contraloría.", "veces"),
    ("en_ultimo_corte_contraloria", "lógico", "TRUE si la obra está en la lista de jun-2026.", "lógico"),
    ("estado_mef", "texto", "Estado de la inversión en el Formato 12-B del MEF.", "categoría"),
    ("devengado_total_soles", "decimal", "Devengado acumulado según el MEF (soles).", "soles"),
    ("pim_anio_actual_soles", "decimal", "Presupuesto institucional modificado del año actual (MEF).", "soles"),
    ("pct_devengado_del_costo", "decimal", "Devengado total / costo actualizado × 100 (puede pasar 100 por diferencias entre fuentes).", "%"),
    ("avance_fisico_mef_pct", "decimal", "Avance físico % que reporta el MEF.", "%"),
    ("mef_ult_problema", "texto", "Última problemática registrada en el MEF (nombres de personas omitidos).", "texto"),
    ("escale_locales_publicos", "entero", "Locales públicos del distrito (ESCALE).", "locales"),
    ("escale_pct_3_servicios", "decimal", "% de locales del distrito con los 3 servicios básicos.", "%"),
    ("escale_pct_rural", "decimal", "% de locales rurales del distrito.", "%"),
    ("escale_pct_riesgo_estructural", "decimal", "% de locales con riesgo estructural.", "%"),
    ("escale_pct_estructura_mal_estado", "decimal", "% de locales con estructura en mal estado.", "%"),
    ("region_escale_locales_publicos", "entero", "Locales públicos de la región (suma de distritos, ESCALE).", "locales"),
    ("region_escale_pct_3_servicios", "decimal", "% de locales de la región con los 3 servicios básicos.", "%"),
    ("region_escale_pct_rural", "decimal", "% de locales rurales de la región.", "%"),
    ("region_escale_pct_riesgo_estructural", "decimal", "% de locales de la región con riesgo estructural.", "%"),
    ("region_escale_pct_estructura_mal_estado", "decimal", "% de locales de la región con estructura en mal estado.", "%"),
    ("region_enla_4p_lectura_satisfactorio", "decimal", "% de estudiantes de 4.º primaria de la región en nivel Satisfactorio en Lectura (último año ENLA).", "%"),
    ("region_enla_4p_matematica_satisfactorio", "decimal", "% en nivel Satisfactorio en Matemática, 4.º primaria.", "%"),
    ("region_enla_2s_lectura_satisfactorio", "decimal", "% en nivel Satisfactorio en Lectura, 2.º secundaria.", "%"),
    ("region_enla_2s_matematica_satisfactorio", "decimal", "% en nivel Satisfactorio en Matemática, 2.º secundaria.", "%"),
]
# ESCALE ampliado (distrito, 2025) y vinculo de la obra con un local en construccion: se insertan despues de los indicadores de ESCALE
_ampliado = [("escale_" + c, t, d + " (distrito, Censo 2025)", u) for c, t, d, u in escale_ampliado.DICCIONARIO if c not in ("anio", "ubigeo", "n_locales_publicos_ampliado")]
_vinculo = [("escale_n_locales_obra", "entero", "Locales que declaran en el Censo 2025 estar en construcción con el CUI de esta obra (0 = ninguno).", "locales"),
            ("escale_codlocal", "texto", "Código del primer local de ESCALE que declara el CUI de esta obra.", "código")]
_anexo03 = [(c, t, d + " Vacío = la obra no figura en el anexo 03 (corte mar-2026).", u) for c, t, d, u in contraloria_anexo03.DICCIONARIO
            if c not in ("codigo_infobras", "corte_anexo03")]
_pos_sc = [c for c, *_ in DICCIONARIO].index("reingresos_contraloria") + 1
DICCIONARIO = DICCIONARIO[:_pos_sc] + _anexo03 + DICCIONARIO[_pos_sc:]
_pos = [c for c, *_ in DICCIONARIO].index("escale_pct_estructura_mal_estado") + 1
DICCIONARIO = DICCIONARIO[:_pos] + _vinculo + _ampliado + DICCIONARIO[_pos:]
# ENLA: todos los grados que ofrece SICRECE (ultimo anio de cada uno); region_enla_{grado}_anio dice de que anio es cada dato
GRADOS_ENLA = [("2p", "2.º primaria"), ("4p", "4.º primaria"), ("6p", "6.º primaria"), ("2s", "2.º secundaria")]
_enla = [("region_enla_" + suf + "_anio", "entero", f"Último año de la ENLA de {gr} disponible para la región.", "año") for suf, gr in GRADOS_ENLA]
for suf, gr in GRADOS_ENLA:
    if suf not in ("4p", "2s"):
        _enla += [(f"region_enla_{suf}_lectura_satisfactorio", "decimal", f"% en nivel Satisfactorio en Lectura, {gr} (último año ENLA).", "%"),
                  (f"region_enla_{suf}_matematica_satisfactorio", "decimal", f"% en nivel Satisfactorio en Matemática, {gr}.", "%")]
DICCIONARIO += _enla
COLUMNAS = [c for c, *_ in DICCIONARIO]


def _fecha_iso(s):
    return pd.to_datetime(s, errors="coerce").dt.strftime("%Y-%m-%d")


def _contexto_region(resumen):
    """Columnas region_* a partir de resumen_region (una fila por region ENLA)."""
    r = resumen.copy()
    pares = {"escale_locales_publicos": "region_escale_locales_publicos", "escale_pct_3_servicios": "region_escale_pct_3_servicios",
             "escale_pct_rural": "region_escale_pct_rural", "escale_pct_riesgo_estructural": "region_escale_pct_riesgo_estructural",
             "escale_pct_estructura_mal_estado": "region_escale_pct_estructura_mal_estado",
             "enla_4p_lectura_satisfactorio": "region_enla_4p_lectura_satisfactorio", "enla_4p_matematica_satisfactorio": "region_enla_4p_matematica_satisfactorio",
             "enla_2s_lectura_satisfactorio": "region_enla_2s_lectura_satisfactorio", "enla_2s_matematica_satisfactorio": "region_enla_2s_matematica_satisfactorio"}
    for suf, _ in GRADOS_ENLA:
        for sufijo in ("anio",) + (() if suf in ("4p", "2s") else ("lectura_satisfactorio", "matematica_satisfactorio")):
            pares[f"enla_{suf}_{sufijo}"] = f"region_enla_{suf}_{sufijo}"
    return r[["region_enla", "cod_departamento"] + list(pares)].rename(columns=pares)


def alertas(d):
    """Texto con los avisos de calidad de cada fila (ver el diccionario). No cambia ningun valor: solo marca lo que viene dudoso de la fuente."""
    n = lambda c: pd.to_numeric(d[c], errors="coerce")
    obra, corte = d.tipo_registro == "obra_infobras", d.tipo_registro == "obra_corte_contraloria"
    cui_ok = d.cui.astype(str).str.fullmatch(r"\d+").fillna(False)
    repetidos = d[obra & cui_ok].cui.value_counts()
    reglas = {
        "sin_coordenadas": obra & d.latitud.isna(),
        "sin_expediente_tecnico": obra & ~(n("monto_expediente_tecnico") > 0),
        "cui_no_asociado": obra & ~cui_ok,
        "cui_sin_datos_mef": obra & cui_ok & d.estado_mef.isna(),
        "cui_en_varias_obras": obra & cui_ok & d.cui.map(repetidos).gt(1).fillna(False),
        "paralizacion_anterior_al_inicio": obra & (pd.to_datetime(d.fecha_paralizacion, errors="coerce") < pd.to_datetime(d.fecha_inicio, errors="coerce")),
        "avance_infobras_vs_mef_difiere_30_puntos": obra & ((n("avance_fisico_pct") - n("avance_fisico_mef_pct")).abs() > 30),
        "devengado_mayor_al_costo": obra & (n("pct_devengado_del_costo") > 100),
        "ejecucion_mayor_al_expediente": obra & (n("monto_ejecucion_acumulado") > n("monto_expediente_tecnico") * 1.0001),
        "causa_sin_clasificar": obra & d.causa_grupo_final.isin(["otros", "sin_informacion"]),
        "costo_cero_o_vacio_en_fuente": corte & ~(n("costo_actualizado_soles") > 0),
        "saldo_mayor_que_costo": corte & (n("saldo_inversion_soles") > n("costo_actualizado_soles") * 1.0001),
        "sin_provincia_ni_distrito": corte & (d.provincia.isna() | d.distrito.isna()),
    }
    texto = pd.Series("", index=d.index)
    for nombre, marca in reglas.items():
        marca = marca.fillna(False)
        texto = texto.where(~marca, texto + np.where(texto == "", "", "|") + nombre)
    return texto.replace("", np.nan)


def construir(m, resumen, serie_pais, serie_dep, causales, region_fn):
    """Une las tablas del producto final en el CSV unico. m = obras_maestra, resumen = resumen_region, serie_* y causales = tablas finales."""
    ctx = _contexto_region(resumen)
    cols_region = [c for c in ctx.columns if c.startswith("region_") and c != "region_enla"]
    partes = []

    # 1) obras de INFOBRAS (una fila por obra)
    a = m.copy()
    a["tipo_registro"] = "obra_infobras"
    a["fecha_corte"] = _fecha_iso(a.fecha_lectura_infobras)
    a["fuente_dato"] = "INFOBRAS (lectura 11-nov-2026) + Contraloria + MEF + ESCALE"
    a["sector"] = "EDUCACION"
    a["causal_oficial"] = a.causal_oficial_contraloria
    a["n_obras"] = 1
    a["n_obras_paralizadas"] = a.paralizada_hoy.astype(int)
    a = a.merge(ctx.drop(columns="cod_departamento"), on="region_enla", how="left")
    partes.append(a)

    # 2) obras de Educacion en cada corte de la Contraloria (anexos Excel)
    oc = pd.read_csv(config.PROCESSED / "contraloria_obras_corte.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    oc = oc[oc.sector_agrupado.str.contains("EDUC")].copy()
    oc["tipo_registro"] = "obra_corte_contraloria"
    oc["fecha_corte"] = _fecha_iso(oc.corte)
    oc["fuente_dato"] = oc.fuente_excel
    oc["sector"] = "EDUCACION"
    oc["modalidad"] = oc.modalidad_ejecucion
    oc["evento_contraloria"] = oc.evento
    oc["causal_oficial"] = oc.causal_paralizacion
    oc["causa_grupo_final"] = [nlp_causas.clasificar_causa(c) for c in oc.causal_paralizacion]
    oc["causa_macro"] = oc.causa_grupo_final.map(nlp_causas.macro)
    oc["avance_fisico_pct"] = pd.to_numeric(oc.avance_fisico, errors="coerce")
    oc["region_enla"] = [region_fn(d, p) for d, p in zip(oc.departamento, oc.provincia)]
    for c in ("costo_actualizado_soles", "saldo_inversion_soles"):
        oc[c] = pd.to_numeric(oc[c], errors="coerce")
    oc["n_obras"] = 1
    oc["n_obras_paralizadas"] = 1
    oc = oc.merge(ctx.drop(columns="cod_departamento"), on="region_enla", how="left")
    partes.append(oc)

    # 3) Educacion por departamento y corte
    d = serie_dep.rename(columns={"obras_educacion": "n_obras", "costo_educacion_soles": "costo_actualizado_soles", "obras_educacion_estricto": "n_obras_estricto",
                                  "costo_educacion_estricto_soles": "costo_estricto_soles", "fuente_excel": "fuente_dato"}).copy()
    d["tipo_registro"] = "departamento_corte"
    d["fecha_corte"] = _fecha_iso(d.fecha_corte)
    d["sector"] = "EDUCACION"
    d["n_obras_paralizadas"] = d.n_obras
    partes.append(d)

    # 4) pais: total y Educacion
    p = serie_pais.copy()
    pt = pd.DataFrame({"tipo_registro": "pais_total_corte", "fecha_corte": _fecha_iso(p.fecha_corte), "sector": "TODOS", "n_obras": p.obras_pais,
                       "n_obras_paralizadas": p.obras_pais, "costo_actualizado_soles": p.costo_pais_soles, "saldo_inversion_soles": p.saldo_pais_soles,
                       "fuente_dato": p.fuente_pdf})
    pe = pd.DataFrame({"tipo_registro": "pais_educacion_corte", "fecha_corte": _fecha_iso(p.fecha_corte), "sector": "EDUCACION", "n_obras": p.obras_educacion,
                       "n_obras_paralizadas": p.obras_educacion, "costo_actualizado_soles": p.costo_educacion_pdf_soles, "pct_obras": p.pct_educacion_obras,
                       "educacion_corregida": p.educacion_corregida, "fuente_obras_educacion": p.fuente_obras_educacion, "fuente_dato": p.fuente_pdf})
    partes += [pt, pe]

    # 5) causales por corte
    c = causales.rename(columns={"causal": "causal_oficial", "causa_grupo": "causa_grupo_final", "obras_paralizadas": "n_obras_paralizadas",
                                 "fuente_pdf": "fuente_dato"}).copy()
    c["tipo_registro"] = "causal_corte"
    c["fecha_corte"] = _fecha_iso(c.fecha_corte)
    c["n_obras"] = c.n_obras_paralizadas
    c["sector"] = "TODOS"
    partes.append(c)

    # 6) contexto por region
    x = ctx.copy()
    x["tipo_registro"] = "contexto_region"
    x["fuente_dato"] = "ESCALE (Minedu) y ENLA (Minedu)"
    partes.append(x)

    partes = [t.reindex(columns=COLUMNAS) for t in partes]   # agrega de una vez las columnas que faltan (vacias)
    out = pd.concat(partes, ignore_index=True)
    out["anio"] = pd.to_datetime(out.fecha_corte, errors="coerce").dt.year.astype("Int64")
    out["alertas_calidad"] = alertas(out)
    for col in ("n_obras", "n_obras_paralizadas", "n_obras_estricto", "dias_paralizado", "dias_desde_paralizacion", "meses_paralizado", "n_tramos_paralizacion", "n_cortes_contraloria",
                "reingresos_contraloria", "escale_locales_publicos", "region_escale_locales_publicos"):
        out[col] = pd.to_numeric(out[col], errors="coerce").round().astype("Int64")
    # el departamento de las series viene como texto; todas las columnas de codigo quedan como texto
    out["tipo_registro"] = pd.Categorical(out.tipo_registro, categories=TIPOS, ordered=True)
    out = out.sort_values(["tipo_registro", "fecha_corte", "cod_departamento", "codigo_infobras", "causal_oficial"], na_position="last", kind="stable")
    out["tipo_registro"] = out.tipo_registro.astype(str)
    for col in ("paralizada_hoy", "en_ultimo_corte_contraloria", "educacion_corregida"):    # logicos como True/False (vacio si no aplica)
        out[col] = out[col].map({True: "True", False: "False", 1.0: "True", 0.0: "False", "True": "True", "False": "False"})
    for col in out.columns:
        if str(out[col].dtype).startswith("float"):
            out[col] = out[col].round(6 if col in ("latitud", "longitud", "latitud_mapa", "longitud_mapa") else 4)
    return out.reset_index(drop=True)


def validar(d, m, serie_pais, serie_dep):
    """Comprobaciones del CSV unico; devuelve lista de (comprobacion, valor, esperado, ok)."""
    c = []
    obra = d[d.tipo_registro == "obra_infobras"]
    c.append(("dashboard: tipos de registro presentes (7)", d.tipo_registro.nunique(), 7, d.tipo_registro.nunique() == 7))
    c.append(("dashboard: filas obra_infobras = obras_maestra", len(obra), len(m), len(obra) == len(m)))
    c.append(("dashboard: obras paralizadas hoy = obras_maestra", int(obra.n_obras_paralizadas.sum()), int(m.paralizada_hoy.sum()), int(obra.n_obras_paralizadas.sum()) == int(m.paralizada_hoy.sum())))
    c.append(("dashboard: codigo_infobras sin repetidos en obra_infobras", int(obra.codigo_infobras.duplicated().sum()), 0, not obra.codigo_infobras.duplicated().any()))
    oc = d[d.tipo_registro == "obra_corte_contraloria"]
    rep = int(oc.duplicated(["fecha_corte", "codigo_infobras"]).sum())
    c.append(("dashboard: obra_corte_contraloria sin obra repetida en un corte", rep, 0, rep == 0))
    # las obras de Educacion por corte (suma de obras) deben cuadrar con la serie por departamento en los 13 cortes de Excel
    por_corte = oc.groupby("fecha_corte").size()
    dep = d[d.tipo_registro == "departamento_corte"].groupby("fecha_corte").n_obras.sum()
    cuadran = int(sum(abs(int(por_corte.get(f, -1)) - int(dep.get(f, -2))) <= 2 for f in por_corte.index))
    c.append(("dashboard: obras por corte (Excel) = serie por departamento (tolerancia 2 obras)", cuadran, len(por_corte), cuadran == len(por_corte)))
    sp = d[d.tipo_registro == "pais_educacion_corte"].n_obras.sum()
    c.append(("dashboard: serie pais Educacion = tabla serie_pais_educacion", int(sp), int(serie_pais.obras_educacion.sum()), int(sp) == int(serie_pais.obras_educacion.sum())))
    lat, lon = obra.latitud.dropna(), obra.longitud.dropna()
    fuera = int(((lat > 0.1) | (lat < -18.6)).sum() + ((lon > -68.4) | (lon < -81.4)).sum())
    c.append(("dashboard: coordenadas dentro del Peru", fuera, 0, fuera == 0))
    c.append(("dashboard: obras con coordenadas (informativo: al menos 90 %)", int(obra.latitud.notna().sum()), len(obra), obra.latitud.notna().mean() >= 0.90))
    lat_m, lon_m = obra.latitud_mapa.dropna(), obra.longitud_mapa.dropna()
    fuera_m = int(((lat_m > 0.1) | (lat_m < -18.6)).sum() + ((lon_m > -68.4) | (lon_m < -81.4)).sum())
    c.append(("dashboard: coordenadas para el mapa dentro del Peru", fuera_m, 0, fuera_m == 0))
    c.append(("dashboard: obras con coordenadas para el mapa (INFOBRAS o aproximadas; informativo: al menos 90 %)", int(obra.latitud_mapa.notna().sum()),
              len(obra), obra.latitud_mapa.notna().mean() >= 0.90))
    cods = d.cod_departamento.dropna().astype(str)
    c.append(("dashboard: cod_departamento de 2 digitos", int(cods.str.fullmatch(r"\d{2}").sum()), len(cods), bool(cods.str.fullmatch(r"\d{2}").all())))
    ubi = obra.ubigeo.dropna().astype(str)
    c.append(("dashboard: ubigeo de 6 digitos", int(ubi.str.fullmatch(r"\d{6}").sum()), len(ubi), bool(ubi.str.fullmatch(r"\d{6}").all())))
    c.append(("dashboard: sin filas completamente repetidas", int(d.duplicated().sum()), 0, not d.duplicated().any()))
    return c


def escribir(d):
    config.FINAL.mkdir(parents=True, exist_ok=True)
    ruta = config.FINAL / "dashboard_obras.csv"
    d.to_csv(ruta, index=False, encoding="utf-8-sig", na_rep="", lineterminator="\n")
    diccionario = pd.DataFrame(DICCIONARIO, columns=["columna", "tipo", "descripcion", "unidad"])
    diccionario["rellena_en"] = [", ".join(sorted(d.loc[d[c].notna(), "tipo_registro"].unique())) for c in diccionario.columna]
    diccionario.to_csv(config.FINAL / "dashboard_obras_diccionario.csv", index=False, encoding="utf-8-sig", lineterminator="\n")
    utils.log(f"DASHBOARD: {ruta.name} con {len(d)} filas y {d.shape[1]} columnas; filas por tipo: {d.tipo_registro.value_counts().to_dict()}")
    return ruta
