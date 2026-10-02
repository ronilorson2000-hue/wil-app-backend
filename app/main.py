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
import base64
import json
import math
import os
import re
import secrets
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from langdetect import LangDetectException, detect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.db import get_supabase
from app.style_guide import get_style_guide
from app.translations import DEFAULT_LANG, LANG_FLAGS, LANG_NAMES, SUPPORTED_LANGS, t

# Charge les variables du fichier .env (clés TikTok, redirect URI, etc.)
load_dotenv()

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

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

# Un emoji par catégorie, purement décoratif (choix visuel des boutons du
# mini-questionnaire sur /tools/analyze-video) — n'affecte jamais le
# contenu envoyé à l'IA, seulement l'affichage du bouton.
NICHE_EMOJIS = {
    "Beauté & Skincare": "💄",
    "Mode & Style": "👗",
    "Fitness & Sport": "🏋️",
    "Cuisine & Nutrition": "🍳",
    "Voyage": "✈️",
    "Humour & Divertissement": "😂",
    "Musique & Danse": "🎵",
    "Gaming & Tech": "🎮",
    "Business & Finance": "💼",
    "Développement personnel": "🌱",
    "Éducation & Culture générale": "📚",
    "Lifestyle & Vlog quotidien": "📱",
    "Parentalité & Famille": "👨‍👩‍👧",
    "Art & Créativité": "🎨",
    "Animaux": "🐾",
    "Santé & Bien-être": "🧘",
    "Autre": "✨",
}


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

# Sert les fichiers statiques (captures d'écran de témoignages, etc.)
# depuis app/static/ — ex. app/static/testimonials/1.png devient
# accessible sur /static/testimonials/1.png.
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/favicon.ico")
def favicon():
    """
    Sert le favicon (icône affichée dans l'onglet du navigateur).
    Le fichier favicon.ico doit se trouver dans le dossier app/,
    au même niveau que ce fichier main.py.
    """
    favicon_path = Path(__file__).parent / "favicon.ico"
    return FileResponse(favicon_path)


UI_LANG_COOKIE = "wil_lang"


def _detect_ui_lang(request: Request) -> str:
    """
    Détermine la langue d'interface à utiliser : priorité au choix
    explicite de l'utilisateur (cookie posé par /set-language), sinon
    déduite de l'en-tête Accept-Language envoyé par le navigateur/
    téléphone du visiteur, sinon repli sur le français.
    """
    cookie_lang = request.cookies.get(UI_LANG_COOKIE)
    if cookie_lang in SUPPORTED_LANGS:
        return cookie_lang

    accept_language = request.headers.get("accept-language", "")
    for part in accept_language.split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in SUPPORTED_LANGS:
            return code

    return DEFAULT_LANG


def _language_menu_html(current_lang: str, current_path: str) -> str:
    """
    Génère le menu déroulant "Langue" (accordéon natif <details>, sans
    JS) réutilisé sur toutes les pages publiques.
    """
    from urllib.parse import quote

    next_enc = quote(current_path, safe="")
    options = "".join(
        f'<a href="/set-language?lang={code}&to={next_enc}" '
        f'class="block px-4 py-2 text-sm hover:bg-slate-50 whitespace-nowrap '
        f'{"font-semibold text-blue-600" if code == current_lang else "text-slate-600"}">'
        f"{LANG_FLAGS[code]} {LANG_NAMES[code]}</a>"
        for code in SUPPORTED_LANGS
    )
    return f"""
          <details class="relative">
            <summary class="list-none cursor-pointer flex items-center gap-1 hover:text-slate-900">
              {LANG_FLAGS[current_lang]} {t(current_lang, "nav_language")}
            </summary>
            <div class="absolute right-0 mt-2 min-w-[9rem] bg-white border border-slate-200 rounded-xl shadow-lg py-2 z-20">
              {options}
            </div>
          </details>
    """


@app.get("/set-language")
def set_language(lang: str, to: str = "/"):
    """
    Enregistre le choix explicite de langue de l'utilisateur dans un
    cookie longue durée (1 an), puis le redirige vers la page d'où il
    vient. Cette langue devient ensuite la langue de l'interface ET
    celle utilisée par l'IA pour rédiger les rapports d'analyse.
    """
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    if not to.startswith("/"):
        to = "/"
    response = RedirectResponse(to)
    response.set_cookie(UI_LANG_COOKIE, lang, max_age=60 * 60 * 24 * 365, samesite="lax")
    return response


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
def home(request: Request):
    """
    Page d'accueil présentant le service en détail : fonctionnalités,
    tarifs, fonctionnement, et liens légaux visibles directement, sans
    menu ni connexion requise (exigence explicite de TikTok).

    Traduite en 6 langues (fr/en/de/es/pt/it) — voir app/translations.py.
    La langue est déterminée par _detect_ui_lang (cookie explicite, sinon
    Accept-Language du navigateur/téléphone, sinon français par défaut).
    """
    lang = _detect_ui_lang(request)
    tt = lambda key: t(lang, key)  # noqa: E731
    lang_menu = _language_menu_html(lang, "/")

    # Témoignages : faux avis pour le lancement (aucun vrai utilisateur
    # cité), à remplacer par de vrais témoignages dès qu'ils existent —
    # inspirés dans leur présentation (défilement horizontal en continu)
    # d'une page d'accueil concurrente vue par l'utilisateur, mais avec
    # un contenu qui reflète les vraies fonctionnalités de Wil App.
    #
    # Les témoignages 1 à 7 sont accompagnés d'une capture d'écran TikTok
    # Studio (vues, engagement, récompenses de créateurs) choisie par
    # l'utilisateur comme "preuve de résultat" — décision explicite de sa
    # part après qu'on l'ait prévenu que ces captures ne montrent pas
    # Wil App et ne prouvent pas de lien de cause à effet réel avec
    # l'app. Les témoignages suivants (8+) restent uniquement textuels.
    TESTIMONIAL_PROOF_IMAGE_COUNT = 7
    TESTIMONIAL_TOTAL_COUNT = 13
    _TESTIMONIAL_GRADIENTS = [
        "from-blue-600 to-sky-400",
        "from-purple-500 to-pink-400",
        "from-emerald-500 to-teal-400",
        "from-orange-500 to-amber-400",
        "from-rose-500 to-red-400",
        "from-indigo-500 to-blue-400",
    ]

    def testimonial_card(i: int) -> str:
        gradient = _TESTIMONIAL_GRADIENTS[(i - 1) % len(_TESTIMONIAL_GRADIENTS)]
        name = tt(f"testimonial_{i}_name")
        image_html = (
            f'<img src="/static/testimonials/{i}.png" alt="" class="w-full h-28 sm:h-40 object-cover object-top" loading="lazy" />'
            if i <= TESTIMONIAL_PROOF_IMAGE_COUNT
            else ""
        )
        return f'''<div class="testimonial-card bg-blue-50 border border-blue-100 rounded-2xl overflow-hidden">
              {image_html}
              <div class="p-4 sm:p-6">
                <p class="text-xs sm:text-sm text-slate-600 leading-relaxed mb-3 sm:mb-4">"{tt(f"testimonial_{i}_quote")}"</p>
                <div class="flex items-center gap-2 sm:gap-3">
                  <div class="w-8 h-8 sm:w-10 sm:h-10 rounded-full bg-gradient-to-br {gradient} flex items-center justify-center text-white font-bold text-xs sm:text-sm flex-shrink-0">{name[0]}</div>
                  <div>
                    <p class="font-semibold text-xs sm:text-sm text-slate-900">{name}</p>
                    <p class="text-[11px] sm:text-xs text-slate-500">{tt(f"testimonial_{i}_role")}</p>
                  </div>
                </div>
              </div>
            </div>'''

    testimonial_cards_html = "".join(testimonial_card(i) for i in list(range(1, TESTIMONIAL_TOTAL_COUNT + 1)) * 2)

    return f"""
    <html lang="{lang}">
      <head>
        <meta charset="utf-8">
        <title>Wil App</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
          tailwind.config = {{ theme: {{ extend: {{ fontFamily: {{ sans: ['Inter', 'system-ui', 'sans-serif'] }} }} }} }};
        </script>
        <style>
          html {{ overflow-x: hidden; }}
          body {{ font-family: 'Inter', system-ui, sans-serif; }}
          .reveal {{ opacity: 0; transform: translateY(28px); transition: opacity 0.7s ease, transform 0.7s ease; }}
          .reveal.is-visible {{ opacity: 1; transform: translateY(0); }}
          @media (prefers-reduced-motion: reduce) {{
            .reveal {{ opacity: 1; transform: none; transition: none; }}
          }}
          .testimonial-track {{ display: flex; gap: 1rem; overflow-x: auto; scroll-behavior: smooth; -webkit-overflow-scrolling: touch; scrollbar-width: none; padding: 0 0.25rem; }}
          .testimonial-track::-webkit-scrollbar {{ display: none; }}
          .testimonial-card {{ flex-shrink: 0; width: 200px; }}
          @media (min-width: 640px) {{
            .testimonial-card {{ width: 260px; }}
          }}
        </style>
      </head>
      <body class="bg-white text-slate-900 antialiased overflow-x-hidden">

        <nav class="flex items-center justify-between max-w-6xl mx-auto px-6 py-5 relative z-10">
          <div class="flex items-center gap-2">
            <div class="w-9 h-9 rounded-full bg-gradient-to-br from-blue-600 to-sky-400 flex items-center justify-center text-white font-bold text-sm">W</div>
            <span class="font-bold text-lg">Wil App</span>
          </div>
          <div class="hidden md:flex items-center gap-8 text-sm font-medium text-slate-600">
            <a href="/services" class="hover:text-slate-900">{tt("nav_services")}</a>
            <a href="#how-it-works" class="hover:text-slate-900">{tt("nav_how_it_works")}</a>
            <a href="/pricing" class="hover:text-slate-900">{tt("nav_pricing")}</a>
            {lang_menu}
          </div>
          <div class="flex items-center gap-2">
            <details class="md:hidden relative">
              <summary class="list-none cursor-pointer p-2 -mr-1 text-slate-700">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="w-6 h-6">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5" />
                </svg>
              </summary>
              <div class="fixed right-4 top-20 w-56 bg-white border border-slate-200 rounded-xl shadow-lg py-2 z-30 text-sm font-medium text-slate-600">
                <a href="/services" class="block px-4 py-2 hover:bg-slate-50 hover:text-slate-900">{tt("nav_services")}</a>
                <a href="#how-it-works" class="block px-4 py-2 hover:bg-slate-50 hover:text-slate-900">{tt("nav_how_it_works")}</a>
                <a href="/pricing" class="block px-4 py-2 hover:bg-slate-50 hover:text-slate-900">{tt("nav_pricing")}</a>
                <div class="border-t border-slate-100 mt-2 pt-2">
                  {lang_menu}
                </div>
              </div>
            </details>
            <a href="/app" class="px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold hover:bg-blue-700 transition">{tt("nav_login")}</a>
          </div>
        </nav>

        <div class="relative overflow-hidden">
          <div class="pointer-events-none absolute inset-0 -z-0">
            <div class="absolute -top-24 left-1/4 w-96 h-96 bg-blue-100 rounded-full blur-3xl opacity-40"></div>
            <div class="absolute top-10 right-1/4 w-96 h-96 bg-sky-100 rounded-full blur-3xl opacity-40"></div>
            <div class="absolute top-40 left-1/3 w-72 h-72 bg-blue-50 rounded-full blur-3xl opacity-60"></div>
          </div>
          <header class="relative max-w-3xl mx-auto text-center px-6 pt-20 pb-10 sm:pb-24">
            <div class="inline-block px-4 py-1.5 rounded-full bg-blue-50 border border-blue-100 text-blue-700 text-xs font-semibold mb-6">
              {tt("hero_badge")}
            </div>
            <h1 class="text-3xl sm:text-5xl font-extrabold tracking-tight leading-tight mb-5">
              {tt("hero_title_1")}<span class="italic bg-gradient-to-r from-blue-600 to-sky-400 bg-clip-text text-transparent">{tt("hero_title_2")}</span>
            </h1>
            <p class="text-sm sm:text-lg text-slate-500 mb-10 leading-relaxed">
              {tt("hero_subtitle")}
            </p>
            <div class="flex flex-col items-center gap-4">
              <a href="/app?open=account"
                 class="w-full max-w-sm sm:max-w-[19.2rem] mx-auto flex items-center justify-center gap-2 px-[1.875rem] sm:px-[1.2rem] py-[1.243125rem] sm:py-[1.5912rem] rounded-[0.690625rem] sm:rounded-[0.7956rem] text-white font-bold text-[1.0359375rem] sm:text-[1.1934rem] shadow-lg shadow-blue-600/25 bg-gradient-to-br from-blue-600 to-sky-400 hover:opacity-90 transition">
                {tt("hero_cta")}
              </a>
              <p class="text-xs text-slate-400 -mt-1">{tt("trust_line")}</p>
              <a href="/app?open=video"
                 class="w-full max-w-sm sm:max-w-[19.2rem] mx-auto flex items-center justify-center gap-2 px-[1.875rem] sm:px-[1.2rem] py-[1.243125rem] sm:py-[1.5912rem] rounded-[0.690625rem] sm:rounded-[0.7956rem] text-white font-bold text-[1.0359375rem] sm:text-[1.1934rem] shadow-lg shadow-blue-600/25 bg-gradient-to-br from-blue-600 to-sky-400 hover:opacity-90 transition">
                🎬 {tt("hero_cta_video")}
              </a>
              <a href="/app?open=script"
                 class="w-full max-w-sm sm:max-w-[19.2rem] mx-auto flex items-center justify-center gap-2 px-[1.875rem] sm:px-[1.2rem] py-[1.243125rem] sm:py-[1.5912rem] rounded-[0.690625rem] sm:rounded-[0.7956rem] text-white font-bold text-[1.0359375rem] sm:text-[1.1934rem] shadow-lg shadow-blue-600/25 bg-gradient-to-br from-blue-600 to-sky-400 hover:opacity-90 transition">
                📝 {tt("hero_cta_script")}
              </a>
            </div>
          </header>
        </div>

        <div class="max-w-5xl mx-auto px-6">

          <section id="how-it-works" class="py-10 sm:py-20">
            <h2 class="text-2xl sm:text-3xl font-bold text-center mb-14">{tt("hiw_title")}</h2>
            <div class="grid sm:grid-cols-3 gap-3 sm:gap-6">
              <div class="reveal bg-blue-50 border border-blue-100 rounded-2xl p-4 sm:p-7" style="transition-delay:0s">
                <div class="w-11 h-11 sm:w-16 sm:h-16 rounded-full bg-blue-700 text-white flex items-center justify-center mb-3 sm:mb-4">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="w-5 h-5 sm:w-8 sm:h-8">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l3 3m0 0l-3 3m3-3H3" />
                  </svg>
                </div>
                <h3 class="font-bold text-base mb-2">{tt("hiw_1_title")}</h3>
                <p class="text-slate-500 text-sm leading-relaxed">{tt("hiw_1_desc")}</p>
              </div>
              <div class="reveal bg-blue-50 border border-blue-100 rounded-2xl p-4 sm:p-7" style="transition-delay:0.12s">
                <div class="w-11 h-11 sm:w-16 sm:h-16 rounded-full bg-blue-700 text-white flex items-center justify-center mb-3 sm:mb-4">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="w-5 h-5 sm:w-8 sm:h-8">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z" />
                  </svg>
                </div>
                <h3 class="font-bold text-base mb-2">{tt("hiw_2_title")}</h3>
                <p class="text-slate-500 text-sm leading-relaxed">{tt("hiw_2_desc")}</p>
              </div>
              <div class="reveal bg-blue-50 border border-blue-100 rounded-2xl p-4 sm:p-7" style="transition-delay:0.24s">
                <div class="w-11 h-11 sm:w-16 sm:h-16 rounded-full bg-blue-700 text-white flex items-center justify-center mb-3 sm:mb-4">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="w-5 h-5 sm:w-8 sm:h-8">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                  </svg>
                </div>
                <h3 class="font-bold text-base mb-2">{tt("hiw_3_title")}</h3>
                <p class="text-slate-500 text-sm leading-relaxed">{tt("hiw_3_desc")}</p>
              </div>
            </div>
          </section>

          <section id="results" class="py-10 sm:py-20 border-t border-slate-100">
            <h2 class="text-2xl sm:text-3xl font-bold text-center mb-2">{tt("results_title")}</h2>
            <p class="text-sm sm:text-base text-slate-500 text-center mb-10 sm:mb-14">{tt("results_subtitle")}</p>
          </section>
          <div class="relative w-screen left-1/2 -translate-x-1/2 py-2 -mt-10 sm:-mt-14 mb-10 sm:mb-20">
            <button onclick="scrollTestimonials(-1)" aria-label="{tt("results_prev")}" type="button"
                    class="absolute left-2 sm:left-6 top-1/2 -translate-y-1/2 z-10 w-8 h-8 sm:w-9 sm:h-9 rounded-full bg-white shadow-md border border-slate-200 flex items-center justify-center text-slate-600 hover:text-blue-600 active:scale-90 transition">‹</button>
            <div id="testimonial-track" class="testimonial-track">
              {testimonial_cards_html}
            </div>
            <button onclick="scrollTestimonials(1)" aria-label="{tt("results_next")}" type="button"
                    class="absolute right-2 sm:right-6 top-1/2 -translate-y-1/2 z-10 w-8 h-8 sm:w-9 sm:h-9 rounded-full bg-white shadow-md border border-slate-200 flex items-center justify-center text-slate-600 hover:text-blue-600 active:scale-90 transition">›</button>
          </div>

          <section id="faq" class="py-20 border-t border-slate-100">
            <h2 class="text-2xl sm:text-3xl font-bold text-center mb-14">{tt("faq_title")}</h2>
            <div class="max-w-2xl mx-auto space-y-3">
              <details class="reveal group bg-blue-50 border border-blue-100 rounded-2xl p-6" style="transition-delay:0s">
                <summary class="font-semibold cursor-pointer list-none flex items-center justify-between gap-4">
                  {tt("faq_q1")}
                  <span class="flex-shrink-0 text-blue-600 text-xl leading-none group-open:rotate-45 transition-transform">+</span>
                </summary>
                <p class="text-slate-500 text-sm leading-relaxed mt-3">{tt("faq_a1")}</p>
              </details>
              <details class="reveal group bg-blue-50 border border-blue-100 rounded-2xl p-6" style="transition-delay:0.08s">
                <summary class="font-semibold cursor-pointer list-none flex items-center justify-between gap-4">
                  {tt("faq_q2")}
                  <span class="flex-shrink-0 text-blue-600 text-xl leading-none group-open:rotate-45 transition-transform">+</span>
                </summary>
                <p class="text-slate-500 text-sm leading-relaxed mt-3">{tt("faq_a2")}</p>
              </details>
              <details class="reveal group bg-blue-50 border border-blue-100 rounded-2xl p-6" style="transition-delay:0.16s">
                <summary class="font-semibold cursor-pointer list-none flex items-center justify-between gap-4">
                  {tt("faq_q3")}
                  <span class="flex-shrink-0 text-blue-600 text-xl leading-none group-open:rotate-45 transition-transform">+</span>
                </summary>
                <p class="text-slate-500 text-sm leading-relaxed mt-3">{tt("faq_a3")}</p>
              </details>
              <details class="reveal group bg-blue-50 border border-blue-100 rounded-2xl p-6" style="transition-delay:0.24s">
                <summary class="font-semibold cursor-pointer list-none flex items-center justify-between gap-4">
                  {tt("faq_q4")}
                  <span class="flex-shrink-0 text-blue-600 text-xl leading-none group-open:rotate-45 transition-transform">+</span>
                </summary>
                <p class="text-slate-500 text-sm leading-relaxed mt-3">{tt("faq_a4")}</p>
              </details>
              <details class="reveal group bg-blue-50 border border-blue-100 rounded-2xl p-6" style="transition-delay:0.32s">
                <summary class="font-semibold cursor-pointer list-none flex items-center justify-between gap-4">
                  {tt("faq_q5")}
                  <span class="flex-shrink-0 text-blue-600 text-xl leading-none group-open:rotate-45 transition-transform">+</span>
                </summary>
                <p class="text-slate-500 text-sm leading-relaxed mt-3">{tt("faq_a5")} <a href="mailto:contact.wilapp@proton.me" class="text-blue-600 font-medium hover:text-blue-700">contact.wilapp@proton.me</a>.</p>
              </details>
            </div>
          </section>
        </div>

        <footer class="bg-blue-900 text-blue-100 mt-10">
          <div class="max-w-6xl mx-auto px-6 py-8 sm:py-14 grid grid-cols-2 sm:grid-cols-3 gap-6 sm:gap-10">
            <div class="col-span-2 sm:col-span-1">
              <div class="flex items-center gap-2 mb-3">
                <div class="w-9 h-9 rounded-full bg-gradient-to-br from-blue-400 to-sky-300 flex items-center justify-center text-blue-900 font-bold text-sm">W</div>
                <span class="font-bold text-lg text-white">Wil App</span>
              </div>
              <p class="text-sm text-blue-200 leading-relaxed mb-4">{tt("hero_subtitle")}</p>
              <a href="https://wa.me/447446953451" target="_blank" rel="noopener"
                 class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-800 hover:bg-blue-700 transition text-sm font-medium text-white">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" class="w-4 h-4">
                  <path d="M12.04 2c-5.52 0-10 4.48-10 10 0 1.77.46 3.44 1.26 4.89L2 22l5.25-1.28A9.96 9.96 0 0012.04 22c5.52 0 10-4.48 10-10s-4.48-10-10-10zm0 18.2c-1.6 0-3.14-.43-4.47-1.24l-.32-.19-3.12.76.79-3.04-.2-.31A8.18 8.18 0 013.84 12c0-4.53 3.68-8.2 8.2-8.2s8.2 3.68 8.2 8.2-3.67 8.2-8.2 8.2zm4.5-6.13c-.25-.12-1.45-.72-1.68-.8-.23-.08-.39-.12-.56.12-.16.25-.64.8-.78.96-.14.16-.29.18-.53.06-.25-.12-1.05-.39-1.99-1.23-.74-.66-1.23-1.47-1.38-1.72-.14-.25-.02-.38.11-.51.11-.11.25-.29.37-.43.12-.14.16-.25.25-.41.08-.16.04-.31-.02-.43-.06-.12-.56-1.35-.77-1.85-.2-.48-.41-.42-.56-.43h-.48c-.16 0-.43.06-.65.31-.23.25-.86.84-.86 2.05s.88 2.38 1 2.55c.12.16 1.73 2.64 4.19 3.7.59.25 1.05.4 1.41.52.59.19 1.13.16 1.55.1.47-.07 1.45-.59 1.66-1.16.2-.57.2-1.06.14-1.16-.06-.1-.22-.16-.47-.28z"/>
                </svg>
                {tt("footer_whatsapp")}
              </a>
            </div>
            <div>
              <h4 class="font-semibold text-white mb-3 text-sm">{tt("footer_col_product")}</h4>
              <ul class="space-y-2 text-sm text-blue-200">
                <li><a href="/services" class="hover:text-white transition">{tt("nav_services")}</a></li>
                <li><a href="/pricing" class="hover:text-white transition">{tt("nav_pricing")}</a></li>
                <li><a href="#faq" class="hover:text-white transition">{tt("nav_faq")}</a></li>
              </ul>
            </div>
            <div>
              <h4 class="font-semibold text-white mb-3 text-sm">{tt("footer_col_info")}</h4>
              <ul class="space-y-2 text-sm text-blue-200">
                <li><a href="/about" class="hover:text-white transition">{tt("nav_about")}</a></li>
                <li><a href="/contact" class="hover:text-white transition">{tt("nav_contact")}</a></li>
                <li><a href="/terms" class="hover:text-white transition">{tt("footer_terms")}</a></li>
                <li><a href="/privacy" class="hover:text-white transition">{tt("footer_privacy")}</a></li>
              </ul>
            </div>
          </div>
          <div class="border-t border-blue-800 text-center py-4 sm:py-6 px-6 text-xs text-blue-300">
            © 2026 Wil App. {tt("footer_rights")}
          </div>
        </footer>

        <script>
          // Anime les cartes (How it works, Pricing, FAQ) en fondu + léger
          // déplacement vers le haut au moment où elles entrent dans l'écran
          // en scrollant, plutôt que de tout afficher d'un coup au chargement.
          (function () {{
            var revealEls = document.querySelectorAll('.reveal');
            if (!('IntersectionObserver' in window) || revealEls.length === 0) {{
              revealEls.forEach(function (el) {{ el.classList.add('is-visible'); }});
              return;
            }}
            var observer = new IntersectionObserver(function (entries) {{
              entries.forEach(function (entry) {{
                if (entry.isIntersecting) {{
                  entry.target.classList.add('is-visible');
                  observer.unobserve(entry.target);
                }}
              }});
            }}, {{ threshold: 0.15, rootMargin: '0px 0px -40px 0px' }});
            revealEls.forEach(function (el) {{ observer.observe(el); }});
          }})();

          // Témoignages : défilement horizontal automatique et continu
          // (repositionnement invisible à mi-parcours, la liste étant
          // dupliquée une fois côté serveur), avec deux boutons pour
          // avancer/reculer manuellement sans attendre — le défilement
          // auto reprend après une pause si l'utilisateur n'interagit
          // plus.
          (function () {{
            var track = document.getElementById('testimonial-track');
            if (!track) return;
            var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
            var autoScrollTimer = null;
            var resumeTimer = null;

            function tick() {{
              track.scrollLeft += 1;
              var half = track.scrollWidth / 2;
              if (track.scrollLeft >= half) {{
                track.scrollLeft -= half;
              }}
            }}

            function startAuto() {{
              if (reduceMotion || autoScrollTimer) return;
              autoScrollTimer = setInterval(tick, 30);
            }}

            function stopAuto() {{
              clearInterval(autoScrollTimer);
              autoScrollTimer = null;
            }}

            function pauseThenResume() {{
              stopAuto();
              clearTimeout(resumeTimer);
              resumeTimer = setTimeout(startAuto, 4000);
            }}

            window.scrollTestimonials = function (direction) {{
              pauseThenResume();
              var firstCard = track.querySelector('.testimonial-card');
              var cardWidth = firstCard ? firstCard.offsetWidth + 16 : 260;
              track.scrollBy({{ left: direction * cardWidth * 2, behavior: 'smooth' }});
            }};

            track.addEventListener('pointerdown', pauseThenResume);
            track.addEventListener('touchstart', pauseThenResume, {{ passive: true }});
            track.addEventListener('mouseenter', stopAuto);
            track.addEventListener('mouseleave', startAuto);

            startAuto();
          }})();
        </script>
      </body>
    </html>
    """


# En-tête partagé par les pages secondaires (Services/About/Contact) : accessibles
# uniquement via un clic depuis le menu de la page d'accueil, plus dans le flux de
# scroll de la landing page elle-même (contenu identique à l'ancien affichage inline).
_SECONDARY_PAGE_HEAD = """
  <link rel="icon" type="image/x-icon" href="/favicon.ico">
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = { theme: { extend: { fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] } } } };
  </script>
  <style>body { font-family: 'Inter', system-ui, sans-serif; }</style>
"""

def _secondary_page_nav_html(lang: str, current_path: str) -> str:
    """Nav partagée par Services/About/Contact : logo, retour, langue."""
    return f"""
  <nav class="flex items-center justify-between max-w-6xl mx-auto px-6 py-5">
    <a href="/" class="flex items-center gap-2">
      <div class="w-9 h-9 rounded-full bg-gradient-to-br from-blue-600 to-sky-400 flex items-center justify-center text-white font-bold text-sm">W</div>
      <span class="font-bold text-lg text-slate-900">Wil App</span>
    </a>
    <div class="flex items-center gap-6 text-sm font-medium text-slate-600">
      <a href="/" class="hover:text-slate-900">{t(lang, "back_home")}</a>
      {_language_menu_html(lang, current_path)}
    </div>
  </nav>
"""


@app.get("/services", response_class=HTMLResponse)
def services_page(request: Request):
    """
    Page "Our Services" — accessible uniquement via le lien du menu de la
    page d'accueil (plus affichée en ligne dans le scroll de la landing
    page elle-même, à la demande explicite de l'utilisateur).
    """
    lang = _detect_ui_lang(request)
    tt = lambda key: t(lang, key)  # noqa: E731
    return f"""
    <html lang="{lang}">
      <head><title>{tt("services_title")} — Wil App</title>{_SECONDARY_PAGE_HEAD}</head>
      <body class="bg-white text-slate-900 antialiased">
        {_secondary_page_nav_html(lang, "/services")}
        <div class="max-w-5xl mx-auto px-6 py-16">
          <h1 class="text-3xl font-bold text-center mb-14">{tt("services_title")}</h1>
          <div class="grid sm:grid-cols-3 gap-6">
            <div class="bg-slate-50 border border-slate-100 rounded-2xl p-7">
              <div class="text-2xl mb-3">📊</div>
              <h3 class="font-bold text-base mb-2">{tt("services_1_title")}</h3>
              <p class="text-slate-500 text-sm leading-relaxed">{tt("services_1_desc")}</p>
            </div>
            <div class="bg-slate-50 border border-slate-100 rounded-2xl p-7">
              <div class="text-2xl mb-3">🎬</div>
              <h3 class="font-bold text-base mb-2">{tt("services_2_title")}</h3>
              <p class="text-slate-500 text-sm leading-relaxed">{tt("services_2_desc")}</p>
            </div>
            <div class="bg-slate-50 border border-slate-100 rounded-2xl p-7">
              <div class="text-2xl mb-3">📝</div>
              <h3 class="font-bold text-base mb-2">{tt("services_3_title")}</h3>
              <p class="text-slate-500 text-sm leading-relaxed">{tt("services_3_desc")}</p>
            </div>
          </div>
        </div>
      </body>
    </html>
    """


@app.get("/pricing", response_class=HTMLResponse)
def pricing_page(request: Request):
    """
    Page "Pricing" — accessible uniquement via le lien du menu de la page
    d'accueil (plus affichée en ligne dans le scroll de la landing page
    elle-même, remplacée par la section "Résultats & Témoignages" à la
    demande explicite de l'utilisateur, même logique déjà appliquée à
    "Our Services").
    """
    lang = _detect_ui_lang(request)
    tt = lambda key: t(lang, key)  # noqa: E731
    return f"""
    <html lang="{lang}">
      <head><title>{tt("pricing_title")} — Wil App</title>{_SECONDARY_PAGE_HEAD}</head>
      <body class="bg-white text-slate-900 antialiased">
        {_secondary_page_nav_html(lang, "/pricing")}
        <div class="max-w-5xl mx-auto px-6 py-16">
          <h1 class="text-3xl font-bold text-center mb-14">{tt("pricing_title")}</h1>
          <div class="grid sm:grid-cols-2 gap-6 max-w-xl mx-auto">
            <div class="border border-slate-200 rounded-2xl p-8 text-center flex flex-col">
              <h3 class="font-bold text-lg mb-2">{tt("pricing_free_name")}</h3>
              <div class="text-3xl font-extrabold mb-5">$0<span class="text-sm font-normal text-slate-400">{tt("pricing_free_period")}</span></div>
              <ul class="text-sm text-slate-600 space-y-2 text-left mb-6">
                <li>✔ {tt("pricing_free_feature1")}</li>
                <li>✔ {tt("pricing_free_feature2")}</li>
              </ul>
              <a href="/app" class="mt-auto inline-block px-6 py-3 rounded-xl bg-blue-600 text-white font-semibold text-sm hover:bg-blue-700 transition">{tt("pricing_free_cta")}</a>
              <p class="text-xs text-slate-400 mt-3">{tt("trust_line")}</p>
            </div>
            <div class="border-2 border-blue-600 rounded-2xl p-8 text-center relative flex flex-col">
              <h3 class="font-bold text-lg mb-2">{tt("pricing_pro_name")}</h3>
              <div class="text-2xl font-extrabold mb-5 text-blue-600">{tt("pricing_pro_price")}</div>
              <ul class="text-sm text-slate-600 space-y-2 text-left mb-6">
                <li>✔ {tt("pricing_pro_feature1")}</li>
                <li>✔ {tt("pricing_pro_feature2")}</li>
                <li>✔ {tt("pricing_pro_feature3")}</li>
              </ul>
              <button disabled class="mt-auto px-6 py-3 rounded-xl bg-blue-300 text-white font-semibold text-sm cursor-not-allowed">{tt("pricing_pro_cta")}</button>
            </div>
          </div>
        </div>
      </body>
    </html>
    """


@app.get("/about", response_class=HTMLResponse)
def about_page(request: Request):
    """
    Page "About Wil App" — accessible uniquement via le lien du menu de
    la page d'accueil (plus affichée en ligne dans le scroll de la
    landing page elle-même, à la demande explicite de l'utilisateur).
    """
    lang = _detect_ui_lang(request)
    tt = lambda key: t(lang, key)  # noqa: E731
    return f"""
    <html lang="{lang}">
      <head><title>{tt("about_title")} — Wil App</title>{_SECONDARY_PAGE_HEAD}</head>
      <body class="bg-white text-slate-900 antialiased">
        {_secondary_page_nav_html(lang, "/about")}
        <div class="max-w-2xl mx-auto px-6 py-16 text-center">
          <h1 class="text-3xl font-bold mb-6">{tt("about_title")}</h1>
          <p class="text-slate-500 leading-relaxed">{tt("about_body")}</p>
        </div>
      </body>
    </html>
    """


@app.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request):
    """
    Page "Contact" — accessible uniquement via le lien du menu de la
    page d'accueil (plus affichée en ligne dans le scroll de la landing
    page elle-même, à la demande explicite de l'utilisateur).
    """
    lang = _detect_ui_lang(request)
    tt = lambda key: t(lang, key)  # noqa: E731
    return f"""
    <html lang="{lang}">
      <head><title>{tt("contact_title")} — Wil App</title>{_SECONDARY_PAGE_HEAD}</head>
      <body class="bg-white text-slate-900 antialiased">
        {_secondary_page_nav_html(lang, "/contact")}
        <div class="max-w-2xl mx-auto px-6 py-16 text-center">
          <h1 class="text-3xl font-bold mb-6">{tt("contact_title")}</h1>
          <p class="text-slate-500">{tt("contact_body")}
             <a href="mailto:contact.wilapp@proton.me" class="text-blue-600 font-medium hover:text-blue-700">contact.wilapp@proton.me</a></p>
        </div>
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


CHALLENGE_STATE_CODES = {"followers": "fo", "engagement": "en", "reach": "re"}
CHALLENGE_STATE_CODES_REVERSE = {v: k for k, v in CHALLENGE_STATE_CODES.items()}


@app.get("/auth/tiktok/login")
def tiktok_login(source: str = "web", main_challenge: str = ""):
    """
    Étape 1 du flow OAuth : on redirige l'utilisateur vers la page
    d'autorisation de TikTok.

    Le paramètre "source" indique d'où vient la demande :
    - "web"  (par défaut) : affichera la page HTML classique à la fin
    - "app"  : redirigera vers l'app mobile (wilapp://callback) à la fin
    L'app Flutter appelle cette route avec ?source=app.

    `main_challenge` vient du mini-questionnaire d'onboarding de
    /tools/analyze-account (même structure que vidéo/script) : encodé
    dans le "state" lui-même (2 caractères fixes juste après le préfixe
    source) plutôt que stocké à part, pour ne pas avoir à faire évoluer
    le schéma pending_states — récupéré tel quel par tiktok_callback et
    transmis à /api/analyze-account pour orienter l'angle des conseils.
    """
    if not TIKTOK_CLIENT_KEY or not TIKTOK_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="TIKTOK_CLIENT_KEY ou TIKTOK_REDIRECT_URI manquant dans .env",
        )

    # Le "state" sert à la fois de protection anti-CSRF ET à retenir la
    # source de la demande (web ou app) ainsi que le défi choisi, en
    # préfixant la valeur aléatoire. Code à largeur fixe (2 caractères)
    # pour pouvoir le relire sans ambiguïté même si le token aléatoire
    # lui-même contient un "_" (alphabet de token_urlsafe).
    prefix = "app_" if source == "app" else "web_"
    challenge_code = CHALLENGE_STATE_CODES.get(main_challenge, "no")
    state = prefix + challenge_code + secrets.token_urlsafe(24)
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

    # Défi choisi dans l'onboarding de /tools/analyze-account, relu
    # depuis le "state" (voir tiktok_login) — chaîne vide si non fourni
    # (connexion directe sans passer par l'onboarding, ex. lien existant).
    main_challenge = CHALLENGE_STATE_CODES_REVERSE.get(state[4:6], "")

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
            "main_challenge": main_challenge,
        })
        return RedirectResponse(f"wilapp://callback?{app_params}")

    # Langue d'interface ET langue de rédaction des rapports IA (voir
    # analyze_account/analyze_video/analyze_video_upload/analyze_transcript
    # : chacune reçoit ce même code de langue en paramètre `ui_lang`).
    lang = _detect_ui_lang(request)
    tt = lambda key: t(lang, key)  # noqa: E731

    verified_badge = (
        f'<span style="color:#0EA5E9; font-weight:bold;">✔ {tt("dash_verified")}</span>'
        if is_verified else ""
    )
    bio_html = f'<p style="color:#475569; max-width:400px; margin:12px auto; font-size:14px;">{bio}</p>' if bio else ""
    link_html = (
        f'<p><a href="{profile_link}" target="_blank">{tt("dash_view_profile")}</a></p>'
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
    main_challenge_enc = quote(main_challenge)
    tiktok_profile_js = _js_json(
        {
            "display_name": display_name,
            "username": username,
            "avatar_url": avatar_url,
            "is_verified": bool(is_verified),
        }
    )
    # Pas de sélecteur de langue interactif ici : cette page n'est
    # accessible que via le retour OAuth de TikTok (code/state à usage
    # unique) — un rechargement casserait la page ("state déjà utilisé").
    # La langue est déjà correcte via le cookie posé sur une autre page
    # (accueil, Services/About/Contact) ou l'Accept-Language du visiteur.

    return f"""
    <html>
      <head>
        <meta charset="utf-8">
        <title>Wil App — Dashboard</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
        <script src="https://cdn.tailwindcss.com"></script>
        <script>
          tailwind.config = {{ theme: {{ extend: {{ fontFamily: {{ sans: ['Inter', 'system-ui', 'sans-serif'] }} }} }} }};
        </script>
        <style>
          body {{ font-family: 'Inter', system-ui, sans-serif; text-align: center;
                  margin: 0; padding: 56px 20px; color: #0F172A; background: #EFF6FF; }}
          .card {{ max-width: 480px; margin: 0 auto 16px; background: #FFFFFF; border: 1px solid #E2E8F0;
                   border-radius: 16px; padding: 28px; box-shadow: 0 1px 3px rgba(15,23,42,0.05);
                   text-align: left; }}
          .card.profile {{ text-align: center; }}
          img.avatar {{ width: 96px; height: 96px; border-radius: 9999px; object-fit: cover; }}
          h2 {{ margin: 16px 0 4px; font-size: 20px; font-weight: 700; }}
          .username {{ color: #64748B; margin: 0 0 8px; font-size: 14px; }}
          .stats {{ display: flex; justify-content: center; gap: 24px; margin-top: 20px;
                    padding-top: 20px; border-top: 1px solid #E2E8F0; font-size: 13px; color: #64748B; }}
          a.home {{ display: block; margin-top: 24px; color: #2563EB; text-decoration: none;
                    font-size: 14px; font-weight: 500; }}
          a.home:hover {{ color: #1D4ED8; }}
          .loading {{ color: #64748B; font-size: 14px; }}
          .bar-bg {{ background: #E2E8F0; border-radius: 999px; height: 10px; overflow: hidden; }}
          .bar-fill {{ background: #2563EB; height: 100%; border-radius: 999px; }}
          .chip {{ display: inline-block; background: #2563EB; color: white; padding: 6px 14px;
                   border-radius: 999px; font-size: 13px; font-weight: 600; }}
          .tag {{ display: inline-block; background: #EFF6FF; color: #1D4ED8; padding: 4px 12px;
                  border-radius: 999px; font-size: 12px; margin: 3px; font-weight: 500; }}
          ul.bullets {{ padding-left: 20px; margin: 8px 0; }}
          ul.bullets li {{ margin-bottom: 6px; line-height: 1.5; font-size: 14px; }}
          .btn-pill {{ padding: 7px 9px; border-radius: 999px; border: 1px solid #2563EB;
                       background: #2563EB; color: #FFFFFF; font-weight: 600; font-size: 11px;
                       cursor: pointer; transition: background 0.15s ease; white-space: nowrap;
                       flex-shrink: 0; }}
          .btn-pill:hover {{ background: #1D4ED8; }}
        </style>
      </head>
      <body>
        <div style="max-width:480px; margin:0 auto 20px; display:flex; gap:5px; justify-content:center; flex-wrap:nowrap; overflow-x:auto;">
          <button onclick="location.href='/tools/analyze-video?niche_category='+encodeURIComponent(window.__wilNicheCategory||'')+'&account_avg_views='+encodeURIComponent(window.__wilAvgViews||'')"
                  class="btn-pill">
            🎬 {tt("dash_btn_analyze_video")}
          </button>
          <button onclick="location.href='/tools/analyze-script'"
                  class="btn-pill">
            📝 {tt("dash_btn_analyze_script")}
          </button>
        </div>

        <p style="color:#16A34A; font-weight:600; font-size:14px;">✅ {tt("dash_connected")}</p>
        <div class="card profile">
          <img class="avatar" src="{avatar_url}" alt="Profile picture" />
          <h2>{display_name} {verified_badge}</h2>
          <p class="username">@{username}</p>
          {bio_html}
          {link_html}
          <div class="stats">
            <div>🔗 {tt("dash_account_linked")}</div>
            <div>🔒 {tt("dash_data_secured")}</div>
          </div>
        </div>

        <div id="analysis-loading" class="card">
          <p class="loading">⏳ {tt("dash_analyzing")}</p>
        </div>
        <div id="analysis-result"></div>

        <a href="/app" class="home">{tt("dash_back")}</a>

        <script>
          // Mémorise le profil (jamais le session_id) pour l'onglet Profil de /app.
          try {{
            localStorage.setItem('wilTikTok', JSON.stringify({tiktok_profile_js}));
          }} catch (e) {{}}
          const sessionId = "{session_id}";
          const uiLang = "{lang}";
          window.__wilUiLang = uiLang;
          // Petit helper i18n : remplace {{cle}} par sa valeur dans un
          // gabarit traduit côté serveur (ex: "{{count}} vidéos...").
          function fmt(template, vars) {{
            return template.replace(/\\{{(\\w+)\\}}/g, (_, k) => (k in vars) ? vars[k] : `{{${{k}}}}`);
          }}
          fetch(`/api/analyze-account?session=${{sessionId}}&display_name={display_name_enc}&username={username_enc}&bio={bio_enc}&main_challenge={main_challenge_enc}&ui_lang=${{uiLang}}`)
            .then(r => r.json().then(data => ({{ok: r.ok, status: r.status, data}})))
            .then(({{ok, status, data}}) => {{
              document.getElementById('analysis-loading').style.display = 'none';
              // Si le serveur a répondu avec une erreur (401 session expirée,
              // 502 API TikTok/Anthropic indisponible...), on affiche la
              // VRAIE raison (data.detail, fournie par FastAPI) au lieu d'un
              // message générique qui masque le problème.
              if (!ok) {{
                const reason = (data && data.detail) ? data.detail : `{tt("common_error_prefix")} ${{status}}`;
                document.getElementById('analysis-result').innerHTML =
                  `<div class="card"><p class="loading" style="color:#DC2626;">${{reason}}</p></div>`;
                return;
              }}
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
                  ? `<p style="font-size:12px;color:#94A3B8;margin:2px 0 0;">${{fmt("{tt('dash_likes_ratio')}", {{ratio: stats.likes_followers_ratio}})}}</p>`
                  : '';
                html += `
                  <div class="card">
                    <p style="font-size:30px;font-weight:800;margin:0;">${{scoreIcon(stats.account_virality_score)}} ${{stats.account_virality_score}}/100</p>
                    <p style="font-size:12px;color:#64748B;margin:2px 0 14px;">{tt('dash_virality_score_label')}</p>
                    <p style="font-size:13px;color:#475569;">${{fmt("{tt('dash_videos_analyzed')}", {{count: stats.total_videos_analyzed, threshold: stats.viral_threshold_views/1000}})}}</p>
                    <div class="bar-bg" style="margin-top:8px;"><div class="bar-fill" style="width:${{stats.viral_percentage}}%"></div></div>
                    <p style="margin-top:14px;font-size:14px;"><strong>🚀 ${{fmt("{tt('dash_viral_pct')}", {{pct: stats.viral_percentage}})}}</strong> &nbsp;|&nbsp; <strong>${{fmt("{tt('dash_non_viral_pct')}", {{pct: stats.non_viral_percentage}})}}</strong></p>
                    <p style="font-size:14px;">${{fmt("{tt('dash_avg_engagement')}", {{pct: stats.average_engagement_rate}})}}</p>
                    ${{ratioLine}}
                  </div>`;

                if (stats.videos && stats.videos.length > 0) {{
                  window.__wilVideos = stats.videos;
                  window.__wilAvgViews = stats.average_view_count || '';
                  const videoRows = stats.videos.map((v, idx) => `
                    <div style="display:flex; gap:12px; align-items:flex-start; padding:14px 0; border-bottom:1px solid #F1F5F9;">
                      <div style="width:60px;height:84px;flex-shrink:0;border-radius:10px;overflow:hidden;background:#F1F5F9;">
                        ${{v.cover_image_url ? `<img src="${{v.cover_image_url}}" style="width:100%;height:100%;object-fit:cover;" />` : ''}}
                      </div>
                      <div style="flex:1;min-width:0;">
                        <p style="font-size:13px;font-weight:700;margin:0;">${{scoreIcon(v.virality_score)}} ${{v.virality_score}}/100</p>
                        <p style="font-size:12px;color:#64748B;margin:2px 0 8px;">${{v.view_count}} {tt('dash_views_suffix')}</p>
                        <button onclick="analyzeVideo(${{idx}})" id="analyze-btn-${{idx}}"
                                style="font-size:12px;padding:7px 14px;border-radius:999px;border:1px solid #E2E8F0;
                                       background:#fff;color:#1D4ED8;font-weight:600;cursor:pointer;">
                          {tt('dash_btn_analyze_video')}
                        </button>
                        <div id="video-analysis-${{idx}}" style="margin-top:8px;font-size:13px;"></div>
                      </div>
                    </div>`).join('');
                  videoListHtml = `
                    <div class="card">
                      <p style="font-weight:700;margin-bottom:4px;">{tt('dash_video_detail_title')}</p>
                      <p style="font-size:12px;color:#64748B;margin:0 0 8px;">{tt('dash_video_detail_subtitle')}</p>
                      <div>${{videoRows}}</div>
                    </div>`;
                }}
              }}

              if (report) {{
                const strengths = (report.strengths || []).map(s => `<li>${{s}}</li>`).join('');
                const improvements = (report.improvements || []).map(s => `<li>${{s}}</li>`).join('');
                const hashtags = (report.suggested_hashtags || []).map(h => `<span class="tag">#${{h}}</span>`).join('');
                const hashtagDiag = report.hashtag_diagnosis
                  ? `<p style="margin-top:16px;"><strong>🏷 {tt('dash_hashtag_diagnosis')}</strong></p><p style="font-size:14px;">${{report.hashtag_diagnosis}}</p>`
                  : '';
                const nicheFocus = report.niche_focus_advice
                  ? `<div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:12px;padding:16px;margin:16px 0;">
                       <p style="font-weight:700;margin:0 0 8px;">🧭 {tt('dash_multi_niche_title')}</p>
                       <div>${{(report.niches_detected || []).map(n => `<span class="tag">${{n}}</span>`).join('')}}</div>
                       <p style="font-size:14px;margin:10px 0 0;">${{report.niche_focus_advice}}</p>
                     </div>`
                  : '';
                html += `
                  <div class="card">
                    <span class="chip">${{report.niche || ''}}</span>
                    <p style="margin-top:14px;font-size:15px;line-height:1.5;">${{report.summary || ''}}</p>
                    ${{nicheFocus}}
                    <p style="margin-top:16px;"><strong>✅ {tt('dash_strengths')}</strong></p>
                    <ul class="bullets">${{strengths}}</ul>
                    <p><strong>📈 {tt('dash_improvements')}</strong></p>
                    <ul class="bullets">${{improvements}}</ul>
                    ${{hashtagDiag}}
                    <p style="margin-top:16px;"><strong>{tt('dash_suggested_hashtags')}</strong></p>
                    <div style="margin-top:6px;">${{hashtags}}</div>
                  </div>`;

                window.__wilNiche = report.niche || '';
                window.__wilNicheCategory = report.niche_category || '';
                window.__wilBio = "{bio_enc}";
              }}
              window.__wilLang = data.lang || 'fr';
              // Contexte du compte pour le diagnostic étendu par vidéo
              // (voir analyzeVideo ci-dessous) : hashtags sur-utilisés/
              // sous-performants et meilleur créneau, calculés côté serveur.
              window.__wilBestPostingBucket = (stats && stats.best_posting_bucket) || '';
              window.__wilOverusedHashtags = (stats && stats.overused_hashtags || []).join(',');
              window.__wilUnderperformingHashtags = (stats && stats.underperforming_hashtags || []).join(',');

              if (!html) {{
                html = '<div class="card"><p class="loading">{tt('dash_analysis_unavailable')}</p></div>';
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
            .catch((e) => {{
              document.getElementById('analysis-loading').innerHTML =
                `<p class="loading" style="color:#DC2626;">{tt('dash_network_error')} ${{e && e.message ? e.message : e}}</p>`;
            }});

          // --- Analyse IA d'une vidéo précise (bouton sous chaque vignette) ---
          function analyzeVideo(idx) {{
            const v = (window.__wilVideos || [])[idx];
            if (!v) return;
            const btn = document.getElementById(`analyze-btn-${{idx}}`);
            const result = document.getElementById(`video-analysis-${{idx}}`);
            btn.disabled = true;
            btn.textContent = '{tt('dash_analyzing_short')}';
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
              create_time: v.create_time || 0,
              best_posting_bucket: window.__wilBestPostingBucket || '',
              overused_hashtags: window.__wilOverusedHashtags || '',
              underperforming_hashtags: window.__wilUnderperformingHashtags || '',
              ui_lang: window.__wilUiLang || 'fr',
            }});

            fetch(`/api/analyze-video?${{params.toString()}}`)
              .then(r => r.json().then(data => ({{ok: r.ok, status: r.status, data}})))
              .then(({{ok, status, data}}) => {{
                if (!ok) {{
                  const reason = (data && data.detail) ? data.detail : `{tt('common_error_prefix')} ${{status}}`;
                  result.innerHTML = `<p style="color:#DC2626;font-size:12px;">${{reason}}</p>`;
                  return;
                }}
                const diagnosis = data.main_diagnosis
                  ? `<p style="margin:6px 0 2px;"><strong>🔍 {tt('dash_real_problem')}</strong></p><p style="margin:0 0 8px;">${{data.main_diagnosis}}</p>`
                  : '';
                const strengths = (data.strengths || []).map(s => `<li>${{s}}</li>`).join('');
                const strengthsBlock = strengths
                  ? `<p style="margin:6px 0 2px;"><strong>✅ {tt('dash_strengths')}</strong></p><ul class="bullets" style="margin:0;">${{strengths}}</ul>`
                  : '';
                const weaknesses = (data.weaknesses || []).map(s => `<li>${{s}}</li>`).join('');
                const actions = (data.action_plan || []).map(s => `<li>${{s}}</li>`).join('');
                result.innerHTML = `
                  ${{diagnosis}}
                  ${{strengthsBlock}}
                  <p style="margin:6px 0 2px;"><strong>⚠️ {tt('dash_avoid')}</strong></p>
                  <ul class="bullets" style="margin:0;">${{weaknesses}}</ul>
                  <p style="margin:6px 0 2px;"><strong>🎯 {tt('dash_todo')}</strong></p>
                  <ul class="bullets" style="margin:0;">${{actions}}</ul>`;
              }})
              .catch((e) => {{
                result.innerHTML = `<p style="color:#DC2626;font-size:12px;">{tt('common_network_error')} ${{e && e.message ? e.message : e}}</p>`;
              }})
              .finally(() => {{
                btn.disabled = false;
                btn.textContent = '{tt('dash_btn_analyze_video')}';
              }});
          }}
        </script>
      </body>
    </html>
    """


# Style partagé par les pages outils (chacune a désormais sa propre URL,
# séparée du tableau de bord — voir /tools/analyze-video, /tools/analyze-script,
# /tools/trending-ideas).
_TOOL_PAGE_STYLE = """
  * { box-sizing: border-box; }
  body { font-family: -apple-system, Arial, sans-serif; margin: 0; padding: 40px 20px; color: #1a1a1a; }
  .wrap { max-width: 460px; margin: 0 auto; }
  h1 { font-size: 22px; margin: 0 0 6px; }
  .subtitle { color: #666; font-size: 13px; margin: 0 0 24px; line-height: 1.5; }
  .card { border: 1px solid #eee; border-radius: 14px; padding: 24px; box-shadow: 0 4px 16px rgba(0,0,0,0.06); }
  input, textarea { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #ddd; margin-bottom: 10px; font-family: inherit; }
  button.primary { width: 100%; padding: 12px; border-radius: 10px; border: none; background: #2563EB; color: white; cursor: pointer; font-weight: 600; font-size: 15px; }
  a.back { display: inline-block; margin-bottom: 20px; color: #1d4ed8; text-decoration: none; font-size: 14px; }
  .bullets { padding-left: 18px; }
  .loading { color: #777; font-size: 14px; }
"""


# Barre des 4 onglets (Accueil, Bibliothèque, Découvrir, Profil) : EN HAUT sur
# le web (choix validé après comparaison haut/bas) ; l'app mobile Flutter aura
# la sienne en bas. Fixée en haut ; body.nav-visible réserve sa hauteur.
_NAV_POSITION_CSS = """
  #app-topbar { position: fixed; top: 0; left: 0; right: 0; z-index: 40; background: #fff; padding-top: env(safe-area-inset-top); box-shadow: 0 2px 12px rgba(15, 23, 42, 0.06); }
  body.nav-visible { padding-top: 76px; }
"""

# Onboarding partagé entre "Analyser la vidéo" et "Analyser le script" :
# même structure en 9 écrans (objectif -> défi -> niche -> audience ->
# provenance -> vues moyennes -> expérience -> configuration ->
# complétion) avant que chaque outil ne prenne le relais avec son propre
# contenu (upload de fichier vidéo vs. zone de texte). Extrait ici pour
# éviter de dupliquer ~400 lignes identiques entre les deux pages.
_ONBOARDING_STYLE = """
  body { font-family: 'Inter', system-ui, sans-serif; background: #F8FAFC; }
  .step { display: none; }
  .step.active { display: block; }
  .step.active.dir-forward { animation: slideInRight 0.35s ease; }
  .step.active.dir-back { animation: slideInLeft 0.35s ease; }
  @keyframes slideInRight { from { transform: translateX(24px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
  @keyframes slideInLeft { from { transform: translateX(-24px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
  .progress-track { background: #E2E8F0; border-radius: 999px; height: 6px; overflow: hidden; }
  .progress-fill { background: linear-gradient(90deg, #2563EB, #38BDF8); height: 100%; border-radius: 999px; transition: width 0.35s ease; }
  .score-track { background: #E2E8F0; border-radius: 999px; height: 8px; overflow: hidden; }
  .score-fill { height: 100%; border-radius: 999px; transition: width 0.9s cubic-bezier(0.22, 1, 0.36, 1); }
  .niche-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
  .niche-btn { position: relative; display: flex; align-items: center; gap: 8px; padding: 12px; border-radius: 12px; background: #F1F5F9; border: 2px solid transparent; font-size: 13px; font-weight: 600; color: #334155; text-align: left; cursor: pointer; transition: all 0.15s ease; }
  .niche-btn.selected { background: #0F172A; color: #fff; border-color: #0F172A; }
  .niche-btn.selected::after { content: '✓'; position: absolute; top: 6px; right: 8px; width: 16px; height: 16px; border-radius: 50%; background: #38BDF8; color: #fff; font-size: 10px; line-height: 16px; text-align: center; animation: popIn 0.25s cubic-bezier(0.34, 1.56, 0.64, 1); }
  .challenge-btn, .simple-btn, .niche-btn { transition: all 0.15s ease, transform 0.1s ease; }
  .challenge-btn:active, .simple-btn:active, .niche-btn:active { transform: scale(0.97); }
  .challenge-btn { display: block; width: 100%; padding: 16px; border-radius: 14px; background: #F1F5F9; border: 2px solid transparent; text-align: left; cursor: pointer; margin-bottom: 12px; }
  .challenge-btn.selected { background: #0F172A; border-color: #0F172A; }
  .challenge-btn.selected .challenge-title { color: #fff; }
  .challenge-btn.selected .challenge-desc { color: #CBD5E1; }
  .challenge-title { font-weight: 700; font-size: 15px; color: #0F172A; }
  .challenge-desc { font-size: 13px; color: #64748B; margin-top: 2px; }
  .simple-btn { display: block; width: 100%; padding: 14px 16px; border-radius: 14px; background: #F1F5F9; border: 2px solid transparent; text-align: left; cursor: pointer; margin-bottom: 10px; font-weight: 600; font-size: 14px; color: #0F172A; }
  .simple-btn.selected { background: #0F172A; color: #fff; border-color: #0F172A; }
  .glow-thumb { position: relative; width: 160px; margin: 0 auto; }
  .glow-thumb::before { content: ''; position: absolute; inset: -20px; background: radial-gradient(circle, rgba(37,99,235,0.25), transparent 70%); border-radius: 24px; z-index: 0; }
  .glow-thumb img { position: relative; z-index: 1; width: 100%; border-radius: 16px; box-shadow: 0 8px 24px rgba(15,23,42,0.15); object-fit: cover; aspect-ratio: 9/16; background: #E2E8F0; }
  #step-loading .glow-thumb::before { animation: glowPulse 1.8s ease-in-out infinite; }
  @keyframes glowPulse { 0%, 100% { opacity: 0.6; transform: scale(1); } 50% { opacity: 1; transform: scale(1.06); } }
  #loading-status-text { transition: opacity 0.25s ease; }
  .tab-btn { flex: 1; text-align: center; padding: 10px; border-radius: 999px; font-size: 13px; font-weight: 600; color: #64748B; cursor: pointer; transition: all 0.15s ease; }
  .tab-btn.active { background: #0F172A; color: #fff; }
  .insight-card { background: #fff; border: 1px solid #E2E8F0; border-radius: 16px; padding: 18px; margin-bottom: 12px; animation: cardIn 0.4s ease both; }
  @keyframes cardIn { from { transform: translateY(8px); opacity: 0; } to { transform: translateY(0); opacity: 1; } }
  .copy-btn { cursor: pointer; color: #94A3B8; transition: color 0.15s ease, transform 0.1s ease; }
  .copy-btn:hover { color: #2563EB; }
  .copy-btn:active { transform: scale(0.85); }
  .improve-icon { width: 40px; height: 40px; border-radius: 10px; background: #EFF6FF; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
  .dot-bounce { display: flex; gap: 8px; justify-content: center; margin-top: 28px; }
  .dot-bounce span { width: 12px; height: 12px; border-radius: 50%; background: #2563EB; display: inline-block; animation: dotBounce 1.4s infinite ease-in-out both; }
  .dot-bounce span:nth-child(1) { animation-delay: -0.32s; }
  .dot-bounce span:nth-child(2) { animation-delay: -0.16s; }
  @keyframes dotBounce { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
  @keyframes popIn { 0% { transform: scale(0.6); opacity: 0; } 100% { transform: scale(1); opacity: 1; } }
  .complete-emoji-wrap { position: relative; display: inline-block; }
  .complete-emoji { font-size: 56px; animation: popIn 0.5s cubic-bezier(0.34, 1.56, 0.64, 1); display: inline-block; }
  .sparkle { position: absolute; font-size: 18px; opacity: 0; animation: popIn 0.4s cubic-bezier(0.34, 1.56, 0.64, 1) both; }
  .sparkle-1 { top: -6px; left: -18px; animation-delay: 0.25s; }
  .sparkle-2 { top: -10px; right: -14px; animation-delay: 0.4s; }
  .sparkle-3 { bottom: 2px; right: -22px; animation-delay: 0.55s; }
  #mute-toggle-btn { transition: transform 0.15s ease, top 0.2s ease; }
  #mute-toggle-btn:active { transform: scale(0.9); }
  .nav-item { color: #6B7280; font-size: 11.5px; font-weight: 500; text-decoration: none; border-radius: 14px; margin: 8px 3px; transition: background 0.15s ease, color 0.15s ease; }
  .nav-item:hover { background: #F8FAFC; }
  .nav-item.active { color: #2563EB; font-weight: 700; background: #EFF6FF; }
  .nav-item svg { width: 24px; height: 24px; }
""" + _NAV_POSITION_CSS

_ONBOARDING_HEAD_ASSETS = """
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = { theme: { extend: { fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] } } } };
    </script>"""

_ONBOARDING_MUTE_BUTTON_HTML = """
        <button id="mute-toggle-btn" onclick="toggleMute()" type="button" title="Son"
                class="fixed top-4 right-4 z-50 w-9 h-9 rounded-full bg-white shadow-md flex items-center justify-center text-base">
          <span id="mute-toggle-icon">🔊</span>
        </button>"""


_TOPBAR_ICONS = {
    "home": '<path d="M3 11.5L12 4l9 7.5"/><path d="M5.5 10v10h13V10"/><path d="M10 20v-5h4v5"/>',
    "library": '<rect x="3.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.8"/>',
    "discover": '<circle cx="12" cy="12" r="9"/><path d="M15.6 8.4l-2 5.2-5.2 2 2-5.2z"/>',
    "profile": '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c0-4 3.4-6 7.5-6s7.5 2 7.5 6"/>',
}


def _app_topbar_html(tt, active: str = "home") -> str:
    """
    Barre des 4 onglets (Accueil, Bibliothèque, Découvrir, Profil) pour les
    pages d'outils : même rendu que sur /app, mais en liens vers
    /app#<onglet>. Masquée tant que l'onboarding est en cours (le JS du
    coeur d'onboarding la montre dès qu'on atteint le contenu de l'outil).
    """
    labels = {
        "home": tt("app_tab_home"),
        "library": tt("app_tab_library"),
        "discover": tt("app_tab_discover"),
        "profile": tt("app_tab_profile"),
    }
    items = "".join(
        f'''<a href="/app#{key}" class="nav-item{" active" if key == active else ""} flex-1 flex flex-col items-center justify-center gap-0.5 py-2">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{_TOPBAR_ICONS[key]}</svg>
          <span>{labels[key]}</span></a>'''
        for key in ("home", "library", "discover", "profile")
    )
    return (
        '<nav id="app-topbar" class="hidden">'
        f'<div class="max-w-md mx-auto flex px-2">{items}</div></nav>'
    )


def _onboarding_steps_html(
    tt, niche_buttons: str, content_step_id: str, complete_onclick: str | None = None
) -> str:
    """
    Étapes 1 à 9 de l'onboarding, identiques entre les outils. Seul
    `content_step_id` change : c'est l'étape suivante propre à chaque
    outil (upload vidéo ou zone de script) que le bouton "Commencer" de
    l'écran de complétion doit viser. `complete_onclick` remplace cette
    navigation par une action JS (page /onboarding autonome : mémoriser
    les réponses puis ouvrir /app).
    """
    complete_action = complete_onclick or f"goToStep('{content_step_id}', 100, true)"
    return f"""
          <div id="onboarding-header" class="flex items-center gap-3 mb-6">
            <a href="#" onclick="goBackStep(); return false;" class="text-slate-400 hover:text-slate-700">←</a>
            <div class="progress-track flex-1"><div id="progress-fill" class="progress-fill" style="width:11%"></div></div>
          </div>

          <!-- ÉTAPE 1 : objectif principal -->
          <div id="step-goal" class="step active">
            <h1 class="text-xl font-extrabold mb-1">{tt("onboarding_goal_title")}</h1>
            <p class="text-sm text-slate-500 mb-6">{tt("onboarding_goal_subtitle")}</p>
            <button type="button" class="simple-btn goal-btn" onclick="selectGoal('views', this)">{tt("onboarding_goal_views")}</button>
            <button type="button" class="simple-btn goal-btn" onclick="selectGoal('engagement', this)">{tt("onboarding_goal_engagement")}</button>
            <button type="button" class="simple-btn goal-btn" onclick="selectGoal('fanbase', this)">{tt("onboarding_goal_fanbase")}</button>
            <button type="button" class="simple-btn goal-btn" onclick="selectGoal('collabs', this)">{tt("onboarding_goal_collabs")}</button>
            <button type="button" class="simple-btn goal-btn" onclick="selectGoal('other', this)">{tt("onboarding_goal_other")}</button>
            <button id="goal-next-btn" disabled onclick="goToStep('step-challenge', 22, true)"
                    class="w-full mt-2 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition">
              {tt("onboarding_next")}
            </button>
          </div>

          <!-- ÉTAPE 2 : plus gros défi -->
          <div id="step-challenge" class="step">
            <h1 class="text-xl font-extrabold mb-6">{tt("onboarding_challenge_title")}</h1>
            <button type="button" class="challenge-btn" onclick="selectChallenge('followers', this)">
              <div class="challenge-title">👤 {tt("onboarding_challenge_followers_title")}</div>
              <div class="challenge-desc">{tt("onboarding_challenge_followers_desc")}</div>
            </button>
            <button type="button" class="challenge-btn" onclick="selectChallenge('engagement', this)">
              <div class="challenge-title">💬 {tt("onboarding_challenge_engagement_title")}</div>
              <div class="challenge-desc">{tt("onboarding_challenge_engagement_desc")}</div>
            </button>
            <button type="button" class="challenge-btn" onclick="selectChallenge('reach', this)">
              <div class="challenge-title">▶️ {tt("onboarding_challenge_reach_title")}</div>
              <div class="challenge-desc">{tt("onboarding_challenge_reach_desc")}</div>
            </button>
            <button id="challenge-next-btn" disabled onclick="goToStep('step-niche', 33, true)"
                    class="w-full mt-2 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition">
              {tt("onboarding_next")}
            </button>
          </div>

          <!-- ÉTAPE 3 : niche (sélection multiple) -->
          <div id="step-niche" class="step">
            <h1 class="text-xl font-extrabold mb-1">{tt("onboarding_niche_title")}</h1>
            <p class="text-sm text-slate-500 mb-1">{tt("onboarding_niche_subtitle")}</p>
            <p class="text-xs text-slate-400 mb-4">{tt("onboarding_niche_multi_hint")}</p>
            <div class="niche-grid">{niche_buttons}</div>
            <button id="niche-next-btn" disabled onclick="goToStep('step-audience', 44, true)"
                    class="w-full mt-6 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition">
              {tt("onboarding_next")}
            </button>
          </div>

          <!-- ÉTAPE 4 : âge de l'audience -->
          <div id="step-audience" class="step">
            <h1 class="text-xl font-extrabold mb-1">{tt("onboarding_audience_title")}</h1>
            <p class="text-sm text-slate-500 mb-6">{tt("onboarding_audience_subtitle")}</p>
            <button type="button" class="challenge-btn audience-opt" onclick="selectAudience('teens', this)">
              <div class="challenge-title">{tt("onboarding_audience_teens")}</div>
              <div class="challenge-desc">{tt("onboarding_audience_teens_desc")}</div>
            </button>
            <button type="button" class="challenge-btn audience-opt" onclick="selectAudience('young_adults', this)">
              <div class="challenge-title">{tt("onboarding_audience_young_adults")}</div>
              <div class="challenge-desc">{tt("onboarding_audience_young_adults_desc")}</div>
            </button>
            <button type="button" class="challenge-btn audience-opt" onclick="selectAudience('adults', this)">
              <div class="challenge-title">{tt("onboarding_audience_adults")}</div>
              <div class="challenge-desc">{tt("onboarding_audience_adults_desc")}</div>
            </button>
            <button type="button" class="challenge-btn audience-opt" onclick="selectAudience('general', this)">
              <div class="challenge-title">{tt("onboarding_audience_general")}</div>
              <div class="challenge-desc">{tt("onboarding_audience_general_desc")}</div>
            </button>
            <button id="audience-next-btn" disabled onclick="goToStep('step-source', 55, true)"
                    class="w-full mt-2 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition">
              {tt("onboarding_next")}
            </button>
          </div>

          <!-- ÉTAPE 5 : provenance -->
          <div id="step-source" class="step">
            <h1 class="text-xl font-extrabold mb-6">{tt("onboarding_source_title")}</h1>
            <button type="button" class="simple-btn source-btn" onclick="selectSource('tiktok', this)">🎵 {tt("onboarding_source_tiktok")}</button>
            <button type="button" class="simple-btn source-btn" onclick="selectSource('instagram', this)">📸 {tt("onboarding_source_instagram")}</button>
            <button type="button" class="simple-btn source-btn" onclick="selectSource('reddit', this)">👽 {tt("onboarding_source_reddit")}</button>
            <button type="button" class="simple-btn source-btn" onclick="selectSource('google', this)">🔎 {tt("onboarding_source_google")}</button>
            <button type="button" class="simple-btn source-btn" onclick="selectSource('friend', this)">👥 {tt("onboarding_source_friend")}</button>
            <button type="button" class="simple-btn source-btn" onclick="selectSource('other', this)">✨ {tt("onboarding_source_other")}</button>
            <button id="source-next-btn" disabled onclick="advanceFromSource()"
                    class="w-full mt-2 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition">
              {tt("onboarding_next")}
            </button>
          </div>

          <!-- ÉTAPE 6 : vues moyennes (sautée si déjà connue via le tableau de bord) -->
          <div id="step-views" class="step">
            <h1 class="text-xl font-extrabold mb-1">{tt("onboarding_views_title")}</h1>
            <p class="text-sm text-slate-500 mb-6">{tt("onboarding_views_subtitle")}</p>
            <button type="button" class="simple-btn views-btn" onclick="selectViews(500, this)">{tt("onboarding_views_lt1000")}</button>
            <button type="button" class="simple-btn views-btn" onclick="selectViews(3000, this)">{tt("onboarding_views_1k_5k")}</button>
            <button type="button" class="simple-btn views-btn" onclick="selectViews(12000, this)">{tt("onboarding_views_5k_20k")}</button>
            <button type="button" class="simple-btn views-btn" onclick="selectViews(35000, this)">{tt("onboarding_views_20k_50k")}</button>
            <button type="button" class="simple-btn views-btn" onclick="selectViews(75000, this)">{tt("onboarding_views_gt50k")}</button>
            <button id="views-next-btn" disabled onclick="goToStep('step-experience', 77, true)"
                    class="w-full mt-2 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition">
              {tt("onboarding_next")}
            </button>
          </div>

          <!-- ÉTAPE 7 : niveau d'expérience -->
          <div id="step-experience" class="step">
            <h1 class="text-xl font-extrabold mb-6">{tt("onboarding_experience_title")}</h1>
            <button type="button" class="challenge-btn experience-opt" onclick="selectExperience('beginner', this)">
              <div class="challenge-title">{tt("onboarding_experience_beginner")}</div>
              <div class="challenge-desc">{tt("onboarding_experience_beginner_desc")}</div>
            </button>
            <button type="button" class="challenge-btn experience-opt" onclick="selectExperience('starting', this)">
              <div class="challenge-title">{tt("onboarding_experience_starting")}</div>
              <div class="challenge-desc">{tt("onboarding_experience_starting_desc")}</div>
            </button>
            <button type="button" class="challenge-btn experience-opt" onclick="selectExperience('advanced', this)">
              <div class="challenge-title">{tt("onboarding_experience_advanced")}</div>
              <div class="challenge-desc">{tt("onboarding_experience_advanced_desc")}</div>
            </button>
            <button type="button" class="challenge-btn experience-opt" onclick="selectExperience('pro', this)">
              <div class="challenge-title">{tt("onboarding_experience_pro")}</div>
              <div class="challenge-desc">{tt("onboarding_experience_pro_desc")}</div>
            </button>
            <button id="experience-next-btn" disabled onclick="enterSetupStep()"
                    class="w-full mt-2 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition">
              {tt("onboarding_next")}
            </button>
          </div>

          <!-- ÉTAPE 8 : configuration (transition automatique) -->
          <div id="step-setup" class="step text-center">
            <div class="dot-bounce mt-24"><span></span><span></span><span></span></div>
            <p class="mt-8 font-semibold text-slate-700">{tt("onboarding_setup_text")}</p>
          </div>

          <!-- ÉTAPE 9 : complétion de l'onboarding -->
          <div id="step-complete" class="step text-center">
            <div class="mt-16 mb-4">
              <div class="complete-emoji-wrap">
                <span class="complete-emoji">📣</span>
                <span class="sparkle sparkle-1">✨</span>
                <span class="sparkle sparkle-2">⭐</span>
                <span class="sparkle sparkle-3">✨</span>
              </div>
            </div>
            <p class="inline-block bg-green-50 text-green-700 text-xs font-bold px-3 py-1 rounded-full mb-4">✅ {tt("onboarding_complete_badge")}</p>
            <h1 class="text-2xl font-extrabold mb-3">{tt("onboarding_complete_title")}</h1>
            <p class="text-sm text-slate-500 mb-8">{tt("onboarding_complete_subtitle")}</p>
            <button onclick="{complete_action}"
                    class="w-full py-3.5 rounded-xl bg-blue-600 text-white font-bold text-sm transition hover:bg-blue-700">
              {tt("onboarding_complete_start_btn")}
            </button>
          </div>"""


def _onboarding_js_core(
    niche_category: str,
    account_avg_views: str,
    lang: str,
    content_step_id: str,
    allow_skip: bool = True,
) -> str:
    """
    État, audio synthétisé (jamais de fichier audio copié — voir le
    commentaire dans la doc de la route ci-dessous), navigation avant/
    arrière et fonctions de sélection de l'onboarding, identiques entre
    les deux outils. `content_step_id` est l'étape propre à chaque outil
    qui suit l'écran de complétion (seule variation).

    Mémoire : les réponses sont sauvegardées dans localStorage
    ("wilOnboarding") dès la fin de l'onboarding. Si elles existent déjà
    (`allow_skip`), la page saute directement à `content_step_id` :
    l'utilisateur ne refait jamais l'onboarding à chaque visite. La page
    /onboarding elle-même passe allow_skip=False.
    """
    apply_stored_js = (
        f"""
          (function applyStoredOnboarding() {{
            const stored = loadOnboarding();
            if (!stored || !stored.niches || stored.niches.length === 0) return;
            selectedGoal = stored.goal || '';
            selectedChallenge = stored.challenge || '';
            selectedAudience = stored.audience || '';
            selectedSource = stored.source || '';
            selectedExperience = stored.experience || '';
            if (selectedNiches.length === 0) {{ selectedNiches = stored.niches.slice(); }}
            if (!accountAvgViewsFromUrl && stored.avgViews) {{ accountAvgViewsFinal = String(stored.avgViews); }}
            onboardingSkipped = true;
            goToStep('{content_step_id}', 100, true);
          }})();"""
        if allow_skip
        else ""
    )
    return f"""
          const nicheCategoryFromUrl = "{niche_category}";
          const accountAvgViewsFromUrl = "{account_avg_views}";
          const uiLang = "{lang}";
          const MAX_NICHES = 3;
          let selectedNiches = [];
          let selectedGoal = '';
          let selectedChallenge = '';
          let selectedAudience = '';
          let selectedSource = '';
          let selectedExperience = '';
          let accountAvgViewsFinal = accountAvgViewsFromUrl;
          let currentStepId = 'step-goal';
          let onboardingSkipped = false;

          const WIL_ONBOARDING_KEY = 'wilOnboarding';
          const WIL_HISTORY_KEY = 'wilHistory';

          function saveOnboarding() {{
            try {{
              localStorage.setItem(WIL_ONBOARDING_KEY, JSON.stringify({{
                goal: selectedGoal, challenge: selectedChallenge, niches: selectedNiches,
                audience: selectedAudience, source: selectedSource, avgViews: accountAvgViewsFinal,
                experience: selectedExperience, savedAt: Date.now()
              }}));
            }} catch (e) {{}}
          }}

          function loadOnboarding() {{
            try {{ return JSON.parse(localStorage.getItem(WIL_ONBOARDING_KEY) || 'null'); }} catch (e) {{ return null; }}
          }}

          function saveHistoryEntry(entry) {{
            try {{
              const list = JSON.parse(localStorage.getItem(WIL_HISTORY_KEY) || '[]');
              list.unshift(entry);
              localStorage.setItem(WIL_HISTORY_KEY, JSON.stringify(list.slice(0, 50)));
            }} catch (e) {{}}
          }}

          let audioCtx = null;
          let masterGain = null;
          let ambientStarted = false;
          let audioMuted = false;

          function ensureAudioContext() {{
            if (!audioCtx) {{
              const Ctx = window.AudioContext || window.webkitAudioContext;
              if (!Ctx) return;
              audioCtx = new Ctx();
              masterGain = audioCtx.createGain();
              masterGain.gain.value = audioMuted ? 0 : 0.15;
              masterGain.connect(audioCtx.destination);
            }}
            if (audioCtx.state === 'suspended') {{ audioCtx.resume(); }}
          }}

          function startAmbient() {{
            ensureAudioContext();
            if (!audioCtx || ambientStarted) return;
            ambientStarted = true;

            const filter = audioCtx.createBiquadFilter();
            filter.type = 'lowpass';
            filter.frequency.value = 900;
            filter.connect(masterGain);
            filter.frequency.linearRampToValueAtTime(1400, audioCtx.currentTime + 12);

            const freqs = [130.81, 164.81, 196.00];
            freqs.forEach(function (f, i) {{
              const osc = audioCtx.createOscillator();
              osc.type = 'sine';
              osc.frequency.value = f;
              const oscGain = audioCtx.createGain();
              oscGain.gain.value = 0;
              osc.connect(oscGain);
              oscGain.connect(filter);
              osc.start();
              oscGain.gain.linearRampToValueAtTime(0.32 / freqs.length, audioCtx.currentTime + 2 + i * 0.3);

              const lfo = audioCtx.createOscillator();
              lfo.frequency.value = 0.08 + i * 0.02;
              const lfoGain = audioCtx.createGain();
              lfoGain.gain.value = 3;
              lfo.connect(lfoGain);
              lfoGain.connect(osc.frequency);
              lfo.start();
            }});
          }}

          function playTapSound() {{
            if (audioMuted || !audioCtx) return;
            const osc = audioCtx.createOscillator();
            osc.type = 'sine';
            osc.frequency.value = 880;
            const g = audioCtx.createGain();
            g.gain.value = 0.3;
            osc.connect(g);
            // Branché directement (pas via masterGain, réglé bas pour l'ambiance) : le son
            // de sélection reste bien audible sans rendre l'ambiance plus forte.
            g.connect(audioCtx.destination);
            osc.start();
            g.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.2);
            osc.stop(audioCtx.currentTime + 0.21);
          }}

          function toggleMute() {{
            audioMuted = !audioMuted;
            ensureAudioContext();
            startAmbient();
            if (masterGain) {{ masterGain.gain.linearRampToValueAtTime(audioMuted ? 0 : 0.15, audioCtx.currentTime + 0.2); }}
            document.getElementById('mute-toggle-icon').textContent = audioMuted ? '🔇' : '🔊';
          }}

          document.addEventListener('click', function initAudioOnce() {{
            startAmbient();
            document.removeEventListener('click', initAudioOnce);
          }}, {{ once: true }});

          function animateNumber(el, to, duration) {{
            const startTime = performance.now();
            function step(ts) {{
              const progress = Math.min((ts - startTime) / duration, 1);
              el.textContent = Math.round(progress * to) + '/100';
              if (progress < 1) {{ requestAnimationFrame(step); }}
            }}
            requestAnimationFrame(step);
          }}

          function setLoadingText(text) {{
            const el = document.getElementById('loading-status-text');
            el.style.opacity = 0;
            setTimeout(function () {{ el.textContent = text; el.style.opacity = 1; }}, 250);
          }}

          const BACK_TARGETS = {{
            'step-challenge': ['step-goal', 11],
            'step-niche': ['step-challenge', 22],
            'step-audience': ['step-niche', 33],
            'step-source': ['step-audience', 44],
            'step-views': ['step-source', 55],
            '{content_step_id}': ['step-experience', 77]
          }};

          if (nicheCategoryFromUrl) {{
            try {{
              const preBtn = document.querySelector('.niche-btn[data-niche="' + CSS.escape(nicheCategoryFromUrl) + '"]');
              if (preBtn) {{ toggleNiche(nicheCategoryFromUrl, preBtn); }}
            }} catch (e) {{}}
          }}

          const ONBOARDING_STEP_IDS = ['step-goal', 'step-challenge', 'step-niche', 'step-audience', 'step-source', 'step-views', 'step-experience', 'step-setup', 'step-complete'];
          function isOnboardingStep(stepId) {{ return ONBOARDING_STEP_IDS.indexOf(stepId) !== -1; }}

          function goToStep(stepId, progressPct, showHeader, direction) {{
            document.querySelectorAll('.step').forEach(function (s) {{ s.classList.remove('active', 'dir-forward', 'dir-back'); }});
            const el = document.getElementById(stepId);
            el.classList.add('active');
            el.classList.add(direction === 'back' ? 'dir-back' : 'dir-forward');
            currentStepId = stepId;
            // Hors onboarding (contenu de l'outil, chargement, résultats) : la barre des
            // 4 onglets reste en haut et la flèche de retour ramène à l'accueil.
            const inTool = !isOnboardingStep(stepId);
            const header = document.getElementById('onboarding-header');
            header.style.display = (showHeader || (inTool && stepId !== 'step-loading')) ? 'flex' : 'none';
            const track = header.querySelector('.progress-track');
            if (track) {{ track.style.display = inTool ? 'none' : ''; }}
            document.getElementById('progress-fill').style.width = progressPct + '%';
            const topbar = document.getElementById('app-topbar');
            if (topbar) {{ topbar.classList.toggle('hidden', !inTool); }}
            document.body.classList.toggle('nav-visible', inTool && !!topbar);
            const muteBtn = document.getElementById('mute-toggle-btn');
            if (muteBtn) {{ muteBtn.style.top = (inTool && topbar) ? '84px' : '16px'; }}
            window.scrollTo(0, 0);
          }}

          function goBackStep() {{
            if (!isOnboardingStep(currentStepId)) {{ window.location.href = '/app'; return; }}
            if (currentStepId === 'step-goal') {{ window.location.href = '/'; return; }}
            if (currentStepId === 'step-experience') {{
              if (accountAvgViewsFromUrl) {{ goToStep('step-source', 55, true, 'back'); }} else {{ goToStep('step-views', 66, true, 'back'); }}
              return;
            }}
            const target = BACK_TARGETS[currentStepId];
            if (target) {{ goToStep(target[0], target[1], true, 'back'); }}
          }}

          function advanceFromSource() {{
            if (accountAvgViewsFromUrl) {{ goToStep('step-experience', 77, true); }} else {{ goToStep('step-views', 66, true); }}
          }}

          function enterSetupStep() {{
            saveOnboarding();
            goToStep('step-setup', 88, false);
            setTimeout(function () {{ goToStep('step-complete', 100, false); }}, 2200);
          }}

          function toggleNiche(niche, btnEl) {{
            playTapSound();
            const idx = selectedNiches.indexOf(niche);
            if (idx !== -1) {{
              selectedNiches.splice(idx, 1);
              btnEl.classList.remove('selected');
            }} else {{
              if (selectedNiches.length >= MAX_NICHES) return;
              selectedNiches.push(niche);
              btnEl.classList.add('selected');
            }}
            var btn = document.getElementById('niche-next-btn');
            if (selectedNiches.length > 0) {{
              btn.disabled = false;
              btn.className = 'w-full mt-6 py-3.5 rounded-xl bg-blue-600 text-white font-bold text-sm transition hover:bg-blue-700';
            }} else {{
              btn.disabled = true;
              btn.className = 'w-full mt-6 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition';
            }}
          }}

          function selectGoal(value, btnEl) {{
            playTapSound();
            selectedGoal = value;
            document.querySelectorAll('.goal-btn').forEach(function (b) {{ b.classList.remove('selected'); }});
            btnEl.classList.add('selected');
            var btn = document.getElementById('goal-next-btn');
            btn.disabled = false;
            btn.className = 'w-full mt-2 py-3.5 rounded-xl bg-blue-600 text-white font-bold text-sm transition hover:bg-blue-700';
          }}

          function selectChallenge(challenge, btnEl) {{
            playTapSound();
            selectedChallenge = challenge;
            document.querySelectorAll('#step-challenge .challenge-btn').forEach(function (b) {{ b.classList.remove('selected'); }});
            btnEl.classList.add('selected');
            var btn = document.getElementById('challenge-next-btn');
            btn.disabled = false;
            btn.className = 'w-full mt-2 py-3.5 rounded-xl bg-blue-600 text-white font-bold text-sm transition hover:bg-blue-700';
          }}

          function selectAudience(value, btnEl) {{
            playTapSound();
            selectedAudience = value;
            document.querySelectorAll('.audience-opt').forEach(function (b) {{ b.classList.remove('selected'); }});
            btnEl.classList.add('selected');
            var btn = document.getElementById('audience-next-btn');
            btn.disabled = false;
            btn.className = 'w-full mt-2 py-3.5 rounded-xl bg-blue-600 text-white font-bold text-sm transition hover:bg-blue-700';
          }}

          function selectSource(value, btnEl) {{
            playTapSound();
            selectedSource = value;
            document.querySelectorAll('.source-btn').forEach(function (b) {{ b.classList.remove('selected'); }});
            btnEl.classList.add('selected');
            var btn = document.getElementById('source-next-btn');
            btn.disabled = false;
            btn.className = 'w-full mt-2 py-3.5 rounded-xl bg-blue-600 text-white font-bold text-sm transition hover:bg-blue-700';
          }}

          function selectViews(value, btnEl) {{
            playTapSound();
            accountAvgViewsFinal = String(value);
            document.querySelectorAll('.views-btn').forEach(function (b) {{ b.classList.remove('selected'); }});
            btnEl.classList.add('selected');
            var btn = document.getElementById('views-next-btn');
            btn.disabled = false;
            btn.className = 'w-full mt-2 py-3.5 rounded-xl bg-blue-600 text-white font-bold text-sm transition hover:bg-blue-700';
          }}

          function selectExperience(value, btnEl) {{
            playTapSound();
            selectedExperience = value;
            document.querySelectorAll('.experience-opt').forEach(function (b) {{ b.classList.remove('selected'); }});
            btnEl.classList.add('selected');
            var btn = document.getElementById('experience-next-btn');
            btn.disabled = false;
            btn.className = 'w-full mt-2 py-3.5 rounded-xl bg-blue-600 text-white font-bold text-sm transition hover:bg-blue-700';
          }}

          function copyText(text) {{
            if (navigator.clipboard) {{ navigator.clipboard.writeText(text).catch(function () {{}}); }}
          }}

          function switchTab(tab) {{
            document.getElementById('tab-stats').classList.toggle('hidden', tab !== 'stats');
            document.getElementById('tab-improvements').classList.toggle('hidden', tab !== 'improvements');
            document.getElementById('tabbtn-stats').classList.toggle('active', tab === 'stats');
            document.getElementById('tabbtn-improvements').classList.toggle('active', tab === 'improvements');
          }}

          function scoreColor(score) {{
            if (score <= 40) return '#DC2626';
            if (score <= 60) return '#F59E0B';
            if (score <= 80) return '#F97316';
            return '#2563EB';
          }}
{apply_stored_js}"""


@app.get("/tools/analyze-account", response_class=HTMLResponse)
def tool_analyze_account_page(request: Request):
    """
    Page d'onboarding avant la connexion TikTok — même structure que
    "Analyser la vidéo"/"Analyser le script" (objectif -> défi -> niche
    -> audience -> provenance -> vues moyennes -> expérience ->
    configuration -> complétion), suivie d'un écran "Connecte ton compte
    TikTok" au lieu d'un upload/d'une zone de texte : il n'y a rien
    d'autre à fournir ici, la vraie analyse se fait automatiquement sur
    le tableau de bord une fois connecté (voir tiktok_callback).

    Contrairement à la vidéo/au script, la niche n'est jamais envoyée
    au backend depuis cette page : /api/analyze-account la détecte déjà
    depuis les vraies vidéos du compte, la redemander à l'utilisateur
    serait à la fois redondant et trompeur. Seul `main_challenge` est
    transmis, encodé dans le "state" OAuth (voir tiktok_login), pour
    orienter l'angle des conseils sans jamais inventer de statistique.
    """
    lang = _detect_ui_lang(request)
    tt = lambda key: t(lang, key)  # noqa: E731

    niche_buttons = "".join(
        f'''<button type="button" class="niche-btn" data-niche="{n}" onclick="toggleNiche('{n}', this)">
              <span class="text-lg">{NICHE_EMOJIS.get(n, "✨")}</span>
              <span>{n}</span>
            </button>'''
        for n in NICHE_CATEGORIES
    )

    return f"""
    <html lang="{lang}">
      <head>
        <title>{tt("tool_account_title")} — Wil App</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">{_ONBOARDING_HEAD_ASSETS}
        <style>{_ONBOARDING_STYLE}</style>
      </head>
      <body class="text-slate-900">{_ONBOARDING_MUTE_BUTTON_HTML}{_app_topbar_html(tt)}
        <div class="max-w-md mx-auto px-5 py-6">
{_onboarding_steps_html(tt, niche_buttons, "step-account")}

          <!-- ÉTAPE 10 : connexion TikTok -->
          <div id="step-account" class="step text-center">
            <div class="text-6xl mt-10 mb-6">🔗</div>
            <h1 class="text-xl font-extrabold mb-1">{tt("tool_account_title")}</h1>
            <p class="text-sm text-slate-500 mb-8">{tt("tool_account_subtitle")}</p>
            <button onclick="connectTikTok()"
                    class="w-full py-3.5 rounded-xl bg-blue-600 text-white font-bold text-sm transition hover:bg-blue-700">
              {tt("tool_account_connect_btn")}
            </button>
            <p class="text-xs text-slate-400 mt-3">{tt("trust_line")}</p>
          </div>

        </div>

        <script>
{_onboarding_js_core("", "", lang, "step-account")}

          function connectTikTok() {{
            window.location.href = '/auth/tiktok/login?main_challenge=' + encodeURIComponent(selectedChallenge);
          }}
        </script>
      </body>
    </html>
    """


@app.get("/tools/analyze-video", response_class=HTMLResponse)
def tool_analyze_video_page(request: Request, niche_category: str = "", account_avg_views: str = ""):
    """
    Page dédiée pour l'analyse approfondie d'une vidéo importée (upload +
    analyse de la vidéo brute par Gemini, images et son). Reçoit le contexte du compte (niche, moyenne de
    vues) en paramètres d'URL, transmis par le tableau de bord au clic sur
    le bouton "Analyser la vidéo" — cette page n'a plus besoin de session.

    Parcours en onboarding complet à plusieurs écrans (objectif, défi,
    niche, audience, provenance, vues moyennes, expérience, écran de
    configuration, écran de complétion) -> upload -> chargement par
    étapes -> résultat en onglets, inspiré de la structure d'une app
    concurrente ("Go Viral"). Les écrans purement déclaratifs (choix de
    l'utilisateur sur lui-même) sont repris fidèlement. En revanche, ses
    statistiques de vues/likes prédites, son graphique de simulation et
    ses témoignages sont fabriqués (vérifié en comparant plusieurs vidéos
    dans leur app : même animation générique à chaque fois, aucun vrai
    calcul derrière, avis clients inventés) — Wil App ne les reprend pas.
    À la place : un vrai score de viralité basé sur l'analyse réelle du
    hook/rythme (RÈGLE D'OR N°1 : jamais inventé).
    """
    lang = _detect_ui_lang(request)
    tt = lambda key: t(lang, key)  # noqa: E731

    niche_buttons = "".join(
        f'''<button type="button" class="niche-btn" data-niche="{n}" onclick="toggleNiche('{n}', this)">
              <span class="text-lg">{NICHE_EMOJIS.get(n, "✨")}</span>
              <span>{n}</span>
            </button>'''
        for n in NICHE_CATEGORIES
    )

    return f"""
    <html lang="{lang}">
      <head>
        <title>{tt("tool_video_title")} — Wil App</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">{_ONBOARDING_HEAD_ASSETS}
        <style>{_ONBOARDING_STYLE}</style>
      </head>
      <body class="text-slate-900">{_ONBOARDING_MUTE_BUTTON_HTML}{_app_topbar_html(tt)}
        <div class="max-w-md mx-auto px-5 py-6">
{_onboarding_steps_html(tt, niche_buttons, "step-upload")}

          <!-- ÉTAPE 10 : upload -->
          <div id="step-upload" class="step">
            <h1 class="text-xl font-extrabold mb-1">{tt("tool_video_title")}</h1>
            <p class="text-sm text-slate-500 mb-6">{tt("tool_video_subtitle")}</p>
            <label for="upload-video-input" id="upload-dropzone" class="block cursor-pointer text-center"
                   style="border:3px dashed #d4d4d8;border-radius:28px;background:#f1f1f1;padding:36px 20px;">
              <div id="upload-dropzone-empty">
                <svg class="mx-auto" width="56" height="56" viewBox="0 0 48 48" fill="none" stroke="#ff2d55" stroke-width="5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M24 31V9"/><path d="M13 20L24 9l11 11"/><path d="M6 30v7a3 3 0 0 0 3 3h30a3 3 0 0 0 3-3v-7"/>
                </svg>
                <p class="font-semibold text-xl text-slate-900 mt-5 leading-snug">{tt("upload_dropzone_title")}</p>
                <p class="text-sm text-slate-500 mt-3">{tt("upload_dropzone_formats")}</p>
              </div>
              <img id="upload-thumb-preview" alt="" class="hidden mx-auto rounded-2xl" style="max-height:260px;object-fit:cover;" />
            </label>
            <input id="upload-video-input" type="file" accept="video/*" class="hidden" onchange="onVideoSelected(event)" />
            <p id="upload-file-hint" class="text-center text-xs text-slate-400 mt-3 break-all"></p>
            <p class="font-semibold text-sm text-center mt-6 mb-3">{tt("tool_video_published_q")}</p>
            <div class="flex gap-3">
              <button type="button" id="published-yes-btn" onclick="setPublished(true)"
                      class="flex-1 py-3 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm transition">{tt("tool_video_published_yes")}</button>
              <button type="button" id="published-no-btn" onclick="setPublished(false)"
                      class="flex-1 py-3 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm transition">{tt("tool_video_published_no")}</button>
            </div>
            <button id="upload-launch-btn" disabled onclick="launchAnalysis()"
                    class="w-full mt-4 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition">
              {tt("tool_video_analyze_btn")}
            </button>
            <div id="upload-error" class="text-center text-sm text-red-600 mt-3"></div>
          </div>

          <!-- ÉTAPE 11 : chargement -->
          <div id="step-loading" class="step text-center">
            <div class="glow-thumb mt-10">
              <img id="loading-thumb-preview" alt="" />
            </div>
            <p id="loading-status-text" class="mt-8 font-semibold text-slate-700">{tt("loading_upload")}</p>
          </div>

          <!-- ÉTAPE 12 : résultat -->
          <div id="step-results" class="step">
            <div class="flex items-center justify-between mb-4">
              <span class="font-extrabold text-lg">Wil App</span>
              <button onclick="resetFlow()" class="text-xs font-semibold text-blue-600 hover:text-blue-700">{tt("tool_video_analyze_btn")}</button>
            </div>

            <div class="glow-thumb mb-5" style="width:110px;">
              <img id="result-thumb-preview" alt="" />
            </div>

            <h2 class="text-lg font-bold mb-4">{tt("results_smart_insights")}</h2>

            <div class="insight-card">
              <div class="flex items-center justify-between mb-2">
                <span class="font-semibold text-sm">{tt("results_viral_potential")}</span>
                <span id="viral-score-value" class="font-extrabold text-blue-600">—/100</span>
              </div>
              <div class="score-track"><div id="viral-score-bar" class="score-fill" style="width:0%"></div></div>
              <p id="score-basis-text" class="text-xs text-slate-400 mt-2"></p>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div class="insight-card">
                <p class="font-semibold text-sm mb-1">{tt("results_niche_label")}</p>
                <p id="result-niche-value" class="text-sm text-slate-600"></p>
              </div>
              <div class="insight-card">
                <div class="flex items-center justify-between mb-1">
                  <p class="font-semibold text-sm">Hashtags</p>
                  <span class="copy-btn text-xs" onclick="copyText(document.getElementById('result-hashtags-value').textContent)">📋</span>
                </div>
                <p id="result-hashtags-value" class="text-sm text-blue-600"></p>
              </div>
            </div>

            <div class="insight-card">
              <div class="flex items-center justify-between mb-1">
                <p class="font-semibold text-sm">{tt("results_caption_label")}</p>
                <span class="copy-btn text-xs" onclick="copyText(document.getElementById('result-caption-value').textContent)">📋</span>
              </div>
              <p id="result-caption-value" class="text-sm text-slate-600"></p>
            </div>

            <div class="flex gap-2 bg-slate-100 rounded-full p-1 my-5">
              <div id="tabbtn-improvements" class="tab-btn active" onclick="switchTab('improvements')">{tt("results_tab_improvements")}</div>
              <div id="tabbtn-stats" class="tab-btn" onclick="switchTab('stats')">{tt("results_tab_stats")}</div>
            </div>

            <div id="tab-improvements">
              <div class="insight-card">
                <div class="flex items-start gap-3">
                  <div class="improve-icon">🎬</div>
                  <div class="flex-1">
                    <p class="font-bold text-sm mb-1">{tt("tool_video_hook_real")}</p>
                    <p id="result-hook-value" class="text-sm text-slate-600 italic"></p>
                  </div>
                </div>
              </div>
              <div class="insight-card">
                <div class="flex items-start gap-3">
                  <div class="improve-icon">✅</div>
                  <div class="flex-1">
                    <p class="font-bold text-sm mb-1">{tt("dash_strengths")}</p>
                    <ul id="result-strengths-value" class="text-sm text-slate-600 list-disc pl-4 space-y-1"></ul>
                  </div>
                </div>
              </div>
              <div class="insight-card">
                <div class="flex items-start gap-3">
                  <div class="improve-icon">⚠️</div>
                  <div class="flex-1">
                    <p class="font-bold text-sm mb-1">{tt("tool_video_weaknesses")}</p>
                    <ul id="result-weaknesses-value" class="text-sm text-slate-600 list-disc pl-4 space-y-1"></ul>
                  </div>
                </div>
              </div>
              <div class="insight-card">
                <div class="flex items-start gap-3">
                  <div class="improve-icon">🎯</div>
                  <div class="flex-1">
                    <p class="font-bold text-sm mb-1">{tt("tool_video_to_break_through")}</p>
                    <ul id="result-actions-value" class="text-sm text-slate-600 list-disc pl-4 space-y-1"></ul>
                  </div>
                </div>
              </div>
            </div>

            <div id="tab-stats" class="hidden">
              <div class="insight-card">
                <p class="font-semibold text-sm mb-2">{tt("results_viral_potential")}</p>
                <p id="stats-score-value" class="text-3xl font-extrabold text-blue-600 mb-1">—/100</p>
                <p id="stats-score-basis" class="text-xs text-slate-400"></p>
              </div>
              <div class="insight-card">
                <p class="font-semibold text-sm mb-3">{tt("results_categories_title")}</p>
                <div id="stats-categories" class="space-y-3"></div>
              </div>
              <div id="policy-card" class="insight-card hidden">
                <p class="font-bold text-sm mb-1">⚠️ {tt("results_policy_title")}</p>
                <ul id="policy-issues" class="text-sm text-slate-600 list-disc pl-4 space-y-1"></ul>
              </div>
              <div id="estimate-card" class="insight-card hidden">
                <p class="font-semibold text-sm mb-1">{tt("est_title")}</p>
                <p id="estimate-band" class="text-sm font-bold text-blue-600 mb-2"></p>
                <div id="estimate-numbers" class="grid grid-cols-3 gap-2 text-center mb-2"></div>
                <p id="estimate-basis" class="text-sm text-slate-600 mb-1"></p>
                <p id="estimate-disclaimer" class="text-xs text-slate-400"></p>
                <div id="feedback-block" class="mt-4 pt-4 border-t border-slate-100">
                  <p class="font-semibold text-sm mb-3">{tt("est_feedback_q")}</p>
                  <div id="feedback-buttons" class="flex gap-2">
                    <button type="button" onclick="sendFeedback('yes')" class="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-sm font-semibold text-slate-700 hover:border-blue-600 transition">{tt("est_feedback_yes")}</button>
                    <button type="button" onclick="sendFeedback('roughly')" class="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-sm font-semibold text-slate-700 hover:border-blue-600 transition">{tt("est_feedback_roughly")}</button>
                    <button type="button" onclick="sendFeedback('no')" class="flex-1 py-2.5 rounded-xl border-2 border-slate-200 text-sm font-semibold text-slate-700 hover:border-blue-600 transition">{tt("est_feedback_no")}</button>
                  </div>
                  <p id="feedback-message" class="text-sm mt-2"></p>
                </div>
              </div>
              <div class="insight-card">
                <p class="font-semibold text-sm mb-1">{tt("results_niche_label")}</p>
                <p id="stats-niche-value" class="text-sm text-slate-600"></p>
              </div>
            </div>
          </div>

        </div>

        <script>
{_onboarding_js_core(niche_category, account_avg_views, lang, "step-upload")}

          const LOADING_STAGES = ["{tt("loading_upload")}", "{tt("loading_watching")}", "{tt("loading_analyzing")}", "{tt("loading_insights")}"];
          const CAT_LABELS = {{
            hook: "{tt("cat_hook")}",
            visual_engagement: "{tt("cat_visual")}",
            storytelling: "{tt("cat_story")}",
            call_to_action: "{tt("cat_cta")}"
          }};
          const BAND_LABELS = {{
            well_below: "{tt("est_band_well_below")}",
            below: "{tt("est_band_below")}",
            around: "{tt("est_band_around")}",
            above: "{tt("est_band_above")}",
            well_above: "{tt("est_band_well_above")}"
          }};
          const EST_LABELS = {{ views: "{tt("est_views")}", likes: "{tt("est_likes")}", comments: "{tt("est_comments")}" }};
          let selectedFile = null;
          let thumbDataUrl = '';
          let alreadyPublished = null;
          let currentAnalysisId = null;

          function escapeHtml(text) {{
            return String(text == null ? '' : text).replace(/[&<>"']/g, function (c) {{
              return {{'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}}[c];
            }});
          }}

          function updateLaunchBtn() {{
            const btn = document.getElementById('upload-launch-btn');
            const ready = selectedFile && alreadyPublished !== null;
            btn.disabled = !ready;
            btn.className = ready
              ? 'w-full mt-4 py-3.5 rounded-xl bg-blue-600 text-white font-bold text-sm transition hover:bg-blue-700'
              : 'w-full mt-4 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition';
          }}

          function setPublished(value) {{
            alreadyPublished = value;
            const on = 'flex-1 py-3 rounded-xl border-2 border-blue-600 bg-blue-50 text-blue-700 font-semibold text-sm transition';
            const off = 'flex-1 py-3 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm transition';
            document.getElementById('published-yes-btn').className = value ? on : off;
            document.getElementById('published-no-btn').className = value ? off : on;
            updateLaunchBtn();
          }}

          function onVideoSelected(event) {{
            const file = event.target.files && event.target.files[0];
            if (!file) return;
            selectedFile = file;
            document.getElementById('upload-file-hint').textContent = file.name;

            const videoEl = document.createElement('video');
            videoEl.src = URL.createObjectURL(file);
            videoEl.muted = true;
            videoEl.addEventListener('loadeddata', function () {{
              videoEl.currentTime = Math.min(0.5, (videoEl.duration || 1) / 2);
            }});
            videoEl.addEventListener('seeked', function () {{
              const canvas = document.createElement('canvas');
              canvas.width = videoEl.videoWidth || 360;
              canvas.height = videoEl.videoHeight || 640;
              const ctx = canvas.getContext('2d');
              ctx.drawImage(videoEl, 0, 0, canvas.width, canvas.height);
              thumbDataUrl = canvas.toDataURL('image/jpeg', 0.85);
              document.getElementById('upload-thumb-preview').src = thumbDataUrl;
              document.getElementById('upload-thumb-preview').classList.remove('hidden');
              document.getElementById('upload-dropzone-empty').classList.add('hidden');
            }});

            updateLaunchBtn();
          }}

          function resetFlow() {{
            document.getElementById('upload-video-input').value = '';
            selectedFile = null;
            alreadyPublished = null;
            currentAnalysisId = null;
            document.getElementById('published-yes-btn').className = 'flex-1 py-3 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm transition';
            document.getElementById('published-no-btn').className = 'flex-1 py-3 rounded-xl border-2 border-slate-200 text-slate-600 font-semibold text-sm transition';
            document.getElementById('upload-thumb-preview').removeAttribute('src');
            document.getElementById('upload-thumb-preview').classList.add('hidden');
            document.getElementById('upload-dropzone-empty').classList.remove('hidden');
            document.getElementById('upload-file-hint').textContent = '';
            updateLaunchBtn();
            document.getElementById('upload-error').textContent = '';
            goToStep('step-upload', 100, true);
          }}

          function launchAnalysis() {{
            if (!selectedFile) return;
            document.getElementById('loading-thumb-preview').src = thumbDataUrl;
            document.getElementById('result-thumb-preview').src = thumbDataUrl;
            let stageIdx = 0;
            document.getElementById('loading-status-text').textContent = LOADING_STAGES[0];
            goToStep('step-loading', 100, false);
            const stageInterval = setInterval(function () {{
              stageIdx = Math.min(stageIdx + 1, LOADING_STAGES.length - 1);
              setLoadingText(LOADING_STAGES[stageIdx]);
            }}, 4000);

            const formData = new FormData();
            formData.append('file', selectedFile);
            formData.append('account_avg_views', accountAvgViewsFinal);
            formData.append('niche_category', selectedNiches[0] || '');
            formData.append('main_challenge', selectedChallenge);
            formData.append('ui_lang', uiLang);
            formData.append('already_published', alreadyPublished ? 'true' : 'false');

            fetch('/api/analyze-video-upload', {{ method: 'POST', body: formData }})
              .then(function (r) {{ return r.json().then(function (data) {{ return {{ok: r.ok, status: r.status, data: data}}; }}); }})
              .then(function (res) {{
                clearInterval(stageInterval);
                if (!res.ok) {{
                  const reason = (res.data && res.data.detail) ? res.data.detail : ('{tt("common_error_prefix")} ' + res.status);
                  document.getElementById('upload-error').textContent = reason;
                  goToStep('step-upload', 100, true);
                  return;
                }}
                setLoadingText('{tt("loading_done")}');
                renderResults(res.data);
                setTimeout(function () {{ goToStep('step-results', 100, false); }}, 500);
              }})
              .catch(function (e) {{
                clearInterval(stageInterval);
                document.getElementById('upload-error').textContent = '{tt("common_network_error")} ' + (e && e.message ? e.message : e);
                goToStep('step-upload', 100, true);
              }});
          }}

          function renderResults(data) {{
            const score = data.virality_score != null ? data.virality_score : 0;
            const color = scoreColor(score);
            animateNumber(document.getElementById('viral-score-value'), score, 900);
            document.getElementById('viral-score-value').style.color = color;
            document.getElementById('viral-score-bar').style.width = score + '%';
            document.getElementById('viral-score-bar').style.background = color;
            document.getElementById('score-basis-text').textContent = data.score_basis || '';
            animateNumber(document.getElementById('stats-score-value'), score, 900);
            document.getElementById('stats-score-value').style.color = color;
            document.getElementById('stats-score-basis').textContent = data.score_basis || '';

            document.getElementById('result-niche-value').textContent = data.niche || selectedNiches[0] || '—';
            document.getElementById('stats-niche-value').textContent = data.niche || selectedNiches[0] || '—';
            document.getElementById('result-hashtags-value').textContent = (data.suggested_hashtags || []).map(function (h) {{ return '#' + h; }}).join(' ');
            document.getElementById('result-caption-value').textContent = data.suggested_caption || '';

            document.getElementById('result-hook-value').textContent = (data.hook_excerpt ? ('"' + data.hook_excerpt + '" — ') : '') + (data.hook_type || '');
            document.getElementById('result-strengths-value').innerHTML = (data.strengths || []).map(function (s) {{ return '<li>' + s + '</li>'; }}).join('');
            document.getElementById('result-weaknesses-value').innerHTML = (data.weaknesses || []).map(function (s) {{ return '<li>' + s + '</li>'; }}).join('');
            document.getElementById('result-actions-value').innerHTML = (data.action_plan || []).map(function (s) {{ return '<li>' + s + '</li>'; }}).join('');

            saveHistoryEntry({{
              type: 'video', score: score, niche: data.niche || selectedNiches[0] || '',
              title: data.hook_excerpt || data.niche || selectedNiches[0] || '', ts: Date.now()
            }});

            const cats = data.category_scores || {{}};
            document.getElementById('stats-categories').innerHTML = Object.keys(CAT_LABELS).map(function (key) {{
              const c = cats[key] || {{score: 0, comment: ''}};
              return '<div><div class="flex items-center justify-between mb-1"><span class="text-sm font-medium">' + CAT_LABELS[key] +
                '</span><span class="text-sm font-extrabold" style="color:' + scoreColor(c.score) + '">' + c.score + '</span></div>' +
                '<div class="score-track"><div class="score-fill" style="width:' + c.score + '%;background:' + scoreColor(c.score) + '"></div></div>' +
                '<p class="text-xs text-slate-500 mt-1">' + escapeHtml(c.comment) + '</p></div>';
            }}).join('');

            const issues = (data.policy_check && data.policy_check.status === 'risk') ? (data.policy_check.issues || []) : [];
            document.getElementById('policy-card').classList.toggle('hidden', issues.length === 0);
            document.getElementById('policy-issues').innerHTML = issues.map(function (s) {{ return '<li>' + escapeHtml(s) + '</li>'; }}).join('');

            const est = data.estimate;
            currentAnalysisId = data.analysis_id || null;
            document.getElementById('estimate-card').classList.toggle('hidden', !est);
            if (est) {{
              const fmt = new Intl.NumberFormat(uiLang, {{notation: 'compact', maximumFractionDigits: 1}});
              document.getElementById('estimate-band').textContent = BAND_LABELS[est.band] || '';
              document.getElementById('estimate-numbers').innerHTML = est.views
                ? ['views', 'likes', 'comments'].map(function (k) {{
                    return '<div class="rounded-xl bg-slate-50 py-2"><p class="text-xs text-slate-500">' + EST_LABELS[k] + '</p>' +
                      '<p class="text-sm font-extrabold">' + fmt.format(est[k][0]) + ' – ' + fmt.format(est[k][1]) + '</p></div>';
                  }}).join('')
                : '<p class="col-span-3 text-xs text-slate-500">' + escapeHtml("{tt("est_no_avg")}") + '</p>';
              document.getElementById('estimate-basis').textContent = est.basis || '';
              document.getElementById('estimate-disclaimer').textContent = "{tt("est_disclaimer")}";
              document.getElementById('feedback-buttons').classList.remove('hidden');
              document.getElementById('feedback-message').textContent = '';
              document.getElementById('feedback-block').classList.toggle('hidden', !currentAnalysisId);
            }}
          }}

          function sendFeedback(verdict) {{
            if (!currentAnalysisId) return;
            const msg = document.getElementById('feedback-message');
            fetch('/api/video-estimate-feedback', {{
              method: 'POST',
              headers: {{'Content-Type': 'application/json'}},
              body: JSON.stringify({{analysis_id: currentAnalysisId, verdict: verdict}})
            }})
              .then(function (r) {{
                if (!r.ok) throw new Error('http ' + r.status);
                document.getElementById('feedback-buttons').classList.add('hidden');
                msg.className = 'text-sm mt-2 text-green-600';
                msg.textContent = "{tt("est_feedback_thanks")}";
              }})
              .catch(function () {{
                msg.className = 'text-sm mt-2 text-red-600';
                msg.textContent = "{tt("est_feedback_error")}";
              }});
          }}
        </script>
      </body>
    </html>
    """


@app.get("/tools/analyze-script", response_class=HTMLResponse)
def tool_analyze_script_page(request: Request):
    """
    Page dédiée pour l'analyse d'un script déjà écrit (avant tournage).
    Réutilise directement /api/analyze-transcript — la même route qui
    analyse le texte parlé d'une vidéo déjà tournée/postée — pour donner
    un score de viralité et un rapport cohérent avec celui des vidéos.

    Même onboarding complet que "Analyser la vidéo" (objectif -> défi ->
    niche -> audience -> provenance -> vues moyennes -> expérience ->
    configuration -> complétion), qui alimente ici `niche_category` et
    `main_challenge` envoyés à /api/analyze-transcript. Le résultat garde
    volontairement son propre format, plus riche qu'un simple score
    (accroche, rythme, structure, pourquoi ça marche ou pas) plutôt que
    d'être aligné de force sur celui des vidéos.
    """
    lang = _detect_ui_lang(request)
    tt = lambda key: t(lang, key)  # noqa: E731
    words_suffix = tt("tool_script_words_suffix")

    niche_buttons = "".join(
        f'''<button type="button" class="niche-btn" data-niche="{n}" onclick="toggleNiche('{n}', this)">
              <span class="text-lg">{NICHE_EMOJIS.get(n, "✨")}</span>
              <span>{n}</span>
            </button>'''
        for n in NICHE_CATEGORIES
    )

    return f"""
    <html lang="{lang}">
      <head>
        <title>{tt("tool_script_title")} — Wil App</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">{_ONBOARDING_HEAD_ASSETS}
        <style>{_ONBOARDING_STYLE}</style>
      </head>
      <body class="text-slate-900">{_ONBOARDING_MUTE_BUTTON_HTML}{_app_topbar_html(tt)}
        <div class="max-w-md mx-auto px-5 py-6">
{_onboarding_steps_html(tt, niche_buttons, "step-script")}

          <!-- ÉTAPE 10 : script -->
          <div id="step-script" class="step">
            <h1 class="text-xl font-extrabold mb-1">{tt("tool_script_title")}</h1>
            <p class="text-sm text-slate-500 mb-6">{tt("tool_script_subtitle")}</p>
            <textarea id="script-text" placeholder="{tt("tool_script_placeholder")}" rows="10"
                      class="w-full rounded-xl border-2 border-slate-200 p-3 text-sm focus:outline-none focus:border-blue-500"
                      oninput="updateScriptWordCount()"></textarea>
            <p id="script-word-count" class="text-xs text-slate-400 mt-2">0 / {MAX_TRANSCRIPT_WORDS} {words_suffix}</p>
            <button id="script-analyze-btn" disabled onclick="launchAnalysis()"
                    class="w-full mt-4 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition">
              {tt("tool_script_analyze_btn")}
            </button>
            <div id="script-error" class="text-center text-sm text-red-600 mt-3"></div>
          </div>

          <!-- ÉTAPE 11 : chargement -->
          <div id="step-loading" class="step text-center">
            <div class="dot-bounce mt-24"><span></span><span></span><span></span></div>
            <p id="loading-status-text" class="mt-8 font-semibold text-slate-700">{tt("loading_script_reading")}</p>
          </div>

          <!-- ÉTAPE 12 : résultat -->
          <div id="step-results" class="step">
            <div class="flex items-center justify-between mb-4">
              <span class="font-extrabold text-lg">Wil App</span>
              <button onclick="resetFlow()" class="text-xs font-semibold text-blue-600 hover:text-blue-700">{tt("tool_script_analyze_btn")}</button>
            </div>

            <h2 class="text-lg font-bold mb-4">{tt("results_smart_insights")}</h2>

            <div class="insight-card">
              <div class="flex items-center justify-between mb-2">
                <span class="font-semibold text-sm">{tt("tool_script_virality_estimated")}</span>
                <span id="script-score-value" class="font-extrabold text-blue-600">—/100</span>
              </div>
              <div class="score-track"><div id="script-score-bar" class="score-fill" style="width:0%"></div></div>
            </div>

            <div class="insight-card">
              <div class="flex items-start gap-3">
                <div class="improve-icon">🎬</div>
                <div class="flex-1">
                  <p class="font-bold text-sm mb-1">{tt("tool_script_hook")}</p>
                  <p id="script-hook-value" class="text-sm text-slate-600"></p>
                </div>
              </div>
            </div>

            <div class="insight-card">
              <div class="flex items-start gap-3">
                <div class="improve-icon">⏱️</div>
                <div class="flex-1">
                  <p class="font-bold text-sm mb-1">{tt("tool_script_rhythm")}</p>
                  <p id="script-rhythm-value" class="text-sm text-slate-600"></p>
                </div>
              </div>
            </div>

            <div class="insight-card">
              <div class="flex items-start gap-3">
                <div class="improve-icon">🧩</div>
                <div class="flex-1">
                  <p class="font-bold text-sm mb-1">{tt("tool_script_structure")}</p>
                  <ul id="script-structure-value" class="text-sm text-slate-600 list-disc pl-4 space-y-1"></ul>
                </div>
              </div>
            </div>

            <div class="insight-card">
              <div class="flex items-start gap-3">
                <div class="improve-icon">✅</div>
                <div class="flex-1">
                  <p class="font-bold text-sm mb-1">{tt("dash_strengths")}</p>
                  <ul id="script-strengths-value" class="text-sm text-slate-600 list-disc pl-4 space-y-1"></ul>
                </div>
              </div>
            </div>

            <div class="insight-card">
              <div class="flex items-start gap-3">
                <div class="improve-icon">⚠️</div>
                <div class="flex-1">
                  <p class="font-bold text-sm mb-1">{tt("tool_script_to_fix")}</p>
                  <ul id="script-weaknesses-value" class="text-sm text-slate-600 list-disc pl-4 space-y-1"></ul>
                </div>
              </div>
            </div>

            <div class="insight-card">
              <div class="flex items-start gap-3">
                <div class="improve-icon">🎯</div>
                <div class="flex-1">
                  <p class="font-bold text-sm mb-1">{tt("tool_script_why")}</p>
                  <p id="script-why-value" class="text-sm text-slate-600"></p>
                </div>
              </div>
            </div>
          </div>

        </div>

        <script>
{_onboarding_js_core("", "", lang, "step-script")}

          const MAX_SCRIPT_WORDS = {MAX_TRANSCRIPT_WORDS};
          const LOADING_STAGES = ["{tt("loading_script_reading")}", "{tt("loading_script_analyzing")}", "{tt("loading_insights")}"];

          function countWords(text) {{
            const trimmed = text.trim();
            return trimmed ? trimmed.split(/\\s+/).length : 0;
          }}

          function updateScriptWordCount() {{
            const text = document.getElementById('script-text').value;
            const count = countWords(text);
            const counter = document.getElementById('script-word-count');
            counter.textContent = count + ' / ' + MAX_SCRIPT_WORDS + ' {words_suffix}';
            counter.className = count > MAX_SCRIPT_WORDS ? 'text-xs text-red-600 mt-2' : 'text-xs text-slate-400 mt-2';
            const valid = count > 0 && count <= MAX_SCRIPT_WORDS;
            const btn = document.getElementById('script-analyze-btn');
            btn.disabled = !valid;
            btn.className = valid
              ? 'w-full mt-4 py-3.5 rounded-xl bg-blue-600 text-white font-bold text-sm transition hover:bg-blue-700'
              : 'w-full mt-4 py-3.5 rounded-xl bg-slate-200 text-slate-400 font-bold text-sm transition';
          }}

          function resetFlow() {{
            document.getElementById('script-text').value = '';
            updateScriptWordCount();
            document.getElementById('script-error').textContent = '';
            goToStep('step-script', 100, true);
          }}

          function launchAnalysis() {{
            const transcript = document.getElementById('script-text').value.trim();
            if (!transcript) return;

            let stageIdx = 0;
            document.getElementById('loading-status-text').textContent = LOADING_STAGES[0];
            goToStep('step-loading', 100, false);
            const stageInterval = setInterval(function () {{
              stageIdx = Math.min(stageIdx + 1, LOADING_STAGES.length - 1);
              setLoadingText(LOADING_STAGES[stageIdx]);
            }}, 3000);

            const params = new URLSearchParams({{
              transcript: transcript,
              niche_category: selectedNiches[0] || '',
              main_challenge: selectedChallenge,
              ui_lang: uiLang
            }});

            fetch('/api/analyze-transcript?' + params.toString())
              .then(function (r) {{ return r.json().then(function (data) {{ return {{ok: r.ok, status: r.status, data: data}}; }}); }})
              .then(function (res) {{
                clearInterval(stageInterval);
                if (!res.ok) {{
                  const reason = (res.data && res.data.detail) ? res.data.detail : ('{tt("common_error_prefix")} ' + res.status);
                  document.getElementById('script-error').textContent = reason;
                  goToStep('step-script', 100, true);
                  return;
                }}
                setLoadingText('{tt("loading_done")}');
                renderScriptResults(res.data);
                setTimeout(function () {{ goToStep('step-results', 100, false); }}, 500);
              }})
              .catch(function (e) {{
                clearInterval(stageInterval);
                document.getElementById('script-error').textContent = '{tt("common_network_error")} ' + (e && e.message ? e.message : e);
                goToStep('step-script', 100, true);
              }});
          }}

          function renderScriptResults(data) {{
            const score = data.virality_score != null ? data.virality_score : 0;
            const color = scoreColor(score);
            animateNumber(document.getElementById('script-score-value'), score, 900);
            document.getElementById('script-score-value').style.color = color;
            document.getElementById('script-score-bar').style.width = score + '%';
            document.getElementById('script-score-bar').style.background = color;

            document.getElementById('script-hook-value').textContent = data.hook_analysis || '';
            document.getElementById('script-rhythm-value').textContent = data.rhythm_analysis || '';
            document.getElementById('script-structure-value').innerHTML = (data.structure_breakdown || []).map(function (s) {{ return '<li>' + s + '</li>'; }}).join('');
            document.getElementById('script-strengths-value').innerHTML = (data.strengths || []).map(function (s) {{ return '<li>' + s + '</li>'; }}).join('');
            document.getElementById('script-weaknesses-value').innerHTML = (data.weaknesses || []).map(function (s) {{ return '<li>' + s + '</li>'; }}).join('');
            document.getElementById('script-why-value').textContent = data.why_it_worked_or_not || '';

            saveHistoryEntry({{
              type: 'script', score: score, niche: selectedNiches[0] || '',
              title: document.getElementById('script-text').value.trim().slice(0, 70), ts: Date.now()
            }});
          }}
        </script>
      </body>
    </html>
    """


@app.get("/tools/trending-ideas", response_class=HTMLResponse)
def tool_trending_ideas_page(request: Request, niche_category: str = "", lang: str = "fr"):
    """
    Page dédiée aux idées de vidéos et accroches tendance pour la niche du
    compte. Lance la recherche automatiquement au chargement (le contexte
    niche_category/lang arrive déjà dans l'URL, pas besoin d'un clic de plus).
    """
    ui_lang = _detect_ui_lang(request)
    tt = lambda key: t(ui_lang, key)  # noqa: E731
    return f"""
    <html lang="{ui_lang}">
      <head>
        <title>{tt("tool_trending_title")} — Wil App</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>{_TOOL_PAGE_STYLE}</style>
      </head>
      <body>
        <div class="wrap">
          <a href="/" class="back">{tt("back_home")}</a>
          <h1>{tt("tool_trending_title")}</h1>
          <p class="subtitle">{tt("tool_trending_subtitle")}</p>
          <div class="card" id="trending-result">
            <p class="loading">⏳ {tt("tool_trending_searching")}</p>
          </div>
        </div>
        <script>
          const nicheCategory = "{niche_category}";
          const lang = "{lang}";
          const result = document.getElementById('trending-result');

          if (!nicheCategory) {{
            result.innerHTML = '<p class="loading">{tt("tool_trending_no_niche")}</p>';
          }} else {{
            fetch(`/api/trending-ideas?niche_category=${{encodeURIComponent(nicheCategory)}}&lang=${{encodeURIComponent(lang)}}`)
              .then(r => r.json().then(data => ({{ok: r.ok, status: r.status, data}})))
              .then(({{ok, status, data}}) => {{
                if (!ok) {{
                  const reason = (data && data.detail) ? data.detail : `{tt("common_error_prefix")} ${{status}}`;
                  result.innerHTML = `<p style="color:#c0392b;">${{reason}}</p>`;
                  return;
                }}
                const ideas = (data.video_ideas || []).map(i => `<li>${{i}}</li>`).join('');
                const hooks = (data.trending_hooks || []).map(h => `<li>${{h}}</li>`).join('');
                result.innerHTML = `
                  <p><strong>💡 {tt("tool_trending_ideas_label")}</strong></p>
                  <ul class="bullets">${{ideas}}</ul>
                  <p><strong>🎬 {tt("tool_trending_hooks_label")}</strong></p>
                  <ul class="bullets">${{hooks}}</ul>`;
              }})
              .catch((e) => {{
                result.innerHTML = `<p style="color:#c0392b;">{tt("common_network_error")} ${{e && e.message ? e.message : e}}</p>`;
              }});
          }}
        </script>
      </body>
    </html>
    """


def _js_json(value) -> str:
    """
    Sérialise une valeur Python en littéral JSON sûr à insérer dans un bloc
    <script> : échappe <, > et & pour qu'aucune donnée (nom TikTok, texte
    traduit...) ne puisse refermer la balise ou injecter du HTML.
    """
    return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


_ONBOARDING_NEXT_RE = re.compile(r"/app(\?open=(video|script|account))?")


@app.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request, next: str = ""):
    """
    Onboarding autonome, juste après la landing page : mêmes 7 questions
    que celles des outils, mais réponses mémorisées (localStorage) puis
    redirection vers /app. L'utilisateur ne le refait plus ensuite :
    /app et les pages d'outils sautent directement au contenu quand les
    réponses existent. `next` n'accepte que /app ou /app?open=<outil>
    (jamais une URL externe).
    """
    lang = _detect_ui_lang(request)
    tt = lambda key: t(lang, key)  # noqa: E731
    next_url = next if _ONBOARDING_NEXT_RE.fullmatch(next) else "/app"

    niche_buttons = "".join(
        f'''<button type="button" class="niche-btn" data-niche="{n}" onclick="toggleNiche('{n}', this)">
              <span class="text-lg">{NICHE_EMOJIS.get(n, "✨")}</span>
              <span>{n}</span>
            </button>'''
        for n in NICHE_CATEGORIES
    )

    return f"""
    <html lang="{lang}">
      <head>
        <title>Wil App</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">{_ONBOARDING_HEAD_ASSETS}
        <style>{_ONBOARDING_STYLE}</style>
      </head>
      <body class="text-slate-900">{_ONBOARDING_MUTE_BUTTON_HTML}
        <div class="max-w-md mx-auto px-5 py-6">
{_onboarding_steps_html(tt, niche_buttons, "step-none", complete_onclick="finishOnboarding()")}
        </div>

        <script>
{_onboarding_js_core("", "", lang, "step-none", allow_skip=False)}

          function finishOnboarding() {{
            saveOnboarding();
            window.location.href = {_js_json(next_url)};
          }}
        </script>
      </body>
    </html>
    """


_APP_SHELL_HTML = """<!DOCTYPE html>
<html lang="__LANG__">
<head>
  <meta charset="utf-8">
  <title>Wil App</title>
  <link rel="icon" type="image/x-icon" href="/favicon.ico">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <script>
    // Pas d'onboarding mémorisé -> on y va d'abord (puis retour ici).
    (function () {
      try {
        var stored = JSON.parse(localStorage.getItem('wilOnboarding') || 'null');
        var done = stored && stored.niches && stored.niches.length > 0;
        var open = new URLSearchParams(location.search).get('open');
        var tools = { video: '/tools/analyze-video', script: '/tools/analyze-script', account: '/tools/analyze-account' };
        if (!done) {
          location.replace('/onboarding' + (tools[open] ? '?next=' + encodeURIComponent('/app?open=' + open) : ''));
        } else if (tools[open]) {
          location.replace(tools[open]);
        }
      } catch (e) {}
    })();
  </script>
  __HEAD_ASSETS__
  <style>
    body { font-family: 'Inter', system-ui, sans-serif; background: #F8FAFC; -webkit-tap-highlight-color: transparent; }
    .tool-card { display: flex; align-items: center; gap: 14px; padding: 16px; background: #fff; border: 1.5px solid #E2E8F0; border-radius: 20px; margin-bottom: 12px; text-decoration: none; color: inherit; transition: transform 0.1s ease, border-color 0.15s ease; }
    .tool-card:active { transform: scale(0.98); }
    .tool-card:hover { border-color: #93C5FD; }
    .tool-icon { width: 48px; height: 48px; border-radius: 14px; background: #EFF6FF; display: flex; align-items: center; justify-content: center; font-size: 22px; flex-shrink: 0; }
    .history-item { background: #fff; border: 1.5px solid #E2E8F0; border-radius: 20px; padding: 16px 18px; margin-bottom: 10px; }
    .idea-card { background: #fff; border: 1.5px solid #E2E8F0; border-radius: 20px; padding: 18px; margin-bottom: 12px; }
    .badge { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border-radius: 999px; font-size: 12px; font-weight: 700; }
    .badge-trend { background: #E0F2FE; color: #0369A1; }
    .badge-niche { background: #F1F5F9; color: #64748B; }
    .chip { display: inline-block; padding: 6px 12px; border-radius: 999px; background: #EFF6FF; color: #1D4ED8; font-size: 12px; font-weight: 600; margin: 0 6px 6px 0; }
    .niche-pill { padding: 8px 14px; border-radius: 999px; border: 2px solid #E2E8F0; background: #fff; font-size: 13px; font-weight: 600; color: #334155; white-space: nowrap; cursor: pointer; }
    .niche-pill.active { background: #2563EB; border-color: #2563EB; color: #fff; }
    .nav-item { color: #6B7280; font-size: 11.5px; font-weight: 500; border-radius: 14px; margin: 8px 3px; transition: background 0.15s ease, color 0.15s ease; }
    .nav-item:hover { background: #F8FAFC; }
    .nav-item.active { color: #2563EB; font-weight: 700; background: #EFF6FF; }
    .nav-item svg { width: 24px; height: 24px; }
    __NAV_CSS__
    .app-tab { animation: tabIn 0.25s ease; }
    @keyframes tabIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
    .row { display: flex; justify-content: space-between; gap: 12px; padding: 12px 0; border-bottom: 1px solid #F1F5F9; font-size: 14px; }
    .row:last-child { border-bottom: none; }
  </style>
</head>
<body class="text-slate-900 nav-visible">
  <div class="max-w-md mx-auto px-5 pt-6 pb-10">

    <!-- ACCUEIL -->
    <section id="tab-home" class="app-tab">
      <div class="flex items-center gap-2 mb-6">
        <div class="w-9 h-9 rounded-full bg-gradient-to-br from-blue-600 to-sky-400 flex items-center justify-center text-white font-bold text-sm">W</div>
        <span class="font-extrabold text-lg">Wil App</span>
      </div>
      <h1 class="text-2xl font-extrabold">__T_app_welcome__</h1>
      <p class="text-sm text-slate-500 mt-1 mb-5">__T_app_home_subtitle__</p>

      <a class="tool-card" href="/tools/analyze-video">
        <div class="tool-icon">🎬</div>
        <div class="flex-1"><p class="font-bold">__T_app_tool_video_title__</p><p class="text-sm text-slate-500 leading-snug">__T_app_tool_video_desc__</p></div>
        <span class="text-slate-400">›</span>
      </a>
      <a class="tool-card" href="/tools/analyze-script">
        <div class="tool-icon">📝</div>
        <div class="flex-1"><p class="font-bold">__T_app_tool_script_title__</p><p class="text-sm text-slate-500 leading-snug">__T_app_tool_script_desc__</p></div>
        <span class="text-slate-400">›</span>
      </a>
      <a class="tool-card" href="/tools/analyze-account">
        <div class="tool-icon">🔗</div>
        <div class="flex-1"><p class="font-bold">__T_app_tool_account_title__</p><p class="text-sm text-slate-500 leading-snug">__T_app_tool_account_desc__</p></div>
        <span class="text-slate-400">›</span>
      </a>

      <div class="flex items-center justify-between mt-8 mb-3">
        <h2 class="text-xl font-extrabold">__T_app_history_title__</h2>
        <button type="button" onclick="showTab('library')" class="text-sm font-semibold text-blue-600">__T_app_see_all__ ›</button>
      </div>
      <div id="home-history"></div>
    </section>

    <!-- BIBLIOTHÈQUE -->
    <section id="tab-library" class="app-tab hidden">
      <h1 class="text-2xl font-extrabold mb-5">__T_app_tab_library__</h1>
      <div id="library-list"></div>
    </section>

    <!-- DÉCOUVRIR -->
    <section id="tab-discover" class="app-tab hidden">
      <h1 class="text-2xl font-extrabold">__T_app_tab_discover__</h1>
      <p class="text-sm text-slate-500 mt-1 mb-4">__T_app_discover_subtitle__</p>
      <div id="discover-niches" class="flex gap-2 overflow-x-auto pb-3 mb-2"></div>
      <div id="discover-content"></div>
    </section>

    <!-- PROFIL -->
    <section id="tab-profile" class="app-tab hidden">
      <h1 class="text-2xl font-extrabold mb-5">__T_app_tab_profile__</h1>
      <div id="profile-content"></div>
    </section>

  </div>

  <nav id="app-topbar">
    <div class="max-w-md mx-auto flex px-2">
      <button type="button" data-tab="home" onclick="showTab('home')" class="nav-item flex-1 flex flex-col items-center justify-center gap-0.5 py-2">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11.5L12 4l9 7.5"/><path d="M5.5 10v10h13V10"/><path d="M10 20v-5h4v5"/></svg>
        <span>__T_app_tab_home__</span>
      </button>
      <button type="button" data-tab="library" onclick="showTab('library')" class="nav-item flex-1 flex flex-col items-center justify-center gap-0.5 py-2">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect x="3.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.8"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.8"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.8"/></svg>
        <span>__T_app_tab_library__</span>
      </button>
      <button type="button" data-tab="discover" onclick="showTab('discover')" class="nav-item flex-1 flex flex-col items-center justify-center gap-0.5 py-2">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M15.6 8.4l-2 5.2-5.2 2 2-5.2z"/></svg>
        <span>__T_app_tab_discover__</span>
      </button>
      <button type="button" data-tab="profile" onclick="showTab('profile')" class="nav-item flex-1 flex flex-col items-center justify-center gap-0.5 py-2">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c0-4 3.4-6 7.5-6s7.5 2 7.5 6"/></svg>
        <span>__T_app_tab_profile__</span>
      </button>
    </div>
  </nav>

  <script>
    const I18N = __I18N__;
    const LANG = __LANG_JS__;
    const TABS = ['home', 'library', 'discover', 'profile'];

    function esc(text) {
      return String(text == null ? '' : text).replace(/[&<>"']/g, function (c) {
        return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c];
      });
    }
    function readJson(key, fallback) {
      try { return JSON.parse(localStorage.getItem(key) || 'null') || fallback; } catch (e) { return fallback; }
    }
    function scoreColor(score) {
      if (score <= 40) return '#DC2626';
      if (score <= 60) return '#F59E0B';
      if (score <= 80) return '#F97316';
      return '#2563EB';
    }

    const onboarding = readJson('wilOnboarding', {});
    const niches = onboarding.niches || [];

    function historyItemHtml(entry) {
      const typeLabel = entry.type === 'script' ? I18N.script : I18N.video;
      const date = entry.ts ? new Date(entry.ts).toLocaleDateString(LANG) : '';
      return '<div class="history-item"><p class="font-bold text-base truncate">' + esc(entry.title || entry.niche || typeLabel) + '</p>' +
        '<p class="text-sm mt-1"><span style="color:' + scoreColor(entry.score) + ';font-weight:700;">' + esc(entry.score) + I18N.scoreSuffix + '</span>' +
        '<span class="text-slate-400"> · ' + esc(typeLabel) + (date ? ' · ' + esc(date) : '') + '</span></p></div>';
    }

    function renderHistory() {
      const history = readJson('wilHistory', []);
      const home = document.getElementById('home-history');
      home.innerHTML = history.length
        ? history.slice(0, 3).map(historyItemHtml).join('')
        : '<p class="text-sm text-slate-500">' + esc(I18N.historyEmpty) + '</p>';

      const library = document.getElementById('library-list');
      library.innerHTML = history.length
        ? history.map(historyItemHtml).join('')
        : '<div class="text-center py-16"><div class="w-20 h-20 mx-auto rounded-full bg-blue-50 flex items-center justify-center text-3xl mb-5">🗂️</div>' +
          '<p class="font-extrabold text-lg mb-2">' + esc(I18N.libraryEmptyTitle) + '</p>' +
          '<p class="text-sm text-slate-500 leading-relaxed px-6">' + esc(I18N.libraryEmptyDesc) + '</p></div>';
    }

    let discoverNiche = niches[0] || '';
    const discoverCache = {};

    function renderDiscoverNiches() {
      const wrap = document.getElementById('discover-niches');
      wrap.innerHTML = niches.length > 1
        ? niches.map(function (n, i) {
            return '<button type="button" class="niche-pill' + (n === discoverNiche ? ' active' : '') + '" data-i="' + i + '">' + esc(n) + '</button>';
          }).join('')
        : '';
      wrap.querySelectorAll('.niche-pill').forEach(function (b) {
        b.addEventListener('click', function () { discoverNiche = niches[Number(b.dataset.i)]; renderDiscoverNiches(); loadDiscover(); });
      });
    }

    function ideasHtml(data) {
      const card = function (text, badge) {
        return '<div class="idea-card"><div class="flex items-center justify-between mb-3"><span class="badge badge-trend">🔥 ' + esc(badge) +
          '</span><span class="badge badge-niche">' + esc(discoverNiche) + '</span></div><p class="font-semibold leading-snug">' + esc(text) + '</p></div>';
      };
      return (data.video_ideas || []).map(function (i) { return card(i, I18N.ideasLabel); }).join('') +
        (data.trending_hooks || []).map(function (h) { return card(h, I18N.hooksLabel); }).join('');
    }

    function loadDiscover() {
      const box = document.getElementById('discover-content');
      if (!discoverNiche) { box.innerHTML = '<p class="text-sm text-slate-500">' + esc(I18N.discoverNoNiche) + '</p>'; return; }
      if (discoverCache[discoverNiche]) { box.innerHTML = ideasHtml(discoverCache[discoverNiche]); return; }
      const requested = discoverNiche;
      box.innerHTML = '<p class="text-sm text-slate-500">⏳ ' + esc(I18N.searching) + '</p>';
      fetch('/api/trending-ideas?niche_category=' + encodeURIComponent(requested) + '&lang=' + encodeURIComponent(LANG))
        .then(function (r) { return r.json().then(function (data) { return {ok: r.ok, status: r.status, data: data}; }); })
        .then(function (res) {
          if (requested !== discoverNiche) return;
          if (!res.ok) {
            box.innerHTML = '<p class="text-sm text-red-600">' + esc((res.data && res.data.detail) || (I18N.errorPrefix + ' ' + res.status)) + '</p>';
            return;
          }
          discoverCache[requested] = res.data;
          box.innerHTML = ideasHtml(res.data);
        })
        .catch(function (e) {
          if (requested === discoverNiche) box.innerHTML = '<p class="text-sm text-red-600">' + esc(I18N.networkError + ' ' + (e && e.message ? e.message : e)) + '</p>';
        });
    }

    function renderProfile() {
      const tiktok = readJson('wilTikTok', null);
      const account = tiktok
        ? '<div class="history-item text-center"><img src="' + esc(tiktok.avatar_url) + '" alt="" class="w-24 h-24 rounded-full object-cover mx-auto mb-3" onerror="this.style.display=\\'none\\'">' +
          '<p class="font-extrabold text-lg">' + esc(tiktok.display_name) + (tiktok.is_verified ? ' <span style="color:#0EA5E9">✔</span>' : '') + '</p>' +
          '<p class="text-sm text-slate-500">@' + esc(tiktok.username) + '</p>' +
          '<p class="text-xs font-semibold text-green-600 mt-2">✅ ' + esc(I18N.profileConnected) + '</p></div>'
        : '<div class="history-item text-center"><div class="w-20 h-20 mx-auto rounded-full bg-blue-50 flex items-center justify-center text-3xl mb-3">👤</div>' +
          '<p class="font-extrabold text-lg">' + esc(I18N.profileNotConnected) + '</p>' +
          '<p class="text-sm text-slate-500 mt-1 mb-4">' + esc(I18N.profileNotConnectedDesc) + '</p>' +
          '<a href="/tools/analyze-account" class="block w-full py-3.5 rounded-xl bg-slate-900 text-white font-bold text-sm">' + esc(I18N.profileConnectBtn) + '</a></div>';

      const nicheChips = niches.length
        ? '<p class="font-extrabold mt-6 mb-2">' + esc(I18N.profileThemes) + '</p><div>' + niches.map(function (n) { return '<span class="chip">' + esc(n) + '</span>'; }).join('') + '</div>'
        : '';
      const rows = [];
      if (onboarding.goal && I18N.goals[onboarding.goal]) rows.push('<div class="row"><span class="text-slate-500">' + esc(I18N.profileGoal) + '</span><span class="font-semibold text-right">' + esc(I18N.goals[onboarding.goal]) + '</span></div>');
      if (onboarding.challenge && I18N.challenges[onboarding.challenge]) rows.push('<div class="row"><span class="text-slate-500">' + esc(I18N.profileChallenge) + '</span><span class="font-semibold text-right">' + esc(I18N.challenges[onboarding.challenge]) + '</span></div>');
      const summary = rows.length ? '<div class="history-item mt-4">' + rows.join('') + '</div>' : '';

      document.getElementById('profile-content').innerHTML = account + nicheChips + summary +
        '<a href="/onboarding" class="tool-card mt-6"><div class="tool-icon">🔄</div><div class="flex-1 font-bold">' + esc(I18N.profileRedo) + '</div><span class="text-slate-400">›</span></a>';
    }

    let discoverLoaded = false;
    function showTab(name) {
      if (TABS.indexOf(name) === -1) name = 'home';
      TABS.forEach(function (t) {
        document.getElementById('tab-' + t).classList.toggle('hidden', t !== name);
      });
      document.querySelectorAll('.nav-item').forEach(function (b) { b.classList.toggle('active', b.dataset.tab === name); });
      if (name === 'discover' && !discoverLoaded) { discoverLoaded = true; renderDiscoverNiches(); loadDiscover(); }
      try { history.replaceState(null, '', '#' + name); } catch (e) {}
      window.scrollTo(0, 0);
    }

    renderHistory();
    renderProfile();
    showTab(location.hash.replace('#', '') || 'home');
  </script>
</body>
</html>
"""


@app.get("/app", response_class=HTMLResponse)
def app_shell_page(request: Request):
    """
    Application web après l'onboarding : 4 onglets (Accueil, Bibliothèque,
    Découvrir, Profil) avec une barre de navigation en bas. Tout l'état
    vient de localStorage : réponses de l'onboarding ("wilOnboarding"),
    historique des analyses ("wilHistory", alimenté par les pages
    d'analyse vidéo/script) et profil TikTok ("wilTikTok", écrit au
    retour de connexion). Sans onboarding mémorisé, la page redirige vers
    /onboarding avant même de s'afficher.
    """
    lang = _detect_ui_lang(request)
    tt = lambda key: t(lang, key)  # noqa: E731

    i18n = {
        "video": tt("app_tool_video_title"),
        "script": tt("app_tool_script_title"),
        "scoreSuffix": tt("app_score_suffix"),
        "historyEmpty": tt("app_history_empty"),
        "libraryEmptyTitle": tt("app_library_empty_title"),
        "libraryEmptyDesc": tt("app_library_empty_desc"),
        "discoverNoNiche": tt("app_discover_no_niche"),
        "ideasLabel": tt("tool_trending_ideas_label"),
        "hooksLabel": tt("tool_trending_hooks_label"),
        "searching": tt("tool_trending_searching"),
        "errorPrefix": tt("common_error_prefix"),
        "networkError": tt("common_network_error"),
        "profileConnected": tt("app_profile_connected"),
        "profileNotConnected": tt("app_profile_not_connected"),
        "profileNotConnectedDesc": tt("app_profile_not_connected_desc"),
        "profileConnectBtn": tt("app_profile_connect_btn"),
        "profileThemes": tt("app_profile_themes"),
        "profileGoal": tt("app_profile_goal"),
        "profileChallenge": tt("app_profile_challenge"),
        "profileRedo": tt("app_profile_redo"),
        "goals": {
            "views": tt("onboarding_goal_views"),
            "engagement": tt("onboarding_goal_engagement"),
            "fanbase": tt("onboarding_goal_fanbase"),
            "collabs": tt("onboarding_goal_collabs"),
            "other": tt("onboarding_goal_other"),
        },
        "challenges": {
            "followers": tt("onboarding_challenge_followers_title"),
            "engagement": tt("onboarding_challenge_engagement_title"),
            "reach": tt("onboarding_challenge_reach_title"),
        },
    }

    html = (
        _APP_SHELL_HTML.replace("__HEAD_ASSETS__", _ONBOARDING_HEAD_ASSETS)
        .replace("__NAV_CSS__", _NAV_POSITION_CSS)
        .replace("__I18N__", _js_json(i18n))
        .replace("__LANG_JS__", _js_json(lang))
        .replace("__LANG__", lang)
    )
    for key in (
        "app_welcome", "app_home_subtitle", "app_tool_video_title", "app_tool_video_desc",
        "app_tool_script_title", "app_tool_script_desc", "app_tool_account_title",
        "app_tool_account_desc", "app_history_title", "app_see_all", "app_tab_home",
        "app_tab_library", "app_tab_discover", "app_tab_profile", "app_discover_subtitle",
    ):
        html = html.replace(f"__T_{key}__", tt(key))
    return html


_LEGAL_STYLE = """
  body { font-family: -apple-system, Arial, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #222; }
  h1 { font-size: 28px; }
  h2 { font-size: 20px; margin-top: 32px; }
  footer { margin-top: 60px; color: #777; font-size: 14px; }
  a { color: #0645AD; }
"""


@app.get("/terms", response_class=HTMLResponse)
def terms_of_service():
    """
    Page des Terms of Service (tout regroupé dans un seul document, y
    compris les futures conditions de vente du plan Pro, plutôt que des
    CGU/CGV séparées — choix explicite de l'utilisateur), hébergée
    directement sur ce domaine. Rédigée en français, sur mesure pour le
    fonctionnement réel de Wil App (connexion TikTok OAuth, analyses IA
    de compte/vidéo/script, upload volontaire jamais scraping — voir la
    politique déjà établie pour /api/analyze-transcript). Volontairement
    non traduite pour l'instant (contrairement au reste de l'app) : une
    traduction juridique demande une rigueur et une relecture
    différentes d'une traduction d'interface.
    """
    return f"""
    <html lang="fr">
    <head>
      <title>Terms of Service — Wil App</title>
      <link rel="icon" type="image/x-icon" href="/favicon.ico">
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <style>{_LEGAL_STYLE}</style>
    </head>
    <body>
    <p><a href="/">← Retour à l'accueil</a></p>
    <h1>Terms of Service</h1>
    <p><em>Dernière mise à jour : septembre 2026</em></p>

    <p>Les présentes Terms of Service (« Conditions ») régissent l'accès et l'utilisation de l'application Wil App (le « Service »), accessible à l'adresse wilapp.tech. En utilisant le Service, vous acceptez sans réserve les présentes Conditions. Elles couvrent aussi bien les règles d'usage du Service que, le cas échéant, les conditions applicables à l'offre payante Pro.</p>

    <h2>1. Objet et description du service</h2>
    <p>Wil App est un outil d'analyse propulsé par l'intelligence artificielle destiné aux créateurs de contenu TikTok. Le Service permet notamment de :</p>
    <ul>
      <li>connecter son compte TikTok pour obtenir un diagnostic automatique (score de viralité, taux d'engagement, points forts, points à améliorer, hashtags suggérés) ;</li>
      <li>analyser une vidéo (déjà publiée ou non) importée manuellement par l'utilisateur, avec transcription du contenu parlé ;</li>
      <li>analyser le script d'une vidéo pas encore tournée.</li>
    </ul>
    <p>Les rapports sont générés par un modèle d'intelligence artificielle (Claude, développé par Anthropic) à partir des données que vous fournissez ou des données réellement récupérées via l'API officielle de TikTok.</p>

    <h2>2. Connexion et accès au compte</h2>
    <p>L'accès aux fonctionnalités liées à l'analyse de compte nécessite une connexion via le Login Kit officiel de TikTok (protocole OAuth). Wil App n'a et ne demande jamais accès à votre mot de passe TikTok. Vous pouvez révoquer l'autorisation donnée à Wil App à tout moment depuis les paramètres de connexions tierces de votre compte TikTok.</p>

    <h2>3. Contenu importé par l'utilisateur</h2>
    <p>Lorsque vous importez un fichier vidéo ou un texte de script pour analyse, vous garantissez :</p>
    <ul>
      <li>être titulaire des droits sur ce contenu, ou disposer des autorisations nécessaires pour l'utiliser (y compris pour le contenu d'un autre créateur, à condition de l'avoir obtenu légalement — jamais par extraction automatisée depuis un simple lien) ;</li>
      <li>que ce contenu ne viole aucune loi, aucun droit de tiers, ni les règles de la communauté TikTok.</li>
    </ul>
    <p>Wil App ne collecte, ne télécharge et ne scrape aucune vidéo directement depuis TikTok à l'insu de l'utilisateur : chaque fichier ou texte analysé est fourni volontairement par vous.</p>

    <h2>4. Usage autorisé</h2>
    <p>Vous vous engagez à utiliser le Service à des fins strictement personnelles et légales, et à ne pas :</p>
    <ul>
      <li>tenter de contourner les limites techniques du Service (par exemple la limite de mots pour l'analyse de script) ;</li>
      <li>utiliser le Service à des fins d'ingénierie inverse, de revente, ou d'extraction automatisée massive des rapports générés ;</li>
      <li>utiliser le Service pour analyser du contenu que vous n'avez pas le droit d'utiliser.</li>
    </ul>

    <h2>5. Offres et tarifs</h2>
    <p>Le Service propose actuellement une offre gratuite (« Free ») donnant accès à la connexion du compte et à un aperçu de profil de base. Une offre payante (« Pro »), avec des analyses avancées et un support prioritaire, sera proposée ultérieurement ; ses conditions tarifaires seront communiquées avant sa mise en disponibilité.</p>

    <h2>6. Nature des analyses fournies</h2>
    <p>Les scores, diagnostics et conseils fournis par Wil App sont générés automatiquement par une intelligence artificielle à partir des données disponibles. Ils constituent une aide à la décision et ne garantissent en aucun cas un résultat (augmentation de vues, d'abonnés ou de revenus). Wil App ne peut être tenu responsable des décisions prises sur la base de ces analyses.</p>

    <h2>7. Propriété intellectuelle</h2>
    <p>L'application, sa marque, son design et son code restent la propriété exclusive de Wil App. Les rapports générés pour votre compte vous sont fournis pour votre usage personnel ; vous en conservez le contenu, sans que cela ne vous transfère de droit sur la plateforme elle-même.</p>

    <h2>8. Disponibilité et évolution du service</h2>
    <p>Wil App est un projet en développement actif. Certaines fonctionnalités peuvent être ajoutées, modifiées ou temporairement retirées sans préavis. Nous nous efforçons d'assurer la continuité du Service mais ne garantissons pas une disponibilité ininterrompue.</p>

    <h2>9. Limitation de responsabilité</h2>
    <p>Le Service est fourni « en l'état ». Wil App n'est ni affilié, ni sponsorisé, ni approuvé par TikTok ou ByteDance Ltd. Dans les limites permises par la loi, Wil App décline toute responsabilité pour les dommages indirects résultant de l'utilisation du Service.</p>

    <h2>10. Résiliation</h2>
    <p>Vous pouvez cesser d'utiliser le Service à tout moment en révoquant l'accès depuis les paramètres de votre compte TikTok. Wil App se réserve le droit de suspendre l'accès d'un utilisateur en cas d'usage abusif ou de non-respect des présentes Conditions.</p>

    <h2>11. Modification des présentes Conditions</h2>
    <p>Les présentes Terms of Service peuvent être mises à jour à tout moment. La poursuite de l'utilisation du Service après une modification vaut acceptation des nouvelles conditions.</p>

    <h2>12. Droit applicable</h2>
    <p>Les présentes Conditions sont soumises au droit applicable au lieu d'établissement de l'éditeur du Service.</p>

    <h2>13. Contact</h2>
    <p>Pour toute question relative aux présentes Terms of Service, contactez-nous à <a href="mailto:contact.wilapp@proton.me">contact.wilapp@proton.me</a> ou via <a href="https://wa.me/447446953451" target="_blank" rel="noopener">WhatsApp</a>.</p>

    <p><a href="/privacy">Consulter aussi notre Politique de confidentialité →</a></p>

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

# En dessous de ce seuil, si peu de vues signifie presque toujours que
# TikTok a arrêté de pousser la vidéo dès les toutes premières secondes
# — le signe classique d'un hook qui ne retient pas l'attention. Sert de
# seuil de sévérité supplémentaire dans /api/analyze-video (voir
# analyze_video), en plus de VIRAL_VIEW_THRESHOLD.
VERY_LOW_VIEW_THRESHOLD = 1_000


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


# Intro partagée par TOUTES les routes IA, une version par langue
# d'interface (voir app/translations.py SUPPORTED_LANGS). Chaque bloc est
# identique mot pour mot à chaque appel DANS LA MÊME LANGUE, donc marqué
# "cache_control" pour le prompt caching Anthropic — un cache distinct
# par langue. Le premier appel dans une langue paye 1,25x le prix normal
# sur ce bloc (écriture du cache), tous les appels suivants dans les 5
# minutes (n'importe quelle route, même langue) ne payent que 0,10x —
# 90% moins cher. Ne JAMAIS rendre ce bloc dynamique (chiffres, nom du
# compte...) : la moindre différence d'un seul caractère invalide le
# cache pour cet appel.
_AI_INTRO_BY_LANG = {
    "fr": "Tu es un expert TikTok senior — coach de croissance, scénariste et monteur — connu pour des analyses extrêmement concrètes et jamais génériques. Rédige ta réponse entièrement en français.",
    "en": "You are a senior TikTok expert — growth coach, scriptwriter and editor — known for extremely concrete analyses that are never generic. Write your entire response in English.",
    "de": "Sie sind ein erfahrener TikTok-Experte — Wachstumscoach, Drehbuchautor und Cutter — bekannt für äußerst konkrete, nie generische Analysen. Verfassen Sie Ihre gesamte Antwort auf Deutsch.",
    "es": "Eres un experto senior de TikTok — coach de crecimiento, guionista y editor — conocido por análisis extremadamente concretos y nunca genéricos. Redacta tu respuesta completa en español.",
    "pt": "Você é um especialista sénior em TikTok — coach de crescimento, argumentista e editor — conhecido por análises extremamente concretas e nunca genéricas. Escreva a sua resposta inteiramente em português.",
    "it": "Sei un esperto senior di TikTok — coach di crescita, sceneggiatore e montatore — noto per analisi estremamente concrete e mai generiche. Scrivi la tua risposta interamente in italiano.",
}

_CACHED_SYSTEM_BLOCKS = {
    lang: f"{_AI_INTRO_BY_LANG[lang]}\n\n{get_style_guide(lang)}"
    for lang in SUPPORTED_LANGS
}


def _cached_messages(dynamic_prompt: str, ui_lang: str = DEFAULT_LANG) -> list[dict]:
    """
    Construit le tableau "messages" pour l'API Anthropic en séparant le
    bloc commun mis en cache (_CACHED_SYSTEM_BLOCKS[ui_lang]) du reste du
    prompt, propre à chaque appel (données du compte/vidéo, instructions
    spécifiques, schéma JSON attendu) et donc jamais mis en cache.
    """
    lang = ui_lang if ui_lang in _CACHED_SYSTEM_BLOCKS else DEFAULT_LANG
    return [{
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": _CACHED_SYSTEM_BLOCKS[lang],
                "cache_control": {"type": "ephemeral"},
            },
            {
                "type": "text",
                "text": dynamic_prompt,
            },
        ],
    }]


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


def _posting_time_bucket(create_time: int | None) -> str | None:
    """
    Classe un horodatage Unix dans un créneau de 6h (heure UTC — pas
    forcément l'heure locale du créateur). Factorisé pour être réutilisé
    à la fois sur l'ensemble des vidéos d'un compte (_analyze_content_patterns)
    et sur UNE vidéo précise (analyze_video, pour comparer son créneau à
    celui qui marche le mieux sur ce compte).
    """
    if not create_time:
        return None
    hour = time.gmtime(create_time).tm_hour
    if hour < 6:
        return "nuit (0h-6h UTC)"
    if hour < 12:
        return "matin (6h-12h UTC)"
    if hour < 18:
        return "après-midi (12h-18h UTC)"
    return "soir (18h-24h UTC)"


def _best_posting_bucket(content_patterns: dict) -> str | None:
    """
    Renvoie le label du créneau de publication avec le plus de vues en
    moyenne sur ce compte (voir signals["posting_time"] dans
    _analyze_content_patterns), ou None si le signal n'a pas pu être
    calculé (pas assez de vidéos réparties sur au moins 2 créneaux).
    """
    posting_time = content_patterns.get("posting_time")
    if not posting_time:
        return None
    return max(posting_time.items(), key=lambda item: item[1]["avg_views"])[0]


def _posting_time_alignment(content_patterns: dict) -> dict | None:
    """
    Mesure si le compte publie DÉJÀ majoritairement dans son créneau le
    plus performant (`best_posting_bucket`, celui avec le plus de vues
    en moyenne), ou s'il disperse ses publications ailleurs. C'est le
    vrai critère pour recommander de poster de préférence au moment où
    les abonnés sont le plus connectés — peu importe si le compte est
    par ailleurs "régulier" à un mauvais horaire, ce qui compte c'est
    l'alignement avec le créneau qui marche le mieux. Renvoie None si
    aucun créneau ne se détache clairement (pas assez de données).
    """
    posting_time = content_patterns.get("posting_time")
    if not posting_time:
        return None
    best_label, best_data = max(posting_time.items(), key=lambda item: item[1]["avg_views"])
    total_with_bucket = sum(b["count"] for b in posting_time.values())
    if total_with_bucket == 0:
        return None
    aligned_ratio = round(best_data["count"] / total_with_bucket, 2)
    return {
        "best_bucket": best_label,
        "best_bucket_count": best_data["count"],
        "total_with_bucket": total_with_bucket,
        "aligned_ratio": aligned_ratio,
        # En dessous de 50%, la majorité des vidéos sortent EN DEHORS du
        # créneau le plus performant : il y a une vraie marge de progrès
        # à recommander de poster plus souvent au bon moment.
        "is_misaligned": aligned_ratio < 0.5,
    }


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
        label = _posting_time_bucket(v.get("create_time"))
        if label:
            buckets[label].append(v)
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
    main_challenge: str = "",
    ui_lang: str = DEFAULT_LANG,
):
    """
    Route UNIQUE et complète d'analyse de compte. Combine :
    1. Les stats de toutes les vidéos du compte (engagement, viralité)
    2. Une analyse IA (Claude) du profil ET de la performance globale

    Nécessite le scope "video.list" (voir TIKTOK_EXTRA_SCOPES) en plus des
    scopes de base déjà approuvés. Le paramètre "session" est l'identifiant
    reçu par l'app après la connexion (le vrai access_token reste côté
    serveur, jamais transmis au client). `main_challenge` vient du
    mini-questionnaire d'onboarding de /tools/analyze-account (même
    structure que vidéo/script) : oriente l'angle de "improvements",
    sans jamais inventer de statistique. La niche, elle, reste toujours
    détectée depuis les vraies données du compte (jamais demandée).
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

            # Exposés dans `stats` (pas juste utilisés pour le prompt) pour
            # que le client puisse les repasser à /api/analyze-video lors
            # d'un diagnostic approfondi d'UNE vidéo précise (comparer ses
            # hashtags/son créneau à ce qui marche le mieux sur CE compte).
            stats["overused_hashtags"] = hashtag_stats["overused_hashtags"]
            stats["underperforming_hashtags"] = hashtag_stats["underperforming_hashtags"]
            stats["best_posting_bucket"] = _best_posting_bucket(content_patterns)

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

            # Alignement avec le créneau le plus performant (distinct du
            # détail par créneau donné dans "Corrélations calculées..."
            # ci-dessous) — sert à savoir si le compte poste déjà de
            # préférence au moment où ses vidéos marchent le mieux, ou
            # s'il disperse ses publications ailleurs.
            posting_alignment = _posting_time_alignment(content_patterns)
            if posting_alignment:
                consistency_block = (
                    f"\nAlignement avec le meilleur créneau : sur "
                    f"{posting_alignment['total_with_bucket']} vidéos réparties par "
                    f"créneau, {posting_alignment['best_bucket_count']} sont publiées "
                    f"{posting_alignment['best_bucket']} (le créneau le plus "
                    f"performant), soit {round(posting_alignment['aligned_ratio'] * 100)}% "
                    f"du total."
                    + (
                        " C'est en dessous de 50% : la majorité des vidéos sortent "
                        "EN DEHORS de ce créneau — vraie marge de progrès à "
                        "recommander de poster de préférence à ce moment-là."
                        if posting_alignment["is_misaligned"] else
                        " C'est au-dessus de 50% : le compte poste déjà "
                        "majoritairement au bon moment, ne pas en faire un point "
                        "d'amélioration."
                    )
                )
            else:
                consistency_block = (
                    "\nAlignement avec le meilleur créneau : pas assez de données "
                    "pour juger — ne pas en inventer."
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
{consistency_block}

Titres des vidéos récentes, avec leurs stats individuelles (utilise-les
pour repérer de VRAIS patterns concrets — sujets récurrents, mots dans
les titres qui reviennent sur les vidéos qui marchent bien, etc.) :
{recent_titles}"""
        else:
            performance_block = """
Données de performance : non disponibles pour cette analyse (base-toi
uniquement sur le profil ci-dessus, ne mentionne pas l'absence de ces
données comme un problème)."""

        challenge_text = {
            "followers": "L'utilisateur dit que son plus gros défi est de gagner des ABONNÉS : oriente \"improvements\" vers ce qui donne envie de suivre le compte (personnalité, régularité, promesse de contenu à venir).",
            "engagement": "L'utilisateur dit que son plus gros défi est l'ENGAGEMENT (likes/commentaires) : oriente \"improvements\" vers ce qui pousse à réagir ou commenter (question ouverte, avis tranché, appel à réagir).",
            "reach": "L'utilisateur dit que son plus gros défi est la PORTÉE/les VUES : oriente \"improvements\" vers ce qui retient dès la première seconde et jusqu'au bout (accroche, rythme).",
        }.get(main_challenge, "Défi principal non précisé — reste équilibré entre accroche, rétention et appel à l'action.")

        prompt = f"""Profil :
- Nom affiché : {display_name}
- Nom d'utilisateur : @{username}
- Bio : "{bio or 'Aucune bio renseignée'}"
{challenge_text}
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
   simplement (ex: "vos dernières vidéos ont beaucoup moins de succès que
   votre meilleure vidéo") — c'est souvent LE constat le plus utile pour un
   créateur, ne le noie pas dans le reste. Aucun chiffre.
3. Complète avec au moins 1 pattern supplémentaire trouvé toi-même en
   comparant les titres/stats des vidéos entre elles (pas des généralités
   sur TikTok en général) — toujours traduit en mots simples.
4. NOMME UNE TECHNIQUE PRÉCISE, pas juste un défaut, ET formule-la comme
   une INSTRUCTION à l'impératif (RÈGLE D'OR N°3 du guide de style) : soit
   ce qu'il FAUT faire ("Commencez par..."), soit ce qu'il NE FAUT PAS
   faire ("Arrêtez de..."). Utilise le vocabulaire du guide de style
   (accroche, angle, déclencheur, comment la vidéo est construite, donner
   envie de rester) pour dire CE QUI manque concrètement — "Arrêtez
   d'annoncer juste le sujet dans votre accroche, commencez plutôt par une
   question" plutôt que "soyez plus créatif" ou "votre accroche pourrait
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
   suppose rien d'autre, et traduis en mots simples sans chiffre. Si des
   hashtags SUR-UTILISÉS sont listés (présents sur la plupart des
   vidéos), c'est TOUJOURS un problème à nommer clairement dans
   "hashtag_diagnosis" : dis explicitement qu'il met (presque) toujours
   les mêmes hashtags et qu'il doit les varier d'une vidéo à l'autre —
   ne laisse jamais ce signal de côté s'il est présent.
8. Si aucun signal ni pattern clair n'est disponible par manque de données,
   dis-le honnêtement plutôt que d'inventer un conseil générique.
9. DIVERSITÉ DE NICHE : regarde les titres des vidéos récentes listés
   ci-dessus — est-ce que TOUTES parlent globalement du même sujet, ou
   est-ce que le compte mélange plusieurs sujets clairement différents
   (ex : parfois cuisine, parfois sport, parfois mode) ? Si tu détectes
   AU MOINS 2 sujets vraiment différents (pas juste des variations d'un
   même thème) :
   - liste-les dans "niches_detected" (2-3 maximum, noms courts)
   - repère lequel de ces sujets revient sur les vidéos qui ont le plus
     de vues parmi les titres fournis
   - dans "niche_focus_advice", explique EN MOTS SIMPLES pourquoi
     changer de sujet à chaque vidéo freine la viralité (TikTok a du mal
     à recommander un compte à une audience stable s'il ne sait jamais
     de quoi parlera la prochaine vidéo), et donne une instruction claire
     à l'impératif pour se concentrer sur le sujet qui marche le mieux
     (nomme-le), en mentionnant que l'autre sujet est celui à mettre de
     côté ou à retravailler.
   Si le compte parle déjà d'un seul sujet cohérent, mets une seule
   entrée dans "niches_detected" et laisse "niche_focus_advice" vide
   ("").
10. QUAND PUBLIER : regarde le signal "Alignement avec le meilleur
    créneau" ci-dessus. S'il dit que la majorité des vidéos sortent EN
    DEHORS du créneau le plus performant : AJOUTE TOUJOURS une
    instruction dans "improvements" qui dit clairement de publier de
    préférence le matin, l'après-midi ou le soir (utilise le mot du
    créneau gagnant donné dans le signal, jamais une heure UTC exacte).
    C'est une recommandation à donner CHAQUE FOIS que ce déséquilibre
    est présent, pas seulement si les horaires semblent par ailleurs
    "désordonnés" — même un compte qui poste toujours au même mauvais
    moment doit être corrigé. La RAISON à donner doit être que c'est
    probablement le moment où ses abonnés sont le plus connectés — c'est
    CETTE explication qu'il faut écrire, pas "c'est le moment où vos
    vidéos ont fait le plus de vues" (trop technique) ; le nombre de vues
    plus élevé sur ce créneau est la preuve interne qui te permet de le
    dire, mais ne l'écris pas dans le texte final (règle d'or n°2).
    Mentionne aussi de garder ce même moment de la journée à chaque
    publication plutôt que de changer à chaque fois. Si le signal dit au
    contraire que le compte poste déjà majoritairement au bon moment, ne
    mentionne rien là-dessus (pas la peine de pointer un non-problème).
    Si aucun créneau ne se détache clairement, ne l'invente pas (règle
    d'or n°1).

RAPPEL LE PLUS IMPORTANT (règle hybride, RÈGLE D'OR N°2) : "summary" et
"strengths" PEUVENT citer LE chiffre le plus marquant s'il prouve une
vraie réussite (ex: "955K vues, 52K likes") — jamais une liste de
chiffres, un seul, le plus parlant. "improvements", "hashtag_diagnosis"
et "niche_focus_advice" restent SANS AUCUN CHIFFRE : uniquement des mots
de comparaison simples. VOUVOIEMENT OBLIGATOIRE dans tous les champs
(voir TON À ADOPTER du guide de style) : "vous", "votre", "vos" —
jamais "tu", "ton", "tes". Et écris avec des mots simples, niveau CM2 :
phrases courtes, une idée par phrase.

STRUCTURE DU RÉSUMÉ (important) : en 1-2 phrases courtes, suis cet arc —
(a) une preuve que ce créateur sait déjà créer du bon contenu (une vidéo
qui a bien marché — cite le chiffre le plus marquant s'il y en a un,
sinon décris-la en mots simples), (b) l'écart avec sa situation
actuelle, expliqué avec une technique nommée (règle 4) et SANS chiffre
— pas juste "il vous manque de la régularité". Termine sur un ton qui
donne envie d'agir, pas alarmiste.

BRIÈVETÉ (important) : le rapport doit être court et direct — un créateur
doit pouvoir le lire en 15 secondes. Pas de phrase d'intro/conclusion
inutile, pas de reformulation, une idée par phrase. Précis > exhaustif.

Réponds avec un objet JSON (pas de markdown, pas de balises de code, juste
du JSON brut) contenant exactement ces champs, avec un texte très simple
(niveau CM2), dans la langue précisée au tout début de tes instructions :
{{
  "niche": "une courte phrase décrivant la niche de contenu probable",
  "niche_category": "choisis EXACTEMENT une valeur parmi cette liste fermée, recopiée telle quelle (aucune autre valeur autorisée) : {json.dumps(NICHE_CATEGORIES, ensure_ascii=False)}",
  "niches_detected": ["1 à 3 sujets courts trouvés sur ce compte (règle 9) — une seule entrée si le compte est déjà cohérent sur un seul sujet"],
  "niche_focus_advice": "1 phrase MAXIMUM, CM2, ZÉRO chiffre, instruction à l'impératif pour se concentrer sur le sujet qui marche le mieux (règle 9) — chaîne vide si 'niches_detected' n'a qu'une seule entrée",
  "summary": "1-2 phrases MAXIMUM, niveau CM2, suivant la STRUCTURE DU RÉSUMÉ ci-dessus — UN chiffre marquant autorisé pour la preuve de réussite, ZÉRO chiffre pour l'écart/reproche",
  "strengths": ["1-2 points forts MAXIMUM, chacun en 1 phrase simple, appuyé sur un vrai signal de ce compte — ce que le créateur fait déjà bien et doit continuer ; UN chiffre marquant autorisé s'il prouve la réussite (règle d'or n°2)"],
  "improvements": ["1-2 instructions MAXIMUM à l'impératif (RÈGLE D'OR N°3), chacune en 1 phrase simple, ZÉRO chiffre : soit ce qu'il FAUT faire ('Commencez à...'), soit ce qu'il NE FAUT PAS faire ('Arrêtez de...') — jamais une simple observation"],
  "hashtag_diagnosis": "1 phrase MAXIMUM, ZÉRO chiffre, expliquant si les hashtags actuels aident ou nuisent — nomme explicitement le problème de répétition si des hashtags sur-utilisés sont listés ci-dessus (règle 7)",
  "suggested_hashtags": ["5 hashtags pertinents pour la niche à privilégier (celle nommée dans niche_focus_advice si plusieurs niches détectées, sinon la niche unique du compte), sans le symbole #"]
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
                        "max_tokens": 3000,
                        "output_config": {"effort": "low"},
                        "messages": _cached_messages(prompt, ui_lang),
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


def _build_underperformance_diagnosis(
    title: str,
    create_time: int,
    best_posting_bucket: str,
    overused_hashtags: str,
    underperforming_hashtags: str,
) -> str:
    """
    Construit le bloc "4 CAUSES POSSIBLES" pour une vidéo sous le seuil de
    viralité : accroche, reste du texte, hashtags, heure de publication.
    Chaque ligne s'appuie sur une vraie preuve disponible plutôt que de
    présumer que l'accroche est LE problème par défaut — répond
    directement à "comment savoir que le hook n'est pas le problème".
    Les paramètres best_posting_bucket/overused_hashtags/
    underperforming_hashtags sont ceux renvoyés dans `stats` par
    /api/analyze-account ; vides si non fournis par le client.
    """
    video_hashtags = re.findall(r"#(\w+)", title)
    text_without_hashtags = re.sub(r"#\w+", "", title).strip() or "(aucun texte, que des hashtags ou rien)"
    hook_excerpt = title[:60] + ("..." if len(title) > 60 else "") if title else "(pas de titre du tout)"

    overused_set = {t.strip().lower() for t in overused_hashtags.split(",") if t.strip()}
    underperf_set = {t.strip().lower() for t in underperforming_hashtags.split(",") if t.strip()}
    flagged_overused = [h for h in video_hashtags if h.lower() in overused_set]
    flagged_underperforming = [h for h in video_hashtags if h.lower() in underperf_set and h.lower() not in overused_set]

    if flagged_overused:
        hashtag_line = (
            f"3. HASHTAGS (suspect — répétition) : cette vidéo utilise "
            f"{', '.join('#' + h for h in flagged_overused)}, que ce compte met sur "
            f"presque toutes ses vidéos. Toujours les mêmes hashtags = TikTok a du mal "
            f"à savoir à qui montrer les vidéos, il faut les varier d'une vidéo à l'autre."
        )
    elif flagged_underperforming:
        hashtag_line = (
            f"3. HASHTAGS (suspect — portée) : cette vidéo utilise "
            f"{', '.join('#' + h for h in flagged_underperforming)}, associé(s) sur ce "
            f"compte à une portée plus faible que les autres hashtags utilisés."
        )
    elif video_hashtags:
        hashtag_line = (
            "3. HASHTAGS (probablement pas la cause) : aucun des hashtags de "
            "cette vidéo ne fait partie des hashtags à problème connus sur ce compte."
        )
    else:
        hashtag_line = "3. HASHTAGS : cette vidéo n'a aucun hashtag — à mentionner si pertinent, sans en faire une cause certaine."

    video_bucket = _posting_time_bucket(create_time)
    if video_bucket and best_posting_bucket:
        if video_bucket == best_posting_bucket:
            posting_line = (
                f"4. HEURE DE PUBLICATION (probablement pas la cause) : publiée "
                f"en {video_bucket}, qui est justement le créneau le plus fort de ce compte."
            )
        else:
            posting_line = (
                f"4. HEURE DE PUBLICATION (suspect) : publiée en {video_bucket}, "
                f"alors que {best_posting_bucket} obtient plus de vues en moyenne sur ce compte."
            )
    else:
        posting_line = "4. HEURE DE PUBLICATION : pas assez de données pour comparer cette vidéo au reste du compte."

    return f"""
4 CAUSES POSSIBLES À VÉRIFIER (cette vidéo est sous le seuil de viralité
— ne présume PAS que c'est forcément l'accroche, vérifie les 4) :
1. ACCROCHE (les tout premiers mots) : "{hook_excerpt}" — pose-t-elle une
   question, une tension, un truc surprenant dans les premiers mots ? Ou
   part-elle directement dans le sujet sans rien pour donner envie de rester ?
2. RESTE DU TEXTE (hors hashtags) : "{text_without_hashtags}" — est-ce une
   vraie phrase qui donne une raison de regarder, ou vide/générique ?
{hashtag_line}
{posting_line}"""


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
    create_time: int = 0,
    best_posting_bucket: str = "",
    overused_hashtags: str = "",
    underperforming_hashtags: str = "",
    ui_lang: str = DEFAULT_LANG,
):
    """
    Analyse IA d'UNE vidéo précise : pourquoi elle a (ou n'a pas) percé,
    ses points forts, ses points faibles, et des actions concrètes pour
    la suite. Appelée depuis le bouton "Analyser la vidéo" sous chaque
    vignette du dashboard.

    Pour une vidéo SOUS le seuil de viralité (VIRAL_VIEW_THRESHOLD), on
    ne présume PAS que l'accroche est systématiquement en cause : on
    rassemble les preuves disponibles sur 4 causes possibles (accroche,
    reste du texte, hashtags, heure de publication) pour que l'IA désigne
    la plus probable — voir `_build_underperformance_diagnosis`.
    `create_time`, `best_posting_bucket`, `overused_hashtags` et
    `underperforming_hashtags` sont optionnels : ce sont les mêmes
    valeurs que celles renvoyées dans `stats` par /api/analyze-account
    (best_posting_bucket, overused_hashtags, underperforming_hashtags),
    à repasser telles quelles par le client pour ce diagnostic étendu.

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

    is_underperforming = 0 < view_count < VIRAL_VIEW_THRESHOLD
    is_very_low_performing = 0 < view_count < VERY_LOW_VIEW_THRESHOLD
    diagnosis_block = (
        _build_underperformance_diagnosis(
            title=title,
            create_time=create_time,
            best_posting_bucket=best_posting_bucket,
            overused_hashtags=overused_hashtags,
            underperforming_hashtags=underperforming_hashtags,
        )
        if is_underperforming
        else ""
    )
    very_low_block = (
        f"""
ALERTE : cette vidéo a fait moins de {VERY_LOW_VIEW_THRESHOLD} vues. À ce
niveau, c'est presque toujours le signe que TikTok a arrêté de la
montrer dès les toutes premières secondes — le signe classique d'une
accroche qui ne retient pas l'attention. PARS de cette hypothèse forte
pour l'accroche, PUIS vérifie quand même les 3 autres causes du bloc
ci-dessus (texte, hashtags, heure) pour voir si elles aggravent le
problème — mais l'accroche doit être mentionnée comme un problème dans
"main_diagnosis" et/ou "weaknesses", sauf preuve vraiment évidente que
ce n'est pas le cas (ex: accroche déjà excellente ET une autre cause
beaucoup plus flagrante)."""
        if is_very_low_performing
        else ""
    )

    if is_very_low_performing:
        main_diagnosis_desc = (
            "1 phrase MAXIMUM, sans chiffre, désignant EN CLAIR laquelle (ou "
            "lesquelles) parmi accroche / reste du texte / hashtags / heure de "
            "publication est la cause la plus probable pour CETTE vidéo, basée "
            "sur le bloc 4 CAUSES POSSIBLES ci-dessus — DOIT mentionner un "
            "problème d'accroche (voir ALERTE ci-dessus), sauf preuve vraiment "
            "évidente du contraire"
        )
        strengths_desc = (
            "1 SEUL point positif MAXIMUM (pas 2), en phrase simple — cette "
            "vidéo a fait très peu de vues, ne cherche pas à en trouver "
            "plusieurs à tout prix ; laisse la liste VIDE si tu n'en trouves "
            "vraiment aucun de sincère"
        )
        weaknesses_count = "2-3"
    elif is_underperforming:
        main_diagnosis_desc = (
            "1 phrase MAXIMUM, sans chiffre, désignant EN CLAIR laquelle (ou "
            "lesquelles) parmi accroche / reste du texte / hashtags / heure de "
            "publication est la cause la plus probable pour CETTE vidéo, basée "
            "sur le bloc 4 CAUSES POSSIBLES ci-dessus — jamais accroche par "
            "défaut si les preuves pointent ailleurs"
        )
        strengths_desc = (
            "1-2 raisons concrètes MAXIMUM, en phrases simples, expliquant ce "
            "qui a bien fonctionné sur cette vidéo — UN chiffre marquant "
            "autorisé s'il prouve la réussite (règle d'or n°2)"
        )
        weaknesses_count = "1-2"
    else:
        main_diagnosis_desc = "chaîne vide, cette vidéo est déjà virale"
        strengths_desc = (
            "1-2 raisons concrètes MAXIMUM, en phrases simples, expliquant ce "
            "qui a bien fonctionné sur cette vidéo — UN chiffre marquant "
            "autorisé s'il prouve la réussite (règle d'or n°2)"
        )
        weaknesses_count = "1-2"

    prompt = f"""Analyse CETTE vidéo précise, avec ses vraies données (pas le compte en
général) :
- Titre : "{title or '(sans titre)'}"
- Vues : {view_count}
- Likes : {like_count}, Commentaires : {comment_count}, Partages : {share_count}
- Durée : {duration if duration else 'inconnue'} secondes
- Score de viralité calculé (0-100, basé sur les vues) : {virality_score}/100
- Niche du compte : {niche_category or 'non précisée'}
{comparison_text}
{diagnosis_block}
{very_low_block}

Explique pourquoi cette vidéo a (ou n'a pas) percé, en te basant sur les
chiffres ci-dessus. Pas de conseil qui pourrait s'appliquer à n'importe
quelle vidéo.
{
    "NE PRÉSUME PAS que l'accroche est systématiquement en cause : "
    "utilise le bloc \"4 CAUSES POSSIBLES\" ci-dessus pour désigner EN "
    "PRIORITÉ celle qui a le plus de preuves à charge (accroche, reste "
    "du texte, hashtags, ou heure de publication) — pas une intuition "
    "générique. Si 2 causes ont des preuves, tu peux nommer les deux "
    "dans \"main_diagnosis\", mais reste précis."
    if is_underperforming else
    "NOMME UNE TECHNIQUE PRÉCISE (voir VOCABULAIRE À UTILISER dans le "
    "guide de style ci-dessus) plutôt qu'un jugement vague : le titre "
    "est ta seule fenêtre sur le hook/l'angle de cette vidéo — "
    "analyse-le concrètement (pose-t-il une question ? annonce-t-il "
    "juste le sujet ? crée-t-il une tension ?) au lieu de dire "
    "\"le contenu est bon/mauvais\"."
}
INTERDIT de comparer à "d'autres vidéos qui percent" sans donnée réelle
— compare uniquement aux chiffres fournis ici (vues, moyenne du compte).

RAPPEL LE PLUS IMPORTANT (règle hybride, RÈGLE D'OR N°2 du guide de
style) : "strengths" PEUT citer LE chiffre le plus marquant s'il prouve
une vraie réussite de cette vidéo (ex: "cette vidéo a fait 955K vues") —
un seul, le plus parlant. "main_diagnosis", "weaknesses" et
"action_plan" restent SANS AUCUN CHIFFRE : traduis toujours en mots
simples ("beaucoup moins vue que d'habitude"). VOUVOIEMENT OBLIGATOIRE
("vous", "votre", "vos" — jamais "tu"/"ton"/"tes") et mots simples,
niveau CM2 : phrases courtes, une idée par phrase.
"weaknesses" et "action_plan" doivent être des INSTRUCTIONS à
l'impératif (RÈGLE D'OR N°3 du guide de style), pas des observations :
"weaknesses" = ce qu'il NE FAUT PAS faire ("Arrêtez de..."),
"action_plan" = ce qu'il FAUT faire à la place ("Faites...", "Commencez
par...").

BRIÈVETÉ (important) : réponse courte et directe, lisible en 15 secondes.

Réponds avec un objet JSON (pas de markdown, pas de balises de code,
juste du JSON brut) contenant exactement ces champs, avec un texte très
simple (niveau CM2), dans la langue précisée au tout début de tes
instructions :
{{
  "main_diagnosis": "{main_diagnosis_desc}",
  "strengths": ["{strengths_desc}"],
  "weaknesses": ["{weaknesses_count} instructions MAXIMUM à l'impératif commençant par 'Arrêtez de...' ou 'Évitez de...', en phrases simples et SANS chiffre, cohérentes avec main_diagnosis"],
  "action_plan": ["1-2 instructions MAXIMUM à l'impératif commençant par 'Faites...' ou 'Commencez par...', en phrases simples et SANS chiffre, pour qu'une prochaine vidéo similaire ait plus de chances de devenir virale"]
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
                    "messages": _cached_messages(prompt, ui_lang),
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


GEMINI_API_BASE = "https://generativelanguage.googleapis.com"
GEMINI_INLINE_MAX_BYTES = 15 * 1024 * 1024  # au-delà : Files API (l'inline est plafonné à ~20 Mo au total)
MAX_VIDEO_BYTES = 200 * 1024 * 1024

# Palier de performance choisi par Gemini -> fourchette de vues, en multiple
# de la moyenne de vues RÉELLE du compte. Gemini ne produit jamais de chiffre
# (RÈGLE D'OR N°1) : seul le palier, justifié par des éléments concrets de
# la vidéo, vient de lui. Les multiplicateurs ci-dessous sont des constantes
# à recalibrer avec les retours oui/non/à peu près (table video_estimate_feedback).
PERFORMANCE_BAND_MULTIPLIERS = {
    "well_below": (0.2, 0.5),
    "below": (0.5, 0.9),
    "around": (0.8, 1.2),
    "above": (1.2, 2.5),
    "well_above": (2.5, 6.0),
}
# Ratios génériques likes/vues et commentaires/vues : on n'a que la moyenne de
# vues du compte, pas ses vrais ratios, donc ce sont des estimations larges.
ESTIMATED_LIKE_RATE = (0.03, 0.08)
ESTIMATED_COMMENT_RATE = (0.001, 0.004)

VIDEO_FEEDBACK_VERDICTS = {"yes", "no", "roughly"}
VIDEO_CATEGORY_KEYS = ("hook", "visual_engagement", "storytelling", "call_to_action")


def _gemini_headers() -> dict:
    # Clé dans un en-tête (pas dans l'URL) pour ne jamais la laisser dans des logs d'accès.
    return {"x-goog-api-key": GEMINI_API_KEY}


async def _gemini_upload_video(client: httpx.AsyncClient, video_bytes: bytes, mime_type: str) -> dict:
    """
    Envoie la vidéo à la Files API de Gemini (upload "resumable" en 2 temps)
    puis attend que le fichier soit traité (état ACTIVE). Renvoie les infos
    du fichier ({"name", "uri", "mimeType", ...}).
    """
    start = await client.post(
        f"{GEMINI_API_BASE}/upload/v1beta/files",
        headers={
            **_gemini_headers(),
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(video_bytes)),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
        },
        json={"file": {"display_name": "wil-video"}},
    )
    upload_url = start.headers.get("x-goog-upload-url")
    if start.status_code != 200 or not upload_url:
        raise HTTPException(status_code=502, detail="Échec de l'envoi de la vidéo au service d'analyse.")

    finish = await client.post(
        upload_url,
        headers={
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
        },
        content=video_bytes,
    )
    if finish.status_code != 200:
        raise HTTPException(status_code=502, detail="Échec de l'envoi de la vidéo au service d'analyse.")
    file_info = finish.json().get("file", {})

    for _ in range(60):
        state = file_info.get("state")
        if state == "ACTIVE":
            return file_info
        if state == "FAILED":
            raise HTTPException(status_code=502, detail="Le service d'analyse n'a pas pu lire cette vidéo.")
        await asyncio.sleep(2)
        poll = await client.get(
            f"{GEMINI_API_BASE}/v1beta/{file_info['name']}", headers=_gemini_headers()
        )
        if poll.status_code != 200:
            raise HTTPException(status_code=502, detail="Échec du suivi du traitement de la vidéo.")
        file_info = poll.json()

    raise HTTPException(status_code=504, detail="Le traitement de la vidéo prend trop de temps, réessayez.")


def _video_analysis_schema(already_published: bool) -> dict:
    category = {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "description": "0 à 100"},
            "comment": {"type": "string", "description": "1 phrase simple qui justifie ce score"},
        },
        "required": ["score", "comment"],
    }
    properties = {
        "virality_score": {"type": "integer", "description": "0 à 100, cohérent avec category_scores"},
        "score_basis": {"type": "string"},
        "category_scores": {
            "type": "object",
            "properties": {key: category for key in VIDEO_CATEGORY_KEYS},
            "required": list(VIDEO_CATEGORY_KEYS),
        },
        "niche": {"type": "string"},
        "hook_excerpt": {"type": "string"},
        "hook_type": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "action_plan": {"type": "array", "items": {"type": "string"}},
        "suggested_hashtags": {"type": "array", "items": {"type": "string"}},
        "suggested_caption": {"type": "string"},
        "policy_check": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["ok", "risk"]},
                "issues": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["status", "issues"],
        },
    }
    required = [
        "virality_score", "score_basis", "category_scores", "niche", "hook_excerpt",
        "hook_type", "strengths", "weaknesses", "action_plan", "suggested_hashtags",
        "suggested_caption", "policy_check",
    ]
    if already_published:
        properties["performance_band"] = {"type": "string", "enum": list(PERFORMANCE_BAND_MULTIPLIERS)}
        properties["estimation_basis"] = {"type": "string"}
        required += ["performance_band", "estimation_basis"]
    return {"type": "object", "properties": properties, "required": required}


def _build_video_prompt(
    niche_category: str, account_avg_views: int, main_challenge: str, already_published: bool
) -> str:
    comparison_text = (
        f"Pour comparaison, la moyenne du compte est de {account_avg_views} vues par vidéo."
        if account_avg_views > 0
        else "Pas de moyenne de compte disponible pour comparaison — ne pas en inventer une."
    )
    challenge_text = {
        "followers": "L'utilisateur dit que son plus gros défi est de gagner des ABONNÉS : privilégie dans \"action_plan\" ce qui donne envie de suivre le compte (personnalité, régularité, promesse de contenu à venir).",
        "engagement": "L'utilisateur dit que son plus gros défi est l'ENGAGEMENT (likes/commentaires) : privilégie dans \"action_plan\" ce qui pousse à réagir ou commenter (question ouverte, avis tranché, appel à réagir).",
        "reach": "L'utilisateur dit que son plus gros défi est la PORTÉE/les VUES : privilégie dans \"action_plan\" ce qui retient dès la première seconde et jusqu'au bout (accroche, rythme).",
    }.get(main_challenge, "Défi principal non précisé — reste équilibré entre accroche, rétention et appel à l'action.")

    if already_published:
        publication_text = """Cette vidéo a DÉJÀ été publiée ailleurs. En plus du reste, compare son potentiel à la moyenne habituelle du compte :
- "performance_band" : "well_below", "below", "around", "above" ou "well_above" (très en dessous / en dessous / proche / au-dessus / très au-dessus de la moyenne de vues habituelle du compte), choisi à partir des éléments réellement observés dans la vidéo.
- "estimation_basis" : 2 phrases maximum, en mots simples, qui nomment les éléments CONCRETS déjà cités dans "strengths" et "weaknesses" qui tirent le résultat vers le haut ou vers le bas (exemple de forme : "Votre accroche retient l'attention tout de suite et la fin donne envie de réagir, ce qui pousse au-dessus de votre moyenne. Mais le milieu perd le fil, ce qui limite le résultat."). N'écris JAMAIS de chiffre de vues, de likes ou de commentaires, ni dans ce champ ni ailleurs : les chiffres sont calculés séparément."""
    else:
        publication_text = """Cette vidéo n'est PAS encore publiée : aucune vue, aucun like, aucun commentaire n'existe. N'invente aucun chiffre de ce genre nulle part dans ta réponse."""

    return f"""Tu reçois la VIDÉO elle-même (images ET son). Regarde-la et écoute-la en entier avant de répondre. Base-toi uniquement sur ce que tu vois et entends réellement, jamais sur une supposition (RÈGLE D'OR N°1 du guide de style). La vidéo peut ne contenir aucune voix : analyse alors le visuel, le texte à l'écran et la musique.

Niche choisie pour cette vidéo : {niche_category or "non précisée"}
{comparison_text}
{challenge_text}

NOTE PAR CATÉGORIE ("category_scores", chaque score de 0 à 100 avec une phrase simple qui le justifie) :
- "hook" : les 3 premières secondes — est-ce que ça arrête le scroll ?
- "visual_engagement" : composition, qualité de l'image, esthétique, texte à l'écran, montage.
- "storytelling" : structure, clarté du propos, rythme, arc émotionnel jusqu'à la fin.
- "call_to_action" : y a-t-il un appel à l'action, est-il efficace, pousse-t-il à interagir ?

NOTE GLOBALE : "virality_score" (0-100) résume ces 4 catégories. Elle doit être COHÉRENTE avec elles et avec "strengths"/"weaknesses" : jamais au-dessus de la meilleure catégorie ni au-dessous de la pire, et une note élevée exige de vrais points forts cités. Ne la calcule pas à part. "score_basis" : 1 phrase rappelant que c'est une estimation basée sur la vidéo, PAS une prédiction de vues garantie.

{publication_text}

Analyse le HOOK réel (les toutes premières secondes : ce qui est dit, écrit à l'écran ou montré) en t'appuyant EN INTERNE sur les "TYPES D'ACCROCHES RÉELLES" du guide de style pour comprendre ce qui se joue — mais dans ta réponse, décris ce que fait ce hook en mots simples (ex : "le spectateur se reconnaît tout de suite dans ce que vous dites"), JAMAIS avec un nom technique de catégorie. Si aucun type ne correspond clairement, dis simplement qu'il n'y a pas vraiment d'accroche identifiable. "hook_excerpt" : ce qui est réellement dit ou écrit dans ces premières secondes, cité tel quel (chaîne vide s'il n'y a ni parole ni texte).

CONFORMITÉ ("policy_check") : vérifie aussi que la vidéo respecte les règles de modération de TikTok, Instagram, YouTube et Facebook (violence, nudité, discours haineux, propos trompeurs, contenu manifestement protégé, produits réglementés...). "status" = "ok" si rien de problématique n'est VISIBLE ou AUDIBLE ; "risk" seulement si tu vois ou entends un vrai problème, décrit en 1-3 phrases simples dans "issues" (sinon liste vide). Jamais un risque supposé.

MOMENTS DANS LA VIDÉO : tu estimes, tu ne mesures pas. Si tu situes un passage, reste approximatif ("vers le début", "autour de la dixième seconde"), jamais une seconde exacte.

RAPPEL LE PLUS IMPORTANT (règle hybride, RÈGLE D'OR N°2 du guide de style) : "strengths" PEUT citer LE chiffre le plus marquant SEULEMENT si une vraie donnée chiffrée est fournie ci-dessus (ex: la moyenne du compte) et qu'elle prouve une réussite — sinon reste en mots simples, n'invente jamais un chiffre. "hook_type", "weaknesses" et "action_plan" restent SANS AUCUN CHIFFRE. VOUVOIEMENT OBLIGATOIRE ("vous", "votre", "vos" — jamais "tu"/"ton"/"tes") et mots simples, niveau CM2 : phrases courtes, une idée par phrase, aucun nom technique de catégorie d'accroche. "weaknesses" et "action_plan" doivent être des INSTRUCTIONS à l'impératif (RÈGLE D'OR N°3 du guide de style), pas des observations : "weaknesses" = ce qu'il NE FAUT PAS faire ("Arrêtez de..."), "action_plan" = ce qu'il FAUT faire à la place ("Faites...", "Commencez par...").

BRIÈVETÉ (important) : 1-2 éléments MAXIMUM dans "strengths", "weaknesses" et "action_plan", 3-5 hashtags sans le #, une légende TikTok courte et accrocheuse cohérente avec le vrai contenu. Réponse courte et directe, lisible en 15 secondes."""


async def _analyze_video_with_gemini(
    video_bytes: bytes, mime_type: str, prompt: str, ui_lang: str, response_schema: dict
) -> dict:
    """
    Envoie la vidéo brute (images + son) à Gemini avec le guide de style en
    instruction système, et renvoie l'analyse structurée (JSON garanti par
    responseSchema). Lève une HTTPException explicite à chaque étape qui
    peut échouer.
    """
    lang = ui_lang if ui_lang in _CACHED_SYSTEM_BLOCKS else DEFAULT_LANG
    uploaded_name = None
    try:
        # Timeouts larges : l'envoi d'une grosse vidéo peut durer plusieurs minutes sur une connexion lente.
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30, read=300, write=300, pool=30)) as client:
            if len(video_bytes) <= GEMINI_INLINE_MAX_BYTES:
                video_part = {
                    "inline_data": {"mime_type": mime_type, "data": base64.b64encode(video_bytes).decode()}
                }
            else:
                file_info = await _gemini_upload_video(client, video_bytes, mime_type)
                uploaded_name = file_info["name"]
                video_part = {"file_data": {"mime_type": mime_type, "file_uri": file_info["uri"]}}

            response = await client.post(
                f"{GEMINI_API_BASE}/v1beta/models/{GEMINI_MODEL}:generateContent",
                headers=_gemini_headers(),
                json={
                    "systemInstruction": {"parts": [{"text": _CACHED_SYSTEM_BLOCKS[lang]}]},
                    "contents": [{"role": "user", "parts": [video_part, {"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.4,
                        "maxOutputTokens": 4000,
                        "responseMimeType": "application/json",
                        "responseSchema": response_schema,
                        "mediaResolution": "MEDIA_RESOLUTION_LOW",
                    },
                },
            )

            if uploaded_name:
                try:
                    await client.delete(f"{GEMINI_API_BASE}/v1beta/{uploaded_name}", headers=_gemini_headers())
                except httpx.HTTPError:
                    pass  # best effort : Google supprime de toute façon le fichier après 48 h
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Erreur réseau vers le service d'analyse vidéo.")

    if response.status_code != 200:
        try:
            message = response.json().get("error", {}).get("message", "")
        except ValueError:
            message = ""
        raise HTTPException(
            status_code=502,
            detail=f"Erreur du service d'analyse vidéo: {response.status_code} {message[:300]}",
        )

    data = response.json()
    if data.get("promptFeedback", {}).get("blockReason"):
        raise HTTPException(status_code=422, detail="Cette vidéo n'a pas pu être analysée (contenu refusé par le service d'IA).")
    candidates = data.get("candidates") or []
    parts = (candidates[0].get("content", {}).get("parts") if candidates else None) or []
    raw_text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not raw_text:
        raise HTTPException(status_code=502, detail="Réponse IA vide.")
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Réponse IA invalide.")


def _round_sig(value: float, digits: int = 2) -> int:
    if value <= 0:
        return 0
    step = 10 ** max(int(math.floor(math.log10(value))) - (digits - 1), 0)
    return int(round(value / step) * step)


def _build_estimate(band: str, avg_views: int, basis: str) -> dict:
    """
    Convertit le palier choisi par Gemini en fourchettes de vues/likes/
    commentaires, ancrées sur la moyenne RÉELLE du compte. Sans moyenne
    connue, aucun chiffre (RÈGLE D'OR N°1) : seul le palier est renvoyé.
    """
    estimate = {"band": band, "basis": basis, "views": None, "likes": None, "comments": None}
    if avg_views <= 0:
        return estimate
    low_mult, high_mult = PERFORMANCE_BAND_MULTIPLIERS[band]
    views = (_round_sig(avg_views * low_mult), _round_sig(avg_views * high_mult))
    estimate["views"] = list(views)
    estimate["likes"] = [_round_sig(views[0] * ESTIMATED_LIKE_RATE[0]), _round_sig(views[1] * ESTIMATED_LIKE_RATE[1])]
    comments_low = _round_sig(views[0] * ESTIMATED_COMMENT_RATE[0])
    comments_high = max(_round_sig(views[1] * ESTIMATED_COMMENT_RATE[1]), comments_low, 1)
    estimate["comments"] = [comments_low, comments_high]
    return estimate


def _clamp_score(value, default: int = 0) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return default


def _store_video_estimate(row: dict) -> None:
    supabase = get_supabase()
    if not supabase:
        return
    try:
        supabase.table("video_estimate_feedback").insert(row).execute()
    except Exception as exc:  # ne jamais faire échouer l'analyse pour de la mesure interne
        print(f"[video_estimate_feedback] insertion impossible: {exc}")


@app.post("/api/analyze-video-upload", response_class=JSONResponse)
async def analyze_video_upload(
    file: UploadFile = File(...),
    account_avg_views: str = Form(""),
    niche_category: str = Form(""),
    main_challenge: str = Form(""),
    ui_lang: str = Form(DEFAULT_LANG),
    already_published: str = Form(""),
):
    """
    Analyse approfondie d'UNE vidéo importée directement par l'utilisateur
    (téléphone ou machine — jamais récupérée depuis TikTok, l'API ne
    fournit aucun fichier vidéo). La vidéo brute (images + son) est envoyée
    à Gemini en UN seul appel : il voit et entend la vidéo, note 4
    catégories (accroche, impact visuel, narration, appel à l'action),
    en déduit le score de viralité, repère les points forts/faibles et
    vérifie la conformité aux règles des plateformes.

    `already_published` ("true"/"false", réponse à "avez-vous déjà publié
    cette vidéo ailleurs ?") : si vrai, Gemini choisit en plus un palier de
    performance justifié par des éléments concrets, converti côté serveur
    en fourchettes de vues/likes/commentaires ancrées sur
    `account_avg_views` (jamais de chiffre inventé par l'IA). Un
    `analysis_id` est alors renvoyé pour que l'utilisateur confirme ensuite
    via /api/video-estimate-feedback si l'estimation était proche du réel.
    `niche_category` est la niche choisie pour CETTE vidéo, `main_challenge`
    (abonnés/engagement/vues) oriente l'angle du conseil.
    """
    if not GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY manquant dans .env")

    published = already_published.strip().lower() == "true"
    try:
        avg_views = max(int(float(account_avg_views)), 0) if account_avg_views.strip() else 0
    except ValueError:
        avg_views = 0

    video_bytes = await file.read()
    # Garde-fou : 200 Mo max, largement suffisant pour une vidéo TikTok
    # (quelques minutes maximum), évite un upload abusif ou accidentel.
    if len(video_bytes) > MAX_VIDEO_BYTES:
        raise HTTPException(status_code=413, detail="Fichier trop volumineux (200 Mo max).")
    if not video_bytes:
        raise HTTPException(status_code=400, detail="Fichier vide.")
    mime_type = file.content_type if (file.content_type or "").startswith("video/") else "video/mp4"

    result = await _analyze_video_with_gemini(
        video_bytes,
        mime_type,
        _build_video_prompt(niche_category, avg_views, main_challenge, published),
        ui_lang,
        _video_analysis_schema(published),
    )

    # Garde-fous côté serveur : on ne fait jamais confiance aveuglément au
    # modèle pour la cohérence des scores.
    categories = result.get("category_scores") or {}
    cleaned_categories = {}
    for key in VIDEO_CATEGORY_KEYS:
        entry = categories.get(key) or {}
        cleaned_categories[key] = {
            "score": _clamp_score(entry.get("score")),
            "comment": entry.get("comment") or "",
        }
    category_values = [c["score"] for c in cleaned_categories.values()]
    score = _clamp_score(result.get("virality_score"))
    score = max(min(category_values), min(max(category_values), score))
    result["category_scores"] = cleaned_categories
    result["virality_score"] = score

    band = result.pop("performance_band", None)
    basis = result.pop("estimation_basis", "")
    if published and band in PERFORMANCE_BAND_MULTIPLIERS:
        estimate = _build_estimate(band, avg_views, basis)
        analysis_id = str(uuid.uuid4())
        result["estimate"] = estimate
        result["analysis_id"] = analysis_id
        await asyncio.to_thread(
            _store_video_estimate,
            {
                "id": analysis_id,
                "lang": ui_lang,
                "niche_category": niche_category or None,
                "virality_score": score,
                "performance_band": band,
                "account_avg_views": avg_views or None,
                "estimated_views_low": (estimate["views"] or [None, None])[0],
                "estimated_views_high": (estimate["views"] or [None, None])[1],
            },
        )

    return JSONResponse(content=result)


class VideoEstimateFeedback(BaseModel):
    analysis_id: str
    verdict: str


@app.post("/api/video-estimate-feedback", response_class=JSONResponse)
async def video_estimate_feedback(body: VideoEstimateFeedback):
    """
    Enregistre la réponse de l'utilisateur (yes / no / roughly) à la
    question "ces estimations sont-elles proches des résultats réels ?".
    Mesure interne uniquement : n'altère pas le rapport déjà affiché. Une
    seule réponse par analyse (la première gagne).
    """
    if body.verdict not in VIDEO_FEEDBACK_VERDICTS:
        raise HTTPException(status_code=422, detail="Réponse invalide.")
    try:
        uuid.UUID(body.analysis_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Identifiant d'analyse invalide.")

    supabase = get_supabase()
    if not supabase:
        raise HTTPException(status_code=503, detail="Stockage indisponible.")

    def _save():
        return (
            supabase.table("video_estimate_feedback")
            .update({"verdict": body.verdict})
            .eq("id", body.analysis_id)
            .is_("verdict", "null")
            .execute()
        )

    try:
        res = await asyncio.to_thread(_save)
    except Exception as exc:
        print(f"[video_estimate_feedback] mise à jour impossible: {exc}")
        raise HTTPException(status_code=503, detail="Stockage indisponible.")
    if not res.data:
        raise HTTPException(status_code=404, detail="Analyse inconnue ou déjà évaluée.")
    return JSONResponse(content={"ok": True})


WORDS_PER_SECOND_FR = 2.5  # débit oral moyen en français, approximatif
MAX_TRANSCRIPT_WORDS = 1000  # limite de longueur pour /api/analyze-transcript (GET, taille d'URL)


def _extract_hook_portion(transcript: str, hook_seconds: float = 3.0) -> str:
    """
    Isole la portion du transcript correspondant approximativement aux
    premières `hook_seconds` secondes parlées, en se basant sur un débit
    oral moyen. Approximation volontairement simple (pas de vrais
    timestamps mot-par-mot) mais bien plus précise que de prendre les 3
    premiers mots ou la première phrase au hasard.
    """
    words = transcript.strip().split()
    n_words = max(1, int(hook_seconds * WORDS_PER_SECOND_FR))
    return " ".join(words[:n_words])


@app.get("/api/analyze-transcript", response_class=JSONResponse)
async def analyze_transcript(
    transcript: str,
    duration_seconds: float = 0,
    claimed_views: int = 0,
    claimed_likes: int = 0,
    claimed_comments: int = 0,
    claimed_shares: int = 0,
    niche_category: str = "",
    main_challenge: str = "",
    ui_lang: str = DEFAULT_LANG,
):
    """
    Analyse un transcript de vidéo TikTok déjà transcrit (audio → texte
    fait en amont, par ex. via /api/analyze-video-upload ou un pipeline
    externe) : hook réellement isolé par débit de parole (pas une simple
    troncature), rythme mesuré, structure découpée en parties citées
    littéralement, points forts/faibles ancrés dans des extraits réels du
    texte — pour une analyse concordante avec le contenu réel de la
    vidéo plutôt qu'un résultat vague et générique.

    Sert aussi bien pour la propre vidéo de l'utilisateur que pour celle
    d'un créateur qui l'inspire, téléchargée légalement par l'utilisateur
    lui-même (jamais par scraping/lien direct — voir la politique du
    projet). Les stats (claimed_*) sont déclarées manuellement par
    l'utilisateur (visibles par lui sur TikTok) : aucune API ne permet de
    les récupérer automatiquement pour une vidéo hors du compte connecté.

    `niche_category`/`main_challenge` viennent du mini-questionnaire
    d'onboarding de la page "Analyser le script" (même structure que
    "Analyser la vidéo") : oriente l'angle des instructions données,
    sans jamais inventer de statistique.
    """
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY manquant dans .env")
    if not transcript or not transcript.strip():
        raise HTTPException(status_code=422, detail="Le transcript ne peut pas être vide.")

    word_count = len(transcript.split())
    if word_count > MAX_TRANSCRIPT_WORDS:
        raise HTTPException(
            status_code=422,
            detail=f"Le script est trop long ({word_count} mots). Limite actuelle : {MAX_TRANSCRIPT_WORDS} mots.",
        )

    hook_portion = _extract_hook_portion(transcript)
    estimated_duration = duration_seconds or round(word_count / WORDS_PER_SECOND_FR, 1)
    words_per_second_actual = (
        round(word_count / duration_seconds, 2) if duration_seconds > 0 else None
    )

    has_stats = claimed_views > 0
    if has_stats:
        engagement_rate = round(
            (claimed_likes + claimed_comments + claimed_shares) / claimed_views * 100, 2
        )
        is_viral = claimed_views >= VIRAL_VIEW_THRESHOLD
        stats_block = f"""
Statistiques réelles déclarées par l'utilisateur (visibles par lui sur TikTok) :
- Vues : {claimed_views}
- Likes : {claimed_likes}, Commentaires : {claimed_comments}, Partages : {claimed_shares}
- Taux d'engagement calculé : {engagement_rate}%
- Statut viral (seuil {VIRAL_VIEW_THRESHOLD} vues) : {"OUI, cette vidéo EST virale" if is_viral else "NON, cette vidéo n'a PAS dépassé le seuil viral"}

Base ton "score de viralité" et ton diagnostic sur CES VRAIS CHIFFRES,
pas sur une estimation abstraite. Si la vidéo n'est pas virale malgré un
bon transcript apparent, dis-le honnêtement et cherche pourquoi dans le
texte (décalage entre qualité perçue du script et performance réelle)."""
    else:
        stats_block = """
Aucune statistique réelle fournie. Le "score de viralité" que tu donnes
est donc une ESTIMATION basée uniquement sur la structure du transcript
— précise-le explicitement dans le résumé, ne fais pas comme si
c'était un fait vérifié."""

    challenge_text = {
        "followers": "L'utilisateur dit que son plus gros défi est de gagner des ABONNÉS : oriente tes instructions vers ce qui donne envie de suivre le compte (personnalité, régularité, promesse de contenu à venir).",
        "engagement": "L'utilisateur dit que son plus gros défi est l'ENGAGEMENT (likes/commentaires) : oriente tes instructions vers ce qui pousse à réagir ou commenter (question ouverte, avis tranché, appel à réagir).",
        "reach": "L'utilisateur dit que son plus gros défi est la PORTÉE/les VUES : oriente tes instructions vers ce qui retient dès la première seconde et jusqu'au bout (accroche, rythme).",
    }.get(main_challenge, "Défi principal non précisé — reste équilibré entre accroche, rétention et appel à l'action.")

    prompt = f"""DONNÉES DISPONIBLES :
- Transcript complet ({word_count} mots, durée {"réelle" if duration_seconds else "estimée"} ~{estimated_duration}s) :
"{transcript}"

- Portion correspondant approximativement aux 3 premières secondes parlées
  (calculée à partir du débit oral, PAS une simple troncature arbitraire) :
"{hook_portion}"

{f"- Débit réel mesuré : {words_per_second_actual} mots/seconde (moyenne naturelle en français : ~2.5)" if words_per_second_actual else ""}
Niche du script : {niche_category or "non précisée"}
{challenge_text}
{stats_block}

MÉTHODE D'ANALYSE (obligatoire, avant de répondre) :
1. Analyse la portion "hook" isolée ci-dessus EN T'APPUYANT sur les
   "TYPES D'ACCROCHES RÉELLES" du guide de style ci-dessus (distillées
   d'un corpus de 84 scripts de créateurs réels) : identifie EN INTERNE
   laquelle de ces mécaniques s'en rapproche le plus (cadrage négatif,
   miroir, insider, contraste/retournement...), mais décris-la dans ta
   réponse en mots simples, jamais avec un nom technique de catégorie —
   pose-t-elle une question, une promesse, une tension immédiate ? Ou
   démarre-t-elle par une mise en contexte lente (signe fréquent de
   perte d'audience dans les 3 premières secondes) ?
2. Analyse le RYTHME global : le débit mesuré (si disponible) est-il
   rapide (>3 mots/s, signe de dynamisme) ou lent (<2 mots/s, risque de
   décrochage) ? Y a-t-il des variations de rythme dans le texte
   (phrases courtes qui cassent le débit = respiration/emphase probable) ?
3. Découpe la STRUCTURE en 2-4 parties logiques du transcript (ex: hook
   / mise en tension / résolution / appel à l'action) en citant à quel
   endroit du texte chaque partie commence.
4. Chaque point fort/faible doit citer un EXTRAIT LITTÉRAL du transcript
   (entre guillemets), jamais une généralité du type "bon rythme".

RAPPEL IMPORTANT : vouvoiement obligatoire ("vous", "votre", "vos" —
jamais "tu"/"ton"/"tes", voir TON À ADOPTER du guide de style), niveau
CM2 (phrases courtes, mots simples). Un chiffre réel déclaré peut
apparaître (règle d'or n°2, il prouve une vraie réussite ou une vraie
contre-performance) mais reste précis, jamais une liste de statistiques
brutes.

Réponds avec un objet JSON (pas de markdown, pas de balises de code),
dans la langue précisée au tout début de tes instructions, avec
exactement ces champs :
{{
  "virality_score": nombre entre 0 et 100 (basé sur les vraies stats si fournies, sinon estimation clairement signalée dans le résumé),
  "hook_analysis": "2-3 phrases analysant PRÉCISÉMENT la portion hook citée ci-dessus, avec un extrait entre guillemets, décrivant la mécanique en mots simples (jamais le nom technique de la catégorie)",
  "rhythm_analysis": "2-3 phrases sur le rythme/débit, citant le chiffre mots/seconde si disponible",
  "structure_breakdown": ["liste de 2-4 parties identifiées, chacune avec l'extrait qui la démarre entre guillemets"],
  "strengths": ["2-3 points forts, CHACUN avec un extrait littéral entre guillemets"],
  "weaknesses": ["2-3 instructions à l'impératif ('Arrêtez de...', 'Commencez par...'), CHACUNE justifiée par un extrait littéral entre guillemets ou un passage manquant identifié"],
  "why_it_worked_or_not": "3-4 phrases d'explication causale, reliant les stats réelles (si fournies) aux éléments concrets du transcript"
}}"""

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
                    "max_tokens": 2000,
                    "output_config": {"effort": "low"},
                    "messages": _cached_messages(prompt, ui_lang),
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
        analysis = json.loads(cleaned)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Réponse IA invalide, impossible de l'analyser.")

    return JSONResponse(content=analysis)


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
