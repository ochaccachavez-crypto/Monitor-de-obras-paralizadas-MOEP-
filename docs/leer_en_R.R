# =====================================================================
# Lee en R el CSV unico del dashboard: data/final/dashboard_obras.csv
#
#  - Una sola tabla en formato largo. La columna `tipo_registro` dice que representa cada fila:
#      obra_infobras, obra_corte_contraloria, departamento_corte, pais_total_corte,
#      pais_educacion_corte, causal_corte, contexto_region
#    Hay que filtrar por ella en cada grafico (si no, se mezclan niveles distintos).
#  - Los codigos (cod_departamento, ubigeo, codigo_infobras, cui) se leen como TEXTO para no perder ceros.
#  - Cada columna lleva su descripcion en el atributo "label" (RStudio la muestra en View()).
#
# USO: abrir en RStudio y pulsar "Source" (o ejecutar todo con Ctrl+Shift+Enter).
#      Funciona aunque el directorio de trabajo sea otro: busca solo la carpeta del proyecto.
#      Si no la encuentra, escribe su ruta en RAIZ_MANUAL (por ejemplo "C:/data_analytic").
# =====================================================================
RAIZ_MANUAL <- ""

if (!requireNamespace("readr", quietly = TRUE)) install.packages("readr")
library(readr)

ARCHIVO <- file.path("data", "final", "dashboard_obras.csv")
raiz <- local({
  candidatas <- character(0)
  # 1) carpeta de este archivo (cuando se ejecuta con Source o Rscript)
  f <- sub("^--file=", "", grep("^--file=", commandArgs(FALSE), value = TRUE))
  if (!length(f)) f <- tryCatch(sys.frame(1)$ofile, error = function(e) NULL)
  if (length(f) && !is.null(f)) candidatas <- c(candidatas, dirname(normalizePath(f, winslash = "/")), file.path(dirname(normalizePath(f, winslash = "/")), ".."))
  # 2) archivo abierto en RStudio (cuando se ejecuta linea por linea)
  ruta_rs <- tryCatch(rstudioapi::getSourceEditorContext()$path, error = function(e) "")
  if (length(ruta_rs) && nzchar(ruta_rs)) candidatas <- c(candidatas, dirname(ruta_rs), file.path(dirname(ruta_rs), ".."))
  # 3) directorio de trabajo y sus carpetas superiores
  wd <- getwd()
  candidatas <- c(RAIZ_MANUAL, candidatas, wd, file.path(wd, ".."), file.path(wd, "..", ".."), "C:/data_analytic")
  candidatas <- candidatas[nzchar(candidatas)]
  for (ruta_c in candidatas) {
    if (file.exists(file.path(ruta_c, ARCHIVO))) return(normalizePath(ruta_c, winslash = "/"))
  }
  stop("No encuentro ", ARCHIVO, ". Escribe la ruta de la carpeta del proyecto en RAIZ_MANUAL (primera linea de codigo del script).")
})
cat("Carpeta del proyecto:", raiz, "\n")

dic <- read_csv(file.path(raiz, "data", "final", "dashboard_obras_diccionario.csv"),
                col_types = cols(.default = col_character()), show_col_types = FALSE)

dashboard <- read_csv(
  file.path(raiz, ARCHIVO),
  col_types = cols(
    .default = col_guess(),
    cod_departamento = col_character(), ubigeo = col_character(), codigo_infobras = col_character(), cui = col_character(),
    escale_codlocal = col_character(),
    fecha_corte = col_date(format = "%Y-%m-%d"), fecha_inicio = col_date(format = "%Y-%m-%d"),
    fecha_fin_prevista = col_date(format = "%Y-%m-%d"), fecha_paralizacion = col_date(format = "%Y-%m-%d"),
    paralizada_hoy = col_logical(), en_ultimo_corte_contraloria = col_logical(), educacion_corregida = col_logical()
  ),
  locale = locale(encoding = "UTF-8")
)
for (i in seq_len(nrow(dic))) {
  if (dic$columna[i] %in% names(dashboard)) attr(dashboard[[dic$columna[i]]], "label") <- dic$descripcion[i]
}

cat("dashboard_obras:", nrow(dashboard), "filas x", ncol(dashboard), "columnas\n")
print(table(dashboard$tipo_registro))

# Ejemplos: obras paralizadas hoy por macro-categoria de causa, y Educacion en el pais por corte
obras <- dashboard[dashboard$tipo_registro == "obra_infobras" & dashboard$paralizada_hoy %in% TRUE, ]
print(sort(table(obras$causa_macro), decreasing = TRUE))
pais <- dashboard[dashboard$tipo_registro == "pais_educacion_corte", c("fecha_corte", "n_obras", "pct_obras")]
print(tail(pais))

# ---------------------------------------------------------------------
# Datos de ESCALE (Censo Educativo) completos. Estan aparte del CSV unico:
#   escale_infraestructura : un distrito por fila y anio (2022-2025)
#   escale_distrito_ampliado : 16 indicadores mas por distrito (Censo 2025): internet, agua y luz todos los dias, rampas, antiguedad, estado de techos...
#   escale_obras_en_local  : locales que declaran estar en construccion en 2025 (con el CUI de la obra si lo informaron)
#   catalogo_escale        : las 331 variables de los archivos de ESCALE con su descripcion oficial
# Se leen solo si los archivos estan en la carpeta (en el zip de datos vienen incluidos).
# ---------------------------------------------------------------------
leer_si_existe <- function(ruta_relativa, tipos) {
  ruta <- file.path(raiz, ruta_relativa)
  if (!file.exists(ruta)) return(NULL)
  read_csv(ruta, col_types = tipos, locale = locale(encoding = "UTF-8"), show_col_types = FALSE)
}
escale_infraestructura <- leer_si_existe(file.path("data", "processed", "escale_infraestructura.csv"),
                                         cols(.default = col_guess(), ubigeo = col_character()))
escale_obras_en_local <- leer_si_existe(file.path("data", "processed", "escale_obras_en_local.csv"),
                                        cols(.default = col_guess(), ubigeo = col_character(), codlocal = col_character(), cui = col_character()))
escale_distrito_ampliado <- leer_si_existe(file.path("data", "processed", "escale_distrito_ampliado.csv"),
                                           cols(.default = col_guess(), ubigeo = col_character()))
catalogo_escale <- leer_si_existe(file.path("docs", "catalogo_variables_escale.csv"), cols(.default = col_guess()))
# descripcion de cada columna (atributo "label") desde el diccionario general, si esta en la carpeta
dic_general <- leer_si_existe(file.path("docs", "diccionario.csv"), cols(.default = col_character()))
poner_labels <- function(datos, nombre) {
  if (is.null(datos) || is.null(dic_general)) return(datos)
  d <- dic_general[dic_general$tabla == nombre, ]
  for (i in seq_len(nrow(d))) if (d$columna[i] %in% names(datos)) attr(datos[[d$columna[i]]], "label") <- d$descripcion[i]
  datos
}
escale_infraestructura <- poner_labels(escale_infraestructura, "escale_infraestructura")
escale_obras_en_local <- poner_labels(escale_obras_en_local, "escale_obras_en_local")
escale_distrito_ampliado <- poner_labels(escale_distrito_ampliado, "escale_distrito_ampliado")
if (!is.null(escale_infraestructura)) cat("escale_infraestructura:", nrow(escale_infraestructura), "filas (distrito x anio)\n")
if (!is.null(escale_obras_en_local)) cat("escale_obras_en_local:", nrow(escale_obras_en_local), "locales en construccion\n")
if (!is.null(escale_distrito_ampliado)) cat("escale_distrito_ampliado:", nrow(escale_distrito_ampliado), "distritos (16 indicadores, Censo 2025)
")
if (!is.null(catalogo_escale)) cat("catalogo_escale:", nrow(catalogo_escale), "variables\n")

# En RStudio: abre las tablas en pestanas para verlas con claridad
if (interactive() || identical(Sys.getenv("VER_TABLAS"), "1")) {
  View(dashboard, "dashboard_obras")
  View(dic, "diccionario")
  if (!is.null(escale_infraestructura)) View(escale_infraestructura, "escale_infraestructura")
  if (!is.null(escale_obras_en_local)) View(escale_obras_en_local, "escale_obras_en_local")
  if (!is.null(escale_distrito_ampliado)) View(escale_distrito_ampliado, "escale_distrito_ampliado")
  if (!is.null(catalogo_escale)) View(catalogo_escale, "catalogo_escale")
}
