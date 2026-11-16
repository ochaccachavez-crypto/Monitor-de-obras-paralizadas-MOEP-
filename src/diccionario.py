"""Diccionario de datos de las dos tablas finales (se escribe en docs/diccionario.csv y en los Excel)."""
import pandas as pd

import config
import utils

TABLAS = ("escale_infraestructura", "enla_regiones")
ESCALE = "ESCALE (Censo Educativo): lineal 1, servicios básicos, padrón y edificaciones"
SICRECE = "SICRECE (UMC, MINEDU), acceso público"

# (tabla, columna, tipo, descripción, unidad, fuente, notas)
DICCIONARIO = [
    ("escale_infraestructura", "anio", "entero", "Año del Censo Educativo.", "año", ESCALE, ""),
    ("escale_infraestructura", "ubigeo", "texto de 6 dígitos",
     "Código de ubigeo del distrito (departamento, provincia y distrito).", "código", ESCALE,
     "Es texto para no perder el cero inicial. En Excel, importar la columna como texto (si no, 010101 se ve 10101)."),
    ("escale_infraestructura", "departamento", "texto",
     "Departamento, como viene en la base (mayúsculas y sin tildes).", "texto", ESCALE, "Callao figura como departamento."),
    ("escale_infraestructura", "provincia", "texto", "Provincia, como viene en la base.", "texto", ESCALE, ""),
    ("escale_infraestructura", "distrito", "texto", "Distrito, como viene en la base.", "texto", ESCALE, ""),
    ("escale_infraestructura", "n_locales_publicos", "entero",
     "Locales educativos públicos (de gestión directa o privada), activos en el padrón y que respondieron el censo.",
     "locales", ESCALE,
     "Con pocos locales los porcentajes son muy escalonados: con 2 locales solo pueden dar 0, 50 o 100."),
    ("escale_infraestructura", "n_locales_sin_dato", "entero",
     "De los anteriores, locales de los que no se puede saber si tienen agua, desagüe y electricidad de red pública "
     "(sin respuesta o respuesta ambigua).", "locales", ESCALE,
     "En 2023 son muchos (8,5 % de los locales públicos): es un hueco de la base publicada."),
    ("escale_infraestructura", "pct_3_servicios", "decimal de 0 a 100",
     "Porcentaje de locales con agua, desagüe y electricidad de red pública, calculado solo con los locales con dato.",
     "%", ESCALE,
     "Vacío si ningún local del distrito tiene dato. En 2025 la electricidad «de terceros» también cuenta como red pública (efecto de 0,18 puntos)."),
    ("escale_infraestructura", "pct_sin_3_servicios", "decimal de 0 a 100", "100 menos pct_3_servicios.", "%", ESCALE, ""),
    ("escale_infraestructura", "pct_rural", "decimal de 0 a 100",
     "Porcentaje de locales públicos ubicados en zona rural (según el padrón).", "%", ESCALE, ""),
    ("escale_infraestructura", "n_locales_con_dato_edif", "entero",
     "Locales públicos con al menos una edificación en uso que respondió la pregunta de riesgo estructural. "
     "Es la base de las dos columnas siguientes.", "locales", ESCALE, ""),
    ("escale_infraestructura", "pct_riesgo_estructural", "decimal de 0 a 100",
     "Porcentaje de esos locales con al menos una edificación en uso que declara riesgo de colapso o riesgo estructural.",
     "%", ESCALE,
     "2024 no es comparable con los otros años (se declara mucho menos). Vacío si no hay locales con dato."),
    ("escale_infraestructura", "pct_estructura_mal_estado", "decimal de 0 a 100",
     "Porcentaje de esos locales con al menos una edificación en uso con muros, columnas, vigas o estructura de techos en mal estado.",
     "%", ESCALE,
     "No equivale a «reparación total»: esa categoría no existe en el censo. Vacío si no hay locales con dato."),
    ("enla_regiones", "region", "texto",
     "Región según la DRE (Dirección Regional de Educación): 23 departamentos sin Lima, Callao, Lima Metropolitana y Lima Provincias (26 en total).",
     "texto", SICRECE,
     "Para unir con la tabla de ESCALE se asume: Lima Metropolitana = departamento LIMA, provincia LIMA; Lima Provincias = el resto de provincias de LIMA."),
    ("enla_regiones", "anio", "entero", "Año de la evaluación.", "año", SICRECE, ""),
    ("enla_regiones", "grado", "texto", "Grado evaluado: «2.° primaria», «4.° primaria», «6.° primaria», «2.° secundaria» o «5.° secundaria».", "texto", SICRECE, ""),
    ("enla_regiones", "evaluacion", "texto", "Tipo de evaluación: MUESTRAL o CENSAL.", "texto", SICRECE,
     "En 2024 el 4.° de primaria es censal (todas las escuelas); los demás años son muestrales: no son estrictamente comparables."),
    ("enla_regiones", "lectura_satisfactorio", "decimal de 0 a 100",
     "Porcentaje de estudiantes en nivel Satisfactorio en Lectura.", "%", SICRECE,
     "Los otros niveles de logro (previo al inicio, en inicio, en proceso) están en los archivos de data/raw/enla."),
    ("enla_regiones", "matematica_satisfactorio", "decimal de 0 a 100",
     "Porcentaje de estudiantes en nivel Satisfactorio en Matemática.", "%", SICRECE,
     "Los otros niveles de logro están en los archivos de data/raw/enla."),
]


def construir_diccionario():
    """Devuelve el diccionario como tabla; los años de cada columna se calculan con los datos de data/processed."""
    tablas = {}
    for nombre in TABLAS:
        ruta = config.PROCESSED / f"{nombre}.csv"
        if ruta.exists():
            tablas[nombre] = pd.read_csv(ruta, dtype={"ubigeo": str})
    filas = []
    for tabla, columna, tipo, descripcion, unidad, fuente, notas in DICCIONARIO:
        df = tablas.get(tabla)
        anios = ""
        if df is not None and columna in df:
            anios = ", ".join(str(a) for a in sorted(df.loc[df[columna].notna(), "anio"].unique()))
        filas.append({"tabla": tabla, "columna": columna, "tipo": tipo, "descripcion": descripcion,
                      "unidad": unidad, "fuente": fuente, "anios": anios, "notas": notas})
    return pd.DataFrame(filas)


def escribir_diccionario():
    """Escribe docs/diccionario.csv y devuelve la tabla."""
    import diccionario_pdf   # las tablas del proyecto PDF/INFOBRAS se agregan al mismo diccionario
    tabla = pd.concat([construir_diccionario(), diccionario_pdf.construir_diccionario_pdf()], ignore_index=True)
    ruta = config.DOCS / "diccionario.csv"
    tabla.to_csv(ruta, index=False, encoding="utf-8-sig")
    utils.log(f"DICCIONARIO: escrito {ruta.name} ({len(tabla)} columnas)")
    return tabla
