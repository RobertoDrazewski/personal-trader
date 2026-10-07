"""Vista previa al compartir el link (WhatsApp, Telegram, etc.) e ícono de pantalla de inicio.

Los buscadores de previsualización NO ejecutan JavaScript: leen el HTML crudo que sirve Streamlit,
cuyo <title> es "Streamlit" y no tiene etiquetas og:. Acá se parchea ese index.html (una sola vez,
es idempotente) para que diga lo que corresponde. Si no hay permiso de escritura, no pasa nada:
la app sigue funcionando igual, solo que la vista previa queda genérica.
"""
import os
import re

PUBLIC_URL = os.getenv("PUBLIC_URL", "https://trading-agent.puma-code.com").rstrip("/")
TITLE = "Puma-Code Trading Agent"
DESC = ("Agente de trading algorítmico en vivo (paper trading): acciones y cripto conservadora, "
        "con datos reales, frenos de riesgo y alarmas. Demo educativa de Puma Code.")
START, END = "<!-- pc-seo:start -->", "<!-- pc-seo:end -->"


def _block() -> str:
    img = f"{PUBLIC_URL}/app/static/og-image.png"
    return f"""{START}
    <title>{TITLE}</title>
    <meta name="description" content="{DESC}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="Puma Code" />
    <meta property="og:title" content="{TITLE}" />
    <meta property="og:description" content="{DESC}" />
    <meta property="og:url" content="{PUBLIC_URL}/" />
    <meta property="og:image" content="{img}" />
    <meta property="og:image:type" content="image/png" />
    <meta property="og:image:width" content="1200" />
    <meta property="og:image:height" content="630" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="{TITLE}" />
    <meta name="twitter:description" content="{DESC}" />
    <meta name="twitter:image" content="{img}" />
    <meta name="theme-color" content="#04060D" />
    <link rel="apple-touch-icon" sizes="180x180" href="/app/static/apple-touch-icon.png" />
    <link rel="manifest" href="/app/static/manifest.json" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-title" content="PC Trading" />
    {END}"""


def patch_index_html() -> str:
    """Devuelve 'ok', 'ya estaba' o el motivo por el que no se pudo."""
    try:
        import streamlit
        path = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
        html = open(path, encoding="utf-8").read()
        block = _block()
        if START in html:
            new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: block, html, flags=re.S)
        else:
            new, n = re.subn(r"<title>.*?</title>", lambda m: block, html, count=1, flags=re.S)
            if n == 0:
                return "no se encontró <title> en index.html"
        if new == html:
            return "ya estaba"
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        return "ok"
    except Exception as e:  # sin permisos u otra cosa: no es crítico
        return f"no se pudo: {e}"
