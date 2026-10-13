"""
Suivi des erreurs (Sentry) : prévenir le propriétaire quand le serveur plante, au lieu de l'apprendre par un client.

- Inactif tant que la variable SENTRY_DSN n'est pas définie (aucun effet en local ni dans les tests).
- Aucune donnée personnelle ne part : pas de cookies, pas d'en-têtes, pas de corps de requête, pas d'adresse IP,
  pas de variables locales, adresses e-mail / jetons / clés masqués dans les messages et les URL.
- Pas de mesure de performance (traces) : seulement les erreurs.
"""
import os
import re
from urllib.parse import urlsplit, urlunsplit

try:  # le service doit continuer à démarrer même si le paquet manque
    import sentry_sdk
except ImportError:  # pragma: no cover
    sentry_sdk = None

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_SECRET_PARAM = re.compile(r"(?i)\b(key|api_key|apikey|token|access_token|code|secret|password|signature|sig)=[^&\s'\"]+")
_LONG_TOKEN = re.compile(r"\b[A-Za-z0-9_\-]{28,}\b")
# Erreurs sans intérêt : le visiteur a fermé sa page / la tâche a été annulée.
_IGNORED_TYPES = {"ClientDisconnect", "CancelledError", "BrokenPipeError", "ConnectionResetError"}

_enabled = False


def scrub_text(value: str) -> str:
    """Masque e-mails, paramètres secrets (…?key=…) et longues chaînes ressemblant à un jeton."""
    value = _EMAIL.sub("[email]", value)
    value = _SECRET_PARAM.sub(lambda m: m.group(1) + "=[masqué]", value)
    return _LONG_TOKEN.sub("[masqué]", value)


def _scrub_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except Exception:
        return "[url]"


def _scrub_any(obj):
    if isinstance(obj, str):
        return scrub_text(obj)
    if isinstance(obj, dict):
        return {k: _scrub_any(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub_any(v) for v in obj]
    return obj


def before_send(event, hint):
    """Dernier filtre avant l'envoi : supprime tout ce qui est personnel."""
    exc_info = hint.get("exc_info") if hint else None
    if exc_info and exc_info[0] is not None and exc_info[0].__name__ in _IGNORED_TYPES:
        return None

    request = event.get("request")
    if request:
        # On garde seulement la méthode et le chemin (sans paramètres) : de quoi retrouver la page qui plante.
        event["request"] = {"method": request.get("method"), "url": _scrub_url(request.get("url", ""))}
    event.pop("user", None)
    event.pop("server_name", None)
    event.pop("modules", None)
    if "message" in event and isinstance(event["message"], str):
        event["message"] = scrub_text(event["message"])
    if "logentry" in event:
        event["logentry"] = _scrub_any(event["logentry"])
    for exc in (event.get("exception") or {}).get("values", []) or []:
        if isinstance(exc.get("value"), str):
            exc["value"] = scrub_text(exc["value"])
        for frame in (exc.get("stacktrace") or {}).get("frames", []) or []:
            frame.pop("vars", None)
    if "extra" in event:
        event["extra"] = _scrub_any(event["extra"])
    return event


def before_breadcrumb(crumb, hint):
    """Les fils d'Ariane (appels HTTP sortants, journaux) peuvent contenir des URL avec des clés : on les nettoie."""
    data = crumb.get("data")
    if isinstance(data, dict):
        if "url" in data and isinstance(data["url"], str):
            data["url"] = _scrub_url(data["url"])
        data.pop("http.query", None)
        data.pop("http.fragment", None)
        crumb["data"] = _scrub_any(data)
    if isinstance(crumb.get("message"), str):
        crumb["message"] = scrub_text(crumb["message"])
    return crumb


def init_monitoring(transport=None) -> bool:
    """Active Sentry si SENTRY_DSN est défini. `transport` sert aux tests. Renvoie True si actif."""
    global _enabled
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn or sentry_sdk is None:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production").strip() or "production",
        release=os.getenv("RENDER_GIT_COMMIT", "").strip() or None,
        send_default_pii=False,
        include_local_variables=False,
        traces_sample_rate=0,
        max_breadcrumbs=20,
        before_send=before_send,
        before_breadcrumb=before_breadcrumb,
        transport=transport,
    )
    _enabled = True
    return True


def is_enabled() -> bool:
    return _enabled


def capture_exception(exc: BaseException, **tags) -> None:
    """Signale une erreur déjà attrapée (par exemple dans une tâche de fond). Sans effet si le suivi est inactif."""
    if not _enabled:
        return
    try:
        with sentry_sdk.new_scope() as scope:
            for key, value in tags.items():
                scope.set_tag(key, str(value)[:100])
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass  # le suivi ne doit jamais aggraver une panne


def capture_message(message: str, **tags) -> None:
    """Signale un incident sans exception (par exemple une erreur 5xx renvoyée volontairement)."""
    if not _enabled:
        return
    try:
        with sentry_sdk.new_scope() as scope:
            for key, value in tags.items():
                scope.set_tag(key, str(value)[:100])
            scope.fingerprint = [message.split(":")[0][:80], str(tags.get("path", "")), str(tags.get("status", ""))]
            sentry_sdk.capture_message(scrub_text(message)[:300], level="error")
    except Exception:
        pass
