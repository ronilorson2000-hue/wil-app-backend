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
    # récupérées via l'API, pour donner un aperçu concret du service
    # (pas juste un écran de confirmation vide).
    return f"""
    <html>
      <head>
        <title>Wil App — Dashboard</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
          body {{ font-family: -apple-system, Arial, sans-serif; text-align: center;
                  margin: 0; padding: 60px 20px; color: #1a1a1a; }}
          .card {{ max-width: 420px; margin: 0 auto; border: 1px solid #eee;
                   border-radius: 14px; padding: 32px; box-shadow: 0 4px 16px rgba(0,0,0,0.06); }}
          img {{ width: 110px; height: 110px; border-radius: 50%; object-fit: cover; }}
          h2 {{ margin: 16px 0 4px; }}
          .username {{ color: #777; margin: 0 0 8px; }}
          .stats {{ display: flex; justify-content: center; gap: 24px; margin-top: 24px;
                    padding-top: 20px; border-top: 1px solid #eee; font-size: 14px; color: #555; }}
          a.home {{ display:inline-block; margin-top: 30px; color:#555; }}
        </style>
      </head>
      <body>
        <p style="color:#22c55e; font-weight:bold;">✅ Connected successfully</p>
        <div class="card">
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
        <a href="/" class="home">← Back to Wil App</a>
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
