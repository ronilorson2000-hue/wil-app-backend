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

import os
import secrets
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse

# Charge les variables du fichier .env (clés TikTok, redirect URI, etc.)
load_dotenv()

TIKTOK_CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY")
TIKTOK_CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET")
TIKTOK_REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI")

# On garde en mémoire les "state" générés, pour vérifier que la réponse
# de TikTok correspond bien à une demande qu'on a nous-même initiée
# (protection basique contre les attaques CSRF). En production, on
# utiliserait plutôt une vraie base de données ou des sessions signées.
_pending_states: set[str] = set()

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


@app.get("/", response_class=HTMLResponse)
def home():
    """
    Page d'accueil avec un bouton "Se connecter avec TikTok" et des liens
    visibles vers les CGU et la politique de confidentialité (exigés par
    TikTok directement sur cette page, sans menu ni connexion requise).
    """
    return """
    <html>
      <head>
        <title>Wil App</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
      </head>
      <body style="font-family: sans-serif; text-align: center; margin-top: 100px;">
        <h1>Wil App</h1>
        <p>Wil App helps TikTok creators understand and grow their account.</p>
        <a href="/auth/tiktok/login"
           style="display:inline-block; padding: 14px 28px; background:#000;
                  color:#fff; border-radius:8px; text-decoration:none;">
          Se connecter avec TikTok
        </a>
        <footer style="margin-top: 60px; font-size: 14px;">
          <a href="https://ronilorson2000-hue.github.io/wil-app-legal/terms.html">Terms of Service</a>
          &nbsp;|&nbsp;
          <a href="https://ronilorson2000-hue.github.io/wil-app-legal/privacy.html">Privacy Policy</a>
        </footer>
      </body>
    </html>
    """


@app.get("/tiktokduU5VyZDYUA3xEXGVEkwALeLjZu2rBIn.txt", response_class=PlainTextResponse)
def tiktok_site_verification():
    """
    Route qui sert le fichier de vérification de propriété demandé par
    TikTok for Developers (Verify URL properties). Le contenu doit
    correspondre EXACTEMENT à celui fourni par TikTok, sans espace ni
    ligne supplémentaire.
    """
    return "tiktok-developers-site-verification=duU5VyZDYUA3xEXGVEkwALeLjZu2rBIn"


@app.get("/auth/tiktok/login")
def tiktok_login():
    """
    Étape 1 du flow OAuth : on redirige l'utilisateur vers la page
    d'autorisation de TikTok. Il va s'y connecter (avec un compte test
    Sandbox pour l'instant) et accepter de partager ses infos avec nous.
    """
    if not TIKTOK_CLIENT_KEY or not TIKTOK_REDIRECT_URI:
        raise HTTPException(
            status_code=500,
            detail="TIKTOK_CLIENT_KEY ou TIKTOK_REDIRECT_URI manquant dans .env",
        )

    # Le "state" est une chaîne aléatoire qu'on va retrouver plus tard
    # dans la réponse de TikTok, pour vérifier que c'est bien nous qui
    # avons initié cette demande de connexion (sécurité anti-CSRF).
    state = secrets.token_urlsafe(24)
    _pending_states.add(state)

    params = {
        "client_key": TIKTOK_CLIENT_KEY,
        "scope": "user.info.basic,user.info.profile",
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

    # Avec l'access_token en main, on peut maintenant appeler l'API
    # TikTok pour récupérer les infos de profil de l'utilisateur.
    async with httpx.AsyncClient() as client:
        user_response = await client.get(
            "https://open.tiktokapis.com/v2/user/info/",
            params={"fields": "open_id,display_name,avatar_url,username"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    user_data = user_response.json()

    user_info = user_data.get("data", {}).get("user", {})
    display_name = user_info.get("display_name", "Utilisateur TikTok")
    avatar_url = user_info.get("avatar_url", "")
    username = user_info.get("username", "")

    # Page de confirmation simple, qui prouve que le flow fonctionne
    # de bout en bout — c'est cette page que tu montreras dans ta vidéo
    # de démo pour TikTok.
    return f"""
    <html>
      <body style="font-family: sans-serif; text-align: center; margin-top: 100px;">
        <h1>Connexion réussie 🎉</h1>
        <img src="{avatar_url}" style="width:120px; border-radius:50%;" />
        <p><strong>{display_name}</strong></p>
        <p>@{username}</p>
      </body>
    </html>
    """
