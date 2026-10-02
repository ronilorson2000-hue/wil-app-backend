"""
Contenu de départ de la Bibliothèque : affiché quand la recherche web de la
semaine n'est pas disponible (clé manquante, erreur API...) pour que chaque
rubrique ne soit jamais vide. Ce sont des formats et des idées "évergreen"
rédigés à la main, PAS des tendances mesurées : l'interface les présente avec
l'étiquette « Exemple », jamais « Tendance ». Disponible en français et en
anglais ; les autres langues d'interface retombent sur l'anglais.
"""

# Formules de hooks réutilisables, complétées par le sujet de la niche. Aucune
# statistique : ce sont des structures d'accroche, pas des résultats mesurés.
_HOOK_FORMULAS = {
    "fr": [
        "Personne ne vous dit ça sur {topic}, et pourtant ça change tout.",
        "J'ai testé {topic} pendant 30 jours, voici ce qui s'est vraiment passé.",
        "L'erreur que presque tout le monde fait avec {topic}.",
        "Si vous débutez dans {topic}, regardez ça avant de faire quoi que ce soit.",
        "3 choses que j'aurais voulu savoir avant de me lancer dans {topic}.",
        "Arrêtez de faire ça si vous voulez progresser dans {topic}.",
    ],
    "en": [
        "Nobody tells you this about {topic}, and it changes everything.",
        "I tried {topic} for 30 days — here's what really happened.",
        "The mistake almost everyone makes with {topic}.",
        "If you're starting out in {topic}, watch this before doing anything.",
        "3 things I wish I knew before getting into {topic}.",
        "Stop doing this if you want to get better at {topic}.",
    ],
}

# niche -> sujet (avec article en français) utilisé dans les formules de hooks
_TOPICS = {
    "Beauté & Skincare": {"fr": "le skincare", "en": "skincare"},
    "Mode & Style": {"fr": "la mode", "en": "fashion"},
    "Fitness & Sport": {"fr": "le sport", "en": "fitness"},
    "Cuisine & Nutrition": {"fr": "la cuisine", "en": "cooking"},
    "Voyage": {"fr": "le voyage", "en": "travel"},
    "Humour & Divertissement": {"fr": "l'humour", "en": "comedy"},
    "Musique & Danse": {"fr": "la danse", "en": "dance"},
    "Gaming & Tech": {"fr": "le gaming", "en": "gaming"},
    "Business & Finance": {"fr": "l'entrepreneuriat", "en": "business"},
    "Développement personnel": {"fr": "le développement personnel", "en": "self-improvement"},
    "Éducation & Culture générale": {"fr": "la culture générale", "en": "learning"},
    "Lifestyle & Vlog quotidien": {"fr": "le vlog quotidien", "en": "vlogging"},
    "Parentalité & Famille": {"fr": "la parentalité", "en": "parenting"},
    "Art & Créativité": {"fr": "la créativité", "en": "creative work"},
    "Animaux": {"fr": "les animaux", "en": "pets"},
    "Santé & Bien-être": {"fr": "le bien-être", "en": "wellness"},
    "Autre": {"fr": "votre sujet", "en": "your topic"},
}

_IDEAS = {
    "Beauté & Skincare": {
        "fr": ["Ma routine skincare du soir, étape par étape", "Un produit, trois façons de l'utiliser", "Avant/après : 2 semaines avec une seule nouvelle habitude", "Les ingrédients à éviter selon votre type de peau"],
        "en": ["My night skincare routine, step by step", "One product, three ways to use it", "Before/after: 2 weeks with one new habit", "Ingredients to avoid for your skin type"],
    },
    "Mode & Style": {
        "fr": ["Une pièce, cinq tenues", "Une tenue complète avec un petit budget", "Les erreurs de style qui vieillissent une tenue", "Ma garde-robe capsule de la saison"],
        "en": ["One piece, five outfits", "A full outfit on a small budget", "Style mistakes that age an outfit", "My capsule wardrobe for the season"],
    },
    "Fitness & Sport": {
        "fr": ["Un entraînement complet en 10 minutes à la maison", "Mon programme de la semaine, jour par jour", "L'exercice mal fait que tout le monde répète", "Ce que je mange dans une journée d'entraînement"],
        "en": ["A full 10-minute workout at home", "My weekly plan, day by day", "The badly done exercise everyone repeats", "What I eat on a training day"],
    },
    "Cuisine & Nutrition": {
        "fr": ["Une recette en 60 secondes avec trois ingrédients", "Les repas de la semaine préparés en une heure", "Je refais un plat de restaurant à la maison", "Les erreurs qui ratent votre recette préférée"],
        "en": ["A 60-second recipe with three ingredients", "A week of meals prepped in one hour", "I recreate a restaurant dish at home", "Mistakes that ruin your favorite recipe"],
    },
    "Voyage": {
        "fr": ["Mon itinéraire de 3 jours dans une ville, budget compris", "Les pièges à touristes à éviter dans cette destination", "Ce que j'ai mis dans ma valise (et ce que je regrette)", "Un endroit peu connu près de chez vous"],
        "en": ["My 3-day city itinerary, budget included", "Tourist traps to avoid in this destination", "What I packed (and what I regret)", "A little-known spot close to home"],
    },
    "Humour & Divertissement": {
        "fr": ["Les types de personnes dans une situation du quotidien (sketch)", "Je réponds à vos commentaires les plus drôles", "Une situation absurde racontée comme un reportage", "Expliquer un truc simple à ses parents"],
        "en": ["The types of people in an everyday situation (skit)", "I answer your funniest comments", "An absurd situation told like a news report", "Explaining something simple to your parents"],
    },
    "Musique & Danse": {
        "fr": ["Une chorégraphie apprise en une journée", "Je reprends un tube dans un autre style", "Les coulisses de la création d'un morceau", "Un conseil pour progresser en 30 secondes"],
        "en": ["A choreography learned in one day", "I cover a hit in a different style", "Behind the scenes of making a track", "One tip to improve in 30 seconds"],
    },
    "Gaming & Tech": {
        "fr": ["Le réglage qui change tout dans ce jeu", "Je teste un gadget tech pendant une semaine", "Le classement de mes jeux préférés du moment", "Les astuces cachées de votre téléphone"],
        "en": ["The setting that changes everything in this game", "I test a tech gadget for a week", "Ranking my favorite games right now", "Hidden tricks on your phone"],
    },
    "Business & Finance": {
        "fr": ["Comment je gère mon budget mensuel", "Une erreur d'entrepreneur débutant que j'ai faite", "Ce que coûte vraiment un projet, dépenses à l'appui", "Un outil gratuit qui m'économise des heures"],
        "en": ["How I manage my monthly budget", "A beginner entrepreneur mistake I made", "What a project really costs, expenses included", "A free tool that saves me hours"],
    },
    "Développement personnel": {
        "fr": ["Ma routine du matin et ce qu'elle a changé", "Un livre, une idée à appliquer dès aujourd'hui", "Comment je me suis relevé d'un échec", "Une habitude de 5 minutes pour mieux dormir"],
        "en": ["My morning routine and what it changed", "One book, one idea to apply today", "How I bounced back from a failure", "A 5-minute habit to sleep better"],
    },
    "Éducation & Culture générale": {
        "fr": ["Un fait étonnant expliqué en 30 secondes", "Une idée reçue démontée", "L'histoire derrière un objet du quotidien", "Un concept à connaître cette semaine"],
        "en": ["A surprising fact explained in 30 seconds", "A myth debunked", "The story behind an everyday object", "A concept worth knowing this week"],
    },
    "Lifestyle & Vlog quotidien": {
        "fr": ["Une journée dans ma vie, du réveil au coucher", "Ma routine du dimanche pour bien démarrer la semaine", "Ce que j'ai acheté ce mois-ci et ce que j'en pense", "Une journée sans écran : ce qui s'est passé"],
        "en": ["A day in my life, from wake-up to bedtime", "My Sunday routine to start the week right", "What I bought this month and what I think", "A screen-free day: what happened"],
    },
    "Parentalité & Famille": {
        "fr": ["Notre routine du soir avec les enfants", "Une astuce de parent testée et approuvée", "Une journée type avec un tout-petit", "Une erreur de jeune parent dont on rit aujourd'hui"],
        "en": ["Our evening routine with the kids", "A parenting trick tested and approved", "A typical day with a toddler", "A new-parent mistake we laugh about now"],
    },
    "Art & Créativité": {
        "fr": ["Un dessin du début à la fin en accéléré", "Je recrée une œuvre célèbre avec ce que j'ai chez moi", "Mon processus créatif, de l'idée au résultat", "Un défi créatif en 24 heures"],
        "en": ["A drawing from start to finish, sped up", "I recreate a famous artwork with what I have at home", "My creative process, from idea to result", "A 24-hour creative challenge"],
    },
    "Animaux": {
        "fr": ["Une journée avec mon animal", "Un conseil d'éducation pour votre animal", "La réaction de mon animal à une nouveauté", "Les erreurs courantes quand on adopte un animal"],
        "en": ["A day with my pet", "A training tip for your pet", "My pet's reaction to something new", "Common mistakes when adopting a pet"],
    },
    "Santé & Bien-être": {
        "fr": ["Une routine de 5 minutes pour réduire le stress", "Les habitudes de sommeil que je teste", "Un mythe santé démonté", "Mon repas équilibré de la journée"],
        "en": ["A 5-minute routine to reduce stress", "Sleep habits I'm testing", "A health myth debunked", "My balanced meal of the day"],
    },
    "Autre": {
        "fr": ["Un conseil que j'aurais aimé recevoir plus tôt", "Les coulisses de mon quotidien de créateur", "La question d'un abonné, ma réponse", "Un avant/après de mon projet"],
        "en": ["A tip I wish I'd received earlier", "Behind the scenes of my creator life", "A follower's question, my answer", "A before/after of my project"],
    },
}

_HASHTAGS = {
    "Beauté & Skincare": ["skincare", "skincareroutine", "beautytips", "glowup", "makeuptutorial", "selfcare"],
    "Mode & Style": ["fashion", "ootd", "styleinspo", "outfitideas", "thrifted", "fashiontips"],
    "Fitness & Sport": ["fitness", "workout", "homeworkout", "gymtok", "fitnessmotivation", "healthylifestyle"],
    "Cuisine & Nutrition": ["recipe", "easyrecipes", "foodtok", "mealprep", "cooking", "healthyrecipes"],
    "Voyage": ["travel", "traveltok", "traveltips", "wanderlust", "budgettravel", "hiddengems"],
    "Humour & Divertissement": ["comedy", "funny", "skit", "humor", "relatable", "fyp"],
    "Musique & Danse": ["dance", "music", "dancechallenge", "cover", "musician", "choreography"],
    "Gaming & Tech": ["gaming", "gamer", "tech", "techtok", "gadgets", "gamingtips"],
    "Business & Finance": ["business", "entrepreneur", "finance", "moneytips", "sidehustle", "personalfinance"],
    "Développement personnel": ["selfimprovement", "motivation", "mindset", "productivity", "habits", "personaldevelopment"],
    "Éducation & Culture générale": ["learnontiktok", "education", "didyouknow", "history", "science", "culture"],
    "Lifestyle & Vlog quotidien": ["vlog", "dayinmylife", "lifestyle", "routine", "aesthetic", "minivlog"],
    "Parentalité & Famille": ["parenting", "momtok", "dadtok", "parentingtips", "familylife", "toddler"],
    "Art & Créativité": ["art", "artist", "drawing", "creative", "diy", "artprocess"],
    "Animaux": ["pets", "dogsoftiktok", "catsoftiktok", "petcare", "animals", "cutepets"],
    "Santé & Bien-être": ["wellness", "selfcare", "mentalhealth", "healthylifestyle", "mindfulness", "sleeptok"],
    "Autre": ["fyp", "foryou", "tips", "howto", "behindthescenes", "creator"],
}


def get_starter_library(niche_category: str, lang: str) -> dict:
    """Contenu de départ d'une niche : hooks, idées de vidéos et hashtags."""
    key = "fr" if lang == "fr" else "en"
    niche = niche_category if niche_category in _TOPICS else "Autre"
    topic = _TOPICS[niche][key]
    return {
        "niche_category": niche_category,
        "lang": lang,
        "source": "starter",
        "hooks": [formula.format(topic=topic) for formula in _HOOK_FORMULAS[key]],
        "video_ideas": list(_IDEAS[niche][key]),
        "hashtags": list(_HASHTAGS[niche]),
    }
