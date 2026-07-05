# Blow(n) — Backend

API backend en Python (FastAPI). Voici comment le lancer sur Windows, étape par étape.

## Prérequis

- Python installé (voir instructions données dans la conversation) et vérifié avec `python --version` dans l'invite de commandes.

## Installation (à faire une seule fois)

Ouvre l'invite de commandes **dans le dossier `blowup-backend`** (astuce : dans l'explorateur Windows, ouvre le dossier, clique dans la barre d'adresse, tape `cmd` et appuie sur Entrée — ça ouvre une invite de commandes directement au bon endroit).

Puis tape ces commandes une par une :

```
python -m venv venv
```

Ça crée un "environnement virtuel" : un espace isolé pour les dépendances de CE projet, pour ne pas mélanger avec d'autres projets Python sur ta machine. C'est une bonne pratique standard.

```
venv\Scripts\activate
```

Tu dois voir `(venv)` apparaître au début de la ligne dans l'invite de commandes. Ça veut dire que l'environnement virtuel est actif.

```
pip install -r requirements.txt
```

Ça installe toutes les librairies nécessaires (FastAPI, etc.). Ça peut prendre 1-2 minutes.

## Lancer le serveur

À chaque fois que tu veux démarrer le backend (après avoir activé le venv avec `venv\Scripts\activate` si ce n'est pas déjà fait) :

```
uvicorn app.main:app --reload
```

Tu devrais voir un message du type `Uvicorn running on http://127.0.0.1:8000`.

Ouvre ton navigateur à l'adresse : **http://127.0.0.1:8000/docs**

Tu verras une interface avec la route `/` listée. Clique dessus, puis "Try it out", puis "Execute" — tu dois voir une réponse `{"status": "ok", ...}`. Si tu vois ça, ton backend fonctionne.

Pour arrêter le serveur : `Ctrl + C` dans l'invite de commandes.

## Structure du projet

```
blowup-backend/
├── app/
│   ├── __init__.py
│   └── main.py          <- le point d'entrée de l'API
├── requirements.txt      <- liste des librairies Python nécessaires
├── .env.example           <- modèle pour tes futures clés secrètes TikTok
└── README.md              <- ce fichier
```

## Prochaine étape

Une fois que ce serveur de base tourne chez toi, on ajoutera :
1. La route d'authentification TikTok (OAuth)
2. La connexion à une base de données
3. Les routes d'analyse IA
