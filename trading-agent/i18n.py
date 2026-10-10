"""
i18n.py
Cambio de idioma Español / English para toda la pantalla (landing y panel).

Cómo funciona:
  - El idioma vive en st.session_state["lang"] ("es" o "en") y se recuerda en el enlace (?lang=en).
  - En español no se toca nada: el código sigue escribiendo todo en español.
  - En inglés, cada texto que se dibuja (markdown, títulos, botones, tablas, gráficos, el asteroide 3D...) pasa por
    tr(), que reemplaza las frases en español por su versión de i18n_en.py.
  - Si agregás un texto nuevo en español en la interfaz, agregá su traducción en i18n_en.py.
"""
import copy
import functools
import json
import re

import streamlit as st
import streamlit.components.v1 as components
from streamlit.delta_generator import DeltaGenerator

from i18n_en import EN

# Palabras sueltas que solo se traducen cuando son TODO el texto (no se pueden reemplazar en cualquier lado).
EN_EXACT = {"y": "and", "o": "or", "en": "in", "de": "of", "De": "Out of", "con": "with"}

_KEYS = sorted((k for k in EN if k.strip()), key=len, reverse=True)


def _compile():
    parts = []
    for k in _KEYS:
        p = re.escape(k)
        if re.match(r"\w", k[0]):
            p = r"(?<!\w)" + p
        if re.match(r"\w", k[-1]):
            p = p + r"(?!\w)"
        parts.append(p)
    return re.compile("|".join(parts))


_RX = _compile()
_DATA_URI = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+")


# ---------- Idioma ----------
def lang() -> str:
    try:
        return st.session_state.get("lang", "es")
    except Exception:
        return "es"


def is_en() -> bool:
    return lang() == "en"


def init_lang():
    """Primera visita: toma el idioma del enlace (?lang=en); si no, español."""
    if "lang" not in st.session_state:
        q = st.query_params.get("lang")
        st.session_state["lang"] = "en" if q == "en" else "es"


def _flip():
    new = "es" if is_en() else "en"
    st.session_state["lang"] = new
    st.query_params["lang"] = new


# ---------- Traducción ----------
@functools.lru_cache(maxsize=4096)
def _tr_en(s: str) -> str:
    st_ = s.strip()
    if st_ in EN_EXACT:
        return s.replace(st_, EN_EXACT[st_])
    if "base64," not in s:
        return _RX.sub(lambda m: EN[m.group(0)], s)
    # Las imágenes incrustadas (data:...;base64,XXXX) no se tocan: una frase suelta dentro de los datos las rompe.
    out, last = [], 0
    for m in _DATA_URI.finditer(s):
        out.append(_RX.sub(lambda x: EN[x.group(0)], s[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(_RX.sub(lambda x: EN[x.group(0)], s[last:]))
    return "".join(out)


def tr(s):
    """Traduce un texto al idioma actual. En español devuelve el texto tal cual."""
    if isinstance(s, str) and s and is_en():
        return _tr_en(s)
    return s


def dec(text: str) -> str:
    """Separador decimal según el idioma: coma en español, punto en inglés."""
    return text if is_en() else text.replace(".", ",")


def thousands(text: str) -> str:
    """Separador de miles según el idioma (recibe un número ya formateado con comas): punto en español."""
    return text if is_en() else text.replace(",", ".")


def _walk(o):
    if isinstance(o, str):
        return _tr_en(o)
    if isinstance(o, list):
        return [_walk(x) for x in o]
    if isinstance(o, dict):
        return {k: _walk(v) for k, v in o.items()}
    return o


def _tr_fig(fig):
    try:
        import plotly.graph_objects as go
        d = json.loads(fig.to_json())
        return go.Figure(_walk(d))
    except Exception:
        return fig


def _tr_df(df):
    try:
        import pandas as pd
        if not isinstance(df, pd.DataFrame):
            return df
        out = df.copy()
        out.columns = [tr(c) if isinstance(c, str) else c for c in out.columns]
        for c in out.columns:
            if out[c].dtype == object:
                out[c] = out[c].map(lambda v: tr(v) if isinstance(v, str) else v)
        if isinstance(out.index, pd.Index) and out.index.dtype == object:
            out.index = [tr(v) if isinstance(v, str) else v for v in out.index]
        return out
    except Exception:
        return df


_TEXT_KW = ("label", "help", "placeholder", "body", "text", "caption")


def _wrap_text(orig, first_text=True):
    @functools.wraps(orig)
    def inner(self, *a, **k):
        if is_en():
            a = list(a)
            if a and isinstance(a[0], str):
                a[0] = _tr_en(a[0])
            for key in _TEXT_KW:
                if isinstance(k.get(key), str):
                    k[key] = _tr_en(k[key])
        return orig(self, *a, **k)
    return inner


def _wrap_choice(orig):
    """selectbox / radio: traduce la etiqueta y cómo se ven las opciones, sin cambiar los valores que devuelve."""
    @functools.wraps(orig)
    def inner(self, label, options=(), *a, **k):
        if is_en():
            label = _tr_en(label) if isinstance(label, str) else label
            fmt = k.get("format_func", str)
            k["format_func"] = lambda v, _f=fmt: tr(str(_f(v)))
        return orig(self, label, options, *a, **k)
    return inner


def _wrap_tabs(orig):
    @functools.wraps(orig)
    def inner(self, tabs, *a, **k):
        if is_en():
            tabs = [tr(t) for t in tabs]
        return orig(self, tabs, *a, **k)
    return inner


def _wrap_frame(orig):
    @functools.wraps(orig)
    def inner(self, data=None, *a, **k):
        if is_en():
            data = _tr_df(data)
        return orig(self, data, *a, **k)
    return inner


def _wrap_plot(orig):
    @functools.wraps(orig)
    def inner(self, figure_or_data, *a, **k):
        if is_en():
            figure_or_data = _tr_fig(figure_or_data)
        return orig(self, figure_or_data, *a, **k)
    return inner


def _wrap_write(orig):
    @functools.wraps(orig)
    def inner(self, *a, **k):
        if is_en():
            a = [tr(x) if isinstance(x, str) else x for x in a]
        return orig(self, *a, **k)
    return inner


def install():
    """Envuelve las funciones de Streamlit para traducir al dibujar. Se hace una sola vez por proceso."""
    if getattr(st, "_pc_i18n_installed", False):
        return
    text_fns = ["markdown", "caption", "info", "warning", "error", "success", "subheader", "header", "title", "text",
                "button", "toggle", "checkbox", "text_input", "text_area", "number_input", "expander", "popover",
                "form_submit_button", "metric"]
    for name in text_fns:
        if hasattr(DeltaGenerator, name):
            setattr(DeltaGenerator, name, _wrap_text(getattr(DeltaGenerator, name)))
    for name in ("selectbox", "radio"):
        if hasattr(DeltaGenerator, name):
            setattr(DeltaGenerator, name, _wrap_choice(getattr(DeltaGenerator, name)))
    if hasattr(DeltaGenerator, "tabs"):
        DeltaGenerator.tabs = _wrap_tabs(DeltaGenerator.tabs)
    for name in ("dataframe", "table", "data_editor"):
        if hasattr(DeltaGenerator, name):
            setattr(DeltaGenerator, name, _wrap_frame(getattr(DeltaGenerator, name)))
    if hasattr(DeltaGenerator, "plotly_chart"):
        DeltaGenerator.plotly_chart = _wrap_plot(DeltaGenerator.plotly_chart)
    if hasattr(DeltaGenerator, "write"):
        DeltaGenerator.write = _wrap_write(DeltaGenerator.write)

    # st.markdown, st.button... son atajos ya enlazados a la versión vieja: se vuelven a enlazar.
    main = getattr(st, "_main", None)
    if main is not None:
        for name in text_fns + ["selectbox", "radio", "tabs", "dataframe", "table", "data_editor", "plotly_chart", "write"]:
            if hasattr(st, name) and hasattr(main, name):
                setattr(st, name, getattr(main, name))

    # Piezas que no son métodos de DeltaGenerator.
    _spinner = st.spinner

    @functools.wraps(_spinner)
    def spinner(text="In progress...", *a, **k):
        return _spinner(tr(text), *a, **k)
    st.spinner = spinner

    _html = components.html

    @functools.wraps(_html)
    def html(src, *a, **k):
        return _html(tr(src), *a, **k)
    components.html = html

    st._pc_i18n_installed = True


# ---------- Botón de idioma (arriba del todo) ----------
_TOGGLE_CSS = """
<style>
.st-key-lang_bar {position: fixed; top: 10px; right: 16px; z-index: 1000002; width: auto !important;}
.st-key-lang_bar .stElementContainer, .st-key-lang_bar .stButton {width: auto !important;}
.st-key-lang_bar button {padding: 3px 13px; min-height: 0; border-radius: 999px; font: 700 12px 'Chakra Petch', sans-serif;
    letter-spacing: .08em; background: rgba(4,6,13,.82) !important; border: 1px solid rgba(79,209,232,.55) !important;
    color: #CFE9F3 !important; backdrop-filter: blur(6px); box-shadow: 0 2px 14px rgba(0,0,0,.35);}
.st-key-lang_bar button:hover {border-color: #4FD1E8 !important; color: #fff !important;}
.st-key-lang_bar button p {font: inherit; color: inherit; margin: 0;}
.pc-top {padding-right: 130px;}
</style>
"""


def render_toggle():
    """Botón fijo arriba a la derecha que alterna Español / English. Va en las dos vistas (landing y panel)."""
    st.markdown(_TOGGLE_CSS, unsafe_allow_html=True)
    with st.container(key="lang_bar"):
        st.button("🌐 Español" if is_en() else "🌐 English", key="lang_btn", on_click=_flip,
                  help=("Cambiar a español" if is_en() else "Switch to English"))
