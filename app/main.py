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

import json
import os
import re
import secrets
import time
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
)

from app.style_guide import STYLE_GUIDE

# Charge les variables du fichier .env (clés TikTok, redirect URI, etc.)
load_dotenv()

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# On garde en mémoire les "state" générés, pour vérifier que la réponse
# de TikTok correspond bien à une demande qu'on a nous-même initiée
# (protection basique contre les attaques CSRF). En production, on
# utiliserait plutôt une vraie base de données ou des sessions signées.
_pending_states: set[str] = set()

# Stocke temporairement les access_token après connexion, associés à un
# identifiant de session aléatoire. On ne transmet jamais l'access_token
# brut à l'app/au navigateur : seulement cet identifiant, plus sûr.
# ATTENTION : stockage en mémoire uniquement (perdu si le serveur redémarre) —
# suffisant pour le MVP, à remplacer par une vraie base de données plus tard.
_sessions: dict[str, dict] = {}

# Liste de scopes supplémentaires à demander, en plus des scopes de base
# déjà approuvés en Production. Configurable via variable d'environnement
# pour ne JAMAIS casser la Production tant que TikTok n'a pas approuvé ces
# scopes : on l'active uniquement temporairement en Sandbox pour tester.
# Exemple de valeur : "video.list,user.info.stats"
EXTRA_SCOPES = os.getenv("TIKTOK_EXTRA_SCOPES", "").strip()

# Cache des hashtags tendance par niche (recherche web coûteuse, donc on
# ne la relance qu'une fois par niche par jour, pas à chaque analyse de
# compte). Clé = niche en minuscules, valeur = {"hashtags": [...], "cached_at": timestamp}.
_trending_hashtags_cache: dict[str, dict] = {}
TRENDING_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h


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
    _pending_states.add(state)

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

    return RedirectResponse(authorize_url)


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

    if not code or not state or state not in _pending_states:
        raise HTTPException(status_code=400, detail="Code ou state invalide/manquant")

    # Le state a rempli son rôle, on l'enlève pour ne pas le réutiliser
    _pending_states.discard(state)

    # Échange du code contre un access_token (appel serveur-à-serveur,
    # jamais fait depuis le navigateur pour ne pas exposer le client_secret)
    async with httpx.AsyncClient() as client:
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
    token_data = token_response.json()

    if "access_token" not in token_data:
        return f"<h1>Erreur lors de l'échange du token</h1><pre>{token_data}</pre>"

    access_token = token_data["access_token"]

    # On génère un identifiant de session aléatoire, associé à
    # l'access_token côté serveur. On ne transmettra JAMAIS l'access_token
    # brut à l'app ou au navigateur : seulement cet identifiant, qui sert
    # ensuite de "clé" pour les appels comme /api/videos.
    session_id = secrets.token_urlsafe(24)
    _sessions[session_id] = {"access_token": access_token}

    # Avec l'access_token en main, on peut maintenant appeler l'API
    # TikTok pour récupérer les infos de profil de l'utilisateur.
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            "https://open.tiktokapis.com/v2/user/info/",
            params={
                "fields": "open_id,display_name,avatar_url,username,"
                          "bio_description,profile_web_link,is_verified"
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
    user_data = user_response.json()

    user_info = user_data.get("data", {}).get("user", {})
    display_name = user_info.get("display_name", "TikTok User")
    avatar_url = user_info.get("avatar_url", "")
    username = user_info.get("username", "")
    bio = user_info.get("bio_description", "")
    profile_link = user_info.get("profile_web_link", "")
    is_verified = user_info.get("is_verified", False)

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

              if (stats && stats.total_videos_analyzed > 0) {{
                html += `
                  <div class="card">
                    <p style="font-size:13px;color:#666;">${{stats.total_videos_analyzed}} vidéos analysées (seuil : ${{stats.viral_threshold_views/1000}}k vues)</p>
                    <div class="bar-bg"><div class="bar-fill" style="width:${{stats.viral_percentage}}%"></div></div>
                    <p style="margin-top:12px;"><strong>🚀 ${{stats.viral_percentage}}%</strong> vidéos virales &nbsp;|&nbsp; <strong>${{stats.non_viral_percentage}}%</strong> non virales</p>
                    <p>Taux d'engagement moyen : <strong>${{stats.average_engagement_rate}}%</strong></p>
                  </div>`;
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
                window.__wilBio = "{bio_enc}";
              }}

              if (!html) {{
                html = '<div class="card"><p class="loading">Analyse indisponible pour le moment.</p></div>';
              }}

              document.getElementById('analysis-result').innerHTML = html;

              // Affiche les sections "Idées tendance" et "Générer un script"
              // une fois l'analyse principale terminée (on a besoin de la niche).
              if (report && report.niche) {{
                document.getElementById('extra-tools').style.display = 'block';
              }}
            }})
            .catch(() => {{
              document.getElementById('analysis-loading').innerHTML =
                '<p class="loading">Analyse indisponible pour le moment.</p>';
            }});

          // --- Idées de vidéos et hooks tendance ---
          function loadTrendingIdeas() {{
            const btn = document.getElementById('trending-btn');
            const result = document.getElementById('trending-result');
            btn.disabled = true;
            btn.textContent = 'Recherche en cours...';
            result.innerHTML = '';

            fetch(`/api/trending-ideas?niche=${{encodeURIComponent(window.__wilNiche || '')}}`)
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
MAX_PAGES = 10  # garde-fou : ~200 vidéos max pour éviter un appel trop long


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
                "fields": "id,title,cover_image_url,create_time,"
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


def _compute_engagement(video: dict) -> dict:
    """Calcule le taux d'engagement d'une vidéo et renvoie un dict enrichi."""
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
    - hashtags utilisés uniquement sur des vidéos qui n'ont pas marché
    - vidéos sans aucun hashtag
    """
    all_tags: list[str] = []
    videos_without_tags = 0
    tag_to_engagements: dict[str, list[float]] = {}

    for video in videos:
        tags = video.get("hashtags", [])
        if not tags:
            videos_without_tags += 1
        for tag in tags:
            tag_lower = tag.lower()
            all_tags.append(tag_lower)
            tag_to_engagements.setdefault(tag_lower, []).append(video["engagement_rate"])

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

    # Hashtags dont l'engagement moyen associé est nettement inférieur à
    # la moyenne générale du compte (piste : ce hashtag n'aide pas, voire
    # dessert les vidéos qui l'utilisent).
    overall_avg = (
        sum(v["engagement_rate"] for v in videos) / len(videos) if videos else 0
    )
    underperforming_tags = [
        tag for tag, engagements in tag_to_engagements.items()
        if len(engagements) >= 2 and (sum(engagements) / len(engagements)) < overall_avg * 0.5
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


import re
from collections import Counter


def _extract_hashtags(title: str) -> list[str]:
    """Extrait les hashtags (#mot) d'un titre/légende de vidéo."""
    return re.findall(r"#(\w+)", title or "", flags=re.UNICODE)


def _analyze_hashtag_usage(videos: list[dict]) -> dict:
    """
    Analyse l'usage des hashtags sur l'ensemble des vidéos :
    - fréquence de chaque hashtag
    - répétition excessive (même hashtag sur presque toutes les vidéos)
    - présence ou absence quasi-totale de hashtags
    - engagement moyen des vidéos AVEC hashtags vs SANS hashtags
    """
    total = len(videos)
    all_tags: list[str] = []
    videos_with_tags = 0
    engagement_with = []
    engagement_without = []

    for v in videos:
        tags = _extract_hashtags(v.get("title", ""))
        all_tags.extend(tags)
        if tags:
            videos_with_tags += 1
            engagement_with.append(v["engagement_rate"])
        else:
            engagement_without.append(v["engagement_rate"])

    tag_counts = Counter(t.lower() for t in all_tags)
    most_common = tag_counts.most_common(8)

    avg_with = round(sum(engagement_with) / len(engagement_with), 2) if engagement_with else None
    avg_without = round(sum(engagement_without) / len(engagement_without), 2) if engagement_without else None

    return {
        "videos_with_hashtags": videos_with_tags,
        "videos_without_hashtags": total - videos_with_tags,
        "most_used_hashtags": most_common,  # [(tag, count), ...]
        "avg_engagement_with_hashtags": avg_with,
        "avg_engagement_without_hashtags": avg_without,
        "total_distinct_hashtags": len(tag_counts),
    }


async def _get_trending_hashtags(niche: str) -> list[str] | None:
    """
    Récupère les hashtags réellement tendance pour une niche donnée, via
    l'outil de recherche web de Claude. Résultat mis en cache 24h par
    niche pour limiter le coût et la latence — une recherche par niche
    par jour maximum, pas une par utilisateur/analyse.
    """
    if not niche or not ANTHROPIC_API_KEY:
        return None

    cache_key = niche.strip().lower()
    cached = _trending_hashtags_cache.get(cache_key)
    if cached and (time.time() - cached["cached_at"]) < TRENDING_CACHE_TTL_SECONDS:
        return cached["hashtags"]

    prompt = f"""Cherche sur le web les hashtags TikTok réellement tendance
en ce moment pour la niche suivante : "{niche}".

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
                    "model": "claude-sonnet-4-5-20250929",
                    "max_tokens": 500,
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

        _trending_hashtags_cache[cache_key] = {"hashtags": hashtags, "cached_at": time.time()}
        return hashtags
    except Exception:
        # En cas d'échec (timeout, réponse invalide...), on ne casse pas
        # toute l'analyse — on retombe simplement sur les suggestions
        # génériques déjà présentes dans le rapport IA.
        return None


_trending_ideas_cache: dict[str, dict] = {}


async def _get_trending_content_ideas(niche: str) -> dict | None:
    """
    Récupère, via recherche web, des idées de vidéos et des types de
    hooks (accroches) actuellement tendance pour une niche donnée.
    Résultat mis en cache 24h par niche (même logique que les hashtags
    tendance), pour limiter le coût des recherches web.
    """
    if not niche or not ANTHROPIC_API_KEY:
        return None

    cache_key = niche.strip().lower()
    cached = _trending_ideas_cache.get(cache_key)
    if cached and (time.time() - cached["cached_at"]) < TRENDING_CACHE_TTL_SECONDS:
        return cached["data"]

    prompt = f"""Cherche sur le web les tendances actuelles sur TikTok pour
la niche suivante : "{niche}" — à la fois en termes de formats/idées de
vidéos qui marchent bien en ce moment, et de types d'accroches (hooks)
efficaces actuellement.

Réponds UNIQUEMENT avec un objet JSON (pas de markdown, pas de balises de
code), rédigé en FRANÇAIS, avec exactement ces champs :
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
                    "model": "claude-sonnet-4-5-20250929",
                    "max_tokens": 900,
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

        _trending_ideas_cache[cache_key] = {"data": parsed, "cached_at": time.time()}
        return parsed
    except Exception:
        return None


@app.get("/api/trending-ideas", response_class=JSONResponse)
async def trending_ideas(niche: str):
    """
    Route dédiée : renvoie des idées de vidéos et des hooks tendance pour
    une niche donnée. Peut être appelée séparément de l'analyse complète
    du compte (ex: bouton "Idées tendance" dans l'app), avec le même
    système de cache 24h par niche pour limiter le coût.
    """
    result = await _get_trending_content_ideas(niche)
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
    session_data = _sessions.get(session)
    if not session_data:
        raise HTTPException(
            status_code=401,
            detail="Session invalide ou expirée. Reconnecte-toi avec TikTok.",
        )
    access_token = session_data["access_token"]

    # 1. Récupération de toutes les vidéos + calcul des statistiques.
    # Si le scope "video.list" n'est pas encore approuvé côté TikTok
    # (review en attente), cet appel échoue — dans ce cas, on continue
    # quand même avec une analyse basée uniquement sur le profil, plutôt
    # que de faire échouer toute la route.
    stats = None
    try:
        async with httpx.AsyncClient() as client:
            raw_videos = await _fetch_all_videos(client, access_token)

        enriched_videos = [_compute_engagement(v) for v in raw_videos]
        enriched_videos.sort(key=lambda v: v["engagement_rate"], reverse=True)

        total = len(enriched_videos)
        viral_count = sum(1 for v in enriched_videos if v["view_count"] >= VIRAL_VIEW_THRESHOLD)
        non_viral_count = total - viral_count
        viral_percentage = round(viral_count / total * 100, 2) if total > 0 else 0
        non_viral_percentage = round(non_viral_count / total * 100, 2) if total > 0 else 0
        average_engagement_rate = (
            round(sum(v["engagement_rate"] for v in enriched_videos) / total, 2) if total > 0 else 0
        )

        stats = {
            "total_videos_analyzed": total,
            "average_engagement_rate": average_engagement_rate,
            "viral_threshold_views": VIRAL_VIEW_THRESHOLD,
            "viral_count": viral_count,
            "non_viral_count": non_viral_count,
            "viral_percentage": viral_percentage,
            "non_viral_percentage": non_viral_percentage,
            "best_video": enriched_videos[0] if enriched_videos else None,
            "worst_video": enriched_videos[-1] if len(enriched_videos) > 1 else None,
            "videos": enriched_videos,
        }
    except HTTPException:
        # video.list indisponible (scope pas encore approuvé, ou compte
        # sans vidéo) : on continue sans les stats vidéo, pas bloquant.
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
                    f'\nMeilleure vidéo (engagement) : "{best["title"] or "(sans titre)"}" '
                    f'— {best["view_count"]} vues, {best["like_count"]} likes, '
                    f'{best["engagement_rate"]}% engagement'
                )
            if worst:
                best_worst_text += (
                    f'\nPire vidéo (engagement) : "{worst["title"] or "(sans titre)"}" '
                    f'— {worst["view_count"]} vues, {worst["like_count"]} likes, '
                    f'{worst["engagement_rate"]}% engagement'
                )

            # Analyse des hashtags : répétition, présence, impact sur l'engagement
            hashtag_stats = _analyze_hashtag_usage(videos)
            top_tags_text = ", ".join(
                f"#{tag} ({count} vidéos)" for tag, count in hashtag_stats["most_used_hashtags"]
            ) or "aucun hashtag détecté sur ces vidéos"

            hashtag_block = f"""
Analyse des hashtags utilisés :
- Vidéos avec au moins un hashtag : {hashtag_stats['videos_with_hashtags']}/{len(videos)}
- Vidéos sans aucun hashtag : {hashtag_stats['videos_without_hashtags']}/{len(videos)}
- Nombre de hashtags différents utilisés au total : {hashtag_stats['total_distinct_hashtags']}
- Hashtags les plus utilisés : {top_tags_text}
- Engagement moyen des vidéos AVEC hashtag(s) : {hashtag_stats['avg_engagement_with_hashtags']}%
- Engagement moyen des vidéos SANS hashtag : {hashtag_stats['avg_engagement_without_hashtags']}%"""

            performance_block = f"""
Données de performance (chiffres réels de son compte) :
- Nombre total de vidéos analysées : {stats['total_videos_analyzed']}
- Fréquence de publication : {freq_text}
- Taux d'engagement moyen : {stats['average_engagement_rate']}%
- Vidéos ayant dépassé 10 000 vues ("virales") : {stats['viral_count']} ({stats['viral_percentage']}%)
- Vidéos en dessous de 10 000 vues : {stats['non_viral_count']} ({stats['non_viral_percentage']}%)
{best_worst_text}
{hashtag_block}

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
1. Repère au moins 2 patterns CONCRETS en comparant les titres/stats des
   vidéos entre elles (pas des généralités sur TikTok en général).
2. Chaque point fort et chaque amélioration doit citer un élément
   spécifique de CE compte (un titre, un chiffre, une comparaison) —
   jamais un conseil qui pourrait s'appliquer à n'importe quel compte.
3. Pour le diagnostic hashtags : compare l'engagement moyen avec/sans
   hashtag, regarde si les mêmes hashtags reviennent sur toutes les
   vidéos (répétition excessive = mauvais signal), et détermine si les
   hashtags semblent être un frein à la viralité ou non — base-toi
   UNIQUEMENT sur les chiffres fournis, ne suppose rien d'autre.
4. Si tu ne repères pas de pattern clair par manque de données, dis-le
   honnêtement plutôt que d'inventer un conseil générique.

Réponds avec un objet JSON (pas de markdown, pas de balises de code, juste
du JSON brut) contenant exactement ces champs, avec du texte en FRANÇAIS :
{{
  "niche": "une courte phrase décrivant la niche de contenu probable",
  "summary": "résumé honnête de 3-4 phrases, citant au moins un chiffre ou titre concret",
  "strengths": ["2-3 points forts, CHACUN doit référencer un titre/chiffre précis de ce compte"],
  "improvements": ["2-3 suggestions concrètes et actionnables, CHACUNE justifiée par une comparaison précise entre vidéos de ce compte"],
  "hashtag_diagnosis": "2-3 phrases expliquant si les hashtags actuels aident ou nuisent à la viralité, basé sur les chiffres avec/sans hashtag et la répétition observée",
  "suggested_hashtags": ["5 hashtags pertinents pour cette niche, sans le symbole #"]
}}

Le contenu de chaque champ doit être rédigé entièrement en français."""

        # Note : la recherche web en direct (pour des hashtags vraiment
        # "tendance maintenant") a été désactivée pour l'instant, car plus
        # coûteuse et plus lente. Les hashtags suggérés se basent donc sur
        # les connaissances générales de Claude, pas sur une recherche en
        # temps réel. À réactiver plus tard si besoin (voir version
        # précédente avec le paramètre "tools": [{"type": "web_search_..."}]).
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-5-20250929",
                    "max_tokens": 1200,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )

        if response.status_code == 200:
            raw_text = response.json()["content"][0]["text"]

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

    # 3. Remplace les hashtags génériques par de vrais hashtags tendance
    # (recherche web mise en cache 24h par niche, cf. _get_trending_hashtags).
    # Échec silencieux si indisponible : on garde alors les suggestions
    # génériques déjà produites à l'étape précédente.
    if ai_report and ai_report.get("niche"):
        trending = await _get_trending_hashtags(ai_report["niche"])
        if trending:
            ai_report["suggested_hashtags"] = trending

    return JSONResponse(content={
        "stats": stats,
        "ai_report": ai_report,
    })


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
                "model": "claude-sonnet-4-5-20250929",
                "max_tokens": 700,
                "messages": [{"role": "user", "content": prompt}],
            },
        )

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Erreur API Anthropic: {response.status_code} {response.text}",
        )

    raw_text = response.json()["content"][0]["text"]
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
