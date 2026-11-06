"""Tools about France and the physical world, from free public sources with no key: communes, addresses, companies, electricity mix,
fuel prices, postal codes, altitude, sea, pollen, past weather, rocket launches, molecules, food by barcode, free images.

Every answer comes from a web service, so every tool is named in TAINT (the text was not written by the user).
"""

import re
from datetime import date, datetime, timedelta
from urllib.parse import quote

from .kit_base import clean, get_json, get_json_or_none, locate, num, spec, text, whole

SPECS = [
    spec("commune_fr", "Fiche d'une commune francaise : population, departement, region, surface, codes postaux (par nom ou code postal).", nom="string", code_postal="string"),
    spec("adresse_fr", "Trouve une adresse en France (base officielle) : adresse complete, code postal, commune et coordonnees GPS.", adresse="string!"),
    spec("entreprise_fr", "Cherche une entreprise francaise (nom ou SIREN) : siege, activite, date de creation, effectif, etat.", recherche="string!"),
    spec("electricite_fr", "Electricite en France maintenant : consommation, production par filiere (nucleaire, eolien, solaire...) et CO2 par kWh."),
    spec("carburant_fr", "Prix des carburants dans une ville de France (gazole, sp95, sp98, e10, e85, gplc) : les stations les moins cheres.", ville="string!", carburant="string"),
    spec("code_postal", "Ville d'un code postal dans un pays (fr, de, us, gb, es, it, be, ch, ca...) avec coordonnees.", code="string!", pays="string"),
    spec("elevation", "Altitude (en metres) d'une ville ou de coordonnees GPS.", ville="string", latitude="number", longitude="number"),
    spec("marine", "Etat de la mer pres d'une ville cotiere : hauteur des vagues, periode, direction, temperature de l'eau.", ville="string!"),
    spec("pollen", "Niveau de pollen maintenant dans une ville d'Europe (bouleau, graminees, ambroisie, olivier...).", ville="string!"),
    spec("meteo_historique", "Meteo passee d'une ville : temperatures et pluie jour par jour entre deux dates (31 jours max).", ville="string!", debut="string!", fin="string"),
    spec("space_launches", "Prochains lancements de fusees dans le monde : date, fusee, mission, statut.", nombre="integer"),
    spec("molecule", "Formule, masse et nom chimique d'une molecule ou d'un produit (ex. aspirine, cafeine, glucose).", nom="string!"),
    spec("nutrition", "Fiche d'un produit alimentaire par code-barres (EAN) : marque, Nutri-Score, NOVA, calories, sucres, sel pour 100 g.", code_barres="string!"),
    spec("image_libre", "Cherche une image libre de droits sur Wikimedia Commons : lien, licence et auteur.", recherche="string!"),
]
GROUPS = [
    (r"commune|population de |habitants? (?:de|a) |combien d.habitants|code insee|departement de|region de|surface de la (?:ville|commune)", {"commune_fr"}),
    (r"adresse (?:de |du |d.)|trouve l.adresse|coordonnees gps|latitude|longitude|geocode|ou se trouve le \d", {"adresse_fr"}),
    (r"entreprise|societe |siren|siret|boite (?:de|qui)|infogreffe|dirigeant|creee en|chiffre d.affaires", {"entreprise_fr"}),
    (r"electricite|courant electrique|production d.electricite|nucleaire|eolien|panneaux solaires? en france|mix energetique|co2 par kwh|reseau electrique|\brte\b|eco2mix", {"electricite_fr"}),
    (r"carburant|essence|gazole|diesel|sp95|sp98|\be10\b|\be85\b|\bgpl\b|prix du plein|station.?service|moins cher.* (?:essence|gazole)", {"carburant_fr"}),
    (r"code postal|zip ?code|postcode|cp de ", {"code_postal"}),
    (r"altitude|elevation|a quelle hauteur|metres? au.dessus de la mer|denivele", {"elevation"}),
    (r"vagues?|houle|etat de la mer|temperature de l.eau|mer (?:agitee|calme)|\bsurf\b|plage.*(?:eau|mer)", {"marine"}),
    (r"pollen|allergie|rhume des foins|graminees|bouleau|ambroisie", {"pollen"}),
    (r"meteo (?:du|de la semaine|passee|historique)|il a fait combien (?:le|en|hier)|temperature (?:le|du|en) \d|archives? meteo|combien de pluie|meteo d.il y a", {"meteo_historique"}),
    (r"lancements? de fusees?|prochaine fusee|spacex|ariane|starship|mission spatiale|launch|nasa.*lanc", {"space_launches"}),
    (r"molecule|formule chimique|formule de l.|masse molaire|composition chimique|c\d+h\d+|caffeine|cafeine|aspirine|paracetamol|glucose|compose chimique", {"molecule"}),
    (r"nutri.?score|code.?barres?|\bean\b|calories? (?:du|de ce|dans ce) produit|ce produit (?:est.il|est) (?:sain|bon)|\b\d{8,14}\b.*produit|produit.*\b\d{8,14}\b|additifs?|\bnova\b", {"nutrition"}),
    (r"image libre|photo libre|libre de droits?|wikimedia|commons|image sans droit|photo gratuite|illustration gratuite", {"image_libre"}),
]
TAINT = {s["name"] for s in SPECS}


def _lat_lon(a):
    """(latitude, longitude, label) from a city name or from explicit coordinates."""
    if a.get("ville"):
        lat, lon, name, country = locate(text(a, "ville", "", 80))
        return lat, lon, f"{name} ({country})" if country else name
    if a.get("latitude") is not None and a.get("longitude") is not None:
        lat, lon = num(a, "latitude", 0, -90, 90), num(a, "longitude", 0, -180, 180)
        return lat, lon, f"{lat:.4f}, {lon:.4f}"
    raise LookupError("donne une ville ou des coordonnees")


def commune_fr(chat_id, a):
    name, zipcode = text(a, "nom", "", 80), re.sub(r"\D", "", text(a, "code_postal", "", 10))
    if not name and len(zipcode) != 5:
        return {"erreur": "donne un nom de commune ou un code postal a 5 chiffres"}
    params = {"fields": "nom,code,codesPostaux,population,departement,region,surface", "limit": 5, "boost": "population"}
    rows = get_json("https://geo.api.gouv.fr/communes", **params, **({"codePostal": zipcode} if len(zipcode) == 5 and not name else {"nom": name}))
    if not rows:
        return {"erreur": "aucune commune trouvee"}
    return {"communes": [{"nom": r["nom"], "code_insee": r["code"], "population": r.get("population"), "departement": (r.get("departement") or {}).get("nom"),
                          "code_departement": (r.get("departement") or {}).get("code"), "region": (r.get("region") or {}).get("nom"),
                          "surface_km2": round(r["surface"] / 100, 1) if r.get("surface") else None, "codes_postaux": (r.get("codesPostaux") or [])[:8]} for r in rows]}


def adresse_fr(chat_id, a):
    data = get_json("https://api-adresse.data.gouv.fr/search/", q=text(a, "adresse", "", 200), limit=3)
    found = data.get("features") or []
    if not found:
        return {"erreur": "adresse introuvable"}
    out = []
    for f in found:
        p, lon_lat = f["properties"], (f.get("geometry") or {}).get("coordinates") or [None, None]
        out.append({"adresse": p.get("label"), "code_postal": p.get("postcode"), "commune": p.get("city"), "contexte": p.get("context"), "fiabilite": round(p.get("score", 0), 2),
                    "latitude": lon_lat[1], "longitude": lon_lat[0], "carte": f"https://www.openstreetmap.org/?mlat={lon_lat[1]}&mlon={lon_lat[0]}&zoom=17"})
    return {"adresses": out}


ACTIVITY = {"A": "agriculture", "C": "industrie", "F": "construction", "G": "commerce", "I": "hotellerie-restauration", "J": "information-communication", "K": "finance-assurance",
            "L": "immobilier", "M": "services aux entreprises", "N": "services administratifs", "P": "enseignement", "Q": "sante", "R": "arts-loisirs", "S": "autres services"}


def entreprise_fr(chat_id, a):
    query = text(a, "recherche", "", 120)
    data = get_json("https://recherche-entreprises.api.gouv.fr/search", q=query, per_page=4)
    rows = data.get("results") or []
    if not rows:
        return {"erreur": "aucune entreprise trouvee"}
    out = []
    for r in rows:
        head = r.get("siege") or {}
        out.append({"nom": clean(r.get("nom_complet"), 120), "siren": r.get("siren"), "etat": "active" if r.get("etat_administratif") == "A" else "fermee ou inactive",
                    "creation": r.get("date_creation"), "activite_code": r.get("activite_principale"), "adresse_siege": clean(head.get("adresse") or head.get("geo_adresse"), 160),
                    "etablissements": r.get("nombre_etablissements"), "effectif_tranche": r.get("tranche_effectif_salarie"), "categorie": r.get("categorie_entreprise"),
                    "dirigeants": [clean(f"{d.get('prenoms', '')} {d.get('nom', '')}".strip() or d.get("denomination"), 60) for d in (r.get("dirigeants") or [])[:3]],
                    "fiche": f"https://annuaire-entreprises.data.gouv.fr/entreprise/{r.get('siren')}"})
    return {"entreprises": out}


FILIERES = ("nucleaire", "eolien", "solaire", "hydraulique", "gaz", "charbon", "fioul", "bioenergies", "pompage")


def electricite_fr(chat_id, a):
    data = get_json("https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/eco2mix-national-tr/records", limit=1, order_by="date_heure desc", where="consommation is not null")
    rows = data.get("results") or []
    if not rows:
        return {"erreur": "pas de donnees RTE pour le moment"}
    f = rows[0]
    prod = {k: f[k] for k in FILIERES if isinstance(f.get(k), (int, float))}
    total = sum(v for v in prod.values() if v > 0)
    return {"date_locale": f.get("date"), "heure_locale": f.get("heure"), "consommation_MW": f.get("consommation"), "production_MW": prod,
            "parts_pct": {k: round(v / total * 100) for k, v in prod.items() if total and v > 0}, "co2_g_par_kwh": f.get("taux_co2"), "echanges_MW": f.get("ech_physiques"),
            "source": "RTE eco2mix (donnees quasi temps reel)"}


FUELS = {"gazole": "gazole_prix", "diesel": "gazole_prix", "sp95": "sp95_prix", "sp98": "sp98_prix", "e10": "e10_prix", "e85": "e85_prix", "gpl": "gplc_prix", "gplc": "gplc_prix"}


def carburant_fr(chat_id, a):
    city = re.sub(r"[^A-Za-zÀ-ÿ' -]", "", text(a, "ville", "", 60)).strip()
    fuel = FUELS.get(text(a, "carburant", "gazole", 10).lower())
    if not city:
        return {"erreur": "donne une ville"}
    if not fuel:
        return {"erreur": "carburants : gazole, sp95, sp98, e10, e85, gplc"}
    data = get_json("https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/prix-des-carburants-en-france-flux-instantane-v2/records", timeout=20,
                    limit=8, where=f'ville="{city.title()}" and {fuel} is not null', order_by=fuel, select=f"adresse,ville,{fuel}")
    rows = data.get("results") or []
    if not rows:
        return {"erreur": f"aucune station avec ce carburant a {city.title()} (ecris la ville avec ses accents)"}
    return {"carburant": fuel.replace("_prix", ""), "ville": city.title(), "moins_chers": [{"prix_eur_litre": r[fuel], "adresse": clean(r.get("adresse"), 80)} for r in rows],
            "source": "prix-carburants.gouv.fr (donnees ouvertes)"}


def code_postal(chat_id, a):
    country, code = re.sub(r"[^a-z]", "", text(a, "pays", "fr", 3).lower()) or "fr", re.sub(r"[^\w -]", "", text(a, "code", "", 12))
    if not code:
        return {"erreur": "donne un code postal"}
    d = get_json_or_none(f"https://api.zippopotam.us/{country}/{quote(code.replace(' ', ''))}")
    if not d:
        return {"erreur": f"code postal {code} inconnu pour le pays {country}"}
    return {"code": d.get("post code"), "pays": d.get("country"), "lieux": [{"nom": p.get("place name"), "region": p.get("state"), "latitude": p.get("latitude"), "longitude": p.get("longitude")}
                                                                          for p in (d.get("places") or [])[:6]]}


def elevation(chat_id, a):
    try:
        lat, lon, label = _lat_lon(a)
    except LookupError as e:
        return {"erreur": str(e)}
    values = get_json("https://api.open-meteo.com/v1/elevation", latitude=lat, longitude=lon).get("elevation") or []
    return {"lieu": label, "altitude_m": values[0]} if values else {"erreur": "altitude indisponible"}


def marine(chat_id, a):
    lat, lon, name, _ = locate(text(a, "ville", "", 80))
    data = get_json("https://marine-api.open-meteo.com/v1/marine", latitude=lat, longitude=lon, current="wave_height,wave_direction,wave_period,sea_surface_temperature")
    cur = data.get("current") or {}
    if data.get("error") or cur.get("wave_height") is None:
        return {"erreur": f"pas de donnees de mer pres de {name} (ville loin de la cote ?)"}
    return {"lieu": name, "vagues_m": cur["wave_height"], "periode_s": cur.get("wave_period"), "direction_deg": cur.get("wave_direction"), "eau_c": cur.get("sea_surface_temperature"), "heure": cur.get("time")}


POLLENS = {"alder_pollen": "aulne", "birch_pollen": "bouleau", "grass_pollen": "graminees", "mugwort_pollen": "armoise", "olive_pollen": "olivier", "ragweed_pollen": "ambroisie"}


def _pollen_level(value):
    return "nul" if value < 1 else "faible" if value < 20 else "modere" if value < 100 else "eleve" if value < 300 else "tres eleve"


def pollen(chat_id, a):
    lat, lon, name, _ = locate(text(a, "ville", "", 80))
    cur = get_json("https://air-quality-api.open-meteo.com/v1/air-quality", latitude=lat, longitude=lon, current=",".join(POLLENS)).get("current") or {}
    levels = {fr: {"grains_par_m3": cur[k], "niveau": _pollen_level(cur[k])} for k, fr in POLLENS.items() if isinstance(cur.get(k), (int, float))}
    if not levels:
        return {"erreur": f"pas de donnees de pollen pour {name} (disponible seulement en Europe, et selon la saison)"}
    return {"lieu": name, "heure": cur.get("time"), "pollens": levels}


def _day(value, default=None):
    value = str(value or "").strip()
    if not value:
        return default
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"date illisible : {value[:20]} (ecris AAAA-MM-JJ)")


def meteo_historique(chat_id, a):
    try:
        start = _day(a.get("debut"))
        end = _day(a.get("fin"), start)
    except ValueError as e:
        return {"erreur": str(e)}
    if not start or end < start:
        return {"erreur": "donne une date de debut (et une fin apres le debut)"}
    if (end - start).days > 30:
        return {"erreur": "31 jours au maximum"}
    if end >= date.today() - timedelta(days=2):
        return {"erreur": "les archives ne couvrent pas les 2 derniers jours (utilise la meteo normale)"}
    lat, lon, name, _ = locate(text(a, "ville", "", 80))
    d = get_json("https://archive-api.open-meteo.com/v1/archive", latitude=lat, longitude=lon, start_date=start.isoformat(), end_date=end.isoformat(),
                 daily="temperature_2m_max,temperature_2m_min,precipitation_sum", timezone="auto").get("daily") or {}
    days = [{"jour": t, "max_c": hi, "min_c": lo, "pluie_mm": rain} for t, hi, lo, rain in zip(d.get("time", []), d.get("temperature_2m_max", []), d.get("temperature_2m_min", []), d.get("precipitation_sum", []))]
    if not days:
        return {"erreur": "pas de donnees pour ces dates"}
    highs = [x["max_c"] for x in days if x["max_c"] is not None]
    return {"lieu": name, "jours": days, "resume": {"max_c": max(highs) if highs else None, "pluie_totale_mm": round(sum(x["pluie_mm"] or 0 for x in days), 1)}}


def space_launches(chat_id, a):
    data = get_json("https://ll.thespacedevs.com/2.2.0/launch/upcoming/", timeout=20, limit=whole(a, "nombre", 6, 1, 15), mode="list")
    rows = data.get("results") or []
    if not rows:
        return {"erreur": "aucun lancement annonce"}
    return {"lancements": [{"nom": clean(r.get("name"), 100), "date_utc": r.get("net"), "statut": (r.get("status") or {}).get("name"), "fournisseur": r.get("lsp_name"),
                            "mission": clean((r.get("mission") or {}).get("description") if isinstance(r.get("mission"), dict) else r.get("mission"), 160) or None,
                            "site": (r.get("pad") or {}).get("name") if isinstance(r.get("pad"), dict) else r.get("pad")} for r in rows],
            "note": "dates previsionnelles : elles bougent souvent"}


def molecule(chat_id, a):
    name = text(a, "nom", "", 80)
    if not name:
        return {"erreur": "donne un nom"}
    d = get_json_or_none(f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{quote(name, safe='')}/property/MolecularFormula,MolecularWeight,IUPACName/JSON", timeout=15)
    rows = ((d or {}).get("PropertyTable") or {}).get("Properties") or []
    if not rows:
        return {"erreur": f"molecule inconnue : {name} (essaie le nom anglais)"}
    r = rows[0]
    return {"nom": name, "formule": r.get("MolecularFormula"), "masse_molaire_g_mol": r.get("MolecularWeight"), "nom_iupac": clean(r.get("IUPACName"), 160),
            "fiche": f"https://pubchem.ncbi.nlm.nih.gov/compound/{r.get('CID')}"}


def _grade(value):
    """A to E, or "?" when Open Food Facts has no grade ("unknown", "not-applicable")."""
    g = str(value or "").strip().upper()
    return g if g in ("A", "B", "C", "D", "E") else "?"


def nutrition(chat_id, a):
    code = re.sub(r"\D", "", text(a, "code_barres", "", 20))
    if not 8 <= len(code) <= 14:
        return {"erreur": "un code-barres fait 8 a 14 chiffres"}
    d = get_json_or_none(f"https://world.openfoodfacts.org/api/v2/product/{code}.json", timeout=15, fields="product_name,brands,nutriscore_grade,nova_group,quantity,nutriments,ecoscore_grade")
    prod = (d or {}).get("product")
    if not prod or d.get("status") == 0:
        return {"erreur": "produit absent d'Open Food Facts"}
    n = prod.get("nutriments") or {}
    return {"produit": clean(prod.get("product_name"), 100), "marque": clean(prod.get("brands"), 60), "quantite": prod.get("quantity"),
            "nutriscore": _grade(prod.get("nutriscore_grade")), "nova": prod.get("nova_group"), "ecoscore": _grade(prod.get("ecoscore_grade")),
            "pour_100g": {"calories_kcal": n.get("energy-kcal_100g"), "graisses_g": n.get("fat_100g"), "dont_satures_g": n.get("saturated-fat_100g"), "sucres_g": n.get("sugars_100g"),
                          "sel_g": n.get("salt_100g"), "proteines_g": n.get("proteins_100g"), "fibres_g": n.get("fiber_100g")},
            "note": "base collaborative : peut etre incomplete"}


def image_libre(chat_id, a):
    d = get_json("https://commons.wikimedia.org/w/api.php", action="query", generator="search", gsrsearch=text(a, "recherche", "", 100), gsrnamespace=6, gsrlimit=4,
                 prop="imageinfo", iiprop="url|extmetadata", iiurlwidth=800, format="json")
    pages = list(((d.get("query") or {}).get("pages") or {}).values())
    out = []
    for p in sorted(pages, key=lambda x: x.get("index", 0)):
        info = (p.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        if not info.get("url") or not str(info["url"]).split("?")[0].lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg")):
            continue
        out.append({"titre": clean(p.get("title", "").replace("File:", ""), 100), "image": info.get("thumburl") or info["url"], "original": info["url"], "page": info.get("descriptionurl"),
                    "licence": clean((meta.get("LicenseShortName") or {}).get("value"), 40), "auteur": clean((meta.get("Artist") or {}).get("value"), 80)})
    return {"images": out, "rappel": "respecte la licence et cite l'auteur"} if out else {"erreur": "aucune image libre trouvee"}


FUNCS = {"commune_fr": commune_fr, "adresse_fr": adresse_fr, "entreprise_fr": entreprise_fr, "electricite_fr": electricite_fr, "carburant_fr": carburant_fr, "code_postal": code_postal,
         "elevation": elevation, "marine": marine, "pollen": pollen, "meteo_historique": meteo_historique, "space_launches": space_launches, "molecule": molecule,
         "nutrition": nutrition, "image_libre": image_libre}
