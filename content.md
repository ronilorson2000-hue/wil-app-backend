# Wil App — Brief de contenu pour Lovable

Ce document sert de base à la génération d'une interface frontend soignée
pour Wil App via Lovable. Il ne contient **aucune logique** à coder : uniquement
la présentation, le contenu réel des pages, et la direction de design à suivre.
Voir la section 6 pour la contrainte de branchement à l'API backend existante.

---

## 1. Présentation de l'application

**Nom :** Wil App

**Mission :** Aider les créateurs TikTok à comprendre pourquoi leurs vidéos
marchent (ou pas), et à faire grandir leur compte grâce à une analyse
détaillée propulsée par l'IA — viralité, engagement, hashtags, accroches,
rythme, structure de script.

**Positionnement :** Un outil d'analytics et de coaching pour créateurs TikTok,
centré sur le diagnostic concret (pas de conseils génériques) : chaque
recommandation s'appuie sur les vraies données du compte connecté ou sur le
vrai texte/contenu fourni par le créateur, jamais sur des suppositions vagues.

**Titre d'accroche actuel (page d'accueil) :** *"Comprends pourquoi tes
vidéos marchent — ou pas"*

---

## 2. Audience cible

Créateurs de contenu TikTok, tous niveaux — du débutant qui cherche à percer
au créateur déjà actif qui veut professionnaliser son approche (accroches,
rythme, régularité, niche). Public familier avec TikTok et ses codes, à l'aise
avec un outil self-service en ligne.

---

## 3. Direction de design

- **Couleur dominante : bleu**, moderne et vif. Palette déjà en place dans le
  produit actuel (à réutiliser pour rester cohérent) :
  - `#2563EB` (blue-600) — couleur primaire (boutons, éléments actifs, chiffres clés)
  - `#38BDF8` (sky-400) — accent secondaire, utilisé en dégradé avec le bleu primaire (ex: `from-blue-600 to-sky-400`) sur le CTA principal et le logo
  - `#1D4ED8` (blue-700) — état hover / variante plus foncée
  - `#EFF6FF` (blue-50) — fonds très clairs (badges, tags, fond de page du dashboard)
  - `#0F172A` (slate-900) — texte principal
  - `#64748B` (slate-500) — texte secondaire
  - `#E2E8F0` (slate-200) — bordures discrètes
  - `#16A34A` (green-600) — succès (ex: "Connected successfully")
  - `#DC2626` (red-600) — erreurs
- **Typographie :** Inter (Google Fonts), moderne et claire, avec une vraie
  hiérarchie de graisses (400 à 800). Poppins acceptable en alternative si
  Inter n'est pas disponible.
- **Style général :** épuré, façon landing page SaaS actuelle — beaucoup
  d'espace blanc, cartes arrondies (`rounded-2xl`, ~16px), ombres légères et
  discrètes, pas de surcharge visuelle.
- **Icônes :** le produit actuel utilise des emojis comme icônes légères
  (📊 🔒 🎯 🔥 🎬 📝 💡 ✅ ⚠️ 🏷 🧭 🚀 🔗). Lovable peut les garder tels quels ou
  les remplacer par une iconographie plus soignée (Lucide/Heroicons) en
  conservant exactement le même sens à chaque endroit.

---

## 4. Structure des pages/sections (contenu réel, pas de placeholder)

### 4.1 Page d'accueil (`/`)

**Navigation :** logo "Wil App" à gauche + liens d'ancre (Services, How It
Works, Pricing, About, Contact) + bouton "Se connecter" (bleu plein) à droite.

**Hero :**
- Badge : "Analyse TikTok propulsée par l'IA"
- Titre (H1) : "Comprends pourquoi tes vidéos marchent — ou pas"
- Tagline : "Analytics and insights for TikTok creators. Connecte ton compte
  et reçois un diagnostic clair de ta viralité, tes hashtags et tes
  accroches."
- CTA principal (dégradé bleu) : **"Se connecter avec TikTok"**

**Section "Our Services"** (3 cartes) :
1. 📊 **Account Overview** — "Connect your TikTok account to see your
   profile information and account activity gathered in one simple
   dashboard."
2. 🔒 **Secure Authentication** — "Wil App uses TikTok's official Login Kit.
   We never see or store your TikTok password, and access can be revoked at
   any time."
3. 🎯 **Built for Creators** — "Designed specifically to help TikTok
   creators better understand their own account and presence on the
   platform."

**Section "How It Works"** (3 étapes numérotées) :
1. **Connect your account** — "Log in securely with your TikTok account
   using the button above."
2. **Authorize access** — "Review and approve the permissions Wil App
   requests, directly on TikTok."
3. **View your overview** — "See your connected profile information right
   away in your Wil App dashboard."

**Section "Pricing"** (2 cartes) :
- **Free** — $0/month : ✔ Connect your TikTok account · ✔ Basic profile
  overview
- **Pro** — Coming soon : ✔ Everything in Free · ✔ Advanced account
  insights · ✔ Priority support

**Section "About" :** "Wil App is an independent project built to give
TikTok creators a simple, secure way to connect their account and view
their profile information in one place. The project is under active
development, with more account insight features on the way."

**Section "Contact" :** "Questions about Wil App? Reach us at
contact.wilapp@proton.me"

**Footer :** liens "Terms of Service" / "Privacy Policy", puis
"© 2026 Wil App. All rights reserved."

---

### 4.2 Dashboard (après connexion TikTok réussie)

- Message de confirmation : "✅ Connected successfully"
- **Carte profil :** photo de profil, nom + badge "✔ Verified" si le compte
  est certifié, `@username`, bio (si renseignée), lien "View TikTok profile
  ↗" (si disponible), deux indicateurs "🔗 Account linked" / "🔒 Data
  secured"
- **3 boutons d'action** en haut, sur une seule ligne, fond bleu plein et
  texte blanc — chacun ouvre sa propre page dédiée (voir 4.3 à 4.5) :
  - 🎬 Analyser la vidéo
  - 📝 Analyser le script
  - 💡 Idées de vidéo
- **Carte "Score de viralité du compte" :** gros score sur 100 avec icône
  couleur selon le niveau (🔴 faible · 🟡 moyen · 🟠 bon · 🔵 excellent),
  nombre de vidéos analysées, barre de progression, pourcentage de vidéos
  virales vs non virales, taux d'engagement moyen, ratio likes/abonnés
- **Carte "Rapport IA" :** badge niche (ex: "Fitness", "Humour"...), résumé
  en une phrase, bloc optionnel "🧭 Plusieurs sujets détectés sur ton
  compte" (si le compte couvre plusieurs niches, avec tags + conseil de
  focalisation), liste "✅ Points forts", liste "📈 À améliorer", bloc
  optionnel "🏷 Diagnostic hashtags", puis "Hashtags suggérés" (tags `#`)
- **Carte "Détail par vidéo" :** liste des vidéos du compte (miniature,
  score de viralité individuel, nombre de vues), chaque vidéo a un bouton
  "Analyser la vidéo" qui déplie un mini-rapport : "🔍 Le vrai problème",
  "✅ Points forts", "⚠️ À éviter", "🎯 À faire"
- Lien retour : "← Back to Wil App"

---

### 4.3 Page "Analyser la vidéo" (`/tools/analyze-video`)

- Titre : "Analyse approfondie d'une vidéo"
- Sous-titre : "Importe le fichier vidéo (déjà postée ou pas encore) depuis
  ton téléphone ou ta machine — on transcrit le vrai contenu parlé pour
  analyser ton accroche précisément."
- Zone d'upload de fichier vidéo + bouton "Analyser cette vidéo" (état de
  chargement : "Transcription et analyse en cours (peut prendre 1-2
  min)...")
- Résultat affiché : "🎬 Hook réel" (citation exacte + type d'accroche),
  "✅ Points forts", "⚠️ Points faibles", "🎯 Pour percer"

---

### 4.4 Page "Analyser le script" (`/tools/analyze-script`)

- Titre : "Analyser le script d'une vidéo"
- Sous-titre : "Écris ou colle le script complet de ta vidéo (ce que tu
  comptes dire à l'oral) — on l'analyse comme si c'était déjà tourné pour
  estimer son potentiel de viralité."
- Grande zone de texte dédiée + compteur de mots en direct ("X / 1000
  mots", passe en rouge au-delà de la limite) + bouton "Analyser le script"
- Résultat affiché : "🔥 Score de viralité estimé" (gros chiffre sur 100 en
  bleu), "🎬 Accroche", "⏱️ Rythme", "🧩 Structure" (liste des parties du
  script), "✅ Points forts", "⚠️ À corriger", "🎯 Pourquoi" (explication
  causale)

---

### 4.5 Page "Idées de vidéo" (`/tools/trending-ideas`)

- Titre : "Idées de vidéo"
- Sous-titre : idées de vidéos et types d'accroches qui marchent en ce
  moment, adaptées à la niche du compte connecté
- La recherche se lance automatiquement à l'ouverture de la page (pas de
  clic supplémentaire nécessaire)
- Résultat affiché en deux blocs : "💡 Idées de vidéos tendance" et
  "Accroches qui marchent"

---

## 5. Fonctionnalités techniques à représenter visuellement (sans logique)

- Boutons avec état normal / désactivé+chargement (le texte change, ex:
  "Analyse en cours...", "Transcription et analyse en cours...")
- Cartes de résultats : fond blanc, coins arrondis, ombre légère, contraste
  net sur fond bleu très clair
- Indicateurs numériques/scores avec code couleur (rouge → jaune → orange →
  bleu selon le niveau)
- Barres de progression (% vidéos virales vs non virales)
- Tags/pills pour les hashtags suggérés et les niches détectées
- Compteur de mots/caractères avec seuil visuel (texte qui passe en rouge
  au-delà de la limite)
- Messages d'erreur inline en texte rouge (jamais de popup/alert)
- Zone d'upload de fichier vidéo stylée
- Grande zone de texte pour coller un script

---

## 6. Contrainte technique importante

Ce brief décrit **uniquement le frontend**. Il devra ensuite être connecté à
une vraie API backend FastAPI déjà existante et en production sur
`https://wilapp.tech`, avec des routes déjà fonctionnelles sous `/api/*`
(analyse de compte, de vidéo, de script, idées tendance) et un flow
d'authentification TikTok OAuth (`/auth/tiktok/login`,
`/auth/tiktok/callback`).

**En conséquence :**
- Prévoir une architecture qui permette de remplacer facilement les données
  statiques/mock par de vrais appels `fetch` vers ces endpoints (gestion
  d'état propre par section, pas de données codées en dur enfouies
  profondément dans les composants).
- Ne pas recoder la logique métier (calcul des scores, appels IA, etc.) —
  seulement la présentation, les états de chargement/erreur, et la
  structure des données attendues telle que décrite ci-dessus.
- Les couleurs, la typographie et le style décrits en section 3 sont déjà
  utilisés côté backend (pages actuelles générées en HTML/Tailwind) : les
  respecter garantit une cohérence visuelle totale une fois le frontend
  Lovable branché à la place.
