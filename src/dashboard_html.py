"""Dashboard en HTML: un solo archivo que se abre en cualquier navegador, sin instalar nada y sin internet.

Lee los productos ya validados del pipeline (no recalcula nada por su cuenta):
  data/final/dashboard_obras.csv     obras, series de la Contraloria, causales y contexto por region
  docs/validacion_final.csv          comprobaciones del producto final
  docs/auditoria_calidad.csv         auditoria de calidad del CSV unico
  docs/registro_fuentes.csv          archivos descargados por fuente
  docs/inventario_datos.csv          tablas del proyecto (filas, periodo)
  docs/limites_y_calidad.md          limites y calidad del dato
y escribe resultados/dashboard.html (Plotly incluido dentro del archivo).

Pestanas: Resumen, Mapa, Causas, Regiones (pregunta guia), Obras (ficha), Proceso (como se construyo) y Limites.
Solo muestra obras de educacion basica (colegios): las deportivas, culturales y de educacion superior se excluyen del analisis y se listan en Proceso.
Filtros comunes: estado (por defecto paralizadas hoy), region y causa.
"""
import html
import json
import re
from datetime import datetime

import numpy as np
import pandas as pd

import config
import utils

SALIDA = config.RAIZ / "resultados" / "dashboard.html"
# silueta de Sudamerica para el mapa (Natural Earth via el paquete sane-topojson, licencia MIT): va dentro del HTML para que funcione sin internet
TOPOJSON = config.RAIZ / "src" / "recursos" / "south-america_50m.json"
RECURSOS = config.RAIZ / "src" / "recursos"
# limites de departamentos y provincias y capitales (github.com/juaneladio/peru-geojson, licencia MPL 2.0; ver src/recursos/FUENTE_peru-geojson.txt)
PERU_DEPARTAMENTOS, PERU_PROVINCIAS, PERU_CIUDADES = RECURSOS / "peru_departamentos.geojson", RECURSOS / "peru_provincias.geojson", RECURSOS / "peru_ciudades.json"
PLOTLY_JS = config.RAIZ / "src" / "recursos" / "plotly.min.js"   # plotly.js (licencia MIT) va con el proyecto: no hace falta instalar plotly

COLUMNAS_OBRA = ["codigo_infobras", "cui", "nombre_obra", "entidad", "departamento", "provincia", "distrito", "ubigeo", "region_enla",
                 "latitud_mapa", "longitud_mapa", "coordenada_origen", "tipo_infraestructura", "estado_infobras", "paralizada_hoy", "origen",
                 "causa_macro", "causa_grupo_final", "causa_fuente", "causal_oficial", "nivel_gobierno", "modalidad",
                 "monto_expediente_tecnico", "costo_actualizado_soles", "devengado_total_soles", "avance_fisico_pct",
                 "fecha_inicio", "fecha_paralizacion", "dias_paralizado", "dias_desde_paralizacion", "n_tramos_paralizacion", "alertas_calidad", "escale_pct_3_servicios"]
COLUMNAS_REGION = ["region_enla", "region_escale_locales_publicos", "region_escale_pct_3_servicios", "region_escale_pct_rural",
                   "region_escale_pct_riesgo_estructural", "region_enla_4p_lectura_satisfactorio", "region_enla_4p_matematica_satisfactorio",
                   "region_enla_2s_lectura_satisfactorio", "region_enla_2s_matematica_satisfactorio", "region_enla_4p_anio", "region_enla_2s_anio"]
NUMERICAS = ["latitud_mapa", "longitud_mapa", "monto_expediente_tecnico", "costo_actualizado_soles", "devengado_total_soles",
             "avance_fisico_pct", "dias_paralizado", "dias_desde_paralizacion", "n_tramos_paralizacion", "escale_pct_3_servicios", "n_obras", "costo_actualizado_soles",
             "pct_obras"] + COLUMNAS_REGION[1:]


def _registros(tabla):
    """DataFrame -> lista de dicts lista para JSON (NaN -> null; numeros como numeros)."""
    t = tabla.copy()
    for c in t.columns:
        if c in NUMERICAS:
            t[c] = pd.to_numeric(t[c], errors="coerce").round(4)
    t = t.astype(object).where(t.notna(), None)
    return t.to_dict(orient="records")


def _md_a_html(texto):
    """Markdown sencillo (titulos, listas, negrita, codigo) -> HTML. Suficiente para docs/limites_y_calidad.md."""
    salida, en_lista = [], False
    for linea in texto.splitlines():
        l = html.escape(linea.rstrip())
        l = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", l)
        l = re.sub(r"`(.+?)`", r"<code>\1</code>", l)
        if l.startswith("- "):
            if not en_lista:
                salida.append("<ul>")
                en_lista = True
            salida.append(f"<li>{l[2:]}</li>")
            continue
        if en_lista:
            salida.append("</ul>")
            en_lista = False
        if l.startswith("## "):
            salida.append(f"<h3>{l[3:]}</h3>")
        elif l.startswith("# "):
            continue          # el titulo lo pone la pestana
        elif l.strip():
            salida.append(f"<p>{l}</p>")
    if en_lista:
        salida.append("</ul>")
    return "\n".join(salida)


def _proceso(dash, validacion, calidad, fuentes, inventario, n_diccionario):
    """Pasos del pipeline con los numeros que salen de esta corrida (para la pestana Proceso)."""
    filas = dict(zip(inventario.tabla, pd.to_numeric(inventario.filas, errors="coerce")))
    disponibles = fuentes[fuentes.estado.isin(["ok", "omitido"])].drop_duplicates("archivo")   # el registro acumula una fila por corrida
    por_fuente = disponibles.groupby("fuente").size().to_dict()
    errores_calidad = int((calidad.nivel.str.upper() == "ERROR").sum()) if len(calidad) else 0
    avisos_calidad = int((calidad.nivel.str.lower() == "aviso").sum()) if len(calidad) else 0
    obras = dash[dash.tipo_registro == "obra_infobras"]
    n = lambda tabla: int(filas.get(tabla, 0) or 0)
    return [
        {"paso": "1. Descarga", "detalle": "Portales públicos: ESCALE, SICRECE (ENLA), Contraloría, MEF e INFOBRAS. Lo ya descargado se salta.",
         "cifra": f"{len(disponibles)} archivos", "extra": ", ".join(f"{k}: {v}" for k, v in sorted(por_fuente.items()))},
        {"paso": "2. ESCALE y ENLA", "detalle": "Infraestructura escolar por distrito y aprendizajes por región.",
         "cifra": f"{n('escale_infraestructura'):,} filas", "extra": f"ENLA: {n('enla_regiones')} filas por región y grado"},
        {"paso": "3. Datos personales", "detalle": "Se quitan nombres de personas de los textos libres antes de guardar.", "cifra": "Limpieza", "extra": "se comprueba en el paso 7"},
        {"paso": "4. PDF, anexos e INFOBRAS", "detalle": "Cifras oficiales de los informes de la Contraloría y lectura de las fichas HTML de INFOBRAS (semiestructurado).",
         "cifra": f"{len(obras)} obras", "extra": f"{n('infobras_avances'):,} avances mensuales · {n('contraloria_obras_corte'):,} filas obra-corte"},
        {"paso": "5. Producto final", "detalle": "Une todo por obra (CUI, ubigeo) y por región; clasifica la causa (reglas + NLP) y el tipo de infraestructura.",
         "cifra": f"{len(dash):,} filas", "extra": f"{int(validacion.ok.astype(str).eq('True').sum())} de {len(validacion)} comprobaciones pasan"},
        {"paso": "6. Diccionario", "detalle": "Cada columna de cada tabla con su tipo, descripción y unidad.", "cifra": f"{n_diccionario} columnas", "extra": "docs/diccionario.csv"},
        {"paso": "7. Auditoría de datos personales", "detalle": "Busca nombres, DNI y teléfonos en las tablas finales.", "cifra": "0 hallazgos", "extra": ""},
        {"paso": "8. Inventario", "detalle": "Qué tablas hay, de qué fuente y qué período cubren.", "cifra": f"{len(inventario)} tablas", "extra": ""},
        {"paso": "9. Auditoría de calidad", "detalle": "Tipos, rangos, códigos y coordenadas del CSV único.", "cifra": f"{errores_calidad} errores", "extra": f"{avisos_calidad} avisos (ver Límites)"},
        {"paso": "10. Dashboard", "detalle": "Este archivo: se genera solo con los productos validados.", "cifra": "dashboard.html", "extra": ""},
    ]


def _distritos(regiones_validas):
    """Todos los distritos del pais con sus indicadores de ESCALE (ultimo anio) y su region ENLA (Lima se separa en Metropolitana y Provincias)."""
    e = pd.read_csv(config.PROCESSED / "escale_infraestructura.csv", dtype={"ubigeo": str}, encoding="utf-8-sig")
    e = e[e.anio == e.anio.max()].copy()
    e["region_enla"] = np.where(e.departamento != "LIMA", e.departamento, np.where(e.provincia == "LIMA", "LIMA METROPOLITANA", "LIMA PROVINCIAS"))
    fuera = sorted(set(e.region_enla) - set(regiones_validas))
    if fuera:
        utils.log(f"AVISO DASHBOARD HTML: regiones de ESCALE que no estan en ENLA: {fuera}")
    cols = ["ubigeo", "region_enla", "provincia", "distrito", "n_locales_publicos", "pct_3_servicios", "pct_rural", "pct_riesgo_estructural"]
    for c in cols[4:]:
        e[c] = pd.to_numeric(e[c], errors="coerce").round(1)
    return e[cols].astype(object).where(e[cols].notna(), None).to_dict(orient="records"), int(e.anio.max())


MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]


def _cobertura(obras, serie, regiones, lectura):
    """Desde que anio hay informacion de cada fuente (texto corto para el encabezado)."""
    colegios = obras[obras.tipo_infraestructura == "educacion_basica"]
    anio = lambda col: pd.to_datetime(colegios[col], errors="coerce").dt.year
    corte = pd.to_datetime(serie.fecha_corte, errors="coerce")
    mes = lambda f: f"{MESES[f.month - 1]}-{f.year}"
    escale = pd.read_csv(config.PROCESSED / "escale_infraestructura.csv", usecols=["anio"], encoding="utf-8-sig").anio
    enla = pd.to_numeric(regiones[[c for c in regiones.columns if c.startswith("region_enla_") and c.endswith("_anio")]].stack(), errors="coerce")
    return (f"Información: obras iniciadas desde {int(anio('fecha_inicio').min())} y paralizaciones registradas desde {int(anio('fecha_paralizacion').min())} "
            f"(INFOBRAS, leído el {lectura}) · Contraloría de {mes(corte.min())} a {mes(corte.max())} · ESCALE {int(escale.min())}–{int(escale.max())} · "
            f"ENLA {int(enla.min())}–{int(enla.max())} · MEF: Formato 12-B (foto mensual).")


def _archivos_embebidos():
    """CSV de descarga comprimidos dentro del HTML: el tablero no depende de su carpeta."""
    import base64, gzip
    def uno(ruta, nombre):
        return {"nombre": nombre, "ruta": str(ruta.relative_to(config.RAIZ)).replace("\\", "/"),
                "datos": base64.b64encode(gzip.compress(ruta.read_bytes(), 9)).decode("ascii")}
    return json.dumps({"csv": uno(config.FINAL / "dashboard_obras.csv", "dashboard_obras.csv"),
                       "diccionario": uno(config.DOCS / "diccionario.csv", "diccionario.csv")})


def _punto_etiqueta(geom):
    """Centroide del poligono mas grande (lon, lat): donde va el nombre de la region o provincia."""
    poligonos = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    def area_centro(anillo):
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(anillo, anillo[1:] + anillo[:1]):
            c = x0 * y1 - x1 * y0; a += c; cx += (x0 + x1) * c; cy += (y0 + y1) * c
        return (abs(a) / 2, cx / (3 * a), cy / (3 * a)) if a else (0, anillo[0][0], anillo[0][1])
    _, x, y = max((area_centro(pol[0]) for pol in poligonos), key=lambda t: t[0])
    return round(x, 3), round(y, 3)


# ajustes a mano donde el centroide queda mal ubicado o se cruza con otro nombre (lon, lat)
AJUSTE_ETIQUETA = {"LIMA": (-76.55, -11.45), "ICA": (-75.45, -14.45), "TUMBES": (-80.5, -3.85), "LAMBAYEQUE": (-80.15, -6.45), "CAJAMARCA": (-78.6, -6.95),
                   "AMAZONAS": (-78.05, -5.3), "MOQUEGUA": (-70.95, -16.75), "TACNA": (-70.35, -17.6), "PASCO": (-75.4, -10.45),
                   "HUANCAVELICA": (-75.05, -12.85), "AYACUCHO": (-74.15, -14.1), "APURIMAC": (-72.95, -14.25), "CUSCO": (-71.95, -12.85),
                   "LA LIBERTAD": (-78.25, -7.95), "ANCASH": (-77.6, -9.45), "PIURA": (-80.25, -5.15)}


def _cartografia():
    """Regiones y provincias del Peru (GeoJSON), puntos para sus nombres y ciudades principales: el mapa no necesita internet."""
    if not (PERU_DEPARTAMENTOS.exists() and PERU_PROVINCIAS.exists()):
        utils.log("AVISO DASHBOARD HTML: faltan los limites del Peru en src/recursos; el mapa se dibuja sin regiones")
        return None
    dep = json.loads(PERU_DEPARTAMENTOS.read_text(encoding="utf-8"))
    prov = json.loads(PERU_PROVINCIAS.read_text(encoding="utf-8"))
    etiquetas_dep = []
    for f in dep["features"]:
        nombre = f["properties"]["departamento"]
        lon, lat = AJUSTE_ETIQUETA.get(nombre) or _punto_etiqueta(f["geometry"])
        if nombre != "CALLAO":   # es muy pequeno: lo nombra la ciudad
            etiquetas_dep.append({"nombre": nombre, "lon": lon, "lat": lat})
    etiquetas_prov = [dict(zip(("lon", "lat"), _punto_etiqueta(f["geometry"])), nombre=f["properties"]["provincia"], departamento=f["properties"]["departamento"]) for f in prov["features"]]
    ciudades = json.loads(PERU_CIUDADES.read_text(encoding="utf-8")) if PERU_CIUDADES.exists() else []
    return {"departamentos": dep, "provincias": prov, "etiquetas_dep": etiquetas_dep, "etiquetas_prov": etiquetas_prov, "ciudades": ciudades}


def construir():
    dash = pd.read_csv(config.FINAL / "dashboard_obras.csv", dtype=str, encoding="utf-8-sig", low_memory=False)
    validacion = pd.read_csv(config.DOCS / "validacion_final.csv", dtype=str, encoding="utf-8-sig")
    calidad = pd.read_csv(config.DOCS / "auditoria_calidad.csv", dtype=str, encoding="utf-8-sig")
    fuentes = pd.read_csv(config.DOCS / "registro_fuentes.csv", dtype=str, encoding="utf-8-sig")
    inventario = pd.read_csv(config.DOCS / "inventario_datos.csv", dtype=str, encoding="utf-8-sig")
    limites = (config.DOCS / "limites_y_calidad.md").read_text(encoding="utf-8") if (config.DOCS / "limites_y_calidad.md").exists() else ""

    tipo = dash.tipo_registro
    obras = dash.loc[tipo == "obra_infobras", COLUMNAS_OBRA].copy()
    obras["paralizada_hoy"] = obras.paralizada_hoy.astype(str).str.lower().eq("true")
    # Nombres del distrito y la provincia segun el ubigeo (ESCALE/INEI): en 4 obras INFOBRAS trae mal la ubicacion y el ubigeo ya esta corregido
    escale = pd.read_csv(config.PROCESSED / "escale_infraestructura.csv", dtype={"ubigeo": str}, encoding="utf-8-sig", usecols=["ubigeo", "anio", "provincia", "distrito"])
    nombres = escale.sort_values("anio").drop_duplicates("ubigeo", keep="last").set_index("ubigeo")
    for col in ("distrito", "provincia"):
        obras[col] = obras.ubigeo.map(nombres[col]).fillna(obras[col])
    serie = dash.loc[tipo.isin(["pais_educacion_corte", "pais_total_corte"]), ["tipo_registro", "fecha_corte", "n_obras", "costo_actualizado_soles", "pct_obras"]]
    causales = (dash.loc[tipo == "causal_corte"].assign(n=lambda d: pd.to_numeric(d.n_obras, errors="coerce"))
                .groupby(["fecha_corte", "causa_macro"], as_index=False).n.sum())
    regiones = dash.loc[tipo == "contexto_region", COLUMNAS_REGION]
    validacion = validacion.assign(**{c: validacion[c].str.replace(r"\.0$", "", regex=True) for c in ("valor", "esperado")})
    distritos, anio_escale = _distritos(regiones.region_enla.tolist())
    regiones_todo = dash.loc[tipo == "contexto_region"]
    datos = {
        "geo": _cartografia(),
        "cobertura": _cobertura(obras, serie, regiones_todo, dash.loc[tipo == "obra_infobras", "fecha_corte"].dropna().max()),
        "obras": _registros(obras), "serie": _registros(serie), "causales": causales.rename(columns={"n": "n_obras"}).to_dict(orient="records"),
        "regiones": _registros(regiones),
        "distritos": distritos, "anio_escale": anio_escale,
        "validacion": validacion[["tabla", "comprobacion", "valor", "esperado", "ok"]].fillna("").to_dict(orient="records"),
        "calidad": calidad.fillna("").to_dict(orient="records"),
        "proceso": _proceso(dash, validacion, calidad, fuentes, inventario, len(pd.read_csv(config.DOCS / "diccionario.csv", dtype=str, encoding="utf-8-sig"))),
        "generado": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "url_ficha": f"{config.INFOBRAS_BASE}/Mapa/Sumario?ObraId=",
    }
    js_datos = json.dumps(datos, ensure_ascii=False).replace("</", "<\\/")
    if PLOTLY_JS.exists():
        plotly_js = PLOTLY_JS.read_text(encoding="utf-8")
    else:   # respaldo: la libreria plotly, si esta instalada
        import plotly.offline
        plotly_js = plotly.offline.get_plotlyjs()
    if TOPOJSON.exists():
        topo = '{"south-america_50m": ' + TOPOJSON.read_text(encoding="utf-8") + "}"
    else:   # sin el archivo, Plotly descarga la silueta de internet (el mapa solo se ve con conexion)
        utils.log(f"AVISO DASHBOARD HTML: falta {TOPOJSON}; el mapa necesitara internet para verse")
        topo = "{}"
    pagina = (PLANTILLA.replace("/*PLOTLY*/", plotly_js)
              .replace("/*TOPOJSON*/", topo)
              .replace("/*ARCHIVOS*/", _archivos_embebidos())
              .replace("/*DATOS*/", js_datos)
              .replace("<!--LIMITES-->", _md_a_html(limites)))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(pagina, encoding="utf-8")
    basica = obras[(obras.tipo_infraestructura == "educacion_basica") & obras.paralizada_hoy]
    utils.log(f"DASHBOARD HTML: {SALIDA.relative_to(config.RAIZ)} ({SALIDA.stat().st_size / 1e6:.1f} MB); "
              f"{len(obras)} obras, {len(basica)} de educacion basica paralizadas hoy en {basica.ubigeo.nunique()} distritos")
    return SALIDA


PLANTILLA = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor de obras de infraestructura educativa paralizadas · Perú</title>
<style>
:root {
  color-scheme: light;
  --surface-0: #f6f9fd; --surface-1: #ffffff; --border: #dde6f2; --grid: #edf1f7;
  --text-primary: #0f1d2e; --text-secondary: #46566b; --text-muted: #77849a;
  --series-1: #2a78d6; --series-2: #eb6834; --series-3: #1baf7a; --other: #a9b0bb;
  --good: #0ca30c; --critical: #d03b3b; --accent-soft: #e4edfa;
  --azul: #3a72c4; --azul-osc: #2a5ba8; --azul-claro: #7d9fd6; --azul-palido: #b8c8e6; --naranja: #f7a21b;
  --rojo: #ee6a72; --ambar: #f3c04c; --verde: #74c47a;
  --c-amarillo: #f5b915; --c-verde: #3fb36b; --c-rojo: #ec5466; --c-naranja: #f7891f; --c-celeste: #3a9ad9;
  --acento: #f7891f; --acento-tx: #fff;
  --sombra: 0 3px 10px rgba(58, 114, 196, .12);
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --surface-0: #0f1620; --surface-1: #172230; --border: #263446; --grid: #22303f;
    --text-primary: #eef2f7; --text-secondary: #b8c3d1; --text-muted: #8996a8;
    --series-1: #3987e5; --series-2: #d95926; --series-3: #199e70; --other: #5f6b7a;
    --good: #0ca30c; --critical: #e66767; --accent-soft: #1d2d42;
    --azul: #3a72c4; --azul-osc: #24508f; --azul-claro: #6f90cc; --azul-palido: #4a6696;
    --rojo: #ee6a72; --ambar: #e9b843; --verde: #63b46a; --sombra: none;
  }
}
* { box-sizing: border-box; }
[hidden] { display: none !important; }
body { margin: 0; font-family: "Segoe UI", system-ui, -apple-system, sans-serif; background: var(--surface-0); color: var(--text-primary); }
svg.ic { width: 26px; height: 26px; fill: none; stroke: currentColor; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; flex: none; }
/* ---------- portada ---------- */
.portada { min-height: 100vh; display: grid; grid-template-columns: 300px 1fr 170px; gap: 28px; padding: 26px 34px; align-items: start; }
.portada .menu { display: flex; flex-direction: column; gap: 12px; }
.portada .menu button { display: flex; align-items: center; gap: 14px; text-align: left; border: 0; border-radius: 10px; padding: 14px 16px; font-size: 16px; color: var(--tx, #fff);
  background: var(--bg, var(--azul)); box-shadow: inset 0 0 0 3px rgba(255,255,255,.55), var(--sombra); cursor: pointer; transition: transform .15s, background .15s; }
.portada .menu button:hover { transform: translateX(6px); filter: brightness(1.06); box-shadow: inset 0 0 0 3px #fff, 0 4px 14px rgba(0,0,0,.15); }
.portada .menu button small { display: block; font-size: 12px; opacity: .85; }
.portada .marca { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.portada .marca .sello { background: var(--azul); color: #fff; font-weight: 800; font-size: 26px; letter-spacing: 1px; padding: 6px 14px; border-radius: 6px; }
.portada .marca small { color: var(--text-secondary); font-size: 12px; line-height: 1.3; }
.portada .centro { text-align: center; }
.portada h1 { margin: 6px 0 2px; font-size: 30px; font-style: italic; font-weight: 500; color: var(--azul); }
.portada .gancho { font-size: 18px; color: var(--text-secondary); margin: 4px auto 6px; max-width: 760px; }
.portada .gancho b { color: var(--rojo); font-size: 22px; }
#rueda { width: min(470px, 90%); height: auto; display: block; margin: 0 auto; }
#rueda .seg { cursor: pointer; transition: transform .2s, filter .2s; transform-origin: 250px 250px; }
#rueda .seg:hover { transform: scale(1.04); filter: brightness(1.08); }
.cifras { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-top: 10px; }
.cifra-p { background: var(--surface-1); border-radius: 12px; padding: 14px 10px; box-shadow: var(--sombra); border-top: 5px solid var(--c); }
.cifra-p svg.ic { width: 34px; height: 34px; color: var(--c); }
.cifra-p .v { font-size: 26px; font-weight: 750; margin-top: 4px; }
.cifra-p .e { font-size: 12px; color: var(--text-secondary); }
.portada .derecha { display: flex; flex-direction: column; gap: 26px; align-items: center; padding-top: 120px; }
.portada .derecha a { display: flex; flex-direction: column; align-items: center; gap: 6px; color: var(--c, var(--azul)); text-decoration: none; font-size: 13px; text-align: center; }
.portada .derecha a svg.ic { width: 54px; height: 54px; stroke-width: 1.6; color: var(--c); }
.portada .derecha a { color: var(--text-secondary) !important; font-weight: 600; }
.portada .derecha a:hover { filter: brightness(.85); }
.portada .caja { border: 1px solid var(--border); background: var(--surface-1); padding: 10px 12px; font-size: 12px; color: var(--text-secondary); margin-top: 18px; border-radius: 6px; }
/* ---------- paginas internas ---------- */
.banda { background: linear-gradient(90deg, var(--azul), #4f8ad8); color: #fff; padding: 14px 28px 0; display: grid; grid-template-columns: 1fr auto; gap: 8px 20px; align-items: center; }
.banda .marca { font-size: 12px; opacity: .8; letter-spacing: .4px; text-transform: uppercase; }
.banda h1 { margin: 2px 0 0; font-size: 26px; font-weight: 600; }
.inicio-btn { grid-row: span 2; width: 86px; height: 86px; border-radius: 50%; border: 0; background: #fff; color: var(--azul); cursor: pointer; display: flex; flex-direction: column; align-items: center; justify-content: center; font-size: 12px; font-weight: 700; box-shadow: 0 2px 10px rgba(0,0,0,.2); }
.inicio-btn svg.ic { width: 34px; height: 34px; }
.inicio-btn:hover { background: var(--naranja); color: #fff; }
.pildoras { display: flex; gap: 8px; flex-wrap: wrap; padding: 10px 0 14px; }
.pildoras button { border: 0; border-radius: 999px; padding: 9px 22px; font-size: 14px; background: #e8edf4; color: #1f2d3d; cursor: pointer; }
.pildoras button.activa { background: var(--naranja); color: #fff; font-weight: 700; box-shadow: 0 2px 6px rgba(0,0,0,.2); }
nav { display: flex; gap: 6px; padding: 10px 28px; background: var(--surface-1); border-bottom: 1px solid var(--border); flex-wrap: wrap; }
nav button { display: flex; align-items: center; gap: 6px; border: 1px solid var(--border); background: var(--surface-1); padding: 6px 12px; border-radius: 8px; font-size: 13px; color: var(--text-secondary); cursor: pointer; }
nav button svg.ic { width: 18px; height: 18px; }
nav button.activa { background: var(--acento); border-color: var(--acento); color: var(--acento-tx); font-weight: 700; }
nav button:hover { border-color: var(--acento); }
.cuerpo { display: grid; grid-template-columns: 250px minmax(0, 1fr) 190px; gap: 18px; padding: 18px 28px 40px; align-items: start; }
.cuerpo.ancho { grid-template-columns: minmax(0, 1fr); }
.cuerpo.ancho .panel, .cuerpo.ancho .lateral { display: none; }
.panel { background: var(--surface-1); border-radius: 12px; padding: 14px; box-shadow: var(--sombra); border-top: 5px solid var(--acento); position: sticky; top: 10px; }
.panel h3 { margin: 0 0 10px; text-align: center; font-size: 17px; font-weight: 600; }
.panel label, label.en-linea { display: flex; flex-direction: column; font-size: 12px; color: var(--text-secondary); gap: 4px; margin-bottom: 10px; }
label.en-linea { flex-direction: row; align-items: center; gap: 8px; margin: 0; font-size: 13px; white-space: nowrap; }
label.en-linea select { width: auto; }
.panel select, label.en-linea select { font-size: 14px; padding: 7px 8px; border: 1px solid var(--border); border-radius: 8px; background: var(--surface-1); color: var(--text-primary); width: 100%; }
.que-muestra { background: var(--azul); color: #fff; border-radius: 10px; padding: 12px; margin: 12px 0; font-size: 13px; line-height: 1.45; }
.que-muestra b { display: block; font-size: 14px; margin-bottom: 4px; color: #ffe08a; }
.borrar { width: 100%; border: 0; border-radius: 8px; padding: 10px; background: #a9b4c4; color: #fff; font-size: 15px; font-weight: 700; cursor: pointer; }
.borrar:hover { background: var(--c-rojo); }
.panel .nota { font-size: 11px; color: var(--text-muted); margin-top: 10px; }
.lateral { display: flex; flex-direction: column; gap: 12px; position: sticky; top: 10px; }
.kpi { background: var(--surface-1); border-radius: 10px; padding: 14px 12px; text-align: center; box-shadow: var(--sombra); border-bottom: 5px solid var(--c, var(--azul)); }
.kpi:first-child { background: var(--c-naranja); color: #fff; border-bottom-color: #d96f08; }
.kpi:first-child .etiqueta { color: #fff7e6; }
.kpi .valor { font-size: 24px; font-weight: 700; line-height: 1.1; color: inherit; }
.kpi .etiqueta { font-size: 12px; color: var(--text-secondary); margin-top: 4px; }
.pestana { display: none; }
.pestana.activa { display: block; }
.fila { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); margin-bottom: 16px; }
.tarjeta { background: var(--surface-1); border-radius: 12px; padding: 16px; box-shadow: var(--sombra); border-top: 5px solid var(--acento); }
.tarjeta h2 { margin: 0 0 2px; font-size: 16px; font-weight: 650; color: var(--azul); text-align: center; }
.tarjeta .sub { margin: 0 0 8px; font-size: 12px; color: var(--text-muted); text-align: center; }
.grafico { width: 100%; height: 360px; }
.grafico.alto { height: 560px; }
.fuente { font-size: 11px; color: var(--text-muted); margin-top: 6px; }
.semaforo { display: flex; gap: 14px; flex-wrap: wrap; align-items: center; font-size: 13px; color: var(--text-secondary); margin-left: auto; }
.semaforo span { display: inline-flex; align-items: center; gap: 6px; }
.semaforo i { display: inline-block; width: 46px; height: 10px; border-radius: 6px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--acento-tx); background: var(--acento); font-weight: 600; position: sticky; top: 0; cursor: pointer; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr:nth-child(even) { background: rgba(0, 0, 0, .025); }
tbody tr:hover { background: var(--accent-soft); cursor: pointer; }
.tabla-scroll { max-height: 560px; overflow: auto; }
.ficha { display: none; margin-bottom: 16px; border-top-color: var(--c-rojo) !important; }
.ficha.visible { display: block; }
.ficha h2 { text-align: left; }
.ficha dl { display: grid; grid-template-columns: 220px 1fr; gap: 6px 14px; margin: 8px 0 0; font-size: 13px; }
.ficha dt { color: var(--text-secondary); }
.ficha dd { margin: 0; }
.estado { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; border: 1px solid var(--border); }
.ok { color: var(--good); font-weight: 600; }
.no { color: var(--critical); font-weight: 600; }
.flujo { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
.paso { background: var(--surface-1); border-radius: 10px; padding: 12px; box-shadow: var(--sombra); border-left: 5px solid var(--naranja); }
.paso b { display: block; font-size: 14px; }
.paso .cifra { font-size: 20px; font-weight: 700; margin: 6px 0 2px; color: var(--c-naranja); }
.paso:nth-child(4n+2) { border-left-color: var(--c-verde); } .paso:nth-child(4n+3) { border-left-color: var(--c-amarillo); } .paso:nth-child(4n+4) { border-left-color: var(--c-rojo); }
.paso small { color: var(--text-secondary); font-size: 12px; display: block; }
.aviso { background: #fff7e0; border-left: 5px solid var(--c-amarillo); border-radius: 8px; padding: 10px 12px; font-size: 13px; color: var(--text-secondary); margin-bottom: 14px; }
.texto-limites { max-width: 900px; font-size: 14px; line-height: 1.55; margin: 0 auto; }
.texto-limites h2 { text-align: left; }
.texto-limites h3 { margin: 22px 0 6px; font-size: 16px; color: var(--azul); }
code { font-size: 12px; background: var(--surface-0); padding: 1px 4px; border-radius: 4px; }
@media (max-width: 1150px) {
  .portada, .cuerpo { grid-template-columns: 1fr; }
  .portada .derecha { flex-direction: row; padding-top: 0; justify-content: center; }
  .panel, .lateral { position: static; }
  .lateral { flex-direction: row; flex-wrap: wrap; } .lateral .kpi { flex: 1 1 150px; }
  .cifras { grid-template-columns: repeat(2, 1fr); }
}
</style>
</head>
<body>
<section id="inicio" class="portada">
  <div>
    <div class="marca"><span class="sello">MOEP</span><small>Monitor de Obras<br>Escolares Paralizadas · Perú</small></div>
    <div class="menu" id="menu-portada"></div>
    <div class="caja" id="cobertura"></div>
  </div>
  <div class="centro">
    <h1>¿Qué colegios tienen obras paralizadas?</h1>
    <p class="gancho" id="gancho"></p>
    <svg id="rueda" viewBox="0 0 500 500" role="img" aria-label="Las cuatro preguntas del monitor"></svg>
    <div class="cifras" id="cifras-portada"></div>
  </div>
  <div class="derecha">
    <a style="--c:#3fb36b" href="#" onclick="descargar('csv');return false" title="CSV único del proyecto (data/final/dashboard_obras.csv)"><span data-ic="descarga"></span>Descargar datos (CSV)</a>
    <a style="--c:#f5b915" href="#" onclick="descargar('diccionario');return false" title="Qué significa cada columna (docs/diccionario.csv)"><span data-ic="libro"></span>Diccionario de datos</a>
    <a style="--c:#f7891f" href="#" onclick="mostrar('proceso');return false"><span data-ic="base"></span>Fuentes y proceso</a>
    <a style="--c:#ec5466" href="#" onclick="mostrar('limites');return false"><span data-ic="info"></span>Límites del dato</a>
  </div>
</section>

<div id="app" hidden>
<div class="banda">
  <div><div class="marca">Monitor de obras escolares paralizadas · Perú</div><h1 id="titulo-pagina"></h1></div>
  <button class="inicio-btn" onclick="mostrar('inicio')"><span data-ic="casa"></span>INICIO</button>
  <div class="pildoras" id="pildoras">
    <button data-e="hoy" class="activa">Paralizadas hoy</button>
    <button data-e="ya_no">Ya no paralizadas</button>
    <button data-e="todas">Todas las obras escolares</button>
  </div>
</div>
<nav id="nav"></nav>
<div class="cuerpo" id="cuerpo">
<aside class="panel" id="panel">
  <h3>Filtros</h3>
  <select id="f-estado" hidden><option value="hoy">hoy</option><option value="ya_no">ya_no</option><option value="todas">todas</option></select>
  <label>Región<select id="f-region"></select></label>
  <label>Distrito<select id="f-distrito" disabled><option value="">Elija primero una región</option></select></label>
  <label>Causa principal<select id="f-causa"></select></label>
  <label>Año de paralización<select id="f-anio"></select></label>
  <div class="que-muestra"><b>¿Qué muestra esta página?</b><span id="explica"></span></div>
  <button class="borrar" id="borrar">Borrar filtros</button>
  <div class="nota" id="nota-filtro"></div>
</aside>
<main>

<section class="pestana" id="p-ranking">
  <div class="tarjeta" style="margin-bottom:16px;display:flex;gap:16px;align-items:center;flex-wrap:wrap">
    <label class="en-linea">Ordenar por <select id="f-orden-ranking">
      <option value="n">Número de obras</option><option value="monto">Monto del expediente técnico (S/ millones)</option><option value="anios">Años paralizada (mediana)</option>
    </select></label>
    <div class="semaforo" id="leyenda-semaforo"></div>
  </div>
  <div class="fila">
    <div class="tarjeta"><h2>Región</h2><p class="sub">Color = cuántos años llevan paralizadas sus obras (mediana) · clic en una región para filtrarla</p><div class="grafico" id="g-rank-region"></div></div>
    <div class="tarjeta"><h2>Distrito (los 25 primeros)</h2><p class="sub">Mismo color · clic en un distrito para ver sus obras</p><div class="grafico" id="g-rank-distrito"></div></div>
  </div>
  <div class="fuente">Fuente: INFOBRAS (lectura del 11-nov-2026) y Contraloría. El tiempo paralizada se mide desde la fecha de paralización; solo existe para las obras paralizadas hoy (las demás van en gris).</div>
</section>

<section class="pestana" id="p-resumen">
  <div class="fila">
    <div class="tarjeta"><h2>Obras de Educación paralizadas en el país, por corte</h2><p class="sub">Número de obras · lista oficial de la Contraloría (todo el sector Educación)</p><div class="grafico" id="g-serie"></div><div class="fuente">Fuente: Contraloría, informes de obras paralizadas (jun-2022 a jun-2026). Cuenta <b>todo el sector Educación</b>, incluidas obras que no son colegios (la fuente no permite separarlas). No depende de los filtros.</div></div>
    <div class="tarjeta"><h2>Regiones con más obras (según filtros)</h2><p class="sub">Número de obras</p><div class="grafico" id="g-top-regiones"></div><div class="fuente">Fuente: INFOBRAS (lectura del 11-nov-2026) y Contraloría.</div></div>
  </div>
  <div class="fila">
    <div class="tarjeta"><h2>Obras por año en que se paralizaron (según filtros)</h2><p class="sub">Número de obras de colegios · año de la fecha de paralización registrada en INFOBRAS · no depende del filtro de año</p><div class="grafico" id="g-anio-paralizacion"></div><div class="fuente">Fuente: INFOBRAS, detalle del último avance paralizado.</div></div>
    <div class="tarjeta"><h2>Obras por año de inicio (según filtros)</h2><p class="sub">Número de obras de colegios · año de inicio de la obra</p><div class="grafico" id="g-anio-inicio"></div><div class="fuente">Fuente: INFOBRAS, datos generales de la obra.</div></div>
  </div>
</section>

<section class="pestana" id="p-mapa">
  <div class="fila" style="grid-template-columns: 1fr">
  <div class="tarjeta">
    <h2>Dónde están las obras</h2><p class="sub">Cada punto es una obra · color = causa principal · ◆ = ubicación aproximada (centro del distrito o local escolar de ESCALE) · clic en un punto para ver la ficha</p>
    <div class="grafico" id="g-mapa" style="height:760px"></div>
    <div class="fuente">Fuente: coordenadas de INFOBRAS; 17 obras sin coordenadas se ubican de forma aproximada con ESCALE 2025.</div>
  </div>
  <div class="tarjeta"><h2>Distritos con más obras (según filtros)</h2><p class="sub">Haga clic en un distrito para ver sus obras</p><div class="tabla-scroll" style="max-height:640px"><table id="t-distritos"></table></div></div>
  </div>
</section>

<section class="pestana" id="p-causas">
  <div class="fila">
    <div class="tarjeta"><h2>Causa principal de la paralización (según filtros)</h2><p class="sub">Número de obras por macro-categoría</p><div class="grafico" id="g-causa-macro"></div><div class="fuente">Fuente: causal oficial de la Contraloría, comentarios de INFOBRAS y problemática del MEF, clasificados con reglas (NLP).</div></div>
    <div class="tarjeta"><h2>Causa detallada (según filtros)</h2><p class="sub">Número de obras por grupo de causa</p><div class="grafico" id="g-causa-grupo"></div><div class="fuente">Fuente: igual que el gráfico anterior.</div></div>
  </div>
  <div class="tarjeta"><h2>Causas a lo largo del tiempo (todos los sectores)</h2><p class="sub">Número de obras paralizadas por macro-categoría de causa, por corte · contractual, financiera y técnica (las más frecuentes en las obras escolares); el resto y lo que el informe no clasifica, agrupado</p><div class="grafico" id="g-causa-tiempo"></div><div class="fuente">Fuente: Contraloría, cuadro de causales de cada informe. No depende de los filtros.</div></div>
</section>

<section class="pestana" id="p-regiones">
  <div class="aviso"><b>Pregunta guía:</b> ¿las regiones con más obras educativas paralizadas son también las de mayores brechas de infraestructura y aprendizaje? Se compara cada región con su número de obras <b>por cada 100 locales escolares públicos</b> (para no favorecer a las regiones grandes). Son 26 regiones: es una <b>asociación</b>, no prueba que una cosa cause la otra.</div>
  <div class="fila" style="grid-template-columns: 1fr">
    <div class="tarjeta">
      <h2 id="t-dispersion">Obras por cada 100 locales frente al indicador</h2>
      <p class="sub"><label>Indicador: <select id="f-indicador"></select></label> · <span id="rho"></span></p>
      <div class="grafico alto" id="g-dispersion"></div>
      <div class="fuente">Fuentes: obras según filtros (INFOBRAS/Contraloría); locales y servicios: ESCALE 2025; aprendizajes: ENLA (último año disponible por grado).</div>
    </div>
    <div class="tarjeta"><h2>Tabla por región</h2><p class="sub">Clic en un encabezado para ordenar · clic en una región para ver sus distritos</p><div class="tabla-scroll"><table id="t-regiones"></table></div></div>
  </div>
  <div class="tarjeta" id="c-distritos">
    <h2 id="h-distritos-region">Distritos de la región</h2>
    <p class="sub" id="s-distritos-region"></p>
    <div class="tabla-scroll"><table id="t-distritos-region"></table></div>
    <div class="fuente" id="f-distritos-region"></div>
  </div>
</section>

<section class="pestana" id="p-obras">
  <div class="tarjeta ficha" id="ficha"></div>
  <div class="tarjeta">
    <h2>Obras (según filtros)</h2>
    <p class="sub"><input id="buscar" placeholder="Buscar por nombre, distrito, colegio o código..." style="width:340px;padding:6px 8px;border:1px solid var(--border);border-radius:6px;background:var(--surface-1);color:var(--text-primary)"> · haga clic en una fila para ver la ficha · <span id="n-obras"></span></p>
    <div class="tabla-scroll"><table id="t-obras"></table></div>
  </div>
</section>

<section class="pestana" id="p-proceso">
  <div class="aviso">Todo se genera con <b>un solo comando</b> (<code>ejecutar.bat</code> o <code>python src\pipeline_completo.py</code>). El detalle paso a paso, con el código y sus resultados, está en <code>notebooks/proyecto_completo.ipynb</code>. Las cifras de este tablero salen de esa misma corrida. <b>Generado: <span id="generado"></span>.</b></div>
  <div class="tarjeta" style="margin-bottom:16px">
    <h2>De las obras leídas a las obras del análisis</h2>
    <p class="sub">INFOBRAS agrupa Educación y Cultura. Como el objetivo son las instituciones educativas (y ESCALE y ENLA miden colegios y alumnos), el análisis se limita a la educación básica. Las demás obras siguen en los datos (columna <code>tipo_infraestructura</code>).</p>
    <div id="embudo"></div>
    <div class="fila" style="margin-top:12px">
      <div><h2 style="font-size:14px">Obras excluidas del análisis, por tipo</h2><table id="t-excluidas"></table></div>
      <div class="sub" style="align-self:center">La clasificación usa reglas sobre el nombre de la obra (por ejemplo «I.E.», «colegio», «local escolar» → colegio; «estadio», «losa deportiva» → deportiva; «universidad», «instituto superior» → educación superior; «museo», «arqueológico» → cultural). Si el nombre no lo dice, se usa el tipo de obra de INFOBRAS. Puede haber errores puntuales: la lista completa está abajo para revisarla.</div>
    </div>
    <details style="margin-top:10px"><summary style="cursor:pointer;font-size:13px">Ver la lista de obras excluidas</summary><div class="tabla-scroll" style="max-height:420px;margin-top:8px"><table id="t-excluidas-lista"></table></div></details>
  </div>
  <div class="flujo" id="flujo"></div>
  <div class="tarjeta" style="margin-top:16px"><h2>Auditoría de calidad del CSV único</h2><p class="sub">Los errores detienen el pipeline; los avisos se explican en Límites</p><table id="t-calidad"></table></div>
  <div class="tarjeta" style="margin-top:16px"><h2>Comprobaciones del producto final</h2><p class="sub" id="resumen-validacion"></p><div class="tabla-scroll"><table id="t-validacion"></table></div></div>
</section>

<section class="pestana" id="p-limites">
  <div class="tarjeta texto-limites"><h2>Límites y calidad del dato</h2><!--LIMITES--></div>
</section>
</main>
<aside class="lateral" id="kpis"></aside>
</div>
</div>

<script>const ARCHIVOS = /*ARCHIVOS*/;
async function descargar(clave) {
  // los CSV van dentro del HTML (gzip + base64) para que la descarga funcione aunque el tablero se abra fuera del proyecto
  const a = ARCHIVOS[clave];
  try {
    const bytes = Uint8Array.from(atob(a.datos), c => c.charCodeAt(0));
    const blob = await new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))).blob();
    const url = URL.createObjectURL(new Blob([blob], {type: "text/csv;charset=utf-8"}));
    const enlace = document.createElement("a"); enlace.href = url; enlace.download = a.nombre;
    document.body.appendChild(enlace); enlace.click(); enlace.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (e) { alert("Este navegador no pudo preparar la descarga. El archivo está en el proyecto: " + a.ruta); }
}
</script>
<script>window.PlotlyGeoAssets = {topojson: /*TOPOJSON*/};</script>
<script>/*PLOTLY*/</script>
<script>
const D = /*DATOS*/;
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const ETIQ_TIPO = {educacion_basica: "Educación básica (colegios)", educacion_superior: "Educación superior", deportiva_recreativa: "Deportiva y recreativa", cultural_patrimonio: "Cultural y patrimonio", otra: "Otra"};
const ETIQ_MACRO = {financiera: "Financiera", contractual_y_legal: "Contractual y legal", tecnica: "Técnica", logistica: "Logística", fuerza_mayor: "Fuerza mayor", entorno_social_y_territorial: "Entorno social y territorial", sin_causa_de_paralizacion: "Sin causa de paralización", sin_clasificar: "Sin clasificar"};
const COLOR_CAUSA = {contractual_y_legal: "--series-1", financiera: "--series-2", tecnica: "--series-3"};
const colorCausa = k => css(COLOR_CAUSA[k] || "--other");
const etq = (m, k) => m[k] || (k ? k.replaceAll("_", " ") : "—");
const fmt = (x, d = 0) => (x === null || x === undefined || isNaN(x)) ? "—" : Number(x).toLocaleString("es-PE", {maximumFractionDigits: d, minimumFractionDigits: d});
const soles = x => (x === null || x === undefined || isNaN(x)) ? "—" : "S/ " + fmt(x / 1e6, 1) + " mill.";
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
document.getElementById("cobertura").textContent = D.cobertura;
const ICON = {
  casa: '<path d="M3 11l9-8 9 8"/><path d="M5 9.5V21h5v-6h4v6h5V9.5"/>',
  ranking: '<path d="M3 21h18"/><rect x="4" y="12" width="4" height="9"/><rect x="10" y="6" width="4" height="15"/><rect x="16" y="9" width="4" height="12"/>',
  reloj: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
  pin: '<path d="M12 22s7-7.4 7-13a7 7 0 10-14 0c0 5.6 7 13 7 13z"/><circle cx="12" cy="9" r="2.6"/>',
  alerta: '<path d="M10.3 4l-8 14a2 2 0 001.7 3h16a2 2 0 001.7-3l-8-14a2 2 0 00-3.4 0z"/><path d="M12 9.5v4.5M12 17.5v.01"/>',
  capas: '<path d="M3 6.5l6-3 6 3 6-3v14l-6 3-6-3-6 3z"/><path d="M9 3.5v14M15 6.5v14"/>',
  lista: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2.5h6V4M8.5 10h7M8.5 14h7M8.5 18h4"/>',
  engranes: '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="18" r="3"/><path d="M9 6h5a4 4 0 014 4v5"/><path d="M15 18h-5a4 4 0 01-4-4V9"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.01"/>',
  descarga: '<path d="M7 18a4.5 4.5 0 01-.6-9A6 6 0 0118 8a4 4 0 01-1 10"/><path d="M12 11v9M8.5 16.5L12 20l3.5-3.5"/>',
  libro: '<path d="M4 5a2 2 0 012-2h13v15H6a2 2 0 00-2 2z"/><path d="M4 20a2 2 0 002 2h13v-4M8 7h7M8 11h5"/>',
  base: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  escuela: '<path d="M2.5 10L12 4l9.5 6"/><path d="M5 9v12h14V9M10 21v-5h4v5M12 8.5v2.5"/>',
  monedas: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
};
const ic = k => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICON[k]}</svg>`;
document.querySelectorAll("[data-ic]").forEach(e => e.outerHTML = ic(e.dataset.ic));
const PAGINAS = [
  ["resumen", "Panorama", "reloj", "¿Desde cuándo están paralizadas?", "Cuántas obras de colegios hay con los filtros, cuánto dinero comprometen y en qué año se paralizaron. La línea muestra cómo cambió el total del país en cada informe de la Contraloría.", "#3fb36b", "#fff"],
  ["ranking", "Ranking", "ranking", "Ranking de regiones y distritos", "Regiones y distritos ordenados por número de obras, por monto o por años paralizadas. El color es un semáforo: rojo = sus obras llevan más de 3 años detenidas.", "#f5b915", "#3a2a00"],
  ["mapa", "Mapa", "pin", "¿Dónde están las obras?", "Cada punto es una obra de colegio; su color indica la causa de la paralización. Haga clic en una región para acercarse y ver sus provincias, y en un punto para ver la ficha de la obra. «Borrar filtros» vuelve al Perú completo.", "#f7891f", "#fff"],
  ["causas", "Causas", "alerta", "¿Por qué se paralizaron?", "Las causas se clasificaron leyendo el texto oficial de la Contraloría, los comentarios de INFOBRAS y la problemática del MEF. Problemas de contrato y de dinero son los más comunes.", "#ec5466", "#fff"],
  ["regiones", "Regiones y distritos", "capas", "Regiones, distritos y brechas", "¿Las regiones con más obras paralizadas son las de peor infraestructura y aprendizaje? Elija un indicador. Al elegir una región aparecen todos sus distritos.", "#3fb36b", "#fff"],
  ["obras", "Obras", "lista", "Ficha de cada obra", "Busque una obra por nombre, distrito o código. Haga clic en una fila para ver su ficha completa y el enlace a INFOBRAS.", "#f5b915", "#3a2a00"],
  ["proceso", "Proceso", "engranes", "Cómo se construyó este monitor", "", "#f7891f", "#fff"],
  ["limites", "Límites", "info", "Límites y calidad del dato", "", "#ec5466", "#fff"],
];
document.getElementById("menu-portada").innerHTML = PAGINAS.map(p => `<button style="--bg:${p[5]};--tx:${p[6]}" onclick="mostrar('${p[0]}')">${ic(p[2])}<span>${p[1]}<small>${p[3]}</small></span></button>`).join("");
document.getElementById("nav").innerHTML = PAGINAS.map(p => `<button data-p="${p[0]}">${ic(p[2])}${p[1]}</button>`).join("");
function portada() {
  const hoy = COLEGIOS.filter(o => o.paralizada_hoy), anios = hoy.map(o => o.anios_paralizada).filter(x => x !== null);
  const masDos = hoy.filter(o => o.anios_paralizada > 2).length, de10 = Math.round(10 * masDos / hoy.length);
  document.getElementById("gancho").innerHTML = `<b>${de10} de cada 10</b> colegios con una obra paralizada llevan <b>más de 2 años</b> esperando que se reanude.`;
  const cif = (c, i, v, e) => `<div class="cifra-p" style="--c:${c}">${ic(i)}<div class="v">${v}</div><div class="e">${e}</div></div>`;
  document.getElementById("cifras-portada").innerHTML =
    cif("#f7891f", "escuela", fmt(hoy.length), "obras de colegios paralizadas hoy") + cif("#3fb36b", "pin", fmt(new Set(hoy.map(o => o.ubigeo)).size), "distritos afectados") +
    cif("#f5b915", "monedas", soles(suma(hoy.map(o => o.monto_expediente_tecnico))), "comprometidos (expediente técnico)") + cif("#ec5466", "reloj", fmt(mediana(anios), 1) + " años", "paralizadas (mediana)");
  const segs = [["mapa", ["¿Dónde?"], "#f7891f"], ["ranking", ["¿Cuánto?"], "#f5b915"], ["resumen", ["¿Desde", "cuándo?"], "#3fb36b"], ["causas", ["¿Por qué?"], "#ec5466"]];
  const R = 225, r = 125, cx = 250, cy = 250, pt = (rad, a) => [cx + rad * Math.cos(a), cy + rad * Math.sin(a)];
  document.getElementById("rueda").innerHTML = segs.map((sg, i) => {
    const a0 = -Math.PI / 2 + i * Math.PI / 2 + 0.035, a1 = a0 + Math.PI / 2 - 0.07, m = (a0 + a1) / 2;
    const [x0, y0] = pt(R, a0), [x1, y1] = pt(R, a1), [x2, y2] = pt(r, a1), [x3, y3] = pt(r, a0), [tx, ty] = pt((R + r) / 2, m);
    return `<g class="seg" onclick="mostrar('${sg[0]}')"><path d="M${x0},${y0} A${R},${R} 0 0 1 ${x1},${y1} L${x2},${y2} A${r},${r} 0 0 0 ${x3},${y3} Z" fill="${sg[2]}"/>
      <text x="${tx}" y="${ty - (sg[1].length - 1) * 12}" text-anchor="middle" dominant-baseline="middle" fill="${i === 1 ? "#3a2a00" : "#fff"}" font-size="21" font-weight="700">${sg[1].map((t, k) => `<tspan x="${tx}" dy="${k ? 24 : 0}">${t}</tspan>`).join("")}</text></g>`;
  }).join("") + `<circle cx="250" cy="250" r="112" fill="var(--surface-1)"/>
    <text x="250" y="232" text-anchor="middle" font-size="64" font-weight="800" fill="var(--azul)">${hoy.length}</text>
    <text x="250" y="268" text-anchor="middle" font-size="16" fill="var(--text-secondary)">colegios con obra</text>
    <text x="250" y="290" text-anchor="middle" font-size="16" fill="var(--text-secondary)">paralizada hoy</text>`;
}

// ---------- filtros ----------
const opciones = (id, valores, etiquetas, todas) => {
  const s = document.getElementById(id);
  s.innerHTML = (todas ? `<option value="">${todas}</option>` : "") + valores.map(v => `<option value="${esc(v)}">${esc(etiquetas ? etq(etiquetas, v) : v)}</option>`).join("");
};
const contar = (arr, k) => arr.reduce((m, o) => (m[o[k]] = (m[o[k]] || 0) + 1, m), {});
const porFrecuencia = (arr, k) => Object.entries(contar(arr, k)).sort((a, b) => b[1] - a[1]).map(e => e[0]).filter(v => v && v !== "null");
const anioDe = f => f ? Number(String(f).slice(0, 4)) || null : null;
D.obras.forEach(o => { o.anio_inicio = anioDe(o.fecha_inicio); o.anio_paralizacion = anioDe(o.fecha_paralizacion); o.anios_paralizada = o.dias_desde_paralizacion === null ? null : o.dias_desde_paralizacion / 365.25; });
const COLEGIOS = D.obras.filter(o => o.tipo_infraestructura === "educacion_basica");   // el analisis es solo de colegios
opciones("f-region", [...new Set(COLEGIOS.map(o => o.region_enla))].filter(Boolean).sort(), null, "Todas las regiones");
opciones("f-causa", porFrecuencia(COLEGIOS, "causa_macro"), ETIQ_MACRO, "Todas las causas");
opciones("f-anio", [...new Set(COLEGIOS.map(o => o.anio_paralizacion))].filter(Boolean).sort().reverse().map(String), null, "Todos los años");

function poblarDistritos() {
  const r = document.getElementById("f-region").value, s = document.getElementById("f-distrito");
  if (!r) { s.innerHTML = '<option value="">Elija primero una región</option>'; s.disabled = true; return; }
  const vistos = {}; COLEGIOS.filter(o => o.region_enla === r).forEach(o => vistos[o.ubigeo] = `${o.distrito} (${o.provincia})`);
  s.innerHTML = '<option value="">Todos los distritos con obras</option>' + Object.entries(vistos).sort((a, b) => a[1].localeCompare(b[1])).map(([u, n]) => `<option value="${esc(u)}">${esc(n)}</option>`).join("");
  s.disabled = false;
}
function filtradas(sinRegion = false, sinAnio = false) {
  const e = document.getElementById("f-estado").value, r = document.getElementById("f-region").value, c = document.getElementById("f-causa").value,
        d = sinRegion ? "" : document.getElementById("f-distrito").value, a = sinAnio ? "" : document.getElementById("f-anio").value;
  return COLEGIOS.filter(o => (e === "todas" || (e === "hoy" ? o.paralizada_hoy : !o.paralizada_hoy))
                          && (sinRegion || !r || o.region_enla === r) && (!d || o.ubigeo === d) && (!c || o.causa_macro === c)
                          && (!a || String(o.anio_paralizacion) === a));
}
function elegirRegion(r) { document.getElementById("f-region").value = r; poblarDistritos(); actualizar(); }

// ---------- utilidades de graficos ----------
function base(extra = {}) {
  return Object.assign({
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: {family: "Segoe UI, system-ui, sans-serif", size: 12, color: css("--text-secondary")},
    margin: {l: 50, r: 16, t: 10, b: 40}, hoverlabel: {bgcolor: css("--surface-1"), bordercolor: css("--border"), font: {color: css("--text-primary")}},
    xaxis: {gridcolor: css("--grid"), zeroline: false, linecolor: css("--border")}, yaxis: {gridcolor: css("--grid"), zeroline: false, linecolor: css("--border")},
  }, extra);
}
const CONFIG = {displaylogo: false, responsive: true, locale: "es", modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"]};
const dibujar = (id, trazas, layout) => Plotly.react(id, trazas, base(layout), CONFIG);
function barrasH(id, conteo, etiquetas, titulo, color = "--c-naranja") {
  const pares = Object.entries(conteo).sort((a, b) => a[1] - b[1]);
  dibujar(id, [{type: "bar", orientation: "h", x: pares.map(p => p[1]), y: pares.map(p => etq(etiquetas || {}, p[0])), marker: {color: css(color)},
               text: pares.map(p => p[1]), textposition: "outside", cliponaxis: false, hovertemplate: "%{y}: %{x} obras<extra></extra>"}],
          {margin: {l: 190, r: 40, t: 10, b: 30}, xaxis: {gridcolor: css("--grid"), title: titulo || "Número de obras"}, bargap: 0.35});
}
const mediana = a => { const s = a.filter(x => x !== null && !isNaN(x)).sort((x, y) => x - y); if (!s.length) return null; const m = Math.floor(s.length / 2); return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const suma = a => a.reduce((s, x) => s + (x || 0), 0);

// ---------- Cifras de la derecha ----------
function kpis(obras) {
  const anios = obras.map(o => o.anios_paralizada).filter(x => x !== null), distritos = new Set(obras.map(o => o.ubigeo)).size;
  const masDos = obras.filter(o => o.anios_paralizada > 2).length;
  const kpi = (v, e, c) => `<div class="kpi" style="--c:${c}"><div class="valor">${v}</div><div class="etiqueta">${e}</div></div>`;
  document.getElementById("kpis").innerHTML =
    kpi(fmt(obras.length), "obras de colegios con los filtros", "") + kpi(fmt(distritos), "distritos", "#3fb36b") +
    kpi(soles(suma(obras.map(o => o.monto_expediente_tecnico))), "expediente técnico", "#f5b915") +
    kpi(anios.length ? fmt(mediana(anios), 1) + " años" : "—", anios.length ? "paralizadas (mediana)" : "tiempo paralizada: solo para las paralizadas hoy", "#ec5466") +
    kpi(anios.length ? fmt(masDos) : "—", "llevan más de 2 años paralizadas", "#f7891f");
}

// ---------- Ranking ----------
const semaforo = a => a === null || a === undefined ? css("--other") : a > 3 ? css("--rojo") : a >= 1 ? css("--ambar") : css("--verde");
document.getElementById("leyenda-semaforo").innerHTML = [["--rojo", "Más de 3 años"], ["--ambar", "De 1 a 3 años"], ["--verde", "Menos de 1 año"], ["--other", "Sin dato (no paralizada hoy)"]]
  .map(([c, t]) => `<span><i style="background:var(${c})"></i>${t}</span>`).join("");
function ranking(obras) {
  const met = document.getElementById("f-orden-ranking").value;
  const agrupar = (clave, nombre) => { const g = {}; obras.forEach(o => { const k = o[clave]; g[k] = g[k] || {clave: k, nombre: nombre(o), n: 0, monto: 0, anios: []};
    g[k].n++; g[k].monto += o.monto_expediente_tecnico || 0; if (o.anios_paralizada !== null) g[k].anios.push(o.anios_paralizada); });
    return Object.values(g).map(x => ({...x, med: mediana(x.anios)})); };
  const valor = x => met === "monto" ? x.monto / 1e6 : met === "anios" ? x.med : x.n;
  const titulo = {n: "Número de obras", monto: "Expediente técnico (S/ millones)", anios: "Años paralizada (mediana)"}[met];
  const dib = (id, lista, top, alClic) => {
    const l = lista.filter(x => valor(x) !== null).sort((a, b) => valor(b) - valor(a) || b.n - a.n).slice(0, top).reverse();
    const div = document.getElementById(id); div.style.height = Math.max(300, l.length * 26 + 70) + "px";
    dibujar(id, [{type: "bar", orientation: "h", x: l.map(valor), y: l.map(x => x.nombre), marker: {color: l.map(x => semaforo(x.med))},
      text: l.map(x => fmt(valor(x), met === "n" ? 0 : 1)), textposition: "outside", cliponaxis: false, customdata: l.map(x => x.clave),
      hovertext: l.map(x => `<b>${esc(x.nombre)}</b><br>${x.n} obras · ${soles(x.monto)}<br>${x.med === null ? "Sin obras paralizadas hoy" : "Paralizadas hace " + fmt(x.med, 1) + " años (mediana)"}`),
      hovertemplate: "%{hovertext}<extra></extra>"}],
      {margin: {l: 210, r: 50, t: 6, b: 44}, xaxis: {gridcolor: css("--grid"), title: titulo, rangemode: "tozero"}, yaxis: {automargin: true}, bargap: 0.28});
    if (div.removeAllListeners) div.removeAllListeners("plotly_click");
    div.on("plotly_click", ev => alClic(ev.points[0].customdata));
  };
  dib("g-rank-region", agrupar("region_enla", o => o.region_enla), 26, elegirRegion);
  dib("g-rank-distrito", agrupar("ubigeo", o => `${o.distrito} (${o.region_enla})`), 25, u => {
    const o = COLEGIOS.find(x => x.ubigeo === u); document.getElementById("f-region").value = o.region_enla; poblarDistritos();
    document.getElementById("f-distrito").value = u; mostrar("obras"); });
}

// ---------- Resumen ----------
function resumen(obras) {
  const reg = contar(obras, "region_enla"); const top = Object.fromEntries(Object.entries(reg).sort((a, b) => b[1] - a[1]).slice(0, 12));
  barrasH("g-top-regiones", top, null, null, "--c-naranja");
  barrasAnio("g-anio-paralizacion", filtradas(false, true), "anio_paralizacion", "Año en que se paralizó");
  barrasAnio("g-anio-inicio", obras, "anio_inicio", "Año de inicio de la obra");
}
function barrasAnio(id, obras, campo, titulo) {
  const c = contar(obras.filter(o => o[campo]), campo), anios = Object.keys(c).map(Number).sort((a, b) => a - b);
  const sel = document.getElementById("f-anio").value;
  dibujar(id, [{type: "bar", x: anios, y: anios.map(a => c[a]), text: anios.map(a => c[a]), textposition: "outside", cliponaxis: false,
    marker: {color: anios.map(a => campo === "anio_paralizacion" && sel && String(a) === sel ? css("--c-rojo") : css(campo === "anio_paralizacion" ? "--c-verde" : "--c-amarillo"))},
    hovertemplate: "%{x}: %{y} obras<extra></extra>"}],
    {xaxis: {gridcolor: "rgba(0,0,0,0)", title: titulo, dtick: 1, tickangle: -45}, yaxis: {gridcolor: css("--grid"), title: "Obras", rangemode: "tozero"}, bargap: 0.3, margin: {l: 50, r: 16, t: 20, b: 60}});
  const g = document.getElementById(id);
  if (campo === "anio_paralizacion") { if (g.removeAllListeners) g.removeAllListeners("plotly_click"); g.on("plotly_click", ev => { const f = document.getElementById("f-anio"); f.value = f.value === String(ev.points[0].x) ? "" : String(ev.points[0].x); actualizar(); }); }
}
function serie() {
  const edu = D.serie.filter(s => s.tipo_registro === "pais_educacion_corte").sort((a, b) => a.fecha_corte.localeCompare(b.fecha_corte));
  dibujar("g-serie", [{type: "scatter", mode: "lines+markers", x: edu.map(s => s.fecha_corte), y: edu.map(s => s.n_obras), line: {color: css("--c-rojo"), width: 2.5},
    marker: {size: 8, color: css("--c-rojo"), line: {color: css("--surface-1"), width: 2}},
    customdata: edu.map(s => [s.pct_obras, s.costo_actualizado_soles]),
    hovertemplate: "%{x|%b %Y}: %{y} obras de Educación<br>%{customdata[0]:.1f}% del total del país<br>Costo: S/ %{customdata[1]:,.0f}<extra></extra>"}],
    {yaxis: {gridcolor: css("--grid"), title: "Obras", rangemode: "tozero"}, xaxis: {gridcolor: css("--grid")}, hovermode: "closest"});
}

// ---------- Mapa ----------
// colores del mapa (estilo de los mapas de calles: mar celeste, Peru en verde claro, la region elegida en amarillo)
const MAPA = {mar: "#aadaff", peru: "#d4ecd5", vecinos: "#eeefe9", borde: "#7f948a", elegida: "#fbe7a1", provincia: "#f6d77a", texto: "#3f5247", ciudad: "#1f2d26"};
const titulo = t => t.toLowerCase().replace(/(^|[\s-])\S/g, m => m.toUpperCase());
const depDe = r => r.startsWith("LIMA") ? "LIMA" : r;
function encuadre(features) {
  let x0 = 999, x1 = -999, y0 = 999, y1 = -999;
  const ver = c => { if (typeof c[0] === "number") { x0 = Math.min(x0, c[0]); x1 = Math.max(x1, c[0]); y0 = Math.min(y0, c[1]); y1 = Math.max(y1, c[1]); } else c.forEach(ver); };
  features.forEach(f => ver(f.geometry.coordinates));
  const px = Math.max(0.35, (x1 - x0) * 0.12), py = Math.max(0.35, (y1 - y0) * 0.12);
  return {lon: [x0 - px, x1 + px], lat: [y0 - py, y1 + py]};
}
function llenar(r, div) {
  const w = div.clientWidth || 900, h = div.clientHeight || 760, y = lat => Math.log(Math.tan(Math.PI / 4 + lat * Math.PI / 360));
  const alto = y(r.lat[1]) - y(r.lat[0]), ancho = (r.lon[1] - r.lon[0]) * Math.PI / 180, cx = (r.lon[0] + r.lon[1]) / 2;
  if (ancho / alto < w / h) { const nuevo = alto * w / h * 180 / Math.PI; return {lat: r.lat, lon: [cx - nuevo / 2, cx + nuevo / 2]}; }
  const nuevoAlto = ancho * h / w, cy = (y(r.lat[0]) + y(r.lat[1])) / 2, inv = v => (2 * Math.atan(Math.exp(v)) - Math.PI / 2) * 180 / Math.PI;
  return {lon: r.lon, lat: [inv(cy - nuevoAlto / 2), inv(cy + nuevoAlto / 2)]};
}
function mapa(obras) {
  const macros = Object.keys(COLOR_CAUSA);
  const grupos = [...macros, "otras"], colores = grupos.map(colorCausa);
  const region = document.getElementById("f-region").value, G = D.geo;
  const trazas = [];
  let rango = {lat: [-18.6, 0.2], lon: [-81.6, -68.4]};
  if (G) {
    const nDep = contar(obras, "region_enla"), porDep = {};
    Object.entries(nDep).forEach(([r, n]) => porDep[depDe(r)] = (porDep[depDe(r)] || 0) + n);
    const depSel = region ? depDe(region) : null;
    const feats = G.departamentos.features;
    // 1) regiones del Peru
    trazas.push({type: "choropleth", geojson: G.departamentos, featureidkey: "properties.departamento", locations: feats.map(f => f.properties.departamento),
      z: feats.map(f => f.properties.departamento === depSel ? 1 : 0), zmin: 0, zmax: 1, colorscale: [[0, MAPA.peru], [1, MAPA.elegida]], showscale: false,
      marker: {line: {color: MAPA.borde, width: 1}}, customdata: feats.map(f => porDep[f.properties.departamento] || 0),
      hovertemplate: "<b>%{location}</b><br>%{customdata} obras de colegios con los filtros<extra></extra>", showlegend: false});
    // 2) con una region elegida: sus provincias y zoom
    if (depSel) {
      let provs = G.provincias.features.filter(f => f.properties.departamento === depSel);
      if (region === "LIMA METROPOLITANA") provs = provs.filter(f => f.properties.provincia === "LIMA");
      if (region === "LIMA PROVINCIAS") provs = provs.filter(f => f.properties.provincia !== "LIMA");
      const nProv = contar(obras.filter(o => o.region_enla === region), "provincia");
      trazas.push({type: "choropleth", geojson: {type: "FeatureCollection", features: provs}, featureidkey: "properties.cod", locations: provs.map(f => f.properties.cod),
        z: provs.map(f => nProv[f.properties.provincia] ? 1 : 0), zmin: 0, zmax: 1, colorscale: [[0, MAPA.elegida], [1, MAPA.provincia]], showscale: false,
        marker: {line: {color: "#ffffff", width: 1.6}}, text: provs.map(f => titulo(f.properties.provincia)), customdata: provs.map(f => nProv[f.properties.provincia] || 0),
        hovertemplate: "<b>Provincia de %{text}</b><br>%{customdata} obras de colegios<extra></extra>", showlegend: false});
      const ep = G.etiquetas_prov.filter(e => provs.some(f => f.properties.provincia === e.nombre && f.properties.departamento === e.departamento));
      trazas.push({type: "scattergeo", mode: "text", lon: ep.map(e => e.lon), lat: ep.map(e => e.lat), text: ep.map(e => titulo(e.nombre)),
        textfont: {size: 11, color: "#7a6a2c", family: "Segoe UI, sans-serif"}, hoverinfo: "skip", showlegend: false});
      const callao = region === "LIMA METROPOLITANA" ? G.departamentos.features.filter(f => f.properties.departamento === "CALLAO") : [];
      rango = encuadre([...provs, ...callao]);
    }
    rango = llenar(rango, document.getElementById("g-mapa"));
    // 3) nombres de las regiones (la elegida se nombra por sus provincias)
    const ed = G.etiquetas_dep.filter(e => e.nombre !== depSel && (!depSel || (e.lon > rango.lon[0] && e.lon < rango.lon[1] && e.lat > rango.lat[0] && e.lat < rango.lat[1])));
    trazas.push({type: "scattergeo", mode: "text", lon: ed.map(e => e.lon), lat: ed.map(e => e.lat), text: ed.map(e => e.nombre.replace(" ", "<br>")),
      textfont: {size: depSel ? 13 : 11, color: MAPA.texto, family: "Segoe UI Semibold, Segoe UI, sans-serif"}, hoverinfo: "skip", showlegend: false});
    if (depSel) trazas.push({type: "scattergeo", mode: "text", lon: [(rango.lon[0] + rango.lon[1]) / 2], lat: [rango.lat[1] - (rango.lat[1] - rango.lat[0]) * 0.04],
      text: [`<b>${region}</b>`], textfont: {size: 16, color: MAPA.ciudad}, hoverinfo: "skip", showlegend: false});
    // 4) paises vecinos y el mar
    const fuera = [["ECUADOR", -78.4, -1.2], ["COLOMBIA", -72.6, -0.7], ["BRASIL", -70.1, -7.2], ["BOLIVIA", -68.85, -11.6], ["CHILE", -69.75, -18.45], ["Océano Pacífico", -79.6, -12.8]]
      .filter(([, x, y]) => x > rango.lon[0] && x < rango.lon[1] && y > rango.lat[0] && y < rango.lat[1]);
    trazas.push({type: "scattergeo", mode: "text", lon: fuera.map(f => f[1]), lat: fuera.map(f => f[2]), text: fuera.map(f => f[0].startsWith("Océano") ? `<i>${f[0]}</i>` : f[0]),
      textfont: {size: 12, color: fuera.map(f => f[0].startsWith("Océano") ? "#3b7bbf" : "#8b918c")}, hoverinfo: "skip", showlegend: false});
    // 5) ciudades
    const ci = G.ciudades.filter(c => c.lon > rango.lon[0] && c.lon < rango.lon[1] && c.lat > rango.lat[0] && c.lat < rango.lat[1] && (depSel || c.ciudad === "LIMA"));   // vista del pais: solo Lima; al acercarse, las ciudades
    trazas.push({type: "scattergeo", mode: "markers+text", lon: ci.map(c => c.lon), lat: ci.map(c => c.lat), text: ci.map(c => titulo(c.ciudad)), textposition: "middle right",
      textfont: {size: ci.map(c => c.ciudad === "LIMA" ? 14 : c.capital_region ? 12 : 11), color: MAPA.ciudad},
      marker: {size: ci.map(c => c.ciudad === "LIMA" ? 8 : 6), color: "#ffffff", line: {color: MAPA.ciudad, width: 1.5}}, hovertemplate: "%{text}<extra></extra>", showlegend: false});
  }
  // 6) las obras, coloreadas por causa
  grupos.forEach((g, i) => {
    const sel = obras.filter(o => o.latitud_mapa !== null && (g === "otras" ? !macros.includes(o.causa_macro) : o.causa_macro === g));
    trazas.push({type: "scattergeo", mode: "markers", name: g === "otras" ? "Otras causas" : etq(ETIQ_MACRO, g), lat: sel.map(o => o.latitud_mapa), lon: sel.map(o => o.longitud_mapa),
      marker: {size: region ? 12 : 10, color: colores[i], opacity: 0.92, line: {color: "#ffffff", width: 1.5}, symbol: sel.map(o => o.coordenada_origen === "infobras" ? "circle" : "diamond")},
      text: sel.map(o => `<b>${esc(o.nombre_obra).slice(0, 90)}…</b><br>${esc(o.distrito)}, ${esc(o.provincia)} (${esc(o.region_enla)})<br>Estado: ${esc(o.estado_infobras)}${o.anios_paralizada !== null ? " · paralizada hace " + fmt(o.anios_paralizada, 1) + " años" : ""}<br>Expediente: ${soles(o.monto_expediente_tecnico)}<br>Causa: ${esc(etq(ETIQ_MACRO, o.causa_macro))}${o.coordenada_origen !== "infobras" ? "<br><i>Ubicación aproximada</i>" : ""}`),
      hovertemplate: "%{text}<extra></extra>", customdata: sel.map(o => o.codigo_infobras)});
  });
  dibujar("g-mapa", trazas, {margin: {l: 0, r: 0, t: 0, b: 0}, paper_bgcolor: MAPA.mar,
    legend: {orientation: "h", y: 0.01, yanchor: "bottom", x: 0.01, bgcolor: "rgba(255,255,255,.88)", bordercolor: MAPA.borde, borderwidth: 1, font: {color: "#1f2d26"}},
    geo: {resolution: 50, scope: "south america", fitbounds: false, lataxis: {range: rango.lat}, lonaxis: {range: rango.lon}, projection: {type: "mercator"},
          showcountries: true, countrycolor: "#b9bdb5", countrywidth: 1, showcoastlines: false, showland: true, landcolor: MAPA.vecinos,
          showocean: true, oceancolor: MAPA.mar, showlakes: true, lakecolor: MAPA.mar, showrivers: false, bgcolor: MAPA.mar, showframe: false}});
  const g = document.getElementById("g-mapa");
  if (g.removeAllListeners) g.removeAllListeners("plotly_click");
  g.on("plotly_click", ev => {
    const pt = ev.points[0];
    if (pt.data.type === "choropleth" && pt.data.featureidkey === "properties.departamento") {   // clic en una region: filtrarla
      const r = pt.location === "LIMA" ? "LIMA PROVINCIAS" : pt.location;
      if ([...document.getElementById("f-region").options].some(o => o.value === r)) elegirRegion(r);
      return; }
    if (pt.data.type === "scattergeo" && pt.customdata !== undefined && pt.customdata !== null) { mostrar("obras"); verFicha(pt.customdata); } });
  const porDistrito = {};
  obras.forEach(o => { const k = o.ubigeo; porDistrito[k] = porDistrito[k] || {distrito: o.distrito, provincia: o.provincia, region: o.region_enla, n: 0, monto: 0, anios: []};
    porDistrito[k].n++; porDistrito[k].monto += o.monto_expediente_tecnico || 0; if (o.anios_paralizada !== null) porDistrito[k].anios.push(o.anios_paralizada); });
  const lista = Object.values(porDistrito).sort((a, b) => b.n - a.n || b.monto - a.monto);
  document.getElementById("t-distritos").innerHTML = "<thead><tr><th>Distrito</th><th>Región</th><th class='num'>Obras</th><th class='num'>Expediente</th><th class='num'>Años paralizada (mediana)</th></tr></thead><tbody>" +
    lista.map(d => `<tr data-d="${esc(d.distrito)}"><td>${esc(d.distrito)}<br><small style="color:var(--text-muted)">${esc(d.provincia)}</small></td><td>${esc(d.region)}</td><td class="num">${d.n}</td><td class="num">${soles(d.monto)}</td><td class="num">${d.anios.length ? fmt(mediana(d.anios), 1) : "—"}</td></tr>`).join("") + "</tbody>";
  document.querySelectorAll("#t-distritos tbody tr").forEach(tr => tr.onclick = () => {
    const o = obras.find(x => x.distrito === tr.dataset.d); if (!o) return;
    document.getElementById("f-region").value = o.region_enla; poblarDistritos(); document.getElementById("f-distrito").value = o.ubigeo; mostrar("obras"); });
}

// ---------- Causas ----------
function causas(obras) {
  barrasH("g-causa-macro", contar(obras, "causa_macro"), ETIQ_MACRO, null, "--c-rojo");
  const grupos = {}; Object.entries(contar(obras, "causa_grupo_final")).forEach(([k, v]) => { const t = (k || "").replaceAll("_", " "); grupos[t.charAt(0).toUpperCase() + t.slice(1)] = v; });
  barrasH("g-causa-grupo", grupos, {}, null, "--c-naranja");
}
function causasTiempo() {
  const tot = {}; D.causales.forEach(c => tot[c.causa_macro] = (tot[c.causa_macro] || 0) + c.n_obras);
  const top = Object.keys(COLOR_CAUSA);
  const fechas = [...new Set(D.causales.map(c => c.fecha_corte))].sort();
  const colores = [...top, "otras"].map(colorCausa);
  const trazas = [...top, "otras"].map((g, i) => ({type: "scatter", mode: "lines+markers", name: g === "otras" ? "Otras o sin clasificar" : etq(ETIQ_MACRO, g), x: fechas,
    y: fechas.map(f => suma(D.causales.filter(c => c.fecha_corte === f && (g === "otras" ? !top.includes(c.causa_macro) : c.causa_macro === g)).map(c => c.n_obras))),
    line: {color: colores[i], width: 2}, marker: {size: 8, color: colores[i], line: {color: css("--surface-1"), width: 2}},
    hovertemplate: "%{x|%b %Y}: %{y:,} obras<extra>%{fullData.name}</extra>"}));
  dibujar("g-causa-tiempo", trazas, {yaxis: {gridcolor: css("--grid"), title: "Obras paralizadas", rangemode: "tozero"}, legend: {orientation: "h", y: 1.12, font: {color: css("--text-primary")}}, hovermode: "x unified"});
}

// ---------- Regiones ----------
const INDICADORES = {
  region_enla_4p_lectura_satisfactorio: "ENLA 4.º primaria · Lectura satisfactorio (%)", region_enla_4p_matematica_satisfactorio: "ENLA 4.º primaria · Matemática satisfactorio (%)",
  region_enla_2s_lectura_satisfactorio: "ENLA 2.º secundaria · Lectura satisfactorio (%)", region_enla_2s_matematica_satisfactorio: "ENLA 2.º secundaria · Matemática satisfactorio (%)",
  region_escale_pct_3_servicios: "Locales públicos con agua, desagüe y luz (%)", region_escale_pct_riesgo_estructural: "Locales con riesgo estructural (%)", region_escale_pct_rural: "Locales rurales (%)"};
opciones("f-indicador", Object.keys(INDICADORES), INDICADORES);
function rangos(a) { const idx = a.map((v, i) => [v, i]).sort((x, y) => x[0] - y[0]); const r = Array(a.length); let i = 0;
  while (i < idx.length) { let j = i; while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++; for (let k = i; k <= j; k++) r[idx[k][1]] = (i + j) / 2 + 1; i = j + 1; } return r; }
function spearman(x, y) { const rx = rangos(x), ry = rangos(y), n = x.length, mx = suma(rx) / n, my = suma(ry) / n;
  let a = 0, b = 0, c = 0; for (let i = 0; i < n; i++) { a += (rx[i] - mx) * (ry[i] - my); b += (rx[i] - mx) ** 2; c += (ry[i] - my) ** 2; } return a / Math.sqrt(b * c); }
let ordenRegion = {col: "por100", asc: false};
function regiones() {
  const obras = filtradas(true), conteo = contar(obras, "region_enla"), ind = document.getElementById("f-indicador").value;
  const filas = D.regiones.map(r => ({...r, n: conteo[r.region_enla] || 0, por100: 100 * (conteo[r.region_enla] || 0) / r.region_escale_locales_publicos}));
  const validas = filas.filter(f => f[ind] !== null && !isNaN(f[ind]) && isFinite(f.por100));
  const rho = spearman(validas.map(f => f.por100), validas.map(f => f[ind]));
  document.getElementById("rho").innerHTML = `Correlación de Spearman: <b>${fmt(rho, 2)}</b> (n = ${validas.length} regiones; de −1 a +1)`;
  const sel = document.getElementById("f-region").value;
  const maxX = Math.max(...validas.map(f => f.por100), 0.1);
  dibujar("g-dispersion", [{type: "scatter", mode: "markers+text", x: validas.map(f => f.por100), y: validas.map(f => f[ind]), text: validas.map(f => f.n > 0 ? f.region_enla : ""),
    hovertext: validas.map(f => f.region_enla), textposition: "top center", textfont: {size: 10, color: css("--text-secondary")},
    marker: {size: validas.map(f => f.region_enla === sel ? 14 : 10), color: validas.map(f => f.region_enla === sel ? css("--c-rojo") : css("--c-verde")), line: {color: css("--surface-1"), width: 2}},
    customdata: validas.map(f => [f.n, f.region_escale_locales_publicos]),
    hovertemplate: "<b>%{hovertext}</b><br>%{customdata[0]} obras · %{customdata[1]:,} locales públicos<br>%{x:.2f} obras por 100 locales<br>Indicador: %{y:.1f}<extra></extra>"}],
    {xaxis: {gridcolor: css("--grid"), title: "Obras por cada 100 locales escolares públicos (regiones sin obras: en 0, sin nombre)", range: [-0.04 * maxX, maxX * 1.12]}, yaxis: {gridcolor: css("--grid"), title: INDICADORES[ind]}, margin: {l: 60, r: 20, t: 10, b: 50}});
  const cols = [["region_enla", "Región", 0], ["n", "Obras", 0], ["por100", "Por 100 locales", 2], ["region_escale_pct_3_servicios", "% con 3 servicios", 1],
                ["region_enla_4p_lectura_satisfactorio", "4.º prim. lectura %", 1], ["region_enla_4p_matematica_satisfactorio", "4.º prim. matem. %", 1]];
  const o = ordenRegion; filas.sort((a, b) => { const x = a[o.col], y = b[o.col]; return (typeof x === "string" ? x.localeCompare(y) : (x ?? -1) - (y ?? -1)) * (o.asc ? 1 : -1); });
  document.getElementById("t-regiones").innerHTML = "<thead><tr>" + cols.map(c => `<th class="${c[2] || c[0] === "n" ? "num" : ""}" data-c="${c[0]}">${c[1]}</th>`).join("") + "</tr></thead><tbody>" +
    filas.map(f => "<tr>" + cols.map(c => `<td class="${c[0] === "region_enla" ? "" : "num"}">${c[0] === "region_enla" ? esc(f[c[0]]) : fmt(f[c[0]], c[2])}</td>`).join("") + "</tr>").join("") + "</tbody>";
  document.querySelectorAll("#t-regiones th").forEach(th => th.onclick = () => { ordenRegion = {col: th.dataset.c, asc: ordenRegion.col === th.dataset.c ? !ordenRegion.asc : false}; regiones(); });
  document.querySelectorAll("#t-regiones tbody tr").forEach((tr, i) => tr.onclick = () => elegirRegion(filas[i].region_enla));
  const g = document.getElementById("g-dispersion");
  if (g.removeAllListeners) g.removeAllListeners("plotly_click");
  g.on("plotly_click", ev => elegirRegion(ev.points[0].hovertext));
  distritosRegion(obras, sel);
}
let ordenDistrito = {col: "n", asc: false};
function distritosRegion(obras, region) {
  const tit = document.getElementById("h-distritos-region"), sub = document.getElementById("s-distritos-region"), tab = document.getElementById("t-distritos-region"),
        fte = document.getElementById("f-distritos-region");
  if (!region) {
    tit.textContent = "Distritos de la región"; tab.innerHTML = ""; fte.textContent = "";
    sub.innerHTML = "Elija una región en el filtro de arriba, en la tabla o en el gráfico para ver <b>todos sus distritos</b>, con y sin obras, y su infraestructura escolar.";
    return;
  }
  const n = contar(obras.filter(o => o.region_enla === region), "ubigeo");
  const filas = D.distritos.filter(d => d.region_enla === region).map(d => ({...d, n: n[d.ubigeo] || 0}));
  const con = filas.filter(f => f.n > 0), sin = filas.filter(f => f.n === 0);
  const med = (a, k) => mediana(a.map(f => f[k]));
  tit.textContent = `Distritos de ${region} (${filas.length})`;
  sub.innerHTML = `<b>${con.length}</b> distritos con obras de colegios según los filtros (${fmt(suma(con.map(f => f.n)))} obras). ` +
    `Locales públicos con agua, desagüe y luz (mediana): <b>${fmt(med(con, "pct_3_servicios"), 1)} %</b> en los distritos con obras frente a <b>${fmt(med(sin, "pct_3_servicios"), 1)} %</b> en los demás. ` +
    `Clic en un distrito con obras para verlas.`;
  const o = ordenDistrito;
  filas.sort((a, b) => { const x = a[o.col], y = b[o.col]; return (typeof x === "string" ? x.localeCompare(y) : (x ?? -1) - (y ?? -1)) * (o.asc ? 1 : -1) || b.n - a.n || (a.pct_3_servicios ?? 0) - (b.pct_3_servicios ?? 0); });
  const cols = [["distrito", "Distrito"], ["provincia", "Provincia"], ["n", "Obras", 0], ["n_locales_publicos", "Locales públicos", 0], ["pct_3_servicios", "% con agua, desagüe y luz", 1],
                ["pct_rural", "% rurales", 1], ["pct_riesgo_estructural", "% con riesgo estructural", 1]];
  tab.innerHTML = "<thead><tr>" + cols.map(c => `<th class="${c.length > 2 ? "num" : ""}" data-c="${c[0]}">${c[1]}</th>`).join("") + "</tr></thead><tbody>" +
    filas.map(f => `<tr data-u="${esc(f.ubigeo)}" style="${f.n ? "" : "color:var(--text-muted)"}">` + cols.map(c => c.length > 2 ? `<td class="num">${c[0] === "n" && f.n ? "<b>" + f.n + "</b>" : fmt(f[c[0]], c[2])}</td>` : `<td>${esc(f[c[0]])}</td>`).join("") + "</tr>").join("") + "</tbody>";
  fte.textContent = `Fuente: obras según filtros (INFOBRAS/Contraloría); indicadores de los locales escolares públicos: ESCALE ${D.anio_escale}. En gris, distritos sin obras de colegios con los filtros elegidos.`;
  tab.querySelectorAll("th").forEach(th => th.onclick = () => { ordenDistrito = {col: th.dataset.c, asc: ordenDistrito.col === th.dataset.c ? !ordenDistrito.asc : false}; distritosRegion(obras, region); });
  tab.querySelectorAll("tbody tr").forEach(tr => tr.onclick = () => { if (!n[tr.dataset.u]) return; document.getElementById("f-distrito").value = tr.dataset.u; mostrar("obras"); });
}

// ---------- Obras y ficha ----------
let ordenObras = {col: "dias_desde_paralizacion", asc: false};
function tablaObras(obras) {
  const q = document.getElementById("buscar").value.trim().toLowerCase();
  let lista = q ? obras.filter(o => [o.nombre_obra, o.distrito, o.provincia, o.region_enla, o.codigo_infobras, o.cui, o.entidad].join(" ").toLowerCase().includes(q)) : obras.slice();
  const o = ordenObras; lista.sort((a, b) => { const x = a[o.col], y = b[o.col]; return (typeof x === "string" ? (x || "").localeCompare(y || "") : (x ?? -1) - (y ?? -1)) * (o.asc ? 1 : -1); });
  document.getElementById("n-obras").textContent = `${lista.length} obras`;
  const cols = [["nombre_obra", "Obra"], ["distrito", "Distrito"], ["region_enla", "Región"], ["estado_infobras", "Estado"], ["anio_inicio", "Inicio"], ["fecha_paralizacion", "Paralizada desde"], ["dias_desde_paralizacion", "Años paralizada"],
                ["monto_expediente_tecnico", "Expediente (S/)"], ["causa_macro", "Causa principal"]];
  document.getElementById("t-obras").innerHTML = "<thead><tr>" + cols.map(c => `<th class="${["dias_desde_paralizacion", "monto_expediente_tecnico", "anio_inicio"].includes(c[0]) ? "num" : ""}" data-c="${c[0]}">${c[1]}</th>`).join("") + "</tr></thead><tbody>" +
    lista.slice(0, 500).map(x => `<tr data-id="${esc(x.codigo_infobras)}"><td>${esc(x.nombre_obra).slice(0, 110)}${x.nombre_obra && x.nombre_obra.length > 110 ? "…" : ""}</td><td>${esc(x.distrito)}</td><td>${esc(x.region_enla)}</td><td>${esc(x.estado_infobras)}</td><td class="num">${x.anio_inicio ?? "—"}</td><td>${esc(x.fecha_paralizacion || "—")}</td><td class="num">${x.anios_paralizada === null ? "—" : fmt(x.anios_paralizada, 1)}</td><td class="num">${fmt(x.monto_expediente_tecnico)}</td><td>${esc(etq(ETIQ_MACRO, x.causa_macro))}</td></tr>`).join("") + "</tbody>";
  document.querySelectorAll("#t-obras th").forEach(th => th.onclick = () => { ordenObras = {col: th.dataset.c, asc: ordenObras.col === th.dataset.c ? !ordenObras.asc : false}; tablaObras(filtradas()); });
  document.querySelectorAll("#t-obras tbody tr").forEach(tr => tr.onclick = () => verFicha(tr.dataset.id));
}
function verFicha(id) {
  const o = D.obras.find(x => x.codigo_infobras === id); if (!o) return;
  const filas = [["Código INFOBRAS / CUI", `${esc(o.codigo_infobras)} / ${esc(o.cui)}`], ["Entidad", esc(o.entidad)], ["Ubicación", `${esc(o.distrito)}, ${esc(o.provincia)}, ${esc(o.departamento)} (ubigeo ${esc(o.ubigeo)})`],
    ["Tipo de infraestructura", esc(etq(ETIQ_TIPO, o.tipo_infraestructura))], ["Estado (INFOBRAS, 11-nov-2026)", `<span class="estado">${esc(o.estado_infobras)}</span>`],
    ["Paralizada desde", `${esc(o.fecha_paralizacion || "—")}${o.anios_paralizada !== null ? " · hace " + fmt(o.anios_paralizada, 1) + " años (" + fmt(o.dias_desde_paralizacion) + " días)" : ""} · ${fmt(o.n_tramos_paralizacion)} tramo(s) de paralización`],
    ["Inicio de la obra", esc(o.fecha_inicio || "—")],
    ["Causa principal", `${esc(etq(ETIQ_MACRO, o.causa_macro))} · ${esc((o.causa_grupo_final || "").replaceAll("_", " "))} (fuente: ${esc(o.causa_fuente || "—")})`],
    ["Causal oficial (Contraloría)", esc(o.causal_oficial || "—")], ["Expediente técnico", soles(o.monto_expediente_tecnico)], ["Costo actualizado (Contraloría)", soles(o.costo_actualizado_soles)],
    ["Devengado (MEF)", soles(o.devengado_total_soles)], ["Avance físico", o.avance_fisico_pct === null ? "—" : fmt(o.avance_fisico_pct, 1) + " %"],
    ["Nivel de gobierno / modalidad", `${esc(o.nivel_gobierno || "—")} / ${esc(o.modalidad || "—")}`],
    ["Locales del distrito con 3 servicios (ESCALE)", o.escale_pct_3_servicios === null ? "—" : fmt(o.escale_pct_3_servicios, 1) + " %"],
    ["Alertas de calidad", esc(o.alertas_calidad || "ninguna")], ["Ficha oficial", `<a href="${D.url_ficha}${encodeURIComponent(o.codigo_infobras)}" target="_blank" rel="noopener">Ver en INFOBRAS</a>`]];
  const f = document.getElementById("ficha");
  f.innerHTML = `<h2>${esc(o.nombre_obra)}</h2><dl>${filas.map(r => `<dt>${r[0]}</dt><dd>${r[1]}</dd>`).join("")}</dl>`;
  f.classList.add("visible"); f.scrollIntoView({behavior: "smooth", block: "start"});
}

// ---------- Proceso ----------
function proceso() {
  document.getElementById("generado").textContent = D.generado;
  const total = D.obras.length, colegios = COLEGIOS.length, hoy = COLEGIOS.filter(o => o.paralizada_hoy), distritos = new Set(hoy.map(o => o.ubigeo)).size;
  const p198 = D.obras.filter(o => o.origen === "infobras_paralizada_2026-10-27").length;
  const etapa = (n, titulo, detalle, ancho) => `<div style="margin:6px 0"><div style="display:flex;justify-content:space-between;font-size:13px"><span><b>${titulo}</b> · <span style="color:var(--text-muted)">${detalle}</span></span><b>${fmt(n)}</b></div><div style="height:14px;border-radius:4px;background:var(--c-naranja);width:${ancho}%;opacity:${0.45 + ancho / 180}"></div></div>`;
  document.getElementById("embudo").innerHTML =
    etapa(total, "Obras leídas de INFOBRAS", `${p198} paralizadas al 27-oct + ${total - p198} de la lista de Educación de la Contraloría (jun-2026)`, 100) +
    etapa(colegios, "Obras de colegios (educación básica)", "se excluyen deportivas, culturales, de educación superior y otras", 100 * colegios / total) +
    etapa(hoy.length, "Colegios con la obra paralizada hoy", `estado PARALIZADA en INFOBRAS el 11-nov-2026 · ${distritos} distritos`, 100 * hoy.length / total);
  const excl = D.obras.filter(o => o.tipo_infraestructura !== "educacion_basica"), porTipo = {};
  excl.forEach(o => { porTipo[o.tipo_infraestructura] = porTipo[o.tipo_infraestructura] || {n: 0, hoy: 0}; porTipo[o.tipo_infraestructura].n++; if (o.paralizada_hoy) porTipo[o.tipo_infraestructura].hoy++; });
  document.getElementById("t-excluidas").innerHTML = "<thead><tr><th>Tipo</th><th class='num'>Obras</th><th class='num'>Paralizadas hoy</th></tr></thead><tbody>" +
    Object.entries(porTipo).sort((a, b) => b[1].n - a[1].n).map(([t, v]) => `<tr><td>${esc(etq(ETIQ_TIPO, t))}</td><td class="num">${v.n}</td><td class="num">${v.hoy}</td></tr>`).join("") +
    `<tr><td><b>Total excluidas</b></td><td class="num"><b>${excl.length}</b></td><td class="num"><b>${excl.filter(o => o.paralizada_hoy).length}</b></td></tr></tbody>`;
  document.getElementById("t-excluidas-lista").innerHTML = "<thead><tr><th>Tipo</th><th>Obra</th><th>Región</th><th>Estado</th></tr></thead><tbody>" +
    excl.sort((a, b) => (a.tipo_infraestructura || "").localeCompare(b.tipo_infraestructura || "")).map(o => `<tr><td>${esc(etq(ETIQ_TIPO, o.tipo_infraestructura))}</td><td>${esc(o.nombre_obra)}</td><td>${esc(o.region_enla)}</td><td>${esc(o.estado_infobras)}</td></tr>`).join("") + "</tbody>";
  document.getElementById("flujo").innerHTML = D.proceso.map(p => `<div class="paso"><b>${esc(p.paso)}</b><div class="cifra">${esc(p.cifra)}</div><small>${esc(p.detalle)}</small><small>${esc(p.extra)}</small></div>`).join("");
  const ok = D.validacion.filter(v => String(v.ok) === "True").length;
  document.getElementById("resumen-validacion").innerHTML = `<span class="${ok === D.validacion.length ? "ok" : "no"}">${ok} de ${D.validacion.length} pasan</span>`;
  document.getElementById("t-validacion").innerHTML = "<thead><tr><th>Tabla</th><th>Comprobación</th><th class='num'>Valor</th><th class='num'>Esperado</th><th>Resultado</th></tr></thead><tbody>" +
    D.validacion.map(v => `<tr><td>${esc(v.tabla)}</td><td>${esc(v.comprobacion)}</td><td class="num">${esc(v.valor)}</td><td class="num">${esc(v.esperado)}</td><td>${String(v.ok) === "True" ? '<span class="ok">✓ pasa</span>' : '<span class="no">✗ falla</span>'}</td></tr>`).join("") + "</tbody>";
  document.getElementById("t-calidad").innerHTML = "<thead><tr><th>Nivel</th><th>Tema</th><th>Detalle</th></tr></thead><tbody>" +
    (D.calidad.length ? D.calidad.map(c => `<tr><td>${esc(c.nivel)}</td><td>${esc(c.tema)}</td><td>${esc(c.detalle)}</td></tr>`).join("") : "<tr><td colspan=3>Sin errores ni avisos</td></tr>") + "</tbody>";
}

// ---------- navegacion y actualizacion ----------
let pestana = "inicio";
function mostrar(p) {
  pestana = p;
  const enInicio = p === "inicio";
  document.getElementById("inicio").hidden = !enInicio; document.getElementById("app").hidden = enInicio;
  window.scrollTo(0, 0);
  if (enInicio) return;
  const pg = PAGINAS.find(x => x[0] === p);
  document.getElementById("titulo-pagina").textContent = pg[3];
  document.documentElement.style.setProperty("--acento", pg[5]); document.documentElement.style.setProperty("--acento-tx", pg[6]);
  document.getElementById("explica").textContent = pg[4];
  document.getElementById("cuerpo").classList.toggle("ancho", ["proceso", "limites"].includes(p));
  document.getElementById("pildoras").style.visibility = ["proceso", "limites"].includes(p) ? "hidden" : "visible";
  document.querySelectorAll("nav button").forEach(b => b.classList.toggle("activa", b.dataset.p === p));
  document.querySelectorAll(".pestana").forEach(s => s.classList.toggle("activa", s.id === "p-" + p));
  actualizar();
}
document.querySelectorAll("nav button").forEach(b => b.onclick = () => mostrar(b.dataset.p));
document.querySelectorAll("#pildoras button").forEach(b => b.onclick = () => {
  document.getElementById("f-estado").value = b.dataset.e;
  document.querySelectorAll("#pildoras button").forEach(x => x.classList.toggle("activa", x === b)); actualizar(); });
document.getElementById("borrar").onclick = () => {
  ["f-region", "f-causa", "f-anio"].forEach(id => document.getElementById(id).value = "");
  document.getElementById("buscar").value = ""; poblarDistritos(); document.querySelector('#pildoras button[data-e="hoy"]').click(); };
function actualizar() {
  if (pestana === "inicio") return;
  const obras = filtradas();
  kpis(obras);
  if (pestana === "ranking") ranking(obras);
  document.getElementById("nota-filtro").innerHTML = "Solo obras de <b>colegios</b> (educación básica). INFOBRAS agrupa Educación y Cultura: las obras deportivas, culturales y universitarias se excluyeron (ver <a href='#' onclick='mostrar(\"proceso\");return false'>Proceso</a>).";
  if (pestana === "resumen") { resumen(obras); serie(); }
  if (pestana === "mapa") mapa(obras);
  if (pestana === "causas") { causas(obras); causasTiempo(); }
  if (pestana === "regiones") regiones();
  if (pestana === "obras") tablaObras(obras);
  if (pestana === "proceso") proceso();
  window.dispatchEvent(new Event("resize"));
}
["f-distrito", "f-causa", "f-anio", "f-indicador", "f-orden-ranking"].forEach(id => document.getElementById(id).onchange = actualizar);
document.getElementById("f-region").onchange = () => { poblarDistritos(); actualizar(); };
document.getElementById("buscar").oninput = () => tablaObras(filtradas());
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", actualizar);
portada(); mostrar("inicio");
</script>
</body>
</html>
"""


if __name__ == "__main__":
    construir()
