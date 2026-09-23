"""
Point d'entrée de l'API backend.

Comment lancer ce serveur (depuis le dossier blowup-backend) :
    uvicorn app.main:app --reload

Puis ouvre dans ton navigateur : http://127.0.0.1:8000/docs
Tu verras une interface interactive générée automatiquement par FastAPI
qui liste toutes les routes disponibles. C'est très pratique pour tester
sans avoir besoin de l'app mobile.

Pour tester le flow TikTok complet (obligatoire car TikTok exige une vraie
URL publique), il faut que ton tunnel Cloudflare tourne en parallèle et que
la variable TIKTOK_REDIRECT_URI dans .env pointe vers cette URL publique.
"""

import asyncio
import json
import math
import os
import re
import secrets
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from langdetect import LangDetectException, detect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)

from app.db import get_supabase
from app.style_guide import STYLE_GUIDE

# Charge les variables du fichier .env (clés TikTok, redirect URI, etc.)
load_dotenv()

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")

# Les "state" générés servent à vérifier que la réponse de TikTok
# correspond bien à une demande qu'on a nous-même initiée (protection
# anti-CSRF). Repli en mémoire tant que Supabase n'est pas configuré —
# voir _store_pending_state/_consume_pending_state. IMPORTANT : un state
# en mémoire seule ne survit pas à un redémarrage du serveur (redéploiement
# Render, veille du plan gratuit...), ce qui casse la connexion de tout
# utilisateur pile au milieu du flow OAuth à ce moment-là — d'où le passage
# par Supabase, comme pour _sessions.
_pending_states: set[str] = set()
PENDING_STATE_TTL_SECONDS = 10 * 60  # 10 minutes, largement suffisant pour un flow OAuth


def _store_pending_state(state: str) -> None:
    supabase = get_supabase()
    if supabase:
        supabase.table("pending_states").insert({"state": state}).execute()
    else:
        _pending_states.add(state)


def _consume_pending_state(state: str) -> bool:
    """Vérifie qu'un state est valide (existant et pas trop vieux) ET le retire, en un seul geste."""
    supabase = get_supabase()
    if supabase:
        res = supabase.table("pending_states").select("*").eq("state", state).limit(1).execute()
        if not res.data:
            return False
        supabase.table("pending_states").delete().eq("state", state).execute()
        created_at = datetime.fromisoformat(res.data[0]["created_at"]).timestamp()
        return (time.time() - created_at) < PENDING_STATE_TTL_SECONDS

    if state in _pending_states:
        _pending_states.discard(state)
        return True
    return False

# Stocke temporairement les access_token après connexion, associés à un
# identifiant de session aléatoire. On ne transmet jamais l'access_token
# brut à l'app/au navigateur : seulement cet identifiant, plus sûr.
# Repli en mémoire (perdu si le serveur redémarre) tant que Supabase n'est
# pas configuré (SUPABASE_URL/SUPABASE_KEY absents) — voir _store_session
# et _get_session, qui basculent automatiquement sur Supabase quand c'est
# disponible.
_sessions: dict[str, dict] = {}


def _store_session(session_id: str, access_token: str, open_id: str) -> None:
    supabase = get_supabase()
    if supabase:
        supabase.table("sessions").insert({
            "session_id": session_id,
            "access_token": access_token,
            "open_id": open_id,
        }).execute()
    else:
        _sessions[session_id] = {"access_token": access_token, "open_id": open_id}


def _get_session(session_id: str) -> dict | None:
    supabase = get_supabase()
    if supabase:
        res = supabase.table("sessions").select("*").eq("session_id", session_id).limit(1).execute()
        return res.data[0] if res.data else None
    return _sessions.get(session_id)


def _save_account_snapshot(
    open_id: str,
    username: str,
    niche_category: str | None,
    lang: str,
    stats: dict,
) -> None:
    """
    Enregistre un snapshot des stats du compte à l'instant de cette
    analyse (une ligne par analyse), pour construire un historique dans le
    temps — nécessaire pour le futur diagnostic de plateau et le rapport
    de progression mensuel. Sans effet si Supabase n'est pas configuré
    (pas de repli en mémoire : un historique volatile n'a aucune valeur).
    Échec silencieux : ne doit jamais faire échouer l'analyse elle-même.
    """
    supabase = get_supabase()
    if not supabase:
        return
    try:
        supabase.table("account_snapshots").insert({
            "open_id": open_id,
            "username": username,
            "niche_category": niche_category,
            "lang": lang,
            "total_videos_analyzed": stats.get("total_videos_analyzed"),
            "average_engagement_rate": stats.get("average_engagement_rate"),
            "viral_percentage": stats.get("viral_percentage"),
            "viral_count": stats.get("viral_count"),
            "non_viral_count": stats.get("non_viral_count"),
        }).execute()
    except Exception:
        pass

# Liste de scopes supplémentaires à demander, en plus des scopes de base
# déjà approuvés en Production. Configurable via variable d'environnement
# pour ne JAMAIS casser la Production tant que TikTok n'a pas approuvé ces
# scopes : on l'active uniquement temporairement en Sandbox pour tester.
# Exemple de valeur : "video.list,user.info.stats"
EXTRA_SCOPES = os.getenv("TIKTOK_EXTRA_SCOPES", "").strip()

# Cache des hashtags/idées tendance par catégorie de niche + langue
# (recherche web coûteuse, donc on ne la relance qu'une fois par
# catégorie+langue par jour, pas à chaque analyse de compte).
# Clé = "{niche_category}:{lang}", valeur = {"hashtags": [...], "cached_at": timestamp}.
# On catégorise sur NICHE_CATEGORIES (liste fermée) plutôt que sur le texte
# libre "niche" généré par Claude, qui varie légèrement à chaque appel et
# cassait le cache (deux analyses du même compte donnaient rarement
# exactement la même phrase, donc quasiment jamais de cache hit).
_trending_hashtags_cache: dict[str, dict] = {}
TRENDING_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h

# Liste fermée de catégories de niche. Claude doit choisir EXACTEMENT une
# valeur de cette liste (en plus du champ "niche" en texte libre, gardé
# pour l'affichage), pour que la clé de cache des tendances soit stable
# d'une analyse à l'autre.
NICHE_CATEGORIES = [
    "Beauté & Skincare",
    "Mode & Style",
    "Fitness & Sport",
    "Cuisine & Nutrition",
    "Voyage",
    "Humour & Divertissement",
    "Musique & Danse",
    "Gaming & Tech",
    "Business & Finance",
    "Développement personnel",
    "Éducation & Culture générale",
    "Lifestyle & Vlog quotidien",
    "Parentalité & Famille",
    "Art & Créativité",
    "Animaux",
    "Santé & Bien-être",
    "Autre",
]


def _detect_language(bio: str, titles: list[str]) -> str:
    """
    Détecte la langue probable du compte à partir de la bio et des titres
    de vidéos récentes, pour adapter la langue des hashtags/idées tendance
    ET pour affiner la clé de cache (une même catégorie de niche a des
    tendances différentes en français et en anglais, par exemple).
    Retombe sur "fr" (langue par défaut de l'app) si le texte est trop
    court pour une détection fiable, ou si langdetect échoue.
    """
    text = " ".join([bio] + list(titles)).strip()
    if len(text) < 10:
        return "fr"
    try:
        return detect(text)
    except LangDetectException:
        return "fr"


app = FastAPI(title="Wil App Backend", version="0.1.0")

# CORS = permet à l'app Flutter (qui tournera sur une autre adresse)
# de communiquer avec ce backend sans être bloquée par le navigateur/OS.
# En développement on autorise tout ("*"), on restreindra plus tard.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/favicon.ico")
def favicon():
    """
    Sert le favicon (icône affichée dans l'onglet du navigateur).
    Le fichier favicon.ico doit se trouver dans le dossier app/,
    au même niveau que ce fichier main.py.
    """
    favicon_path = Path(__file__).parent / "favicon.ico"
    return FileResponse(favicon_path)


@app.head("/")
def home_head():
    """
    Réponse explicite aux requêtes HEAD sur la page d'accueil (utilisées
    par les outils de monitoring comme UptimeRobot pour vérifier que le
    site répond, sans télécharger tout le contenu). FastAPI gère déjà ça
    automatiquement pour les routes GET en théorie — cette route explicite
    est une sécurité supplémentaire au cas où un problème surviendrait
    entre notre code et l'infrastructure d'hébergement.
    """
    return


@app.get("/", response_class=HTMLResponse)
def home():
    """
    Page d'accueil présentant le service en détail : fonctionnalités,
    tarifs, fonctionnement, et liens légaux visibles directement, sans
    menu ni connexion requise (exigence explicite de TikTok).
    """
    return """
    <html>
      <head>
        <title>Wil App</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          * { box-sizing: border-box; }
          body { font-family: -apple-system, Segoe UI, Arial, sans-serif;
                 margin: 0; color: #1a1a1a; }
          .wrap { max-width: 880px; margin: 0 auto; padding: 0 24px; }
          header { text-align: center; padding: 70px 24px 50px; }
          header h1 { font-size: 36px; margin-bottom: 8px; }
          header p { color: #666; font-size: 19px; margin: 0 0 32px; }
          .cta { display: inline-block; padding: 15px 32px; background: #000;
                 color: #fff; border-radius: 8px; text-decoration: none;
                 font-weight: bold; font-size: 16px; }
          section { padding: 50px 0; border-top: 1px solid #eee; }
          section h2 { font-size: 26px; text-align: center; margin-bottom: 36px; }
          .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                  gap: 28px; }
          .card { background: #fafafa; border: 1px solid #eee; border-radius: 10px;
                  padding: 22px; }
          .card h3 { margin: 0 0 8px; font-size: 17px; }
          .card p { margin: 0; color: #555; font-size: 14px; }
          .steps { display: flex; flex-direction: column; gap: 18px; max-width: 560px; margin: 0 auto; }
          .step { display: flex; gap: 16px; align-items: flex-start; }
          .step .num { flex-shrink: 0; width: 32px; height: 32px; border-radius: 50%;
                       background: #000; color: #fff; display: flex; align-items: center;
                       justify-content: center; font-weight: bold; }
          .pricing { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
                     gap: 24px; max-width: 640px; margin: 0 auto; }
          .plan { border: 1px solid #ddd; border-radius: 12px; padding: 28px; text-align: center; }
          .plan.highlight { border: 2px solid #000; }
          .plan .price { font-size: 32px; font-weight: bold; margin: 12px 0; }
          .plan .price span { font-size: 15px; font-weight: normal; color: #777; }
          .plan ul { list-style: none; padding: 0; margin: 20px 0; text-align: left; font-size: 14px; color: #444; }
          .plan ul li { padding: 6px 0; }
          footer { text-align: center; padding: 40px 24px; color: #777; font-size: 14px; }
          footer a { color: #444; }
          .contact { text-align: center; padding: 40px 0; }
          .contact a { color: #000; }
          nav { display: flex; justify-content: center; gap: 28px; padding: 18px 0;
                border-bottom: 1px solid #eee; font-size: 14px; }
          nav a { color: #444; text-decoration: none; font-weight: 500; }
          nav a:hover { color: #000; }
          .about p { max-width: 600px; margin: 0 auto; color: #444; text-align: center; }
        </style>
      </head>
      <body>
        <nav>
          <a href="#services">Services</a>
          <a href="#how-it-works">How It Works</a>
          <a href="#pricing">Pricing</a>
          <a href="#about">About</a>
          <a href="#contact">Contact</a>
        </nav>
        <header>
          <h1>Wil App</h1>
          <p>Analytics and insights for TikTok creators</p>
          <a href="/auth/tiktok/login" class="cta">Se connecter avec TikTok</a>
        </header>

        <div class="wrap">
          <section id="services">
            <h2>Our Services</h2>
            <div class="grid">
              <div class="card">
                <h3>📊 Account Overview</h3>
                <p>Connect your TikTok account to see your profile information
                   and account activity gathered in one simple dashboard.</p>
              </div>
              <div class="card">
                <h3>🔒 Secure Authentication</h3>
                <p>Wil App uses TikTok's official Login Kit. We never see or
                   store your TikTok password, and access can be revoked at
                   any time from your TikTok settings.</p>
              </div>
              <div class="card">
                <h3>🎯 Built for Creators</h3>
                <p>Designed specifically to help TikTok creators better
                   understand their own account and presence on the platform.</p>
              </div>
            </div>
          </section>

          <section id="how-it-works">
            <h2>How It Works</h2>
            <div class="steps">
              <div class="step">
                <div class="num">1</div>
                <div><strong>Connect your account</strong><br>Log in securely with your TikTok account using the button above.</div>
              </div>
              <div class="step">
                <div class="num">2</div>
                <div><strong>Authorize access</strong><br>Review and approve the permissions Wil App requests, directly on TikTok.</div>
              </div>
              <div class="step">
                <div class="num">3</div>
                <div><strong>View your overview</strong><br>See your connected profile information right away in your Wil App dashboard.</div>
              </div>
            </div>
          </section>

          <section id="pricing">
            <h2>Pricing</h2>
            <div class="pricing">
              <div class="plan">
                <h3>Free</h3>
                <div class="price">$0<span>/month</span></div>
                <ul>
                  <li>✔ Connect your TikTok account</li>
                  <li>✔ Basic profile overview</li>
                </ul>
              </div>
              <div class="plan highlight">
                <h3>Pro</h3>
                <div class="price">Coming soon</div>
                <ul>
                  <li>✔ Everything in Free</li>
                  <li>✔ Advanced account insights</li>
                  <li>✔ Priority support</li>
                </ul>
              </div>
            </div>
          </section>

          <section id="about" class="about">
            <h2>About Wil App</h2>
            <p>Wil App is an independent project built to give TikTok creators
               a simple, secure way to connect their account and view their
               profile information in one place. The project is under active
               development, with more account insight features on the way.</p>
          </section>

          <section id="contact" class="contact">
            <h2>Contact</h2>
            <p>Questions about Wil App? Reach us at
               <a href="mailto:contact.wilapp@proton.me">contact.wilapp@proton.me</a></p>
          </section>
        </div>

        <footer>
          <a href="/terms">Terms of Service</a>
          &nbsp;|&nbsp;
          <a href="/privacy">Privacy Policy</a>
          <br><br>
          © 2026 Wil App. All rights reserved.
        </footer>
      </body>
    </html>
    """


@app.get("/tiktokduU5VyZDYUA3xEXGVEkwALeLjZu2rBIn.txt", response_class=PlainTextResponse)
def tiktok_site_verification():
    """
    Route qui sert le fichier de vérification de propriété demandé par
    TikTok pour l'ancien domaine Render. Conservée pour compatibilité.
    """
    return "tiktok-developers-site-verification=duU5VyZDYUA3xEXGVEkwALeLjZu2rBIn"


@app.get("/tiktokyTrx2kzthutNNU4nYzj6QLfKq33zYvJe.txt", response_class=PlainTextResponse)
def tiktok_site_verification_wilapp_tech():
    """
    Route qui sert le fichier de vérification de propriété demandé par
    TikTok pour le nouveau domaine wilapp.tech.
    """
    return "tiktok-developers-site-verification=yTrx2kzthutNNU4nYzj6QLfKq33zYvJe"


@app.get("/auth/tiktok/login")
def tiktok_login(source: str = "web"):
    """
    Étape 1 du flow OAuth : on redirige l'utilisateur vers la page
    d'autorisation de TikTok.

    Le paramètre "source" indique d'où vient la demande :
    - "web"  (par défaut) : affichera la page HTML classique à la fin
    - "app"  : redirigera vers l'app mobile (wilapp://callback) à la fin
    L'app Flutter appelle cette route avec ?source=app.
    """
    if not TIKTOK_CLIENT_KEY or not TIKTOK_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="TIKTOK_CLIENT_KEY ou TIKTOK_REDIRECT_URI manquant dans .env",
        )

    # Le "state" sert à la fois de protection anti-CSRF ET à retenir la
    # source de la demande (web ou app), en préfixant la valeur aléatoire.
    prefix = "app_" if source == "app" else "web_"
    state = prefix + secrets.token_urlsafe(24)
    _store_pending_state(state)

    base_scope = "user.info.basic,user.info.profile"
    scope = f"{base_scope},{EXTRA_SCOPES}" if EXTRA_SCOPES else base_scope

    params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "scope": scope,
        "response_type": "code",
        "redirect_uri": TIKTOK_REDIRECT_URI,
        "state": state,
    }
    query_string = "&".join(f"{key}={value}" for key, value in params.items())
    authorize_url = f"https://www.tiktok.com/v2/auth/authorize/?{query_string}"

    # En-têtes anti-cache explicites : chaque appel génère un state unique
    # à usage unique. Sans ça, Cloudflare (le site passe par leur CDN, cf.
    # les en-têtes Cf-Ray observés en prod) ou le navigateur pourrait
    # mettre cette redirection en cache et resservir un ancien state déjà
    # consommé/expiré lors d'une connexion ultérieure, provoquant le "State
    # introuvable" alors même que le mécanisme Supabase fonctionne
    # correctement (vérifié séparément).
    return RedirectResponse(authorize_url, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
    })


@app.get("/auth/tiktok/callback", response_class=HTMLResponse)
async def tiktok_callback(request: Request):
    """
    Étape 2 du flow OAuth : TikTok redirige l'utilisateur ici après
    qu'il a autorisé (ou refusé) la connexion. On récupère le "code"
    fourni par TikTok, puis on l'échange contre un vrai access_token,
    et enfin on récupère les infos de profil de l'utilisateur.
    """
    error = request.query_params.get("error")
    if error:
        return f"<h1>Connexion refusée ou erreur</h1><p>{error}</p>"

    code = request.query_params.get("code")
    state = request.query_params.get("state")

    # Détail explicite du cas d'échec (plutôt qu'un message générique) pour
    # pouvoir diagnostiquer depuis la réponse HTTP sans avoir besoin des
    # logs serveur — cf. le bug du 23/09/2026 où le message générique ne
    # permettait pas de savoir si le vrai problème avait changé ou non.
    if not code:
        raise HTTPException(status_code=400, detail="Paramètre 'code' manquant dans le retour TikTok.")
    if not state:
        raise HTTPException(status_code=400, detail="Paramètre 'state' manquant dans le retour TikTok.")
    if not _consume_pending_state(state):
        raise HTTPException(
            status_code=400,
            detail=f"State '{state[:12]}...' introuvable, déjà utilisé, ou expiré (>10 min) — reconnecte-toi depuis le début.",
        )

    # Échange du code contre un access_token (appel serveur-à-serveur,
    # jamais fait depuis le navigateur pour ne pas exposer le client_secret).
    # Timeout explicite + try/except : un timeout réseau (httpx.HTTPError,
    # pas une HTTPException) vers TikTok plantait sinon toute la route en
    # 500 au lieu d'un message d'erreur lisible — même bug déjà corrigé
    # pour les appels TikTok/Anthropic dans analyze_account.
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            token_response = await client.post(
                "https://open.tiktokapis.com/v2/oauth/token/",
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_key": TIKTOK_CLIENT_KEY,
                    "client_secret": TIKTOK_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": TIKTOK_REDIRECT_URI,
                },
            )
    except httpx.HTTPError:
        return "<h1>Erreur réseau vers TikTok</h1><p>Réessaie dans un instant.</p>"
    token_data = token_response.json()

    if "access_token" not in token_data:
        return f"<h1>Erreur lors de l'échange du token</h1><pre>{token_data}</pre>"

    access_token = token_data["access_token"]

    # Avec l'access_token en main, on peut maintenant appeler l'API
    # TikTok pour récupérer les infos de profil de l'utilisateur (dont
    # open_id, nécessaire pour identifier ce compte de façon stable dans
    # le temps — utilisé notamment par account_snapshots).
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            user_response = await client.get(
                "https://open.tiktokapis.com/v2/user/info/",
                params={
                    "fields": "open_id,display_name,avatar_url,username,"
                              "bio_description,profile_web_link,is_verified"
                },
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.HTTPError:
        return "<h1>Erreur réseau vers TikTok</h1><p>Réessaie dans un instant.</p>"
    user_data = user_response.json()

    user_info = user_data.get("data", {}).get("user", {})
    open_id = user_info.get("open_id", "")
    display_name = user_info.get("display_name", "TikTok User")
    avatar_url = user_info.get("avatar_url", "")
    username = user_info.get("username", "")
    bio = user_info.get("bio_description", "")
    profile_link = user_info.get("profile_web_link", "")
    is_verified = user_info.get("is_verified", False)

    # On génère un identifiant de session aléatoire, associé à
    # l'access_token côté serveur. On ne transmettra JAMAIS l'access_token
    # brut à l'app ou au navigateur : seulement cet identifiant, qui sert
    # ensuite de "clé" pour les appels comme /api/analyze-account.
    session_id = secrets.token_urlsafe(24)
    _store_session(session_id, access_token, open_id)

    # Si la connexion a été initiée depuis l'app mobile (state préfixé par
    # "app_"), on redirige vers le deep link "wilapp://callback" avec les
    # infos du profil en paramètres, pour que Flutter reprenne la main.
    # Android/iOS interceptent cette adresse et rouvrent Wil App directement.
    if state.startswith("app_"):
        from urllib.parse import urlencode

        app_params = urlencode({
            "display_name": display_name,
            "avatar_url": avatar_url,
            "username": username,
            "bio": bio,
            "profile_link": profile_link,
            "is_verified": "true" if is_verified else "false",
            "session": session_id,
        })
        return RedirectResponse(f"wilapp://callback?{app_params}")

    verified_badge = (
        '<span style="color:#20d5ec; font-weight:bold;">✔ Verified</span>'
        if is_verified else ""
    )
    bio_html = f'<p style="color:#555; max-width:400px; margin:12px auto;">{bio}</p>' if bio else ""
    link_html = (
        f'<p><a href="{profile_link}" target="_blank">View TikTok profile ↗</a></p>'
        if profile_link else ""
    )

    # Tableau de bord affiché après connexion : montre les vraies données
    # récupérées via l'API, ET lance automatiquement l'analyse complète du
    # compte (engagement, viralité, rapport IA) via JavaScript, pour que
    # la version web offre la même expérience que l'app mobile.
    from urllib.parse import quote

    display_name_enc = quote(display_name)
    username_enc = quote(username)
    bio_enc = quote(bio)

    return f"""
    <html>
      <head>
        <title>Wil App — Dashboard</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          body {{ font-family: -apple-system, Arial, sans-serif; text-align: center;
                  margin: 0; padding: 60px 20px; color: #1a1a1a; }}
          .card {{ max-width: 460px; margin: 0 auto 20px; border: 1px solid #eee;
                   border-radius: 14px; padding: 32px; box-shadow: 0 4px 16px rgba(0,0,0,0.06);
                   text-align: left; }}
          .card.profile {{ text-align: center; }}
          img {{ width: 110px; height: 110px; border-radius: 50%; object-fit: cover; }}
          h2 {{ margin: 16px 0 4px; }}
          .username {{ color: #777; margin: 0 0 8px; }}
          .stats {{ display: flex; justify-content: center; gap: 24px; margin-top: 24px;
                    padding-top: 20px; border-top: 1px solid #eee; font-size: 14px; color: #555; }}
          a.home {{ display:inline-block; margin-top: 30px; color:#555; }}
          .loading {{ color: #777; font-size: 14px; }}
          .bar-bg {{ background: #e5e7eb; border-radius: 8px; height: 16px; overflow: hidden; }}
          .bar-fill {{ background: #5B21B6; height: 100%; }}
          .chip {{ display: inline-block; background: #EC4899; color: white; padding: 4px 12px;
                   border-radius: 999px; font-size: 13px; font-weight: bold; }}
          .tag {{ display: inline-block; background: #f3f4f6; padding: 3px 10px; border-radius: 999px;
                  font-size: 12px; margin: 3px; }}
          ul.bullets {{ padding-left: 18px; }}
        </style>
      </head>
      <body>
        <p style="color:#22c55e; font-weight:bold;">✅ Connected successfully</p>
        <div class="card profile">
          <img src="{avatar_url}" alt="Profile picture" />
          <h2>{display_name} {verified_badge}</h2>
          <p class="username">@{username}</p>
          {bio_html}
          {link_html}
          <div class="stats">
            <div>🔗 Account linked</div>
            <div>🔒 Data secured</div>
          </div>
        </div>

        <div id="analysis-loading" class="card">
          <p class="loading">⏳ Analyse du compte en cours (récupération des vidéos et calcul des statistiques)...</p>
        </div>
        <div id="analysis-result"></div>

        <a href="/" class="home">← Back to Wil App</a>

        <script>
          const sessionId = "{session_id}";
          fetch(`/api/analyze-account?session=${{sessionId}}&display_name={display_name_enc}&username={username_enc}&bio={bio_enc}`)
            .then(r => r.json())
            .then(data => {{
              document.getElementById('analysis-loading').style.display = 'none';
              const stats = data.stats;
              const report = data.ai_report;
              let html = '';
              // Section "Détail par vidéo" construite séparément et ajoutée
              // TOUT EN BAS (après l'analyse globale) : c'est la partie qui
              // deviendra la fonctionnalité payante, donc visuellement
              // secondaire par rapport à l'analyse de compte gratuite.
              let videoListHtml = '';

              if (stats && stats.total_videos_analyzed > 0) {{
                const scoreIcon = s => s <= 40 ? '🔴' : s <= 60 ? '🟡' : s <= 80 ? '🟠' : '🔵';
                const ratioLine = (stats.likes_followers_ratio !== null && stats.likes_followers_ratio !== undefined)
                  ? `<p style="font-size:12px;color:#999;margin:2px 0 0;">Ratio likes/abonnés : ${{stats.likes_followers_ratio}}</p>`
                  : '';
                html += `
                  <div class="card">
                    <p style="font-size:28px;font-weight:800;margin:0;">${{scoreIcon(stats.account_virality_score)}} ${{stats.account_virality_score}}/100</p>
                    <p style="font-size:12px;color:#888;margin:2px 0 12px;">Score de viralité du compte</p>
                    <p style="font-size:13px;color:#666;">${{stats.total_videos_analyzed}} vidéos analysées (seuil : ${{stats.viral_threshold_views/1000}}k vues)</p>
                    <div class="bar-bg"><div class="bar-fill" style="width:${{stats.viral_percentage}}%"></div></div>
                    <p style="margin-top:12px;"><strong>🚀 ${{stats.viral_percentage}}%</strong> vidéos virales &nbsp;|&nbsp; <strong>${{stats.non_viral_percentage}}%</strong> non virales</p>
                    <p>Taux d'engagement moyen : <strong>${{stats.average_engagement_rate}}%</strong></p>
                    ${{ratioLine}}
                  </div>`;

                if (stats.videos && stats.videos.length > 0) {{
                  window.__wilVideos = stats.videos;
                  window.__wilAvgViews = stats.average_view_count || '';
                  const videoRows = stats.videos.map((v, idx) => `
                    <div style="display:flex; gap:12px; align-items:flex-start; padding:12px 0; border-bottom:1px solid #f0f0f0;">
                      <div style="width:60px;height:84px;flex-shrink:0;border-radius:8px;overflow:hidden;background:#f3f4f6;">
                        ${{v.cover_image_url ? `<img src="${{v.cover_image_url}}" style="width:100%;height:100%;object-fit:cover;" />` : ''}}
                      </div>
                      <div style="flex:1;min-width:0;">
                        <p style="font-size:13px;font-weight:700;margin:0;">${{scoreIcon(v.virality_score)}} ${{v.virality_score}}/100</p>
                        <p style="font-size:12px;color:#666;margin:2px 0 8px;">${{v.view_count}} vues</p>
                        <button onclick="analyzeVideo(${{idx}})" id="analyze-btn-${{idx}}"
                                style="font-size:12px;padding:6px 12px;border-radius:8px;border:1px solid #ddd;
                                       background:#fff;cursor:pointer;">
                          Analyser la vidéo
                        </button>
                        <div id="video-analysis-${{idx}}" style="margin-top:8px;font-size:13px;"></div>
                      </div>
                    </div>`).join('');
                  videoListHtml = `
                    <div class="card">
                      <p style="font-weight:bold;margin-bottom:4px;">Détail par vidéo</p>
                      <p style="font-size:12px;color:#888;margin:0 0 8px;">Vidéos triées par date de publication, comme sur ton profil TikTok. Score de viralité basé sur les vues (0-100), pas sur le taux d'engagement.</p>
                      <div>${{videoRows}}</div>
                    </div>`;
                }}
              }}

              if (report) {{
                const strengths = (report.strengths || []).map(s => `<li>${{s}}</li>`).join('');
                const improvements = (report.improvements || []).map(s => `<li>${{s}}</li>`).join('');
                const hashtags = (report.suggested_hashtags || []).map(h => `<span class="tag">#${{h}}</span>`).join('');
                const hashtagDiag = report.hashtag_diagnosis
                  ? `<p><strong>🏷 Diagnostic hashtags</strong></p><p style="font-size:14px;">${{report.hashtag_diagnosis}}</p>`
                  : '';
                html += `
                  <div class="card">
                    <span class="chip">${{report.niche || ''}}</span>
                    <p style="margin-top:12px;">${{report.summary || ''}}</p>
                    <p><strong>✅ Points forts</strong></p>
                    <ul class="bullets">${{strengths}}</ul>
                    <p><strong>📈 À améliorer</strong></p>
                    <ul class="bullets">${{improvements}}</ul>
                    ${{hashtagDiag}}
                    <p><strong>Hashtags suggérés</strong></p>
                    <div>${{hashtags}}</div>
                  </div>`;

                window.__wilNiche = report.niche || '';
                window.__wilNicheCategory = report.niche_category || '';
                window.__wilBio = "{bio_enc}";
              }}
              window.__wilLang = data.lang || 'fr';

              if (!html) {{
                html = '<div class="card"><p class="loading">Analyse indisponible pour le moment.</p></div>';
              }}
              // Détail par vidéo tout en bas, après l'analyse globale du compte.
              html += videoListHtml;

              document.getElementById('analysis-result').innerHTML = html;

              // Affiche les sections "Idées tendance" et "Générer un script"
              // une fois l'analyse principale terminée (on a besoin de la
              // catégorie de niche pour le bouton "Idées tendance").
              if (report && report.niche_category) {{
                document.getElementById('extra-tools').style.display = 'block';
              }}
            }})
            .catch(() => {{
              document.getElementById('analysis-loading').innerHTML =
                '<p class="loading">Analyse indisponible pour le moment.</p>';
            }});

          // --- Analyse IA d'une vidéo précise (bouton sous chaque vignette) ---
          function analyzeVideo(idx) {{
            const v = (window.__wilVideos || [])[idx];
            if (!v) return;
            const btn = document.getElementById(`analyze-btn-${{idx}}`);
            const result = document.getElementById(`video-analysis-${{idx}}`);
            btn.disabled = true;
            btn.textContent = 'Analyse en cours...';
            result.innerHTML = '';

            const params = new URLSearchParams({{
              title: v.title || '',
              view_count: v.view_count || 0,
              like_count: v.like_count || 0,
              comment_count: v.comment_count || 0,
              share_count: v.share_count || 0,
              duration: v.duration || '',
              virality_score: v.virality_score || 0,
              account_avg_views: window.__wilAvgViews || '',
              niche_category: window.__wilNicheCategory || '',
            }});

            fetch(`/api/analyze-video?${{params.toString()}}`)
              .then(r => r.json())
              .then(data => {{
                const strengths = (data.strengths || []).map(s => `<li>${{s}}</li>`).join('');
                const weaknesses = (data.weaknesses || []).map(s => `<li>${{s}}</li>`).join('');
                const actions = (data.action_plan || []).map(s => `<li>${{s}}</li>`).join('');
                result.innerHTML = `
                  <p style="margin:6px 0 2px;"><strong>✅ Points forts</strong></p>
                  <ul class="bullets" style="margin:0;">${{strengths}}</ul>
                  <p style="margin:6px 0 2px;"><strong>⚠️ Points faibles</strong></p>
                  <ul class="bullets" style="margin:0;">${{weaknesses}}</ul>
                  <p style="margin:6px 0 2px;"><strong>🎯 Pour percer</strong></p>
                  <ul class="bullets" style="margin:0;">${{actions}}</ul>`;
              }})
              .catch(() => {{
                result.innerHTML = '<p style="color:#c0392b;font-size:12px;">Analyse indisponible pour le moment.</p>';
              }})
              .finally(() => {{
                btn.disabled = false;
                btn.textContent = 'Analyser la vidéo';
              }});
          }}

          // --- Idées de vidéos et hooks tendance ---
          function loadTrendingIdeas() {{
            const btn = document.getElementById('trending-btn');
            const result = document.getElementById('trending-result');
            btn.disabled = true;
            btn.textContent = 'Recherche en cours...';
            result.innerHTML = '';

            fetch(`/api/trending-ideas?niche_category=${{encodeURIComponent(window.__wilNicheCategory || '')}}&lang=${{encodeURIComponent(window.__wilLang || 'fr')}}`)
              .then(r => r.json())
              .then(data => {{
                const ideas = (data.video_ideas || []).map(i => `<li>${{i}}</li>`).join('');
                const hooks = (data.trending_hooks || []).map(h => `<li>${{h}}</li>`).join('');
                result.innerHTML = `
                  <p><strong>💡 Idées de vidéos tendance</strong></p>
                  <ul class="bullets">${{ideas}}</ul>
                  <p><strong>🎬 Hooks tendance</strong></p>
                  <ul class="bullets">${{hooks}}</ul>`;
              }})
              .catch(() => {{
                result.innerHTML = '<p class="loading">Indisponible pour le moment, réessaie plus tard.</p>';
              }})
              .finally(() => {{
                btn.disabled = false;
                btn.textContent = 'Idées tendance de ma niche';
              }});
          }}

          // --- Générateur de script personnalisé ---
          // --- Analyse approfondie d'une vidéo importée (transcription réelle) ---
          function analyzeUploadedVideo() {{
            const fileInput = document.getElementById('upload-video-input');
            const btn = document.getElementById('upload-analyze-btn');
            const result = document.getElementById('upload-analyze-result');

            if (!fileInput.files || fileInput.files.length === 0) {{
              result.innerHTML = '<p style="color:#c0392b;">Choisis d\\'abord un fichier vidéo.</p>';
              return;
            }}

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('account_avg_views', window.__wilAvgViews || '');
            formData.append('niche_category', window.__wilNicheCategory || '');

            btn.disabled = true;
            btn.textContent = 'Transcription et analyse en cours (peut prendre 1-2 min)...';
            result.innerHTML = '';

            fetch('/api/analyze-video-upload', {{ method: 'POST', body: formData }})
              .then(r => {{
                if (!r.ok) throw new Error('failed');
                return r.json();
              }})
              .then(data => {{
                const strengths = (data.strengths || []).map(s => `<li>${{s}}</li>`).join('');
                const weaknesses = (data.weaknesses || []).map(s => `<li>${{s}}</li>`).join('');
                const actions = (data.action_plan || []).map(s => `<li>${{s}}</li>`).join('');
                result.innerHTML = `
                  <p><strong>🎬 Hook réel</strong></p>
                  <p style="font-style:italic;">"${{data.hook_excerpt || ''}}"</p>
                  <p style="font-size:13px;color:#666;">${{data.hook_type || ''}}</p>
                  <p style="margin-top:10px;"><strong>✅ Points forts</strong></p>
                  <ul class="bullets">${{strengths}}</ul>
                  <p><strong>⚠️ Points faibles</strong></p>
                  <ul class="bullets">${{weaknesses}}</ul>
                  <p><strong>🎯 Pour percer</strong></p>
                  <ul class="bullets">${{actions}}</ul>`;
              }})
              .catch(() => {{
                result.innerHTML = '<p style="color:#c0392b;">Analyse indisponible pour le moment. Réessaie.</p>';
              }})
              .finally(() => {{
                btn.disabled = false;
                btn.textContent = 'Analyser cette vidéo';
              }});
          }}

          function generateScript() {{
            const topic = document.getElementById('script-topic').value.trim();
            const tone = document.getElementById('script-tone').value.trim();
            const limits = document.getElementById('script-limits').value.trim();
            const result = document.getElementById('script-result');
            const btn = document.getElementById('script-btn');

            if (!topic) {{
              result.innerHTML = '<p style="color:#c0392b;">Décris le sujet de ta vidéo pour continuer.</p>';
              return;
            }}

            btn.disabled = true;
            btn.textContent = 'Génération...';
            result.innerHTML = '';

            const params = new URLSearchParams({{
              topic, tone, limits,
              niche: window.__wilNiche || '',
              bio: window.__wilBio || '',
            }});

            fetch(`/api/generate-script?${{params.toString()}}`)
              .then(r => r.json())
              .then(data => {{
                result.innerHTML = `
                  <p><strong>🎬 Accroche (0-3s)</strong></p><p>${{data.hook || ''}}</p>
                  <p><strong>📝 Corps du script</strong></p><p>${{data.body || ''}}</p>
                  <p><strong>👉 Appel à l'action</strong></p><p>${{data.call_to_action || ''}}</p>
                  <p><strong>💡 Conseils de tournage</strong></p><p>${{data.notes || ''}}</p>`;
              }})
              .catch(() => {{
                result.innerHTML = '<p style="color:#c0392b;">Erreur lors de la génération. Réessaie.</p>';
              }})
              .finally(() => {{
                btn.disabled = false;
                btn.textContent = 'Générer le script';
              }});
          }}
        </script>

        <div id="extra-tools" style="display:none; max-width:460px; margin:0 auto;">
          <div class="card">
            <button id="trending-btn" onclick="loadTrendingIdeas()"
                    style="width:100%; padding:12px; border-radius:10px; border:1px solid #ddd;
                           background:#fff; cursor:pointer; font-weight:600;">
              Idées tendance de ma niche
            </button>
            <div id="trending-result" style="margin-top:14px;"></div>
          </div>

          <div class="card">
            <p style="font-weight:bold; margin-bottom:4px;">Analyse approfondie d'une vidéo</p>
            <p style="font-size:12px;color:#888;margin:0 0 10px;">Importe le fichier vidéo (déjà postée ou pas encore) depuis ton téléphone ou ta machine — on transcrit le vrai contenu parlé pour analyser ton hook précisément.</p>
            <input id="upload-video-input" type="file" accept="video/*"
                   style="width:100%; margin-bottom:10px;" />
            <button id="upload-analyze-btn" onclick="analyzeUploadedVideo()"
                    style="width:100%; padding:12px; border-radius:10px; border:none;
                           background:#5B21B6; color:white; cursor:pointer; font-weight:600;">
              Analyser cette vidéo
            </button>
            <div id="upload-analyze-result" style="margin-top:14px; text-align:left;"></div>
          </div>

          <div class="card">
            <p style="font-weight:bold; margin-bottom:10px;">Générer un script personnalisé</p>
            <textarea id="script-topic" placeholder="Sujet de la vidéo *" rows="2"
                      style="width:100%; padding:10px; border-radius:8px; border:1px solid #ddd; margin-bottom:10px; font-family:inherit;"></textarea>
            <input id="script-tone" placeholder="Ton habituel (optionnel)"
                   style="width:100%; padding:10px; border-radius:8px; border:1px solid #ddd; margin-bottom:10px; font-family:inherit;" />
            <textarea id="script-limits" placeholder="Limites à respecter (optionnel)" rows="2"
                      style="width:100%; padding:10px; border-radius:8px; border:1px solid #ddd; margin-bottom:10px; font-family:inherit;"></textarea>
            <button id="script-btn" onclick="generateScript()"
                    style="width:100%; padding:12px; border-radius:10px; border:none;
                           background:#EC4899; color:white; cursor:pointer; font-weight:600;">
              Générer le script
            </button>
            <div id="script-result" style="margin-top:14px; text-align:left;"></div>
          </div>
        </div>
      </body>
    </html>
    """


_LEGAL_STYLE = """
  body { font-family: -apple-system, Arial, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #222; }
  h1 { font-size: 28px; }
  h2 { font-size: 20px; margin-top: 32px; }
  footer { margin-top: 60px; color: #777; font-size: 14px; }
  a { color: #0645AD; }
"""


@app.get("/terms", response_class=HTMLResponse)
def terms_of_service():
    """Page des Conditions d'utilisation, hébergée directement sur ce domaine."""
    return f"""
    <html>
    <head>
      <title>Wil App Terms of Service</title>
      <link rel="icon" type="image/x-icon" href="/favicon.ico">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>{_LEGAL_STYLE}</style>
    </head>
    <body>
    <h1>Wil App Terms of Service</h1>
    <p><em>Last updated: July 2026</em></p>

    <p>Welcome to Wil App. These Terms of Service ("Terms") govern your use of the Wil App application and website (the "Service"). By using the Service, you agree to these Terms.</p>

    <h2>1. Description of the Service</h2>
    <p>Wil App allows users to connect their TikTok account in order to receive analytics and insights about their own content and account performance. The Service uses TikTok's official APIs to retrieve information that the user has explicitly authorized.</p>

    <h2>2. Account Connection</h2>
    <p>To use core features of the Service, you must authorize Wil App to access your TikTok account through TikTok's official Login Kit. You may revoke this authorization at any time from your TikTok account settings.</p>

    <h2>3. User Responsibilities</h2>
    <p>You agree to use the Service only for lawful purposes and in accordance with TikTok's own Terms of Service and Developer Policies.</p>

    <h2>4. Data Usage</h2>
    <p>Data retrieved from your TikTok account is used solely to provide you with analytics and insights within the Service. See our <a href="/privacy">Privacy Policy</a> for full details.</p>

    <h2>5. Disclaimer</h2>
    <p>The Service is provided "as is" without warranties of any kind. Wil App is not affiliated with, endorsed by, or sponsored by TikTok or ByteDance Ltd.</p>

    <h2>6. Changes to These Terms</h2>
    <p>We may update these Terms from time to time. Continued use of the Service after changes constitutes acceptance of the new Terms.</p>

    <h2>7. Contact</h2>
    <p>Questions? Contact us at <a href="mailto:contact.wilapp@proton.me">contact.wilapp@proton.me</a>.</p>

    <footer>Wil App — Terms of Service</footer>
    </body>
    </html>
    """


@app.get("/privacy", response_class=HTMLResponse)
def privacy_policy():
    """Page de Politique de confidentialité, hébergée directement sur ce domaine."""
    return f"""
    <html>
    <head>
      <title>Wil App Privacy Policy</title>
      <link rel="icon" type="image/x-icon" href="/favicon.ico">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>{_LEGAL_STYLE}</style>
    </head>
    <body>
    <h1>Wil App Privacy Policy</h1>
    <p><em>Last updated: July 2026</em></p>

    <p>This Privacy Policy explains how Wil App ("we", "us") collects, uses, and protects information when you use our Service.</p>

    <h2>1. Information We Collect</h2>
    <p>When you connect your TikTok account through TikTok's official Login Kit, we may receive, only with your explicit authorization:</p>
    <ul>
      <li>Basic profile information (username, display name, profile picture)</li>
      <li>Public content and video metadata associated with your account</li>
    </ul>
    <p>We do not access private messages, payment information, or any data beyond what is explicitly permitted by the scopes you authorize.</p>

    <h2>2. How We Use Your Information</h2>
    <p>We use the information solely to provide account insights within the Service and improve its reliability. We do not sell your personal data to third parties.</p>

    <h2>3. Data Storage and Security</h2>
    <p>We take reasonable technical measures to protect the information we store. Access tokens are stored securely and are never shared publicly.</p>

    <h2>4. Third-Party Services</h2>
    <p>Our Service integrates with TikTok's official APIs. Your use of TikTok remains subject to TikTok's own Privacy Policy and Terms of Service.</p>

    <h2>5. Your Rights</h2>
    <p>You may revoke Wil App's access to your TikTok account at any time via your TikTok account settings. You may also request deletion of any data we hold by contacting us.</p>

    <h2>6. Changes to This Policy</h2>
    <p>We may update this Privacy Policy from time to time. Continued use of the Service after changes constitutes acceptance of the updated policy.</p>

    <h2>7. Contact</h2>
    <p>Questions? Contact us at <a href="mailto:contact.wilapp@proton.me">contact.wilapp@proton.me</a>.</p>

    <footer>Wil App — Privacy Policy</footer>
    </body>
    </html>
    """


VIRAL_VIEW_THRESHOLD = 10_000


def _virality_score(views: int) -> int:
    """
    Score de viralité 0-100 pour UNE vidéo, basé sur son nombre de vues,
    ancré sur VIRAL_VIEW_THRESHOLD plutôt que sur le taux d'engagement
    (qui se dilue avec la portée, voir _analyze_content_patterns) et
    plutôt que sur un classement relatif aux autres vidéos du compte (ce
    qui donnerait un score qui varie selon quelles vidéos sont dans le
    lot analysé, et resterait incalculable pour une vidéo isolée).

    Échelle logarithmique pour que la progression reste lisible sur toute
    la plage de vues possibles (de 0 à plusieurs millions) : franchir le
    seuil "viral" (10k vues) donne un score autour de 67/100, 100k vues
    ~83/100, 1M+ vues plafonne à 100/100.
    """
    if views <= 0:
        return 0
    score = 100 * math.log10(views + 1) / math.log10(VIRAL_VIEW_THRESHOLD * 100 + 1)
    return max(0, min(100, round(score)))


def _extract_text_block(response_json: dict) -> str:
    """
    Extrait le texte d'une réponse Claude en cherchant le premier bloc de
    type "text" dans response["content"], au lieu de supposer que
    content[0] est ce bloc. Claude Sonnet 5 a le raisonnement étendu actif
    par défaut : content[0] peut être un bloc "thinking" avant le texte,
    ce qui faisait planter le code avec un KeyError('text') sur
    content[0]["text"] (bug identifié le 23/09/2026 juste après la
    bascule vers Sonnet 5). Renvoie le DERNIER bloc texte trouvé (le plus
    susceptible d'être la réponse finale plutôt qu'un raisonnement
    intermédiaire), vide si aucun.
    """
    content_blocks = response_json.get("content", [])
    text_blocks = [b["text"] for b in content_blocks if b.get("type") == "text"]
    return text_blocks[-1] if text_blocks else ""


# 3 pages = 60 vidéos max. Réduit depuis 10 (200 vidéos) : chaque page est
# un appel séquentiel à l'API TikTok (le curseur de pagination dépend de
# la réponse précédente, impossible à paralléliser), donc c'était la
# principale cause de lenteur de l'analyse. 60 vidéos récentes restent
# largement suffisantes pour des corrélations fiables.
MAX_PAGES = 3


async def _fetch_all_videos(client: httpx.AsyncClient, access_token: str) -> list[dict]:
    """
    Récupère TOUTES les vidéos du compte connecté, en gérant la pagination
    (TikTok ne renvoie que 20 vidéos par appel). Renvoie la liste complète
    de vidéos avec leurs stats (vues, likes, commentaires, partages).
    """
    all_videos: list[dict] = []
    cursor = 0
    has_more = True
    pages_fetched = 0

    while has_more and pages_fetched < MAX_PAGES:
        body = {"max_count": 20}
        if cursor:
            body["cursor"] = cursor

        response = await client.post(
            "https://open.tiktokapis.com/v2/video/list/",
            params={
                "fields": "id,title,cover_image_url,create_time,duration,"
                          "like_count,comment_count,share_count,view_count"
            },
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=body,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Erreur API TikTok (video.list): {response.status_code} {response.text}",
            )

        page_data = response.json().get("data", {})
        all_videos.extend(page_data.get("videos", []))

        has_more = page_data.get("has_more", False)
        cursor = page_data.get("cursor", 0)
        pages_fetched += 1

    return all_videos


async def _fetch_account_stats(client: httpx.AsyncClient, access_token: str) -> dict | None:
    """
    Récupère les stats agrégées du compte (abonnés, likes totaux
    cumulés depuis toujours, nombre de vidéos) via l'API TikTok — champs
    disponibles sous le scope "user.info.stats" (déjà approuvé en
    Production, voir TIKTOK_EXTRA_SCOPES). Renvoie None en cas d'échec
    plutôt que de faire échouer toute l'analyse : ces stats sont un
    complément, pas une donnée bloquante.
    """
    try:
        response = await client.get(
            "https://open.tiktokapis.com/v2/user/info/",
            params={"fields": "follower_count,following_count,likes_count,video_count"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code != 200:
            return None
        user_info = response.json().get("data", {}).get("user", {})
        return {
            "follower_count": user_info.get("follower_count", 0),
            "following_count": user_info.get("following_count", 0),
            "likes_count": user_info.get("likes_count", 0),
            "video_count": user_info.get("video_count", 0),
        }
    except Exception:
        return None


def _compute_engagement(video: dict) -> dict:
    """Calcule le taux d'engagement et le score de viralité d'une vidéo, et renvoie un dict enrichi."""
    views = video.get("view_count", 0)
    likes = video.get("like_count", 0)
    comments = video.get("comment_count", 0)
    shares = video.get("share_count", 0)
    engagement_rate = round((likes + comments + shares) / views * 100, 2) if views > 0 else 0
    hashtags = re.findall(r"#(\w+)", video.get("title", ""))
    return {
        "id": video.get("id"),
        "title": video.get("title", ""),
        "cover_image_url": video.get("cover_image_url", ""),
        "create_time": video.get("create_time"),
        "duration": video.get("duration"),
        "virality_score": _virality_score(views),
        "view_count": views,
        "like_count": likes,
        "comment_count": comments,
        "share_count": shares,
        "engagement_rate": engagement_rate,
        "hashtags": hashtags,
    }


def _analyze_hashtags(videos: list[dict]) -> dict:
    """
    Analyse l'usage des hashtags sur l'ensemble des vidéos :
    - fréquence de chaque hashtag
    - répétition excessive (même set de hashtags copié-collé partout)
    - hashtags associés à des vidéos à faible PORTÉE (vues), pas à un
      taux d'engagement faible — le taux d'engagement se dilue avec la
      portée (voir _analyze_content_patterns), donc comparer dessus ferait
      ressortir à tort les hashtags des vidéos à petite audience comme
      "sous-performants" alors qu'ils ont juste touché moins de monde.
    - vidéos sans aucun hashtag
    """
    all_tags: list[str] = []
    videos_without_tags = 0
    tag_to_views: dict[str, list[int]] = {}

    for video in videos:
        tags = video.get("hashtags", [])
        if not tags:
            videos_without_tags += 1
        for tag in tags:
            tag_lower = tag.lower()
            all_tags.append(tag_lower)
            tag_to_views.setdefault(tag_lower, []).append(video["view_count"])

    tag_counts = Counter(all_tags)
    total_videos = len(videos)
    most_common = tag_counts.most_common(10)

    # Un hashtag est "sur-répété" s'il apparaît sur plus de 70% des vidéos
    # ET qu'il n'y a que très peu de hashtags différents utilisés au total
    # (signe d'un même bloc de hashtags copié-collé sans réflexion).
    overused = [
        tag for tag, count in most_common
        if total_videos > 0 and count / total_videos >= 0.7
    ]

    # Hashtags dont le nombre de vues moyen associé est nettement inférieur
    # à la moyenne générale du compte (piste : ce hashtag n'aide pas la
    # portée, voire dessert les vidéos qui l'utilisent).
    overall_avg = (
        sum(v["view_count"] for v in videos) / len(videos) if videos else 0
    )
    underperforming_tags = [
        tag for tag, views in tag_to_views.items()
        if len(views) >= 2 and (sum(views) / len(views)) < overall_avg * 0.5
    ]

    return {
        "unique_hashtags_count": len(tag_counts),
        "most_used_hashtags": [{"tag": t, "count": c} for t, c in most_common],
        "overused_hashtags": overused,
        "underperforming_hashtags": underperforming_tags[:5],
        "videos_without_hashtags": videos_without_tags,
        "videos_without_hashtags_pct": (
            round(videos_without_tags / total_videos * 100, 1) if total_videos else 0
        ),
    }


def _avg_views(videos: list[dict]) -> float | None:
    return round(sum(v["view_count"] for v in videos) / len(videos), 0) if videos else None


def _analyze_content_patterns(videos: list[dict]) -> dict:
    """
    Calcule des corrélations précises entre des caractéristiques du titre/
    format des vidéos et leur PORTÉE (nombre de vues), pour donner à l'IA
    de vrais signaux chiffrés plutôt que de la laisser "deviner" un pattern
    en lisant une liste de titres. Chaque signal n'est renvoyé que s'il y a
    au moins 2 vidéos de chaque côté de la comparaison (sinon trop peu de
    données pour être fiable, et on préfère ne rien affirmer).

    On compare sur les VUES, pas le taux d'engagement : le taux
    d'engagement se dilue mécaniquement quand la portée augmente (une
    vidéo à faible audience touche surtout des fans fidèles, ratio gonflé),
    donc comparer dessus ferait ressortir des formats à faible portée comme
    "meilleurs" — l'inverse de ce qu'on veut pour identifier ce qui aide
    vraiment un compte à percer.
    """
    signals = {}

    with_question = [v for v in videos if "?" in (v.get("title") or "")]
    without_question = [v for v in videos if "?" not in (v.get("title") or "")]
    if len(with_question) >= 2 and len(without_question) >= 2:
        signals["question_in_title"] = {
            "avg_views_with": _avg_views(with_question),
            "avg_views_without": _avg_views(without_question),
            "count_with": len(with_question),
            "count_without": len(without_question),
        }

    with_digit = [v for v in videos if any(c.isdigit() for c in (v.get("title") or ""))]
    without_digit = [v for v in videos if not any(c.isdigit() for c in (v.get("title") or ""))]
    if len(with_digit) >= 2 and len(without_digit) >= 2:
        signals["digit_in_title"] = {
            "avg_views_with": _avg_views(with_digit),
            "avg_views_without": _avg_views(without_digit),
            "count_with": len(with_digit),
            "count_without": len(without_digit),
        }

    durations = [v["duration"] for v in videos if v.get("duration")]
    if len(durations) >= 4:
        median_duration = sorted(durations)[len(durations) // 2]
        short_videos = [v for v in videos if v.get("duration") and v["duration"] <= median_duration]
        long_videos = [v for v in videos if v.get("duration") and v["duration"] > median_duration]
        if len(short_videos) >= 2 and len(long_videos) >= 2:
            signals["video_duration"] = {
                "median_duration_seconds": median_duration,
                "avg_views_short": _avg_views(short_videos),
                "avg_views_long": _avg_views(long_videos),
                "count_short": len(short_videos),
                "count_long": len(long_videos),
            }

    # Créneau de publication (heure UTC — pas forcément l'heure locale du
    # créateur, à préciser si on affiche ce signal : c'est une tendance,
    # pas un horaire exact à respecter).
    buckets = {"nuit (0h-6h UTC)": [], "matin (6h-12h UTC)": [], "après-midi (12h-18h UTC)": [], "soir (18h-24h UTC)": []}
    for v in videos:
        if not v.get("create_time"):
            continue
        hour = time.gmtime(v["create_time"]).tm_hour
        if hour < 6:
            buckets["nuit (0h-6h UTC)"].append(v)
        elif hour < 12:
            buckets["matin (6h-12h UTC)"].append(v)
        elif hour < 18:
            buckets["après-midi (12h-18h UTC)"].append(v)
        else:
            buckets["soir (18h-24h UTC)"].append(v)
    populated_buckets = {k: v for k, v in buckets.items() if len(v) >= 2}
    if len(populated_buckets) >= 2:
        signals["posting_time"] = {
            label: {"avg_views": _avg_views(vids), "count": len(vids)}
            for label, vids in populated_buckets.items()
        }

    return signals


def _analyze_recency(videos: list[dict]) -> dict | None:
    """
    Compare la performance des vidéos les plus récentes à la meilleure
    vidéo du compte et à la moyenne générale, pour détecter un signal de
    plateau directement dans UNE analyse — sans attendre plusieurs
    semaines d'historique account_snapshots. `videos` doit déjà être
    trié par date décroissante (le plus récent en premier, cf. le tri
    dans analyze_account).

    Sert à produire le type d'observation "tes vidéos récentes plafonnent
    à X vues alors que ta meilleure a fait Y" — un signal réel sur CE
    compte, pas une comparaison inventée à d'autres comptes.
    """
    if len(videos) < 5:
        return None
    recent = videos[:5]
    recent_avg_views = round(sum(v["view_count"] for v in recent) / len(recent))
    overall_avg_views = round(sum(v["view_count"] for v in videos) / len(videos))
    best_views = max(v["view_count"] for v in videos)
    if overall_avg_views == 0 or best_views == 0:
        return None
    return {
        "recent_avg_views": recent_avg_views,
        "recent_count": len(recent),
        "overall_avg_views": overall_avg_views,
        "best_views": best_views,
        # Signal de plateau seulement si les vidéos récentes sont
        # nettement en dessous de la moyenne générale (pas juste du bruit
        # statistique normal) — évite de crier au plateau sur une simple
        # fluctuation.
        "is_plateau": recent_avg_views < overall_avg_views * 0.6,
    }


def _niche_cache_key(niche_category: str, lang: str) -> str:
    return f"{niche_category.strip().lower()}:{lang}"


def _cache_get(cache_type: str, cache_key: str) -> dict | list | None:
    """
    Lit le cache tendances (hashtags ou idées) depuis Supabase si
    configuré, sinon depuis les dicts en mémoire (repli local). Renvoie
    None si absent ou expiré (TTL 24h, TRENDING_CACHE_TTL_SECONDS).
    """
    supabase = get_supabase()
    if supabase:
        res = (
            supabase.table("trending_cache")
            .select("data,cached_at")
            .eq("cache_key", cache_key)
            .eq("cache_type", cache_type)
            .limit(1)
            .execute()
        )
        if not res.data:
            return None
        row = res.data[0]
        cached_at = datetime.fromisoformat(row["cached_at"]).timestamp()
        if (time.time() - cached_at) < TRENDING_CACHE_TTL_SECONDS:
            return row["data"]
        return None

    store = _trending_hashtags_cache if cache_type == "hashtags" else _trending_ideas_cache
    cached = store.get(cache_key)
    if cached and (time.time() - cached["cached_at"]) < TRENDING_CACHE_TTL_SECONDS:
        return cached["hashtags"] if cache_type == "hashtags" else cached["data"]
    return None


def _cache_set(cache_type: str, cache_key: str, data: dict | list) -> None:
    """Écrit dans le cache tendances (Supabase si configuré, sinon en mémoire)."""
    supabase = get_supabase()
    if supabase:
        supabase.table("trending_cache").upsert({
            "cache_key": cache_key,
            "cache_type": cache_type,
            "data": data,
            "cached_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    elif cache_type == "hashtags":
        _trending_hashtags_cache[cache_key] = {"hashtags": data, "cached_at": time.time()}
    else:
        _trending_ideas_cache[cache_key] = {"data": data, "cached_at": time.time()}


async def _get_trending_hashtags(niche_category: str, lang: str) -> list[str] | None:
    """
    Récupère les hashtags réellement tendance pour une catégorie de niche
    et une langue données, via l'outil de recherche web de Claude.
    Résultat mis en cache 24h par (catégorie, langue) pour limiter le coût
    et la latence — une recherche par catégorie+langue par jour maximum,
    pas une par utilisateur/analyse.
    """
    if not niche_category or not ANTHROPIC_API_KEY:
        return None

    cache_key = _niche_cache_key(niche_category, lang)
    cached = _cache_get("hashtags", cache_key)
    if cached:
        return cached

    prompt = f"""Cherche sur le web les hashtags TikTok réellement tendance
en ce moment pour la catégorie de niche suivante : "{niche_category}",
pour un public dont la langue a le code ISO 639-1 "{lang}".

Réponds UNIQUEMENT avec un objet JSON (pas de markdown, pas de balises de
code), avec exactement ce champ :
{{"hashtags": ["5 hashtags tendance actuels, sans le symbole #"]}}"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-5",
                    "max_tokens": 800,
                    "output_config": {"effort": "low"},
                    "tools": [
                        {"type": "web_search_20250305", "name": "web_search", "max_uses": 2}
                    ],
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

        if response.status_code != 200:
            return None

        content_blocks = response.json().get("content", [])
        text_blocks = [b["text"] for b in content_blocks if b.get("type") == "text"]
        raw_text = text_blocks[-1] if text_blocks else ""

        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        hashtags = parsed.get("hashtags")
        if not hashtags:
            return None

        _cache_set("hashtags", cache_key, hashtags)
        return hashtags
    except Exception:
        # En cas d'échec (timeout, réponse invalide...), on ne casse pas
        # toute l'analyse — on retombe simplement sur les suggestions
        # génériques déjà présentes dans le rapport IA.
        return None


_trending_ideas_cache: dict[str, dict] = {}


async def _get_trending_content_ideas(niche_category: str, lang: str) -> dict | None:
    """
    Récupère, via recherche web, des idées de vidéos et des types de
    hooks (accroches) actuellement tendance pour une catégorie de niche et
    une langue données. Résultat mis en cache 24h par (catégorie, langue)
    (même logique que les hashtags tendance), pour limiter le coût des
    recherches web.
    """
    if not niche_category or not ANTHROPIC_API_KEY:
        return None

    cache_key = _niche_cache_key(niche_category, lang)
    cached = _cache_get("ideas", cache_key)
    if cached:
        return cached

    lang_instruction = (
        "RÉDIGÉ EN FRANÇAIS" if lang == "fr"
        else f'rédigé dans la langue de code ISO 639-1 "{lang}"'
    )
    prompt = f"""Cherche sur le web les tendances actuelles sur TikTok pour
la catégorie de niche suivante : "{niche_category}" (public dont la langue
a le code ISO 639-1 "{lang}") — à la fois en termes de formats/idées de
vidéos qui marchent bien en ce moment, et de types d'accroches (hooks)
efficaces actuellement.

Réponds UNIQUEMENT avec un objet JSON (pas de markdown, pas de balises de
code), {lang_instruction}, avec exactement ces champs :
{{
  "video_ideas": ["4-5 idées de vidéos concrètes et actuelles pour cette niche"],
  "trending_hooks": ["3-4 types d'accroches (hooks) qui fonctionnent bien en ce moment, avec un exemple concret de phrase pour chacune"]
}}"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-5",
                    "max_tokens": 1400,
                    "output_config": {"effort": "low"},
                    "tools": [
                        {"type": "web_search_20250305", "name": "web_search", "max_uses": 2}
                    ],
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

        if response.status_code != 200:
            return None

        content_blocks = response.json().get("content", [])
        text_blocks = [b["text"] for b in content_blocks if b.get("type") == "text"]
        raw_text = text_blocks[-1] if text_blocks else ""

        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        parsed = json.loads(cleaned)
        if not parsed.get("video_ideas") and not parsed.get("trending_hooks"):
            return None

        _cache_set("ideas", cache_key, parsed)
        return parsed
    except Exception:
        return None


@app.get("/api/trending-ideas", response_class=JSONResponse)
async def trending_ideas(niche_category: str, lang: str = "fr"):
    """
    Route dédiée : renvoie des idées de vidéos et des hooks tendance pour
    une catégorie de niche et une langue données. Peut être appelée
    séparément de l'analyse complète du compte (ex: bouton "Idées
    tendance" dans l'app), avec le même système de cache 24h par
    catégorie+langue pour limiter le coût.
    """
    if niche_category not in NICHE_CATEGORIES:
        niche_category = "Autre"
    result = await _get_trending_content_ideas(niche_category, lang)
    if not result:
        raise HTTPException(
            status_code=502,
            detail="Impossible de récupérer les tendances pour le moment. Réessaie plus tard.",
        )
    return JSONResponse(content=result)


@app.get("/api/analyze-account", response_class=JSONResponse)
async def analyze_account(
    session: str,
    display_name: str = "",
    username: str = "",
    bio: str = "",
):
    """
    Route UNIQUE et complète d'analyse de compte. Combine :
    1. Les stats de toutes les vidéos du compte (engagement, viralité)
    2. Une analyse IA (Claude) du profil ET de la performance globale

    Nécessite le scope "video.list" (voir TIKTOK_EXTRA_SCOPES) en plus des
    scopes de base déjà approuvés. Le paramètre "session" est l'identifiant
    reçu par l'app après la connexion (le vrai access_token reste côté
    serveur, jamais transmis au client).
    """
    session_data = _get_session(session)
    if not session_data:
        raise HTTPException(
            status_code=401,
            detail="Session invalide ou expirée. Reconnecte-toi avec TikTok.",
        )
    access_token = session_data["access_token"]
    open_id = session_data["open_id"]

    # 1. Récupération de toutes les vidéos + calcul des statistiques.
    # Si le scope "video.list" n'est pas encore approuvé côté TikTok
    # (review en attente), cet appel échoue — dans ce cas, on continue
    # quand même avec une analyse basée uniquement sur le profil, plutôt
    # que de faire échouer toute la route.
    stats = None
    account_stats = None
    try:
        # Timeout explicite et généreux : le défaut d'httpx (5s) est trop
        # court pour une pagination de plusieurs pages vers l'API TikTok
        # depuis Render, et un dépassement levait une httpx.ReadTimeout
        # brute non rattrapée par le except HTTPException ci-dessous,
        # provoquant un 500 au lieu du repli "analyse sans stats vidéo"
        # pourtant prévu (bug identifié le 23/09/2026 via reproduction
        # locale avec une vraie session).
        async with httpx.AsyncClient(timeout=30) as client:
            # Vidéos et stats de compte (abonnés/likes totaux) récupérées
            # en parallèle plutôt qu'en séquence, pour ne pas ajouter de
            # latence — cf. le travail de vitesse fait précédemment.
            raw_videos, account_stats = await asyncio.gather(
                _fetch_all_videos(client, access_token),
                _fetch_account_stats(client, access_token),
            )

        enriched_videos = [_compute_engagement(v) for v in raw_videos]

        # "Meilleure"/"pire" vidéo restent sélectionnées par nombre de vues
        # (portée réelle), PAS par taux d'engagement : le taux d'engagement
        # se dilue mécaniquement quand la portée augmente (une vidéo à 800
        # vues vue presque uniquement par des fans fidèles aura un ratio
        # bien plus élevé qu'une vidéo à 1M de vues touchant une audience
        # froide qui ne connaît pas le compte). Calculé indépendamment de
        # l'ordre d'affichage de la liste (voir plus bas).
        best_video = max(enriched_videos, key=lambda v: v["view_count"]) if enriched_videos else None
        worst_video = min(enriched_videos, key=lambda v: v["view_count"]) if len(enriched_videos) > 1 else None

        # La liste affichée, elle, est triée par date (plus récente
        # d'abord) — comme le grid natif de TikTok — pas par performance :
        # l'utilisateur doit reconnaître ses vidéos dans l'ordre où il les
        # a postées, pas dans un ordre qui bouge à chaque analyse.
        enriched_videos.sort(key=lambda v: v["create_time"] or 0, reverse=True)

        total = len(enriched_videos)
        viral_count = sum(1 for v in enriched_videos if v["view_count"] >= VIRAL_VIEW_THRESHOLD)
        non_viral_count = total - viral_count
        viral_percentage = round(viral_count / total * 100, 2) if total > 0 else 0
        non_viral_percentage = round(non_viral_count / total * 100, 2) if total > 0 else 0
        average_engagement_rate = (
            round(sum(v["engagement_rate"] for v in enriched_videos) / total, 2) if total > 0 else 0
        )
        average_view_count = (
            round(sum(v["view_count"] for v in enriched_videos) / total) if total > 0 else 0
        )

        # Score de viralité DU COMPTE (0-100), pas juste par vidéo : mélange
        # à parts égales la performance récente (5 dernières vidéos) et la
        # performance globale, via le même _virality_score que les vidéos
        # individuelles. Évite qu'un unique gros succès ancien masque un
        # plateau actuel (ou l'inverse, qu'un plateau récent efface un vrai
        # historique de compétence) — reflète la STRUCTURE DU RÉSUMÉ du
        # prompt (preuve de compétence + écart actuel), pas juste une moyenne
        # brute qui gommerait ce contraste.
        recency_for_score = _analyze_recency(enriched_videos)
        if recency_for_score:
            blended_views = round(
                0.5 * recency_for_score["recent_avg_views"] + 0.5 * recency_for_score["overall_avg_views"]
            )
        else:
            blended_views = average_view_count
        account_virality_score = _virality_score(blended_views)

        # Ratio likes/abonnés (likes totaux cumulés du compte / nombre
        # d'abonnés) : signal de fidélité de l'audience existante,
        # complémentaire aux vues (qui mesurent la portée, pas la loyauté).
        # None si les stats de compte n'ont pas pu être récupérées.
        follower_count = account_stats.get("follower_count") if account_stats else None
        account_likes_count = account_stats.get("likes_count") if account_stats else None
        likes_followers_ratio = (
            round(account_likes_count / follower_count, 2)
            if follower_count else None
        )

        stats = {
            "total_videos_analyzed": total,
            "average_engagement_rate": average_engagement_rate,
            "average_view_count": average_view_count,
            "account_virality_score": account_virality_score,
            "follower_count": follower_count,
            "account_likes_count": account_likes_count,
            "likes_followers_ratio": likes_followers_ratio,
            "viral_threshold_views": VIRAL_VIEW_THRESHOLD,
            "viral_count": viral_count,
            "non_viral_count": non_viral_count,
            "viral_percentage": viral_percentage,
            "non_viral_percentage": non_viral_percentage,
            "best_video": best_video,
            "worst_video": worst_video,
            "videos": enriched_videos,
        }
    except (HTTPException, httpx.HTTPError):
        # video.list indisponible (scope pas encore approuvé, compte sans
        # vidéo, OU erreur réseau/timeout vers l'API TikTok) : on continue
        # sans les stats vidéo, pas bloquant. httpx.HTTPError est la
        # classe de base de TOUTES les erreurs de transport httpx (timeout,
        # connexion refusée...) — sans ça, ces erreurs réseau remontaient
        # non gérées et faisaient planter toute la route en 500 au lieu du
        # repli "analyse sans stats vidéo" pourtant prévu.
        stats = None

    # 2. Analyse IA (profil + performance si disponible), si Anthropic
    # est configuré. Fonctionne même sans les stats vidéo (stats=None).
    ai_report = None
    if ANTHROPIC_API_KEY:
        if stats and stats["videos"]:
            videos = stats["videos"]

            # Calcul de la fréquence de publication à partir des horodatages
            # (create_time est en secondes Unix, fourni par TikTok).
            timestamps = sorted(
                [v["create_time"] for v in videos if v.get("create_time")], reverse=True
            )
            if len(timestamps) >= 2:
                span_days = (timestamps[0] - timestamps[-1]) / 86400
                freq_text = (
                    f"{len(timestamps)} vidéos sur {span_days:.0f} jours "
                    f"(environ {len(timestamps) / span_days * 7:.1f} vidéos/semaine)"
                    if span_days > 0 else "toutes publiées le même jour"
                )
            else:
                freq_text = "pas assez de données pour calculer une fréquence"

            # Titres des vidéos les plus récentes (donne le vrai style/sujets)
            recent_titles = "\n".join(
                f'  - "{v["title"] or "(sans titre)"}" — {v["view_count"]} vues, {v["engagement_rate"]}% engagement'
                for v in videos[:8]
            )

            best = stats["best_video"]
            worst = stats["worst_video"]
            best_worst_text = ""
            if best:
                best_worst_text += (
                    f'\nVidéo la plus vue (portée) : "{best["title"] or "(sans titre)"}" '
                    f'— {best["view_count"]} vues, {best["like_count"]} likes, '
                    f'{best["engagement_rate"]}% engagement'
                )
            if worst:
                best_worst_text += (
                    f'\nVidéo la moins vue (portée) : "{worst["title"] or "(sans titre)"}" '
                    f'— {worst["view_count"]} vues, {worst["like_count"]} likes, '
                    f'{worst["engagement_rate"]}% engagement'
                )
            best_worst_text += (
                "\nATTENTION : le taux d'engagement (%) baisse mécaniquement "
                "quand la portée augmente (une vidéo à faible audience "
                "touche surtout des fans fidèles, ratio gonflé ; une vidéo "
                "qui perce touche une audience froide qui interagit moins). "
                "Ne jamais présenter une vidéo à faible nombre de vues comme "
                "'meilleure' juste parce que son % d'engagement est plus "
                "élevé — la vraie réussite ici, c'est le nombre de vues."
            )

            # Signal de plateau récent : compare les vidéos les plus
            # récentes à la meilleure vidéo et à la moyenne du compte —
            # permet de détecter et nommer un plateau dès cette analyse,
            # sans attendre l'historique long terme.
            recency = _analyze_recency(videos)
            if recency:
                best_worst_text += (
                    f"\n\nSignal de récence : les {recency['recent_count']} vidéos "
                    f"les plus récentes font {recency['recent_avg_views']} vues en "
                    f"moyenne, contre {recency['overall_avg_views']} sur l'ensemble "
                    f"du compte et {recency['best_views']} pour la meilleure vidéo "
                    f"jamais postée."
                    + (
                        " C'est un vrai plateau (nettement en dessous de la "
                        "moyenne du compte) — nomme-le explicitement si tu "
                        "l'utilises dans le résumé ou les améliorations."
                        if recency["is_plateau"] else
                        " Pas d'écart flagrant, ne pas parler de 'plateau' ici."
                    )
                )

            # Analyse des hashtags : répétition, sur-utilisation, hashtags
            # qui sous-performent par rapport à la moyenne du compte.
            hashtag_stats = _analyze_hashtags(videos)
            top_tags_text = ", ".join(
                f"#{t['tag']} ({t['count']} vidéos)" for t in hashtag_stats["most_used_hashtags"]
            ) or "aucun hashtag détecté sur ces vidéos"
            overused_text = (
                ", ".join(f"#{t}" for t in hashtag_stats["overused_hashtags"])
                or "aucun"
            )
            underperforming_text = (
                ", ".join(f"#{t}" for t in hashtag_stats["underperforming_hashtags"])
                or "aucun détecté"
            )

            hashtag_block = f"""
Analyse des hashtags utilisés :
- Vidéos sans aucun hashtag : {hashtag_stats['videos_without_hashtags']}/{len(videos)} ({hashtag_stats['videos_without_hashtags_pct']}%)
- Nombre de hashtags différents utilisés au total : {hashtag_stats['unique_hashtags_count']}
- Hashtags les plus utilisés : {top_tags_text}
- Hashtags SUR-UTILISÉS (présents sur ≥70% des vidéos, signe de copié-collé sans réflexion) : {overused_text}
- Hashtags SOUS-PERFORMANTS (vues moyennes ≤50% de la moyenne du compte quand ils sont utilisés) : {underperforming_text}"""

            # Corrélations précises titre/format/horaire ↔ PORTÉE (vues),
            # calculées en Python (pas laissées à l'appréciation du modèle)
            # pour forcer des affirmations vérifiables plutôt que du ressenti.
            # Comparaison sur les vues, pas le taux d'engagement : voir la
            # note dans _analyze_content_patterns pour la raison (le %
            # d'engagement se dilue mécaniquement avec la portée).
            content_patterns = _analyze_content_patterns(videos)
            pattern_lines = []
            if "question_in_title" in content_patterns:
                p = content_patterns["question_in_title"]
                pattern_lines.append(
                    f"- Titres avec un '?' : {p['avg_views_with']:.0f} vues en moyenne "
                    f"({p['count_with']} vidéos) vs {p['avg_views_without']:.0f} vues sans '?' "
                    f"({p['count_without']} vidéos)"
                )
            if "digit_in_title" in content_patterns:
                p = content_patterns["digit_in_title"]
                pattern_lines.append(
                    f"- Titres avec un chiffre : {p['avg_views_with']:.0f} vues en moyenne "
                    f"({p['count_with']} vidéos) vs {p['avg_views_without']:.0f} vues sans chiffre "
                    f"({p['count_without']} vidéos)"
                )
            if "video_duration" in content_patterns:
                p = content_patterns["video_duration"]
                pattern_lines.append(
                    f"- Vidéos courtes (≤{p['median_duration_seconds']}s) : {p['avg_views_short']:.0f} "
                    f"vues en moyenne ({p['count_short']} vidéos) vs vidéos longues : "
                    f"{p['avg_views_long']:.0f} vues ({p['count_long']} vidéos)"
                )
            if "posting_time" in content_patterns:
                for label, p in content_patterns["posting_time"].items():
                    pattern_lines.append(
                        f"- Publié le {label} : {p['avg_views']:.0f} vues en moyenne ({p['count']} vidéos)"
                    )
            content_pattern_block = (
                "\nCorrélations calculées entre format/titre/horaire et PORTÉE "
                "(nombre de vues, chiffres réels, pas une estimation) — "
                "volontairement PAS le taux d'engagement, qui se dilue "
                "mécaniquement avec la portée et donnerait un signal trompeur :\n"
                + "\n".join(pattern_lines)
                if pattern_lines else
                "\nPas assez de vidéos pour calculer des corrélations fiables "
                "titre/format/horaire ↔ vues — ne pas en inventer."
            )

            ratio_line = (
                f"\n- Ratio likes/abonnés (likes TOTAUX du compte / abonnés) : "
                f"{stats['likes_followers_ratio']} — signal de fidélité de "
                f"l'audience existante, distinct des vues (qui mesurent la "
                f"portée, pas la loyauté). Citable comme point fort UNIQUEMENT "
                f"s'il est notablement élevé (>1) ou comme point faible s'il "
                f"est très bas (<0.2) ; sinon ne pas le mentionner pour rien."
                if stats.get("likes_followers_ratio") is not None else ""
            )

            performance_block = f"""
Données de performance (chiffres réels de son compte) :
- Nombre total de vidéos analysées : {stats['total_videos_analyzed']}
- Fréquence de publication : {freq_text}
- Taux d'engagement moyen : {stats['average_engagement_rate']}%
- Vidéos ayant dépassé 10 000 vues ("virales") : {stats['viral_count']} ({stats['viral_percentage']}%)
- Vidéos en dessous de 10 000 vues : {stats['non_viral_count']} ({stats['non_viral_percentage']}%)
- Score de viralité du compte (0-100, mélange récent/global) : {stats['account_virality_score']}/100{ratio_line}
{best_worst_text}
{hashtag_block}
{content_pattern_block}

Titres des vidéos récentes, avec leurs stats individuelles (utilise-les
pour repérer de VRAIS patterns concrets — sujets récurrents, mots dans
les titres qui reviennent sur les vidéos qui marchent bien, etc.) :
{recent_titles}"""
        else:
            performance_block = """
Données de performance : non disponibles pour cette analyse (base-toi
uniquement sur le profil ci-dessus, ne mentionne pas l'absence de ces
données comme un problème)."""

        prompt = f"""Tu es un coach de croissance TikTok senior, connu pour des analyses
extrêmement concrètes et jamais génériques.

{STYLE_GUIDE}

Profil :
- Nom affiché : {display_name}
- Nom d'utilisateur : @{username}
- Bio : "{bio or 'Aucune bio renseignée'}"
{performance_block}

MÉTHODE DE TRAVAIL (fais ça avant de répondre, mentalement) :
1. PRIORITÉ ABSOLUE : utilise les corrélations déjà calculées ci-dessus
   (section "Corrélations calculées...") — ce sont de vrais signaux, pas
   une estimation. Si un signal montre un écart net (ex: beaucoup plus de
   vues avec un point d'interrogation dans le titre), utilise-le pour
   choisir quoi dire. Pour "summary"/"strengths" : tu PEUX citer le
   chiffre le plus marquant tel quel (ex: "955K vues, 52K likes") s'il
   prouve une vraie réussite — règle d'or n°2 (hybride) du guide de
   style. Pour "improvements"/"hashtag_diagnosis" : traduis TOUJOURS en
   mot simple de comparaison ("beaucoup plus", "très peu"), JAMAIS de
   chiffre exact. N'ignore jamais un signal disponible pour dire quelque
   chose de plus vague à la place. Ne parle JAMAIS du taux d'engagement
   (%) comme mesure de succès d'une vidéo — les vues sont la vraie
   mesure (voir la note dans le bloc de corrélations).
2. Si un "Signal de récence" est marqué comme un vrai plateau, dis-le
   simplement (ex: "tes dernières vidéos ont beaucoup moins de succès que
   ta meilleure vidéo") — c'est souvent LE constat le plus utile pour un
   créateur, ne le noie pas dans le reste. Aucun chiffre.
3. Complète avec au moins 1 pattern supplémentaire trouvé toi-même en
   comparant les titres/stats des vidéos entre elles (pas des généralités
   sur TikTok en général) — toujours traduit en mots simples.
4. NOMME UNE TECHNIQUE PRÉCISE, pas juste un défaut, ET formule-la comme
   une INSTRUCTION à l'impératif (RÈGLE D'OR N°3 du guide de style) : soit
   ce qu'il FAUT faire ("Commence par..."), soit ce qu'il NE FAUT PAS
   faire ("Arrête de..."). Utilise le vocabulaire du guide de style
   (accroche, angle, déclencheur, comment la vidéo est construite, donner
   envie de rester) pour dire CE QUI manque concrètement — "Arrête
   d'annoncer juste le sujet dans ton accroche, commence plutôt par une
   question" plutôt que "sois plus créatif" ou "ton accroche pourrait
   être améliorée".
5. INTERDIT : ne JAMAIS comparer ce compte à "d'autres comptes qui
   percent" ou "les pros" sans donnée réelle pour l'étayer — on n'a pas
   de base de comparaison entre comptes aujourd'hui. Reste sur les
   propres résultats de CE compte (sa meilleure vidéo vs ses vidéos
   récentes, avec/sans tel pattern, etc.). Nommer une technique manquante
   (règle 4) ne veut pas dire inventer une comparaison à des tiers.
6. Chaque point fort et chaque amélioration doit s'appuyer sur un élément
   réel de CE compte (un titre, un vrai signal) — jamais un conseil qui
   pourrait s'appliquer à n'importe quel compte. Un point fort peut citer
   UN chiffre marquant (règle d'or n°2) ; une amélioration n'en cite
   JAMAIS.
7. Pour le diagnostic hashtags : utilise en priorité les hashtags
   SUR-UTILISÉS et SOUS-PERFORMANTS déjà identifiés ci-dessus plutôt que de
   re-analyser toi-même — base-toi UNIQUEMENT sur les signaux fournis, ne
   suppose rien d'autre, et traduis en mots simples sans chiffre.
8. Si aucun signal ni pattern clair n'est disponible par manque de données,
   dis-le honnêtement plutôt que d'inventer un conseil générique.

RAPPEL LE PLUS IMPORTANT (règle hybride, RÈGLE D'OR N°2) : "summary" et
"strengths" PEUVENT citer LE chiffre le plus marquant s'il prouve une
vraie réussite (ex: "955K vues, 52K likes") — jamais une liste de
chiffres, un seul, le plus parlant. "improvements" et
"hashtag_diagnosis" restent SANS AUCUN CHIFFRE : uniquement des mots de
comparaison simples. Et écris comme si tu parlais à un élève de CM2 :
phrases courtes, mots simples, une idée par phrase.

STRUCTURE DU RÉSUMÉ (important) : en 1-2 phrases courtes, suis cet arc —
(a) une preuve que ce créateur sait déjà créer du bon contenu (une vidéo
qui a bien marché — cite le chiffre le plus marquant s'il y en a un,
sinon décris-la en mots simples), (b) l'écart avec sa situation
actuelle, expliqué avec une technique nommée (règle 4) et SANS chiffre
— pas juste "il te manque de la régularité". Termine sur un ton qui
donne envie d'agir, pas alarmiste.

BRIÈVETÉ (important) : le rapport doit être court et direct — un créateur
doit pouvoir le lire en 15 secondes. Pas de phrase d'intro/conclusion
inutile, pas de reformulation, une idée par phrase. Précis > exhaustif.

Réponds avec un objet JSON (pas de markdown, pas de balises de code, juste
du JSON brut) contenant exactement ces champs, avec du texte en FRANÇAIS
TRÈS SIMPLE (niveau CM2) :
{{
  "niche": "une courte phrase décrivant la niche de contenu probable",
  "niche_category": "choisis EXACTEMENT une valeur parmi cette liste fermée, recopiée telle quelle (aucune autre valeur autorisée) : {json.dumps(NICHE_CATEGORIES, ensure_ascii=False)}",
  "summary": "1-2 phrases MAXIMUM, niveau CM2, suivant la STRUCTURE DU RÉSUMÉ ci-dessus — UN chiffre marquant autorisé pour la preuve de réussite, ZÉRO chiffre pour l'écart/reproche",
  "strengths": ["1-2 points forts MAXIMUM, chacun en 1 phrase simple, appuyé sur un vrai signal de ce compte — ce que le créateur fait déjà bien et doit continuer ; UN chiffre marquant autorisé s'il prouve la réussite (règle d'or n°2)"],
  "improvements": ["1-2 instructions MAXIMUM à l'impératif (RÈGLE D'OR N°3), chacune en 1 phrase simple, ZÉRO chiffre : soit ce qu'il FAUT faire ('Commence à...'), soit ce qu'il NE FAUT PAS faire ('Arrête de...') — jamais une simple observation"],
  "hashtag_diagnosis": "1 phrase MAXIMUM, ZÉRO chiffre, expliquant si les hashtags actuels aident ou nuisent",
  "suggested_hashtags": ["5 hashtags pertinents pour cette niche, sans le symbole #"]
}}

Le contenu de chaque champ doit être rédigé entièrement en français, très
simple, sans aucun chiffre (sauf le champ suggested_hashtags qui n'en
contient de toute façon pas)."""

        # Note : la recherche web en direct (pour des hashtags vraiment
        # "tendance maintenant") a été désactivée pour l'instant, car plus
        # coûteuse et plus lente. Les hashtags suggérés se basent donc sur
        # les connaissances générales de Claude, pas sur une recherche en
        # temps réel. À réactiver plus tard si besoin (voir version
        # précédente avec le paramètre "tools": [{"type": "web_search_..."}]).
        # Appel enveloppé dans un try/except : sans ça, une erreur réseau/
        # timeout vers l'API Anthropic (httpx.HTTPError, PAS une
        # HTTPException) remonte non gérée et fait planter toute la route
        # en 500 — même bug que celui déjà corrigé pour l'appel TikTok.
        # response reste None si l'appel échoue, et le bloc suivant
        # retombe alors proprement sur ai_report=None au lieu de planter.
        response = None
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": ANTHROPIC_API_KEY,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-sonnet-5",
                        "max_tokens": 1500,
                        "output_config": {"effort": "low"},
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
        except httpx.HTTPError:
            response = None

        if response and response.status_code == 200:
            raw_text = _extract_text_block(response.json())

            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:]
                cleaned = cleaned.strip()
            try:
                ai_report = json.loads(cleaned)
            except json.JSONDecodeError:
                ai_report = None

            # Claude doit choisir dans la liste fermée NICHE_CATEGORIES, mais
            # on ne lui fait pas confiance aveuglément (variation de formulation,
            # accents, etc.) : toute valeur hors liste retombe sur "Autre" pour
            # que la clé de cache des tendances reste stable.
            if ai_report and ai_report.get("niche_category") not in NICHE_CATEGORIES:
                ai_report["niche_category"] = "Autre"

    # Langue du compte, détectée depuis la bio + les titres de vidéos
    # récentes (fallback "fr" si texte trop court). Sert à affiner la clé
    # de cache des tendances (une même catégorie de niche a des tendances
    # différentes selon la langue) et à répondre dans la bonne langue.
    video_titles = [v["title"] for v in stats["videos"]] if stats and stats.get("videos") else []
    lang = _detect_language(bio, video_titles)

    # 3. Remplace les hashtags génériques par de vrais hashtags tendance,
    # UNIQUEMENT si déjà en cache (lecture instantanée, catégorie de niche
    # + langue, cf. _get_trending_hashtags). Si le cache est froid, on ne
    # bloque JAMAIS la réponse sur une recherche web en direct (c'était la
    # plus grosse source de lenteur de l'analyse) : on garde les
    # suggestions déjà produites par l'étape précédente, et on lance le
    # remplissage du cache en tâche de fond pour que la PROCHAINE analyse
    # sur cette catégorie+langue soit rapide.
    if ai_report and ai_report.get("niche_category"):
        cache_key = _niche_cache_key(ai_report["niche_category"], lang)
        trending = _cache_get("hashtags", cache_key)
        if trending:
            ai_report["suggested_hashtags"] = trending
        else:
            asyncio.create_task(_get_trending_hashtags(ai_report["niche_category"], lang))

    # 4. Snapshot pour l'historique (diagnostic de plateau, rapport mensuel).
    # Uniquement si on a de vraies stats vidéo — un snapshot sans métriques
    # n'a pas de valeur pour un suivi dans le temps.
    if stats:
        niche_category = ai_report.get("niche_category") if ai_report else None
        _save_account_snapshot(open_id, username, niche_category, lang, stats)

    return JSONResponse(content={
        "stats": stats,
        "ai_report": ai_report,
        "lang": lang,
    })


@app.get("/api/analyze-video", response_class=JSONResponse)
async def analyze_video(
    title: str = "",
    view_count: int = 0,
    like_count: int = 0,
    comment_count: int = 0,
    share_count: int = 0,
    duration: int = 0,
    virality_score: int = 0,
    account_avg_views: int = 0,
    niche_category: str = "",
):
    """
    Analyse IA d'UNE vidéo précise : pourquoi elle a (ou n'a pas) percé,
    ses points forts, ses points faibles, et des actions concrètes pour
    la suite. Appelée depuis le bouton "Analyser la vidéo" sous chaque
    vignette du dashboard.

    Ne nécessite PAS de session TikTok : les stats de la vidéo sont déjà
    connues côté client (renvoyées par /api/analyze-account), donc pas
    besoin de rappeler l'API TikTok ni de revalider une session — juste
    un appel Claude sur des chiffres déjà en main, rapide et simple.
    """
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY manquant dans .env")

    comparison_text = (
        f"Pour comparaison, la moyenne du compte est de {account_avg_views} vues par vidéo."
        if account_avg_views > 0
        else "Pas de moyenne de compte disponible pour comparaison — ne pas en inventer une."
    )

    prompt = f"""Tu es un coach de croissance TikTok senior, connu pour des
analyses extrêmement concrètes et jamais génériques.

{STYLE_GUIDE}

Analyse CETTE vidéo précise, avec ses vraies données (pas le compte en
général) :
- Titre : "{title or '(sans titre)'}"
- Vues : {view_count}
- Likes : {like_count}, Commentaires : {comment_count}, Partages : {share_count}
- Durée : {duration if duration else 'inconnue'} secondes
- Score de viralité calculé (0-100, basé sur les vues) : {virality_score}/100
- Niche du compte : {niche_category or 'non précisée'}
{comparison_text}

Explique pourquoi cette vidéo a (ou n'a pas) percé, en te basant sur les
chiffres ci-dessus. Pas de conseil qui pourrait s'appliquer à n'importe
quelle vidéo.

NOMME UNE TECHNIQUE PRÉCISE (voir VOCABULAIRE À UTILISER dans le guide
de style ci-dessus) plutôt qu'un jugement vague : le titre ("{title or '(sans titre)'}")
est ta seule fenêtre sur le hook/l'angle de cette vidéo — analyse-le
concrètement (pose-t-il une question ? annonce-t-il juste le sujet ?
crée-t-il une tension ?) au lieu de dire "le contenu est bon/mauvais".
INTERDIT de comparer à "d'autres vidéos qui percent" sans donnée réelle
— compare uniquement aux chiffres fournis ici (vues, moyenne du compte).

RAPPEL LE PLUS IMPORTANT (règle hybride, RÈGLE D'OR N°2 du guide de
style) : "strengths" PEUT citer LE chiffre le plus marquant s'il prouve
une vraie réussite de cette vidéo (ex: "cette vidéo a fait 955K vues") —
un seul, le plus parlant. "weaknesses" et "action_plan" restent SANS
AUCUN CHIFFRE : traduis toujours en mots simples ("beaucoup moins vue
que d'habitude"). Écris comme pour un élève de CM2 : phrases courtes,
mots simples, une idée par phrase. "weaknesses" et "action_plan"
doivent être des INSTRUCTIONS à l'impératif (RÈGLE D'OR N°3 du guide de
style), pas des observations : "weaknesses" = ce qu'il NE FAUT PAS
faire ("Arrête de..."), "action_plan" = ce qu'il FAUT faire à la place
("Fais...", "Commence par...").

BRIÈVETÉ (important) : réponse courte et directe, lisible en 15 secondes.

Réponds avec un objet JSON (pas de markdown, pas de balises de code,
juste du JSON brut) contenant exactement ces champs, en FRANÇAIS TRÈS
SIMPLE (niveau CM2) :
{{
  "strengths": ["1-2 raisons concrètes MAXIMUM, en phrases simples, expliquant ce qui a bien fonctionné sur cette vidéo — UN chiffre marquant autorisé s'il prouve la réussite (règle d'or n°2)"],
  "weaknesses": ["1-2 instructions MAXIMUM à l'impératif commençant par 'Arrête de...' ou 'Évite de...', en phrases simples et SANS chiffre, nommant une technique manquante plutôt qu'un défaut vague"],
  "action_plan": ["1-2 instructions MAXIMUM à l'impératif commençant par 'Fais...' ou 'Commence par...', en phrases simples et SANS chiffre, pour qu'une prochaine vidéo similaire ait plus de chances de devenir virale"]
}}"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-5",
                    "max_tokens": 1000,
                    "output_config": {"effort": "low"},
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Erreur réseau vers l'API Anthropic.")

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur API Anthropic: {response.status_code} {response.text}",
        )

    raw_text = _extract_text_block(response.json())
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Réponse IA invalide.")

    return JSONResponse(content=result)


async def _transcribe_video(client: httpx.AsyncClient, video_bytes: bytes) -> str:
    """
    Transcrit un fichier vidéo/audio via AssemblyAI : upload du fichier
    brut, lancement de la transcription, puis attente (polling) jusqu'à
    complétion. AssemblyAI extrait l'audio automatiquement des conteneurs
    vidéo courants (mp4, mov...), pas besoin de le faire nous-mêmes.
    Lève une HTTPException explicite à chaque étape qui peut échouer.
    """
    upload_response = await client.post(
        "https://api.assemblyai.com/v2/upload",
        headers={"authorization": ASSEMBLYAI_API_KEY},
        content=video_bytes,
    )
    if upload_response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Échec de l'envoi du fichier au service de transcription.",
        )
    upload_url = upload_response.json()["upload_url"]

    transcript_response = await client.post(
        "https://api.assemblyai.com/v2/transcript",
        headers={"authorization": ASSEMBLYAI_API_KEY},
        json={"audio_url": upload_url, "language_detection": True},
    )
    if transcript_response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail="Échec de la demande de transcription.",
        )
    transcript_id = transcript_response.json()["id"]

    # Vidéos TikTok courtes (quelques dizaines de secondes à ~3 min) :
    # on attend jusqu'à 2 minutes, avec un poll toutes les 2 secondes.
    for _ in range(60):
        poll_response = await client.get(
            f"https://api.assemblyai.com/v2/transcript/{transcript_id}",
            headers={"authorization": ASSEMBLYAI_API_KEY},
        )
        poll_data = poll_response.json()
        status = poll_data.get("status")
        if status == "completed":
            return poll_data.get("text") or ""
        if status == "error":
            raise HTTPException(
                status_code=502,
                detail=f"Erreur de transcription : {poll_data.get('error')}",
            )
        await asyncio.sleep(2)

    raise HTTPException(
        status_code=504,
        detail="La transcription prend trop de temps, réessaie plus tard.",
    )


@app.post("/api/analyze-video-upload", response_class=JSONResponse)
async def analyze_video_upload(
    file: UploadFile = File(...),
    account_avg_views: int = 0,
    niche_category: str = "",
):
    """
    Analyse approfondie d'UNE vidéo à partir d'un fichier importé
    directement par l'utilisateur (téléphone ou machine — jamais récupéré
    depuis TikTok, l'API ne fournit aucun fichier vidéo). Transcrit le
    contenu parlé réel via AssemblyAI, puis l'envoie à Claude pour une
    analyse du hook/de la structure basée sur ce qui est VRAIMENT dit,
    pas seulement le titre — contrairement à /api/analyze-video.

    Fonctionne aussi bien sur une vidéo déjà postée que sur une vidéo pas
    encore publiée (analyse "avant de poster").
    """
    if not ASSEMBLYAI_API_KEY:
        raise HTTPException(status_code=500, detail="ASSEMBLYAI_API_KEY manquant dans .env")
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY manquant dans .env")

    video_bytes = await file.read()
    # Garde-fou : 200 Mo max, largement suffisant pour une vidéo TikTok
    # (quelques minutes maximum), évite un upload abusif ou accidentel.
    if len(video_bytes) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (200 Mo max).")

    try:
        async with httpx.AsyncClient(timeout=150) as client:
            transcript_text = await _transcribe_video(client, video_bytes)
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Erreur réseau vers le service de transcription.")

    if not transcript_text.strip():
        raise HTTPException(
            status_code=502,
            detail="Transcription vide — vérifie que la vidéo contient bien de la voix.",
        )

    comparison_text = (
        f"Pour comparaison, la moyenne du compte est de {account_avg_views} vues par vidéo."
        if account_avg_views > 0
        else "Pas de moyenne de compte disponible pour comparaison — ne pas en inventer une."
    )

    prompt = f"""Tu es un coach de croissance TikTok senior, connu pour des
analyses extrêmement concrètes et jamais génériques.

{STYLE_GUIDE}

Voici la TRANSCRIPTION RÉELLE (le vrai contenu parlé) de cette vidéo,
obtenue par transcription audio — pas juste un titre :
\"\"\"{transcript_text}\"\"\"

Niche du compte : {niche_category or "non précisée"}
{comparison_text}

Analyse le HOOK réel (les toutes premières phrases prononcées, pas un
titre) en t'appuyant EN INTERNE sur les "TYPES D'ACCROCHES RÉELLES" du
guide de style ci-dessus pour comprendre ce qui se joue — mais dans ta
réponse, décris ce que fait ce hook en mots simples (ex : "le spectateur
se reconnaît tout de suite dans ce que tu dis"), JAMAIS avec un nom
technique de catégorie. Si aucun type ne correspond clairement, dis
simplement qu'il n'y a pas vraiment d'accroche identifiable.
Analyse aussi comment la vidéo est construite du début à la fin (est-ce
que le propos reste clair, y a-t-il un vrai fil, la fin donne-t-elle
envie d'agir) à partir du texte réel, pas d'une supposition.

RAPPEL LE PLUS IMPORTANT (règle hybride, RÈGLE D'OR N°2 du guide de
style) : "strengths" PEUT citer LE chiffre le plus marquant SI une vraie
donnée chiffrée est disponible ci-dessus (ex: comparaison à la moyenne
du compte) et qu'elle prouve une réussite — sinon reste en mots simples,
n'invente jamais un chiffre. "hook_type", "weaknesses" et "action_plan"
restent SANS AUCUN CHIFFRE. Écris comme pour un élève de CM2 : phrases
courtes, mots simples, une idée par phrase, aucun nom technique de
catégorie d'accroche. "weaknesses" et "action_plan" doivent être des
INSTRUCTIONS à l'impératif (RÈGLE D'OR N°3 du guide de style), pas des
observations : "weaknesses" = ce qu'il NE FAUT PAS faire ("Arrête
de..."), "action_plan" = ce qu'il FAUT faire à la place ("Fais...",
"Commence par...").

BRIÈVETÉ (important) : réponse courte et directe, lisible en 15 secondes.

Réponds avec un objet JSON (pas de markdown, pas de balises de code,
juste du JSON brut) contenant exactement ces champs, en FRANÇAIS TRÈS
SIMPLE (niveau CM2) :
{{
  "hook_excerpt": "les 1-2 premières phrases réellement prononcées, citées telles quelles",
  "hook_type": "1 phrase simple décrivant CE QUE FAIT ce hook (sans nom technique de catégorie), ou dis qu'il n'y a pas vraiment d'accroche",
  "strengths": ["1-2 points forts concrets MAXIMUM, en phrases simples, basés sur le texte réel — ce que le créateur fait déjà bien et doit continuer ; UN chiffre marquant autorisé si une vraie donnée le permet"],
  "weaknesses": ["1-2 instructions MAXIMUM à l'impératif commençant par 'Arrête de...' ou 'Évite de...', en phrases simples et sans chiffre, nommant une technique manquante"],
  "action_plan": ["1-2 instructions MAXIMUM à l'impératif commençant par 'Fais...' ou 'Commence par...', en phrases simples et sans chiffre, pour la prochaine vidéo"]
}}"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-5",
                    "max_tokens": 1200,
                    "output_config": {"effort": "low"},
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Erreur réseau vers l'API Anthropic.")

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur API Anthropic: {response.status_code} {response.text}",
        )

    raw_text = _extract_text_block(response.json())
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Réponse IA invalide.")

    return JSONResponse(content=result)


@app.get("/api/generate-script", response_class=JSONResponse)
async def generate_script(
    topic: str,
    tone: str = "",
    limits: str = "",
    niche: str = "",
    bio: str = "",
):
    """
    Génère un script de vidéo TikTok VRAIMENT personnalisé, en respectant
    strictement le ton et les limites définies par le créateur — pour
    éviter le principal défaut des générateurs concurrents (scripts
    génériques calqués sur des tendances, qui ne collent pas à la vraie
    personne).

    Paramètres :
    - topic  : le sujet/l'idée de la vidéo (obligatoire)
    - tone   : comment le créateur parle à son audience (ex: "humoristique et direct")
    - limits : ce que le créateur ne veut jamais dire/faire (ex: "pas de gros mots, jamais de politique")
    - niche  : niche de contenu détectée (optionnel, améliore la pertinence)
    - bio    : bio du compte (optionnel, contexte supplémentaire)
    """
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY manquant dans .env")

    prompt = f"""Tu es un scénariste spécialisé dans les vidéos courtes TikTok,
qui écrit des scripts qui sonnent VRAIMENT comme la personne qui va les
dire — jamais des scripts génériques copiés sur des tendances virales.

Contexte du créateur :
- Niche : {niche or "non précisée"}
- Bio : "{bio or "non précisée"}"
- Ton habituel du créateur : "{tone or "non précisé, reste neutre et naturel"}"
- Limites strictes à respecter (ne JAMAIS enfreindre) : "{limits or "aucune limite précisée"}"

Sujet de la vidéo à écrire : "{topic}"

TECHNIQUES D'ÉCRITURE (distillées d'un corpus de scripts créateurs réels
qui ont performé — à appliquer sans jamais trahir le ton/les limites
ci-dessus, qui restent prioritaires) :
- Hook (les 3 premières secondes) : répond à "de quoi ça parle" ET
  "pourquoi je devrais rester" en une phrase courte. Un mot-charnière
  (mais, en réalité, sauf que) aide à créer du contraste si le ton s'y
  prête — jamais un simple résumé du sujet.
- Adresse-toi à "tu"/"toi", pas "je"/"moi" — sauf si le sujet EST une
  anecdote personnelle du créateur, auquel cas "je" est légitime.
- Si le sujet est une histoire personnelle : structure conflit ->
  moment clé -> ce que ça change pour le spectateur (version courte
  d'une structure narrative, pas besoin des 7 actes complets sur un
  format aussi court).
- Le call_to_action doit découler du sujet précis, jamais un
  "like et abonne-toi" générique.

Écris un script structuré en 3 parties, RÉDIGÉ ENTIÈREMENT EN FRANÇAIS,
qui respecte STRICTEMENT le ton et les limites ci-dessus. N'invente pas
un ton différent de celui précisé. Si aucun ton n'est précisé, reste
simple et naturel plutôt que d'imposer un style "viral" générique.

Réponds avec un objet JSON (pas de markdown, pas de balises de code,
juste du JSON brut) avec exactement ces champs :
{{
  "hook": "l'accroche des 3 premières secondes, percutante mais fidèle au ton du créateur",
  "body": "le corps du script, 3-5 phrases maximum, adapté au format TikTok court",
  "call_to_action": "une phrase de fin naturelle (pas forcément 'like et abonne-toi', adapte au sujet)",
  "notes": "1-2 conseils courts de mise en scène/tournage propres à CE script précis"
}}"""

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-5",
                "max_tokens": 1200,
                "output_config": {"effort": "low"},
                "messages": [{"role": "user", "content": prompt}],
            },
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur API Anthropic: {response.status_code} {response.text}",
        )

    raw_text = _extract_text_block(response.json())
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        script = json.loads(cleaned)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Réponse IA invalide.")

    return JSONResponse(content=script)
