"""Diccionario de las tablas del proyecto PDF/INFOBRAS. Se agrega a docs/diccionario.csv junto al de ESCALE y ENLA.

Cada columna de cada CSV debe tener descripcion aqui: si falta alguna, construir_diccionario_pdf() falla a proposito.
"""
import re

import pandas as pd

import config

CGR = "Informes de obras paralizadas, Contraloría General de la República (gob.pe)"
CGR_XLSX = "Anexos Excel de los informes de la Contraloría (base de obras paralizadas)"
INFOBRAS = "INFOBRAS, Contraloría (ficha pública de cada obra)"
ENLA_PDF = "Reporte nacional de la Evaluación Muestral 2022, MINEDU-UMC"
PROCEDENCIA = "Informe PDF"

# columna -> (tipo, descripcion, unidad). Las columnas con el mismo nombre en varias tablas se describen una sola vez.
COMUNES = {
    "anio": ("entero", "Año (en la tablas de la Contraloría, el año de la fecha de corte del informe).", "año"),
    "fecha_corte": ("fecha AAAA-MM-DD", "Fecha de corte de los datos del informe (fin del mes o trimestre que indica su título).", "fecha"),
    "cod_departamento": ("texto de 2 dígitos", "Código INEI del departamento (Callao = 07; Lima Metropolitana y Provincias = 15).", "código"),
    "fuente_pdf": ("texto", "Nombre del archivo PDF de data/raw de donde sale la cifra.", "texto"),
    "pagina": ("entero", "Página del PDF donde está la cifra (la primera página si la tabla sigue en la siguiente).", "página"),
    "tabla_n": ("entero", "Número de la tabla dentro de esa página (2023-2026: orden de aparición; en 2022 y ENLA: el número del título).", "número"),
    "obras_paralizadas": ("entero", "Número de obras paralizadas.", "obras"),
    "pct_obras": ("decimal", "Porcentaje que representa del total de obras paralizadas, tal como lo publica el informe.", "%"),
    "pct_costo": ("decimal", "Porcentaje que representa del costo actualizado total, tal como lo publica el informe.", "%"),
    "pct_saldo": ("decimal", "Porcentaje que representa del saldo de inversión total, tal como lo publica el informe.", "%"),
    "costo_actualizado_soles": ("decimal", "Costo actualizado de la inversión (según Invierte.pe) de esas obras.", "soles"),
    "saldo_inversion_soles": ("decimal", "Saldo de inversión por ejecutar (costo actualizado menos lo devengado) de esas obras.", "soles"),
}

POR_TABLA = {
    "cifras_oficiales_contraloria": (CGR, {
        "ambito": ("texto", "Qué representa la fila: nacional (total del país), departamento o sector.", "categoría"),
        "categoria": ("texto", "NACIONAL, nombre del departamento o nombre del sector, en mayúsculas y sin tildes.", "texto"),
        "obras_g_nacional": ("entero", "Solo en filas de sector: obras de entidades del Gobierno Nacional.", "obras"),
        "obras_g_regional": ("entero", "Solo en filas de sector: obras de entidades de Gobiernos Regionales.", "obras"),
        "obras_g_local": ("entero", "Solo en filas de sector: obras de entidades de Gobiernos Locales.", "obras"),
        "unidad_original": ("texto", "Unidad en que venía el monto en el PDF: soles, o millones de soles con 1 decimal (mapas de set y dic 2022).", "texto"),
        "coincide_excel": ("lógico", "TRUE/FALSE si el número de obras coincide con el anexo Excel del mismo corte; vacío si ese corte no tiene anexo con base de obras.", "lógico"),
        "observacion": ("texto", "Aviso sobre la cifra (no coincide con el Excel, o precisión reducida).", "texto"),
        "obras_educacion_corregida": ("entero", "Solo en filas de sector Educación: obras de Educación con la cifra corregida. En los 13 cortes con anexo Excel es la del Excel (corrige set-2023: 324 → 283 y set-2025: 73 → 196); en los demás cortes es la del PDF.", "obras"),
        "fuente_educacion_corregida": ("texto", "De dónde sale obras_educacion_corregida: anexo Excel, o informe PDF cuando el corte no tiene anexo para contrastar.", "texto"),
    }),
    "contraloria_causales": (CGR, {
        "causal": ("texto", "Causal de paralización declarada por la entidad, en mayúsculas y sin tildes. El catálogo de causales cambió entre informes.", "texto"),
    }),
    "contraloria_distribuciones": (CGR, {
        "dimension": ("texto", "Tabla de origen: nivel_gobierno, rango_costo o rango_avance_fisico.", "categoría"),
        "categoria": ("texto", "Categoría dentro de la dimensión (por ejemplo G. LOCAL, '> 1 - 3 MILLONES', '20 - 30 %').", "texto"),
    }),
    "contraloria_educacion_departamento": (CGR_XLSX, {
        "departamento": ("texto", "Departamento en mayúsculas y sin tildes.", "texto"),
        "obras_educacion": ("entero", "Obras paralizadas del sector Educación con el mismo agrupamiento de sectores del informe (en 2026-06 incluye EDUCACION/CULTURA).", "obras"),
        "costo_educacion_soles": ("decimal", "Costo actualizado de esas obras (según Invierte.pe).", "soles"),
        "obras_educacion_estricto": ("entero", "Obras cuyo sector es exactamente EDUCACION (sin Cultura).", "obras"),
        "costo_educacion_estricto_soles": ("decimal", "Costo actualizado de esas obras.", "soles"),
        "fuente_excel": ("texto", "Anexo Excel de data/raw/contraloria del que se calcula.", "texto"),
        "hoja": ("texto", "Hoja del Excel con la base de obras.", "texto"),
    }),
    "enla_pdf": (ENLA_PDF, {
        "region": ("texto", "Región ENLA en mayúsculas y sin tildes (Lima Metropolitana y Lima Provincias van por separado).", "texto"),
        "grado": ("texto", "Grado evaluado: 2.°, 4.° o 6.° de primaria; 2.° o 5.° de secundaria.", "texto"),
        "area": ("texto", "Área evaluada: lectura o matematica.", "texto"),
        "pct_satisfactorio": ("decimal de 0 a 100", "Porcentaje de estudiantes en nivel Satisfactorio.", "%"),
    }),
    "fichas_infobras": (INFOBRAS, {
        "codigo_infobras": ("texto", "Código de la obra en INFOBRAS.", "código"),
        "cui": ("texto", "Código Único de Inversiones.", "código"),
        "nombre_obra": ("texto", "Nombre de la obra.", "texto"),
        "entidad": ("texto", "Entidad responsable de la obra (entidad pública).", "texto"),
        "departamento": ("texto", "Departamento en mayúsculas y sin tildes.", "texto"),
        "provincia": ("texto", "Provincia en mayúsculas y sin tildes.", "texto"),
        "distrito": ("texto", "Distrito en mayúsculas y sin tildes.", "texto"),
        "ubigeo": ("texto de 6 dígitos", "Ubigeo INEI del distrito de la obra, tomado de escale_infraestructura (src/ubigeo_obras.py). Puede contradecir departamento/provincia/distrito cuando INFOBRAS los trae mal (ubigeo_metodo = manual).", "código"),
        "ubigeo_metodo": ("texto", "Cómo se asignó el ubigeo: exacto (mismos nombres que ESCALE), normalizado (difieren solo en tildes, eñe, guion bajo, nombre alterno o provincia del Callao), manual (ubicación de INFOBRAS corregida a mano; motivo en docs/nombres_sin_ubigeo.csv) o sin_ubigeo.", "categoría"),
        "estado": ("texto", "Estado de la obra en la ficha (PARALIZADA en todas las filas).", "texto"),
        "modalidad": ("texto", "Modalidad de ejecución.", "texto"),
        "naturaleza": ("texto", "Naturaleza de la obra.", "texto"),
        "tipo_obra": ("texto", "Tipo de obra.", "texto"),
        "monto_expediente_tecnico": ("decimal", "Monto del expediente técnico (del listado de INFOBRAS).", "soles"),
        "monto_ejecucion_acumulado": ("decimal", "Monto de ejecución acumulado.", "soles"),
        "avance_fisico_pct": ("decimal", "Porcentaje de avance físico del encabezado de la ficha.", "%"),
        "fecha_inicio": ("fecha AAAA-MM-DD", "Fecha de inicio de la obra.", "fecha"),
        "fecha_fin_prevista": ("fecha AAAA-MM-DD", "Fecha de fin prevista de la obra.", "fecha"),
        "periodo_ultimo_avance": ("texto", "Año / mes del último avance registrado.", "texto"),
        "n_avances": ("entero", "Número de avances mensuales registrados.", "avances"),
        "periodo_avance_paralizado": ("texto", "Año / mes del último avance en estado Paralizado.", "texto"),
        "causal_paralizacion": ("texto", "Causal de paralización registrada por la entidad. Puede ser genérica («Catalogo de Obra», «-»).", "texto"),
        "fecha_paralizacion": ("fecha AAAA-MM-DD", "Fecha de paralización del último avance paralizado.", "fecha"),
        "dias_paralizado": ("entero", "Días paralizada según el último avance paralizado.", "días"),
        "comentario_fisico": ("texto", "Comentario libre de la entidad sobre el avance físico.", "texto"),
        "comentario_valorizado": ("texto", "Comentario libre de la entidad sobre el avance valorizado.", "texto"),
        "latitud": ("decimal", "Latitud de la obra.", "grados"),
        "longitud": ("decimal", "Longitud de la obra.", "grados"),
        "avance_fisico_tabla": ("decimal", "Avance físico real del último periodo en la tabla de avances (para contrastar con el del encabezado).", "%"),
        "estado_listado": ("texto", "Estado que da el listado exportado por el buscador.", "texto"),
        "url_ficha": ("texto", "Dirección de la ficha pública.", "texto"),
        "fecha_lectura": ("fecha AAAA-MM-DD", "Día en que se leyó la ficha.", "fecha"),
        "causa_grupo": ("texto", "Grupo de causa asignado por reglas de palabras clave (config.CAUSAS_REGLAS) a partir de la causal y los comentarios; «otros» si ninguna regla aplica.", "categoría"),
        "causa_grupo_origen": ("texto", "De dónde salió el grupo: causal (la causal declarada tuvo coincidencias), comentario, sin_informacion u otros.", "categoría"),
    }),
    "citas_educacion": (CGR, {
        "termino": ("texto", "Palabra clave encontrada en la oración (educación, escuela, etc.).", "texto"),
        "cita": ("texto", "Oración literal del informe (limpia de saltos de línea). Citar con fuente_pdf y página.", "texto"),
    }),
    "frecuencia_terminos": (CGR, {
        "tipo": ("texto", "termino (palabra) o par (dos palabras seguidas).", "categoría"),
        "termino": ("texto", "Palabra o par de palabras, sin tildes y en minúsculas.", "texto"),
        "frecuencia": ("entero", "Veces que aparece en la narrativa de los informes de ese año.", "veces"),
        "tfidf": ("decimal", "Puntaje TF-IDF x 1000: frecuencia relativa en el año por log(años totales / años en que aparece). Alto = término propio de ese año; se listan los 40 de mayor puntaje (con al menos 3 apariciones).", "puntaje"),
        "anios_con_termino": ("entero", "Número de años (de los informes disponibles) en cuya narrativa aparece el término; si es igual al total de años, no distingue un año de otro.", "años"),
    }),
}

CGR_EXCEL = "Anexos Excel de los informes de la Contraloría (base de obras paralizadas)"
POR_TABLA_ANEXOS = {
    "contraloria_obras_corte": (CGR_EXCEL, {
        "corte": ("fecha AAAA-MM-DD", "Fecha de corte del anexo del que sale la fila (13 cortes con base obra por obra: sep-2023 a jun-2026).", "fecha"),
        "codigo_infobras": ("texto", "Código de la obra en INFOBRAS. Clave para unir con fichas_infobras.", "código"),
        "cui": ("texto", "Código Único de Inversiones.", "código"),
        "entidad": ("texto", "Entidad pública responsable de la obra, en mayúsculas y sin tildes.", "texto"),
        "evento": ("texto", "Evento registrado en INFOBRAS: PROCESO NORMAL, RECONSTRUCCION CON CAMBIOS, REACTIVACION ECONOMICA o EMBLEMATICAS.", "categoría"),
        "modalidad_ejecucion": ("texto", "Modalidad de ejecución (POR CONTRATA, ADMINISTRACION DIRECTA, etc.; los rótulos CONTRATA y APP se unificaron).", "categoría"),
        "tipo_obra": ("texto", "Tipo de obra (nivel 1) tal como lo trae el anexo; puede diferir de sector.", "categoría"),
        "tipo_obra_nivel2": ("texto", "Tipo de obra, nivel 2.", "categoría"),
        "tipo_obra_nivel3": ("texto", "Tipo de obra, nivel 3.", "categoría"),
        "nivel_gobierno": ("texto", "Nivel de gobierno de la entidad: G. NACIONAL, G. REGIONAL o G. LOCAL.", "categoría"),
        "sector": ("texto", "Sector de la obra (SECTOR del anexo; EDUCACION y EDUCACION/CULTURA son distintos).", "categoría"),
        "sector_agrupado": ("texto", "Sector con el agrupamiento del informe (columna SECTOR 2; si el corte no la trae, EDUCACION/CULTURA se cuenta como EDUCACION).", "categoría"),
        "causal_codigo": ("texto", "Número de la causal oficial (1 a 15); vacío en las causales nuevas que el anexo trae sin número.", "código"),
        "causal_paralizacion": ("texto", "Causal de paralización oficial (sin el número).", "texto"),
        "avance_fisico": ("decimal de 0 a 100", "Avance físico de la obra según INFOBRAS en el corte.", "%"),
        "rango_avance_fisico": ("texto", "Rango de avance físico del anexo.", "categoría"),
        "anio_inicio": ("entero", "Año de inicio de la obra.", "año"),
        "plazo_ejecucion_dias": ("entero", "Plazo de ejecución.", "días"),
        "departamento": ("texto", "Departamento en mayúsculas y sin tildes.", "texto"),
        "provincia": ("texto", "Provincia en mayúsculas y sin tildes.", "texto"),
        "distrito": ("texto", "Distrito en mayúsculas y sin tildes.", "texto"),
        "rango_inversion_mll": ("texto", "Rango de inversión (millones de soles) del anexo.", "categoría"),
        "fuente_excel": ("texto", "Anexo Excel de data/raw/contraloria del que sale la fila.", "texto"),
        "hoja": ("texto", "Hoja del Excel con la base de obras.", "texto"),
    }),
    "contraloria_obras_panel": (CGR_EXCEL, {
        "codigo_infobras": ("texto", "Código de la obra en INFOBRAS (una fila por obra).", "código"),
        "primer_corte": ("fecha AAAA-MM-DD", "Primer corte (de los 13 con base) en que la obra aparece en la lista. Si es sep-2023 (primer_corte_censurado) la obra puede estar desde antes.", "fecha"),
        "ultimo_corte": ("fecha AAAA-MM-DD", "Último corte en que la obra aparece.", "fecha"),
        "n_cortes": ("entero", "Número de cortes en que aparece (de 13).", "cortes"),
        "sigue_en_ultimo_corte": ("lógico", "TRUE si la obra está en el último corte (jun-2026).", "lógico"),
        "cortes_faltantes_intermedios": ("entero", "Cortes entre el primero y el último en que la obra no aparece.", "cortes"),
        "reingresos": ("entero", "Veces que la obra salió de la lista y volvió a entrar.", "veces"),
        "primer_corte_censurado": ("lógico", "TRUE si primer_corte es el primer corte del panel (sep-2023): no se sabe desde cuándo está.", "lógico"),
        "cui_ultimo": ("texto", "CUI en el último corte en que aparece.", "código"),
        "sector_agrupado_ultimo": ("texto", "Sector agrupado en el último corte en que aparece.", "categoría"),
        "nivel_gobierno_ultimo": ("texto", "Nivel de gobierno en el último corte en que aparece.", "categoría"),
        "causal_paralizacion_ultimo": ("texto", "Causal de paralización en el último corte en que aparece.", "texto"),
        "cod_departamento_ultimo": ("texto de 2 dígitos", "Código INEI del departamento en el último corte en que aparece.", "código"),
        "departamento_ultimo": ("texto", "Departamento en el último corte en que aparece.", "texto"),
        "provincia_ultimo": ("texto", "Provincia en el último corte en que aparece.", "texto"),
        "distrito_ultimo": ("texto", "Distrito en el último corte en que aparece.", "texto"),
        "avance_primer_corte": ("decimal de 0 a 100", "Avance físico en el primer corte en que aparece.", "%"),
        "avance_ultimo_corte": ("decimal de 0 a 100", "Avance físico en el último corte en que aparece.", "%"),
        "fuente": ("texto", "Tabla de la que se construye el panel.", "texto"),
    }),
    "contraloria_pim": (CGR, {
        "anio_pim": ("entero", "Año del presupuesto (PIM) al que se refiere la tabla.", "año"),
        "ambito": ("texto", "nacional o departamento.", "categoría"),
        "categoria": ("texto", "NACIONAL o nombre del departamento (mayúsculas, sin tildes).", "texto"),
        "obras_con_pim": ("entero", "Obras paralizadas con PIM asignado.", "obras"),
        "pct_obras_con_pim": ("decimal", "Porcentaje de las obras que tienen PIM, tal como lo publica el informe.", "%"),
        "obras_sin_pim": ("entero", "Obras paralizadas sin PIM.", "obras"),
        "pct_obras_sin_pim": ("decimal", "Porcentaje de las obras que no tienen PIM.", "%"),
        "obras_total": ("entero", "Obras paralizadas (con + sin PIM).", "obras"),
        "costo_con_pim_soles": ("decimal", "Solo en la fila nacional: costo actualizado de las obras con PIM.", "soles"),
        "costo_sin_pim_soles": ("decimal", "Solo en la fila nacional: costo actualizado de las obras sin PIM.", "soles"),
        "costo_total_soles": ("decimal", "Solo en la fila nacional: costo actualizado total.", "soles"),
        "pim_soles": ("decimal", "Solo en la fila nacional: PIM asignado a las obras que lo tienen.", "soles"),
    }),
    "contraloria_modalidad_ejecucion": (CGR, {
        "tabla": ("texto", "Tabla del informe: por_modalidad (todas las modalidades) o administracion_directa_y_contrata (solo esas dos).", "categoría"),
        "categoria": ("texto", "Modalidad de ejecución, en mayúsculas y sin tildes (CONTRATA y APP unificados).", "categoría"),
        "nivel_gobierno": ("texto", "NACIONAL, REGIONAL, LOCAL o TOTAL. El orden de las columnas se decide con los totales del informe, no con el rótulo del PDF.", "categoría"),
        "obras_paralizadas": ("entero", "Obras paralizadas de esa categoría y nivel; vacío si el PDF dejó la celda vacía.", "obras"),
        "orden_niveles": ("texto", "verificado = el orden de las columnas de nivel coincide con los totales por nivel de gobierno del mismo informe.", "texto"),
        "pct_obras": ("decimal", "Solo en filas TOTAL: porcentaje de obras, tal como lo publica el informe (algunos informes no lo traen).", "%"),
        "pct_costo": ("decimal", "Solo en filas TOTAL: porcentaje del costo, tal como lo publica el informe.", "%"),
    }),
    "contraloria_evento_infobras": (CGR, {
        "tabla": ("texto", "Siempre por_evento.", "categoría"),
        "categoria": ("texto", "Evento registrado en INFOBRAS (sin la nota al pie).", "categoría"),
        "nivel_gobierno": ("texto", "NACIONAL, REGIONAL, LOCAL o TOTAL. El orden de las columnas se decide con los totales del informe: en el PDF de jun-2026 el rótulo dice Nacional-Regional-Local pero las cifras van en Local-Nacional-Regional.", "categoría"),
        "obras_paralizadas": ("entero", "Obras paralizadas de ese evento y nivel.", "obras"),
        "orden_niveles": ("texto", "verificado = el orden coincide con los totales por nivel de gobierno del mismo informe.", "texto"),
        "pct_obras": ("decimal", "No viene en la tabla de eventos (vacío).", "%"),
        "pct_costo": ("decimal", "Solo en filas TOTAL: porcentaje del costo.", "%"),
    }),
    "contraloria_servicios_control_total": (CGR, {
        "tipo_servicio": ("texto", "Tipo de servicio de control: PREVIO, SIMULTANEO o POSTERIOR.", "categoría"),
        "cantidad": ("entero", "Servicios de control efectuados a obras paralizadas.", "servicios"),
        "pct": ("decimal", "Porcentaje del total de servicios, tal como lo publica el informe.", "%"),
    }),
    "contraloria_servicios_control_nivel_gobierno": (CGR, {
        "tipo_servicio": ("texto", "Tipo de servicio de control: PREVIO, SIMULTANEO o POSTERIOR.", "categoría"),
        "nivel_gobierno": ("texto", "NACIONAL, REGIONAL, LOCAL o TOTAL.", "categoría"),
        "cantidad": ("entero", "Servicios de control a obras de ese nivel de gobierno.", "servicios"),
        "pct": ("decimal", "Porcentaje que publica el informe (de la columna de nivel o del total, según el informe).", "%"),
        "orden_niveles": ("texto", "Cómo se fijó el orden de las columnas de nivel: verificado con la narración del informe o según el encabezado del PDF.", "texto"),
    }),
    "contraloria_servicios_control_departamento": (CGR, {
        "departamento": ("texto", "Departamento en mayúsculas y sin tildes.", "texto"),
        "control_previo": ("entero", "Servicios de control previo (una celda vacía en el PDF se guarda como 0).", "servicios"),
        "control_simultaneo": ("entero", "Servicios de control simultáneo; un servicio hecho a obras de varios departamentos se cuenta en cada uno (nota (*) del informe).", "servicios"),
        "control_posterior": ("entero", "Servicios de control posterior.", "servicios"),
        "total_servicios": ("entero", "Total de servicios del departamento; la suma de los departamentos supera el total nacional por la nota (*).", "servicios"),
    }),
    "contraloria_principales_obras": (CGR_EXCEL, {
        "orden_en_hoja": ("entero", "Orden de la obra en la hoja del anexo (dentro de cada departamento, por nivel de gobierno y costo).", "número"),
        "cui": ("texto", "Código Único de Inversiones.", "código"),
        "codigo_infobras": ("texto", "Código de la obra en INFOBRAS. Los anexos de 2025 en adelante no lo traen: se completa con la base obra por obra del mismo corte (ver codigo_infobras_de_base).", "código"),
        "descripcion_obra": ("texto", "Nombre de la inversión (proyecto público).", "texto"),
        "entidad": ("texto", "Entidad pública responsable.", "texto"),
        "nivel_gobierno": ("texto", "G. NACIONAL, G. REGIONAL o G. LOCAL.", "categoría"),
        "modalidad_ejecucion": ("texto", "Modalidad de ejecución.", "categoría"),
        "causal_codigo": ("texto", "Número de la causal oficial; vacío si el anexo no lo trae.", "código"),
        "causal_paralizacion": ("texto", "Causal de paralización oficial.", "texto"),
        "departamento": ("texto", "Departamento en mayúsculas y sin tildes.", "texto"),
        "codigo_infobras_de_base": ("lógico", "TRUE si codigo_infobras se completó desde la base obra por obra (contraloria_obras_corte) porque la hoja no lo traía.", "lógico"),
        "es_lista_completa": ("lógico", "TRUE en mar-2024, cuya hoja de principales obras trae la lista completa de obras (2 267 filas) y no solo las principales.", "lógico"),
        "fuente_excel": ("texto", "Anexo Excel de data/raw/contraloria del que sale la fila.", "texto"),
        "hoja": ("texto", "Hoja del Excel con la lista de principales obras.", "texto"),
    }),
}
POR_TABLA.update(POR_TABLA_ANEXOS)
# columnas cuyo nombre depende de los datos (una por corte): tabla -> (patron, (tipo, descripcion, unidad))
COLUMNAS_POR_PATRON = {
    "contraloria_obras_panel": (r"^avance_\d{4}-\d{2}-\d{2}$", ("decimal de 0 a 100", "Avance físico de la obra en el corte que indica el nombre de la columna; vacío si la obra no está en ese corte.", "%")),
}

# causa_grupo_origen y causa_grupo se agregan a fichas_infobras en la Fase 4; los demas usan COMUNES

# --- pasada ampliada por INFOBRAS (A4 + B1 + B2), src/scraper_infobras.py ---
_FICHA = POR_TABLA["fichas_infobras"][1]
_PERIODO = {
    "codigo_infobras": _FICHA["codigo_infobras"], "cui": _FICHA["cui"],
    "periodo": ("texto", "Año / mes del avance, como lo escribe INFOBRAS (por ejemplo «2026 / SEPTIEMBRE»).", "texto"),
    "anio": ("entero", "Año del avance (de la columna periodo).", "año"),
    "mes": ("entero", "Mes del avance, de 1 a 12 (de la columna periodo).", "mes"),
    "codigo_avance": ("texto", "Código del avance en INFOBRAS (enlace Mapa/Avance?codigo=…); vacío si la fila no tiene enlace.", "código"),
    "fecha_lectura": ("fecha AAAA-MM-DD", "Día en que se leyó la ficha en la pasada ampliada (no es el 2026-10-27 de fichas_infobras).", "fecha"),
}
POR_TABLA["infobras_avances"] = (INFOBRAS, {
    **_PERIODO,
    "fisico_programado": ("decimal", "Avance físico programado acumulado al mes, según la tabla «Avances de obra».", "%"),
    "fisico_real": ("decimal", "Avance físico real acumulado al mes, según la tabla «Avances de obra».", "%"),
    "estado": ("texto", "Estado de la obra en ese mes (En Ejecución, Paralizado, etc.), tal como lo escribe INFOBRAS.", "texto"),
})
POR_TABLA["infobras_paralizaciones"] = (INFOBRAS, {
    **_PERIODO,
    "tramo": ("entero", "Número del tramo de paralización de la obra: meses en estado Paralizado seguidos en la tabla de avances (1 = el más antiguo).", "número"),
    "posicion_tramo": ("texto", "Lugar del mes en su tramo: unico, inicio, medio o fin.", "categoría"),
    "detalle_leido": ("lógico", "TRUE si se abrió la página de detalle del avance. Con config.INFOBRAS_DETALLE_PARALIZACIONES = por_tramo solo se abren el primer y el último mes de cada tramo; los meses «medio» quedan sin detalle.", "lógico"),
    "causal_paralizacion": ("texto", "Causal registrada en el detalle del avance. Puede ser genérica («Catalogo de Obra», «-»).", "texto"),
    "fecha_paralizacion": ("fecha AAAA-MM-DD", "Fecha de paralización registrada en el detalle del avance.", "fecha"),
    "dias_paralizado": ("entero", "Días paralizada según el detalle del avance.", "días"),
    "comentario_fisico": _FICHA["comentario_fisico"], "comentario_valorizado": _FICHA["comentario_valorizado"],
})
POR_TABLA["infobras_fichas_ampliadas"] = (INFOBRAS, {
    **{c: _FICHA[c] for c in ("codigo_infobras", "cui", "nombre_obra", "entidad", "departamento", "provincia", "distrito", "ubigeo",
                              "ubigeo_metodo", "modalidad", "naturaleza", "tipo_obra", "monto_ejecucion_acumulado", "avance_fisico_pct",
                              "fecha_inicio", "fecha_fin_prevista", "periodo_ultimo_avance", "n_avances", "periodo_avance_paralizado",
                              "causal_paralizacion", "fecha_paralizacion", "dias_paralizado", "latitud", "longitud",
                              "avance_fisico_tabla", "url_ficha")},
    "fecha_lectura": _PERIODO["fecha_lectura"],
    "origen": ("texto", "Por qué se leyó: infobras_paralizada_2026-10-27 (las 198 de fichas_infobras) o contraloria_educacion_2026-06 (obras de Educación/Cultura del anexo de junio de 2026 que no estaban como Paralizada en INFOBRAS, tarea A4).", "categoría"),
    "estado": ("texto", "Estado de la obra en la ficha el día de la lectura (PARALIZADA, EN EJECUCIÓN, FINALIZADO, etc.).", "texto"),
    "estado_listado_todos": ("texto", "Estado según el listado de Educación con todos los estados exportado del buscador (data/raw/infobras).", "texto"),
    "monto_expediente_tecnico": ("decimal", "Monto del expediente técnico, del listado de Educación con todos los estados.", "soles"),
    "n_paralizados": ("entero", "Número de avances mensuales en estado Paralizado (filas de la obra en infobras_paralizaciones).", "avances"),
})
# --- ubicacion corregida por ubigeo y tramos de paralizacion ---
_DEP_INFOBRAS = ("texto", "Departamento tal como lo publica INFOBRAS (en mayúsculas y sin tildes). Difiere de departamento en 2 obras (135083 y 543835: INFOBRAS dice Huancavelica y son de Ica).", "texto")
POR_TABLA["fichas_infobras"][1]["departamento_infobras"] = _DEP_INFOBRAS
POR_TABLA["infobras_fichas_ampliadas"][1]["departamento_infobras"] = _DEP_INFOBRAS
for _t in ("fichas_infobras", "infobras_fichas_ampliadas"):
    POR_TABLA[_t][1]["departamento"] = ("texto", "Departamento del ubigeo (corregido), en mayúsculas y sin tildes. El que publica INFOBRAS está en departamento_infobras.", "texto")
    POR_TABLA[_t][1]["cod_departamento"] = ("texto de 2 dígitos", "Código INEI del departamento del ubigeo (Callao = 07). Texto, con cero a la izquierda.", "código")
POR_TABLA["infobras_paralizaciones"][1]["causal_paralizacion_tramo"] = ("texto", "Causal del tramo de paralización: la del detalle leído, repetida en los meses del medio del tramo (que no se abren).", "texto")
POR_TABLA["infobras_paralizaciones"][1]["fecha_paralizacion_tramo"] = ("fecha AAAA-MM-DD", "Fecha de paralización del tramo, repetida en los meses del medio del tramo.", "fecha")
# --- C3: los 4 niveles de logro de SICRECE ---
POR_TABLA["enla_niveles_logro"] = ("SICRECE (UMC, MINEDU), acceso público", {
    "region": ("texto", "Región ENLA como la escribe SICRECE (con tildes; Lima Metropolitana y Lima Provincias van separadas).", "texto"),
    "region_clave": ("texto", "Región en mayúsculas y sin tildes, para unir con otras tablas.", "texto"),
    "evaluacion": ("texto", "MUESTRAL o CENSAL (la ENLA 2024 de 4.° primaria fue censal).", "categoría"),
    "grado": ("texto", "Grado evaluado: 2.°, 4.° o 6.° de primaria; 2.° o 5.° de secundaria.", "texto"),
    "area": ("texto", "Área evaluada: lectura o matematica.", "texto"),
    "previo_al_inicio": ("decimal de 0 a 100", "% de estudiantes en el nivel Previo al inicio.", "%"),
    "en_inicio": ("decimal de 0 a 100", "% de estudiantes en el nivel En inicio.", "%"),
    "en_proceso": ("decimal de 0 a 100", "% de estudiantes en el nivel En proceso.", "%"),
    "satisfactorio": ("decimal de 0 a 100", "% de estudiantes en el nivel Satisfactorio (igual al de enla_regiones).", "%"),
    "archivo_json": ("texto", "Archivo de data/raw/enla del que sale (procedencia).", "texto"),
})
# --- MEF (Formato 12-B) y locales de ESCALE en construccion ---
POR_TABLA["mef_f12b_obras"] = ("MEF, Portal de Datos Abiertos: Formato 12-B de inversiones", {
    "cui": ("texto", "Código Único de Inversiones (CODIGO_UNICO del MEF).", "código"),
    "estado_mef": ("texto", "Estado de la inversión en el MEF (ACTIVO, DESACTIVADO TEMPORAL, CERRADO, ...).", "categoría"),
    "primer_devengado": ("texto AAAAMM", "Periodo del primer devengado registrado en el SIAF.", "periodo"),
    "ultimo_devengado": ("texto AAAAMM", "Periodo del último devengado registrado en el SIAF.", "periodo"),
    "devengado_hasta_anio_anterior_soles": ("decimal", "Devengado acumulado hasta el año anterior al del archivo.", "soles"),
    "devengado_anio_actual_soles": ("decimal", "Devengado del año del archivo.", "soles"),
    "pim_anio_actual_soles": ("decimal", "Presupuesto Institucional Modificado del año del archivo.", "soles"),
    "avance_fisico_mef_pct": ("decimal", "Avance físico declarado en el Formato 12-B.", "%"),
    "avance_ejecucion_mef_pct": ("decimal", "Avance de ejecución general declarado en el Formato 12-B.", "%"),
    "ult_problema": ("texto", "Última problemática registrada (texto libre de la entidad; se omiten los nombres de personas). No se guardan el estado situacional ni los próximos pasos: son narrativos y traen nombres de ingenieros.", "texto"),
    "fecha_ult_act_f12b": ("fecha", "Fecha de la última actualización del Formato 12-B.", "fecha"),
    "ult_periodo_reg_f12b": ("texto", "Último periodo de registro del Formato 12-B.", "periodo"),
    "inicio_ejec_fisica": ("fecha", "Fecha de inicio de ejecución física registrada en el Formato 12-B.", "fecha"),
    "culmina_ejec_fisica": ("fecha", "Fecha de término de ejecución física registrada en el Formato 12-B.", "fecha"),
    "devengado_total_soles": ("decimal", "devengado_hasta_anio_anterior_soles + devengado_anio_actual_soles.", "soles"),
    "archivo_mef": ("texto", "Archivo de data/raw/mef del que sale (procedencia).", "texto"),
})
POR_TABLA["escale_obras_en_local"] = ("ESCALE (Censo Educativo 2025): archivo de local, pregunta 2.1", {
    "anio": ("entero", "Año del Censo Educativo (solo 2025 trae el CUI de la obra).", "año"),
    "codlocal": ("texto", "Código del local educativo.", "código"),
    "ubigeo": ("texto de 6 dígitos", "Ubigeo del local (CODGEO).", "código"),
    "departamento": ("texto", "Departamento del local, como lo escribe ESCALE (mayúsculas).", "texto"),
    "provincia": ("texto", "Provincia del local.", "texto"),
    "distrito": ("texto", "Distrito del local.", "texto"),
    "tipo_construccion": ("texto", "TOTAL o PARCIAL: si la construcción/reconstrucción es de todo el local o de parte.", "categoría"),
    "cui": ("texto", "CUI de la obra que el local declara en el Censo (vacío si no lo informó).", "código"),
})
# --- producto final: el diccionario de cada tabla vive en producto_final.py junto a su construccion ---
import producto_final   # noqa: E402  (se importa aqui para no repetir las descripciones)
for _tabla, _columnas in producto_final.DICCIONARIO_FINAL.items():
    POR_TABLA[_tabla] = (producto_final.FUENTE_FINAL, {c: (tipo, desc, unidad) for c, tipo, desc, unidad in _columnas})
TABLAS_PDF = tuple(POR_TABLA)


def construir_diccionario_pdf():
    """Diccionario (tabla, columna, ...) de las tablas del proyecto PDF; los años se calculan con los datos."""
    filas = []
    for tabla, (fuente, columnas) in POR_TABLA.items():
        ruta = next((c / f"{tabla}.csv" for c in (config.PROCESSED, config.COMPONENTES, config.FINAL) if (c / f"{tabla}.csv").exists()), None)
        if ruta is None:
            continue
        datos = pd.read_csv(ruta, dtype={"cod_departamento": str, "codigo_infobras": str, "cui": str, "ubigeo": str}, encoding="utf-8-sig")
        patron = COLUMNAS_POR_PATRON.get(tabla)
        por_patron = lambda c: patron[1] if patron and re.match(patron[0], c) else None
        sin_describir = [c for c in datos.columns if c not in columnas and c not in COMUNES and por_patron(c) is None]
        if sin_describir:
            raise KeyError(f"{tabla}: columnas sin descripcion en diccionario_pdf.py: {sin_describir}")
        for columna in datos.columns:
            tipo, descripcion, unidad = columnas.get(columna) or por_patron(columna) or COMUNES[columna]
            fuente_col = PROCEDENCIA if columna in ("fuente_pdf", "pagina", "tabla_n") else fuente
            anios = ""
            if "anio" in datos and datos[columna].notna().any():
                anios = ", ".join(str(a) for a in sorted(datos.loc[datos[columna].notna(), "anio"].unique()))
            elif "fecha_lectura" in datos:
                anios = str(datos.fecha_lectura.iloc[0])[:4]
            filas.append({"tabla": tabla, "columna": columna, "tipo": tipo, "descripcion": descripcion, "unidad": unidad,
                          "fuente": fuente_col, "anios": anios, "notas": ""})
    return pd.DataFrame(filas)
