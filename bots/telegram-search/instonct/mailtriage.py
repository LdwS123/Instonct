"""Mail triage for Instonct: decides if a mail is IMPORTANT (answer to an application, interview, invoice, parcel, security, a real person...)
or just ADVERTISING / newsletter. No AI call, no quota: simple rules on the sender, the subject, the body start and two headers.

classify(sender, subject, body="", bulk=False) -> {"niveau": "important" | "pub", "type": str, "label": str, "raison": str}
  bulk = True when the mail has a List-Unsubscribe header or "Precedence: bulk" (typical of newsletters and ads).
Rule of thumb: better one ad too many than one missed acceptance, so only clear ads are put aside.
"""
import re
import unicodedata


def _n(s):
    s = str(s or "").replace("\u2019", "'").replace("\u2018", "'")            # curly apostrophes (n’a pas, don’t) would otherwise disappear
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s)


def _rx(p):
    return re.compile(p, re.I)


# ---- job hunting
JOB_ALERT = _rx(r"offres? d.emploi|nouvelles? offres?|alertes? emploi|job alert|jobs? (for you|you may|recommended)|recommandations? d.emploi|"
                r"postes? (pour vous|qui vous)|emplois? (pour vous|correspondant)|des offres|offres? pour vous|vous pourriez (aimer|etre interesse)|"
                r"\d+ nouveaux? (emplois?|postes?|jobs?)|ils recrutent|recrute(nt)? (en ce moment|pres de)")
CTX = _rx(r"candidature|candidat|recrut|embauche|\bposte\b|offre d.emploi|application|applying|hiring|talent|ressources humaines|"
          r"\brh\b|recruiter|recruteur|\bjob\b|position|\bcdi\b|\bcdd\b|alternance|stage\b")
NEG = _rx(r"malheureusement|regrett?ons?|nous (ne )?(pouvons|retenons|allons) pas|ne pas (donner suite|poursuivre|retenir)|n.a pas (ete )?retenue?|"
          r"pas ete retenue?|non retenue?|candidature (n.a pas|ne )|autres? (candidats?|profils?)|poursuivre avec (d.autres|un autre)|"
          r"unfortunately(?!.{0,40}(repl|read|receiv|respond)).{0,140}(not (be )?(moving|progressing|proceeding|able|selected|move|invit)|won.t|unable|"
          r"decided not|no relevant|don.t have|not to move|not (be )?(taking|going))|regret to|not (be )?(moving|going|progressing) forward|"
          r"decided (not )?to (move|proceed|pursue)(?!( forward| ahead)? with (you|your)\b)|"
          r"won.t be (moving|proceeding)|(profil|candidature|experience).{0,60}ne correspond pas|ne correspond pas .{0,40}(profil|poste|attentes|recherche)|ne donnerons pas suite")
# Said in a real refusal. Plain "unfortunately" is not enough in an acknowledgement ("unfortunately we cannot answer everyone").
FIRM_NEG = _rx(r"regret to|regrett?ons?|malheureusement,? (nous|votre)|(will not|won.t|not) (be )?(mov|proceed|progress)|position has (now )?been filled|"
               r"decided (not )?to (move|proceed|pursue)|poursuivre avec (d.autres|un autre)|n.a pas (ete )?retenue?|pas ete retenue?|ne donnerons pas suite|ne pas (donner suite|poursuivre|retenir)")
POS = _rx(r"felicitations|nous avons le plaisir|heureux (de|d.) (vous )?(annoncer|informer|proposer|accueillir)|ravis (de|d.)|"
          r"candidature (a (ete )?retenue|est retenue|retenue)|votre profil (nous a|a retenu)|nous souhaitons (vous )?(rencontrer|proposer|inviter|poursuivre)|"
          r"proposition d.embauche|promesse d.embauche|offre (ferme|de contrat)|contrat (de travail )?(a signer|joint)|bienvenue (chez|dans l.equipe)|"
          r"congratulations|pleased to (offer|invite|inform)|we.d like to (invite|schedule|offer|meet)|we would like to (invite|schedule|offer|meet)|"
          r"happy to (offer|invite)|offer letter|you.ve been (selected|shortlisted)|vous (etes|avez ete) (selectionne|retenu)")
STEP = _rx(r"entretien|interview|rendez-vous|\brdv\b|creneau|disponibilites?|visio|google meet|microsoft teams|teams meeting|reunion teams|zoom\.us|sur zoom|via zoom|zoom meeting|appel (telephonique|de presentation)|"
           r"echange (telephonique|visio)|test (technique|de personnalite)|etape suivante|prochaine etape|next step|case study|"
           r"prise de contact|premier echange|schedule a call|book a (time|call|slot)|calendly|invitation:")
# In the body, "application", "position" or "job" often mean something else ("your Stripe application", "our position on privacy").
STRONG_CTX = _rx(r"candidature|candidat|recrut|embauche|applying|your application (to|for|at|with)\b|appl(y|ied) (for|to) the .{0,60}(position|role|poste)|(for|on|about|regarding) your application|recruiter|recruteur|hiring (team|manager)|offre d.emploi|ressources humaines")
# An acknowledgement ("thanks for applying") usually describes the process, so words like "interview" in it promise nothing.
ACK = _rx(r"(merci|thanks?|thank you)\b.{0,30}(candidature|application|applying|to apply|postul|interest in|votre interet)|bien recue?\b|avons (bien )?recu|a bien ete (recue?|envoyee|transmise|enregistree)|"
          r"(we.ve|we have|we) received|received your|application (was |has been |is )?(received|submitted|sent|complete)|candidature (bien )?(recue|envoyee|enregistree|transmise)|"
          r"your application (to|for|at|with)\b|confirmation de (votre |ta )?candidature")
REAL_NEXT = _rx(r"we.d like to (invite|schedule|meet|move)|we would like to (invite|schedule|meet|move)|(pleased|happy|excited|delighted) to (invite|move|offer)|"
                r"invited? you to (an? |your |our )?(\w+ )?(interview|call|meeting|chat|video|complete|schedule|book|take)|you.ve been (selected|shortlisted|invited)|"
                r"nous souhaitons (vous )?(rencontrer|inviter|poursuivre)|nous (aimerions|voudrions) (vous )?(rencontrer|echanger|planifier)|"
                r"(choose|pick|select|book) (a |your )?(time|slot|creneau)|calendly\.com|vos disponibilites|(share|send|give|indicate)\b.{0,12}your availability|"
                r"complete (the|this|your) (assessment|test|questionnaire|video)|"
                r"(felicitations|congratulations)(?! (on|pour|d.avoir) (\w+ ){0,2}(taking|completing|applying|candidature|postule|first))")
_CONDITIONAL = _rx(r"\b(if|should|once|may|might|whether|likely|si|lorsque|au cas|eventuellement|peut-etre|probablement)\b")
INTERVIEW_SUBJECT = _rx(r"entretien|interview|rendez-vous|\brdv\b|next step|prochaine etape|assessment|case study|invitation|meeting|time confirmed|\bscreen\b|\bcall\b")
# ---- other things that matter
FACTURE = _rx(r"facture|invoice|\brecu\b|receipt|paiement|payment|prelevement|echeance|relance|rappel de paiement|amende|avis d.imposition|"
              r"impots?|remboursement|refund|virement|\bsolde\b|quittance|loyer|abonnement (renouvel|expir)")
COLIS = _rx(r"colis|livraison (prevue|aujourd|demain|en cours|effectuee)|votre commande|commande (n|expediee|confirmee|#)|expedi|suivi de (colis|commande)|"
            r"point relais|mondial relay|colissimo|chronopost|\bups\b|\bdhl\b|\bfedex\b|\bdpd\b|out for delivery|your (order|package|parcel)|a ete livre")
SECURITE = _rx(r"code (de )?(verification|securite|confirmation|connexion|a usage unique)|verification code|one-time|\botp\b|\b2fa\b|mot de passe|password|"
               r"nouvelle connexion|connexion (suspecte|inhabituelle)|nouvel appareil|new (sign-in|login|device)|activite suspecte|suspicious|"
               r"securite de votre compte|security alert|alerte de securite|compte (bloque|suspendu|piratage)")
RDV = _rx(r"invitation|convocation|rendez-vous|reunion|meeting|rappel de rendez-vous|appointment|confirmation de (votre )?(rdv|reservation|rendez-vous)|"
          r"reservation|\.ics")
ADMIN_SENDER = _rx(r"francetravail|pole-?emploi|ameli|assurance-?maladie|\bcaf\b|caf\.fr|impots\.gouv|ants\.gouv|service-public|urssaf|"
                   r"cpam|banque|bnp|societegenerale|credit-?agricole|boursorama|revolut|n26|paypal|\.gouv\.fr")
# ---- advertising
PROMO = _rx(r"-\s?\d+\s?(%|€|eur)|\d+\s?(%|€)\s?(de reduction|offert|de remise|sur)|promo|soldes?|reduction|remise|bon plan|code promo|vente flash|"
            r"black friday|cyber monday|french days|derniers? jours|derniere chance|dernier(s)? (jours|instants)|ne manquez pas|profitez|"
            r"offre (speciale|exclusive|limitee|du moment)|exclusif|exclusive|gratuit|offert|cadeau|jeu concours|gagnez|economisez|"
            r"newsletter|a ne pas rater|nouveaute|nouvelle collection|decouvrez|\bdeals?\b|% off|sale\b|limited time|don.t miss|free shipping|"
            r"livraison offerte|parrain|votre avis (nous|compte)|donnez votre avis|enquete|sondage")
NOISE_SENDER = _rx(r"newsletter|marketing|promo|mailer-daemon|updates@|news@|offres?@|deals?@|hello@|bonjour@|contact@|info@|infos@|team@|"
                   r"communication@|communaute|publicite|digest@|actualites?@")
NOREPLY = _rx(r"no-?reply|do-?not-?reply|ne-?pas-?repondre|notifications?@|notify@|automated@|mailer@|bounce")


def _res(niveau, typ, label, raison):
    return {"niveau": niveau, "type": typ, "label": label, "raison": raison}


def _hit(rx, text):
    m = rx.search(text)
    return m.group(0).strip() if m else ""


def _said_firmly(rx, text):
    """A statement, not a possibility: "if your profile matches, we will invite you" invites nobody."""
    return any(not _CONDITIONAL.search(text[max(0, m.start() - 80):m.start()]) for m in rx.finditer(text))


def _only_acknowledges(sub, txt, scope):
    if not (ACK.search(sub) or ACK.search(txt[:600])):
        return False
    return not INTERVIEW_SUBJECT.search(sub) and not _said_firmly(REAL_NEXT, scope)


def classify(sender, subject, body="", bulk=False):
    frm, sub = _n(sender), _n(subject)
    txt = _n(body)[:2500]
    subject_and_body = sub + " " + txt
    scope = sub if bulk else subject_and_body            # newsletters mention "candidature" everywhere: for them only the subject counts

    # 1. job alerts ("12 nouvelles offres pour vous") are ads, even though they talk about jobs
    h = _hit(JOB_ALERT, sub)
    if h:
        return _res("pub", "alerte emploi", "Pub : alerte d'offres d'emploi", f"« {h} »")

    # 2. answer to an application / interview (the thing that matters most)
    if CTX.search(sub) or (not bulk and (CTX.search(frm) or STRONG_CTX.search(txt))):
        h = _hit(NEG, scope)
        if h and (_said_firmly(FIRM_NEG, scope) or not ACK.search(sub)):
            return _res("important", "refus", "REFUS de candidature", f"« {h} »")
        if _only_acknowledges(sub, txt, scope):
            return _res("important", "candidature", "Candidature : bien recue", "simple accuse de reception")
        h = _hit(POS, scope)
        if h:
            return _res("important", "acceptation", "BONNE NOUVELLE : acceptation ou suite positive", f"« {h} »")
        h = _hit(STEP, scope)
        if h:
            return _res("important", "etape", "Candidature : prochaine etape / entretien", f"« {h} »")
        if CTX.search(sub) and not PROMO.search(sub):
            return _res("important", "candidature", "Candidature : reponse a lire", "le sujet parle de ta candidature")
    elif not bulk:
        h = _hit(NEG, sub) or ""
        if h and _hit(STEP, sub):
            return _res("important", "refus", "REFUS probable", f"« {h} »")

    # 2b. a subject that talks about an interview is always worth a look, even from an automatic sender (e.g. "Rappel d'entretien")
    h = _hit(_rx(r"entretien|interview|rappel de rendez-vous|rendez-vous (confirme|fixe)"), sub)
    if h and not PROMO.search(sub):
        return _res("important", "etape", "Entretien / rendez-vous : a ne pas rater", f"« {h} » dans le sujet")

    # 3. clear ads
    h = _hit(PROMO, sub)
    if h and not (COLIS.search(sub) or FACTURE.search(sub) or SECURITE.search(sub)):
        return _res("pub", "pub", "Pub", f"« {h} » dans le sujet")

    # 4. practical things
    for rx, typ, label in ((SECURITE, "securite", "Securite / code de verification"), (FACTURE, "facture", "Facture / paiement"),
                           (COLIS, "colis", "Commande / colis"), (RDV, "rdv", "Rendez-vous / invitation")):
        h = _hit(rx, sub if bulk else subject_and_body[:600])
        if h:
            return _res("important", typ, label, f"« {h} »")
    if ADMIN_SENDER.search(frm) and not bulk:
        return _res("important", "admin", "Administratif / banque", "expediteur officiel")

    # 5. mass mailing that matched nothing above
    if bulk:
        return _res("pub", "pub", "Pub / newsletter", "mail envoye a beaucoup de gens (liste de diffusion)")
    if NOISE_SENDER.search(frm) or NOREPLY.search(frm):
        return _res("pub", "auto", "Message automatique", "expediteur automatique (no-reply, newsletter...)")

    # 6. looks like a real person writing
    return _res("important", "personne", "Message d'une personne", "pas une pub, pas un envoi automatique")
