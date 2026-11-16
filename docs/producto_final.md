# Producto final: el CSV único para el dashboard

**Archivo:** `data/final/dashboard_obras.csv` (UTF-8, coma, punto decimal, 5,053 filas × 107 columnas).
**Diccionario:** `data/final/dashboard_obras_diccionario.csv` (qué es cada columna y en qué tipos de registro se llena).
Se genera con `python src\pipeline_completo.py` o con el cuaderno `notebooks/proyecto_completo.ipynb`. Es la base del **dashboard HTML** (`resultados/dashboard.html`, paso 10 del pipeline).

## Cómo está armado

Una sola tabla en **formato largo**. La columna **`tipo_registro`** dice qué representa cada fila y **hay que filtrar por ella en cada gráfico**
(si no, se mezclan niveles distintos y se cuenta dos veces: por ejemplo, las obras de `obra_infobras` y las de `obra_corte_contraloria` son fuentes distintas).

| tipo_registro | filas | desde | hasta | qué representa | n_obras significa |
|---|---|---|---|---|---|
| causal_corte | 264 | 2022-06-30 | 2026-06-30 | Causales oficiales de paralización por corte (obras y monto), con su grupo de causa del proyecto | obras con esa causal |
| contexto_region | 26 |  |  | Una fila por región ENLA con los indicadores de ESCALE y ENLA (las obras también los traen en columnas `region_*`) | — |
| departamento_corte | 310 | 2023-09-30 | 2026-06-30 | Educación por departamento y corte (obras y costo ya sumados) | obras del departamento |
| obra_corte_contraloria | 3982 | 2023-09-30 | 2026-06-30 | Una fila por obra de Educación y corte de la Contraloría (anexos Excel, 13 cortes): costo, saldo, avance, causal oficial y su grupo de causa | 1 por obra |
| obra_infobras | 429 | 2026-11-11 | 2026-11-11 | Una fila por obra de Educación/Cultura leída en INFOBRAS (foto de nov-2026), con todos sus datos: ubicación, estado, avance, causa, Contraloría, MEF, ESCALE y ENLA de su región | 1 por obra |
| pais_educacion_corte | 21 | 2022-06-30 | 2026-06-30 | Sector Educación del país por corte, con la cifra corregida con los anexos Excel donde el PDF trae error | obras de Educación del país |
| pais_total_corte | 21 | 2022-06-30 | 2026-06-30 | Total nacional (todos los sectores) por corte, según el informe PDF | obras del país |

Medidas comunes a todos los tipos: **`n_obras`**, **`n_obras_paralizadas`**, **`costo_actualizado_soles`**, **`saldo_inversion_soles`**; dimensiones comunes:
`fecha_corte`, `anio`, `cod_departamento`, `departamento`, `region_enla`, `sector`, `causa_grupo_final`, `causa_macro`.

### Cómo lo usa el dashboard (y cómo usarlo en otra herramienta)
1. Leer `cod_departamento`, `ubigeo`, `codigo_infobras` y `cui` como **texto** (si no, se pierden los ceros).
2. Filtrar siempre por `tipo_registro`. Así lo hace el dashboard:
   * **Mapa, ranking y fichas de obras:** `tipo_registro = obra_infobras` (mapa con `latitud_mapa`/`longitud_mapa`: las de INFOBRAS en 412 obras y una ubicación aproximada de ESCALE en las otras 17, marcada en `coordenada_origen`).
   * **Obras paralizadas hoy por causa:** `obra_infobras` y `paralizada_hoy = TRUE`, sumando `n_obras_paralizadas` por `causa_macro`.
   * **Evolución nacional de Educación:** `pais_educacion_corte` (21 cortes, jun-2022 a jun-2026) y, por departamento, `departamento_corte` (13 cortes).
   * **Causas oficiales en el tiempo:** `causal_corte` por `causa_macro` o `causa_grupo_final`.
   * **Contexto educativo (ESCALE, ENLA) frente a las obras:** columnas `escale_*` (distrito) y `region_*` (región) de las filas `obra_infobras`.
3. En lugar de contar filas, sumar `n_obras` o `n_obras_paralizadas`: así la misma medida funciona en todos los tipos.

## Qué contiene `obra_infobras` (429 obras de Educación/Cultura)

* **Quiénes son:** las 198 obras que INFOBRAS marcaba *Paralizada* el 27-oct-2026 más 231 obras de Educación/Cultura de la lista de la
  Contraloría (jun-2026) que ese día no figuraban paralizadas (`origen`). Estado de cada ficha leído el **11-nov-2026**:

| estado | obras |
|---|---|
| PARALIZADA | 179 |
| EN EJECUCIÓN | 150 |
| FINALIZADO | 95 |
| SIN EJECUCIÓN | 5 |

* **Paralizadas hoy:** 179 obras, expediente técnico total de S/ 765 millones, mediana de 190 días paralizadas.
* **Dónde:** las 429 obras tienen ubigeo (185 exacto, 9 normalizado, 4 manual) y `region_enla`; 412 tienen coordenadas en INFOBRAS y las 17 restantes una aproximada de ESCALE (`coordenada_origen`).
* **Dinero (MEF):** 361 de 414 obras con CUI válido aparecen en el Formato 12-B (devengado, PIM). 15 obras tienen CUI «NO ASOCIADO».
* **Colegio:** 32 obras se vinculan por CUI con un local de ESCALE 2025 que declara estar en construcción (`escale_codlocal`, `escale_n_locales_obra`).
* **Infraestructura del distrito (ESCALE):** 5 indicadores 2022-2025 en la tabla de apoyo y, para 2025, **16 indicadores más** (`escale_pct_internet`, agua y luz todos los días, rampas, red interna, antigüedad, pisos, estado de techos, cobertura y tablero eléctrico, área del terreno).
* **Aprendizajes (ENLA) de la región:** 4.° primaria y 2.° secundaria (último año 2025) más 2.° primaria (2022) y 6.° primaria (2024); `region_enla_*_anio` dice de qué año es cada dato.
* **Control de la Contraloría (anexo 03):** `n_servicios_control` y su desglose (simultáneo, previo, posterior) para las obras que figuran en el anexo de marzo de 2026 (vacío = no figura).
* **Avisos de calidad:** `alertas_calidad` marca con palabras clave lo dudoso que viene de la fuente (sin coordenadas, CUI sin datos en el MEF, devengado mayor al costo, costo 0 en la fuente...). No se corrige ningún valor.

## NLP: por qué se paralizó cada obra

**Entrada:** los comentarios de INFOBRAS de todos los meses paralizados (310 de las 429 obras tienen un comentario útil), la causal oficial de la Contraloría y la problemática del MEF.
**Método** (`src/nlp_causas.py`): normalización del texto → 14 grupos de palabras clave con puntaje por grupo (cada grupo pesa igual: 1 punto + 0.5 por patrón extra, máximo 2) →
negación («no», «sin», «permiten») para clima, conflictos, controversias, pandemia e interferencias → combinación de las tres fuentes con pesos (causal oficial 3, último tramo 2,
MEF 1.5, tramos anteriores 0.5) → causa principal + hasta 2 secundarias → **modelo de apoyo** TF-IDF + regresión logística con `class_weight="balanced"`, solo si las reglas no encuentran nada.
Los grupos de estado (*obra concluida o en marcha*, *sin restricciones*) solo se asignan cuando no hay ninguna causa real.

* Las 13 causales oficiales de la Contraloría caen en el grupo esperado (prueba automática).
* Modelo de apoyo (validación cruzada de 5 pliegues, 10 clases con ≥ 8 ejemplos): macro-F1 = 0.885, exactitud = 0.919. Mide la consistencia con las reglas, no una verdad externa. Detalle por clase en `docs/nlp_causas_metricas.csv`.
* Las reglas resolvieron todas las obras; el modelo no tuvo que intervenir (`causa_metodo = reglas` en las 429 obras). Queda como red de seguridad para textos nuevos.
* Revisión manual de una muestra de 30 obras: 28 coherentes y 2 discutibles (texto de la entidad ambiguo).

Macro-categorías (8, para gráficos):

| causa_macro | obras | paralizadas_hoy | % de las 429 |
|---|---|---|---|
| contractual_y_legal | 155 | 47 | 36.1 |
| financiera | 145 | 70 | 33.8 |
| tecnica | 35 | 17 | 8.2 |
| logistica | 29 | 16 | 6.8 |
| fuerza_mayor | 23 | 8 | 5.4 |
| entorno_social_y_territorial | 18 | 4 | 4.2 |
| sin_causa_de_paralizacion | 12 | 9 | 2.8 |
| sin_clasificar | 12 | 8 | 2.8 |

Causas de las obras paralizadas hoy (14 grupos):

| causa | paralizadas hoy | % |
|---|---|---|
| recursos_financieros | 70 | 39.1 |
| incumplimiento_contractual | 37 | 20.7 |
| expediente_tecnico | 17 | 9.5 |
| materiales_logistica | 16 | 8.9 |
| controversias_arbitraje | 10 | 5.6 |
| clima | 7 | 3.9 |
| otros | 7 | 3.9 |
| obra_concluida_o_en_marcha | 6 | 3.4 |
| sin_restricciones | 3 | 1.7 |
| interferencias | 2 | 1.1 |
| permisos_licencias | 2 | 1.1 |
| pandemia | 1 | 0.6 |
| sin_informacion | 1 | 0.6 |

De dónde sale la causa principal:

| fuente de la causa | obras (de 429) |
|---|---|
| contraloria_causal | 310 |
| infobras_comentario | 83 |
| mef_problema | 24 |
| sin_causa_clara | 12 |

**Sobre el "balance" de las categorías:** no se forzó. Las causas reales están concentradas: *recursos financieros* e *incumplimiento contractual* suman la mayoría, igual que en los datos nacionales de la
Contraloría (incumplimiento 8 010 y recursos financieros 6 791 de ~30 000 registros). Lo que sí se hizo para que ninguna categoría pese de más por un artefacto: puntaje por grupo con tope,
reglas más estrictas (por ejemplo, «avance financiero» ya no cuenta como causa financiera), negación, modelo con pesos por clase y macro-categorías (ninguna supera el 50 %).
`otros` + `sin_informacion` = 12 obras (2.8 %): casi todas tienen como única información la causal oficial «OTROS» o ningún texto.

## Comprobaciones

* `docs/validacion_final.csv`: **41 comprobaciones, 0 fallan** (llaves únicas, ubigeo de 6 dígitos, sumas regionales = totales, series = informes, coordenadas dentro del Perú, tipos de registro del CSV único, macro-F1 del NLP ≥ 0.75, ninguna macro-categoría > 50 %).
* `docs/validacion_pdf.csv`: 248 comprobaciones de los PDF, 1 falla (error del propio informe de jun-2023); `docs/validacion_excel.csv`: 52 comparaciones con los Excel, 4 fuera del 10 % (set-2023 y set-2025: errores del PDF, ya corregidos en la serie).
* `docs/auditoria_calidad.csv`: auditoría del CSV único (estructura, texto, códigos, rangos, fechas, consistencia entre tipos y campos obligatorios): **0 errores** y los avisos que vienen de la fuente. Si apareciera un error, el pipeline se detiene.
* `docs/validacion_anexos_excel.csv`: 914 comprobaciones del panel y las tablas de la Contraloría (56 no pasan; explicadas en `docs/hallazgos_pdf.md`).
* `docs/validacion_infobras_ampliada.csv`: lectura de INFOBRAS de las 429 obras. `docs/auditoria_datos_personales.csv`: **0** nombres de personas en las tablas.

## Límites que hay que decir al presentar

1. **INFOBRAS es una foto** (27-oct y 11-nov-2026). Una obra «paralizada» hoy puede reactivarse mañana; la causa de las 198 se leyó el 27-oct.
2. **La base no coincide con la cifra oficial de la Contraloría dentro del ±10 %:** INFOBRAS (paralizadas el 27-oct) 198 obras contra 341 que lista la Contraloría a jun-2026. Las 110 obras en común coinciden al 100 % en monto y departamento; las poblaciones son distintas.
   De las 231 obras de la Contraloría que INFOBRAS no marcaba paralizadas: hoy {'EN EJECUCIÓN': 130, 'FINALIZADO': 95, 'SIN EJECUCIÓN': 5, 'PARALIZADA': 1}.
3. **Causas:** la causal oficial es la del último corte en que aparece la obra (puede ser antigua) y los comentarios de INFOBRAS son más recientes. Donde ambas dicen algo claro, **solo coinciden en 49 %** (188 obras):
   por eso `causa_confianza` es *alta* únicamente cuando dos fuentes apuntan a la misma causa y `causas_secundarias` conserva la otra. `causa_fuente` dice cuál pesó más.
4. **El panel de la Contraloría empieza en sep-2023** (los cortes anteriores no tienen anexo con base por obra): `primer_corte_censurado` marca 151 obras que ya estaban. Antes de esa fecha solo hay cifras agregadas de los PDF (`pais_*`, `causal_corte`).
5. **Los tipos de registro no se suman entre sí:** `obra_corte_contraloria` y `departamento_corte` describen lo mismo con distinto detalle; `obra_infobras` es otra fuente.
6. **MEF:** el devengado es financiero, no físico; `pct_devengado_del_costo` puede pasar de 100 si los costos no son comparables.
7. **ENLA** es por región (no por UGEL ni distrito): 4.° y 2.° de primaria, 6.° de primaria y 2.° de secundaria; SICRECE no devuelve datos de 5.° de secundaria ni de 6.° de primaria 2022. Lima se parte en Metropolitana y Provincias. **ESCALE:** indicadores por distrito del censo 2025 (la serie 2022-2025 solo tiene 5 indicadores).
8. Series de la Contraloría: en set-2023 y set-2025 el PDF trae mal Educación; `pais_educacion_corte` usa el valor del anexo Excel y lo marca (`educacion_corregida`). 3 obras SIN EJECUCIÓN tienen expediente técnico 0 o vacío en INFOBRAS (dato de origen).

## Cómo reproducir

```
python src\pipeline_completo.py --sin-descarga      (procesa lo que ya está en data/raw; ~5 min)
python src\pipeline_completo.py                     (además consulta ESCALE, ENLA, Contraloría y MEF)
python src\pipeline_completo.py --fuentes infobras  (vuelve a leer INFOBRAS: cambia el listado; usar con cuidado)
```
En VS Code: abrir `notebooks/proyecto_completo.ipynb` (un solo cuaderno que lleva **todo el código adentro**; no necesita la carpeta `src`), elegir el kernel `.venv` y *Run All*. Para leer el CSV en R: `docs/leer_en_R.R`.
Las cinco tablas con las que se arma el CSV único (y un Excel con ellas) quedan en `data/interim/componentes` por si se necesita el detalle.

## Todas las tablas del proyecto

| tabla | fuente | filas | columnas | periodo |
|---|---|---|---|---|
| escale_infraestructura | ESCALE (Censo Educativo) | 7546 | 13 | 2022 a 2025 |
| enla_regiones | SICRECE (MINEDU-UMC) | 234 | 6 | 2022 a 2025 |
| mef_f12b_obras | MEF (Portal de Datos Abiertos) | 3742 | 16 | 2018-05-21 11:22:07 a 2026-11-10 21:41:25 |
| escale_obras_en_local | ESCALE (Censo Educativo 2025) | 923 | 8 | 2025 a 2025 |
| dashboard_obras | PRODUCTO FINAL | 5053 | 107 | 2022-06-30 a 2026-11-11 |
| obras_maestra | PRODUCTO FINAL | 429 | 90 | 2026-11-11 |
| resumen_region | PRODUCTO FINAL | 26 | 44 | 2025 |
| serie_pais_educacion | PRODUCTO FINAL | 21 | 12 | 2022-06-30 a 2026-06-30 |
| serie_educacion_departamento | PRODUCTO FINAL | 310 | 9 | 2023-09-30 a 2026-06-30 |
| causales_por_corte | PRODUCTO FINAL | 264 | 11 | 2022-06-30 a 2026-06-30 |
| enla_niveles_logro | SICRECE (MINEDU-UMC) | 468 | 12 | 2022 a 2025 |
| enla_pdf | PDF de la EM 2022 (MINEDU-UMC) | 208 | 9 | 2019 a 2022 |
| fichas_infobras | INFOBRAS (Contraloria) | 198 | 37 | 2026-10-27 |
| cifras_oficiales_contraloria | Informes de obras paralizadas (Contraloria) | 686 | 21 | 2022-06-30 a 2026-06-30 |
| contraloria_causales | Informes de obras paralizadas (Contraloria) | 264 | 12 | 2022-06-30 a 2026-06-30 |
| contraloria_distribuciones | Informes de obras paralizadas (Contraloria) | 415 | 13 | 2022-06-30 a 2026-06-30 |
| contraloria_educacion_departamento | Anexos Excel (Contraloria) | 310 | 10 | 2023-09-30 a 2026-06-30 |
| contraloria_obras_corte | Anexos Excel (Contraloria) | 30348 | 27 | 2023-09-30 a 2026-06-30 |
| contraloria_obras_panel | Anexos Excel (Contraloria) | 5020 | 32 | 2023-09-30 a 2026-06-30 |
| contraloria_pim | Informes de obras paralizadas (Contraloria) | 104 | 18 | 2025-09-30 a 2026-06-30 |
| contraloria_modalidad_ejecucion | Informes de obras paralizadas (Contraloria) | 556 | 13 | 2023-02-28 a 2026-06-30 |
| contraloria_evento_infobras | Informes de obras paralizadas (Contraloria) | 208 | 13 | 2023-02-28 a 2026-06-30 |
| contraloria_servicios_control_total | Informes de obras paralizadas (Contraloria) | 63 | 8 | 2022-06-30 a 2026-06-30 |
| contraloria_servicios_control_nivel_gobierno | Informes de obras paralizadas (Contraloria) | 252 | 10 | 2022-06-30 a 2026-06-30 |
| contraloria_servicios_control_departamento | Informes de obras paralizadas (Contraloria) | 450 | 11 | 2023-02-28 a 2026-06-30 |
| contraloria_principales_obras | Anexos Excel (Contraloria) | 5954 | 18 | 2023-09-30 a 2026-03-31 |
| citas_educacion | Informes de obras paralizadas (Contraloria) | 10 | 6 | 2022-09-30 a 2025-03-31 |
| frecuencia_terminos | Informes de obras paralizadas (Contraloria) | 400 | 6 | 2022 a 2026 |
| infobras_avances | INFOBRAS (Contraloria) | 12858 | 10 | 2010 a 2026 |
| infobras_paralizaciones | INFOBRAS (Contraloria) | 8739 | 17 | 2010 a 2026 |
| infobras_fichas_ampliadas | INFOBRAS (Contraloria) | 429 | 34 | 2026-11-11 |

## Tipo de infraestructura y dashboard en HTML (14-nov-2026)
- `tipo_infraestructura` (en `obras_maestra` y en las filas `obra_infobras` del CSV único): educacion_basica, educacion_superior, deportiva_recreativa, cultural_patrimonio u otra, según reglas sobre el nombre de la obra (y el tipo de obra de INFOBRAS si el nombre no lo dice). Para el objetivo del proyecto (colegios) filtrar `educacion_basica`: 188 obras, 75 paralizadas hoy en 58 distritos.
- `resultados/dashboard.html` (paso 10 del pipeline, `src/dashboard_html.py`): el tablero del proyecto en un solo archivo, sin internet. Lee solo productos ya validados.
