"""Fun and leisure tools from free public sources (no key): recipes, cocktails, Pokemon, quizzes, jokes, animals, quotes, Magic cards,
TV shows, free games of the week, game prices, music and Ghibli films.

Everything that comes from the outside is named in TAINT. The services answer in English: the model translates for the user.
"""

import html
import random
import re
from datetime import datetime, timezone

import requests

from .kit_base import AGENT, clean, get_json, get_json_or_none, spec, text, whole

SPECS = [
    spec("recette", "Cherche une recette de cuisine (nom du plat ou ingredient) : ingredients, etapes, origine, lien.", recherche="string!"),
    spec("cocktail", "Cherche un cocktail (nom ou ingredient) : ingredients, verre, preparation.", recherche="string!"),
    spec("pokemon", "Fiche d'un Pokemon (nom anglais ou numero) : types, taille, poids, capacites, statistiques.", nom="string!"),
    spec("trivia", "Pose 1 a 5 questions de culture generale avec les choix et la bonne reponse (niveau easy|medium|hard).", nombre="integer", niveau="string"),
    spec("blague", "Raconte une blague (theme Any|Programming|Misc|Pun, langue fr ou en).", theme="string", langue="string"),
    spec("animal", "Photo ou fait sur un animal : espece chien|chat|renard.", espece="string!"),
    spec("citation", "Une citation celebre au hasard, avec son auteur."),
    spec("carte_magic", "Fiche d'une carte Magic The Gathering (nom approximatif) : cout, texte, extension, prix, lien.", nom="string!"),
    spec("serie_tv", "Cherche une serie TV : genres, statut, dates, note, chaine, resume, lien.", titre="string!"),
    spec("jeux_gratuits", "Les jeux offerts cette semaine sur l'Epic Games Store, et ceux de la semaine prochaine."),
    spec("prix_jeux", "Cherche le meilleur prix d'un jeu PC dans les boutiques (prix en dollars, reduction, lien).", titre="string!"),
    spec("musique_itunes", "Cherche une chanson, un album, un film, un podcast ou un livre audio (type song|album|film|podcast|audiobook).", recherche="string!", type="string"),
    spec("ghibli", "Les films du studio Ghibli : un film precis (titre) ou la liste complete.", titre="string"),
]
GROUPS = [
    (r"recette|je cuisine|cuisiner|plat de|ingredients pour|que manger|idee repas|comment faire .*(?:gateau|tarte|pates|soupe)", {"recette"}),
    (r"cocktail|boisson alcoolisee|mojito|margarita|apero", {"cocktail"}),
    (r"pokemon|pikachu|pokedex", {"pokemon"}),
    (r"trivia|quiz|culture generale|pose.moi une question|questions? de culture|teste mes connaissances", {"trivia"}),
    (r"blague|histoire drole|fais.moi rire|raconte.moi une drole", {"blague"}),
    (r"photo de (?:chien|chat|renard)|image de (?:chien|chat|renard)|montre.moi un (?:chien|chat|renard)|fait sur les chats|fait sur les chiens|animal mignon", {"animal"}),
    (r"citation|proverbe|phrase celebre|inspire.moi|motivation du jour", {"citation"}),
    (r"magic the gathering|carte magic|\bmtg\b|scryfall", {"carte_magic"}),
    (r"serie tv|\bserie\b|quelle serie|saison|tvmaze|netflix|que regarder|a regarder ce soir", {"serie_tv"}),
    (r"jeux? gratuits?|epic games|offert .* jeu|jeu offert|free game|gratuit cette semaine", {"jeux_gratuits"}),
    (r"prix (?:du|d.un) jeu|jeu .* moins cher|promo .* jeu|steam|soldes? jeux?|cheapshark|jeu pc", {"prix_jeux"}),
    (r"itunes|chanson|album|podcast|livre audio|cherche .* musique|morceau de|clip de|sortie musicale", {"musique_itunes"}),
    (r"ghibli|miyazaki|totoro|chihiro|film d.animation japonais", {"ghibli"}),
]
TAINT = {s["name"] for s in SPECS}                                   # all of them: every answer was written by strangers


def _lines(row, count):
    """'strIngredient1' + 'strMeasure1' ... -> ['2 cups flour', ...] (TheMealDB / TheCocktailDB spread the list over numbered fields)."""
    out = []
    for i in range(1, count + 1):
        ing = clean(row.get(f"strIngredient{i}"), 60)
        if ing:
            out.append(f"{clean(row.get(f'strMeasure{i}'), 30)} {ing}".strip())
    return out


def recette(chat_id, a):
    word = text(a, "recherche", "", 80)
    found = (get_json("https://www.themealdb.com/api/json/v1/1/search.php", s=word).get("meals") or [])
    if not found:
        rows = get_json("https://www.themealdb.com/api/json/v1/1/filter.php", i=word.replace(" ", "_")).get("meals") or []
        if not rows:
            return {"erreur": f"aucune recette trouvee pour {word} (essaie le nom en anglais)"}
        found = (get_json("https://www.themealdb.com/api/json/v1/1/lookup.php", i=rows[0]["idMeal"]).get("meals") or [])
    row = found[0]
    return {"nom": row.get("strMeal"), "categorie": row.get("strCategory"), "origine": row.get("strArea"), "ingredients": _lines(row, 20),
            "etapes": clean(row.get("strInstructions"), 1200), "video": row.get("strYoutube") or "", "autres_resultats": [r["strMeal"] for r in found[1:5]],
            "note": "recette en anglais : traduis-la pour l'utilisateur"}


def cocktail(chat_id, a):
    word = text(a, "recherche", "", 80)
    found = get_json("https://www.thecocktaildb.com/api/json/v1/1/search.php", s=word).get("drinks") or []
    if not found:
        rows = get_json("https://www.thecocktaildb.com/api/json/v1/1/filter.php", i=word).get("drinks") if re.fullmatch(r"[\w ]+", word) else None
        if not rows:
            return {"erreur": f"aucun cocktail trouve pour {word}"}
        found = get_json("https://www.thecocktaildb.com/api/json/v1/1/lookup.php", i=rows[0]["idDrink"]).get("drinks") or []
        if not found:
            return {"erreur": f"aucun cocktail trouve pour {word}"}
    row = found[0]
    return {"nom": row.get("strDrink"), "type": row.get("strAlcoholic"), "verre": row.get("strGlass"), "ingredients": _lines(row, 15),
            "preparation": clean(row.get("strInstructions"), 700), "autres_resultats": [r["strDrink"] for r in found[1:5]]}


def pokemon(chat_id, a):
    key = re.sub(r"[^a-z0-9-]", "", text(a, "nom", "", 40).lower().replace(" ", "-").replace("é", "e"))
    if not key:
        return {"erreur": "donne un nom ou un numero de Pokemon"}
    p = get_json_or_none(f"https://pokeapi.co/api/v2/pokemon/{key}")
    if not p:
        return {"erreur": f"Pokemon introuvable : {key} (utilise le nom anglais, ex. charizard)"}
    return {"numero": p["id"], "nom": p["name"], "types": [t["type"]["name"] for t in p["types"]], "taille_m": p["height"] / 10, "poids_kg": p["weight"] / 10,
            "capacites": [x["ability"]["name"] for x in p["abilities"]], "stats": {s["stat"]["name"]: s["base_stat"] for s in p["stats"]}}


def trivia(chat_id, a):
    level = text(a, "niveau", "", 10).lower()
    params = {"amount": whole(a, "nombre", 1, 1, 5), "type": "multiple", **({"difficulty": level} if level in ("easy", "medium", "hard") else {})}
    data = get_json("https://opentdb.com/api.php", **params)
    if data.get("response_code") != 0 or not data.get("results"):
        return {"erreur": "le service de questions est occupe, reessaie dans quelques secondes"}
    out = []
    for q in data["results"]:
        choices = [html.unescape(x) for x in q["incorrect_answers"]] + [html.unescape(q["correct_answer"])]
        random.shuffle(choices)
        out.append({"categorie": html.unescape(q["category"]), "niveau": q["difficulty"], "question": html.unescape(q["question"]), "choix": choices,
                    "bonne_reponse": html.unescape(q["correct_answer"])})
    return {"questions": out, "note": "pose la question et les choix d'abord ; ne donne la bonne reponse qu'apres la reponse de l'utilisateur ; traduis en francais"}


def _joke(theme, lang, skip):
    """One JokeAPI call. "No joke matches" comes back as HTTP 400 with a JSON body, so read the body whatever the status."""
    r = requests.get(f"https://v2.jokeapi.dev/joke/{theme}", params={"lang": lang, "blacklistFlags": skip}, headers=AGENT, timeout=12)
    try:
        return r.json()
    except ValueError:
        r.raise_for_status()
        return {"error": True}


def blague(chat_id, a):
    theme = text(a, "theme", "Any", 20).capitalize()
    theme = theme if theme in ("Any", "Programming", "Misc", "Pun") else "Any"
    lang = "en" if text(a, "langue", "fr", 5).lower().startswith("en") else "fr"
    skip = "nsfw,religious,political,racist,sexist,explicit"
    data = _joke(theme, lang, skip)
    if data.get("error") and lang == "fr":                             # the French list is short: fall back to English
        data = _joke(theme, "en", skip)
    if data.get("error") and theme != "Any":                            # still nothing for this theme: any theme will do
        data = _joke("Any", lang, skip)
    if data.get("error"):
        return {"erreur": "pas de blague trouvee pour ce theme"}
    return {"blague": data["joke"] if data.get("type") == "single" else f"{data.get('setup')}\n{data.get('delivery')}", "langue": data.get("lang")}


def animal(chat_id, a):
    kind = text(a, "espece", "", 12).lower()
    if kind.startswith("chien"):
        return {"espece": "chien", "photo": get_json("https://dog.ceo/api/breeds/image/random")["message"]}
    if kind.startswith("chat"):
        out = {"espece": "chat", "fait": get_json("https://catfact.ninja/fact")["fact"]}
        try:
            out["photo"] = get_json("https://api.thecatapi.com/v1/images/search", timeout=8)[0]["url"]
        except Exception:                                                # the fact alone is still an answer
            pass
        return out
    if kind.startswith("renard"):
        return {"espece": "renard", "photo": get_json("https://randomfox.ca/floof/")["image"]}
    return {"erreur": "especes disponibles : chien, chat, renard"}


def citation(chat_id, a):
    row = get_json("https://zenquotes.io/api/random")[0]
    if "Too many requests" in row.get("q", ""):
        return {"erreur": "trop de demandes de citations, reessaie dans une minute"}
    return {"citation": row["q"], "auteur": row["a"], "note": "citation en anglais : traduis-la"}


def carte_magic(chat_id, a):
    c = get_json_or_none("https://api.scryfall.com/cards/named", fuzzy=text(a, "nom", "", 80))
    if not c:
        return {"erreur": "carte introuvable (essaie le nom anglais, plus precis)"}
    prices = c.get("prices") or {}
    return {"nom": c["name"], "cout": c.get("mana_cost"), "type": c.get("type_line"), "texte": clean(c.get("oracle_text"), 500), "extension": c.get("set_name"),
            "rarete": c.get("rarity"), "prix_eur": prices.get("eur"), "prix_usd": prices.get("usd"), "lien": (c.get("scryfall_uri") or "").split("?")[0]}


def serie_tv(chat_id, a):
    rows = get_json("https://api.tvmaze.com/search/shows", q=text(a, "titre", "", 80))
    if not rows:
        return {"erreur": "aucune serie trouvee"}
    out = []
    for r in rows[:3]:
        s = r["show"]
        net = (s.get("network") or s.get("webChannel") or {}).get("name")
        out.append({"nom": s["name"], "genres": s.get("genres"), "statut": s.get("status"), "premiere": s.get("premiered"), "fin": s.get("ended"),
                    "note": (s.get("rating") or {}).get("average"), "chaine": net, "resume": clean(s.get("summary"), 350), "lien": s.get("url")})
    return {"series": out}


def _offers(el, key):
    block = (el.get("promotions") or {}).get(key) or []
    return [o for group in block for o in group.get("promotionalOffers", [])]


def _epic_link(el):
    slug = el.get("productSlug") or next((m.get("pageSlug") for m in (el.get("offerMappings") or []) + ((el.get("catalogNs") or {}).get("mappings") or []) if m.get("pageSlug")), "")
    return f"https://store.epicgames.com/fr/p/{slug.split('/')[0]}" if slug else "https://store.epicgames.com/fr/free-games"


def _day(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%d")


def jeux_gratuits(chat_id, a):
    data = get_json("https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions", locale="fr", country="FR")
    items = (((data.get("data") or {}).get("Catalog") or {}).get("searchStore") or {}).get("elements") or []
    now, soon = [], []
    for el in items:
        price = ((el.get("price") or {}).get("totalPrice") or {}).get("discountPrice")
        live, nxt = _offers(el, "promotionalOffers"), _offers(el, "upcomingPromotionalOffers")
        if live and price == 0:
            now.append({"jeu": el["title"], "jusqu_au": _day(live[0]["endDate"]), "lien": _epic_link(el)})
        elif nxt:
            soon.append({"jeu": el["title"], "des_le": _day(nxt[0]["startDate"]), "lien": _epic_link(el)})
    return {"gratuits_maintenant": now, "bientot_gratuits": soon}


def prix_jeux(chat_id, a):
    rows = get_json("https://www.cheapshark.com/api/1.0/deals", title=text(a, "titre", "", 80), pageSize=5, sortBy="Price")
    if not rows:
        return {"erreur": "aucune offre trouvee pour ce jeu"}
    return {"offres": [{"jeu": r["title"], "prix_usd": r["salePrice"], "prix_normal_usd": r["normalPrice"], "reduction_pct": round(float(r["savings"])),
                        "note_metacritic": r.get("metacriticScore"), "lien": f"https://www.cheapshark.com/redirect?dealID={r['dealID']}"} for r in rows]}


KINDS = {"song": "song", "chanson": "song", "album": "album", "film": "movie", "movie": "movie", "podcast": "podcast", "audiobook": "audiobook", "livre": "audiobook"}


def musique_itunes(chat_id, a):
    entity = KINDS.get(text(a, "type", "song", 12).lower(), "song")
    rows = get_json("https://itunes.apple.com/search", term=text(a, "recherche", "", 80), entity=entity, limit=6, country="fr").get("results") or []
    if not rows:
        return {"erreur": "rien trouve"}
    return {"resultats": [{"titre": r.get("trackName") or r.get("collectionName"), "artiste": r.get("artistName"), "album": r.get("collectionName"),
                           "genre": r.get("primaryGenreName"), "annee": (r.get("releaseDate") or "")[:4], "lien": r.get("trackViewUrl") or r.get("collectionViewUrl"),
                           "extrait": r.get("previewUrl")} for r in rows]}


def ghibli(chat_id, a):
    films = get_json("https://ghibliapi.vercel.app/films")
    want = text(a, "titre", "", 80).lower()
    if not want:
        return {"films": [f"{f['title']} ({f['release_date']})" for f in sorted(films, key=lambda f: f["release_date"])]}
    hits = [f for f in films if want in f["title"].lower() or want in f.get("original_title_romanised", "").lower()]
    if not hits:
        return {"erreur": "film Ghibli introuvable (appelle sans titre pour voir la liste)"}
    f = hits[0]
    return {"titre": f["title"], "titre_original": f["original_title"], "annee": f["release_date"], "realisateur": f["director"], "duree_min": f["running_time"],
            "note_rotten_tomatoes": f["rt_score"], "resume": clean(f["description"], 450)}


FUNCS = {"recette": recette, "cocktail": cocktail, "pokemon": pokemon, "trivia": trivia, "blague": blague, "animal": animal, "citation": citation,
         "carte_magic": carte_magic, "serie_tv": serie_tv, "jeux_gratuits": jeux_gratuits, "prix_jeux": prix_jeux, "musique_itunes": musique_itunes, "ghibli": ghibli}
