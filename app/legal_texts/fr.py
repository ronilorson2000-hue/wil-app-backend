"""
Textes juridiques en français : version de référence (elle fait foi en cas de divergence avec une traduction).
Format : un document = titre, date, introduction, sections [(titre, [blocs])]. Bloc : ("p", html) ou ("ul", [html...]).
Les jetons {EMAIL} et {WHATSAPP} sont remplacés par les coordonnées de contact (voir app/legal.py).
À FAIRE RELIRE par un juriste avant des ventes importantes (droit de rétractation, TVA, identité de l'éditeur).
"""

TERMS = {
    "title": "Conditions d'utilisation",
    "updated": "Dernière mise à jour : octobre 2026",
    "prevails": "",
    "back_home": "← Retour à l'accueil",
    "back_settings": "← Retour aux paramètres",
    "see_also": "Consulter aussi notre Politique de confidentialité →",
    "footer": "Wil App — Conditions d'utilisation",
    "intro": "Les présentes Conditions d'utilisation (« Conditions ») régissent l'accès et l'utilisation de l'application Wil App (le « Service »), accessible à l'adresse wilapp.tech et éditée à titre individuel par une personne physique (l'« Éditeur »), joignable aux coordonnées de l'article 15. En utilisant le Service ou en souscrivant un abonnement, vous acceptez sans réserve les présentes Conditions.",
    "sections": [
        ("1. Objet et description du service", [
            ("p", "Wil App est un outil d'analyse propulsé par l'intelligence artificielle destiné aux créateurs de contenu TikTok. Le Service permet notamment de :"),
            ("ul", [
                "connecter son compte TikTok pour obtenir un diagnostic automatique (score de viralité, taux d'engagement, points forts, points à améliorer, hashtags suggérés) ;",
                "analyser une vidéo (déjà publiée ou non) importée manuellement par l'utilisateur, à partir de son contenu visuel et sonore ;",
                "analyser le script d'une vidéo pas encore tournée, ou en générer un ;",
                "consulter une bibliothèque et des idées du jour (hooks, idées de vidéos, hashtags) issues de recherches web réalisées par intelligence artificielle, et enregistrer celles qui vous intéressent.",
            ]),
            ("p", "Les rapports et contenus sont générés par des modèles d'intelligence artificielle fournis par des prestataires tiers : Claude (Anthropic) pour l'analyse de compte, l'analyse et la génération de script et la bibliothèque, et Gemini (Google) pour l'analyse de vidéo. Ils s'appuient sur les données que vous fournissez, sur les données réellement récupérées via l'API officielle de TikTok, ou sur des recherches web."),
        ]),
        ("2. Âge minimum, connexion et accès au compte", [
            ("p", "<strong>Âge minimum.</strong> Le Service est réservé aux personnes âgées de 18 ans révolus ou plus. En utilisant le Service, vous déclarez avoir au moins 18 ans. Si vous avez moins de 18 ans, vous n'êtes pas autorisé à utiliser le Service, et en particulier à importer des vidéos ou des scripts pour analyse. Si nous apprenons qu'un utilisateur a moins de 18 ans, nous pouvons suspendre son accès et supprimer ses données."),
            ("p", "L'accès aux fonctionnalités liées à l'analyse de compte nécessite une connexion via le Login Kit officiel de TikTok (protocole OAuth). Wil App n'a et ne demande jamais accès à votre mot de passe TikTok. Vous pouvez révoquer l'autorisation donnée à Wil App à tout moment depuis les paramètres de connexions tierces de votre compte TikTok."),
            ("p", "L'accès aux fonctionnalités payantes est lié à votre compte Whop, identifié par l'adresse e-mail utilisée lors du paiement. Vous êtes responsable de la confidentialité de votre compte Whop."),
        ]),
        ("3. Contenu importé par l'utilisateur", [
            ("p", "Lorsque vous importez un fichier vidéo ou un texte de script pour analyse, vous garantissez :"),
            ("ul", [
                "être titulaire des droits sur ce contenu, ou disposer des autorisations nécessaires pour l'utiliser (y compris pour le contenu d'un autre créateur, à condition de l'avoir obtenu légalement — jamais par extraction automatisée depuis un simple lien) ;",
                "que ce contenu ne viole aucune loi, aucun droit de tiers, ni les règles de la communauté TikTok.",
            ]),
            ("p", "Wil App ne collecte, ne télécharge et ne scrape aucune vidéo directement depuis TikTok à l'insu de l'utilisateur : chaque fichier ou texte analysé est fourni volontairement par vous."),
            ("p", "Pour être analysé, le fichier vidéo est transmis à Google (API Gemini), qui en analyse les images et le son ; le texte d'un script est transmis à Anthropic (Claude). Wil App ne conserve pas votre fichier vidéo après l'analyse, mais conserve le rapport généré, comme décrit dans notre Politique de confidentialité. Ces prestataires traitent les données selon leurs propres conditions. Vos vidéos et vos scripts ne sont pas utilisés pour alimenter les contenus montrés aux autres utilisateurs."),
        ]),
        ("4. Usage autorisé", [
            ("p", "Vous vous engagez à utiliser le Service à des fins strictement personnelles et légales, et à ne pas :"),
            ("ul", [
                "tenter de contourner les limites techniques du Service (par exemple la limite de mots pour l'analyse de script, ou les limites de fréquence des demandes) ;",
                "utiliser le Service à des fins d'ingénierie inverse, de revente, ou d'extraction automatisée massive des rapports générés ;",
                "utiliser le Service pour analyser du contenu que vous n'avez pas le droit d'utiliser ;",
                "partager votre accès payant avec des tiers.",
            ]),
        ]),
        ("5. Offre gratuite, abonnement et paiement", [
            ("p", "<strong>Offre gratuite.</strong> Le Service permet d'essayer gratuitement une analyse de vidéo et une analyse de compte TikTok ; le rapport complet de ces analyses, ainsi que les autres fonctionnalités, sont réservés aux abonnés."),
            ("p", "<strong>Abonnement.</strong> L'accès complet au Service est proposé par abonnement, mensuel ou annuel. Les fonctionnalités incluses, les prix et la périodicité sont affichés sur la page Tarifs et sur la page de paiement avant votre achat. Les taxes éventuellement applicables selon votre pays sont indiquées sur la page de paiement. L'abonnement est soumis à un usage raisonnable ; des limites techniques de fréquence peuvent s'appliquer pour protéger le Service."),
            ("p", "<strong>Paiement.</strong> Les paiements sont traités par Whop (whop.com), prestataire tiers, selon ses propres conditions. L'Éditeur ne reçoit ni ne conserve vos données de carte bancaire. Selon les cas, Whop peut intervenir comme vendeur de l'abonnement ou comme simple prestataire de paiement ; le vendeur et le prix total, taxes comprises, sont indiqués sur la page de paiement."),
            ("p", "<strong>Renouvellement.</strong> L'abonnement est reconduit automatiquement à la fin de chaque période (mensuelle ou annuelle), au tarif en vigueur, jusqu'à son annulation. L'Éditeur peut modifier ses tarifs : toute hausse s'applique à partir de la période suivante, après une information préalable raisonnable (par e-mail ou dans l'application), et vous pouvez annuler avant son entrée en vigueur."),
        ]),
        ("6. Annulation et remboursement", [
            ("p", "<strong>Annulation.</strong> Vous pouvez annuler votre abonnement à tout moment, depuis Paramètres &gt; Gérer l'abonnement (lien vers votre espace Whop) ou en nous écrivant. L'annulation prend effet à la fin de la période déjà payée : vous conservez l'accès jusqu'à cette date et plus aucun prélèvement n'est effectué ensuite. La période en cours n'est pas remboursée, sous réserve de la règle suivante."),
            ("p", "<strong>Remboursement sous 14 jours.</strong> Vous pouvez demander le remboursement de votre abonnement dans les 14 jours suivant votre achat, à condition qu'<strong>aucune analyse</strong> (vidéo, compte TikTok ou script) n'ait été réalisée avec cet abonnement. Pour cela, écrivez-nous (article 15) en indiquant l'adresse e-mail utilisée pour l'achat. Le remboursement est effectué sur le moyen de paiement d'origine, par l'intermédiaire de notre prestataire de paiement."),
            ("p", "Dès qu'une analyse a été réalisée, le service numérique est considéré comme fourni et le montant payé n'est plus remboursable, sauf obligation légale contraire. Cette règle ne limite pas les droits impératifs dont vous bénéficiez selon la loi de votre pays de résidence, notamment le droit de rétractation applicable aux consommateurs de l'Union européenne. L'accès au Service commence immédiatement après votre paiement."),
        ]),
        ("7. Nature des analyses fournies", [
            ("p", "Les scores, diagnostics, conseils et estimations fournis par Wil App (y compris le score de viralité, les fourchettes de vues, de likes ou de commentaires et le « potentiel de viralité » des idées du jour) sont générés automatiquement par une intelligence artificielle à partir des données disponibles. Ce sont des estimations et non des prédictions : ils constituent une aide à la décision et ne garantissent en aucun cas un résultat (augmentation de vues, d'abonnés ou de revenus). Wil App ne peut être tenu responsable des décisions prises sur la base de ces analyses."),
        ]),
        ("8. Propriété intellectuelle", [
            ("p", "L'application, sa marque, son design et son code restent la propriété exclusive de l'Éditeur. Les rapports générés pour votre compte vous sont fournis pour votre usage personnel ; vous en conservez le contenu, sans que cela ne vous transfère de droit sur la plateforme elle-même."),
        ]),
        ("9. Disponibilité et évolution du service", [
            ("p", "Wil App est un projet en développement actif. Certaines fonctionnalités peuvent être ajoutées, modifiées ou temporairement retirées. Nous nous efforçons d'assurer la continuité du Service mais ne garantissons pas une disponibilité ininterrompue. Si une fonctionnalité incluse dans votre abonnement est retirée de façon durable, vous pouvez annuler votre abonnement et demander le remboursement de la période en cours non utilisée."),
        ]),
        ("10. Limitation de responsabilité", [
            ("p", "Le Service est fourni « en l'état ». Wil App n'est ni affilié, ni sponsorisé, ni approuvé par TikTok ou ByteDance Ltd. Dans les limites permises par la loi, l'Éditeur décline toute responsabilité pour les dommages indirects résultant de l'utilisation du Service. Aucune disposition des présentes n'exclut une responsabilité qui ne peut l'être selon la loi applicable."),
        ]),
        ("11. Résiliation et suspension", [
            ("p", "Vous pouvez cesser d'utiliser le Service à tout moment, en révoquant l'accès depuis les paramètres de votre compte TikTok ou en supprimant votre compte depuis Paramètres &gt; Supprimer mon compte (ce qui supprime vos données, comme décrit dans notre Politique de confidentialité). Supprimer votre compte n'annule pas à lui seul un abonnement payant en cours : annulez-le séparément (article 6). L'Éditeur se réserve le droit de suspendre l'accès d'un utilisateur en cas d'usage abusif ou de non-respect des présentes Conditions."),
        ]),
        ("12. Modification des présentes Conditions", [
            ("p", "Les présentes Conditions peuvent être mises à jour. En cas de modification importante, notamment des prix ou des règles de remboursement, vous en serez informé par e-mail ou dans l'application avant son entrée en vigueur. La poursuite de l'utilisation du Service après une modification vaut acceptation des nouvelles conditions."),
        ]),
        ("13. Droit applicable", [
            ("p", "Les présentes Conditions sont soumises au droit applicable au lieu de résidence de l'Éditeur, sans préjudice des règles impératives de protection des consommateurs de votre pays de résidence."),
        ]),
        ("14. Traductions", [
            ("p", "Les présentes Conditions sont proposées en plusieurs langues pour votre confort. En cas de divergence, la version française fait foi."),
        ]),
        ("15. Contact", [
            ("p", "Pour toute question relative aux présentes Conditions, à votre abonnement ou à une demande de remboursement, contactez-nous à {EMAIL} ou via {WHATSAPP}."),
        ]),
    ],
}

PRIVACY = {
    "title": "Politique de confidentialité",
    "updated": "Dernière mise à jour : octobre 2026",
    "prevails": "",
    "back_home": "← Retour à l'accueil",
    "back_settings": "← Retour aux paramètres",
    "see_also": "Consulter aussi nos Conditions d'utilisation →",
    "footer": "Wil App — Politique de confidentialité",
    "intro": "La présente Politique de confidentialité explique comment Wil App (« nous ») collecte, utilise et protège les informations lorsque vous utilisez notre Service. Wil App est édité à titre individuel par une personne physique, responsable du traitement, joignable aux coordonnées de l'article 12.",
    "sections": [
        ("1. Informations que nous collectons", [
            ("p", "<strong>Compte TikTok.</strong> Lorsque vous connectez votre compte TikTok via le Login Kit officiel de TikTok, nous pouvons recevoir, uniquement avec votre autorisation explicite :"),
            ("ul", [
                "des informations de profil de base (nom d'utilisateur, nom affiché, photo de profil) ;",
                "le contenu public et les métadonnées des vidéos associées à votre compte.",
            ]),
            ("p", "Nous n'accédons ni à vos messages privés, ni à vos informations de paiement, ni à aucune donnée au-delà de ce que permettent les autorisations que vous accordez. De votre compte connecté, nous conservons une session d'accès (le jeton est chiffré) et des relevés périodiques de vos statistiques (taux d'engagement, taux de viralité), pour comparer votre compte à lui-même dans le temps."),
            ("p", "<strong>Compte Whop et abonnement.</strong> Pour gérer les abonnements, nous utilisons Whop : nous recevons votre identifiant Whop, votre adresse e-mail et l'état de votre abonnement (actif ou non, plan). Les paiements sont traités par Whop : nous ne recevons ni ne conservons vos données de carte bancaire."),
            ("p", "<strong>Vidéos et scripts que vous fournissez.</strong> Lorsque vous importez une vidéo ou collez un script pour analyse, il est transmis à nos prestataires d'intelligence artificielle (article 2) pour générer votre rapport. Nous ne conservons pas votre fichier vidéo après l'analyse. Nous n'utilisons pas vos vidéos ou scripts pour constituer les contenus montrés aux autres utilisateurs."),
            ("p", "<strong>Rapports d'analyse.</strong> Le rapport généré est conservé sur nos serveurs sous un identifiant aléatoire, sans lien direct avec votre identité, pour que vous puissiez le retrouver (par exemple après avoir actualisé la page ou souscrit un abonnement). Les rapports sont supprimés automatiquement après 180 jours."),
            ("p", "<strong>Retour sur les estimations.</strong> Si vous nous indiquez qu'une vidéo était déjà publiée et répondez si notre estimation était proche des résultats réels, nous enregistrons cette réponse de façon anonyme (niche, score, niveau estimé et votre réponse), sans la vidéo et sans identifiant."),
            ("p", "<strong>Données conservées sur votre appareil.</strong> Vos réponses d'onboarding, l'historique de vos analyses, vos éléments enregistrés, vos choix de langue et d'apparence, ainsi qu'une copie de vos derniers rapports, sont stockés dans votre navigateur (stockage local), sur votre appareil. Si vous connectez TikTok, votre navigateur conserve aussi votre profil public (nom, pseudonyme, photo) et un identifiant de session."),
            ("p", "<strong>Données techniques.</strong> Pour protéger le Service contre les abus, nous utilisons temporairement votre adresse IP (limitation du nombre de demandes) ; notre hébergeur peut conserver des journaux techniques pour une durée limitée."),
        ]),
        ("2. Traitement par intelligence artificielle", [
            ("p", "Pour produire vos analyses, Wil App <strong>transmet le contenu que vous fournissez à des fournisseurs externes d'intelligence artificielle</strong>, qui le traitent pour l'analyser et le classer. Concrètement :"),
            ("ul", [
                "vos <strong>vidéos</strong> (images et son) sont envoyées à Google (Gemini) ;",
                "vos <strong>scripts</strong> sont envoyés à Anthropic (Claude) ;",
                "les informations de votre <strong>profil TikTok</strong> (nom, nom d'utilisateur, description) et les statistiques de vos vidéos sont envoyées à Anthropic (Claude) ;",
                "les <strong>idées tendance</strong> sont produites par Claude (Anthropic) à partir de recherches web.",
            ]),
            ("p", "Ces envois n'ont lieu que lorsque vous lancez une analyse, et uniquement après votre accord : une fenêtre de consentement s'affiche avant la première analyse, et vous pouvez retirer votre consentement à tout moment dans les réglages (Profil). Ces fournisseurs sont des entreprises indépendantes : elles traitent les données selon leurs propres conditions et leurs propres règles de confidentialité. Nous ne vendons pas vos contenus et ne les utilisons pas pour fabriquer les contenus montrés aux autres utilisateurs. Si vous ne souhaitez pas que votre contenu soit transmis à ces fournisseurs, n'utilisez pas les fonctions d'analyse."),
        ]),
        ("3. Comment nous utilisons vos informations", [
            ("p", "Nous utilisons ces informations uniquement pour fournir le Service (diagnostic de compte, analyse de vidéo et de script, tendances, gestion de votre abonnement), assurer sa sécurité et améliorer sa fiabilité et la précision de nos estimations. Nous ne vendons pas vos données personnelles à des tiers."),
        ]),
        ("4. Bases juridiques", [
            ("p", "Selon les cas, le traitement repose sur l'exécution du contrat (fournir le Service et gérer votre abonnement), votre consentement (connexion de votre compte TikTok, que vous pouvez retirer à tout moment), notre intérêt légitime (sécurité, prévention des abus, amélioration du Service) et le respect de nos obligations légales (comptabilité et paiements)."),
        ]),
        ("5. Conservation et sécurité", [
            ("p", "Nous prenons des mesures techniques raisonnables pour protéger les informations que nous stockons : les jetons d'accès TikTok sont chiffrés, les connexions sont protégées par HTTPS et l'accès à nos bases de données est restreint."),
            ("ul", [
                "Sessions TikTok : au plus 30 jours, ou jusqu'à ce que vous vous déconnectiez ou supprimiez votre compte.",
                "Relevés de statistiques de compte : jusqu'à ce que vous supprimiez votre compte.",
                "Rapports d'analyse : 180 jours.",
                "Données de paiement et de facturation : conservées par Whop et, le cas échéant, par nous pendant la durée exigée par la loi.",
            ]),
        ]),
        ("6. Services tiers", [
            ("p", "Notre Service s'appuie sur les prestataires suivants, chacun soumis à ses propres conditions et à sa politique de confidentialité :"),
            ("ul", [
                "TikTok (API officielles et Login Kit) ;",
                "Anthropic (Claude), qui traite les données de compte, les scripts et les recherches web servant à générer les rapports et tendances ;",
                "Google (API Gemini), qui traite les vidéos que vous importez pour en analyser les images et le son ;",
                "Whop, qui traite les paiements et la connexion à votre compte Whop ;",
                "Sentry, qui reçoit les rapports techniques d'erreur du serveur (sans cookie, sans adresse e-mail, sans contenu de vos vidéos ou scripts) pour nous permettre de corriger les pannes ;",
                "nos prestataires d'hébergement, de base de données et de sécurité réseau (Render, Supabase, Cloudflare), qui stockent ou transmettent les données décrites ci-dessus.",
            ]),
            ("p", "Votre utilisation de TikTok reste soumise à la politique de confidentialité et aux conditions de TikTok."),
        ]),
        ("7. Transferts internationaux", [
            ("p", "Certains de ces prestataires sont situés hors de votre pays, notamment aux États-Unis. Vos données peuvent donc être transférées et traitées dans d'autres pays, avec les garanties prévues par ces prestataires et par la loi applicable."),
        ]),
        ("8. Vos droits", [
            ("p", "Depuis l'écran Paramètres de l'application, vous pouvez à tout moment :"),
            ("ul", [
                "<strong>Déconnecter TikTok</strong> : nous révoquons le jeton d'accès et supprimons votre session, en conservant votre historique ;",
                "<strong>Supprimer votre compte</strong> : nous supprimons les données stockées sur votre appareil et, si TikTok était connecté, nous révoquons l'accès et supprimons vos sessions et l'historique de vos statistiques sur nos serveurs. Cette action est définitive.",
            ]),
            ("p", "Vous pouvez aussi révoquer l'accès de Wil App depuis les paramètres de votre compte TikTok. Selon la loi applicable (par exemple le RGPD), vous disposez en outre d'un droit d'accès, de rectification, d'effacement, de limitation, d'opposition et de portabilité, et du droit d'introduire une réclamation auprès de l'autorité de protection des données de votre pays. Pour exercer ces droits, notamment pour les données liées à votre abonnement ou à un rapport précis (indiquez alors son lien), contactez-nous : nous répondons dans un délai d'un mois."),
        ]),
        ("9. Cookies et stockage local", [
            ("p", "Nous utilisons uniquement des cookies strictement nécessaires au fonctionnement du Service, sans publicité ni suivi : votre choix de langue (1 an), le compteur de l'analyse gratuite (1 an), votre connexion Whop (30 jours), et des cookies temporaires pendant la connexion et le paiement (de quelques minutes à 24 heures). Le stockage local de votre navigateur sert aux préférences et à l'historique décrits à l'article 1."),
        ]),
        ("10. Âge minimum", [
            ("p", "Le Service est destiné aux personnes de 18 ans ou plus. Nous ne collectons pas sciemment d'informations auprès de personnes de moins de 18 ans. Si vous pensez qu'une personne de moins de 18 ans a utilisé le Service, contactez-nous et nous supprimerons les données correspondantes."),
        ]),
        ("11. Modifications", [
            ("p", "Nous pouvons mettre à jour la présente Politique de temps à autre. En cas de modification importante, nous vous en informerons dans l'application. La poursuite de l'utilisation du Service après une modification vaut acceptation de la politique mise à jour. En cas de divergence entre les traductions, la version française fait foi."),
        ]),
        ("12. Contact", [
            ("p", "Une question ? Contactez-nous à {EMAIL} ou via {WHATSAPP}."),
        ]),
    ],
}
