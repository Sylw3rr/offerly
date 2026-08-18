"""Matching a reply to an application.

The failure worth guarding against is the confident wrong answer: moving the
wrong application to "rejected" edits someone's record of their own job search.
"""

from app.ingest import matching


def application(app_id, company, domain=None):
    return {
        "id": app_id,
        "status": "submitted",
        "offers": {"title": "Rola", "companies": {"name": company, "email_domain": domain}},
    }


def test_a_companys_own_domain_settles_it():
    apps = [application("a1", "Acme", "acme.pl"), application("a2", "Zeta", "zeta.pl")]
    match = matching.find(apps, "acme.pl", "Twoja aplikacja", "")
    assert match.application_id == "a1"
    assert match.how == "domain"
    assert match.sure


def test_a_recruiters_subdomain_still_points_at_the_company():
    apps = [application("a1", "Acme", "acme.pl")]
    match = matching.find(apps, "kariera.acme.pl", "", "")
    assert match.application_id == "a1"


def test_a_gmail_address_identifies_nobody():
    """Recruiters write from personal addresses; the domain says nothing then."""
    apps = [application("a1", "Acme", "acme.pl")]
    assert matching.find(apps, "gmail.com", "Dzień dobry", "") is None


def test_two_applications_to_one_company_are_left_for_a_person_to_split():
    apps = [application("a1", "Acme", "acme.pl"), application("a2", "Acme", "acme.pl")]
    assert matching.find(apps, "acme.pl", "Twoja aplikacja", "") is None


def test_the_company_name_in_the_subject_is_a_suggestion_not_a_verdict():
    apps = [application("a1", "Nordlys Systemy"), application("a2", "Zeta")]
    match = matching.find(apps, "gmail.com", "Rekrutacja Nordlys Systemy", "")
    assert match.application_id == "a1"
    assert match.how == "name"
    assert not match.sure  # never enough to move a status on its own


def test_a_name_matched_in_the_body_counts_too():
    apps = [application("a1", "Kwadrat Software")]
    match = matching.find(apps, "gmail.com", "Dzień dobry", "Piszę w sprawie Kwadrat Software.")
    assert match.application_id == "a1"


def test_two_companies_matching_the_same_text_match_neither():
    apps = [application("a1", "Acme Polska"), application("a2", "Acme Polska")]
    assert matching.find(apps, "gmail.com", "Acme Polska", "") is None


def test_legal_boilerplate_in_a_name_cannot_carry_a_match():
    """Otherwise every "Sp. z o.o." in a message would match every company."""
    apps = [application("a1", "Kruszywo Sp. z o.o."), application("a2", "Reduta Sp. z o.o.")]
    assert matching.find(apps, "gmail.com", "Sp. z o.o.", "") is None


def test_accents_do_not_stop_a_name_from_matching():
    apps = [application("a1", "Świt Automatyzacje")]
    match = matching.find(apps, "gmail.com", "Rekrutacja Swit Automatyzacje", "")
    assert match is not None


def test_nothing_recognisable_matches_nothing():
    apps = [application("a1", "Acme", "acme.pl")]
    assert matching.find(apps, "randomcorp.com", "Newsletter", "Promocje") is None


def test_an_empty_register_matches_nothing():
    assert matching.find([], "acme.pl", "Twoja aplikacja", "") is None
