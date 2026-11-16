# Supervisión del uso de IA en el proyecto


Este documento resume cómo el equipo usó y supervisó una herramienta de inteligencia artificial durante el proyecto: que límites le puso, que tareas realizó la IA, que decidió el equipo y cómo se comprobaron sus criterios. Las cifras y los resultados de cada verificación están en los archivos enlazados.

**Contenido**

1. [Herramienta y roles](#herramienta)
2. [Límites que el equipo puso a la IA](#limites-ia)
3. [Qué hizo la IA](#que-hizo-ia)
4. [Qué decidió el equipo](#decisiones-equipo)
5. [Cómo se validaron sus criterios](#validacion)
6. [Errores detectados durante la supervisión](#errores)
7. [Límites del resultado](#limites-resultado)
8. [Limitaciones](#limitaciones)
9. [Referencias Bigliográficas](#referencias-bibliograficas)

---

<a id="herramienta"></a>
## 1. Herramienta y roles

Se usó Claude Code; IA desarrollada por la empresa Anthropic, como asistente de programación y extractor de datos, con acceso a los archivos del proyecto, a la terminal y a un navegador. Se evaluaba cada acción que la IA consultaba para realizar para darle la confirmación y continuar. La IA escribió el código y la documentación técnica a pedido del equipo, se revisó y aceptó cada resultado antes de incorporarlo, conocido como el Bounded autonomy.

<a id="limites-ia"></a>
## 2. Límites que el equipo designó a la IA

- No se debía inventar datos, todo tendría que ser recopilado mediante las fuentes, si existía datos faltantes, se debía trabajar con ello previamente avisado.
- Trabajar por fases y detenerse al final de cada una hasta recibir la aprobación del equipo (Batch review).
- Pedir autorización antes de llenar formularios, usar accesos con rol o publicar cualquier archivo (Bounded autonomy).
- Respetar los portales, lo cual da a revisar `robots.txt`, identificarse, hacer pausas entre descargas y no descargar en paralelo.
- No modificar nunca los datos originales descargados.
- No guardar ni publicar datos personales.
- Dejar trazabilidad de cada archivo y de cada cifra extraída.
- Mantener un código sencillo y comentado en español.

<a id="que-hizo-ia"></a>
## 3. Trabajo de la IA

Exploró las páginas webs de ESCALE, ENLA, la Contraloría, INFOBRAS y el MEF, programó las descargas automatizadas y la extracción de tablas de los PDF, propuso las reglas de limpieza y de cálculo de indicadores, diseñó la clasificación de causas de paralización, construyó el CSV único para el tablero ([dashboard_obras.csv](../data/final/dashboard_obras.csv)) con su [diccionario](diccionario.csv), y armó las auditorías automáticas. También revisó las entregas de los integrantes antes de integrarlas al proyecto.

<a id="decisiones-equipo"></a>
## 4. Qué decidió el equipo

- La problemática a resolver, las fuentes a usar y el formato del producto (un solo CSV para el Dashboard).
- Autorizar el acceso público de SICRECE y descartar fuentes que prohíben bots.
- El reparto del trabajo entre los integrantes y la integración de sus entregas.
- Pedir que la clasificación de causas se rehiciera y que no se forzara un equilibrio artificial entre categorías.
- Aceptar que la base no cumpliera el criterio de ±10 % frente a la cifra oficial, en lugar de ajustar el criterio.
- Qué se publica en GitHub y qué no (los datos crudos quedaron fuera por contener datos personales como nombres de los directores, correros y teléfonos).

<a id="validacion"></a>
## 5. Cómo se validaron sus criterios

El equipo no aceptó un resultado solo porque la IA lo diera por terminado, por ello se utilizó el Reasoning probes, la cual se designaron preguntas de control, tales como, "¿los datos son correctos?", "¿cómo lo comprobaste?", "¿cómo se clasifican las causas?", que obligaron a ejecutar pruebas reales, y exigió que cada criterio se comprobara contra una fuente independiente:

- Cifras de los PDF contra los anexos Excel de la Contraloría: [validacion_pdf.csv](validacion_pdf.csv), [validacion_excel.csv](validacion_excel.csv), [validacion_anexos_excel.csv](validacion_anexos_excel.csv), [validacion_b4_excel.csv](validacion_b4_excel.csv).
- Lectura de INFOBRAS contra la lista oficial: [validacion_infobras.csv](validacion_infobras.csv), [validacion_infobras_ampliada.csv](validacion_infobras_ampliada.csv).
- Comprobaciones del producto final: [validacion_final.csv](validacion_final.csv).
- Auditoría de calidad y de datos personales: [auditoria_calidad.csv](auditoria_calidad.csv), [auditoria_datos_personales.csv](auditoria_datos_personales.csv).
- Clasificación de causas, con métricas y una revisión manual de una muestra: [nlp_causas_metricas.csv](nlp_causas_metricas.csv), [muestra_validacion_causas.csv](muestra_validacion_causas.csv).
- Ubicación de las obras revisada caso por caso: [nombres_sin_ubigeo.csv](nombres_sin_ubigeo.csv).
- Origen de cada archivo y de cada tabla extraída: [registro_fuentes.csv](registro_fuentes.csv), [inventario_pdf.csv](inventario_pdf.csv), [catalogo_tablas.csv](catalogo_tablas.csv), [inventario_datos.csv](inventario_datos.csv).

Además, el proyecto se ejecutó en entornos distintos (otra carpeta, una copia limpia y el lenguaje R con [leer_en_R.R](leer_en_R.R)) para confirmar que se obtenía el mismo resultado en otro programa y las entregas de cada integrante se probaron en una copia antes de aplicarlas.

<a id="errores"></a>
## 6. Errores detectados durante la supervisión

La IA cometió errores, y todos se encontraron gracias a la revisión o a las pruebas:

- Se filtraron nombres de personas en comentarios libres; se corrigió con un filtro y una auditoría que detiene el proceso.
- Se perdieron coordenadas por no esperar a que la página terminara de cargar.
- Las primeras reglas de clasificación de causas eran demasiado amplias.
- Hubo inconsistencias de nombres y de códigos (tildes, ceros a la izquierda) que solo aparecieron al abrir los datos en R.
- La IA dio los datos por "listos" antes de auditarlos; la pregunta de control del equipo llevó a encontrar los defectos.

La validación también encontró errores en los propios informes oficiales, que se documentaron sin corregirlos en silencio.

<a id="limites-resultado"></a>
## 7. Límites del resultado

- La base de INFOBRAS y la lista oficial de la Contraloría son poblaciones distintas y no cumplen el criterio de ±10 %.
- INFOBRAS es una foto de un momento puesto que el estado de las obras cambia rápido.
- El modelo de apoyo para las causas solo mide su consistencia con las reglas, no se validó contra un evaluador independiente.
- Algunas consultas de ENLA no respondieron y ciertos indicadores de ESCALE solo existen para el último año.
- Las relaciones entre obras paralizadas, infraestructura y aprendizajes son asociaciones, no efectos causales.

<a id="limitaciones"></a>
## 8. Limitaciones

- Falta de competencias en programación, puesto que el equipo asumió la mayor parte de los códigos como verdaderos, esto debido al poco conocimiento en programación.
- La IA dio los datos descargados como listo sin antes auditarlos, confirmar en suponer esto como correcto solo por pasar las pruebas esta mal.
- En algún momento se llegó a trabajar con los códigos dados por la IA sin revisarlo por costumbre tras muchas aprobaciones seguidas.

<a id="referencias-bibliograficas"></a>
## 9. Referencias Bibliográficas

Franses, P. H. (2025). *Ethics in Econometrics: A Guide to Research Practice*. Cambridge University Press. [https://doi.org/10.1017/9781009428033](https://doi.org/10.1017/9781009428033)

Mitchell, M., Ghosh, A. y Passi, S. (2026). *AI Agents Push Humans Out of the Loop*. arXiv:2608.23642. [https://arxiv.org/abs/2608.23642](https://arxiv.org/abs/2608.23642)
