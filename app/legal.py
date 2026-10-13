"""
Pages juridiques (Conditions d'utilisation et Politique de confidentialité) dans les 6 langues de l'application.

Les textes vivent dans app/legal_texts/<langue>.py (fr = version de référence qui fait foi). Une langue sans texte
retombe sur l'anglais. Le rendu est ici : un seul gabarit pour toutes les langues.
"""
import html as _html
from importlib import import_module

from app.translations import SUPPORTED_LANGS

EMAIL = "contact.wilapp@proton.me"
WHATSAPP_URL = "https://wa.me/447446953451"
WHATSAPP_LABEL = "WhatsApp"
FALLBACK_LANG = "en"

LEGAL_STYLE = """
  body { font-family: -apple-system, Arial, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #222; }
  h1 { font-size: 28px; }
  h2 { font-size: 20px; margin-top: 32px; }
  footer { margin-top: 60px; color: #777; font-size: 14px; }
  a { color: #0645AD; }
"""

_cache: dict[tuple[str, str], dict] = {}


def _load(lang: str, kind: str) -> dict:
    """Texte `kind` ("TERMS" ou "PRIVACY") dans `lang`, avec repli sur l'anglais si la langue n'a pas de texte."""
    key = (lang, kind)
    if key not in _cache:
        try:
            mod = import_module(f"app.legal_texts.{lang}")
            doc = getattr(mod, kind)
        except (ImportError, AttributeError):
            mod = import_module(f"app.legal_texts.{FALLBACK_LANG}")
            doc = getattr(mod, kind)
        _cache[key] = doc
    return _cache[key]


def _fill(html: str) -> str:
    """Remplace les repères de contact par de vrais liens."""
    return (
        html.replace("{EMAIL}", f'<a href="mailto:{EMAIL}">{EMAIL}</a>')
        .replace("{WHATSAPP}", f'<a href="{WHATSAPP_URL}" target="_blank" rel="noopener">{WHATSAPP_LABEL}</a>')
    )


def render_legal(kind: str, lang: str, from_app: bool = False) -> str:
    """Page HTML complète. `kind` : "terms" ou "privacy"."""
    if lang not in SUPPORTED_LANGS:
        lang = FALLBACK_LANG
    doc = _load(lang, "TERMS" if kind == "terms" else "PRIVACY")
    other_path = "/privacy" if kind == "terms" else "/terms"
    suffix = "?from=app" if from_app else ""
    back = (f'<a href="/app#profile">{doc["back_settings"]}</a>' if from_app
            else f'<a href="/">{doc["back_home"]}</a>')

    parts = [
        "<!doctype html>",
        f'<html lang="{lang}">',
        "<head>",
        '  <meta charset="utf-8">',
        f'  <title>{_html.escape(doc["title"])} — Wil App</title>',
        '  <link rel="icon" type="image/x-icon" href="/favicon.ico">',
        '  <meta name="viewport" content="width=device-width, initial-scale=1">',
        f"  <style>{LEGAL_STYLE}</style>",
        "</head>",
        "<body>",
        f"<p>{back}</p>",
        f'<h1>{_html.escape(doc["title"])}</h1>',
        f'<p><em>{_html.escape(doc["updated"])}</em></p>',
    ]
    if doc.get("prevails"):
        parts.append(f'<p><em>{doc["prevails"]}</em></p>')
    parts.append(f'<p>{_fill(doc["intro"])}</p>')
    for heading, blocks in doc["sections"]:
        parts.append(f"<h2>{heading}</h2>")
        for block_kind, content in blocks:
            if block_kind == "ul":
                parts.append("<ul>" + "".join(f"<li>{_fill(item)}</li>" for item in content) + "</ul>")
            else:
                parts.append(f"<p>{_fill(content)}</p>")
    parts.append(f'<p><a href="{other_path}{suffix}">{doc["see_also"]}</a></p>')
    parts.append(f'<footer>{_html.escape(doc["footer"])}</footer>')
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)
