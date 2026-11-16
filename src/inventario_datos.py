"""Inventario de toda la data del proyecto: que tablas hay, cuantas filas, que periodo cubren y que necesidades cubren.

Las cifras se leen de los archivos (nada se escribe a mano salvo la descripcion de cada tabla y el cuadro de necesidades).
Salida: docs/inventario_datos.csv y docs/inventario_datos.md
"""
import pandas as pd

import config
import utils

# tabla -> (fuente, que es, una fila por, columna de periodo)
TABLAS = {
    "escale_infraestructura": ("ESCALE (Censo Educativo)", "Infraestructura de locales educativos publicos: servicios basicos, ruralidad, riesgo estructural", "distrito y año", "anio"),
    "enla_regiones": ("SICRECE (MINEDU-UMC)", "% de estudiantes en nivel Satisfactorio en Lectura y Matematica", "region, año, grado y evaluacion", "anio"),
    "mef_f12b_obras": ("MEF (Portal de Datos Abiertos)", "Devengado, PIM, ultimo devengado y problematica de cada obra (por CUI), del Formato 12-B", "CUI", "fecha_ult_act_f12b"),
    "escale_obras_en_local": ("ESCALE (Censo Educativo 2025)", "Locales que declaran estar en construccion, con el CUI de la obra", "local", "anio"),
    "dashboard_obras": ("PRODUCTO FINAL", "EL CSV UNICO del proyecto (alimenta el dashboard HTML): obras, cortes de la Contraloria, series por departamento y pais, causales y contexto (filtrar por tipo_registro)", "tipo_registro (obra, corte, departamento...)", "fecha_corte"),
    "obras_maestra": ("PRODUCTO FINAL", "Una fila por obra de Educacion/Cultura (429): INFOBRAS + ubigeo + Contraloria + MEF + ESCALE + causa", "obra", "fecha_lectura_infobras"),
    "resumen_region": ("PRODUCTO FINAL", "Una fila por region ENLA (26): obras paralizadas, causas, Contraloria, ESCALE y ENLA", "region", "escale_anio"),
    "serie_pais_educacion": ("PRODUCTO FINAL", "Cifras oficiales por corte: pais y sector Educacion (con la cifra corregida)", "corte", "fecha_corte"),
    "serie_educacion_departamento": ("PRODUCTO FINAL", "Obras de Educacion por departamento y corte (anexos Excel)", "corte y departamento", "fecha_corte"),
    "causales_por_corte": ("PRODUCTO FINAL", "Causales oficiales por corte con el grupo de causa del proyecto", "corte y causal", "fecha_corte"),
    "enla_niveles_logro": ("SICRECE (MINEDU-UMC)", "Los 4 niveles de logro (previo al inicio, en inicio, en proceso, satisfactorio) en Lectura y Matematica", "region, año, grado, evaluacion y area", "anio"),
    "enla_pdf": ("PDF de la EM 2022 (MINEDU-UMC)", "Lo mismo que enla_regiones, leido del PDF; trae tambien 2019", "region, año, grado y area", "anio"),
    "fichas_infobras": ("INFOBRAS (Contraloria)", "Obras educativas en estado Paralizada: ubicacion, entidad, montos, avance, causal, dias paralizada, grupo de causa", "obra", "fecha_lectura"),
    "cifras_oficiales_contraloria": ("Informes de obras paralizadas (Contraloria)", "Cifras oficiales: total nacional, por sector (incluye Educacion) y por departamento", "corte y ambito (pais, sector, departamento)", "fecha_corte"),
    "contraloria_causales": ("Informes de obras paralizadas (Contraloria)", "Causales de paralizacion declaradas por las entidades, con obras y montos", "corte y causal", "fecha_corte"),
    "contraloria_distribuciones": ("Informes de obras paralizadas (Contraloria)", "Nivel de gobierno, rango de costo y rango de avance fisico", "corte y categoria", "fecha_corte"),
    "contraloria_educacion_departamento": ("Anexos Excel (Contraloria)", "Obras de Educacion paralizadas por departamento", "corte y departamento", "fecha_corte"),
    "contraloria_obras_corte": ("Anexos Excel (Contraloria)", "Datos por obra y corte: causal oficial, nivel de gobierno, sector, avance fisico, tipo, año de inicio, plazo, provincia, distrito, evento, CUI", "obra y corte (13 cortes)", "corte"),
    "contraloria_obras_panel": ("Anexos Excel (Contraloria)", "Panel historico por obra: primer y ultimo corte, numero de cortes, si sigue, reingresos y avance por corte", "obra", "ultimo_corte"),
    "contraloria_pim": ("Informes de obras paralizadas (Contraloria)", "Obras con y sin presupuesto (PIM) por departamento y total nacional", "corte y departamento (o nacional)", "fecha_corte"),
    "contraloria_modalidad_ejecucion": ("Informes de obras paralizadas (Contraloria)", "Obras y costo por modalidad de ejecucion y nivel de gobierno", "corte, tabla, modalidad y nivel", "fecha_corte"),
    "contraloria_evento_infobras": ("Informes de obras paralizadas (Contraloria)", "Obras y costo por evento registrado en INFOBRAS y nivel de gobierno", "corte, evento y nivel", "fecha_corte"),
    "contraloria_servicios_control_total": ("Informes de obras paralizadas (Contraloria)", "Servicios de control efectuados por tipo (previo, simultaneo, posterior)", "corte y tipo de servicio", "fecha_corte"),
    "contraloria_servicios_control_nivel_gobierno": ("Informes de obras paralizadas (Contraloria)", "Servicios de control por tipo y nivel de gobierno", "corte, tipo y nivel", "fecha_corte"),
    "contraloria_servicios_control_departamento": ("Informes de obras paralizadas (Contraloria)", "Servicios de control por departamento y tipo (2023 en adelante)", "corte y departamento", "fecha_corte"),
    "contraloria_principales_obras": ("Anexos Excel (Contraloria)", "Principales obras paralizadas por departamento (entidad, costo, causal, modalidad)", "obra y corte", "fecha_corte"),
    "citas_educacion": ("Informes de obras paralizadas (Contraloria)", "Oraciones de los informes sobre educacion, con archivo y pagina", "oracion", "fecha_corte"),
    "frecuencia_terminos": ("Informes de obras paralizadas (Contraloria)", "Terminos y pares de terminos mas frecuentes por año", "año, tipo y termino", "anio"),
    # --- pasada ampliada por INFOBRAS (A4 + B1 + B2) ---
    "infobras_avances": ("INFOBRAS (Contraloria)", "Avances mensuales de cada obra: fisico programado y real, estado del mes (B1)", "obra y mes", "anio"),
    "infobras_paralizaciones": ("INFOBRAS (Contraloria)", "Meses en estado Paralizado de cada obra, agrupados en tramos, con causal, fecha y dias (B2)", "obra y mes paralizado", "anio"),
    "infobras_fichas_ampliadas": ("INFOBRAS (Contraloria)", "Ficha actual de las 198 obras paralizadas y de las obras de Educacion de la Contraloria que ya no estan como Paralizada, con su estado (A4) y ubigeo", "obra", "fecha_lectura"),
}

# necesidad del proyecto -> (estado, donde esta, comentario). Estado: SI / PARCIAL / NO
# Cifras de la corrida del 2026-11-12 (INFOBRAS leido el 27-oct y el 11-nov-2026; Contraloria hasta jun-2026; MEF: foto mensual)
NECESIDADES = [
    ("Lista de obras educativas paralizadas (estado, monto, ubicacion)", "SI", "obras_maestra (infobras_fichas_ampliadas)",
     "429 obras: las 198 paralizadas en INFOBRAS al 27-oct + las de Educacion de la Contraloria (jun-2026); estado leido el 11-nov-2026 (179 siguen paralizadas). Es una foto, no una serie"),
    ("Serie historica de obras paralizadas por obra", "PARCIAL", "contraloria_obras_corte, contraloria_obras_panel; infobras_avances",
     "Contraloria: 13 cortes (sep-2023 a jun-2026); antes solo cifras agregadas de los PDF. INFOBRAS: avance mensual de cada una de las 429 obras"),
    ("Cifras oficiales para validar la base (pais, Educacion, departamento)", "SI", "cifras_oficiales_contraloria",
     "21 cortes; INFOBRAS y la Contraloria son poblaciones distintas (198 vs 341 obras de Educacion, 110 en comun; ver hallazgos_pdf.md)"),
    ("Causas de paralizacion", "SI", "obras_maestra.causa_grupo_final / causa_macro; contraloria_causales",
     "Por obra: NLP con 3 fuentes (causal oficial, comentarios de INFOBRAS, problematica del MEF); 417 de 429 con causa. Comentarios y causal oficial coinciden en 49 % de las obras con ambas"),
    ("Montos (costo actualizado, saldo, expediente tecnico)", "SI", "cifras_oficiales_contraloria, contraloria_obras_corte, obras_maestra",
     "98 filas de la Contraloria con costo 0 o vacio y 9 con saldo mayor que el costo (marcadas, sin corregir)"),
    ("Gasto devengado por obra (MEF)", "PARCIAL", "mef_f12b_obras, obras_maestra",
     "Formato 12-B por CUI: 361 de las 414 obras con CUI valido aparecen; 15 tienen CUI NO ASOCIADO"),
    ("Tiempo de paralizacion", "SI", "infobras_paralizaciones, obras_maestra",
     "Las 429 obras: meses paralizados agrupados en tramos, con fecha y dias (8 739 meses; detalle leido del primer y ultimo mes de cada tramo). Los PDF no lo traen"),
    ("Nivel de gobierno", "PARCIAL", "contraloria_obras_corte; contraloria_distribuciones",
     "Por obra solo en las obras de la lista de la Contraloria; en INFOBRAS solo el nombre de la entidad"),
    ("Departamento / provincia / distrito de cada obra", "SI", "obras_maestra (ubigeo, latitud, longitud)",
     "Ubigeo INEI en las 429 (4 corregidas a mano: INFOBRAS traia mal la ubicacion). Coordenadas en 412; 17 no las tienen en INFOBRAS"),
    ("Infraestructura escolar por distrito", "SI", "escale_infraestructura, escale_distrito_ampliado",
     "5 indicadores 2022 a 2025; 16 indicadores mas solo para 2025"),
    ("Aprendizajes (ENLA) por region", "SI", "enla_regiones, enla_niveles_logro, enla_pdf",
     "2022 a 2025 (+2019 en enla_pdf); solo por region (no hay UGEL ni distrito); SICRECE no devolvio 3 combinaciones de año y grado"),
    ("Texto citable de los informes", "PARCIAL", "citas_educacion", "Pocas citas: los informes hablan poco de educacion"),
    ("Presupuesto asignado (PIM) por departamento", "PARCIAL", "contraloria_pim", "Solo 4 cortes (set-2025 a jun-2026): los informes anteriores no traen la tabla"),
    ("Datos de ESCALE o ENLA de 2026", "NO", "-", "Aun no publicados")]


def _periodo(tabla, columna):
    if columna not in tabla or tabla[columna].dropna().empty:
        return ""
    valores = tabla[columna].dropna().astype(str)
    if columna == "anio":
        return f"{valores.min()} a {valores.max()}"
    return f"{valores.min()} a {valores.max()}" if valores.min() != valores.max() else valores.min()


def inventario_tablas():
    filas = []
    for nombre, (fuente, que_es, grano, col_periodo) in TABLAS.items():
        carpeta = config.COMPONENTES if fuente == "PRODUCTO FINAL" else config.PROCESSED
        if nombre == "dashboard_obras":
            carpeta = config.FINAL
        ruta = carpeta / f"{nombre}.csv"
        archivo = ruta.relative_to(config.RAIZ).as_posix()
        if not ruta.exists():
            filas.append({"tabla": nombre, "fuente": fuente, "que_es": que_es, "una_fila_por": grano, "filas": 0, "columnas": 0,
                          "periodo": "NO EXISTE", "archivo": archivo})
            continue
        datos = pd.read_csv(ruta, encoding="utf-8-sig", low_memory=False)
        filas.append({"tabla": nombre, "fuente": fuente, "que_es": que_es, "una_fila_por": grano, "filas": len(datos),
                      "columnas": datos.shape[1], "periodo": _periodo(datos, col_periodo), "archivo": archivo})
    return pd.DataFrame(filas)


def inventario_raw():
    """Archivos descargados por fuente (data/raw)."""
    filas = []
    if not config.RAW.exists():   # modo --desde-tablas (por ejemplo en GitHub): los datos crudos no se publican
        return pd.DataFrame(columns=["fuente", "archivos", "mb", "anios"])
    for carpeta in sorted(p for p in config.RAW.iterdir() if p.is_dir()):
        archivos = [a for a in carpeta.rglob("*") if a.is_file()]
        anios = sorted({a.parent.name for a in archivos if a.parent.name.isdigit()})
        filas.append({"fuente": carpeta.name, "archivos": len(archivos), "mb": round(sum(a.stat().st_size for a in archivos) / 1024 / 1024, 1),
                      "anios": ", ".join(anios)})
    return pd.DataFrame(filas)


def _md(tabla):
    columnas = list(tabla.columns)
    lineas = ["| " + " | ".join(columnas) + " |", "|" + "|".join("---" for _ in columnas) + "|"]
    lineas += ["| " + " | ".join("" if pd.isna(v) else str(v) for v in fila) + " |" for fila in tabla.itertuples(index=False)]
    return "\n".join(lineas)


def construir():
    """Escribe docs/inventario_datos.csv y .md; devuelve (tablas, raw, necesidades)."""
    tablas, raw = inventario_tablas(), inventario_raw()
    necesidades = pd.DataFrame(NECESIDADES, columns=["necesidad", "estado", "donde", "comentario"])
    tablas.to_csv(config.DOCS / "inventario_datos.csv", index=False, encoding="utf-8-sig")
    texto = f"""# Inventario de datos del proyecto

Generado automaticamente por `src/inventario_datos.py` ({pd.Timestamp.today():%Y-%m-%d}). Cifras leidas de los archivos.

## Tablas finales (data/processed)

{_md(tablas.drop(columns='archivo'))}

## Archivos descargados (data/raw, nunca se modifican)

{_md(raw)}

## Necesidades del proyecto y que cubrimos

{_md(necesidades)}

SI = cubierto; PARCIAL = hay algo pero con limites (ver comentario); NO = no tenemos.
Detalle de columnas: `docs/diccionario.csv`. Validaciones y limites: `docs/hallazgos_pdf.md`.
"""
    (config.DOCS / "inventario_datos.md").write_text(texto, encoding="utf-8")
    utils.log(f"INVENTARIO DE DATOS: {len(tablas)} tablas, {int(raw.archivos.sum())} archivos en data/raw; escrito docs/inventario_datos.md")
    return tablas, raw, necesidades
