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
  WHOP_COMPANY_ID (biz_...), WHOP_PRODUCT_ID (optionnel), WHOP_CHECKOUT_URL.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from urllib.parse import quote, urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.db import get_supabase

router = APIRouter()

AUTH_COOKIE = "wil_auth"
OAUTH_COOKIE = "wil_oauth"
FREE_COOKIE = "wil_free"
RETURN_COOKIE = "wil_return"
AUTH_TTL_SECONDS = 30 * 24 * 3600
OAUTH_TTL_SECONDS = 10 * 60
FREE_TTL_SECONDS = 365 * 24 * 3600
ENTITLEMENT_CACHE_SECONDS = 120
ACTIVE_STATUSES = ("active", "trialing", "canceling")
FREE_LIMITS = {"video": 1, "account": 1}

WHOP_AUTHORIZE_URL = "https://api.whop.com/oauth/authorize"
WHOP_TOKEN_URL = "https://api.whop.com/oauth/token"
WHOP_USERINFO_URL = "https://api.whop.com/oauth/userinfo"
WHOP_MEMBERSHIPS_URL = "https://api.whop.com/api/v1/memberships"

_fallback_secret = secrets.token_urlsafe(32)
_secret_warned = False
_entitlement_cache: dict[str, tuple[float, bool, str | None]] = {}
_analysis_memory: dict[str, dict] = {}


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
async def _whop_membership(user_id: str) -> tuple[bool, str | None]:
    """Interroge Whop : ce compte a-t-il un abonnement valide ? Renvoie (actif, lien de gestion)."""
    api_key = os.getenv("WHOP_API_KEY", "")
    if not api_key:
        print("[paywall] WHOP_API_KEY manquant : personne n'est considéré comme abonné")
        return False, None
    params: dict = {"user_ids": [user_id], "statuses": list(ACTIVE_STATUSES), "first": 100}
    if os.getenv("WHOP_COMPANY_ID"):
        params["account_id"] = os.getenv("WHOP_COMPANY_ID")
    if os.getenv("WHOP_PRODUCT_ID"):
        params["product_ids"] = [os.getenv("WHOP_PRODUCT_ID")]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(WHOP_MEMBERSHIPS_URL, params=params, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError as exc:
        print(f"[paywall] Whop injoignable : {exc!r}")
        return False, None
    if response.status_code != 200:
        print(f"[paywall] Whop memberships {response.status_code}: {response.text[:300]}")
        return False, None
    product_id = os.getenv("WHOP_PRODUCT_ID")
    for membership in response.json().get("data", []):
        # Filtrage local en plus des paramètres de la requête : on ne se fie jamais à un filtre ignoré.
        if (membership.get("user") or {}).get("id") != user_id:
            continue
        if membership.get("status") not in ACTIVE_STATUSES:
            continue
        if product_id and (membership.get("product") or {}).get("id") != product_id:
            continue
        return True, membership.get("manage_url")
    return False, None


async def membership_status(user_id: str, force: bool = False) -> tuple[bool, str | None]:
    cached = _entitlement_cache.get(user_id)
    if cached and not force and time.time() - cached[0] < ENTITLEMENT_CACHE_SECONDS:
        return cached[1], cached[2]
    active, manage_url = await _whop_membership(user_id)
    _entitlement_cache[user_id] = (time.time(), active, manage_url)
    return active, manage_url


async def get_entitlement(request: Request, force: bool = False) -> dict:
    if not paywall_enabled():
        return {"paywall": False, "subscribed": True, "logged_in": False, "email": None, "manage_url": None}
    auth = read_auth(request)
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


def free_quota_left(request: Request, kind: str) -> int:
    return max(0, FREE_LIMITS.get(kind, 0) - _free_counts(request).get(kind, 0))


def mark_free_used(response, request: Request, kind: str) -> None:
    counts = _free_counts(request)
    counts[kind] = counts.get(kind, 0) + 1
    _set_cookie(response, FREE_COOKIE, counts, FREE_TTL_SECONDS)


# ----------------------------------------------------------------- rapports verrouillés
def store_analysis(kind: str, payload: dict) -> str:
    """Conserve le rapport complet côté serveur et renvoie son identifiant (clé de déverrouillage)."""
    analysis_id = str(uuid.uuid4())
    supabase = get_supabase()
    if supabase:
        try:
            supabase.table("analysis_results").insert({"id": analysis_id, "kind": kind, "payload": payload}).execute()
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
    "account": ["strengths", "improvements", "stats", "suggested_hashtags"],
}


def build_teaser(kind: str, payload: dict, analysis_id: str) -> dict:
    """Ce que voit un non-abonné : uniquement les TITRES des sections (jamais leur contenu)."""
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
    stored = load_analysis(analysis_id)
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
    return JSONResponse(content=ent, headers={"Cache-Control": "no-store"})


# ----------------------------------------------------------------- connexion Whop (OAuth 2.1 + PKCE)
def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


@router.get("/auth/whop/login")
async def whop_login(request: Request, to: str = "/app"):
    client_id = os.getenv("WHOP_CLIENT_ID", "")
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


async def _exchange_code(code: str, verifier: str) -> dict | None:
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": f"{_site_url()}/auth/whop/callback",
        "client_id": os.getenv("WHOP_CLIENT_ID", ""),
        "code_verifier": verifier,
    }
    if os.getenv("WHOP_CLIENT_SECRET"):
        body["client_secret"] = os.getenv("WHOP_CLIENT_SECRET")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(WHOP_TOKEN_URL, json=body)
            if response.status_code in (400, 415):  # certains serveurs OAuth n'acceptent que le format formulaire
                response = await client.post(WHOP_TOKEN_URL, data=body)
    except httpx.HTTPError as exc:
        print(f"[paywall] échange du code impossible: {exc!r}")
        return None
    if response.status_code != 200:
        print(f"[paywall] token Whop {response.status_code}: {response.text[:300]}")
        return None
    return response.json()


@router.get("/auth/whop/callback")
async def whop_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    saved = _unsign(request.cookies.get(OAUTH_COOKIE))
    if error or not code or not saved or not hmac.compare_digest(str(saved.get("state", "")), state):
        return RedirectResponse("/app?login=failed")
    token = await _exchange_code(code, saved["verifier"])
    if not token or not token.get("access_token"):
        return RedirectResponse("/app?login=failed")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            info = await client.get(WHOP_USERINFO_URL, headers={"Authorization": f"Bearer {token['access_token']}"})
    except httpx.HTTPError:
        return RedirectResponse("/app?login=failed")
    if info.status_code != 200 or not info.json().get("sub"):
        return RedirectResponse("/app?login=failed")
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
@router.get("/subscribe")
async def subscribe(request: Request, to: str = "/app"):
    """Se connecter à Whop si besoin, puis envoyer vers le paiement (ou revenir si déjà abonné)."""
    target = safe_return_path(to)
    ent = await get_entitlement(request, force=True)
    if not ent["paywall"] or ent["subscribed"]:
        return RedirectResponse(target)
    if not ent["logged_in"]:
        return RedirectResponse(f"/auth/whop/login?to={quote('/subscribe?to=' + quote(target, safe=''), safe='')}")
    checkout = os.getenv("WHOP_CHECKOUT_URL", "")
    if not checkout:
        raise HTTPException(status_code=503, detail="Les abonnements ne sont pas encore disponibles.")
    response = RedirectResponse(checkout)
    _set_cookie(response, RETURN_COOKIE, {"to": target}, 3600)
    return response


@router.get("/subscribe/done", response_class=HTMLResponse)
async def subscribe_done(request: Request):
    """Retour du paiement Whop : on revérifie l'abonnement puis on renvoie l'utilisateur où il en était."""
    ent = await get_entitlement(request, force=True)
    back = safe_return_path((_unsign(request.cookies.get(RETURN_COOKIE)) or {}).get("to"))
    if ent["subscribed"]:
        response = RedirectResponse(back)
        response.delete_cookie(RETURN_COOKIE)
        return response
    return HTMLResponse(
        f"""<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="6"><title>Wil App</title>
<style>body{{font-family:system-ui,sans-serif;max-width:420px;margin:80px auto;padding:0 20px;text-align:center;color:#0F172A}}
a{{color:#2563EB}}</style></head><body>
<h1 style="font-size:22px">Validation du paiement…</h1>
<p>Nous vérifions votre abonnement. Cette page se met à jour toute seule.</p>
<p><a href="{back}">Revenir à l'application</a></p></body></html>"""
    )


# ----------------------------------------------------------------- composants d'interface partagés
_UI_JS = r"""
const WIL_PW = __L__;
(function () {
  if (document.getElementById('wil-pw-style')) return;
  const st = document.createElement('style');
  st.id = 'wil-pw-style';
  st.textContent =
    '.wilpw{max-width:480px;margin:0 auto 16px;text-align:left}' +
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
    '.wilpw-link{display:block;text-align:center;margin-top:12px;font-size:14px;font-weight:600;color:#2563EB;text-decoration:none}';
  document.head.appendChild(st);
})();
function wilPwEsc(text) {
  return String(text == null ? '' : text).replace(/[&<>"']/g, function (c) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
  });
}
function wilSubscribeHref(returnPath) { return '/subscribe?to=' + encodeURIComponent(returnPath); }
function wilPwActions(returnPath) {
  return '<a class="wilpw-btn" href="' + wilPwEsc(wilSubscribeHref(returnPath)) + '">' + wilPwEsc(WIL_PW.btn) + '</a>' +
    '<a class="wilpw-link" href="' + wilPwEsc(wilSubscribeHref(returnPath)) + '">' + wilPwEsc(WIL_PW.have) + '</a>';
}
// Rapport verrouillé : uniquement les TITRES des sections, leur contenu est grisé (jamais envoyé par le serveur).
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
    }
    return _UI_JS.replace("__L__", json.dumps(labels, ensure_ascii=False).replace("</", "<\\/"))
