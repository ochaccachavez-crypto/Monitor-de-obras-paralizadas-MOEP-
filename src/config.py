"""Configuracion central: rutas, URLs, selectores y parametros. Es el unico lugar a editar."""
from pathlib import Path

# --- Rutas (la raiz se define una sola vez) ---
RAIZ = Path(__file__).resolve().parent.parent   # carpeta del proyecto, donde sea que este (la que contiene src/)
RAW = RAIZ / "data" / "raw"
INTERIM = RAIZ / "data" / "interim"
PROCESSED = RAIZ / "data" / "processed"
FINAL = RAIZ / "data" / "final"                    # ENTREGABLE: el CSV unico para el dashboard (dashboard_obras.csv)
COMPONENTES = RAIZ / "data" / "interim" / "componentes"   # las 5 tablas con las que se arma el CSV unico (uso interno)
DOCS = RAIZ / "docs"
CAPTURAS = DOCS / "capturas"
LOG = DOCS / "log_descargas.txt"
REGISTRO = DOCS / "registro_fuentes.csv"

for carpeta in (RAW / "escale", RAW / "enla", INTERIM, PROCESSED, CAPTURAS):
    carpeta.mkdir(parents=True, exist_ok=True)

# --- Parametros de cortesia con los portales ---
USER_AGENT = "Proyecto academico USMP - Data Analytics"
PAUSA_MIN, PAUSA_MAX = 2, 5      # segundos entre acciones de descarga
REINTENTOS = 3
ESPERA_DESCARGA = 120            # segundos maximos para que termine una descarga
ESPERA_ELEMENTO = 30             # segundos maximos para que aparezca un elemento

ANIO_INICIO = 2022                # primer anio a descargar (se puede cambiar con --anio-inicio)
EXTENSIONES = r"\.(?:zip|pdf|xlsx?|sav|csv|dbf|rar|7z)"   # tipos de archivo que se reconocen en los listados

# --- ESCALE ---
ESCALE_URL_INICIO = "https://escale.minedu.gob.pe/uee"
ESCALE_CARPETA_CENSO = "A. Censo Educativo"     # texto del enlace a la carpeta del censo
ESCALE_SIGUIENTE = "Siguiente"                  # texto del boton de paginacion
ESCALE_BOTON_DESCARGAR = "//a[starts-with(normalize-space(.), 'Descargar (')]"
ESCALE_SELECTOR_ARCHIVOS = "table a"            # enlaces de archivos dentro de la carpeta de un anio
ESCALE_MAX_PAGINAS = 12
# Solo se bajan los archivos necesarios para infraestructura (los nombres cambian cada anio):
ESCALE_PATRONES = {
    "diccionario_local": r"(?i)diccionario.*[ _]LE[ _]",
    "local_lineal": r"(?i)loc(al)?_lineal",
    "servicios_basicos": r"(?i)servicios_basicos|servba",
    "padron_local": r"(?i)^\d+_(padron|padlocal)\.zip",
    "edificaciones": r"(?i)sec400|p401_edific|p53_edific",   # estado de las edificaciones (una fila por edificacion)
}

# --- ESCALE: como se leen los archivos de local en la extraccion ---
# Anios 2022-2024: tabla larga de servicios (una fila por local y servicio; la fila marcada "X" es la predominante)
# NUMERO 1 = red publica en agua, desague y luz (segun el diccionario de cada anio).
ESCALE_SERVICIOS_TABLA = {
    2022: {"zip": r"servicios_basicos", "marca": "TIPO", "cuadros": {"agua": "C202", "desague": "C206", "luz": "C207"}},
    2023: {"zip": r"servba", "marca": "TIPO", "cuadros": {"agua": "C202", "desague": "C206", "luz": "C207"}},
    2024: {"zip": r"servba", "marca": "PREDOMINA", "cuadros": {"agua": "C202", "desague": "C212", "luz": "C216"}},
}
ESCALE_RED_PUBLICA_TABLA = ["1"]
# Anio 2025 en adelante: los servicios son columnas de Loc_Lineal_1 (columna, codigos que cuentan como red publica).
# En luz, el diccionario 2025 llama "Red publica" a 1 (empresa distribuidora) y 2 (terceros).
ESCALE_SERVICIOS_COLUMNAS = {"agua": ("P321", ["1"]), "desague": ("P3212", ["1"]), "luz": ("P3217", ["1", "2"])}
# Archivo lineal 1 de cada anio (el nombre cambia: local_lineal_01 en 2022, loc_lineal_1 despues)
ESCALE_ZIP_LINEAL = r"lineal_0?1[_.]"
ESCALE_ZIP_PADRON = r"padron"
ESCALE_GESTION_PUBLICA = ["1", "2"]      # 1 publica de gestion directa, 2 publica de gestion privada; 3 privada
ESCALE_AREA_RURAL = "2"                  # AREA_CENSO: 1 urbana, 2 rural

# --- CONTRALORIA (gob.pe): informes de obras paralizadas y sus anexos ---
# Ruta de clics: portal -> categoria "Resultados de la Contraloria" -> compendio "Obras paralizadas - Documentos"
CGR_URL_PORTAL = "https://www.gob.pe/contraloria"
CGR_TEXTO_CATEGORIA = "Resultados de la Contraloría"
CGR_TEXTO_COMPENDIO = "Obras paralizadas - Documentos"
CGR_ID_POR_PAGINA = "filter_per_page"      # lista desplegable; asi no se usan las paginas ?sheet= que robots.txt no permite
CGR_OPCION_POR_PAGINA = "100 por página"
CGR_HREF_FICHA = "/informes-publicaciones/"
# Solo se descargan los informes o reportes de obras paralizadas (no infografias ni presentaciones)
CGR_REGEX_INFORME = r"(?i)^(informe|reporte) de obras paralizadas"
CGR_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
             "setiembre": 9, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
CGR_TRIMESTRES = {"i": (3, 31), "ii": (6, 30), "iii": (9, 30), "iv": (12, 31)}   # fin de cada trimestre

# --- INFOBRAS (Contraloria): obras educativas paralizadas ---
INFOBRAS_BASE = "https://infobras.contraloria.gob.pe/InfobrasWeb"
INFOBRAS_URL_BUSCADOR = INFOBRAS_BASE + "/Mapa/Index?search-level=avanzada"
INFOBRAS_ID_NIVEL1 = "ID_ADVANCED_Nivel01"        # lista "Tipo de obra nivel 1"; se espera a que tenga opciones
INFOBRAS_FILTROS = {"ID_ADVANCED_Nivel01": "educaci", "ID_ADVANCED_Estado": "paraliz"}   # id de la lista -> texto de la opcion
INFOBRAS_ID_BOTON_BASICO = "searchBtn"             # boton "Buscar" de la busqueda basica: NO es el de la avanzada
INFOBRAS_ID_EXPORTAR_CSV = "btnExportCSV"
INFOBRAS_FILTROS_TEXTO = "educacion;paralizada"    # se anota en el registro de fuentes
INFOBRAS_FICHAS = INTERIM / "infobras_fichas.jsonl"   # una linea por obra leida (permite retomar si se corta)
INFOBRAS_SALIDA = PROCESSED / "fichas_infobras.csv"
INFOBRAS_DIAS_VIGENCIA = 30   # una ficha leida hace mas dias se vuelve a leer (el estado de la obra cambia)
INFOBRAS_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
                  "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}

# --- ESCALE: estado de las edificaciones (una fila por edificacion; los campos cambian de numero cada anio) ---
# uso = "la edificacion esta en uso"; riesgo = "esta en riesgo de colapso o presenta riesgo estructural";
# estado = estado de conservacion de muros, columnas, vigas y estructura de techos.
ESCALE_ZIP_EDIFICACIONES = r"sec400|p401_edific|p53_edific"
ESCALE_EDIFICACIONES = {
    2022: {"uso": "P401_3", "riesgo": "P401_20", "estado": ["P401_11_1C", "P401_11_2C", "P401_11_3C", "P401_11_4C"]},
    2023: {"uso": "P401_3", "riesgo": "P401_19", "estado": ["P401_10_12", "P401_10_22", "P401_10_32", "P401_10_42"]},
    2024: {"uso": "P401_3", "riesgo": "P401_20", "estado": ["P401_11_12", "P401_11_22", "P401_11_32", "P401_11_42"]},
    2025: {"uso": "P53_3", "riesgo": "P53_20", "estado": ["P53_11_12", "P53_11_22", "P53_11_32", "P53_11_42"]},
}
ESCALE_SI = ["SI", "1"]                 # 2022 usa texto SI/NO; los demas anios 1/2
ESCALE_NO = ["NO", "2"]
ESCALE_ESTADO_MALO = ["03", "MA"]       # 01 Bueno, 02 Regular, 03 Mal estado (2025: BU, RE, MA); 04, 05 y NA = no tiene / no aplica

# --- ENLA: como se leen las tablas regionales de los PDF en la extraccion ---
ENLA_TITULO_TABLA = r"Resultados? regionales seg[uú]n niveles de logro"
ENLA_GRADOS = {("4", "primaria"): "4.° primaria", ("2", "secundaria"): "2.° secundaria"}   # los demas grados no se piden
ENLA_AREAS = {"Lectura": "lectura", "Matemática": "matematica"}
ENLA_REGIONES = ["Amazonas", "Áncash", "Apurímac", "Arequipa", "Ayacucho", "Cajamarca", "Callao", "Cusco",
                 "Huancavelica", "Huánuco", "Ica", "Junín", "La Libertad", "Lambayeque", "Lima Metropolitana",
                 "Lima Provincias", "Loreto", "Madre de Dios", "Moquegua", "Pasco", "Piura", "Puno", "San Martín",
                 "Tacna", "Tumbes", "Ucayali"]   # 23 departamentos sin Lima + Callao + Lima Metropolitana + Lima Provincias = 26

# --- ENLA: SICRECE (acceso publico). Pide un rol antes de entrar; el usuario autorizo "Estudiante de pregrado" ---
SICRECE_URL = "https://sicrece.minedu.gob.pe/#/home"
SICRECE_XPATH_ACCESO_PUBLICO = "//img[contains(@src,'quiensoy-publico')]/ancestor::a[1]"
SICRECE_SELECT_ROL = "app-popuppublico select"
SICRECE_ROL_VALOR = "1"                          # 1 = Estudiante de pregrado
SICRECE_BOTON_INGRESAR = "btnSesion"
SICRECE_PESTANA_BUSQUEDA = "Búsqueda avanzada"
SICRECE_TIPOS = ["MUESTRAL", "CENSAL"]            # tipos de evaluacion a recorrer
# posicion de cada lista desplegable entre las visibles del formulario (los ids mat-input-N cambian)
SICRECE_ORDEN_SELECTS = {"tipo": 0, "anio": 1, "nivel": 2, "grado": 3}
SICRECE_AREAS = ["LECTURA", "MATEMÁTICA"]
SICRECE_AMBITO = "DRE"                           # ambito territorial (una DRE por region); con DRE se desactiva urbana/rural
SICRECE_DRE_TODAS = "TODOS"
SICRECE_BOTON_BUSCAR = "//button[contains(.,'Buscar')]"
# respuesta que el navegador recibe al buscar (cada tipo de evaluacion usa un endpoint distinto)
SICRECE_API_REPORTE = {"MUESTRAL": "reporteGrafico_Publico_EMAmbitos_Nacional_DRE", "CENSAL": "reporteGrafico_Publico_ECE_DRE"}
# (nivel, grado) como aparecen en SICRECE -> etiqueta de grado de enla_regiones.csv
SICRECE_GRADOS = {("PRIMARIA", "SEGUNDO"): "2.° primaria", ("PRIMARIA", "CUARTO"): "4.° primaria", ("PRIMARIA", "SEXTO"): "6.° primaria",
                  ("SECUNDARIA", "SEGUNDO"): "2.° secundaria", ("SECUNDARIA", "QUINTO"): "5.° secundaria"}   # todos los grados que ofrece el portal
# Combinaciones que el menu de SICRECE lista pero cuya consulta nunca devuelve respuesta (3 intentos, 2026-11-12): no se vuelven a pedir
SICRECE_SIN_RESPUESTA = [("MUESTRAL", 2022, "PRIMARIA", "SEXTO"), ("MUESTRAL", 2023, "PRIMARIA", "SEGUNDO"), ("MUESTRAL", 2025, "SECUNDARIA", "QUINTO")]
SICRECE_ESPERA_RESPUESTA = 60

# --- ENLA (UMC). Por HTTPS el certificado esta roto: se usa HTTP ---
ENLA_ORIGEN_HTTP = "http://umc.minedu.gob.pe"   # Chrome bloquea descargas por http salvo que se confie en este origen
ENLA_URL_INICIO = "http://umc.minedu.gob.pe/enla/"
ENLA_REGEX_PAGINA_ANIO = r"/resultados(enla|em)(\d{4})/?$"    # enlaces "Resultados ENLA 2025", "Resultados EM 2022"
ENLA_REGEX_PDF = r"/wp-content/uploads/.*\.pdf$"
ENLA_EXCLUIR = r"(?i)catalogo|infograf|rm_n|_rm_|resoluci"    # catalogo del sitio, infografias y normas
# el HTML puede traer el nombre con tilde literal o codificado (%C3%B3): se prueban las dos formas
ENLA_XPATH_ENLACE_PDF = "//a[contains(@href, '{codificado}') or contains(@href, '{decodificado}')]"


# --- Proyecto PDF: inventario, tablas y texto de los informes ---
LOG_PDF = DOCS / "log_pdf.txt"
INVENTARIO_PDF = DOCS / "inventario_pdf.csv"
CATALOGO_TABLAS = DOCS / "catalogo_tablas.csv"
INTERIM_PDF = INTERIM / "pdf"
EXTENSIONES_DOCUMENTO = (".pdf", ".ppt", ".pptx")
MIN_CARACTERES_PAGINA = 50          # una pagina con menos letras que esto se considera sin texto seleccionable
PAGINAS_PRUEBA_TEXTO = 3            # se prueban las primeras paginas (y una del medio) para saber si el PDF es escaneado

# Departamentos del Peru con su codigo INEI de 2 digitos (el Callao se trata como departamento, como hace la Contraloria)
DEPARTAMENTOS = {
    "AMAZONAS": "01", "ANCASH": "02", "APURIMAC": "03", "AREQUIPA": "04", "AYACUCHO": "05", "CAJAMARCA": "06",
    "CALLAO": "07", "CUSCO": "08", "HUANCAVELICA": "09", "HUANUCO": "10", "ICA": "11", "JUNIN": "12",
    "LA LIBERTAD": "13", "LAMBAYEQUE": "14", "LIMA": "15", "LORETO": "16", "MADRE DE DIOS": "17", "MOQUEGUA": "18",
    "PASCO": "19", "PIURA": "20", "PUNO": "21", "SAN MARTIN": "22", "TACNA": "23", "TUMBES": "24", "UCAYALI": "25",
}
TOLERANCIA_SOLES = 30        # diferencia aceptada entre una suma de filas y el total del informe (los montos vienen redondeados)
UMBRAL_DIFERENCIA_PCT = 10   # diferencia maxima aceptada contra las cifras oficiales (criterio del proyecto)
CIFRAS_OFICIALES = PROCESSED / "cifras_oficiales_contraloria.csv"
CAUSALES_CGR = PROCESSED / "contraloria_causales.csv"
DISTRIBUCIONES_CGR = PROCESSED / "contraloria_distribuciones.csv"


# --- Fase 4 (texto): citas, terminos y grupos de causa por palabras clave ---
CITAS_REGEX = (r"\b(educaci[oó]n|educativ[oa]s?|escuelas?|colegios?|escolar(?:es)?|aulas?|docentes?|estudiantes?|"
               r"ense[ñn]anza|minedu|pronied)\b")
CITAS_MIN_PALABRAS = 7
CITAS_MAX_CARACTERES = 700
TERMINOS_POR_ANIO = 40
STOPWORDS_ES = set("""para como pero este esta estos estas entre sobre desde hasta cuando donde tambien ademas segun cada tiene tienen
puede pueden sido fueron sera seran parte otros otras todo todos todas mismo misma dicho dicha lugar tras ante bajo contra durante
mediante hacia sino porque aunque luego cual cuales quien cuyo cuya cuyos cuyas esto eso aquel aquella ellos ellas nosotros
tanto tanta tantos tantas mayor menor mayores menores primer primera segundo segunda tercer tercera cuatro cinco seis siete ocho
nueve diez anos fecha total cantidad numero nivel niveles forma manera caso casos vez veces asi aun dentro fuera
obras obra paralizadas paralizada paralizacion publicas publica informe informes territorio nacional siguiente cuadro tabla
fuente elaboracion subgerencia seguimiento evaluacion sistema contraloria general republica control entidades entidad""".split())

# Grupos de causa (se prueban en este orden; en empate gana el primero). Los textos se comparan en minusculas y sin tildes.
# Se evitan palabras que aparecen en simples notas de avance ("valorizacion del mes", "costo del expediente tecnico").
CAUSAS_REGLAS = {
    # Cada grupo es una lista de patrones sobre el texto ya normalizado (minusculas, sin tildes). El orden de los grupos desempata.
    "recursos_financieros": [r"recursos? (financier|economic|presupuest)", r"disponibilidad (oportuna |presupuestal |presupuestaria )?de (los )?recursos",
                             r"presupuest", r"financiamiento|falta de financ|problemas? (de )?financier|desabastecimiento financiero", r"liquidez", r"falta de pago|pagos? (de |por )?(las )?valoriza|valorizacion\w* (impaga|pendiente)",
                             r"deuda|adeud", r"\bfondos\b", r"ano fiscal", r"\bpia\b", r"transferencia (de (los )?recursos|financiera|presupuestal)",
                             r"sin (dinero|recursos)|no cuenta con (dinero|recursos)", r"asignacion (presupuest|de recursos)"],
    "incumplimiento_contractual": [r"incumpl", r"abandon", r"resuelt|resolvi|resuelve (el )?contrato|resolucion (total |parcial )?(de|del) contrato",
                                   r"rescin|rescis", r"carta notarial", r"penalidad", r"carta fianza", r"nulidad (de oficio )?del contrato",
                                   r"contratista.{0,30}(no (ejecut|cumpl|present)|retir|desaparec)"],
    "expediente_tecnico": [r"deficienc\w* (en|del) (el )?expediente", r"deficienc\w* tecnic", r"modificacion\w* (al|del) exp", r"mayores metrados",
                           r"observaciones? de caracter tecnico", r"incompatib", r"(elaboracion|elaborando|elabora|aprobacion|actualizacion|evaluacion|observaciones? (al|del)|absolucion de consultas).{0,40}expediente|expediente tecnico de(l)? saldo", r"adicional(es)? de obra|prestacion(es)? adicional|deductivo",
                           r"saldo de obra", r"reformulacion|error(es)? (en|de) (el )?(diseno|expediente|calculo)|vicios? ocultos?|replanteo|cambio de diseno"],
    "controversias_arbitraje": [r"arbitr", r"controversia", r"conciliacion", r"discrepancia", r"litigio", r"judicial", r"denunci", r"procuradur",
                                r"delito", r"investigacion", r"intervencion de (la )?contraloria", r"\bjrd\b|laudo|medida cautelar|demanda|peritaje|fiscalia"],
    "clima": [r"lluvia", r"clima", r"precipitac", r"pluvial", r"huaico", r"huayco", r"inundac", r"friaje", r"nevada", r"granizo", r"fenomeno",
              r"desastre", r"deslizamiento", r"talud", r"estiaje|sismo|terremoto|helada"],
    "conflictos_sociales": [r"conflicto", r"\bparo\b", r"protesta", r"bloqueo", r"huelga", r"dirigente",
                            r"reclamos? (de la |de los )?(poblacion|comunidad|vecinos|pobladores)",
                            r"(comunidad|poblacion|pobladores|vecinos).{0,40}(oposic|impid|reclam|rechaz|no permit)", r"rondas? campesinas?",
                            r"invasion|impedimento\w* (para el )?ingreso|no permiten? el ingreso", r"inseguridad|extorsi|amenaza"],
    "terreno_saneamiento": [r"terreno", r"saneamiento fisico", r"predio", r"posesion", r"propietari", r"expropiacion", r"titularidad|libre disponibilidad",
                            r"liberacion de (area|terreno|predio)|servidumbre|colindante|invasor"],
    "permisos_licencias": [r"licencia", r"permiso", r"autorizacion", r"\bcira\b", r"certificacion (ambiental|arqueologica)|arqueolog|ministerio de cultura",
                           r"factibilidad|conexion electrica"],
    "interferencias": [r"interferencia", r"reubicacion de (redes|postes|servicios)", r"postes|redes? (de agua|de desague|electricas)|linea de alta tension"],
    "materiales_logistica": [r"material(es)?", r"desabastec", r"abastecimiento", r"transporte", r"cemento|fierro|acero|ladrillo|agregado|asfalto",
                             r"combustible", r"insumo", r"adquisicion|proveedor|suministro|equipamiento|mobiliario|maquinaria|transformador|escasez|postores",
                             r"mano de obra"],
    "personal_clave": [r"personal clave", r"(sin|falta de) (residente|supervisor|supervision|inspector)",
                       r"(renuncia|ausencia|reemplazo|cambio)\w* (del|de la) (residente|supervisor|inspector)"],
    "pandemia": [r"covid", r"pandemia", r"emergencia sanitaria", r"coronavirus"],
    # grupos de ESTADO: no son causas; solo se asignan cuando el texto no trae ninguna causa real
    "obra_concluida_o_en_marcha": [r"concluid|culminad|finalizad", r"dentro de lo programado|adelantado|con normalidad|avance normal",
                                   r"liquidacion|liquidad", r"recepcion de (la )?obra|acta de recepcion|recepcionad",
                                   r"ha iniciado (su )?ejecucion|inicio de (la )?ejecucion|reinici|reanud", r"transferencia (del|de la) (proyecto|obra)"],
    "sin_restricciones": [r"\bno\b[^.]{0,40}\b(restriccion|problema|problematica|inconveniente|dificultad)", r"\bsin (restriccion|problema|problematica|inconveniente)",
                          r"\bninguna?\b"],
}
CAUSAS_PRESENCIA = ("clima", "conflictos_sociales", "controversias_arbitraje", "pandemia", "interferencias")   # si la palabra va precedida de «no», «sin» o «permite», no es causa
CAUSAS_ESTADO = ("obra_concluida_o_en_marcha", "sin_restricciones")     # grupos que no son causa de paralizacion
# Macro-categorias para el dashboard (pocas y de tamano comparable): cada grupo de causa pertenece a una sola
CAUSAS_MACRO = {
    "recursos_financieros": "financiera", "incumplimiento_contractual": "contractual_y_legal", "controversias_arbitraje": "contractual_y_legal",
    "expediente_tecnico": "tecnica", "personal_clave": "tecnica", "materiales_logistica": "logistica",
    "conflictos_sociales": "entorno_social_y_territorial", "terreno_saneamiento": "entorno_social_y_territorial",
    "permisos_licencias": "entorno_social_y_territorial", "interferencias": "entorno_social_y_territorial",
    "clima": "fuerza_mayor", "pandemia": "fuerza_mayor",
    "obra_concluida_o_en_marcha": "sin_causa_de_paralizacion", "sin_restricciones": "sin_causa_de_paralizacion",
    "otros": "sin_clasificar", "sin_informacion": "sin_clasificar"}
# Texto que no dice nada de la causa: frases tipicas y palabras vacias. Si solo queda eso, el grupo es 'sin_informacion'.
FRASES_SIN_INFORMACION = [r"no se (reportaron|registraron) comentarios", r"actualizado segun el inventario de obras publicas paralizadas del banco de inversiones",
                          r"catalogo de obra", r"\bninguno\b"]
PALABRAS_SIN_INFORMACION = set("""obra obras proyecto paralizada paralizado paralizadas paralizados paraliza suspendida suspendido suspension
se encuentra encuentran continua continuan esta viene vienen actualmente fecha actual hasta desde presente la el lo los las un una de del
al en por que con a y o es son su sus ya mes dias dia ano anos total el mismo misma estado situacion sin""".split())
CITAS_EDUCACION = PROCESSED / "citas_educacion.csv"
FRECUENCIA_TERMINOS = PROCESSED / "frecuencia_terminos.csv"


# --- INFOBRAS, pasada ampliada (A4 + B1 + B2): una sola lectura de fichas para las tres tareas ---
# No toca infobras_fichas.jsonl ni fichas_infobras.csv (datos del 2026-10-27): todo lo nuevo va en archivos aparte.
INFOBRAS_FILTROS_TODOS = {"ID_ADVANCED_Nivel01": "educaci"}         # A4: Educacion/Cultura con TODOS los estados (sin filtro de estado)
INFOBRAS_FILTROS_TODOS_TEXTO = "educacion;todos_los_estados"
INFOBRAS_NOMBRE_LISTADO_TODOS = "listado_educacion_todos.csv"       # -> infobras_{anio}_listado_educacion_todos_{fecha}.csv
INFOBRAS_AMPLIADAS = INTERIM / "infobras_fichas_ampliadas.jsonl"     # cache: una linea por obra con ficha, avances y paralizaciones
INFOBRAS_COORDENADAS = INTERIM / "infobras_coordenadas.jsonl"      # coordenadas completadas despues (la ficha las carga con retraso)
INFOBRAS_CANDADO = INTERIM / "infobras_navegador.lock"              # impide dos lecturas de INFOBRAS a la vez
# Detalle de los avances paralizados (B2): "todas" lee la pagina de cada mes paralizado; "por_tramo" solo el primer y
# el ultimo mes de cada tramo seguido de meses paralizados (los meses del medio repiten causal y fecha de paralizacion).
INFOBRAS_DETALLE_PARALIZACIONES = "por_tramo"
INFOBRAS_AVANCES = PROCESSED / "infobras_avances.csv"
INFOBRAS_PARALIZACIONES = PROCESSED / "infobras_paralizaciones.csv"
INFOBRAS_FICHAS_AMPLIADAS = PROCESSED / "infobras_fichas_ampliadas.csv"
INFOBRAS_VALIDACION_AMPLIADA = DOCS / "validacion_infobras_ampliada.csv"

# --- MEF (Portal de Datos Abiertos): Formato 12-B de inversiones, con el devengado por CUI ---
MEF_URL_F12B = "https://fs.datosabiertos.mef.gob.pe/datastorefiles/FORMATO_12B.csv"
MEF_URL_F12B_DICCIONARIO = "https://fs.datosabiertos.mef.gob.pe/datastorefiles/F12B_Diccionario.csv"
MEF_FILTROS_TEXTO = "formato_12b"
