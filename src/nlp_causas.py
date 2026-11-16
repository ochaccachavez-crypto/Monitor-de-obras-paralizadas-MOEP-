"""NLP de las causas de paralizacion: del texto libre (comentarios de INFOBRAS, causal de la Contraloria, problematica del MEF)
a un grupo de causa por obra.

Pasos (todo con reglas simples y un modelo de apoyo; nada de cajas negras):
  1. normalizar: minusculas, sin tildes, sin fechas ni frases de relleno ("No se registraron comentarios").
  2. puntuar: cada grupo de config.CAUSAS_REGLAS suma segun cuantos patrones distintos aparecen (maximo 2 puntos por grupo, asi
     ningun grupo gana solo por tener mas patrones). Se pueden detectar varias causas en un mismo texto.
  3. combinar las tres fuentes de una obra con pesos (la causal oficial pesa mas que un comentario viejo).
     Los grupos de ESTADO (obra concluida, sin restricciones) solo se asignan cuando no hay ninguna causa real.
  4. modelo de apoyo (TF-IDF + regresion logistica con class_weight="balanced"): se entrena con los textos que las reglas clasifican
     sin ambiguedad y solo se usa para textos donde las reglas no encontraron nada. Se mide con validacion cruzada.
  5. macro-categoria (config.CAUSAS_MACRO) para el dashboard: pocas categorias de tamano parecido.
"""
import re
import unicodedata

import numpy as np
import pandas as pd

import config
from utils import log

ESTADO = config.CAUSAS_ESTADO
ORDEN = list(config.CAUSAS_REGLAS)
CAUSAS = [g for g in ORDEN if g not in ESTADO]
UMBRAL_MODELO = 0.60          # probabilidad minima para aceptar la prediccion del modelo
MINIMO_POR_CLASE = 8          # clases con menos ejemplos limpios no entran al modelo (se quedan solo con reglas)
_REGEX = {g: [re.compile(p) for p in patrones] for g, patrones in config.CAUSAS_REGLAS.items()}
_RELLENO = [re.compile(p) for p in config.FRASES_SIN_INFORMACION]


# ---------------- 1) normalizar ----------------
def normalizar(texto):
    """Minusculas, sin tildes (la enie pasa a n), sin fechas ni direcciones web y con espacios simples."""
    if texto is None or (isinstance(texto, float) and np.isnan(texto)):
        return ""
    t = unicodedata.normalize("NFD", str(texto).lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\[\d{1,2}/\d{1,2}/\d{2,4}\]", " ", t)          # [27/10/2026] al inicio de la problematica del MEF
    t = re.sub(r"\d{1,2}/\d{1,2}/\d{2,4}", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def quitar_relleno(norm):
    for r in _RELLENO:
        norm = r.sub(" ", norm)
    return re.sub(r"\s+", " ", norm).strip()


def sin_contenido(texto):
    """True si el texto no dice nada de la causa (vacio, frases tipicas o solo palabras vacias)."""
    limpio = quitar_relleno(normalizar(texto))
    palabras = [p for p in re.findall(r"[a-z]{3,}", limpio) if p not in config.PALABRAS_SIN_INFORMACION]
    return not palabras


# ---------------- 2) puntuar un texto ----------------
_NEGADORES = re.compile(r"\b(sin|no|ni|ningun\w*|permit\w+|favorable\w*|descart\w+)\b[^.;]{0,30}$")


_NEGADORES_DESPUES = re.compile(r"^[^.;]{0,35}\b(permit\w+|favorable\w*|no (impid|afect|limit)\w*|sin (afectar|impedir)\w*)")


def _aparece(regex, norm, comprobar_negacion):
    """True si el patron aparece. En causas «de presencia» (clima, conflictos...) se descartan las apariciones precedidas de
    «no», «sin» o «permiten» en la misma frase («las condiciones climatologicas permiten su ejecucion» no es una causa)."""
    for m in regex.finditer(norm):
        if not comprobar_negacion:
            return True
        antes, despues = norm[max(0, m.start() - 45):m.start()], norm[m.end():m.end() + 45]
        if not _NEGADORES.search(antes) and not _NEGADORES_DESPUES.search(despues):
            return True
    return False


def puntuar(norm):
    """grupo -> puntaje (1 punto por el primer patron que aparece, +0.5 por cada patron distinto adicional, maximo 2)."""
    puntajes = {}
    for grupo, regs in _REGEX.items():
        k = sum(1 for r in regs if _aparece(r, norm, grupo in config.CAUSAS_PRESENCIA))
        if k:
            puntajes[grupo] = min(1 + 0.5 * (k - 1), 2.0)
    return puntajes


# ---------------- 3) combinar las fuentes de una obra ----------------
def analizar(fuentes):
    """fuentes: lista de (nombre_fuente, texto, peso). Devuelve un diccionario con la causa principal y sus datos de apoyo."""
    total, por_fuente, hay_texto = {}, {}, False
    for nombre, texto, peso in fuentes:
        norm = quitar_relleno(normalizar(texto))
        if not norm or sin_contenido(texto):
            continue
        hay_texto = True
        for grupo, puntaje in puntuar(norm).items():
            total[grupo] = total.get(grupo, 0) + puntaje * peso
            por_fuente.setdefault(grupo, {})
            por_fuente[grupo][nombre] = por_fuente[grupo].get(nombre, 0) + puntaje * peso
    causas = {g: s for g, s in total.items() if g not in ESTADO}
    pool = causas or total                       # los grupos de estado solo cuentan si no hay causa real
    if not pool:
        return {"principal": "otros" if hay_texto else "sin_informacion", "secundarias": [], "fuente": "", "confianza": "", "metodo": "reglas"}
    mejor = max(pool.values())
    principal = next(g for g in ORDEN if pool.get(g) == mejor)
    secundarias = [g for g in ORDEN if g != principal and pool.get(g, 0) >= 0.5 * mejor][:2]
    aporte = por_fuente[principal]
    return {"principal": principal, "secundarias": secundarias, "fuente": max(aporte, key=aporte.get),
            "confianza": "alta" if len(aporte) >= 2 else "media", "metodo": "reglas"}


def clasificar_causa(causal, comentario=None):
    """Grupo de causa de un par (causal declarada, comentario). Se mantiene con este nombre porque lo usan otros modulos."""
    return analizar([("causal", causal, 3.0), ("comentario", comentario, 1.0)])["principal"]


def macro(grupo):
    return config.CAUSAS_MACRO.get(grupo, "sin_clasificar")


# ---------------- 4) modelo de apoyo ----------------
def _modelo():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    return make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                         LogisticRegression(class_weight="balanced", max_iter=3000, C=2.0))


def ejemplos_limpios(textos):
    """Textos unicos que las reglas clasifican sin ambiguedad: una sola causa real. Devuelve (textos normalizados, etiquetas)."""
    vistos, X, y = set(), [], []
    for texto in textos:
        norm = quitar_relleno(normalizar(texto))
        if not norm or norm in vistos or sin_contenido(texto):
            continue
        vistos.add(norm)
        causas = [g for g in puntuar(norm) if g not in ESTADO]
        if len(causas) == 1:
            X.append(norm)
            y.append(causas[0])
    return X, y


def entrenar(textos):
    """Entrena el modelo con los ejemplos limpios (solo clases con MINIMO_POR_CLASE ejemplos) y mide con validacion cruzada.
    Devuelve (modelo, metricas) donde metricas es una tabla por clase con precision, recall, f1 y cantidad de ejemplos."""
    from sklearn.metrics import classification_report
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    X, y = ejemplos_limpios(textos)
    cuenta = pd.Series(y).value_counts()
    validas = set(cuenta[cuenta >= MINIMO_POR_CLASE].index)
    X, y = [x for x, g in zip(X, y) if g in validas], [g for g in y if g in validas]
    modelo = _modelo()
    pliegues = int(min(5, pd.Series(y).value_counts().min()))
    prediccion = cross_val_predict(modelo, X, y, cv=StratifiedKFold(pliegues, shuffle=True, random_state=2026))
    reporte = classification_report(y, prediccion, output_dict=True, zero_division=0)
    metricas = pd.DataFrame(reporte).T.reset_index().rename(columns={"index": "clase", "f1-score": "f1", "support": "ejemplos"})
    metricas["ejemplos"] = metricas.ejemplos.round(0).astype(int)
    for c in ("precision", "recall", "f1"):
        metricas[c] = metricas[c].round(3)
    modelo.fit(X, y)
    log(f"NLP causas: modelo entrenado con {len(X)} textos ({len(validas)} clases); validacion cruzada de {pliegues} pliegues: "
        f"macro-F1 = {reporte['macro avg']['f1-score']:.3f}, exactitud = {reporte['accuracy']:.3f}")
    return modelo, metricas


def predecir(modelo, texto):
    """(grupo, probabilidad) del modelo para un texto, o ('', 0) si esta vacio."""
    norm = quitar_relleno(normalizar(texto))
    if not norm or sin_contenido(texto):
        return "", 0.0
    prob = modelo.predict_proba([norm])[0]
    i = int(np.argmax(prob))
    return str(modelo.classes_[i]), float(prob[i])


# ---------------- 5) clasificar toda la tabla maestra ----------------
def textos_de_infobras(paralizaciones):
    """codigo_infobras -> lista de (texto, peso) con los comentarios unicos; los del ultimo tramo de paralizacion pesan 2 y los demas 0.5."""
    p = paralizaciones.copy()
    p["texto"] = (p.comentario_fisico.fillna("") + " " + p.comentario_valorizado.fillna("")).str.strip()
    p["tramo_n"] = pd.to_numeric(p.tramo, errors="coerce").fillna(0)
    p = p[~p.texto.map(sin_contenido)]
    salida = {}
    for codigo, g in p.groupby("codigo_infobras"):
        ultimo = g.tramo_n.max()
        vistos, lista = set(), []
        for texto, tramo in sorted(zip(g.texto, g.tramo_n), key=lambda x: -x[1]):
            clave = normalizar(texto)
            if clave in vistos:
                continue
            vistos.add(clave)
            lista.append((texto, 2.0 if tramo == ultimo else 0.5))
        salida[codigo] = lista
    return salida


def clasificar_maestra(m, paralizaciones, mef_completo):
    """Agrega a la tabla maestra las columnas de causa. m necesita: codigo_infobras, causal_oficial_contraloria, mef_ult_problema.
    Devuelve (m_con_causas, metricas_del_modelo, detalle_por_fuente)."""
    infobras = textos_de_infobras(paralizaciones)
    # el modelo aprende de todos los textos libres disponibles: comentarios de INFOBRAS y problematica de todo el Formato 12-B del MEF
    textos_modelo = [t for lista in infobras.values() for t, _ in lista] + list(mef_completo.get("ult_problema", pd.Series(dtype=str)).fillna(""))
    modelo, metricas = entrenar(textos_modelo)

    filas = []
    for _, r in m.iterrows():
        comentarios = infobras.get(r.codigo_infobras, [])
        fuentes = [("infobras_comentario", t, w) for t, w in comentarios]
        fuentes += [("contraloria_causal", r.causal_oficial_contraloria, 3.0), ("mef_problema", r.mef_ult_problema, 1.5)]
        res = analizar(fuentes)
        # causa por fuente (solo para comparar las fuentes entre si)
        g_infobras = analizar([("x", t, w) for t, w in comentarios])["principal"] if comentarios else "sin_informacion"
        g_contraloria = analizar([("x", r.causal_oficial_contraloria, 1.0)])["principal"]
        g_mef = analizar([("x", r.mef_ult_problema, 1.0)])["principal"]
        if res["principal"] == "otros":
            # las reglas no reconocieron nada: se prueba el modelo solo con los textos libres (no con la causal oficial "OTROS")
            libres = [t for t, _ in comentarios] + [r.mef_ult_problema]
            mejor = max((predecir(modelo, t) for t in libres), key=lambda x: x[1], default=("", 0.0))
            if mejor[0] and mejor[1] >= UMBRAL_MODELO:
                res = {"principal": mejor[0], "secundarias": [], "fuente": "texto_libre", "confianza": "baja", "metodo": "modelo"}
        filas.append({"causa_grupo_infobras": g_infobras, "causa_grupo_contraloria": g_contraloria, "causa_grupo_mef": g_mef,
                      "causa_grupo_final": res["principal"], "causa_macro": macro(res["principal"]),
                      "causas_secundarias": "|".join(res["secundarias"]), "causa_fuente": res["fuente"] or "sin_causa_clara",
                      "causa_confianza": res["confianza"], "causa_metodo": res["metodo"]})
    nuevas = pd.DataFrame(filas, index=m.index)
    m = m.drop(columns=[c for c in nuevas.columns if c in m]).join(nuevas)
    return m, metricas
