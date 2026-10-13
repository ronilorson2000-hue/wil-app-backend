"""
Erreurs présentées aux clients.

Problème d'origine : le serveur renvoyait des messages techniques (« ANTHROPIC_API_KEY manquant dans .env »,
« Erreur API Anthropic: 400 {réponse brute} »...), toujours en français, que les pages affichaient tels quels.

Principe : chaque erreur reçoit un CODE stable (« busy », « video_too_big »...). Le serveur n'envoie plus que ce
code, un texte français SANS détail technique (pour les clients qui ne traduisent pas, comme l'app mobile), et
d'éventuels paramètres (ex. `max`). Les pages affichent le texte traduit correspondant au code (voir
translations.py : clés err_*). Le détail technique d'origine n'est écrit que dans les journaux du serveur.
"""

import json
import re

# code -> texte français sûr (sert de repli et pour les clients non traduits)
SAFE_MESSAGES_FR = {
    "generic": "Une erreur est survenue. Réessaie dans un instant.",
    "service_unavailable": "Cette fonctionnalité est momentanément indisponible. Réessaie un peu plus tard.",
    "busy": "Notre service d'analyse est très sollicité en ce moment. Réessaie dans une minute.",
    "ai_invalid": "L'analyse n'a pas abouti cette fois. Réessaie, cela suffit en général.",
    "video_unreadable": "Cette vidéo n'a pas pu être lue. Essaie avec un autre fichier (MP4 ou MOV).",
    "video_refused": "Cette vidéo n'a pas pu être analysée : le service d'IA a refusé son contenu.",
    "video_too_big": "Cette vidéo est trop volumineuse (200 Mo maximum).",
    "video_empty": "Le fichier est vide. Choisis une autre vidéo.",
    "video_timeout": "Le traitement de la vidéo prend trop de temps. Réessaie avec une vidéo plus courte.",
    "upload_lost": "L'envoi a été interrompu. Relance l'analyse.",
    "rate_limited": "Trop de demandes en peu de temps. Patiente quelques minutes, puis réessaie.",
    "daily_cap": "Notre service est très sollicité aujourd'hui. Réessaie demain.",
    "quota_used": "Ton analyse gratuite est déjà utilisée. Prends un abonnement pour continuer.",
    "subscription_required": "Cette fonctionnalité est réservée aux abonnés.",
    "session_expired": "Ta session TikTok a expiré. Reconnecte-toi avec TikTok.",
    "tiktok_login_failed": "La connexion TikTok n'a pas abouti. Relance la connexion depuis le début.",
    "script_empty": "Écris ou colle ton script avant de l'analyser.",
    "script_too_long": "Ton script est trop long.",
    "report_not_found": "Ce rapport est introuvable ou a expiré.",
    "not_found": "Cette page n'existe pas.",
    "invalid_request": "La demande n'est pas valide. Recharge la page puis réessaie.",
}

# Réponses d'un service d'IA qui signifient « trop de monde / réessaie » : 429, 500, 502, 503, 504, 529
_UPSTREAM_BUSY = {"429", "500", "502", "503", "504", "529"}

# (motif à repérer dans le message d'origine, code). Le premier qui correspond gagne.
_RULES: list[tuple[str, str]] = [
    ("manquant dans .env", "service_unavailable"),
    ("non configuré", "service_unavailable"),
    ("abonnement requis", "subscription_required"),
    ("analyse gratuite est utilisée", "quota_used"),
    ("session invalide ou expirée", "session_expired"),
    ("très sollicité aujourd'hui", "daily_cap"),
    ("trop de demandes", "rate_limited"),
    ("trop d'envois", "rate_limited"),
    ("refusé par le service d'ia", "video_refused"),
    ("pas pu lire cette vidéo", "video_unreadable"),
    ("prend trop de temps", "video_timeout"),
    ("trop volumineux", "video_too_big"),
    ("fichier vide", "video_empty"),
    ("transcript ne peut pas être vide", "script_empty"),
    ("script est trop long", "script_too_long"),
    ("réponse ia", "ai_invalid"),
    ("envoi introuvable", "upload_lost"),
    ("envoi incomplet", "upload_lost"),
    ("analyse introuvable", "upload_lost"),
    ("morceau", "upload_lost"),
    ("rapport introuvable", "report_not_found"),
    ("state '", "tiktok_login_failed"),
    ("paramètre 'code' manquant", "tiktok_login_failed"),
    ("paramètre 'state' manquant", "tiktok_login_failed"),
    ("paramètre 'challenge'", "tiktok_login_failed"),
    ("connexion mobile sans preuve", "tiktok_login_failed"),
    ("code invalide ou expiré", "tiktok_login_failed"),
]


def classify(status: int, detail) -> tuple[str, dict]:
    """
    Renvoie (code, paramètres) pour une erreur HTTP. `detail` est le message d'origine (jamais envoyé tel quel).
    """
    text = detail if isinstance(detail, str) else ""
    low = text.lower()
    extra: dict = {}
    if low.startswith("erreur api") or "erreur du service d'analyse" in low or "erreur réseau vers" in low or "impossible de récupérer" in low:
        upstream = re.search(r"\b(\d{3})\b", text)
        if "erreur réseau" in low or (upstream and upstream.group(1) in _UPSTREAM_BUSY):
            return "busy", extra
        return "service_unavailable", extra
    for pattern, code in _RULES:
        if pattern in low:
            if code == "script_too_long":
                limit = re.search(r"limite actuelle\s*:\s*(\d+)", low)
                if limit:
                    extra["max"] = int(limit.group(1))
            return code, extra
    if status == 429:
        return "rate_limited", extra
    if status in (401, 403):
        return "session_expired", extra
    if status == 402:
        return "subscription_required", extra
    if status == 404:
        return "not_found", extra
    if status == 413:
        return "video_too_big", extra
    if status in (400, 422):
        return "invalid_request", extra
    if status >= 500:
        return "service_unavailable", extra
    return "generic", extra


def public_payload(status: int, detail) -> dict:
    """Corps JSON envoyé au client : code, texte français sûr et paramètres éventuels. Jamais le détail technique."""
    code, extra = classify(status, detail)
    message = SAFE_MESSAGES_FR.get(code, SAFE_MESSAGES_FR["generic"])
    if code == "script_too_long" and "max" in extra:
        message = f"Ton script est trop long (limite : {extra['max']} mots)."
    return {"detail": message, "error_code": code, **extra}


_ERR_JS = r"""
const WIL_ERR = __E__;
// Texte à afficher pour une erreur du serveur : traduit d'après son CODE, jamais le message brut.
function wilErrText(data, status) {
  const key = data && typeof data.error_code === 'string' ? data.error_code : '';
  let text = key && WIL_ERR[key];
  if (text && data && data.max) { text = text.replace('{max}', data.max); }
  if (text) { return text; }
  if (status === 429) { return WIL_ERR.rate_limited; }
  if (status >= 500) { return WIL_ERR.service_unavailable; }
  return WIL_ERR.generic;
}
"""


def error_js(tt) -> str:
    """JS partagé par les pages : dictionnaire des messages d'erreur dans la langue de la page + wilErrText()."""
    labels = {code: tt("err_" + code) for code in SAFE_MESSAGES_FR if code not in ("quota_used", "subscription_required")}
    labels["quota_used"] = tt("pw_trial_used")
    labels["subscription_required"] = tt("pw_feature_sub")
    return _ERR_JS.replace("__E__", json.dumps(labels, ensure_ascii=False).replace("</", "<\\/"))
