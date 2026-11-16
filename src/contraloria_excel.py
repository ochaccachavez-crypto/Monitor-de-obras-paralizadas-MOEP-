"""Tareas de los anexos Excel: datos de la Contraloria desde los anexos Excel y los PDF ya extraidos (sin navegador).

  A2  leer_obras_corte / construir_obras_corte  -> data/processed/contraloria_obras_corte.csv
  A3  construir_panel                           -> data/processed/contraloria_obras_panel.csv
  B7  corregir_educacion                        -> columna obras_educacion_corregida en cifras_oficiales_contraloria.csv
  B3  construir_pim                             -> data/processed/contraloria_pim.csv
  B5  construir_rangos_2022                     -> filas nuevas en contraloria_distribuciones.csv
  B4  construir_modalidad / evento / servicios  -> un CSV por tipo en data/processed
  B6  construir_principales_obras               -> data/processed/contraloria_principales_obras.csv
Reglas: data/raw no se modifica; sin datos personales; lugares en MAYUSCULAS sin tildes; codigos como texto.
"""
import re

import pandas as pd

import config
import leer_pdf
import tablas_finales as tf
from leer_pdf import log

OBRAS_CORTE = config.PROCESSED / "contraloria_obras_corte.csv"
OBRAS_PANEL = config.PROCESSED / "contraloria_obras_panel.csv"

# campo de salida -> patron (sobre el nombre de columna normalizado). El primero que coincida gana;
# asi se sobrevive a los cambios de nombre entre cortes ('SECTOR 2'/'SECTOR2', 'SALDO DE INVERSION'/'SALDO DE LA INVERSION', ...).
PATRONES = {
    "codigo_infobras": r"CODIGO INFOBRAS",
    "cui": r"CUI$",
    "entidad": r"ENTIDAD$",
    "evento": r"EVENTO$",
    "modalidad_ejecucion": r"MODALIDAD DE EJECUCION",
    "tipo_obra": r"TIPO DE OBRA$",
    "tipo_obra_nivel2": r"TIPO DE OBRA \(NIVEL 2\)",
    "tipo_obra_nivel3": r"TIPO DE OBRA \(NIVEL 3\)",
    "nivel_gobierno": r"NIVEL DE GOBIERNO",
    "sector": r"SECTOR$",
    "sector_agrupado": r"SECTOR ?2$",
    "causal_paralizacion": r"CAUSAL PARALIZACION",
    "avance_fisico": r"AVANCE FISICO$",
    "rango_avance_fisico": r"RANGO AVANCE FISICO",
    "anio_inicio": r"ANO INICIO OBRA",
    "plazo_ejecucion_dias": r"PLAZO DE EJECUCION",
    "departamento": r"DEPARTAMENTO",
    "provincia": r"PROVINCIA",
    "distrito": r"DISTRITO",
    "costo_actualizado_soles": r"COSTO ACTUALIZADO",
    "saldo_inversion_soles": r"SALDO DE (LA )?INVERSION",
    "rango_inversion_mll": r"RANGO DE INVERSION \(",
}
COLUMNAS_OBRAS_CORTE = ["corte", "codigo_infobras", "cui", "entidad", "evento", "modalidad_ejecucion", "tipo_obra", "tipo_obra_nivel2",
                        "tipo_obra_nivel3", "nivel_gobierno", "sector", "sector_agrupado", "causal_codigo", "causal_paralizacion",
                        "avance_fisico", "rango_avance_fisico", "anio_inicio", "plazo_ejecucion_dias", "cod_departamento", "departamento",
                        "provincia", "distrito", "costo_actualizado_soles", "saldo_inversion_soles", "rango_inversion_mll",
                        "fuente_excel", "hoja"]
ALIAS_MODALIDAD = {"CONTRATA": "POR CONTRATA", "ASOCIACION PUBLICA PRIVADA - APP": "ASOCIACION PUBLICA PRIVADA APP",
                   "APP / CONCESIONES": "ASOCIACION PUBLICA PRIVADA APP",
                   "ADM. DIRECTA": "ADMINISTRACION DIRECTA", "OBRAS POR IMPUESTO": "OBRAS POR IMPUESTOS"}


def _texto_codigo(serie):
    """'2077997.0' -> '2077997'; vacio -> NA. Los codigos son texto."""
    return serie.astype("string").str.strip().str.replace(r"\.0+$", "", regex=True).replace("", pd.NA)


def leer_obras_corte(ruta):
    """Una fila por obra de un anexo Excel (hoja base), con las columnas de PATRONES. None si el anexo no trae la base.

    Cada columna se busca por patron; las que un corte no tiene quedan vacias. El corte sale de leer_pdf.fechas_de_corte().
    """
    ubicada = tf.hoja_base(ruta)
    if ubicada is None:
        return None
    hoja, fila = ubicada
    base = pd.read_excel(ruta, sheet_name=hoja, header=fila, dtype=str)
    base.columns = [tf.normalizar(c) for c in base.columns]
    base = base.loc[:, ~base.columns.duplicated()]

    def columna(campo):
        return next((c for c in base.columns if re.match(PATRONES[campo], c)), None)

    salida = pd.DataFrame(index=base.index)
    for campo in PATRONES:
        c = columna(campo)
        salida[campo] = base[c] if c else pd.NA
    # solo filas con codigo numerico: el anexo de dic-2024 trae 3 notas al pie ('* Obras culminadas con observaciones', ...)
    salida = salida[salida.codigo_infobras.str.strip().str.fullmatch(r"\d+(\.0+)?", na=False)].copy()

    for c in ("codigo_infobras", "cui"):
        salida[c] = _texto_codigo(salida[c])
    for c in ("avance_fisico", "plazo_ejecucion_dias", "costo_actualizado_soles", "saldo_inversion_soles"):
        salida[c] = pd.to_numeric(salida[c], errors="coerce")
    salida["anio_inicio"] = pd.to_numeric(salida.anio_inicio, errors="coerce").astype("Int64")
    salida["plazo_ejecucion_dias"] = salida.plazo_ejecucion_dias.round().astype("Int64")
    for c in ("entidad", "evento", "modalidad_ejecucion", "tipo_obra", "tipo_obra_nivel2", "tipo_obra_nivel3", "nivel_gobierno", "sector",
              "causal_paralizacion", "rango_avance_fisico", "provincia", "distrito", "rango_inversion_mll"):
        salida[c] = salida[c].map(lambda x: tf.normalizar(x) if pd.notna(x) else pd.NA)
    salida["modalidad_ejecucion"] = salida.modalidad_ejecucion.replace(ALIAS_MODALIDAD)
    # sector agrupado: el informe cuenta Educacion y Educacion/Cultura juntos (columna 'SECTOR 2'; si no existe, se deriva)
    agrupado = salida.sector_agrupado.map(lambda x: tf.normalizar(x) if pd.notna(x) else pd.NA)
    salida["sector_agrupado"] = agrupado.where(agrupado.notna(), salida.sector.replace({"EDUCACION/CULTURA": "EDUCACION"}))
    # causal: '3 DISCREPANCIAS, ...' -> codigo 3 + texto; algunos cortes traen la causal sin numero
    partes = salida.causal_paralizacion.str.extract(r"^(\d+)\s+(.*)$")
    salida["causal_codigo"] = partes[0].astype("string")
    salida["causal_paralizacion"] = partes[1].where(partes[1].notna(), salida.causal_paralizacion)
    # lugares: departamento canonico (misma regla del resto del proyecto)
    dep_crudo = salida.departamento
    salida["departamento"] = dep_crudo.map(tf.departamento_canonico)
    sin_reconocer = salida.departamento.isna() & dep_crudo.notna()
    if sin_reconocer.any():
        log(f"AVISO A2: {ruta.name}: {sin_reconocer.sum()} obra(s) con departamento no reconocido: {sorted(set(dep_crudo[sin_reconocer]))[:5]}")
    salida["cod_departamento"] = salida.departamento.map(config.DEPARTAMENTOS)
    salida["fuente_excel"], salida["hoja"] = ruta.name, hoja
    salida["corte"] = leer_pdf.fechas_de_corte()[ruta.name]
    return salida.reindex(columns=COLUMNAS_OBRAS_CORTE).reset_index(drop=True)


def rutas_con_base():
    """Los anexos Excel que traen la base obra por obra (13 cortes), una ruta por corte."""
    cortes = leer_pdf.fechas_de_corte()
    rutas = {}
    for ruta in sorted(config.RAW.glob("contraloria/*/*.xlsx")):
        if "anexo_03" in ruta.name or ruta.name not in cortes or tf.hoja_base(ruta) is None:
            continue
        rutas.setdefault(cortes[ruta.name], ruta)
    return [rutas[c] for c in sorted(rutas)]


def construir_obras_corte():
    """Apila los 13 cortes: una fila por obra y corte."""
    return pd.concat([leer_obras_corte(r) for r in rutas_con_base()], ignore_index=True)


def validar_obras_corte(obras):
    """Compara filas por corte contra leer_base_excel (la lectura ya validada del proyecto). Devuelve DataFrame con ok."""
    filas = []
    for ruta in rutas_con_base():
        base = tf.leer_base_excel(ruta)
        base = base[base.codigo.str.strip().str.fullmatch(r"\d+(\.0+)?", na=False)]   # sin notas al pie
        o = obras[obras.fuente_excel == ruta.name]
        edu_a = int((o.sector_agrupado == "EDUCACION").sum())
        edu_b = int((base.sector_agrupado == "EDUCACION").sum())
        filas.append({"fecha_corte": o.corte.iloc[0], "obras_nuevo": len(o), "obras_leer_base_excel": len(base),
                      "educacion_nuevo": edu_a, "educacion_leer_base_excel": edu_b,
                      "costo_nuevo": round(o.costo_actualizado_soles.sum(), 2), "costo_leer_base_excel": round(base.costo.sum(), 2),
                      "codigos_duplicados": int(o.codigo_infobras.duplicated().sum()),
                      "ok": len(o) == len(base) and edu_a == edu_b and abs(o.costo_actualizado_soles.sum() - base.costo.sum()) < 1})
    return pd.DataFrame(filas)


# ---------------- A3: panel historico por obra ----------------
def construir_panel(obras):
    """Una fila por codigo_infobras: primer y ultimo corte, numero de cortes, si sigue en el ultimo corte, reingresos y avance por corte.

    Limites: el panel empieza en sep-2023 (los cortes de 2022 y feb-ago 2023 no tienen anexo con base), asi que 'primer_corte'
    de una obra presente desde sep-2023 es solo 'desde antes o igual a esa fecha' (primer_corte_censurado = True).
    reingresos = veces que la obra salio de la lista y volvio a entrar (cortes intermedios faltantes en bloques).
    """
    cortes = sorted(obras.corte.unique())
    posicion = {c: i for i, c in enumerate(cortes)}
    ultimo_global = cortes[-1]
    o = obras.assign(pos=obras.corte.map(posicion)).sort_values(["codigo_infobras", "pos"])
    g = o.groupby("codigo_infobras")
    panel = g.agg(primer_corte=("corte", "min"), ultimo_corte=("corte", "max"), n_cortes=("corte", "nunique"),
                  pos_min=("pos", "min"), pos_max=("pos", "max")).reset_index()
    panel["sigue_en_ultimo_corte"] = panel.ultimo_corte == ultimo_global
    panel["cortes_faltantes_intermedios"] = (panel.pos_max - panel.pos_min + 1) - panel.n_cortes
    saltos = o.assign(salto=g.pos.diff().fillna(1) > 1).groupby("codigo_infobras").salto.sum()
    panel["reingresos"] = panel.codigo_infobras.map(saltos).astype(int)
    panel["primer_corte_censurado"] = panel.primer_corte == cortes[0]
    panel = panel.drop(columns=["pos_min", "pos_max"])
    ultima = g.tail(1).set_index("codigo_infobras")
    for c in ("cui", "sector_agrupado", "nivel_gobierno", "causal_paralizacion", "cod_departamento", "departamento", "provincia", "distrito"):
        panel[f"{c}_ultimo"] = panel.codigo_infobras.map(ultima[c])
    primera = g.head(1).set_index("codigo_infobras")
    panel["avance_primer_corte"] = panel.codigo_infobras.map(primera.avance_fisico)
    panel["avance_ultimo_corte"] = panel.codigo_infobras.map(ultima.avance_fisico)
    ancho = o.pivot(index="codigo_infobras", columns="corte", values="avance_fisico")
    ancho.columns = [f"avance_{c}" for c in ancho.columns]
    panel = panel.merge(ancho.reset_index(), on="codigo_infobras", how="left")
    panel["fuente"] = "contraloria_obras_corte.csv (anexos Excel de la Contraloria, 13 cortes sep-2023 a jun-2026)"
    return panel


def validar_panel(panel, obras):
    """Comprobaciones del panel contra obras_corte (todas deben dar ok)."""
    ultimo = sorted(obras.corte.unique())[-1]
    filas = [("obras distintas", len(panel), obras.codigo_infobras.nunique()),
             ("suma de n_cortes = filas de obras_corte", int(panel.n_cortes.sum()), len(obras)),
             (f"obras que siguen en el ultimo corte ({ultimo})", int(panel.sigue_en_ultimo_corte.sum()), int((obras.corte == ultimo).sum())),
             ("codigos repetidos dentro de un mismo corte", int(obras.duplicated(["corte", "codigo_infobras"]).sum()), 0)]
    t = pd.DataFrame(filas, columns=["comprobacion", "panel", "obras_corte"])
    t["ok"] = t.panel == t.obras_corte
    return t


# ---------------- lectura de tablas de los PDF conservando las celdas vacias ----------------
def filas_posicionales(informe, meta):
    """Filas de una tabla del catalogo con las celdas vacias en su sitio.

    El CSV de data/interim compacta las filas (quita las celdas vacias), y entonces 'Por nucleo ejecutor 27 33134819 27 ...' no dice a que
    nivel de gobierno pertenece. Aqui se vuelve a abrir la pagina del PDF y se recupera la fila con '' donde la celda esta vacia; cada fila
    se empareja con la del CSV por su contenido. Devuelve (filas, n_sin_emparejar); las que no se emparejan quedan como en el CSV.
    """
    import pdfplumber
    import tablas_pdf
    ruta = config.RAW / "contraloria" / str(informe["anio"]) / informe["archivo"]
    csv_filas = [[c for c in fila[3:] if c != ""] for fila in pd.read_csv(
        informe["carpeta"] / meta.archivo_csv, dtype=str, keep_default_na=False, encoding="utf-8-sig").values.tolist()]
    candidatas = []
    with pdfplumber.open(ruta) as pdf:
        for n in range(int(meta["pagina"]), int(meta["pagina_fin"]) + 1):
            for t in pdf.pages[n - 1].find_tables():
                for fila in t.extract():
                    crudas = [tablas_pdf.convertir_celda(c) for c in fila if c is not None]
                    candidatas.append((crudas, [c for c in crudas if c != ""]))
    resultado, sin_emparejar, usadas = [], 0, set()
    for fila in csv_filas:
        i = next((k for k, (_, compacta) in enumerate(candidatas) if k not in usadas and compacta == fila), None)
        if i is None:
            resultado.append(fila)
            sin_emparejar += 1
        else:
            usadas.add(i)
            resultado.append(candidatas[i][0])
    return resultado, sin_emparejar


# ---------------- B7: serie corregida de Educacion ----------------
def corregir_educacion(cifras, educacion_departamento):
    """Agrega obras_educacion_corregida a las cifras oficiales (solo filas ambito='sector', categoria='EDUCACION').

    Donde hay anexo Excel del corte (13 cortes), el valor es la suma de contraloria_educacion_departamento (Excel); en los demas
    cortes (2022 y feb-ago 2023) es el valor del PDF, que no se puede contrastar. fuente_educacion_corregida dice cual se uso.
    En set-2023 y set-2025 el PDF trae la cifra mal (324 vs 283 y 73 vs 196).
    """
    cifras = cifras.drop(columns=[c for c in ("obras_educacion_corregida", "fuente_educacion_corregida") if c in cifras.columns]).copy()
    excel = educacion_departamento.groupby("fecha_corte").obras_educacion.sum()
    es_edu = (cifras.ambito == "sector") & (cifras.categoria == "EDUCACION")
    del_excel = cifras.fecha_corte.map(excel)
    cifras["obras_educacion_corregida"] = pd.Series(pd.NA, index=cifras.index, dtype="Int64")
    cifras["fuente_educacion_corregida"] = ""
    usa_excel = es_edu & del_excel.notna()
    cifras.loc[usa_excel, "obras_educacion_corregida"] = del_excel[usa_excel].round().astype("Int64")
    cifras.loc[usa_excel, "fuente_educacion_corregida"] = "anexo Excel (contraloria_educacion_departamento.csv)"
    solo_pdf = es_edu & del_excel.isna()
    cifras.loc[solo_pdf, "obras_educacion_corregida"] = cifras.loc[solo_pdf, "obras_paralizadas"].astype("Int64")
    cifras.loc[solo_pdf, "fuente_educacion_corregida"] = "informe PDF (sin anexo Excel para contrastar)"
    return cifras


def validar_educacion(cifras):
    """Serie corregida: debe coincidir con el PDF salvo en los cortes que el PDF trae mal (set-2023 y set-2025)."""
    e = cifras[(cifras.ambito == "sector") & (cifras.categoria == "EDUCACION")]
    t = e[["fecha_corte", "obras_paralizadas", "obras_educacion_corregida", "fuente_educacion_corregida"]].copy()
    t["difiere_del_pdf"] = t.obras_paralizadas != t.obras_educacion_corregida
    return t


# ---------------- B3: presupuesto (PIM) ----------------
def _num(celda):
    """Numero de una celda del PDF; '-' o el menos tipografico ('−') = 0; vacio = None."""
    texto = str(celda).strip().replace("−", "-")
    if texto == "":
        return None
    return tf.a_numero(texto)


def construir_pim(cifras):
    """PIM por departamento y para el total nacional de los 4 informes que lo traen (set-2025, dic-2025, mar-2026, jun-2026).

    Departamento: obras con PIM, sin PIM, % y total. Nacional: ademas costo actualizado con y sin PIM y el PIM en soles.
    Valida: 25 departamentos, con+sin = total por fila, suma de departamentos = fila Total, total = obras nacionales de cifras oficiales,
    nacional coincide con la suma de departamentos y costo total = costo nacional oficial.
    """
    filas, checks = [], []
    for informe in tf.informes_contraloria():
        deps = tf.tablas_de(informe, "pim_departamento")
        if not deps:
            continue
        corte, anio = informe["fecha_corte"], informe["anio"]
        meta, crudas = deps[0]
        anio_pim = int(re.search(r"PIM (\d{4})", meta.titulo).group(1))
        crudas = tf.recuperar_departamentos(informe, meta, crudas)
        base = {"anio": anio, "fecha_corte": corte, "anio_pim": anio_pim}
        prov = {"fuente_pdf": informe["archivo"], "pagina": int(meta.pagina), "tabla_n": int(meta.tabla_n)}
        deps_ok, total = [], None
        for f in crudas:
            n = [_num(c) for c in f[1:]]
            if len(n) != 5 or None in n:
                continue
            fila = {"obras_con_pim": n[0], "pct_obras_con_pim": n[1], "obras_sin_pim": n[2], "pct_obras_sin_pim": n[3], "obras_total": n[4]}
            if tf.es_total(f[0]):
                total = fila
                continue
            dep = tf.departamento_canonico(f[0])
            if dep:
                deps_ok.append({**base, "ambito": "departamento", "categoria": dep, "cod_departamento": config.DEPARTAMENTOS[dep], **fila, **prov})
        dep_df = pd.DataFrame(deps_ok)
        # nacional (tabla 'Asignacion de PIM' sin departamento)
        nacional = {}
        sectores = tf.tablas_de(informe, "pim_sector")
        if sectores:
            m2, filas2 = sectores[0]
            por_etiqueta = {re.sub(r"[^A-Z]", "", f[0].upper()): [_num(c) for c in f[1:]] for f in filas2}
            if {"SI", "NO", "TOTAL"} <= set(por_etiqueta):
                si, no, tot = por_etiqueta["SI"], por_etiqueta["NO"], por_etiqueta["TOTAL"]
                nacional = {"obras_con_pim": si[0], "pct_obras_con_pim": si[1], "obras_sin_pim": no[0], "pct_obras_sin_pim": no[1], "obras_total": tot[0],
                            "costo_con_pim_soles": si[2], "costo_sin_pim_soles": no[2], "costo_total_soles": tot[2], "pim_soles": si[4]}
                nac_prov = {"fuente_pdf": informe["archivo"], "pagina": int(m2.pagina), "tabla_n": int(m2.tabla_n)}
                filas.append({**base, "ambito": "nacional", "categoria": "NACIONAL", **nacional, **nac_prov})
        filas += deps_ok
        # ---- validaciones ----
        oficial = cifras[(cifras.fecha_corte == corte) & (cifras.ambito == "nacional")].iloc[0]
        agregar = lambda nombre, a, b, tol=0: checks.append({"fecha_corte": corte, "comprobacion": nombre, "valor_a": a, "valor_b": b,
                                                              "diferencia": None if a is None or b is None else float(a) - float(b), "tolerancia": tol,
                                                              "ok": a is not None and b is not None and abs(float(a) - float(b)) <= tol})
        agregar("departamentos presentes (25)", len(dep_df), 25)
        agregar("con + sin = total en cada departamento (filas que fallan)", int((dep_df.obras_con_pim + dep_df.obras_sin_pim != dep_df.obras_total).sum()), 0)
        if total:
            agregar("suma obras con PIM departamentos = fila Total", dep_df.obras_con_pim.sum(), total["obras_con_pim"])
            agregar("suma obras sin PIM departamentos = fila Total", dep_df.obras_sin_pim.sum(), total["obras_sin_pim"])
            agregar("fila Total de la tabla = obras nacionales oficiales", total["obras_total"], oficial.obras_paralizadas)
        if nacional:
            agregar("nacional: obras con PIM = suma de departamentos", nacional["obras_con_pim"], dep_df.obras_con_pim.sum())
            agregar("nacional: obras total = obras nacionales oficiales", nacional["obras_total"], oficial.obras_paralizadas)
            agregar("nacional: costo total = costo nacional oficial (S/)", nacional["costo_total_soles"], oficial.costo_actualizado_soles, 30)
            agregar("nacional: con + sin = total (costo, S/)", nacional["costo_con_pim_soles"] + nacional["costo_sin_pim_soles"], nacional["costo_total_soles"], 30)
    cols = ["anio", "fecha_corte", "anio_pim", "ambito", "categoria", "cod_departamento", "obras_con_pim", "pct_obras_con_pim", "obras_sin_pim",
            "pct_obras_sin_pim", "obras_total", "costo_con_pim_soles", "costo_sin_pim_soles", "costo_total_soles", "pim_soles",
            "fuente_pdf", "pagina", "tabla_n"]
    pim = pd.DataFrame(filas).reindex(columns=cols)
    return pim, pd.DataFrame(checks)


def validar_pim_con_excel(pim):
    """Contrasta obras con PIM (nacional y por departamento) con la columna TIENE PIM del anexo Excel de los mismos cortes."""
    filas = []
    for ruta in rutas_con_base():
        corte = leer_pdf.fechas_de_corte()[ruta.name]
        p = pim[(pim.fecha_corte == corte)]
        if p.empty:
            continue
        hoja, fila = tf.hoja_base(ruta)
        base = pd.read_excel(ruta, sheet_name=hoja, header=fila, dtype=str)
        base.columns = [tf.normalizar(c) for c in base.columns]
        col = next((c for c in base.columns if re.match(r"TIENE PIM", c)), None)
        if col is None:
            continue
        base = base[base["CODIGO INFOBRAS"].str.strip().str.fullmatch(r"\d+(\.0+)?", na=False)]
        con = base[col].map(lambda x: tf.normalizar(x) if pd.notna(x) else "") == "SI"
        base = base.assign(con_pim=con, dep=base[next(c for c in base.columns if c.startswith("DEPARTAMENTO"))].map(tf.departamento_canonico))
        nac = p[p.ambito == "nacional"]
        if len(nac):
            filas.append({"fecha_corte": corte, "ambito": "nacional", "categoria": "NACIONAL", "obras_con_pim_pdf": nac.obras_con_pim.iloc[0],
                          "obras_con_pim_excel": int(con.sum())})
        por_dep = base.groupby("dep").con_pim.sum()
        for _, f in p[p.ambito == "departamento"].iterrows():
            filas.append({"fecha_corte": corte, "ambito": "departamento", "categoria": f.categoria, "obras_con_pim_pdf": f.obras_con_pim,
                          "obras_con_pim_excel": int(por_dep.get(f.categoria, 0))})
    t = pd.DataFrame(filas)
    if len(t):
        t["diferencia"] = t.obras_con_pim_excel - t.obras_con_pim_pdf
    return t


# ---------------- B6: principales obras por departamento (anexos Excel) ----------------
PATRONES_PRINCIPALES = {
    "departamento": r"DEPARTAMENTO$", "codigo_infobras": r"CODIGO INFOBRAS", "cui": r"CUI$", "descripcion_obra": r"DESCRIPCION OBRA",
    "entidad": r"ENTIDAD$", "costo_actualizado_soles": r"COSTO ACTUALIZADO", "nivel_gobierno": r"NIVEL DE GOBIERNO",
    "causal_paralizacion": r"CAUSAL", "modalidad_ejecucion": r"MODALIDAD DE EJECUCION"}
COLUMNAS_PRINCIPALES = ["anio", "fecha_corte", "cod_departamento", "departamento", "orden_en_hoja", "cui", "codigo_infobras", "descripcion_obra",
                        "entidad", "nivel_gobierno", "modalidad_ejecucion", "causal_codigo", "causal_paralizacion", "costo_actualizado_soles",
                        "codigo_infobras_de_base", "es_lista_completa", "fuente_excel", "hoja"]
UMBRAL_LISTA_COMPLETA = 600   # una hoja de 'principales obras' con mas filas que esto es la lista completa (pasa en mar-2024)


def hoja_principales(ruta):
    """(hoja, fila del encabezado) de la lista de principales obras de un anexo, o None. La hoja cambia de nombre
    ('Principales obras por Dpto', 'Princ_Obras', 'ANEXO N°01', 'Anexo 01', ...); se reconoce por sus columnas CUI + DESCRIPCION OBRA + ENTIDAD."""
    import openpyxl
    libro = openpyxl.load_workbook(ruta, read_only=True, data_only=True)
    for hoja in libro.worksheets:
        if not re.search(r"princ|anexo", hoja.title, re.I) or re.search(r"cuadros", hoja.title, re.I):
            continue
        for i, fila in enumerate(hoja.iter_rows(min_row=1, max_row=8, values_only=True)):
            columnas = [tf.normalizar(c) for c in fila if c is not None]
            if "CUI" in columnas and "DESCRIPCION OBRA" in columnas and "ENTIDAD" in columnas:
                return hoja.title, i
    return None


def leer_principales_obras(ruta):
    """Principales obras por departamento de un anexo Excel. None si el anexo no tiene esa lista."""
    ubicada = hoja_principales(ruta)
    if ubicada is None:
        return None
    hoja, fila = ubicada
    base = pd.read_excel(ruta, sheet_name=hoja, header=fila, dtype=str)
    base.columns = [tf.normalizar(c) for c in base.columns]
    salida = pd.DataFrame(index=base.index)
    for campo, patron in PATRONES_PRINCIPALES.items():
        c = next((c for c in base.columns if re.match(patron, c)), None)
        salida[campo] = base[c] if c else pd.NA
    salida["cui"] = _texto_codigo(salida.cui)
    salida = salida[salida.cui.str.fullmatch(r"\d+", na=False)].copy()   # sin filas vacias ni notas al pie
    salida["codigo_infobras"] = _texto_codigo(salida.codigo_infobras)
    salida["costo_actualizado_soles"] = pd.to_numeric(salida.costo_actualizado_soles, errors="coerce")
    for c in ("departamento", "entidad", "nivel_gobierno", "modalidad_ejecucion", "causal_paralizacion"):
        salida[c] = salida[c].map(lambda x: tf.normalizar(x) if pd.notna(x) else pd.NA)
    salida["departamento"] = salida.departamento.map(tf.departamento_canonico)
    salida["nivel_gobierno"] = salida.nivel_gobierno.str.replace(r"^G\. ", "G. ", regex=True)
    salida["modalidad_ejecucion"] = salida.modalidad_ejecucion.replace(ALIAS_MODALIDAD)
    partes = salida.causal_paralizacion.str.extract(r"^(\d+)\s+(.*)$")
    salida["causal_codigo"] = partes[0].astype("string")
    salida["causal_paralizacion"] = partes[1].where(partes[1].notna(), salida.causal_paralizacion)
    salida["descripcion_obra"] = salida.descripcion_obra.str.replace(r"\s+", " ", regex=True).str.strip()
    salida["cod_departamento"] = salida.departamento.map(config.DEPARTAMENTOS)
    corte = leer_pdf.fechas_de_corte()[ruta.name]
    salida["fecha_corte"], salida["anio"] = corte, int(corte[:4])
    salida["orden_en_hoja"] = range(1, len(salida) + 1)
    salida["es_lista_completa"] = len(salida) > UMBRAL_LISTA_COMPLETA
    salida["codigo_infobras_de_base"] = False
    salida["fuente_excel"], salida["hoja"] = ruta.name, hoja
    return salida.reindex(columns=COLUMNAS_PRINCIPALES).reset_index(drop=True)


def construir_principales_obras(obras=None):
    """Apila las listas de principales obras de todos los anexos que la traen (un anexo por corte).

    Los anexos de 2025 en adelante no traen CODIGO INFOBRAS (solo CUI): si se pasa `obras` (contraloria_obras_corte), el codigo se completa
    desde la base obra por obra del mismo corte y la fila queda marcada con codigo_infobras_de_base = True.
    """
    cortes = leer_pdf.fechas_de_corte()
    por_corte = {}
    for ruta in sorted(config.RAW.glob("contraloria/*/*.xlsx")):
        if "anexo_03" in ruta.name or ruta.name not in cortes:
            continue
        tabla = leer_principales_obras(ruta)
        if tabla is not None and len(tabla):
            por_corte.setdefault(cortes[ruta.name], tabla)
    principales = pd.concat([por_corte[c] for c in sorted(por_corte)], ignore_index=True)
    if obras is not None:
        base = obras.dropna(subset=["cui"]).drop_duplicates(["corte", "cui"]).set_index(["corte", "cui"]).codigo_infobras
        llave = pd.MultiIndex.from_arrays([principales.fecha_corte, principales.cui])
        encontrado = pd.Series(base.reindex(llave).to_numpy(), index=principales.index, dtype="string")
        falta = principales.codigo_infobras.isna() & encontrado.notna()
        principales.loc[falta, "codigo_infobras"] = encontrado[falta]
        principales["codigo_infobras_de_base"] = falta
    return principales


def validar_principales_obras(principales, obras):
    """Por corte: cuantas obras hay, cuantas CUI estan en la base obra por obra del mismo corte, y en cuantas coincide el costo (<= 0,5 %)."""
    filas = []
    for corte, g in principales.groupby("fecha_corte"):
        o = obras[obras.corte == corte].dropna(subset=["cui"]).drop_duplicates("cui").set_index("cui")
        if o.empty:
            filas.append({"fecha_corte": corte, "obras": len(g), "departamentos": g.departamento.nunique(), "cui_en_base": None,
                          "costo_coincide": None, "nota": "el corte no tiene base obra por obra para contrastar"})
            continue
        union = g.join(o[["costo_actualizado_soles"]].rename(columns={"costo_actualizado_soles": "costo_base"}), on="cui")
        en_base = union.costo_base.notna() | union.cui.isin(o.index)
        cercano = ((union.costo_actualizado_soles - union.costo_base).abs() <= 0.005 * union.costo_base.abs()) & en_base
        filas.append({"fecha_corte": corte, "obras": len(g), "departamentos": g.departamento.nunique(), "cui_en_base": int(en_base.sum()),
                      "costo_coincide": int(cercano.sum()), "nota": ""})
    return pd.DataFrame(filas)


# ---------------- B4: modalidad de ejecucion y evento INFOBRAS (tablas nivel de gobierno x categoria) ----------------
NIVELES = ("NACIONAL", "REGIONAL", "LOCAL")
ALIAS_CATEGORIA = {"CONTRATA": "POR CONTRATA", "NUCLEOS EJECUTORES": "POR NUCLEO EJECUTOR", "APP / CONCESIONES": "ASOCIACION PUBLICA PRIVADA APP",
                   "ASOCIACION PUBLICA PRIVADA - APP": "ASOCIACION PUBLICA PRIVADA APP", "ASOCIACIONES PUBLICO PRIVADAS": "ASOCIACION PUBLICA PRIVADA APP"}
CELDAS_POR_TABLA = {"modalidad_ejecucion": 10, "evento_infobras": 9}   # 6 de niveles (N y costo x 3) + cola (N, %, costo, %) o (N, costo, %)
COLUMNAS_NIVEL = ["anio", "fecha_corte", "tabla", "categoria", "nivel_gobierno", "obras_paralizadas", "costo_actualizado_soles", "pct_obras",
                  "pct_costo", "orden_niveles", "fuente_pdf", "pagina", "tabla_n"]


def _es_numero(celda):
    return bool(re.fullmatch(r"[-−]?\d[\d ,.]*%?|[-−]", str(celda).strip()))


def _categoria(etiqueta):
    """'Reconstruccion con Cambios8' -> 'RECONSTRUCCION CON CAMBIOS' (se quita la nota al pie pegada a la palabra)."""
    texto = tf.normalizar(re.sub(r"(?<=[A-Za-zÁÉÍÓÚáéíóúñÑ])\d+$", "", str(etiqueta).strip()))
    return ALIAS_CATEGORIA.get(texto, texto)


def _ensamblar_filas(filas_crudas, esperadas):
    """Filas crudas (con '' en las celdas vacias) -> [(etiqueta, [celdas])] con `esperadas` celdas cada una.

    Resuelve lo que el PDF hace con las tablas: la etiqueta puede venir despues de celdas vacias (['', 'Total', '', '356', ...]); una fila
    partida en dos lineas (una fila corta, con o sin etiqueta, que completa los huecos de la anterior); y filas con mas celdas vacias de las
    esperadas (columnas desplazadas), de las que se quitan las vacias.
    """
    filas = []
    for r in filas_crudas:
        i_etiqueta = next((i for i, c in enumerate(r) if c != "" and not _es_numero(c)), None)
        etiqueta = r[i_etiqueta] if i_etiqueta is not None else ""
        resto = list(r[i_etiqueta + 1:]) if i_etiqueta is not None else (list(r[1:]) if r and r[0] == "" else list(r))
        n_numeros = sum(1 for c in resto if c != "")
        previa = filas[-1] if filas else None
        if n_numeros <= 3 and previa is not None and (previa[0] == "" or "" in previa[1] or len(previa[1]) < esperadas):
            if etiqueta and previa[0] == "":
                previa[0] = etiqueta
            valores = [c for c in resto if c != ""]
            for k, c in enumerate(previa[1]):
                if c == "" and valores:
                    previa[1][k] = valores.pop(0)
        elif n_numeros > 3:
            filas.append([etiqueta, resto])
    salida = []
    for etiqueta, celdas in filas:
        if len(celdas) > esperadas:
            celdas = [c for c in celdas if c != ""]
        if len(celdas) == esperadas + 1:
            celdas = _unir_cifra_partida(celdas, esperadas)
        if len(celdas) == esperadas:
            salida.append((etiqueta, celdas))
    return salida


def _unir_cifra_partida(celdas, esperadas):
    """A veces pdfplumber parte una cifra en dos celdas ('31' y '0' por '310'; '1' y '0,646,852,188'). Si sobra una celda se prueba unir
    cada par contiguo y se deja la union con la que las obras de los tres niveles suman el total de la fila; si ninguna cuadra, no se toca."""
    for i in range(len(celdas) - 1):
        candidata = celdas[:i] + [celdas[i] + celdas[i + 1]] + celdas[i + 2:]
        v = [_num(c) for c in candidata]
        if None not in v and v[0] + v[2] + v[4] == v[6]:
            return candidata
    return celdas


def _registros_nivel(filas, esperadas):
    """[(etiqueta, celdas)] -> lista de dicts: categoria, pares (obras, costo) por columna de nivel, y el total (obras, %, costo, %)."""
    registros = []
    for etiqueta, celdas in filas:
        v = [_num(c) for c in celdas]
        pares = [(v[0], v[1]), (v[2], v[3]), (v[4], v[5])]
        pares = [(0 if p[0] is None and p[1] is None else p[0], p[1]) for p in pares]
        cola = v[6:]
        if esperadas == 10:
            total = {"obras": cola[0], "pct_obras": cola[1], "costo": cola[2], "pct_costo": cola[3]}
        else:
            total = {"obras": cola[0], "pct_obras": None, "costo": cola[1], "pct_costo": cola[2]}
        registros.append({"etiqueta": etiqueta, "pares": pares, "total": total})
    return registros


def _niveles_oficiales(distribuciones, corte):
    d = distribuciones[(distribuciones.fecha_corte == corte) & (distribuciones.dimension == "nivel_gobierno")]
    salida = {}
    for _, f in d.iterrows():
        for nivel in NIVELES:
            if str(f.categoria).endswith(nivel):
                salida[nivel] = int(f.obras_paralizadas)
    return salida


def _orden_de_niveles(fila_total, oficiales, referencia=None, filas_ref_buscar=()):
    """Orden real de las 3 columnas de nivel. El rotulo del PDF no es confiable (en el evento de jun-2026 el PDF dice Nacional-Regional-Local
    pero las cifras estan en Local-Nacional-Regional), asi que se decide por los totales: se busca la permutacion de (NACIONAL, REGIONAL, LOCAL)
    cuyas obras coinciden con las del cuadro 'nivel de gobierno' del mismo informe. Sin coincidencia exacta se prueba contra una tabla de referencia
    ya resuelta del mismo informe (pares obras/costo) y, si no, se deja el orden Nacional-Regional-Local marcado como no verificado.
    Devuelve (orden, verificado)."""
    import itertools
    ns = [p[0] for p in fila_total["pares"]]
    if len(oficiales) == 3:
        for perm in itertools.permutations(NIVELES):
            if all(ns[i] == oficiales[perm[i]] for i in range(3)):
                return list(perm), True
    if referencia:
        conteo = {}
        for nivel, par in referencia:
            conteo.setdefault(par, set()).add(nivel)
        pares_ref = {par: next(iter(n)) for par, n in conteo.items() if len(n) == 1}
        for fila in filas_ref_buscar:
            encontrados = [pares_ref.get(tuple(p)) for p in fila["pares"]]
            if None not in encontrados and len(set(encontrados)) == 3:
                return encontrados, True
    return list(NIVELES), False


def _validar_nivel(registros, orden, nacional_obras):
    """Comprobaciones de una tabla: suma de filas = fila Total por columna (obras y costo) y total de obras = nacional (si se conoce)."""
    es_t = [tf.es_total(r["etiqueta"]) for r in registros]
    if not any(es_t):
        return [("tiene fila Total", 0, 1, 0)]
    total = registros[es_t.index(True)]
    cuerpo = [r for r, t in zip(registros, es_t) if not t]
    checks = []
    for i, nivel in enumerate(orden):
        checks.append((f"suma obras {nivel} = Total", sum((r["pares"][i][0] or 0) for r in cuerpo), total["pares"][i][0] or 0, 0))
        checks.append((f"suma costo {nivel} = Total (S/)", sum((r["pares"][i][1] or 0) for r in cuerpo), total["pares"][i][1] or 0, 10 * len(cuerpo)))
    checks.append(("suma obras total de filas = Total", sum((r["total"]["obras"] or 0) for r in cuerpo), total["total"]["obras"] or 0, 0))
    checks.append(("obras por nivel suman el total de la fila (filas que fallan)",
                   sum(sum((p[0] or 0) for p in r["pares"]) != (r["total"]["obras"] or 0) for r in registros), 0, 0))
    if nacional_obras is not None:
        checks.append(("fila Total = obras nacionales oficiales", total["total"]["obras"], nacional_obras, 0))
    return checks


def construir_modalidad_evento(cifras, distribuciones):
    """Tablas de modalidad de ejecucion (dos por informe) y evento INFOBRAS, en formato largo (una fila por categoria y nivel de gobierno).

    Devuelve (modalidad, evento, validacion). Una tabla solo se guarda si todas sus comprobaciones pasan; las que fallan quedan en la
    validacion con el motivo (no se corrigen a mano).
    """
    modalidad, evento, validacion = [], [], []
    for informe in tf.informes_contraloria():
        corte, anio = informe["fecha_corte"], informe["anio"]
        oficiales = _niveles_oficiales(distribuciones, corte)
        nacional = cifras[(cifras.fecha_corte == corte) & (cifras.ambito == "nacional")].obras_paralizadas.iloc[0]
        referencia = None
        trabajos = [("modalidad_ejecucion", "por_modalidad"), ("modalidad_ejecucion", "administracion_directa_y_contrata"), ("evento_infobras", "por_evento")]
        for tipo, nombre in trabajos:
            tablas = tf.tablas_de(informe, tipo)
            if tipo == "modalidad_ejecucion":
                tablas = [t for t in tablas if (re.search(r"seg[uú]n", t[0].titulo, re.I) is not None) == (nombre != "por_modalidad")]
            if not tablas:
                validacion.append({"fecha_corte": corte, "tabla": nombre, "comprobacion": "tabla encontrada en el catalogo", "valor_a": 0, "valor_b": 1,
                                   "diferencia": -1, "tolerancia": 0, "ok": False})
                continue
            meta, _ = tablas[0]
            crudas, _sin = filas_posicionales(informe, meta)
            esperadas = CELDAS_POR_TABLA[tipo]
            registros = _registros_nivel(_ensamblar_filas(crudas, esperadas), esperadas)
            if not registros:
                validacion.append({"fecha_corte": corte, "tabla": nombre, "comprobacion": "filas legibles", "valor_a": 0, "valor_b": len(crudas),
                                   "diferencia": None, "tolerancia": 0, "ok": False})
                continue
            fila_total = next((r for r in registros if tf.es_total(r["etiqueta"])), None)
            if fila_total is None:
                validacion.append({"fecha_corte": corte, "tabla": nombre, "comprobacion": "tiene fila Total", "valor_a": 0, "valor_b": 1,
                                   "diferencia": -1, "tolerancia": 0, "ok": False})
                continue
            orden, verificado = _orden_de_niveles(fila_total, oficiales if nombre != "administracion_directa_y_contrata" else {}, referencia, registros)
            checks = _validar_nivel(registros, orden, nacional if nombre != "administracion_directa_y_contrata" else None)
            ok_tabla = all(abs(a - b) <= tol for _, a, b, tol in checks)
            for c, a, b, tol in checks:
                validacion.append({"fecha_corte": corte, "tabla": nombre, "comprobacion": c, "valor_a": a, "valor_b": b, "diferencia": a - b,
                                   "tolerancia": tol, "ok": abs(a - b) <= tol})
            validacion.append({"fecha_corte": corte, "tabla": nombre, "comprobacion": "orden de los niveles verificado con los totales del informe",
                               "valor_a": int(verificado), "valor_b": 1, "diferencia": int(verificado) - 1, "tolerancia": 0, "ok": verificado})
            if nombre == "por_modalidad" and ok_tabla and verificado:
                referencia = [(nivel, tuple(par)) for r in registros for nivel, par in zip(orden, r["pares"]) if par[0]]
            if not ok_tabla:
                continue
            base = {"anio": anio, "fecha_corte": corte, "tabla": nombre, "orden_niveles": "verificado" if verificado else "no verificado",
                    "fuente_pdf": informe["archivo"], "pagina": int(meta.pagina), "tabla_n": int(meta.tabla_n)}
            destino = evento if tipo == "evento_infobras" else modalidad
            for r in registros:
                if tf.es_total(r["etiqueta"]):
                    continue
                categoria = _categoria(r["etiqueta"])
                if destino is modalidad:
                    categoria = ALIAS_MODALIDAD.get(categoria, categoria)
                for nivel, (n, costo) in zip(orden, r["pares"]):
                    destino.append({**base, "categoria": categoria, "nivel_gobierno": nivel, "obras_paralizadas": n, "costo_actualizado_soles": costo})
                destino.append({**base, "categoria": categoria, "nivel_gobierno": "TOTAL", "obras_paralizadas": r["total"]["obras"],
                                "costo_actualizado_soles": r["total"]["costo"], "pct_obras": r["total"]["pct_obras"], "pct_costo": r["total"]["pct_costo"]})
    return (pd.DataFrame(modalidad).reindex(columns=COLUMNAS_NIVEL), pd.DataFrame(evento).reindex(columns=COLUMNAS_NIVEL), pd.DataFrame(validacion))


def validar_modalidad_evento_con_excel(modalidad, evento, obras):
    """Contrasta las obras por categoria y nivel de gobierno de cada tabla del PDF con la base obra por obra del mismo corte (13 cortes)."""
    filas = []
    for nombre, tabla, columna in (("por_modalidad", modalidad, "modalidad_ejecucion"), ("por_evento", evento, "evento")):
        for corte, g in tabla[tabla.tabla == nombre].groupby("fecha_corte"):
            o = obras[obras.corte == corte]
            if o.empty:
                continue
            o = o.assign(nivel=o.nivel_gobierno.str.replace("G. ", "", regex=False))
            excel = o.groupby([columna, "nivel"]).size()
            excel_total = o.groupby(columna).size()
            for _, f in g.iterrows():
                v = excel_total.get(f.categoria, 0) if f.nivel_gobierno == "TOTAL" else excel.get((f.categoria, f.nivel_gobierno), 0)
                filas.append({"fecha_corte": corte, "tabla": nombre, "categoria": f.categoria, "nivel_gobierno": f.nivel_gobierno,
                              "obras_pdf": f.obras_paralizadas, "obras_excel": int(v),
                              "diferencia": pd.NA if pd.isna(f.obras_paralizadas) else int(v) - int(f.obras_paralizadas)})
    t = pd.DataFrame(filas)
    return t


def validar_subset_modalidad(modalidad):
    """La tabla 'administracion directa y contrata' es un subconjunto de la de modalidades: sus obras por categoria y nivel deben ser iguales a las de la
    tabla principal del mismo informe. Si no lo son (p. ej. jun-2026, donde el PDF intercambia los rotulos Administracion directa y Por contrata),
    la fila queda marcada con coincide = False."""
    principal = modalidad[modalidad.tabla == "por_modalidad"].set_index(["fecha_corte", "categoria", "nivel_gobierno"]).obras_paralizadas
    sub = modalidad[modalidad.tabla == "administracion_directa_y_contrata"]
    t = sub[["fecha_corte", "categoria", "nivel_gobierno", "obras_paralizadas"]].rename(columns={"obras_paralizadas": "obras_subtabla"}).copy()
    t["obras_tabla_principal"] = [principal.get((a, b, c)) for a, b, c in zip(t.fecha_corte, t.categoria, t.nivel_gobierno)]
    t["coincide"] = t.obras_subtabla == t.obras_tabla_principal
    return t


# ---------------- B4: servicios de control (texto de las paginas del PDF) ----------------
COLUMNAS_SC_TOTAL = ["anio", "fecha_corte", "tipo_servicio", "cantidad", "pct", "fuente_pdf", "pagina", "tabla_n"]
COLUMNAS_SC_NIVEL = ["anio", "fecha_corte", "tipo_servicio", "nivel_gobierno", "cantidad", "pct", "orden_niveles", "fuente_pdf", "pagina", "tabla_n"]
COLUMNAS_SC_DEP = ["anio", "fecha_corte", "cod_departamento", "departamento", "control_previo", "control_simultaneo", "control_posterior",
                   "total_servicios", "fuente_pdf", "pagina", "tabla_n"]
TIPOS_SC = ("PREVIO", "SIMULTANEO", "POSTERIOR")


def _texto_paginas(informe, meta):
    return "\n".join((informe["carpeta"] / f"texto_p{p:02d}.txt").read_text(encoding="utf-8")
                      for p in range(int(meta.pagina), int(meta.pagina_fin) + 1))


def _filas_de_texto(texto, titulo, minimo_cifras):
    """Lineas 'Control previo 24 0.6% 31 0.8% ...' entre el titulo y la fila Total: [(tipo o 'TOTAL', [cifras])]."""
    lineas = texto.splitlines()
    inicio = next((i for i, l in enumerate(lineas) if re.search(titulo, l, re.I)), None)
    if inicio is None:
        return []
    filas = []
    for linea in lineas[inicio + 1:]:
        m = re.match(r"^(Control (?:previo|simult[aá]neo|posterior)|Total(?: general)?)\s+([-−\d].*)$", linea.strip(), re.I)
        if not m:
            continue
        crudos = m.group(2).split()
        tokens = [t.rstrip("%").replace("−", "-") for t in crudos]
        if minimo_cifras == 6 and len(tokens) == 7:   # falta una cifra: la cantidad vacia de un nivel (se lee como 0)
            if tokens.count("-") == 1:                 # un solo guion vale por la pareja (cantidad, %) vacia
                i = tokens.index("-")
                tokens[i:i + 1] = ["-", "-"]
            elif crudos[0].endswith("%"):              # '0.0% 18 1.3% ...': la fila empieza por el % de la cantidad vacia
                tokens.insert(0, "0")
        cifras = [tf.a_numero(t) for t in tokens]
        if None in cifras or len(cifras) < minimo_cifras:
            continue
        etiqueta = "TOTAL" if m.group(1).lower().startswith("total") else tf.normalizar(m.group(1)).replace("CONTROL ", "")
        filas.append((etiqueta, cifras))
        if etiqueta == "TOTAL":
            break
    return filas


def _orden_niveles_texto(informe, meta, totales):
    """Orden de las columnas de nivel de la tabla 'servicios de control por nivel de gobierno': el del encabezado, contrastado con la narracion
    del informe (p. ej. '1 977 (49.3%) corresponden al nivel de Gobierno Local'). Devuelve (orden, verificado)."""
    pagina = (informe["carpeta"] / f"texto_p{int(meta.pagina):02d}.txt").read_text(encoding="utf-8")
    encabezado = " ".join(pagina.split("Tabla 1")[1].split("Control Previo")[0].split("Control previo")[0].split()) if re.search(r"Tabla 1", pagina) else pagina
    orden = [tf.normalizar(m.group(1)) for m in re.finditer(r"(Nacional|Regional|Local)", encabezado)]
    orden = [o for i, o in enumerate(orden) if o not in orden[:i]]
    if sorted(orden) != sorted(NIVELES):
        orden = list(NIVELES)
    texto = re.sub(r"\s+", " ", (informe["carpeta"] / "texto_completo.txt").read_text(encoding="utf-8"))
    por_narracion = {}
    for n in totales:
        miles = f"{n // 1000}\\s?{n % 1000:03d}" if n >= 1000 else str(n)
        m = re.search(rf"(?<![\d.,]){miles}\b.{{0,70}}?Gobierno (Local|Regional|Nacional)", texto, re.I)
        if m:
            por_narracion[n] = tf.normalizar(m.group(1))
    por_encabezado = dict(zip(totales, orden))
    if len(por_narracion) == 3 and len(set(por_narracion.values())) == 3:
        return [por_narracion[n] for n in totales], por_narracion == por_encabezado
    return [por_encabezado[n] for n in totales], False


def _filas_departamento_pdf(informe, meta, paginas_extra=2):
    """Filas por departamento de la tabla de servicios de control, leidas del PDF con las celdas vacias en su sitio.

    Hay informes cuya tabla sigue en la pagina siguiente sin que el catalogo la una (mar-2023, set-2024, mar-2026 traian solo 6, 18 y 19 filas),
    asi que se recorren la pagina de la tabla y las dos siguientes y se toma la primera fila de cada departamento."""
    import pdfplumber
    import tablas_pdf
    ruta = config.RAW / "contraloria" / str(informe["anio"]) / informe["archivo"]
    vistas, filas = set(), []
    with pdfplumber.open(ruta) as pdf:
        for n in range(int(meta.pagina), min(int(meta.pagina) + paginas_extra, len(pdf.pages)) + 1):
            for t in pdf.pages[n - 1].find_tables():
                for fila in t.extract():
                    celdas = [tablas_pdf.convertir_celda(c) for c in fila if c is not None]
                    dep = tf.departamento_canonico(celdas[0]) if celdas else None
                    if dep and dep not in vistas and len(celdas) >= 4:
                        vistas.add(dep)
                        filas.append(celdas)
                    elif celdas and tf.es_total(celdas[0]) and "TOTAL" not in vistas and len(vistas) >= 20:
                        vistas.add("TOTAL")
                        filas.append(celdas)
    return filas


def construir_servicios_control(cifras):
    """Tres tablas: total, por nivel de gobierno y por departamento. Devuelve (total, nivel, departamento, validacion).

    total y nivel salen del texto de la pagina (formato estable en los 21 informes); departamento sale de la tabla del PDF con sus celdas vacias
    en su sitio (una celda vacia = ese tipo de servicio no se hizo en el departamento). 2022 solo trae total y nivel (por departamento es un mapa).
    """
    total, nivel, dep, validacion = [], [], [], []
    check = lambda corte, nombre, a, b, tol=0: validacion.append({"fecha_corte": corte, "tabla": nombre[0], "comprobacion": nombre[1], "valor_a": a, "valor_b": b,
                                                                  "diferencia": a - b, "tolerancia": tol, "ok": abs(a - b) <= tol})
    for informe in tf.informes_contraloria():
        corte, anio = informe["fecha_corte"], informe["anio"]
        base = {"anio": anio, "fecha_corte": corte}
        for meta, _ in tf.tablas_de(informe, "servicios_control_total")[:1]:
            prov = {"fuente_pdf": informe["archivo"], "pagina": int(meta.pagina), "tabla_n": int(meta.tabla_n)}
            filas = _filas_de_texto(_texto_paginas(informe, meta), r"total de servicios de control efectuados", 2)
            cuerpo = [(t, c) for t, c in filas if t != "TOTAL"]
            if cuerpo and any(t == "TOTAL" for t, _ in filas):
                check(corte, ("total", "suma de los tres tipos = Total"), sum(c[0] for _, c in cuerpo), next(c[0] for t, c in filas if t == "TOTAL"))
                for t, c in cuerpo:
                    total.append({**base, "tipo_servicio": t, "cantidad": c[0], "pct": c[1], **prov})
        for meta, _ in tf.tablas_de(informe, "servicios_control_nivel_gobierno")[:1]:
            prov = {"fuente_pdf": informe["archivo"], "pagina": int(meta.pagina), "tabla_n": int(meta.tabla_n)}
            filas = _filas_de_texto(_texto_paginas(informe, meta), r"servicios de control por nivel de gobierno", 6)
            cuerpo = [(t, c) for t, c in filas if t != "TOTAL"]
            fila_total = next((c for t, c in filas if t == "TOTAL"), None)
            if not cuerpo or fila_total is None or len(fila_total) < 8:
                check(corte, ("nivel", "tabla legible"), 0, 1)
                continue
            totales_nivel = [int(fila_total[0]), int(fila_total[2]), int(fila_total[4])]
            orden, verificado = _orden_niveles_texto(informe, meta, totales_nivel)
            for t, c in cuerpo:
                check(corte, ("nivel", f"{t}: niveles suman el total de la fila"), c[0] + c[2] + c[4], c[6])
                for i, n in enumerate(orden):
                    nivel.append({**base, "tipo_servicio": t, "nivel_gobierno": n, "cantidad": c[2 * i], "pct": c[2 * i + 1],
                                  "orden_niveles": "verificado con la narracion" if verificado else "segun el encabezado del PDF", **prov})
                nivel.append({**base, "tipo_servicio": t, "nivel_gobierno": "TOTAL", "cantidad": c[6], "pct": c[7],
                              "orden_niveles": "verificado con la narracion" if verificado else "segun el encabezado del PDF", **prov})
            for i, n in enumerate(orden):
                check(corte, ("nivel", f"suma de tipos {n} = Total"), sum(c[2 * i] for _, c in cuerpo), fila_total[2 * i])
            ref = [r for r in total if r["fecha_corte"] == corte]
            if ref:
                check(corte, ("nivel", "total de servicios = tabla total"), fila_total[6], sum(r["cantidad"] for r in ref))
        tablas_dep = tf.tablas_de(informe, "servicios_control_departamento")
        if tablas_dep:   # la tabla puede venir partida en varias tablas del catalogo (una por pagina)
            meta = tablas_dep[0][0]
            prov = {"fuente_pdf": informe["archivo"], "pagina": int(meta.pagina), "tabla_n": int(meta.tabla_n)}
            crudas = _filas_departamento_pdf(informe, meta)
            filas = []
            for r in crudas:
                if not r or not r[0] or _es_numero(r[0]):
                    continue
                celdas = list(r[1:])
                if len(celdas) != 4:
                    celdas = (celdas + [""] * 4)[:4] if len(celdas) < 4 else [c for c in celdas if c != ""][:4] if len([c for c in celdas if c != ""]) <= 4 else celdas[:4]
                filas.append((r[0], [(_num(c) or 0) for c in celdas]))
            registros = [(f, v) for f, v in filas if tf.departamento_canonico(f)]
            total_fila = next((v for f, v in filas if tf.es_total(f)), None)
            for f, v in registros:
                d = tf.departamento_canonico(f)
                dep.append({**base, "cod_departamento": config.DEPARTAMENTOS[d], "departamento": d, "control_previo": v[0], "control_simultaneo": v[1],
                            "control_posterior": v[2], "total_servicios": v[3], **prov})
            check(corte, ("departamento", "departamentos presentes (25)"), len(registros), 25)
            check(corte, ("departamento", "previo + simultaneo + posterior = total (filas que fallan)"), sum(sum(v[:3]) != v[3] for _, v in registros), 0)
            if total_fila:
                for j, nombre in enumerate(("previo", "simultaneo", "posterior", "total")):
                    check(corte, ("departamento", f"suma {nombre} departamentos = Total"), sum(v[j] for _, v in registros), total_fila[j])
            ref = [r for r in total if r["fecha_corte"] == corte]
            if ref:
                check(corte, ("departamento", "total de servicios = tabla total"), sum(v[3] for _, v in registros), sum(r["cantidad"] for r in ref))
    return (pd.DataFrame(total).reindex(columns=COLUMNAS_SC_TOTAL), pd.DataFrame(nivel).reindex(columns=COLUMNAS_SC_NIVEL),
            pd.DataFrame(dep).reindex(columns=COLUMNAS_SC_DEP), pd.DataFrame(validacion))


# ---------------- ejecucion de todas las tareas de los anexos Excel ----------------
VALIDACION = config.DOCS / "validacion_anexos_excel.csv"
VALIDACION_B4_EXCEL = config.DOCS / "validacion_b4_excel.csv"
ENTEROS_CIFRAS = ["obras_paralizadas", "obras_g_nacional", "obras_g_regional", "obras_g_local", "pagina", "tabla_n", "obras_educacion_corregida"]


def _checks(tarea, tabla):
    """Pasa una tabla de comprobaciones al formato comun de docs/validacion_anexos_excel.csv."""
    if tabla is None or tabla.empty:
        return pd.DataFrame()
    t = tabla.copy()
    t.insert(0, "tarea", tarea)
    for c in ("fecha_corte", "tabla"):
        if c not in t:
            t[c] = ""
    for c in ("valor_a", "valor_b", "diferencia", "tolerancia"):
        if c not in t:
            t[c] = pd.NA
    return t[["tarea", "fecha_corte", "tabla", "comprobacion", "valor_a", "valor_b", "diferencia", "tolerancia", "ok"]]


def ejecutar_anexos_excel():
    """Corre A2, A3, B7, B3, B4 y B6 y guarda sus tablas en data/processed y sus comprobaciones en docs/validacion_anexos_excel.csv.

    Se ejecuta en la Fase 3 del proyecto PDF (despues de tablas_finales.ejecutar_fase3, de la que depende, y antes del diccionario).
    B5 (rangos de 2022) vive en tablas_finales.leer_informe, porque agrega filas a contraloria_distribuciones.csv.
    """
    guardar = tf.guardar_csv
    P = config.PROCESSED
    cifras = tf.a_enteros(pd.read_csv(config.CIFRAS_OFICIALES, encoding="utf-8-sig", dtype={"cod_departamento": str}), ENTEROS_CIFRAS[:-1])
    distribuciones = pd.read_csv(config.DISTRIBUCIONES_CGR, encoding="utf-8-sig")
    checks = []

    # A2 y A3
    obras = construir_obras_corte()
    guardar(obras, OBRAS_CORTE)
    v = validar_obras_corte(obras)
    checks.append(_checks("A2", pd.DataFrame({
        "fecha_corte": v.fecha_corte, "tabla": "contraloria_obras_corte", "comprobacion": "obras y costo = leer_base_excel; educacion igual",
        "valor_a": v.obras_nuevo, "valor_b": v.obras_leer_base_excel, "diferencia": v.obras_nuevo - v.obras_leer_base_excel, "tolerancia": 0, "ok": v.ok})))
    panel = construir_panel(obras)
    guardar(panel, OBRAS_PANEL)
    vp = validar_panel(panel, obras)
    checks.append(_checks("A3", pd.DataFrame({"fecha_corte": "", "tabla": "contraloria_obras_panel", "comprobacion": vp.comprobacion, "valor_a": vp.panel,
                                              "valor_b": vp.obras_corte, "diferencia": vp.panel - vp.obras_corte, "tolerancia": 0, "ok": vp.ok})))

    # B7: la columna nueva va en cifras_oficiales_contraloria.csv (se vuelve a escribir en cada corrida de la Fase 3)
    educacion = pd.read_csv(P / "contraloria_educacion_departamento.csv", encoding="utf-8-sig")
    cifras = corregir_educacion(cifras, educacion)
    guardar(tf.a_enteros(cifras, ENTEROS_CIFRAS), config.CIFRAS_OFICIALES)
    ve = validar_educacion(cifras)
    checks.append(_checks("B7", pd.DataFrame({"fecha_corte": ve.fecha_corte, "tabla": "cifras_oficiales_contraloria",
                                              "comprobacion": "Educacion corregida = Excel (y = PDF salvo set-2023 y set-2025)",
                                              "valor_a": ve.obras_educacion_corregida, "valor_b": ve.obras_paralizadas,
                                              "diferencia": ve.obras_educacion_corregida - ve.obras_paralizadas, "tolerancia": 0,
                                              "ok": ~ve.difiere_del_pdf | ve.fecha_corte.isin(["2023-09-30", "2025-09-30"])})))

    # B3
    pim, vpim = construir_pim(cifras)
    guardar(tf.a_enteros(pim, ["obras_con_pim", "obras_sin_pim", "obras_total", "pagina", "tabla_n"]), P / "contraloria_pim.csv")
    checks.append(_checks("B3", vpim.assign(tabla="contraloria_pim")))
    xp = validar_pim_con_excel(pim)
    if len(xp):
        checks.append(_checks("B3", xp.groupby("fecha_corte").agg(valor_a=("obras_con_pim_pdf", "sum"), valor_b=("obras_con_pim_excel", "sum"),
                                                                  diferencia=("diferencia", lambda s: s.abs().sum())).reset_index().assign(
            tabla="contraloria_pim", comprobacion="obras con PIM del PDF = columna TIENE PIM del Excel (nacional + 25 departamentos)", tolerancia=0).assign(
            ok=lambda d: d.diferencia == 0)))

    # B4
    modalidad, evento, vmod = construir_modalidad_evento(cifras, distribuciones)
    for nombre, tabla in (("contraloria_modalidad_ejecucion", modalidad), ("contraloria_evento_infobras", evento)):
        guardar(tf.a_enteros(tabla, ["obras_paralizadas", "pagina", "tabla_n"]), P / f"{nombre}.csv")
    checks.append(_checks("B4", vmod.assign(tabla=vmod.tabla.map(lambda x: f"contraloria_{'evento_infobras' if x == 'por_evento' else 'modalidad_ejecucion'} / {x}"))))
    vx = pd.concat([validar_modalidad_evento_con_excel(modalidad, evento, obras)], ignore_index=True)
    guardar(vx, VALIDACION_B4_EXCEL)
    if len(vx):
        resumen = vx.groupby(["fecha_corte", "tabla"]).agg(valor_a=("obras_pdf", "sum"), valor_b=("obras_excel", "sum"),
                                                          diferencia=("diferencia", lambda s: s.abs().sum())).reset_index()
        checks.append(_checks("B4", resumen.assign(comprobacion="obras por categoria y nivel: PDF vs base Excel (detalle en validacion_b4_excel.csv)",
                                                   tolerancia=0).assign(ok=lambda d: d.diferencia == 0)))
    sub = validar_subset_modalidad(modalidad)
    if len(sub):
        g = sub.groupby("fecha_corte").coincide.all().reset_index()
        checks.append(_checks("B4", pd.DataFrame({"fecha_corte": g.fecha_corte, "tabla": "contraloria_modalidad_ejecucion / administracion_directa_y_contrata",
                                                  "comprobacion": "obras de la subtabla = obras de la tabla por modalidad (mismos rotulos)",
                                                  "valor_a": g.coincide.astype(int), "valor_b": 1, "diferencia": g.coincide.astype(int) - 1,
                                                  "tolerancia": 0, "ok": g.coincide})))
    sc_total, sc_nivel, sc_dep, vsc = construir_servicios_control(cifras)
    guardar(tf.a_enteros(sc_total, ["cantidad", "pagina", "tabla_n"]), P / "contraloria_servicios_control_total.csv")
    guardar(tf.a_enteros(sc_nivel, ["cantidad", "pagina", "tabla_n"]), P / "contraloria_servicios_control_nivel_gobierno.csv")
    guardar(tf.a_enteros(sc_dep, ["control_previo", "control_simultaneo", "control_posterior", "total_servicios", "pagina", "tabla_n"]),
            P / "contraloria_servicios_control_departamento.csv")
    checks.append(_checks("B4", vsc.assign(tabla=vsc.tabla.map(lambda x: f"contraloria_servicios_control / {x}"))))

    # B6
    principales = construir_principales_obras(obras)
    guardar(principales, P / "contraloria_principales_obras.csv")
    vpr = validar_principales_obras(principales, obras)
    checks.append(_checks("B6", pd.DataFrame({"fecha_corte": vpr.fecha_corte, "tabla": "contraloria_principales_obras",
                                              "comprobacion": "CUI de la lista presentes en la base obra por obra del mismo corte",
                                              "valor_a": vpr.cui_en_base, "valor_b": vpr.obras, "diferencia": vpr.cui_en_base - vpr.obras, "tolerancia": 0,
                                              "ok": vpr.cui_en_base.fillna(vpr.obras) == vpr.obras})))

    todo = pd.concat([c for c in checks if len(c)], ignore_index=True)
    guardar(todo, VALIDACION)
    log(f"Anexos Excel (A2, A3, B7, B3, B4, B6): obras_corte {len(obras)} filas, panel {len(panel)} obras, pim {len(pim)}, modalidad {len(modalidad)}, "
        f"evento {len(evento)}, servicios de control {len(sc_total)}/{len(sc_nivel)}/{len(sc_dep)}, principales obras {len(principales)}; "
        f"comprobaciones {len(todo)} (no pasan: {int((~todo.ok.astype(bool)).sum())}; detalle en docs/validacion_anexos_excel.csv)")
    return todo
