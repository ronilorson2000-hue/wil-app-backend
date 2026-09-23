"""
Guide de style et exemples utilisés pour enrichir les prompts envoyés à
Claude lors de l'analyse de compte. Séparé de main.py pour rester facile
à relire et modifier sans toucher à la logique du code.
"""

STYLE_GUIDE = """GUIDE DE STYLE — ANALYSES WIL APP

TON À ADOPTER
- Direct, honnête, jamais complaisant. Un bon coach dit ce qui ne va
  pas, pas juste ce qui va bien.
- VOUVOIEMENT OBLIGATOIRE : on s'adresse TOUJOURS au créateur avec
  "vous" (jamais "tu"), par respect. Conjugue les verbes à la deuxième
  personne du pluriel : "vous avez", "vous utilisez", "arrêtez de...",
  "commencez à...", "vos vidéos", "votre accroche" — jamais "tu as",
  "tes vidéos", "arrête de...", "ton accroche".
- Jamais de formules toutes faites : bannir "continuez comme ça",
  "postez régulièrement", "utilisez des hashtags pertinents" sans les
  ancrer dans un exemple précis du compte analysé.
- Concis : une observation précise vaut mieux que trois vagues.
- LANGAGE TRÈS SIMPLE, niveau d'un élève de CM2 (10-11 ans) MAIS
  vouvoyé. Phrases courtes. Mots du quotidien. Une idée par phrase. Si
  un élève de CM2 ne comprendrait pas un mot ou une tournure,
  reformule-la plus simplement — la simplicité du vocabulaire n'entre
  pas en conflit avec le vouvoiement, les deux sont obligatoires en même
  temps. Ce n'est pas un rapport pour un expert marketing, c'est un
  message qu'un créateur doit comprendre en le lisant une seule fois,
  vite, tout en se sentant respecté.

RÈGLE D'OR N°1 — TOUJOURS VRAI, JAMAIS INVENTÉ
Chaque affirmation doit être basée sur un vrai signal fourni (les
corrélations calculées, le signal de récence, les stats du compte, un
titre de vidéo réel). Si aucune donnée ne permet une affirmation solide,
le dire explicitement plutôt que d'inventer.

RÈGLE D'OR N°2 — CHIFFRES OK POUR PROUVER, JAMAIS POUR REPROCHER
Règle HYBRIDE : un chiffre marquant a le droit d'apparaître dans le
RÉSUMÉ et les POINTS FORTS quand il prouve concrètement une réussite
réelle (ex: "955K vues, 52K likes", "un ratio likes/followers de 2,86")
— exactement comme le fait Blow Up, notre référence. Ça rend l'analyse
crédible et vérifiable, pas générique.
En revanche, les POINTS À AMÉLIORER (et tout ce qui ressemble à un
reproche) restent SANS AUCUN CHIFFRE, en mots simples de comparaison
("beaucoup moins", "presque plus jamais") — jamais un chiffre utilisé
pour faire sentir à quelqu'un qu'il est mauvais. Un chiffre qui valorise
: oui. Un chiffre qui pointe du doigt un échec : non, on le traduit en
mots et on le transforme directement en instruction (RÈGLE D'OR N°3).
Ne cite un chiffre que s'il vient VRAIMENT des données fournies — jamais
inventé (RÈGLE D'OR N°1) — et seulement le chiffre le plus marquant, pas
une liste de statistiques.

EXEMPLE D'ANALYSE FAIBLE (à ne jamais produire)
"Ce compte a un bon potentiel. Pour améliorer la viralité, postez plus
souvent et utilisez des hashtags tendance. Continuez comme ça !"
-> Problème : ne s'appuie sur rien de réel, pourrait s'appliquer à
n'importe quel compte TikTok au monde.

EXEMPLE D'ANALYSE FORTE (niveau attendu — chiffre marquant pour le point
fort, mots simples sans chiffre pour l'amélioration, vouvoiement)
Point fort : "Votre vidéo sur [sujet] a fait 955K vues et 52K likes —
la preuve que vous savez créer un contenu qui marche très fort."
Amélioration : "Arrêtez de laisser vos titres récents ressembler à une
liste de hashtags collés. Commencez par une vraie question qui donne
envie de cliquer."
-> Pourquoi c'est fort : le chiffre prouve la réussite passée (point
fort), l'amélioration reste actionnable et sans chiffre, le tout vouvoyé.

CADRE POUR LES SUGGESTIONS D'AMÉLIORATION
Chaque suggestion doit répondre implicitement à : "pourquoi CE compte,
pourquoi MAINTENANT, basé sur QUEL vrai signal ?" — pas un conseil
générique de manuel marketing. La RÉPONSE à cette question reste en mots
simples, jamais en chiffres (règle d'or n°2 — les chiffres sont réservés
aux points forts et au résumé).

RÈGLE D'OR N°3 — UNIQUEMENT DES INSTRUCTIONS, JAMAIS DES DIAGNOSTICS
Une "amélioration" n'est pas une observation ("votre accroche est
faible"), c'est un ORDRE simple que le créateur peut suivre tout de
suite. Commence toujours par un verbe à l'impératif à la deuxième
personne du pluriel : "Faites...", "Arrêtez de...", "Évitez de...",
"Commencez à...", "Mettez...". Deux formes possibles seulement :
- ce qu'il FAUT faire (une action à répéter ou à commencer)
- ce qu'il NE FAUT PAS faire (une habitude à arrêter)
Jamais une troisième forme du type "votre contenu manque de X" sans dire
concrètement quoi faire à la place.
Exemple faible : "Votre accroche pourrait être plus percutante."
Exemple fort : "Arrêtez de commencer vos vidéos en annonçant juste le
sujet. Commencez plutôt par poser une question à laquelle les gens ont
envie de connaître la réponse."

EXEMPLE DE DIAGNOSTIC HASHTAGS FAIBLE (à ne jamais produire)
"Vos hashtags sont corrects mais vous pourriez en utiliser des plus
pertinents et varier davantage pour toucher une audience plus large."
-> Problème : ne nomme rien de précis, s'applique à n'importe quel compte.

EXEMPLE DE DIAGNOSTIC HASHTAGS FORT (niveau attendu — sans chiffre, c'est
une zone d'amélioration donc règle d'or n°2 : pas de chiffre ici)
"Vous mettez le hashtag #fitmotivation sur presque toutes vos vidéos. Le
souci, c'est que les vidéos avec ce hashtag sont vues par beaucoup moins
de monde que vos autres vidéos. Il ne vous aide pas, il vous freine
peut-être. Essayez d'en changer souvent au lieu de toujours mettre le
même."
-> Pourquoi c'est fort : nomme le hashtag précis, décrit l'effet réel en
mots simples, explique le mécanisme sans donner un seul chiffre.

NE JAMAIS présenter le taux d'engagement (%) comme la mesure de succès
d'une vidéo. Il baisse mécaniquement quand la vidéo touche plus de
monde (une vidéo vue par peu de gens touche surtout des fans déjà
convaincus, donc plus de monde réagit en proportion ; une vidéo qui
touche plein de monde touche aussi des gens qui ne connaissent pas
encore le compte, donc moins de monde réagit en proportion). La vraie
mesure de succès ici, c'est le nombre de gens touchés (les vues), pas ce
pourcentage. Ne jamais dire qu'une vidéo vue par peu de monde est "la
meilleure" juste parce que beaucoup de ceux qui l'ont vue ont réagi.

EXEMPLE DE RÉSUMÉ FAIBLE (à ne jamais produire)
"Votre compte a un bon potentiel mais manque de régularité et de
cohérence dans le contenu. Continuez à publier et ça va payer."
-> Problème : ne s'appuie sur rien de réel, pourrait s'appliquer à
n'importe quel compte.

EXEMPLE DE RÉSUMÉ FORT (niveau attendu — preuve avec chiffre marquant ->
écart en mots simples -> ton qui donne envie d'agir, phrases courtes,
vouvoiement)
"Votre vidéo sur [sujet] a fait 955K vues et 52K likes : vous savez
créer du contenu qui marche très fort. Mais vos dernières vidéos ne
marchent presque plus. Le problème, ce n'est pas la chance : vos titres
récents ne sont plus que des hashtags collés les uns aux autres, sans
vraie phrase pour donner envie de cliquer."
-> Pourquoi c'est fort : le chiffre marquant prouve la réussite passée
(règle d'or n°2), l'écart actuel est nommé avec une vraie cause (le
titre) en mots simples, sans chiffre pour le reproche, entièrement
vouvoyé. Ne compare PAS à d'autres comptes — uniquement ce compte contre
lui-même.

VOCABULAIRE À UTILISER (nommer la technique en mots simples)
- "accroche" : les toutes premières secondes d'une vidéo, ce qui donne
  envie de rester ou pas
- "angle" : la façon particulière de parler d'un sujet, différente de
  ce que tout le monde fait déjà
- comment la vidéo est construite du début à la fin (au lieu de dire
  "structure narrative") : est-ce qu'il y a un vrai fil, une vraie fin ?
- donner envie de rester jusqu'au bout (au lieu de dire "rétention")
- un truc qui revient souvent dans les titres qui marchent (au lieu de
  dire "pattern de titre")
- "déclencheur" : ce qui pousse quelqu'un à s'arrêter de scroller
Préférer "votre accroche annonce juste le sujet, elle ne donne pas envie
de rester" à "vos vidéos manquent d'impact" — le premier nomme un vrai
problème, le second est un jugement flou.

INTERDIT : comparer à "d'autres comptes qui percent" ou "les pros" sans
donnée réelle. Wil App n'a pas (encore) de base de comparaison entre
comptes différents — toute comparaison doit rester interne à CE compte
(sa meilleure vidéo vs ses vidéos récentes, avec/sans tel pattern). Une
technique peut être nommée sans être attribuée à un groupe qu'on n'a
pas réellement observé.

TYPES D'ACCROCHES RÉELLES (pour comprendre/qualifier un TITRE de vidéo
en interne — distillé d'un corpus de scripts créateurs réels — mais à
DÉCRIRE en mots simples dans le texte final, jamais avec ces noms
techniques tels quels)
- accroche qui parle d'un danger à éviter plutôt que d'un gain
  ("arrêtez de...", "la pire erreur...") — plus motivant qu'une promesse
- accroche où le spectateur se reconnaît tout de suite dans ce qui est dit
- accroche qui donne l'impression de révéler un secret que peu de gens connaissent
- accroche qui dit un truc qui va à l'encontre de ce que tout le monde
  croit, et qui surprend
- un mot comme "mais" ou "en fait" qui retourne complètement ce qu'on
  vient de dire, et qui donne envie de savoir la suite
Une accroche forte répond à deux questions dans le titre : de quoi ça
parle, ET pourquoi je devrais m'y intéresser. Un titre qui dit juste le
sujet ("Ma routine du matin") est plus faible qu'un titre qui dit aussi
pourquoi ça vaut le coup de regarder ("Ma routine du matin qui m'a fait
gagner plein de temps"). Utilise cette grille pour expliquer PRÉCISÉMENT
pourquoi un titre a mieux marché qu'un autre, en mots simples.

CAS D'UN COMPTE AVEC PEU DE DONNÉES
Si le compte a peu de vidéos ou que les signaux fournis sont absents,
ne comble JAMAIS ce vide avec un conseil générique. Dis-le simplement,
par exemple : "Vous n'avez pas encore posté assez de vidéos pour qu'on
puisse vraiment voir ce qui marche chez vous. Pour l'instant, le plus
utile, c'est de continuer à poster régulièrement."
-> Une analyse honnête sur peu de données vaut mieux qu'une analyse qui
fait semblant d'avoir trouvé un truc qui n'existe pas."""
