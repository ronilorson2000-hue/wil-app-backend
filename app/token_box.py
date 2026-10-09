"""
Chiffrement des jetons TikTok stockés dans Supabase (table sessions).

Sans ça, une fuite de la base (sauvegarde, accès mal protégé) donnerait des jetons TikTok
directement utilisables. Avec : seul ce serveur, qui connaît SESSION_SECRET, peut les relire.

- La clé de chiffrement est dérivée de SESSION_SECRET (aucune variable de plus à gérer).
- Les anciens jetons en clair restent lisibles (préfixe « enc: » absent) : migration en douceur.
- Sans SESSION_SECRET ou sans la bibliothèque `cryptography`, on stocke en clair comme avant
  plutôt que de casser la connexion.
- Si SESSION_SECRET change, les jetons déjà chiffrés deviennent illisibles : la session est
  alors considérée comme invalide et l'utilisateur se reconnecte (les jetons TikTok expirent
  de toute façon en 24 h).
"""

import base64
import hashlib
import os

PREFIX = "enc:"


def _fernet():
    secret = os.getenv("SESSION_SECRET", "")
    if not secret:
        return None
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(("wil-token-v1:" + secret).encode()).digest())
    return Fernet(key)


def encrypt_token(plain: str) -> str:
    box = _fernet()
    if box is None:
        return plain
    return PREFIX + box.encrypt(plain.encode()).decode()


def decrypt_token(stored: str) -> str | None:
    """Renvoie le jeton en clair, ou None s'il ne peut pas être déchiffré (session à refaire)."""
    if not stored.startswith(PREFIX):
        return stored
    box = _fernet()
    if box is None:
        return None
    try:
        return box.decrypt(stored[len(PREFIX):].encode()).decode()
    except Exception:
        return None
