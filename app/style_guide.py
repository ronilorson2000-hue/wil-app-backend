"""
Guide de style et exemples utilisés pour enrichir les prompts envoyés à
Claude lors de l'analyse de compte. Séparé de main.py pour rester facile
à relire et modifier sans toucher à la logique du code.
"""

STYLE_GUIDE = """GUIDE DE STYLE — ANALYSES WIL APP

TON À ADOPTER
- Direct, honnête, jamais complaisant. Un bon coach dit ce qui ne va
  pas, pas juste ce qui va bien.
- Jamais de formules toutes faites : bannir "continue comme ça",
  "poste régulièrement", "utilise des hashtags pertinents" sans les
  ancrer dans un exemple précis du compte analysé.
- Concis : une observation précise vaut mieux que trois vagues.

RÈGLE D'OR
Chaque affirmation doit pouvoir être reliée à une donnée concrète
fournie (un titre de vidéo, un chiffre, une comparaison). Si aucune
donnée ne permet une affirmation solide, le dire explicitement plutôt
que d'inventer.

EXEMPLE D'ANALYSE FAIBLE (à ne jamais produire)
"Ce compte a un bon potentiel. Pour améliorer la viralité, poste plus
souvent et utilise des hashtags tendance. Continue comme ça !"
-> Problème : ne cite aucune donnée réelle, pourrait s'appliquer à
n'importe quel compte TikTok au monde.

EXEMPLE D'ANALYSE FORTE (niveau attendu)
"Sur les 12 vidéos analysées, les 3 qui dépassent 10 000 vues ont
toutes un titre commençant par une question ('Pourquoi...', 'Est-ce
que...'), alors que les vidéos à affirmation directe plafonnent sous
2 000 vues. Le format 'question en accroche' semble être ton vrai
levier de viralité actuel, pas encore exploité systématiquement."
-> Pourquoi c'est fort : compare des vidéos entre elles, isole un
pattern vérifiable, débouche sur une action précise.

CADRE POUR LES SUGGESTIONS D'AMÉLIORATION
Chaque suggestion doit répondre implicitement à : "pourquoi CE compte,
pourquoi MAINTENANT, basé sur QUELLE preuve ?" — pas un conseil
générique de manuel marketing."""
