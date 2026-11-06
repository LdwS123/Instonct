"""The menu, by category: one list that feeds Telegram's command menu, /aide, and the /menu buttons.

Every command lives in exactly one category (a test checks it against the handlers), and each category also lists what can simply be SAID.
Leaf module: it imports nothing from the package.
"""

# (key, icon, title, one-line summary, commands [(name, description)], things to say, quick-action keys shown as buttons on the page)
CATEGORIES = [
    ("maison", "🏠", "Maison et télé", "Allumer, éteindre, régler la télé et l'ambiance de la maison.",
     [("telecommande", "Télécommande de la télé (boutons)"), ("panneau", "Tableau de bord : tout en un bouton"),
      ("scene", "Scènes : dodo, film, départ… en un mot"), ("sortie", "Son : auto, télé ou Mac mini"), ("pairer", "Relier la télé (une seule fois)"),
      ("code", "Entrer le code de la télé")],
     ["Éteins la télé", "Allume la télé et mets Netflix", "Mets TF1", "Chaîne suivante", "Monte le son de la télé", "Mode film", "Mode dodo"],
     ["tele_on", "tele_off", "dodo", "film"]),
    ("musique", "🎵", "Musique et son", "Jouer, arrêter, parler à voix haute sur le Mac mini.",
     [("musique", "Jouer une musique YouTube"), ("pause", "Mettre en pause"), ("reprendre", "Reprendre la musique"), ("stop", "Arrêter la musique"),
      ("volume", "Volume du Mac mini 0-100"), ("voix", "Le Mac mini lit mes réponses : on / off"), ("dis", "Le Mac mini parle (anglais)"),
      ("parle", "Le Mac mini parle (français)"), ("ecran", "Message sur l'écran du Mac mini"), ("favoris", "Ce que tu as aimé")],
     ["Mets du Daft Punk", "Arrête la musique", "Baisse le son", "Dis bonjour à voix haute", "J'aime cette musique", "Mets un de mes favoris"],
     ["musique_stop", "volume_moins", "volume_plus"]),
    ("rappels", "⏰", "Rappels et agenda", "Ne rien oublier : rappels, agenda, résumé du matin.",
     [("rappel", "Rappel : minutes + texte"), ("matin", "Résumé du matin (météo, agenda, tâches, mails)"), ("google", "Reconnecter ton agenda Google"),
      ("heure", "Date et heure")],
     ["Rappelle-moi dans 10 minutes de sortir le linge", "J'ai ça à faire : appeler le garage", "Qu'est-ce que j'ai demain ?", "Ajoute un rendez-vous vendredi à 14h avec Meet",
      "Ajoute du lait aux courses", "Prévenez-moi 30 min avant chaque rendez-vous"],
     ["briefing"]),
    ("mails", "📧", "Mails et démarches", "Lire, trier, répondre, suivre tes candidatures et démarches.",
     [("oui", "Confirmer (mail, commande)"), ("non", "Annuler"), ("connexion", "Écran du Mac mini sur ton téléphone pour te connecter"),
      ("site", "Enregistrer un site pour que je m'y connecte")],
     ["Check mes mails", "Y a-t-il une réponse pour ma candidature ?", "Écris un mail à Paul pour demain", "Fais le ménage des pubs", "Où j'en suis de mes candidatures ?",
      "Prépare mon entretien chez Alan", "Réserve un train Paris-Lyon vendredi (je valide à la fin)"],
     []),
    ("argent", "💶", "Argent et perso", "Dépenses, budget, anniversaires, notes, calculs.",
     [],
     ["J'ai dépensé 12 euros au restaurant", "Où j'en suis de mon budget ce mois-ci ?", "L'anniversaire de Léa est le 3 mars", "Note : code du wifi chez Paul",
      "Combien font 15 % de 240 ?", "Mensualité d'un prêt de 200 000 € sur 20 ans à 3,5 %", "On divise l'addition à 4", "Convertis 50 dollars en euros"],
     []),
    ("infos", "🔎", "Infos et recherche", "Le web, la météo, l'actu, la France, le monde.",
     [("meteo", "Météo d'une ville")],
     ["Cherche sur le web les horaires de la piscine", "Fais une vraie recherche sur les mutuelles", "Les infos du jour", "Qualité de l'air à Lyon", "Quand est le coucher du soleil à Nice ?",
      "Où est la station spatiale ?", "Y a-t-il eu un séisme ?", "Les jours fériés en Italie", "Que veut dire « éphémère » ?", "Prix du carburant près de chez moi",
      "Informations sur l'entreprise Alan", "Résume cette vidéo YouTube"],
     []),
    ("outils", "🛠", "Outils et développement", "Petits outils pratiques pour le texte, les fichiers, le code.",
     [],
     ["Fusionne ces deux PDF", "Lis ce PDF / cette image (OCR)", "Fais un QR code de ce lien", "Télécharge la vidéo en mp3", "Teste cette regex", "Calcule le hash sha256 de ce texte",
      "Infos sur le paquet pip requests", "Quelles failles connues pour openssl ?", "Les tendances GitHub", "Convertis ce CSV en JSON", "Fais une archive de mon dossier docs"],
     []),
    ("serveur", "🖥", "Mac mini et réseau", "Surveiller, sauvegarder, réparer le serveur.",
     [("status", "État du Mac mini"), ("temp", "Température du processeur"), ("sante", "Ce qui marche et ne marche pas chez moi"),
      ("journal", "Ce que j'ai vraiment fait"), ("vitesse", "Temps de mes réponses")],
     ["Il reste combien de disque ?", "Pourquoi ça rame ?", "Est-ce que le site exemple.fr est en panne ?", "Quand expire le certificat de exemple.fr ?", "Quels appareils sont sur le wifi ?",
      "Teste mon débit internet", "Fais une sauvegarde maintenant", "Il y a des erreurs dans les logs ?", "Installe l'appli it-tools (Docker)"],
     ["status", "sauvegarde"]),
    ("auto", "🤖", "Automatisations", "Faire faire des choses toutes seules, à l'heure ou selon une condition.",
     [("auto", "Règles : chaque jour à telle heure, si le disque est plein…"), ("scene", "Scènes : une suite d'actions en un mot"),
      ("silence", "Mode silence la nuit (pas de voix)"), ("routines", "Tes routines (un mot lance plusieurs actions)"),
      ("panneau", "Tableau de bord : tout en un bouton"), ("matin", "Résumé du matin"), ("habitudes", "Ce que j'ai appris sur toi")],
     ["Tous les jours à 23h éteins la télé", "Chaque lundi à 9h préviens-moi de payer le loyer", "Si le disque est presque plein, préviens-moi", "Si mon site tombe, préviens-moi",
      "Toutes les 2 heures sauvegarde", "Active le mode silence de 23h à 7h", "Quand je dis bonne nuit, baisse le volume et éteins la télé", "Surveille le prix de cette page",
      "Abonne-moi à ce flux RSS", "Fais un bilan chaque soir"],
     ["dodo", "film", "depart", "briefing"]),
    ("fun", "🎲", "Fun et loisirs", "Pour s'amuser ou se détendre.",
     [("blague", "Une blague"), ("de", "Lancer un dé"), ("pile", "Pile ou face")],
     ["Une recette avec des courgettes", "Un cocktail sans alcool", "Un pokémon au hasard", "Pose-moi une question de culture générale", "Une citation", "Les jeux gratuits du moment",
      "Une série à regarder", "Un film du studio Ghibli"],
     []),
    ("moi", "🧠", "Mémoire et IA", "Ce que je sais de toi, comment je réponds.",
     [("memoire", "Ce que je sais de toi"), ("model", "Choisir le modèle d'IA et voir l'usage"), ("reset", "Oublier la conversation"), ("siri", "Parler à Steve avec Siri")],
     ["Souviens-toi que je suis allergique aux noix", "Qu'est-ce que tu sais de moi ?", "Oublie ça", "Retrouve ce dont on parlait hier"],
     []),
    ("aide", "❓", "Aide", "Retrouver les commandes.",
     [("menu", "Ce menu, par catégories"), ("aide", "Liste de toutes les commandes")],
     [],
     []),
]

HIDDEN = {"start", "help", "tele", "favs", "ecran_distant", "testvoix"}          # accepted by the bot, kept out of the menus
INTRO = ("Je suis un agent : écris-moi (ou parle-moi) et je fais : « mets du Daft Punk », « baisse le volume », « rappelle-moi dans 10 minutes », "
         "« combien de place sur le disque ? », une question sur le web…\n"
         "Tu peux aussi m'envoyer un MESSAGE VOCAL : je t'écoute et je te réponds à voix haute.\n"
         "Tout est gratuit. Tape /menu pour les boutons par catégorie.")


def by_key(key):
    return next((c for c in CATEGORIES if c[0] == key), None)


def all_commands():
    """[(name, description)] in menu order, each name once (a command shown in two categories keeps its first place)."""
    seen, out = set(), []
    for _, icon, _, _, cmds, _, _ in CATEGORIES:
        for name, desc in cmds:
            if name not in seen:
                seen.add(name)
                out.append((name, desc))
    return out


def telegram_commands():
    """For Telegram's setMyCommands: the icon of the category in front of each description (Telegram menus are flat). At most 100, 256 characters each."""
    out, seen = [], set()
    for _, icon, _, _, cmds, _, _ in CATEGORIES:
        for name, desc in cmds:
            if name not in seen:
                seen.add(name)
                out.append((name, f"{icon} {desc}"[:256]))
    return out[:100]


def menu_rows():
    """Buttons of /menu : the categories, two per row."""
    buttons = [(f"{c[1]} {c[2]}", f"menu:{c[0]}") for c in CATEGORIES]
    return [buttons[i:i + 2] for i in range(0, len(buttons), 2)]


def home_text():
    return "Menu — choisis une catégorie :\n(ou écris simplement ce que tu veux, je m'en occupe)"


def page(key):
    """(text, button rows) of one category; the quick-action buttons come first, then « Menu »."""
    cat = by_key(key)
    if cat is None:
        return home_text(), menu_rows()
    _, icon, title, summary, cmds, says, quick = cat
    lines = [f"{icon} {title}", summary]
    if cmds:
        lines += ["", "Commandes :"] + [f"/{n} : {d}" for n, d in cmds]
    if says:
        lines += ["", "Tu peux aussi dire :"] + [f"• {s}" for s in says]
    rows = []
    if quick:
        from .automate import QUICK_LABELS                  # lazy: automate imports a lot of the package
        buttons = [(QUICK_LABELS[q], f"go:{q}") for q in quick if q in QUICK_LABELS]
        rows += [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    rows.append([("⬅ Menu", "menu:home")])
    return "\n".join(lines), rows


def aide_text():
    parts, shown = [INTRO], set()
    for _, icon, title, _, cmds, _, _ in CATEGORIES:
        fresh = [(n, d) for n, d in cmds if n not in shown]          # a command listed in two categories is written once
        shown |= {n for n, _ in fresh}
        if fresh:
            parts.append(f"\n{icon} {title}\n" + "\n".join(f"/{n} : {d}" for n, d in fresh))
    parts.append("\nEt tout ce qui se dit simplement (candidatures, dépenses, anniversaires, notes, calculs, recherches, rappels avant un rendez-vous, "
                 "ménage des pubs, bilan du soir…) : le détail est dans /menu.")
    return "\n".join(parts)
