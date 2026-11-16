**Contenido**

1. [Ejecución del proyecto](#ejecucion)
2. [Fuentes de datos](#fuentes)
3. [Preparación de datos](#preparacion)
4. [Validación](#validacion)
5. [Resultados: CSV y dashboard](#resultados)
6. [Limitaciones](#limitaciones)
7. [Uso de inteligencia artificial](#uso-ia)

---


<a id="ejecucion"></a>
## 1. Ejecución del proyecto

**Lo que se necesita:** Windows, Python 3.12 o superior y VS Code con la extensión Jupyter.

1. Descargar el repositorio: botón verde **Code** y luego **Download ZIP**.
2. Descomprimir el ZIP. Hay una carpeta dentro de otra con el mismo nombre; hay que usar la de adentro, la que tiene `ejecutar.bat`.
3. En el explorador de archivos, entrar a esa carpeta, hacer clic en la barra de direcciones (donde sale la ruta), escribir `cmd` y dar Enter.
4. En la consola que se abre escribir `ejecutar.bat --sin-descarga`. La primera vez crea el entorno `.venv` e instala las librerías, así que demora unos minutos.
5. Abrir la carpeta en VS Code y abrir el cuaderno [notebooks/proyecto_completo.ipynb](notebooks/proyecto_completo.ipynb).
6. Arriba a la derecha, en **Select Kernel**, elegir **Python Environments** y luego `.venv`.
7. Darle a **Run All**. Demora alrededor de un minuto. Al terminar se crea el dashboard en `resultados/dashboard.html` y se abre solo en el navegador.

Tambien hay una opción larga, que es realizarlo de cero, lo cual de debe correr `ejecutar.bat` sin `--sin-descarga`. Para esto se necesita Google Chrome, internet y unos 3 GB libres. Las descargas se hacen con un navegador visible y con pausas, así que demora bastante.

<a id="fuentes"></a>
## 2. Fuentes de datos

| Fuente | Uso | Nivel |
|---|---|---|
| ESCALE (Censo Educativo, MINEDU) | Servicios básicos, ruralidad y estado de los locales públicos | Distrito |
| ENLA (SICRECE, UMC) | Porcentaje de estudiantes en nivel satisfactorio | Región |
| Contraloría (informes PDF y anexos Excel) | Cifras oficiales de obras paralizadas, causales y datos por obra | Corte y obra |
| INFOBRAS | Estado, avance, comentarios y coordenadas de cada obra | Obra |
| MEF (Formato 12-B) | Gasto devengado y presupuesto por CUI | Obra |

Las descargas se automatizaron con Selenium. Se respetó el `robots.txt` de cada portal, se dejaron pausas entre descargas y no se descargó en paralelo. Por esa razón no se usó el repositorio institucional del MINEDU, que no permite bots. De SICRECE se usó el acceso público. Cada archivo descargado está registrado en [docs/registro_fuentes.csv](docs/registro_fuentes.csv).

<a id="preparacion"></a>
## 3. Preparación de datos

- **ESCALE:** Se consideró local público al que tiene al menos un servicio de gestión pública en el padrón del año. Los porcentajes se calcularon solo sobre los locales que tienen dato. Como el censo no registra "reparación total", se usaron el riesgo estructural y la estructura en mal estado de las edificaciones.
- **ENLA:** Se trabajó con 26 regiones (Lima Metropolitana, Lima Provincias y Callao por separado) y se separó la evaluación muestral de la censal.
- **Ubicación de las obras:** El ubigeo se asignó comparando nombres de lugares con ESCALE. Los casos dudosos se revisaron a mano ([docs/nombres_sin_ubigeo.csv](docs/nombres_sin_ubigeo.csv)). El cruce con el MEF se hizo por CUI.
- **Tipo de obra:** INFOBRAS junta Educación y Cultura, así que cada obra se clasificó en educación básica, educación superior, deportiva, cultural u otra. El dashboard muestra solo las de educación básica (colegios).
- **Causas de paralización:** Se clasificaron con reglas de palabras clave, los comentarios de INFOBRAS y los datos del MEF. Además se entrenó un modelo de apoyo para medir qué tan consistentes son esas reglas ([docs/nlp_causas_metricas.csv](docs/nlp_causas_metricas.csv)).
- Los nombres de lugares están en mayúsculas y sin tildes, y los códigos (ubigeo, CUI) se guardan como texto para no perder los ceros.

Lo que significa cada columna está en [docs/diccionario.csv](docs/diccionario.csv).

<a id="validacion"></a>
## 4. Validación

- Las cifras sacadas de los PDF de la Contraloría se compararon con los anexos del Excel de la misma Contraloría ([validacion_pdf](docs/validacion_pdf.csv), [validacion_excel](docs/validacion_excel.csv), [validacion_anexos_excel](docs/validacion_anexos_excel.csv)).
- La lectura de INFOBRAS se comparó con la lista oficial de obras ([validacion_infobras](docs/validacion_infobras.csv)).
- Cuando se encontraron errores en los propios informes oficiales como rótulos cruzados o totales copiados, se marcó en vez de corregirlos. Donde hay anexo Excel, se usa la cifra del Excel.
- El producto final pasa 46 comprobaciones automáticas sin fallos ([validacion_final](docs/validacion_final.csv)).
- La auditoría de calidad no encontró errores, solo 3 avisos ([auditoria_calidad](docs/auditoria_calidad.csv)), y la auditoría de datos personales no encontró ninguno ([auditoria_datos_personales](docs/auditoria_datos_personales.csv)). Si alguna de las dos encuentra un problema, el proceso se detiene.

<a id="resultados"></a>
## 5. Resultados: CSV y dashboard

**CSV final:** [data/final/dashboard_obras.csv](data/final/dashboard_obras.csv), con su [diccionario](data/final/dashboard_obras_diccionario.csv). Tiene 5 053 filas en formato largo: la columna `tipo_registro` indica qué es cada fila (obras de INFOBRAS, obras de la Contraloría, series por departamento y del país, causales y contexto por región). Por eso se tiene que filtrar siempre por `tipo_registro` antes de sumar.

**Dashboard:** se genera en `resultados/dashboard.html` al correr el cuaderno. Es un solo archivo que funciona sin internet y tiene estas páginas:

- **Panorama:** Desde cuándo están paralizadas las obras, año por año.
- **Ranking:** Regiones y distritos con más obras paralizadas.
- **Mapa:** ubicación de cada obra, con filtros por región, distrito, causa y año.
- **Causas:** Por qué se paralizaron.
- **Regiones y distritos:** Obras paralizadas junto con datos de ESCALE y ENLA.
- **Obras:** Ficha de cada obra.
- **Proceso:** Los pasos que se siguieron y sus comprobaciones.
- **Límites:** Lo que los datos no permiten afirmar.

<a id="limitaciones"></a>
## 6. Limitaciones

- INFOBRAS y la lista de la Contraloría no cuentan las mismas obras, por eso se usó la unión de ambas.
- INFOBRAS muestra el estado de las obras en el momento en que se consultó, y cada fuente tiene una fecha distinta.
- La Contraloría tiene datos por obra recién desde septiembre de 2023.
- ENLA solo está disponible por región y algunas consultas no respondieron.
- Algunos indicadores de ESCALE solo existen para 2025.
- Algunas obras tienen coordenadas aproximadas; están marcadas en la columna `coordenada_origen`.
- Que una zona tenga más obras paralizadas y peores resultados no prueba que una cosa cause la otra lo cual son asociaciones.

<a id="uso-ia"></a>
## 8. Uso de inteligencia artificial

En el desarrollo usamos una herramienta de IA como apoyo para programar. Qué límites se puso, que decidió el equipo y cómo se comprobó el trabajo, lo cual está explicado en [Supervision de IA.md](Supervision%20de%20IA.md).
