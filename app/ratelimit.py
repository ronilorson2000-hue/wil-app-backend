"""
Limitation de débit simple (en mémoire) contre les abus qui font exploser la facture d'IA :
quelqu'un qui boucle sur nos routes d'analyse (Gemini, Claude) depuis un script.

- par adresse IP et par "bucket" (ex. "ai"), sur une fenêtre glissante ;
- plafond GLOBAL par jour (filet de sécurité si plusieurs IP coordonnées).

Limites : en mémoire, donc propres à chaque instance du serveur et remises à zéro à chaque
redémarrage. Suffisant comme première protection ; un vrai pare-feu (Cloudflare) peut s'y ajouter.
Réglable par variables d'environnement : AI_LIMIT_ANON, AI_LIMIT_SUBSCRIBER, AI_DAILY_CAP.
"""

import os
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[str, deque] = defaultdict(deque)
_daily = {"day": "", "count": 0}
_last_purge = 0.0


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def client_ip(request: Request) -> str:
    """
    IP du visiteur derrière Cloudflare/Render. On préfère l'en-tête posé par Cloudflare ; pour
    X-Forwarded-For on prend la DERNIÈRE valeur (ajoutée par notre proxy), jamais la première,
    que le visiteur peut falsifier.
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    return (
        request.headers.get("cf-connecting-ip")
        or request.headers.get("x-real-ip")
        or (forwarded.split(",")[-1].strip() if forwarded else "")
        or (request.client.host if request.client else "unknown")
    )


def _purge(now: float) -> None:
    global _last_purge
    if now - _last_purge < 300:
        return
    _last_purge = now
    for key in [k for k, q in _hits.items() if not q or q[-1] < now - 86400]:
        _hits.pop(key, None)


def check(request: Request, bucket: str, limit: int, window: int = 3600) -> None:
    """Refuse (429) si cette IP a déjà fait `limit` appels sur ce bucket pendant la fenêtre."""
    now = time.time()
    _purge(now)
    queue = _hits[f"{bucket}:{client_ip(request)}"]
    while queue and queue[0] < now - window:
        queue.popleft()
    if len(queue) >= limit:
        raise HTTPException(
            status_code=429,
            detail="Trop de demandes en peu de temps. Réessaie un peu plus tard.",
            headers={"Retry-After": str(window)},
        )
    queue.append(now)


def charge_daily() -> None:
    """Plafond global d'appels IA par jour (503 au-delà) : dernier filet contre une facture imprévue."""
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if _daily["day"] != today:
        _daily["day"], _daily["count"] = today, 0
    if _daily["count"] >= _int_env("AI_DAILY_CAP", 3000):
        raise HTTPException(status_code=503, detail="Service très sollicité aujourd'hui. Réessaie demain.")
    _daily["count"] += 1


def ai_limit(subscribed: bool) -> int:
    return _int_env("AI_LIMIT_SUBSCRIBER", 120) if subscribed else _int_env("AI_LIMIT_ANON", 30)
