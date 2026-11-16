# Límites y calidad del dato

Lo que el proyecto **no tiene o no puede afirmar**, con su tamaño. Ningún dato dudoso se corrigió en silencio: se marca en `alertas_calidad` o se explica aquí.

## 1. No existe en la fuente
- **Coordenadas:** 17 de las 429 obras no tienen coordenadas en INFOBRAS. En el mapa se usan coordenadas **aproximadas** de ESCALE (el local escolar que declara el CUI de la obra o el centro de los colegios del distrito; `coordenada_origen`). En las obras que sí tienen coordenadas, ese centro queda a unos 3 km de la ubicación real (mediana).
- **Contraloría antes de sep-2023:** solo hay cifras agregadas en los PDF; no hay datos obra por obra.
- **Costos:** 98 filas de la Contraloría traen costo 0 o vacío y 9 traen saldo mayor que el costo. Están marcadas en `alertas_calidad`, sin corregir.
- **Expediente técnico:** 3 obras sin ejecución tienen expediente técnico 0 o vacío en INFOBRAS.
- **MEF:** 53 obras no aparecen en el Formato 12-B; 15 de ellas tienen CUI «NO ASOCIADO».

## 2. El portal no respondió
- **ENLA:** SICRECE no devolvió datos de 6.º de primaria 2022, 2.º de primaria 2023 ni 5.º de secundaria 2025 (3 intentos cada uno).
- **ENLA por UGEL o provincia:** no se consiguió; solo hay datos por región.

## 3. Fuera del alcance (decisión por tiempo)
- **ESCALE ampliado:** los 16 indicadores nuevos son solo de 2025 (para 2022-2024 habría que mapear los nombres de variable de cada año). Quedan 123 variables candidatas en el catálogo sin extraer. Los 5 indicadores principales sí tienen serie 2022-2025.
- **Anexo 03 de la Contraloría:** solo se usa el corte de marzo de 2026 (el de junio no se publicó). 43 % de las obras figuran ahí; vacío = la obra no figura.
- **INFOBRAS no se actualizó:** es una foto del 27-oct y del 11-nov-2026. Volver a leerlo cambiaría los números.

## 4. Calidad del dato e interpretación
- **INFOBRAS y la Contraloría son poblaciones distintas:** 198 obras de Educación paralizadas en INFOBRAS (27-oct) frente a 341 en la lista de la Contraloría (jun-2026); solo 110 están en ambas. Las 429 obras del tablero son la unión de las dos.
- **Las fuentes tienen fechas distintas:** INFOBRAS, 11-nov-2026; Contraloría, hasta jun-2026; ESCALE y ENLA, hasta 2025; MEF, foto mensual. El tablero compara datos de momentos distintos.
- **El estado cambia rápido:** de las 198 obras paralizadas el 27-oct, 20 ya estaban en ejecución el 11-nov. De las 231 obras de la Contraloría que ya no figuraban como paralizadas, 130 están en ejecución y 95 finalizadas.
- **Causas:** la causa principal sale sobre todo de la causal oficial de la Contraloría (310 de 429 obras); los comentarios de INFOBRAS decidieron en 83 y el MEF en 24. Comentarios y causal oficial coinciden solo en 49 % de las obras donde ambos dicen algo claro. 12 obras quedan sin causa clasificada.
- **Tipo de infraestructura:** INFOBRAS agrupa Educación y Cultura, así que entre las 429 obras hay estadios, losas deportivas, universidades y sitios arqueológicos. La columna `tipo_infraestructura` los separa con reglas sobre el nombre de la obra: 188 son de educación básica (colegios), 159 deportivas o recreativas, 56 de educación superior, 20 culturales y 6 de otro tipo. Al ser reglas, puede haber errores puntuales; el dashboard muestra por defecto solo educación básica.
- **Mapa:** los límites de regiones y provincias y las capitales vienen de [peru-geojson](https://github.com/juaneladio/peru-geojson) (licencia MPL 2.0), simplificados y redondeados a unos 100 m: sirven para ubicar las obras, no para medir distancias ni límites exactos.
- **Tiempo paralizada:** el campo «días paralizado» de INFOBRAS vale 30 o 31 en casi todas las obras (son los días del mes del informe, no el total). El tiempo real se calcula desde la fecha de paralización hasta la lectura de INFOBRAS (`dias_desde_paralizacion`): en los colegios paralizados hoy la mediana es de unos 4 años.
- **Modelo de NLP:** no clasificó ninguna obra (las 429 causas salen de las reglas). Su F1 de 0.885 mide cuánto reproduce a las reglas con las que se entrenó, no la exactitud frente a una revisión manual: es un control de consistencia.
- **INFOBRAS se contradice a sí mismo:** en 6 obras el avance físico del encabezado no coincide con el último avance de su propia tabla. En 4 obras la ubicación estaba mal (2 figuraban en Huancavelica y son de Ica; 2 en el distrito Chavín de Huántar y son de Huanta); se corrigió el ubigeo a mano con el motivo documentado.
- **MEF frente a INFOBRAS:** 41 obras tienen devengado mayor al costo y en 61 el avance físico de INFOBRAS difiere más de 30 puntos del MEF.
- **Alertas:** 206 de las 429 obras tienen al menos una alerta de calidad.
- **Relación no es causa:** que una región tenga más obras paralizadas y peores resultados en ENLA o peor infraestructura no prueba que una cosa cause la otra.

## Hallazgos que no son falta de datos
- **Loreto y Tumbes no tienen obras de Educación paralizadas** ni en la lista de la Contraloría de jun-2026 (tienen 35 y 10 obras paralizadas de otros sectores) ni en INFOBRAS. En el mapa valen 0, no «sin dato».
