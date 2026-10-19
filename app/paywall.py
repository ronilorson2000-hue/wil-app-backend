"""
Abonnement web via Whop : identité (« Se connecter avec Whop », OAuth 2.1 + PKCE),
vérification de l'abonnement (API memberships de Whop), rapports verrouillés
côté serveur et quotas d'essai gratuits.

Principes :
- Rien n'est verrouillé tant que PAYWALL_ENABLED n'est pas activé (variable d'env),
  pour ne jamais enfermer les utilisateurs avant que Whop soit configuré.
- Le contenu verrouillé n'est JAMAIS envoyé au navigateur : un rapport d'analyse est
  conservé côté serveur ; un non-abonné ne reçoit que les titres des sections
  (« teaser »). Griser le texte côté page ne suffirait pas, le JSON serait lisible.
- L'identité vit dans un cookie signé HttpOnly (id Whop + e-mail) ; l'état d'abonnement
  est relu auprès de Whop (cache mémoire de 2 minutes), jamais fait confiance au client.

Variables d'environnement (voir aussi supabase/schema.sql pour analysis_results) :
  PAYWALL_ENABLED, SESSION_SECRET, SITE_URL,
  WHOP_CLIENT_ID (app_...), WHOP_CLIENT_SECRET (optionnel), WHOP_API_KEY,
  WHOP_COMPANY_ID (biz_...), WHOP_PRODUCT_ID (optionnel), WHOP_CHECKOUT_URL,
  WHOP_PLAN_IDS (plan_... payants, séparés par des virgules : exclut les accès gratuits).
"""

import asyncio
import base64
import re
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import errors, ratelimit
from app.db import get_supabase
from app.translations import DEFAULT_LANG, SUPPORTED_LANGS, t

router = APIRouter()

AUTH_COOKIE = "wil_auth"
OAUTH_COOKIE = "wil_oauth"
FREE_COOKIE = "wil_free"
RETURN_COOKIE = "wil_return"
BUYER_COOKIE = "wil_buyer"
AUTH_TTL_SECONDS = 30 * 24 * 3600
OAUTH_TTL_SECONDS = 10 * 60
FREE_TTL_SECONDS = 365 * 24 * 3600
ENTITLEMENT_CACHE_SECONDS = 120
ACTIVE_STATUSES = ("active", "trialing", "canceling")
FREE_LIMITS = {"video": 1, "account": 1}  # ancien essai unique (cookie), plus utilisé pour bloquer


def _free_per_day() -> int:
    try:
        return max(1, int(os.getenv("FREE_ANALYSES_PER_DAY", "5")))
    except ValueError:
        return 5

WHOP_AUTHORIZE_URL = "https://api.whop.com/oauth/authorize"
WHOP_TOKEN_URL = "https://api.whop.com/oauth/token"
WHOP_USERINFO_URL = "https://api.whop.com/oauth/userinfo"
WHOP_MEMBERSHIPS_URL = "https://api.whop.com/api/v1/memberships"
WHOP_CHECKOUT_CONFIG_URL = "https://api.whop.com/api/v1/checkout_configurations"
WHOP_PAYMENTS_URL = "https://api.whop.com/api/v1/payments"

# Paiements confirmés PAR WHOP (webhook signé), instantanément : l'API de liste de Whop peut mettre plusieurs
# minutes à refléter un paiement, le webhook, lui, arrive en quelques secondes.
WEBHOOK_TOLERANCE_SECONDS = 300
BRIDGE_SECONDS = 24 * 3600  # un paiement confirmé par webhook compte comme abonnement le temps que l'API le reflète
_known_configs: dict[str, str] = {}      # id du lien de paiement créé par NOS soins -> notre référence
_grants_by_ref: dict[str, dict] = {}
_grants_by_config: dict[str, dict] = {}
_grants_by_user: dict[str, float] = {}   # id Whop -> instant de la confirmation
_last_webhook: dict = {}                  # dernier message reçu (type et NOMS des champs seulement, jamais de données personnelles)

_fallback_secret = secrets.token_urlsafe(32)
_secret_warned = False
_entitlement_cache: dict[str, tuple[float, bool, str | None]] = {}
_analysis_memory: dict[str, dict] = {}


def _env(name: str) -> str:
    """Variable d'environnement sans espaces ni retours à la ligne autour (fréquents quand on colle une clé)."""
    return os.getenv(name, "").strip()


def plan_prices() -> dict:
    """
    Prix affichés dans l'application (réglables sans toucher au code, via les variables d'environnement
    WIL_PRICE_MONTHLY, WIL_PRICE_YEARLY, WIL_PRICE_CURRENCY). Ils doivent correspondre aux plans créés dans Whop.
    """
    try:
        monthly = float(os.getenv("WIL_PRICE_MONTHLY", "10"))
        yearly = float(os.getenv("WIL_PRICE_YEARLY", "30"))
    except ValueError:
        monthly, yearly = 10.0, 30.0
    currency = os.getenv("WIL_PRICE_CURRENCY", "€")
    save_pct = max(0, round(100 * (1 - yearly / (monthly * 12)))) if monthly > 0 else 0
    return {
        "monthly": f"{monthly:g} {currency}",
        "yearly": f"{yearly:g} {currency}",
        "savePct": save_pct,
        "hasYearly": bool(_env("WHOP_CHECKOUT_URL_YEARLY")),
    }


def paywall_enabled() -> bool:
    return os.getenv("PAYWALL_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")


def _site_url() -> str:
    return os.getenv("SITE_URL", "https://wilapp.tech").rstrip("/")


def _secret() -> bytes:
    global _secret_warned
    value = os.getenv("SESSION_SECRET", "")
    if value:
        return value.encode()
    if not _secret_warned:
        print("[paywall] SESSION_SECRET manquant : secret éphémère (les connexions sautent à chaque redémarrage)")
        _secret_warned = True
    return _fallback_secret.encode()


def _is_https() -> bool:
    return _site_url().startswith("https://")


# ----------------------------------------------------------------- cookies signés
def _sign(payload: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def _unsign(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    raw, sig = token.rsplit(".", 1)
    expected = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    return payload


def _set_cookie(response, name: str, payload: dict, ttl: int) -> None:
    payload = {**payload, "exp": int(time.time()) + ttl}
    response.set_cookie(name, _sign(payload), max_age=ttl, httponly=True, samesite="lax", secure=_is_https())


def read_auth(request: Request) -> dict | None:
    auth = _unsign(request.cookies.get(AUTH_COOKIE))
    return auth if auth and auth.get("uid") else None


def safe_return_path(path: str | None, default: str = "/app") -> str:
    """Chemin interne uniquement (jamais une URL externe)."""
    if path and path.startswith("/") and not path.startswith("//") and "\\" not in path and "\n" not in path:
        return path
    return default


# ----------------------------------------------------------------- abonnement (Whop)
def _diag_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:80]


async def _whop_membership_call(user_id: str) -> tuple[bool, str | None, dict]:
    """
    Interroge Whop : ce compte a-t-il un abonnement valide ?
    Renvoie (actif, lien de gestion, diagnostic). Le diagnostic ({"http", "error"}) sert à /api/me?check=1.
    """
    api_key = _env("WHOP_API_KEY")
    if not api_key:
        print("[paywall] WHOP_API_KEY manquant : personne n'est considéré comme abonné")
        return False, None, {"http": None, "error": "api-key-missing"}
    params: dict = {"user_ids": [user_id], "statuses": list(ACTIVE_STATUSES), "first": 100}
    if _env("WHOP_COMPANY_ID"):
        params["account_id"] = _env("WHOP_COMPANY_ID")
    if _env("WHOP_PRODUCT_ID"):
        params["product_ids"] = [_env("WHOP_PRODUCT_ID")]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(WHOP_MEMBERSHIPS_URL, params=params, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError as exc:
        print(f"[paywall] Whop injoignable : {exc!r}")
        return False, None, {"http": None, "error": "network"}
    if response.status_code != 200:
        print(f"[paywall] Whop memberships {response.status_code}: {response.text[:300]}")
        try:
            payload = response.json()
            detail = payload.get("error") or payload.get("message") or ""
            if isinstance(detail, dict):
                detail = detail.get("message") or detail.get("code") or ""
        except Exception:
            detail = ""
        return False, None, {"http": response.status_code, "error": _diag_slug(str(detail)) or "error"}
    product_id = _env("WHOP_PRODUCT_ID")
    # Plans payants autorisés (WHOP_PLAN_IDS="plan_a,plan_b") : un accès GRATUIT (ex. « App Access ») ne doit
    # jamais compter comme un abonnement. Sans cette variable, seuls le statut et le produit sont vérifiés.
    allowed_plans = {x.strip() for x in _env("WHOP_PLAN_IDS").split(",") if x.strip()}
    for membership in response.json().get("data", []):
        # Filtrage local en plus des paramètres de la requête : on ne se fie jamais à un filtre ignoré.
        if (membership.get("user") or {}).get("id") != user_id:
            continue
        if membership.get("status") not in ACTIVE_STATUSES:
            continue
        if product_id and (membership.get("product") or {}).get("id") != product_id:
            continue
        if allowed_plans and (membership.get("plan") or {}).get("id") not in allowed_plans:
            continue
        return True, membership.get("manage_url"), {"http": 200, "error": None}
    return False, None, {"http": 200, "error": None}


async def _whop_membership(user_id: str) -> tuple[bool, str | None]:
    active, manage_url, _diag = await _whop_membership_call(user_id)
    return active, manage_url


def _prune_grants() -> None:
    cutoff = time.time() - BRIDGE_SECONDS
    for table in (_grants_by_ref, _grants_by_config):
        for key in [k for k, v in table.items() if v["ts"] < cutoff]:
            table.pop(key, None)
    for key in [k for k, v in _grants_by_user.items() if v < cutoff]:
        _grants_by_user.pop(key, None)


def webhook_grant_for(buyer: dict) -> tuple[str, str] | None:
    """(id Whop, e-mail) si Whop a déjà confirmé le paiement fait via le lien de paiement de ce navigateur."""
    grant = _grants_by_ref.get(buyer.get("ref") or "") or _grants_by_config.get(buyer.get("ch") or "")
    return (grant["uid"], grant["email"]) if grant else None


async def membership_status(user_id: str, force: bool = False) -> tuple[bool, str | None]:
    confirmed = _grants_by_user.get(user_id)
    if confirmed and time.time() - confirmed < BRIDGE_SECONDS:
        # Paiement confirmé par Whop (webhook) : actif tout de suite, sans attendre l'API de liste. On demande quand
        # même à l'API (au plus toutes les 60 s) pour récupérer le lien « Gérer mon abonnement » dès qu'elle le montre.
        cached = _entitlement_cache.get(user_id)
        if cached and cached[1] and (cached[2] or time.time() - cached[0] < 60):
            return True, cached[2]
        active, manage_url = await _whop_membership(user_id)
        _entitlement_cache[user_id] = (time.time(), True, manage_url if active else None)
        return True, manage_url if active else None
    cached = _entitlement_cache.get(user_id)
    if cached and not force and time.time() - cached[0] < ENTITLEMENT_CACHE_SECONDS:
        return cached[1], cached[2]
    active, manage_url = await _whop_membership(user_id)
    _entitlement_cache[user_id] = (time.time(), active, manage_url)
    return active, manage_url


async def get_entitlement(request: Request, force: bool = False) -> dict:
    auth = read_auth(request)
    if not paywall_enabled():
        # Tout est ouvert, mais on indique quand même si le visiteur est connecté via Whop (utile pour tester la connexion).
        return {"paywall": False, "subscribed": True, "logged_in": bool(auth), "email": auth.get("email") if auth else None, "manage_url": None}
    if not auth:
        return {"paywall": True, "subscribed": False, "logged_in": False, "email": None, "manage_url": None}
    active, manage_url = await membership_status(auth["uid"], force)
    return {"paywall": True, "subscribed": active, "logged_in": True, "email": auth.get("email"), "manage_url": manage_url}


async def require_subscription(request: Request) -> dict:
    ent = await get_entitlement(request)
    if not ent["subscribed"]:
        raise HTTPException(status_code=402, detail="Abonnement requis pour cette fonctionnalité.")
    return ent


# ----------------------------------------------------------------- essais gratuits
def _free_counts(request: Request) -> dict:
    data = _unsign(request.cookies.get(FREE_COOKIE)) or {}
    return {k: int(data.get(k, 0)) for k in FREE_LIMITS}


def check_free_analysis(request: Request, kind: str, subscribed: bool) -> None:
    """
    Chaque visiteur a droit à UNE analyse gratuite (vidéo, compte) ; la suivante est refusée tout de suite, avant
    l'envoi de la vidéo, avec l'offre d'abonnement. Filet de sécurité en plus (le cookie peut être effacé) :
    FREE_ANALYSES_PER_DAY (5 par défaut) analyses gratuites par jour et par adresse IP.
    """
    if subscribed:
        return
    if free_quota_left(request, kind) <= 0:
        raise HTTPException(status_code=402, detail="Votre analyse gratuite est utilisée. Abonnez-vous pour continuer.")
    try:
        ratelimit.check(request, f"free-{kind}", _free_per_day(), window=86400)
    except HTTPException:
        raise HTTPException(status_code=402, detail="Votre analyse gratuite est utilisée. Abonnez-vous pour continuer.")


def free_quota_left(request: Request, kind: str) -> int:
    return max(0, FREE_LIMITS.get(kind, 0) - _free_counts(request).get(kind, 0))


def mark_free_used(response, request: Request, kind: str) -> None:
    counts = _free_counts(request)
    counts[kind] = counts.get(kind, 0) + 1
    _set_cookie(response, FREE_COOKIE, counts, FREE_TTL_SECONDS)


# ----------------------------------------------------------------- rapports verrouillés
REPORT_RETENTION_DAYS = 180  # annoncé dans la politique de confidentialité
_PURGE_EVERY_SECONDS = 24 * 3600
_last_purge = 0.0


def purge_old_analyses(supabase) -> None:
    """Supprime les rapports plus vieux que REPORT_RETENTION_DAYS (au plus une fois par jour et par instance)."""
    global _last_purge
    now = time.time()
    if now - _last_purge < _PURGE_EVERY_SECONDS:
        return
    _last_purge = now
    cutoff = datetime.now(timezone.utc) - timedelta(days=REPORT_RETENTION_DAYS)
    try:
        supabase.table("analysis_results").delete().lt("created_at", cutoff.isoformat()).execute()
    except Exception as exc:
        print(f"[paywall] purge des anciens rapports impossible: {exc!r}")


def store_analysis(kind: str, payload: dict) -> str:
    """Conserve le rapport complet côté serveur et renvoie son identifiant (clé de déverrouillage)."""
    analysis_id = str(uuid.uuid4())
    supabase = get_supabase()
    if supabase:
        try:
            supabase.table("analysis_results").insert({"id": analysis_id, "kind": kind, "payload": payload}).execute()
            purge_old_analyses(supabase)
            return analysis_id
        except Exception as exc:
            print(f"[paywall] enregistrement du rapport impossible, repli mémoire: {exc!r}")
    _analysis_memory[analysis_id] = {"kind": kind, "payload": payload}
    return analysis_id


def load_analysis(analysis_id: str) -> dict | None:
    try:
        uuid.UUID(analysis_id)
    except ValueError:
        return None
    supabase = get_supabase()
    if supabase:
        try:
            res = supabase.table("analysis_results").select("kind,payload").eq("id", analysis_id).limit(1).execute()
            if res.data:
                return res.data[0]
        except Exception as exc:
            print(f"[paywall] lecture du rapport impossible: {exc!r}")
    return _analysis_memory.get(analysis_id)


# Ordre d'affichage des titres : points forts / points faibles d'abord.
_TEASER_SECTIONS = {
    "video": ["strengths", "weaknesses", "action_plan", "category_scores", "timeline", "hook_rewrites", "shooting_plan"],
    "account": ["strengths", "improvements", "category_scores", "action_plan", "content_ideas", "bio_rewrites", "stats", "suggested_hashtags"],
}


def build_teaser(kind: str, payload: dict, analysis_id: str) -> dict:
    """Ce que voit un non-abonné : uniquement les TITRES des sections (jamais leur contenu). Tout se débloque après paiement."""
    source = payload.get("ai_report", {}) if kind == "account" else payload
    sections = []
    for key in _TEASER_SECTIONS[kind]:
        if key == "stats":
            present = bool(payload.get("stats"))
        else:
            value = source.get(key)
            present = bool(value)
        if present:
            sections.append(key)
    return {"locked": True, "kind": kind, "unlock_id": analysis_id, "sections": sections}


@router.get("/api/analysis/{analysis_id}", response_class=JSONResponse)
async def get_analysis(analysis_id: str, request: Request):
    """
    Rapport d'une analyse déjà faite (rechargement de la page, retour après abonnement).
    Abonné : rapport complet. Non-abonné : seulement les titres des sections (teaser).
    """
    stored = await asyncio.to_thread(load_analysis, analysis_id)
    if not stored:
        raise HTTPException(status_code=404, detail="Rapport introuvable ou expiré.")
    headers = {"Cache-Control": "no-store"}
    if (await get_entitlement(request))["subscribed"]:
        return JSONResponse(content={"kind": stored["kind"], "report": stored["payload"]}, headers=headers)
    teaser = build_teaser(stored["kind"], stored["payload"], analysis_id)
    return JSONResponse(content={"kind": stored["kind"], "locked": True, "teaser": teaser}, headers=headers)


@router.get("/api/me", response_class=JSONResponse)
async def me(request: Request):
    ent = await get_entitlement(request)
    ent["free"] = {kind: free_quota_left(request, kind) for kind in FREE_LIMITS}
    # /api/me?check=1 (connecté uniquement) : teste en direct l'appel à Whop qui vérifie l'abonnement,
    # pour repérer une clé API sans les bonnes permissions AVANT d'activer le paywall.
    auth = read_auth(request)
    if request.query_params.get("check") and auth:
        active, _manage, diag = await _whop_membership_call(auth["uid"])
        ent = {**ent, "membership_check": {**diag, "active_membership": active}}
        # Parcours de paiement sans clic : la clé API doit pouvoir CRÉER un lien de paiement et LIRE les paiements.
        link, _cfg, why = await create_checkout_link(_plan_id_from_link(_env("WHOP_CHECKOUT_URL")), f"{_site_url()}/subscribe/done", "diagnostic")
        ent["checkout_create_ok"] = bool(link)
        ent["checkout_create_reason"] = why
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                probe = await client.get(WHOP_PAYMENTS_URL, params={"first": 1, "account_id": _env("WHOP_COMPANY_ID")}, headers=_whop_headers())
            ent["payments_read"] = {"http": probe.status_code}
        except Exception:
            ent["payments_read"] = {"http": None}
    return JSONResponse(content=ent, headers={"Cache-Control": "no-store"})


# ----------------------------------------------------------------- connexion Whop (OAuth 2.1 + PKCE)
def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


@router.get("/auth/whop/login")
async def whop_login(request: Request, to: str = "/app"):
    client_id = _env("WHOP_CLIENT_ID")
    if not client_id:
        raise HTTPException(status_code=503, detail="Connexion Whop non configurée.")
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    verifier, challenge = _pkce_pair()
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": f"{_site_url()}/auth/whop/callback",
        "scope": "openid profile email",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    response = RedirectResponse(f"{WHOP_AUTHORIZE_URL}?{urlencode(params)}")
    _set_cookie(response, OAUTH_COOKIE, {"state": state, "verifier": verifier, "to": safe_return_path(to)}, OAUTH_TTL_SECONDS)
    return response


def _token_failure_reason(response) -> str:
    """Traduit la réponse d'erreur de Whop en une raison courte (jamais de secret dans l'adresse)."""
    try:
        description = str(response.json().get("error_description", "")).lower()
    except Exception:
        description = ""
    if "client_secret is required" in description:
        return "secret_missing"
    if "client_secret is invalid" in description:
        return "secret_invalid"
    if "redirect" in description:
        return "redirect"
    if "code" in description or "grant" in description:
        return "code"
    # Raison inconnue : on donne le statut HTTP et le code d'erreur de Whop (ex. token_400_invalid_request),
    # des mots courts sans aucun secret, pour pouvoir diagnostiquer sans lire les journaux du serveur.
    try:
        payload = response.json()
        error_code = re.sub(r"[^a-z0-9_]", "", str(payload.get("error", "")).lower())[:30]
        detail = re.sub(r"[^a-z0-9]+", "-", description).strip("-")[:60]
    except Exception:
        error_code, detail = "", ""
    return f"token_{response.status_code}" + (f"_{error_code}" if error_code else "") + (f"~{detail}" if detail else "")


async def _exchange_code(code: str, verifier: str) -> tuple[dict | None, str]:
    """Échange le code contre un jeton. Renvoie (jeton, raison) ; la raison n'est utile qu'en cas d'échec."""
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": f"{_site_url()}/auth/whop/callback",
        "client_id": _env("WHOP_CLIENT_ID"),
        "code_verifier": verifier,
    }
    if _env("WHOP_CLIENT_SECRET"):
        body["client_secret"] = _env("WHOP_CLIENT_SECRET")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(WHOP_TOKEN_URL, json=body)
            if response.status_code == 415:  # format JSON refusé : on tente le format formulaire
                response = await client.post(WHOP_TOKEN_URL, data=body)
    except httpx.HTTPError as exc:
        print(f"[paywall] échange du code impossible: {exc!r}")
        return None, "network"
    if response.status_code != 200:
        print(f"[paywall] token Whop {response.status_code}: {response.text[:300]}")
        return None, _token_failure_reason(response)
    return response.json(), ""


def _login_failed(reason: str) -> RedirectResponse:
    return RedirectResponse(f"/app?login=failed&reason={reason}")


@router.get("/auth/whop/callback")
async def whop_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:  # l'utilisateur a refusé l'autorisation (ou Whop a signalé une erreur)
        return _login_failed("denied")
    saved = _unsign(request.cookies.get(OAUTH_COOKIE))
    if not code or not saved or not hmac.compare_digest(str(saved.get("state", "")), state):
        # Cookie de connexion absent ou expiré (10 min), ou état différent : recommencer depuis le début.
        return _login_failed("state")
    token, reason = await _exchange_code(code, saved["verifier"])
    if not token or not token.get("access_token"):
        return _login_failed(reason or "token")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            info = await client.get(WHOP_USERINFO_URL, headers={"Authorization": f"Bearer {token['access_token']}"})
    except httpx.HTTPError:
        return _login_failed("network")
    if info.status_code != 200 or not info.json().get("sub"):
        print(f"[paywall] userinfo Whop {info.status_code}: {info.text[:300]}")
        return _login_failed("userinfo")
    profile = info.json()
    response = RedirectResponse(safe_return_path(saved.get("to")))
    _set_cookie(response, AUTH_COOKIE, {"uid": profile["sub"], "email": profile.get("email", "")}, AUTH_TTL_SECONDS)
    response.delete_cookie(OAUTH_COOKIE)
    return response


@router.get("/auth/logout")
async def logout():
    response = RedirectResponse("/app")
    response.delete_cookie(AUTH_COOKIE)
    return response


# ----------------------------------------------------------------- parcours d'abonnement
def _plan_id_from_link(url: str) -> str:
    """Identifiant du plan (plan_...) extrait du lien de paiement configuré : pas de variable de plus à gérer."""
    match = re.search(r"plan_[A-Za-z0-9]+", url or "")
    return match.group(0) if match else ""


def _whop_headers() -> dict:
    return {"Authorization": f"Bearer {_env('WHOP_API_KEY')}"}


async def create_checkout_link(plan_id: str, redirect_url: str, ref: str) -> tuple[str, str, str]:
    """
    Crée, côté Whop, un lien de paiement PROPRE à ce visiteur : il porte notre identifiant (metadata) et ramène
    automatiquement le client sur notre site après le paiement. Renvoie (adresse de paiement, id du lien),
    ou ("", "") si Whop refuse (permissions de la clé, réseau...) : l'appelant se replie alors sur le lien fixe.
    Le 3e élément est la raison (mots courts, sans secret) : « ok » ou par ex. « 403-missing-permission... ».
    """
    if not _env("WHOP_API_KEY"):
        return "", "", "no-api-key"
    if not plan_id:
        return "", "", "no-plan-id"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                WHOP_CHECKOUT_CONFIG_URL,
                headers=_whop_headers(),
                json={"plan_id": plan_id, "redirect_url": redirect_url, "metadata": {"wil_ref": ref}},
            )
    except Exception as exc:
        print(f"[paywall] création du lien de paiement impossible : {exc!r}")
        return "", "", "network"
    if response.status_code not in (200, 201):
        print(f"[paywall] checkout_configurations {response.status_code}: {response.text[:300]}")
        try:
            payload = response.json()
            detail = payload.get("error") or payload.get("message") or ""
            if isinstance(detail, dict):
                detail = detail.get("message") or detail.get("code") or ""
        except Exception:
            detail = ""
        return "", "", f"{response.status_code}-{_diag_slug(str(detail))}".rstrip("-")
    try:
        data = response.json()
        url = str(data["purchase_url"])
        config_id = str(data["id"])
    except Exception:
        return "", "", "bad-response"
    if url.startswith("/"):
        url = "https://whop.com" + url
    return (url, config_id, "ok") if url.startswith("https://") else ("", "", "bad-url")


async def _payments_call(params: dict) -> tuple[int | None, list, str]:
    """Un appel à la liste des paiements. Renvoie (statut HTTP, paiements, raison courte en cas d'échec)."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(WHOP_PAYMENTS_URL, params=params, headers=_whop_headers())
    except Exception as exc:
        print(f"[paywall] recherche du paiement impossible : {exc!r}")
        return None, [], "network"
    if response.status_code != 200:
        print(f"[paywall] payments {response.status_code}: {response.text[:300]}")
        try:
            payload = response.json()
            detail = payload.get("error") or payload.get("message") or ""
            if isinstance(detail, dict):
                detail = detail.get("message") or detail.get("code") or ""
        except Exception:
            detail = ""
        return response.status_code, [], _diag_slug(str(detail)) or "error"
    return 200, response.json().get("data", []), ""


async def _recent_memberships(base: dict) -> tuple[int | None, list, str]:
    """Abonnements récents de l'entreprise ; chacun porte checkout_configuration_id (le lien de paiement utilisé)."""
    params = {**base, "order": "created_at", "direction": "desc", "first": 50}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(WHOP_MEMBERSHIPS_URL, params=params, headers=_whop_headers())
    except Exception as exc:
        print(f"[paywall] liste des abonnements impossible : {exc!r}")
        return None, [], "network"
    if response.status_code != 200:
        print(f"[paywall] memberships {response.status_code}: {response.text[:300]}")
        return response.status_code, [], "error"
    return 200, response.json().get("data", []), ""


async def lookup_buyer(config_id: str) -> dict:
    """
    Cherche chez Whop le paiement fait via CE lien de paiement. Plusieurs formes de requête sont essayées tour à
    tour (Whop est strict sur la façon d'écrire les filtres) ; un paiement n'est accepté que s'il appartient bien
    à ce lien, on ne se fie jamais à un filtre ignoré. Renvoie un dictionnaire détaillé (sert au diagnostic).
    """
    info: dict = {"http": None, "count": 0, "matched": False, "uid": "", "email": "", "payment_status": None,
                  "variant": None, "errors": []}
    base: dict = {}
    if _env("WHOP_COMPANY_ID"):
        base["account_id"] = _env("WHOP_COMPANY_ID")
    variants = [
        ("filter", {**base, "checkout_configuration_ids": [config_id], "include_free": "true", "first": 10}),
        ("filter-brackets", {**base, "checkout_configuration_ids[]": config_id, "include_free": "true", "first": 10}),
        ("filter-no-free", {**base, "checkout_configuration_ids": [config_id], "first": 10}),
        ("recent", {**base, "include_free": "true", "order": "created_at", "direction": "desc", "first": 50}),
        ("recent-no-free", {**base, "order": "created_at", "direction": "desc", "first": 50}),
        # Un achat à 0 $ (code promo 100 %) peut ne laisser AUCUN paiement : l'abonnement, lui, porte l'id du lien.
        ("memberships", {}),
    ]
    async def run(name: str, params: dict):
        if name == "memberships":
            return await _recent_memberships(base)
        return await _payments_call(params)

    # Tous les appels partent en même temps : on gagne plusieurs secondes sur chaque vérification.
    results = await asyncio.gather(*(run(name, params) for name, params in variants))
    for (name, _params), (status, payments, reason) in zip(variants, results):
        if info["http"] is None or status == 200:
            info["http"] = status
        if status != 200:
            info["errors"].append(f"{name}:{status}-{reason}")
            continue
        info["count"] = max(info["count"], len(payments))
        for payment in payments:
            user = payment.get("user") or {}
            linked = payment.get("checkout_configuration_id")
            # Si Whop ne renvoie pas l'identifiant du lien, on n'accepte que la réponse d'un filtre qui n'a rendu qu'un paiement.
            if user.get("id") and (linked == config_id or (linked is None and name.startswith("filter") and len(payments) == 1)):
                info.update(matched=True, uid=str(user["id"]), email=str(user.get("email") or ""),
                            payment_status=payment.get("status"), variant=name)
                return info
    return info
    return info


async def find_buyer(config_id: str) -> tuple[str, str]:
    """Qui a payé via ce lien de paiement ? Renvoie (id Whop, e-mail) ou ("", "") si aucun paiement n'est encore visible."""
    info = await lookup_buyer(config_id)
    return (info["uid"], info["email"]) if info["matched"] else ("", "")


@router.get("/subscribe")
async def subscribe(request: Request, to: str = "/app", plan: str = "monthly", diag: str = ""):
    """
    Envoie DIRECTEMENT vers la page de paiement Whop du plan choisi (e-mail + carte sur un seul écran), sans
    connexion avant. Le lien de paiement est créé pour CE visiteur : après le paiement, Whop le ramène tout seul
    sur /subscribe/done, qui retrouve qui a payé et débloque tout, sans aucun clic de sa part.
    """
    target = safe_return_path(to)
    plan = "yearly" if plan == "yearly" else "monthly"
    ent = await get_entitlement(request, force=True)
    if not ent["paywall"] or ent["subscribed"]:
        return RedirectResponse(target)
    ratelimit.check(request, "subscribe", 20)
    static_link = _env("WHOP_CHECKOUT_URL_YEARLY") if plan == "yearly" else ""
    static_link = static_link or _env("WHOP_CHECKOUT_URL")
    if not static_link:
        raise HTTPException(status_code=503, detail="Les abonnements ne sont pas encore disponibles.")
    redirect_url = f"{_site_url()}/subscribe/done?to={quote(target, safe='')}"
    ref = secrets.token_urlsafe(12)
    link, config_id, reason = await create_checkout_link(_plan_id_from_link(static_link), redirect_url, ref)
    response = RedirectResponse(link or static_link)
    # Indicateur de diagnostic (aucun secret) : montre si le lien personnalisé a pu être créé, et sinon pourquoi.
    response.headers["X-Wil-Checkout"] = "personalized" if link else f"fallback-{reason}"
    if diag:  # ?diag=1 : teste aussi la permission de LIRE les paiements (sans aucun secret ni donnée de client)
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                probe = await client.get(
                    WHOP_PAYMENTS_URL, params={"first": 1, "account_id": _env("WHOP_COMPANY_ID")}, headers=_whop_headers()
                )
            body = ""
            if probe.status_code != 200:
                try:
                    payload = probe.json()
                    detail = payload.get("error") or payload.get("message") or ""
                    body = _diag_slug(str(detail.get("message") if isinstance(detail, dict) else detail))
                except Exception:
                    body = ""
            response.headers["X-Wil-Payments"] = f"{probe.status_code}" + (f"-{body}" if body else "")
        except Exception:
            response.headers["X-Wil-Payments"] = "network"
    _set_cookie(response, RETURN_COOKIE, {"to": target}, 3600)
    if config_id:  # retient QUEL lien de paiement ce navigateur a ouvert, pour retrouver l'acheteur ensuite
        _known_configs[config_id] = ref
        _set_cookie(response, BUYER_COOKIE, {"ch": config_id, "ref": ref}, 24 * 3600)
    return response


def _page_lang(request: Request) -> str:
    lang = request.cookies.get("wil_lang", "")
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


async def _recognize_buyer(buyer: dict) -> tuple[str, str] | None:
    """Retrouve l'acheteur du lien de paiement de ce navigateur ET vérifie que son abonnement est actif."""
    if not buyer.get("ch"):
        return None
    confirmed = webhook_grant_for(buyer)  # Whop nous a déjà prévenus : aucun appel à l'API, réponse immédiate
    if confirmed:
        return confirmed
    uid, email = await find_buyer(buyer["ch"])
    if not uid:
        return None
    active, _manage = await membership_status(uid, force=True)
    return (uid, email) if active else None


def _grant_login(response, uid: str, email: str) -> None:
    _set_cookie(response, AUTH_COOKIE, {"uid": uid, "email": email}, AUTH_TTL_SECONDS)
    response.delete_cookie(RETURN_COOKIE)
    response.delete_cookie(BUYER_COOKIE)


@router.get("/subscribe/done", response_class=HTMLResponse)
async def subscribe_done(request: Request, to: str = "", n: int = 0, poll: str = ""):
    """
    Retour du paiement Whop : on retrouve qui a payé grâce au lien de paiement de ce navigateur, on vérifie son
    abonnement, on le connecte et on le renvoie sur son rapport, déverrouillé. Sans lien de paiement mémorisé
    (autre appareil, « J'ai déjà un abonnement »), on passe par la connexion Whop.
    La page d'attente interroge cette même adresse avec ?poll=1 (réponse JSON) toutes les 1,5 s : elle débloque
    l'utilisateur dès que l'abonnement est visible, sans recharger la page.
    """
    back = safe_return_path(to or (_unsign(request.cookies.get(RETURN_COOKIE)) or {}).get("to"))
    n = max(0, min(n, 50))
    ent = await get_entitlement(request, force=True)
    buyer = _unsign(request.cookies.get(BUYER_COOKIE)) or {}
    no_store = {"Cache-Control": "no-store"}

    if poll:
        if not ent["paywall"] or ent["subscribed"]:
            return JSONResponse(content={"status": "ok", "to": back}, headers=no_store)
        found = await _recognize_buyer(buyer)
        if found:
            response = JSONResponse(content={"status": "ok", "to": back}, headers=no_store)
            _grant_login(response, *found)
            return response
        return JSONResponse(content={"status": "waiting"}, headers=no_store)

    if not ent["paywall"] or ent["subscribed"]:
        response = RedirectResponse(back)
        response.delete_cookie(RETURN_COOKIE)
        return response
    if request.query_params.get("diag"):
        # Diagnostic (aucun secret) : montre à quelle étape la reconnaissance de l'acheteur s'arrête.
        report: dict = {"subscribed": ent["subscribed"], "logged_in": ent["logged_in"], "buyer_cookie": bool(buyer.get("ch")),
                        "checkout_config": buyer.get("ch"), "webhook_confirmed": bool(webhook_grant_for(buyer)),
                        "webhook_configured": bool(_env("WHOP_WEBHOOK_SECRET")), "last_webhook": dict(_last_webhook) or None}
        if buyer.get("ch"):
            started = time.time()
            found_info = await lookup_buyer(buyer["ch"])
            report["payments"] = {k: found_info[k] for k in ("http", "count", "matched", "payment_status", "variant", "errors")}
            report["lookup_ms"] = int((time.time() - started) * 1000)
            if found_info["matched"]:
                active, _manage, diag = await _whop_membership_call(found_info["uid"])
                report["membership"] = {**diag, "active": active}
        return JSONResponse(content=report, headers=no_store)
    if buyer.get("ch"):
        found = await _recognize_buyer(buyer)
        if found:
            response = RedirectResponse(back)
            _grant_login(response, *found)
            return response
    elif not ent["logged_in"]:
        here = f"/subscribe/done?to={quote(back, safe='')}&n={n}"
        return RedirectResponse(f"/auth/whop/login?to={quote(here, safe='')}")

    lang = _page_lang(request)
    here = f"/subscribe/done?to={quote(back, safe='')}&n={n}"
    style = (
        "<style>body{font-family:system-ui,sans-serif;max-width:440px;margin:80px auto;padding:0 20px;text-align:center;color:#0F172A}"
        "a{color:#2563EB}.btn{display:inline-block;margin-top:14px;padding:14px 22px;border-radius:12px;background:#2563EB;color:#fff;"
        "font-weight:700;text-decoration:none}.btn:hover{background:#7C3AED}p{line-height:1.5;color:#475569}"
        ".spin{width:44px;height:44px;margin:0 auto 18px;border:5px solid #DBEAFE;border-top-color:#2563EB;border-radius:50%;animation:s 0.9s linear infinite}"
        "@keyframes s{to{transform:rotate(360deg)}}</style>"
    )
    head = f'<!DOCTYPE html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Wil App</title>{style}'
    if n >= 15:  # ~1 minute sans abonnement trouvé : on arrête d'attendre et on explique
        retry = f"/subscribe/done?to={quote(back, safe='')}&n=0"
        signin = f"/auth/whop/login?to={quote(retry, safe='')}"
        return HTMLResponse(
            f"""{head}</head><body><h1 style="font-size:22px">{t(lang, "pw_not_found_title")}</h1>
<p>{t(lang, "pw_not_found_sub")}</p><a class="btn" href="{retry}">{t(lang, "pw_retry")}</a>
<p><a href="{signin}">{t(lang, "pw_signin_whop")}</a></p><p><a href="{back}">{t(lang, "pw_back_app")}</a></p></body></html>"""
        )
    poll_url = f"/subscribe/done?poll=1&to={quote(back, safe='')}"
    fallback = f"/subscribe/done?to={quote(back, safe='')}&n=15"
    next_page = here.replace(f"&n={n}", f"&n={n + 1}")
    return HTMLResponse(
        f"""{head}<noscript><meta http-equiv="refresh" content="4;url={next_page}"></noscript></head><body>
<div class="spin"></div><h1 style="font-size:22px">{t(lang, "pw_checking_title")}</h1><p>{t(lang, "pw_checking_sub")}</p>
<script>
(function () {{
  var tries = 0;
  function tick() {{
    fetch({json.dumps(poll_url)}, {{cache: 'no-store', credentials: 'same-origin'}})
      .then(function (r) {{ return r.json(); }})
      .then(function (d) {{ if (d && d.status === 'ok') {{ location.replace(d.to); }} else {{ next(); }} }})
      .catch(next);
  }}
  function next() {{ tries += 1; if (tries >= 40) {{ location.replace({json.dumps(fallback)}); }} else {{ setTimeout(tick, 1500); }} }}
  tick();
}})();
</script></body></html>"""
    )


def _webhook_signature_ok(headers, body: bytes) -> bool:
    """
    Vérifie la signature Whop (Standard Webhooks) : HMAC-SHA256 de « {webhook-id}.{webhook-timestamp}.{corps} »
    avec le secret `ws_...` utilisé tel quel, comparé en temps constant ; un message trop ancien est refusé.
    """
    secret = _env("WHOP_WEBHOOK_SECRET")
    msg_id, timestamp, signature = headers.get("webhook-id", ""), headers.get("webhook-timestamp", ""), headers.get("webhook-signature", "")
    if not (secret and msg_id and timestamp and signature):
        return False
    try:
        if abs(time.time() - int(timestamp)) > WEBHOOK_TOLERANCE_SECONDS:
            return False
    except ValueError:
        return False
    expected = base64.b64encode(
        hmac.new(secret.encode(), f"{msg_id}.{timestamp}.".encode() + body, hashlib.sha256).digest()
    ).decode()
    for candidate in signature.split():
        version, _, value = candidate.partition(",")
        if version == "v1" and hmac.compare_digest(value, expected):
            return True
    return False


def _read_paid_event(payload: dict) -> dict | None:
    """Extrait (utilisateur, lien de paiement, référence) d'un paiement réussi / abonnement activé, sinon None."""
    if payload.get("type") not in ("payment.succeeded", "membership.activated"):
        return None
    data = payload.get("data") or {}
    user = data.get("user") or (data.get("membership") or {}).get("user") or {}
    uid = user.get("id") or data.get("user_id")
    if not uid:
        return None
    config = data.get("checkout_configuration_id") or (data.get("checkout_configuration") or {}).get("id") or ""
    ref = (data.get("metadata") or {}).get("wil_ref") or ""
    # Sécurité : seuls comptent les paiements faits via un lien de paiement créé par NOS soins (notre marqueur
    # `wil_ref`, ou un lien que ce serveur connaît). Le paiement d'un autre produit ne débloque jamais rien.
    if not (ref or config in _known_configs):
        return None
    allowed = {x.strip() for x in _env("WHOP_PLAN_IDS").split(",") if x.strip()}
    plan_id = (data.get("plan") or {}).get("id")
    if allowed and plan_id and plan_id not in allowed:
        return None
    return {"uid": str(uid), "email": str(user.get("email") or ""), "config": str(config), "ref": str(ref or _known_configs.get(config, ""))}


@router.post("/webhooks/whop")
async def whop_webhook(request: Request):
    """Whop nous prévient dès qu'un paiement réussit : l'abonné est débloqué en quelques secondes."""
    body = await request.body()
    if not _env("WHOP_WEBHOOK_SECRET"):
        raise HTTPException(status_code=503, detail="Webhook non configuré.")
    if not _webhook_signature_ok(request.headers, body):
        raise HTTPException(status_code=401, detail="Signature invalide.")
    try:
        payload = json.loads(body)
        event = _read_paid_event(payload)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Message illisible.")
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    _last_webhook.clear()
    _last_webhook.update(type=str(payload.get("type", ""))[:40], matched=bool(event), at=int(time.time()),
                         data_keys=sorted(str(k) for k in data)[:30],
                         has_metadata_ref=bool((data.get("metadata") or {}).get("wil_ref")) if isinstance(data.get("metadata"), dict) else False,
                         has_checkout_config=bool(data.get("checkout_configuration_id") or data.get("checkout_configuration")))
    if event:
        _prune_grants()
        grant = {"uid": event["uid"], "email": event["email"], "ts": time.time()}
        if event["ref"]:
            _grants_by_ref[event["ref"]] = grant
        if event["config"]:
            _grants_by_config[event["config"]] = grant
        _grants_by_user[event["uid"]] = grant["ts"]
        _entitlement_cache.pop(event["uid"], None)
        print(f"[paywall] webhook : paiement confirmé pour {event['uid']}")
    return JSONResponse(content={"ok": True})


# ----------------------------------------------------------------- composants d'interface partagés
_UI_JS = r"""
const WIL_PW = __L__;
(function () {
  if (document.getElementById('wil-pw-style')) return;
  const st = document.createElement('style');
  st.id = 'wil-pw-style';
  st.textContent =
    '.wilpw{max-width:520px;margin:0 auto 16px;text-align:left}' +
    '.wilpw-head{text-align:center;margin:8px 0 20px}' +
    '.wilpw-ic{width:56px;height:56px;border-radius:50%;background:#EFF6FF;display:flex;align-items:center;justify-content:center;font-size:26px;margin:0 auto 12px}' +
    '.wilpw-head h2{font-size:20px;font-weight:800;margin:0 0 6px;color:#0F172A}' +
    '.wilpw-head p{font-size:14px;color:#64748B;margin:0;line-height:1.5}' +
    '.wilpw-card{background:#fff;border:1px solid #E2E8F0;border-radius:16px;padding:16px 18px;margin-bottom:10px}' +
    '.wilpw-row{display:flex;justify-content:space-between;align-items:center;font-weight:700;font-size:14px;color:#0F172A}' +
    '.wilpw-skel{margin-top:12px;filter:blur(3px);opacity:.7}' +
    '.wilpw-skel i{display:block;height:9px;border-radius:6px;background:#CBD5E1;margin-bottom:8px}' +
    '.wilpw-btn{display:block;text-align:center;margin-top:18px;padding:16px;border-radius:12px;background:#2563EB;color:#fff!important;font-weight:700;font-size:18px;text-decoration:none;box-shadow:0 6px 16px rgba(37,99,235,.25);transition:background .2s}' +
    '.wilpw-btn:hover{background:#7C3AED}' +
    '.wilpw-link{display:block;text-align:center;margin-top:12px;font-size:14px;font-weight:600;color:#2563EB;text-decoration:none}' +
    '.wilpw-btn + .wilpw-btn{margin-top:10px}' +
    '.wilpw-sub{display:block;font-size:12px;font-weight:600;opacity:.92;margin-top:2px}' +
    '.wilpw-note{text-align:center;font-size:12px;color:#64748B;margin:12px 0 0}' +
    '.wilpw-plans{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:22px}' +
    '.wilpw-plans-one{grid-template-columns:minmax(0,1fr);max-width:280px;margin-left:auto;margin-right:auto}' +
    '.wilpw-plan{position:relative;display:flex;flex-direction:column;background:#fff;border:1.5px solid #C4B5FD;border-radius:16px;padding:18px 12px 12px}' +
    '.wilpw-plan-best{border:2px solid #7C3AED;box-shadow:0 6px 18px rgba(124,58,237,.2)}' +
    '.wilpw-badge{position:absolute;top:-11px;left:50%;transform:translateX(-50%);background:#7C3AED;color:#fff;font-size:10.5px;font-weight:700;padding:3px 9px;border-radius:999px;white-space:nowrap}' +
    '.wilpw-plan-name{font-size:14px;font-weight:800;margin:2px 0;text-align:center;color:#0F172A}' +
    '.wilpw-plan-price{font-size:26px;font-weight:800;text-align:center;margin:0 0 2px;color:#2563EB}' +
    '.wilpw-plan-price span{font-size:12px;font-weight:600;color:#64748B;margin-left:3px}' +
    '.wilpw-plan-save{text-align:center;font-size:11.5px;font-weight:700;color:#16A34A;margin:0 0 10px;min-height:16px}' +
    '.wilpw-feats{list-style:none;padding:0;margin:0 0 12px;font-size:12px;line-height:1.4;color:#334155;flex:1}' +
    '.wilpw-feats li{position:relative;padding-left:16px;margin-bottom:7px}' +
    '.wilpw-feats li:before{content:"✓";position:absolute;left:0;color:#16A34A;font-weight:800}' +
    '.wilpw-plan .wilpw-btn{margin-top:auto;padding:11px 8px;font-size:14px}';
  document.head.appendChild(st);
})();
function wilPwEsc(text) {
  return String(text == null ? '' : text).replace(/[&<>"']/g, function (c) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
  });
}
function wilSubscribeHref(returnPath, plan) {
  return '/subscribe?to=' + encodeURIComponent(returnPath) + (plan ? '&plan=' + plan : '');
}
// Boutons d'abonnement : annuel (mis en avant) + mensuel quand les deux plans existent, sinon le seul plan mensuel.
// Cartes d'abonnement côte à côte (mensuel à gauche, annuel mis en avant à droite), avec tout ce que comprend le plan payant.
function wilPwActions(returnPath) {
  const P = WIL_PW.plans;
  const href = function (plan) { return wilPwEsc(wilSubscribeHref(returnPath, plan)); };
  const feats = '<ul class="wilpw-feats">' + (WIL_PW.feats || []).map(function (f) { return '<li>' + wilPwEsc(f) + '</li>'; }).join('') + '</ul>';
  const card = function (plan, title, price, per, best, save) {
    return '<div class="wilpw-plan' + (best ? ' wilpw-plan-best' : '') + '">' +
      (best ? '<span class="wilpw-badge">' + wilPwEsc(WIL_PW.best) + '</span>' : '') +
      '<p class="wilpw-plan-name">' + wilPwEsc(title) + '</p>' +
      '<p class="wilpw-plan-price">' + wilPwEsc(price) + '<span>' + wilPwEsc(per) + '</span></p>' +
      '<p class="wilpw-plan-save">' + (save ? wilPwEsc(save) : '&nbsp;') + '</p>' + feats +
      '<a class="wilpw-btn" href="' + href(plan) + '">' + wilPwEsc(WIL_PW.choose) + '</a></div>';
  };
  let html = '<div class="wilpw-plans' + (P.hasYearly ? '' : ' wilpw-plans-one') + '">';
  if (P.hasYearly) {
    // Mensuel à gauche, annuel (mis en avant) à droite.
    html += card('monthly', WIL_PW.planMonthly, P.monthly, WIL_PW.perMonth, false, '') +
      card('yearly', WIL_PW.planYearly, P.yearly, WIL_PW.perYear, true, P.savePct > 0 ? WIL_PW.save.replace('{pct}', P.savePct) : '');
  } else {
    html += card('monthly', WIL_PW.planMonthly, P.monthly, WIL_PW.perMonth, true, '');
  }
  return html + '</div><p class="wilpw-note">' + wilPwEsc(WIL_PW.cancel) + '</p>' +
    '<a class="wilpw-link" href="' + wilPwEsc('/subscribe/done?to=' + encodeURIComponent(returnPath)) + '">' + wilPwEsc(WIL_PW.have) + '</a>';
}
function wilLockedReportHtml(titles, returnPath) {
  const cards = titles.map(function (title) {
    return '<div class="wilpw-card"><div class="wilpw-row"><span>' + wilPwEsc(title) + '</span><span>🔒</span></div>' +
      '<div class="wilpw-skel"><i style="width:94%"></i><i style="width:78%"></i><i style="width:62%"></i></div></div>';
  }).join('');
  return '<div class="wilpw"><div class="wilpw-head"><div class="wilpw-ic">🔒</div><h2>' + wilPwEsc(WIL_PW.title) + '</h2><p>' +
    wilPwEsc(WIL_PW.sub) + '</p></div>' + cards + wilPwActions(returnPath) + '</div>';
}
// Fonctionnalité réservée aux abonnés (ou essai gratuit déjà utilisé).
function wilNoticeHtml(title, text, returnPath) {
  return '<div class="wilpw"><div class="wilpw-head"><div class="wilpw-ic">🔒</div><h2>' + wilPwEsc(title) + '</h2><p>' +
    wilPwEsc(text) + '</p></div>' + wilPwActions(returnPath) + '</div>';
}
// Rapports gardés dans le navigateur : une actualisation de la page réaffiche le rapport sans relancer l'analyse.
const WIL_REPORTS_KEY = 'wilReports';
function wilReportsRead() {
  try { return JSON.parse(localStorage.getItem(WIL_REPORTS_KEY) || '{}') || {}; } catch (e) { return {}; }
}
function wilGetCachedReport(id) { return wilReportsRead()[id] || null; }
function wilCacheReport(id, entry) {
  try {
    const all = wilReportsRead();
    all[id] = Object.assign({ts: Date.now()}, entry);
    const kept = {};
    Object.keys(all).sort(function (a, b) { return all[b].ts - all[a].ts; }).slice(0, 8).forEach(function (k) { kept[k] = all[k]; });
    localStorage.setItem(WIL_REPORTS_KEY, JSON.stringify(kept));
  } catch (e) {}
}
function wilUnlockId() {
  try {
    const id = new URLSearchParams(location.search).get('unlock');
    return id && /^[0-9a-fA-F-]{36}$/.test(id) ? id : null;
  } catch (e) { return null; }
}
function wilLoadUnlocked(id) {
  return fetch('/api/analysis/' + encodeURIComponent(id)).then(function (r) {
    return r.json().then(function (data) {
      if (!r.ok) { const err = new Error('http ' + r.status); err.status = r.status; throw err; }
      return data;
    });
  });
}

"""


def ui_js(tt) -> str:
    """JS partagé (panneau « verrouillé », bouton d'abonnement) avec les textes dans la langue de la page."""
    labels = {
        "title": tt("pw_locked_title"),
        "sub": tt("pw_locked_sub"),
        "btn": tt("pw_subscribe_btn"),
        "have": tt("pw_have_sub"),
        "unlocking": tt("pw_unlocking"),
        "error": tt("pw_unlock_error"),
        "trial": tt("pw_trial_used"),
        "featTitle": tt("pw_feature_title"),
        "featSub": tt("pw_feature_sub"),
        "active": tt("pw_active"),
        "free": tt("pw_free_plan"),
        "manage": tt("pw_manage"),
        "logout": tt("pw_logout"),
        "planMonthly": tt("pw_plan_monthly"),
        "planYearly": tt("pw_plan_yearly"),
        "perMonth": tt("pw_per_month"),
        "perYear": tt("pw_per_year"),
        "save": tt("pw_save"),
        "best": tt("pw_best_value"),
        "cancel": tt("pw_cancel_anytime"),
        "plans": plan_prices(),
        "feats": [tt("pw_pro_feat1"), tt("pw_pro_feat2"), tt("pw_pro_feat3")],
        "choose": tt("pw_choose"),
    }
    return _UI_JS.replace("__L__", json.dumps(labels, ensure_ascii=False).replace("</", "<\\/")) + errors.error_js(tt)
