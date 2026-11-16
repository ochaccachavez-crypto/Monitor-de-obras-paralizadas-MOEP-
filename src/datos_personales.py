"""Datos personales: limpieza y auditoria de los comentarios libres de INFOBRAS.

Las entidades escriben a veces el nombre de su residente o supervisor en los comentarios de una obra. La regla del proyecto es no
guardar nombres de personas, asi que:
  * utils.omitir_nombres filtra cada comentario en cuanto se lee (scraper_infobras.leer_detalle_avance);
  * limpiar() vuelve a pasar el filtro por lo ya guardado (caches y tablas); se puede repetir sin cambiar nada si ya esta limpio;
  * auditar() busca nombres en TODAS las tablas finales con patrones propios y devuelve lo que encuentre; el pipeline falla si hay alguno.
"""
import json
import re

import pandas as pd

import config
import utils

CACHES = (config.INFOBRAS_FICHAS, config.INFOBRAS_AMPLIADAS)
_NOMBRE = r"[A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ]{2,}"
# titulo + dos palabras con inicial mayuscula (se excluye «don»: sale en calles como «Av. Don Bosco»)
_TITULO_NOMBRE = re.compile(rf"\b(?:(?i:ing|arq|abog|econ|lic|sr|sra|srta|cpc|bach)\.?|(?i:dra?)\.)\s+{_NOMBRE}\s+{_NOMBRE}")
# cargo + dos palabras en minuscula con inicial mayuscula
_CARGO_NOMBRE = re.compile(rf"(?<!(?i:consorcio) )\b(?i:residente|supervisor|supervisora|inspector|inspectora|proyectista)(?:\s+de\s+obra)?[,:]?\s+"
                           rf"(?P<nombre>[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{{2,}}\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]{{2,}})")
_NO_PERSONA = ("consorcio", "empresa", "ejecutor", "municipalidad", "gobierno", "unidad", "proyecto", "contratista", "entidad")
_DNI = re.compile(r"(?<![\d.,])\d{8}(?![\d.,])")


def _limpiar_json(objeto):
    """Aplica omitir_nombres a todo campo 'comentario*' (anidado o no). Devuelve cuantos textos cambio."""
    cambios = 0
    if isinstance(objeto, dict):
        for clave, valor in objeto.items():
            if clave.startswith("comentario") and isinstance(valor, str):
                nuevo = utils.omitir_nombres(valor)
                if nuevo != valor:
                    objeto[clave], cambios = nuevo, cambios + 1
            else:
                cambios += _limpiar_json(valor)
    elif isinstance(objeto, list):
        for elemento in objeto:
            cambios += _limpiar_json(elemento)
    return cambios


def limpiar():
    """Quita nombres de personas de las caches (jsonl) y de los CSV con columnas 'comentario*'. Devuelve el total de textos cambiados."""
    total = 0
    for ruta in CACHES:
        if not ruta.exists():
            continue
        filas = [json.loads(linea) for linea in ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]
        cambios = sum(_limpiar_json(f) for f in filas)
        if cambios:
            ruta.write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in filas) + "\n", encoding="utf-8")
        total += cambios
    for ruta in sorted(config.PROCESSED.glob("*.csv")):
        cabecera = pd.read_csv(ruta, nrows=0, encoding="utf-8-sig").columns
        columnas = [c for c in cabecera if c.startswith("comentario")]
        if not columnas:
            continue
        tabla = pd.read_csv(ruta, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        cambios = 0
        for c in columnas:
            nuevo = tabla[c].map(utils.omitir_nombres)
            cambios += int((nuevo != tabla[c]).sum())
            tabla[c] = nuevo
        if cambios:
            tabla.to_csv(ruta, index=False, encoding="utf-8-sig")
        total += cambios
    utils.log(f"DATOS PERSONALES: {total} texto(s) con nombres de personas reemplazados por {utils.OMITIDO}")
    return total


def auditar(carpetas=None):
    """Busca nombres de personas en las columnas de texto largo de todos los CSV de las carpetas. Devuelve un DataFrame de hallazgos."""
    carpetas = carpetas or [config.PROCESSED, config.COMPONENTES, config.FINAL]
    hallazgos = []
    for carpeta in carpetas:
        for ruta in sorted(carpeta.glob("*.csv")):
            tabla = pd.read_csv(ruta, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            for columna in tabla.columns:
                if tabla[columna].str.len().max() <= 25:
                    continue
                for texto in tabla[columna].drop_duplicates():
                    for patron, tipo in ((_TITULO_NOMBRE, "titulo + nombre"), (_CARGO_NOMBRE, "cargo + nombre")):
                        m = patron.search(texto)
                        if not m:
                            continue
                        if tipo == "cargo + nombre" and m.group("nombre").split()[0].lower() in _NO_PERSONA:
                            continue
                        hallazgos.append({"tabla": ruta.name, "columna": columna, "tipo": tipo, "texto": texto[max(0, m.start() - 30):m.end() + 30]})
                    if columna.startswith("comentario") and _DNI.search(texto):
                        hallazgos.append({"tabla": ruta.name, "columna": columna, "tipo": "numero de 8 digitos (posible DNI)", "texto": texto[:80]})
    return pd.DataFrame(hallazgos, columns=["tabla", "columna", "tipo", "texto"])


def auditoria_o_falla():
    """Registra la auditoria; si hay hallazgos, deja el detalle en docs/auditoria_datos_personales.csv y lanza un error."""
    hallazgos = auditar()
    ruta = config.DOCS / "auditoria_datos_personales.csv"
    hallazgos.to_csv(ruta, index=False, encoding="utf-8-sig")
    if len(hallazgos):
        utils.log(f"AUDITORIA DATOS PERSONALES: {len(hallazgos)} hallazgo(s), ver {ruta.name}")
        raise ValueError(f"se encontraron {len(hallazgos)} posibles nombres de personas en las tablas finales (docs/{ruta.name})")
    utils.log("AUDITORIA DATOS PERSONALES: 0 hallazgos en las tablas finales")
    return hallazgos
