<p align="center">
  <img src="../assets/logo.svg" alt="Instonct (Instant AI) - l'alternative auto-hébergée à Instinct AI, qui tourne sur un vieux Mac mini" width="760">
</p>

<p align="center">
  <b>Instonct, votre <i>Instant AI</i> : l'<a href="../README.md#instinct-ai-vs-instonct">alternative à Instinct AI</a> auto-hébergée.</b><br>
  Un agent IA personnel à qui vous écrivez comme à un ami, sur <b>WhatsApp</b> ou <b>Telegram</b>, hébergé sur votre propre vieux Mac mini.<br>
  Pas de liste d'invitation. Pas le cloud des autres. Vos mails, votre agenda, vos données restent chez vous.
</p>

<p align="center">
  <a href="../README.md">English</a> ·
  <a href="README.zh-CN.md">简体中文</a> ·
  <a href="README.ko.md">한국어</a> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.es.md">Español</a> ·
  <a href="README.pt-BR.md">Português</a> ·
  <b>Français</b> ·
  <a href="README.de.md">Deutsch</a> ·
  <a href="README.ru.md">Русский</a> ·
  <a href="README.hi.md">हिन्दी</a> ·
  <a href="README.ar.md">العربية</a>
</p>

> **Aucun lien avec Instinct AI ni avec Spear Street Technology.** « Instinct » appartient à son propriétaire.
> Instonct est un projet personnel indépendant. Le nom est une parodie assumée, et cette page
> le compare à Instinct AI uniquement pour que les personnes en quête d'une alternative puissent le trouver.

---

**Instonct** est un **agent IA personnel** open source et auto-hébergé. Vous lui écrivez sur **WhatsApp ou Telegram**
(texte ou message vocal) et il passe à l'action : il lit et rédige vos mails, gère votre Google Agenda, programme des rappels
et des tâches, navigue sur le web et remplit des formulaires, extrait une page web vers un CSV, surveille une page et vous prévient quand
elle change, lance de la musique, et exécute même des commandes shell sur la machine qui l'héberge.

Il tourne 24 h/24, 7 j/7 sur un **Mac mini de 2010** (Core 2 Duo, 4,6 Go de RAM, Lubuntu). Si ça marche là-dessus, ça marche sur
presque n'importe quoi : un Raspberry Pi, un vieux portable, un petit VPS.

## Ce qu'il sait faire

| Domaine | Ce que vous pouvez lui dire |
|---|---|
| **Mail** | « Des mails importants aujourd'hui ? », « Réponds à Paul que je suis partant. » N'envoie qu'après votre appui sur **Oui**. |
| **Agenda** | « Mets dentiste jeudi à 15 h », « Ajoute un Google Meet avec Marie ». Signale les conflits. |
| **Navigateur** | « Va sur news.ycombinator.com et donne-moi un CSV des 30 premiers titres », « Connecte-moi au site de ma salle de sport ». |
| **Surveillance** | « Préviens-moi quand cette page affichera *en stock*. » Vérifie toutes les 10 minutes ou plus, ne vous écrit qu'en cas de changement. |
| **Mémoire** | Retient qui vous êtes, vos préférences et vos projets, apprend de ce que vous écrivez (vos mots seulement), corrige les faits dépassés et ressort ce que vous avez déjà dit sur un sujet. En local, sans base vectorielle. `/memoire` la montre. |
| **Vraies démarches** | « Réserve-moi un week-end à Lisbonne », « Commande cette liste », « Conteste cette facture » : garde un dossier qui tient sur plusieurs jours, ouvre un vrai navigateur, remplit le panier ou le formulaire et **s'arrête au paiement** : vous recevez l'écran sur votre téléphone pour vous connecter et payer. Il ne paie jamais. |
| **Appels** | « Prépare mon appel à l'assurance » : trouve le numéro, donne un lien pour appeler d'un geste et quoi dire. C'est **vous** qui appelez : aucune ligne n'est branchée, et il ne peut pas prétendre le contraire. |
| **Actu et recherche** | « Les nouvelles sur X », « Creuse cette question » (lit les meilleures pages et les cite), préparation d'entretien (vos mails + l'entreprise + son actu), heure partout, jours fériés. |
| **Santé et vitesse** | `/sante` dit ce qui marche et ce qui ne marche pas, sans montrer de clé. `/vitesse` montre où part le temps. |
| **Routines** | Un briefing matinal (agenda, mails, météo, votre priorité n° 1), des rappels, des tâches planifiées. |
| **Voix** | Messages vocaux en entrée (Whisper), messages vocaux ou réponses parlées en sortie. |
| **Fichiers** | Envoyez-lui une photo, un PDF ou un CSV et posez-lui des questions dessus. Il peut aussi renvoyer des fichiers. |
| **Maison** | Musique, télécommande de TV, volume, état du serveur, commandes shell (avec confirmation). |
| **Toutes les langues** | Il répond dans la langue dans laquelle vous écrivez ou parlez. |

Il a aussi une personnalité : des réponses courtes, une recommandation claire, pas de blabla. Il s'appelle *Steve*.

## Choisissez votre cerveau : n'importe quel modèle, n'importe quel fournisseur

Instonct dialogue avec n'importe quelle **API compatible OpenAI**, vous n'êtes donc enfermé chez aucune entreprise. Renseignez trois lignes dans `.env` :

```bash
LLM_BASE_URL=https://api.groq.com/openai/v1     # la valeur par défaut
LLM_API_KEY=...
LLM_MODELS=openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b    # essayés dans cet ordre
```

| Fournisseur | `LLM_BASE_URL` |
|---|---|
| Groq (par défaut, rapide, offre gratuite) | `https://api.groq.com/openai/v1` |
| OpenRouter (des centaines de modèles) | `https://openrouter.ai/api/v1` |
| OpenAI | `https://api.openai.com/v1` |
| Together AI | `https://api.together.xyz/v1` |
| Mistral | `https://api.mistral.ai/v1` |
| Cerebras | `https://api.cerebras.ai/v1` |
| Ollama / LM Studio (100 % local, sans clé) | `http://localhost:11434/v1` |

Utilisez les noms de modèles exactement comme votre fournisseur les écrit, et choisissez des modèles qui prennent en charge l'appel d'outils.

- **Changement à la volée** : envoyez `/model` pour voir la liste, `/model 2` pour utiliser le numéro 2 en premier, `/model auto` pour revenir au réglage initial.
- **Bascule automatique** : si un modèle est limité en débit ou indisponible, le suivant prend le relais tout seul.
- **Filet de sécurité facultatif** : ajoutez `GEMINI_API_KEY` et Google Gemini répond quand votre fournisseur principal est en panne (et lit les images).
  Sans cela, Instonct fonctionne très bien avec un seul fournisseur.
- **Messages vocaux** : transcrits via une API Whisper (`STT_MODEL`, `STT_BASE_URL`, `STT_LANGUAGE`, même fournisseur par défaut).

## WhatsApp ou Telegram ?

Les deux fonctionnent, en même temps, avec le même cerveau, la même mémoire et les mêmes règles de sécurité.

| | Telegram | WhatsApp |
|---|---|---|
| Mise en place | 2 minutes avec @BotFather | Compte développeur Meta, un numéro, un jeton (environ 30 minutes) |
| Nécessite une adresse publique | Non (c'est le bot qui appelle) | Oui (Meta appelle votre serveur : Tailscale Funnel convient) |
| Boutons Oui / Non, voix, fichiers | Oui | Oui |
| Clavier de télécommande TV, enregistrement des mots de passe avec `/site` | Oui | Telegram uniquement (volontairement, voir Sécurité) |
| Messages envoyés par le bot de lui-même (rappels) | Toujours | Seulement dans les 24 h suivant votre dernier message |
| Déjà sur votre téléphone | Peut-être | Presque sûrement |

**Conseil honnête** : commencez par Telegram, c'est plus simple et plus sûr. Ajoutez WhatsApp quand vous voulez lui parler depuis l'appli
que vous utilisez déjà tous les jours. Instonct utilise l'**API officielle WhatsApp Cloud** de Meta, jamais une bibliothèque non officielle, donc il n'y
a aucun risque de voir votre numéro banni.

### Ajouter WhatsApp (facultatif)

1. Sur [developers.facebook.com](https://developers.facebook.com), créez une application, ajoutez le produit **WhatsApp** et notez le
   **Phone number ID**. Le numéro de test gratuit permet d'essayer ; vous pourrez rattacher votre propre numéro plus tard.
2. Créez un jeton d'accès permanent (un jeton *System User* dans les paramètres Meta Business) et copiez l'**App secret**
   (Paramètres de l'application, Général).
3. Ajoutez à `~/bots/.env` (votre propre numéro : uniquement des chiffres, indicatif du pays en premier, sans `+`) :
   ```bash
   WA_TOKEN=...
   WA_PHONE_ID=...
   WA_APP_SECRET=...
   WA_VERIFY_TOKEN=any-secret-string-you-invent
   WA_OWNER=33612345678
   ```
4. Donnez à Meta une adresse HTTPS publique pour le webhook local (port 8088, lié à `127.0.0.1`). Avec Tailscale :
   `sudo tailscale funnel --bg 8088`. La commande affiche une adresse `https://<machine>.<tailnet>.ts.net`.
5. Dans les paramètres WhatsApp de votre application Meta, indiquez cette adresse comme **Callback URL** du webhook et votre `WA_VERIFY_TOKEN`
   comme **Verify token**, puis abonnez-vous au champ **messages**.
6. Redémarrez le bot (`sudo systemctl restart bot-telegram`) et écrivez à votre numéro WhatsApp.

Tout appel entrant est rejeté si son en-tête `X-Hub-Signature-256` ne correspond pas à votre app secret, et seuls les numéros de
`WA_OWNER` reçoivent une réponse. Les intitulés du tableau de bord Meta changent de temps en temps ; le principe reste le même.
La version de l'API est `v23.0` par défaut ; remplacez-la avec `WA_API_VERSION` si Meta la retire.

## Instinct AI vs Instonct

| | Instinct AI | Instonct |
|---|---|---|
| Accès | Sur invitation uniquement (d'après la presse) | Clonez le dépôt et lancez-le |
| Où il tourne | Dans le cloud d'une entreprise | **Sur votre propre machine** |
| Vos données | Confiées à une startup | Restent sur votre machine (Redis + fichiers locaux) |
| Comment vous lui parlez | SMS, téléphone, WhatsApp (d'après la presse) | WhatsApp ou Telegram, texte ou voix |
| Modèles | Choisis pour vous | **N'importe quel fournisseur compatible OpenAI**, changement avec `/model` |
| Coût | Non communiqué | Les offres gratuites suffisent (Groq, Gemini) ; ou 100 % local avec Ollama |
| Code source | Fermé | **Juste ici** |
| Appels téléphoniques | Oui (d'après la presse) | **Non.** Il prépare l'appel (numéro, lien pour appeler, quoi dire) et vous appelez. De vrais appels demandent un opérateur payant, non inclus |
| Réservations, courses, litiges | Faits pour vous (d'après la presse) | Prépare tout dans un vrai navigateur jusqu'au paiement, puis vous passe l'écran. Les sites qui bloquent les robots (vus : Carrefour, Booking, Rome2Rio) peuvent le refuser |
| Installation | S'inscrire | `./install.sh` sur une machine Linux, plus un jeton Telegram et une clé de modèle. Ça reste votre serveur |
| Puissance et fiabilité | Une équipe et un support | Modèles gratuits avec quotas, votre matériel, pas de support. `/sante` vous dit ce qui est en panne |

Instinct AI est un vrai produit conçu par une équipe financée ; Instonct est le projet d'un week-end d'une seule personne, devenu son outil du quotidien.
Choisissez Instonct si vous voulez la même idée, mais avec les mains sur le volant.
Ce tableau est écrit par l'auteur d'Instonct, et ses protections **n'ont pas été auditées de façon indépendante** : un agent qui a accès à un shell, à vos mails et à votre agenda reste un vrai risque.

## Comment ça marche

- **Cerveau** : n'importe quel modèle compatible OpenAI (Groq `gpt-oss-120b` / `20b` par défaut, avec effort de raisonnement adaptatif), repli Gemini facultatif.
- **Outils** : le modèle appelle environ 35 outils (mail, agenda, navigateur, fichiers, musique, TV, shell...). Voir `TOOLS` dans [`catalog.py`](../bots/telegram-search/instonct/catalog.py).
- **Navigateur** : [Lightpanda](https://github.com/lightpanda-io/browser), un minuscule navigateur headless (~25 Mo de RAM) qui tourne même sur un processeur de 2010. Voir [`webagent.py`](../bots/telegram-search/instonct/webagent.py).
- **Canaux** : Telegram par long polling (aucun port ouvert), WhatsApp via [`whatsapp.py`](../bots/telegram-search/instonct/whatsapp.py) (un petit webhook sur `127.0.0.1`).
- **État** : Redis (historique, mémoire, rappels, surveillances).
- **Accès** : SSH + [Tailscale](https://tailscale.com), `ufw` fermé par défaut. La configuration du serveur est décrite dans [`home-server.md`](home-server.md).

## Sécurité, parce qu'un agent avec un shell en a besoin

- **Privé** : sur Telegram, la première personne qui envoie `/start` devient l'unique propriétaire ; sur WhatsApp, seuls les numéros de `WA_OWNER`
  reçoivent une réponse. Tous les autres sont ignorés.
- **Rien de risqué ne se fait en douce** : envoyer un mail, soumettre un formulaire, supprimer un événement ou lancer une commande
  demandent tous d'abord un appui sur **Oui / Non**.
- **Il ne paie jamais** : les boutons « Acheter / Payer / Commander » et les champs de carte sont refusés par du code simple, pas laissés au modèle. Vous recevez l'écran et vous payez vous-même.
- **Les mots de passe ne passent jamais par le modèle** : les identifiants de connexion aux sites sont stockés dans un fichier `0600` et saisis par du code ordinaire.
  Leur enregistrement est réservé à Telegram, car le bot supprime votre message juste après (WhatsApp le conserverait).
- **Les pages web sont des données, pas des ordres** : le texte trouvé sur une page ou dans un mail ne peut pas donner d'instructions à l'agent.
- **Pas de réseau local via le navigateur** : seules les adresses `http(s)` publiques sont autorisées (protection SSRF).
- **Jamais de secrets dans ce dépôt** : les clés vivent dans un `.env` sur le serveur.

## Démarrage rapide

Il vous faut une machine Debian ou Ubuntu, un **jeton de bot Telegram** (obtenu auprès de [@BotFather](https://t.me/BotFather)) et une
**clé d'API** de n'importe quel fournisseur ci-dessus (Groq propose une offre gratuite).

```bash
git clone https://github.com/LdwS123/Instonct.git && cd Instonct
./install.sh            # ajoutez --dry-run pour voir d'abord ce qu'il ferait
```

Il installe les paquets, demande vos clés (cachées à la frappe, testées avant d'être enregistrées, en `0600`), démarre le service
et vérifie que tout répond. Ensuite **envoyez `/start` à votre bot tout de suite, vous-même** : la première personne qui le fait en devient l'unique propriétaire.

`/sante` montre ce qu'il reste à régler. En option : `MAIL_USER` / `MAIL_PASS` / `MAIL_HOST` pour le mail, `scripts/google-auth.py`
pour Google Agenda. Le vrai navigateur demande `chromium`, `xvfb`, `openbox`, `x11vnc`, `novnc` et [Tailscale](https://tailscale.com) ; il prend environ 800 Mo de RAM
quand il est ouvert, donc le service a droit à 1500 Mo (`MemoryMax` dans le fichier du service).

Pour changer les clés plus tard : modifiez `~/bots/.env`, puis `sudo systemctl restart bot-telegram`. Pour vérifier à tout moment : `python bot.py doctor`.

## Vous cherchez...

Instant AI · alternative à Instinct AI (Instinct AI alternative) · Instinct AI open source · agent IA personnel auto-hébergé · écrire à son assistant IA ·
assistant IA sur WhatsApp · assistant IA sur Telegram · agent IA WhatsApp · alternative à OpenClaw (OpenClaw alternative) · agent IA qui lit vos mails et
gère votre agenda · faire tourner un agent IA sur un Raspberry Pi ou un vieux Mac mini · assistant IA pour serveur domestique · agent Groq · agent Gemini ·
agent Ollama · agent OpenRouter · agent navigateur Lightpanda · scraper web IA vers CSV · assistant IA privé, sans cloud.

---

<sub>Instonct est un projet indépendant, sans affiliation avec Instinct AI ni Spear Street Technology, Inc., et ni approuvé ni sponsorisé par ces derniers.
Toutes les marques appartiennent à leurs propriétaires respectifs. Licence MIT.</sub>
