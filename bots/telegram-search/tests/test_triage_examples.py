"""Sentences taken from real mails indexed on 2026-11-05, names changed: acknowledgements were counted as interviews, which made the job list and the daily digest wrong."""
import pytest

from instonct.mailtriage import classify


@pytest.mark.parametrize("subject,body", [
    ("Thank you for applying to Acme!", "Alex, congratulations on taking the first step. A member of our recruiting team will be in touch. In the meantime, we invite you to learn more about Acme."),
    ("Thanks for applying to Acme", "Your answers: please confirm your availability/notice period: immediate."),
    ("Thank you for applying to Acme", "We will reach out to discuss the next steps. In the meantime, we invite you to learn more about our hiring process."),
    ("Thank you for applying to Acme", "Details of any background checks will be set out in your offer letter. Interviews happen on Microsoft Teams."),
    ("We've received your application!", "Hello, congratulations on completing the first step."),
    ("Merci pour votre candidature", "Si votre profil correspond, nous vous proposerons un entretien. Vos disponibilites vous seront demandees plus tard."),
    ("We have received your application!", "Due to the very high volume of applications, we're unfortunately not able to provide individual feedback."),
    ("We have received your application!", "If you have not heard from us within three weeks, it most likely means we've decided to move forward with others."),
    ("Thank you for applying to Acme", "Check your spam folder, as unfortunately our emails for interview requests sometimes find their way there. If not, we won't be able to reach you."),
])
def test_a_plain_acknowledgement_is_not_an_interview_nor_a_refusal(subject, body):
    assert classify("Acme Hiring Team <no-reply@acme.com>", subject, body)["type"] == "candidature"


@pytest.mark.parametrize("subject,body,expected", [
    ("Alex - Acme has invited you to a video interview", "Thanks for your interest in Acme. We'd like to invite you to take a video interview.", "acceptation"),
    ("Thank you for applying to Acme | Next step: assessment", "Please complete the assessment using this link.", "etape"),
    ("Time confirmed: First interview Acme", "Your interview is booked.", "etape"),
    ("Thank you for your application!", "After careful consideration, we regret to inform you that we chose someone else.", "refus"),
    ("Update on your application to Acme", "Unfortunately, we will not be moving forward with your application.", "refus"),
    ("Your application at Acme", "We have decided to move forward with other candidates.", "refus"),
    ("Update on your application to Acme", "We have decided not to move forward with your application.", "refus"),
    ("Your application to Acme", "After review we have decided not to progress with your application.", "refus"),
    ("Your application to Acme", "We will move forward with another candidate. The position has now been filled.", "refus"),
    ("Thank you for your application", "Thank you for your interest. Unfortunately, this position is no longer available.", "refus"),
    ("Thank you for your application", "We received applications from many qualified candidates and unfortunately are going in a direction that better fits our needs.", "refus"),
    ("Merci pour votre interet", "Votre candidature n'est pas retenue pour ce poste.", "refus"),
    ("Votre candidature", "Votre dossier n'a pas ete retenu au regard des autres profils.", "refus"),
])
def test_real_news_stays_real_news(subject, body, expected):
    assert classify("Acme Team <talent@acme.com>", subject, body)["type"] == expected


def test_a_software_application_is_not_a_job_application():
    out = classify("Stripe <notifications@stripe.com>", "Problemes de livraison de webhooks", "Your application is failing. Schedule a call with the teams on zoom.us if needed.")
    assert out["type"] not in ("etape", "acceptation", "refus", "candidature")


def test_a_position_named_only_in_the_body_is_still_a_job_mail():
    body = "Hello, thank you for taking the time to apply for the Growth Associate position at Homa! Your application is now in our hands."
    assert classify("Workable <x@workablemail.com>", "Growth Associate - Gaming - Homa", body, False)["type"] == "candidature"


def test_a_refusal_sent_through_a_mailing_tool_still_counts():
    assert classify("Acme <jobs@acme.com>", "Your application to Acme", "We have decided not to move forward with your application.", bulk=True)["type"] == "refus"


def test_a_person_can_refuse_without_saying_application():
    assert classify("Pat Doe <pat@acme.io>", "Re: Acme / Alex presentation", "Thanks for the time. We have decided not to proceed with an offer.")["type"] == "refus"


def test_a_refusal_quoted_in_a_reply_is_not_a_refusal():
    body = "Thanks, see you Tuesday!\n\nOn Mon, Nov 2, 2026 at 3 PM Pat <pat@acme.com> wrote:\nWe regret to inform you that we chose someone else."
    assert classify("Pat <pat@acme.com>", "Re: Your application to Acme", body)["type"] != "refus"
