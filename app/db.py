"""
Client Supabase partagé pour le backend, initialisé une seule fois à
partir des variables d'environnement SUPABASE_URL / SUPABASE_KEY.

IMPORTANT : SUPABASE_KEY doit être la clé "service_role" (accès complet,
trouvable dans Project Settings > API du dashboard Supabase), jamais la
clé "anon" — et cette clé ne doit JAMAIS être exposée côté client
(Flutter, JS de la page web), seulement dans les variables d'env du
backend (Render).
"""

import os

from supabase import Client, create_client

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

_client: Client | None = None


def get_supabase() -> Client | None:
    """
    Renvoie le client Supabase partagé, ou None si les variables d'env ne
    sont pas configurées. Permet au backend de continuer à tourner (avec
    les anciens stockages en mémoire en repli) tant que Supabase n'est
    pas branché, plutôt que de planter au démarrage.
    """
    global _client
    if _client is None and SUPABASE_URL and SUPABASE_KEY:
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client
