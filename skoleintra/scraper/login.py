"""Login flow for ForældreIntra.

Supports:
- ``uni``  — UNI-Login via ``login.emu.dk``
- ``alm``  — ordinary (username/password) login on the portal itself

Inspired by fskintra's ``surllib.skoleLogin()`` (Python 2 / mechanize).
Rewritten for Python 3 + requests + BeautifulSoup.
"""

import logging
import re

from bs4 import BeautifulSoup

from skoleintra.scraper.session import PortalSession

logger = logging.getLogger(__name__)

_MAX_REDIRECTS = 10
_LOGIN_START = "/Account/IdpLogin"


def _parse_form(html: str | bytes) -> tuple[str, dict[str, str]]:
    """Extract the first HTML form's action and hidden/text inputs.

    Returns ``(action_url, {name: value})``.
    """
    soup = BeautifulSoup(html, "lxml")
    form = soup.find("form")
    if form is None:
        return "", {}
    action = form.get("action", "")
    data: dict[str, str] = {}
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        data[name] = inp.get("value", "")
    return action, data


def _looks_like_failed_alm_login(html: str) -> bool:
    """Best-effort detector for ALM credential rejection pages.

    The portal returns HTTP 200 and renders the login form again on
    failed ALM login attempts, so status code alone is not useful.
    """
    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True).lower()
    markers = (
        "forkert",
        "ugyld",
        "fejl",
        "invalid",
        "incorrect",
        "brugernavn",
        "adgangskode",
        "password",
    )
    return any(marker in text for marker in markers)

def login(
    portal: PortalSession,
    username: str,
    password: str,
    login_type: str = "uni",
) -> BeautifulSoup:
    """Log in to ForældreIntra and return the parsed index page.

    Parameters
    ----------
    portal:
        An initialised :class:`PortalSession`.
    username, password:
        Portal credentials.
    login_type:
        ``'uni'`` (UNI-Login) or ``'alm'`` (ordinary login).

    Returns
    -------
    BeautifulSoup
        The parsed HTML of the post-login index page.

    Raises
    ------
    RuntimeError
        If login could not be completed within the redirect budget.
    """
    resp = portal.get(_LOGIN_START, allow_redirects=True)
    url = resp.url

    for step in range(_MAX_REDIRECTS):
        logger.debug("Login step %d: %s", step, url)
        html = resp.text

        # ----------------------------------------------------------------
        # Arrived at the portal index (logged-in landing page)
        # ----------------------------------------------------------------
        if re.search(r"/parent/\d+/[^/]+/Index", url):
            logger.info("Login successful at %s", url)
            portal.save_cookies()
            return BeautifulSoup(html, "lxml")

        # ----------------------------------------------------------------
        # Intermediate relay / SAML page (single hidden form, auto-submit)
        # ----------------------------------------------------------------
        soup = BeautifulSoup(html, "lxml")
        forms = soup.find_all("form")
        if len(forms) == 1:
            action, data = _parse_form(html)
            is_saml_relay = (
                bool(re.search(r"ssocomplete|relay", html, re.IGNORECASE))
                or "ssocomplete" in url.lower()
                or "assertionconsumerservice" in action.lower()
                or "samlresponse" in {k.lower() for k in data.keys()}
            )
            if action and is_saml_relay:
                abs_action = _abs(portal, action)
                logger.debug("Relaying SAML form to %s", abs_action)
                resp = portal.post(abs_action, data=data, allow_redirects=True)
                url = resp.url
                continue

        # ----------------------------------------------------------------
        # Contact confirmation page
        # ----------------------------------------------------------------
        if url.endswith("/ConfirmContacts"):
            logger.info("Confirming contact details at %s", url)
            for form in forms:
                if "/Confirm" in (form.get("action") or ""):
                    action = form.get("action", "")
                    data = {
                        inp.get("name"): inp.get("value", "")
                        for inp in form.find_all("input")
                        if inp.get("name")
                    }
                    resp = portal.post(
                        _abs(portal, action), data=data, allow_redirects=True
                    )
                    url = resp.url
                    break
            else:
                raise RuntimeError(
                    f"Could not find confirmation form at {url}"
                )
            continue

        # ----------------------------------------------------------------
        # UNI-Login page (login.emu.dk)
        # ----------------------------------------------------------------
        if "login.emu.dk" in url:
            if login_type == "alm":
                raise RuntimeError(
                    "Reached UNI-Login page but login_type is 'alm'. "
                    "Set SKOLEINTRA_LOGIN_TYPE=uni or check your credentials."
                )
            logger.debug("Filling UNI-Login form for %s", username)
            pwd_form = soup.find("form", {"id": "pwd"}) or (forms[0] if forms else None)
            if pwd_form is None:
                raise RuntimeError(
                    f"Could not find UNI-Login password form at {url}. "
                    "The portal may require JavaScript. "
                    "See https://svalgaard.github.io/fskintra/troubleshooting"
                )
            action = pwd_form.get("action", url)
            data = {
                inp.get("name"): inp.get("value", "")
                for inp in pwd_form.find_all("input")
                if inp.get("name")
            }
            data["user"] = username
            data["pass"] = password
            resp = portal.post(_abs(portal, action), data=data, allow_redirects=True)
            url = resp.url
            continue

        # ----------------------------------------------------------------
        # Portal login page (/Account/IdpLogin) — alm or uni chooser
        # ----------------------------------------------------------------
        if "/Account/IdpLogin" in url:
            if login_type == "uni":
                uni_links = soup.find_all(
                    "a", href=re.compile(r"RedirectToUniLogin", re.IGNORECASE)
                )
                if not uni_links:
                    raise RuntimeError(
                        "Could not find UNI-Login link on login page. "
                        "Check SKOLEINTRA_HOSTNAME is correct."
                    )
                logger.debug("Following UNI-Login redirect link")
                resp = portal.get(
                    _abs(portal, uni_links[0]["href"]), allow_redirects=True
                )
                url = resp.url
            else:
                logger.debug("Filling ALM login form for %s", username)
                action, data = _parse_form(html)
                if not action:
                    # Some failed login pages render a form without action.
                    # Reuse current URL to avoid posting to portal root (/).
                    action = url
                data["UserName"] = username
                data["Password"] = password
                resp = portal.post(
                    _abs(portal, action), data=data, allow_redirects=True
                )
                url = resp.url

                # ALM failure often returns HTTP 200 on the same login page.
                # Reposting the same credentials in a loop does not help.
                if "/Account/IdpLogin" in url and _looks_like_failed_alm_login(
                    resp.text
                ):
                    raise RuntimeError(
                        "ALM login was rejected (portal returned IdpLogin again). "
                        "Verify SKOLEINTRA_USERNAME/SKOLEINTRA_PASSWORD or try "
                        "SKOLEINTRA_LOGIN_TYPE=uni."
                    )
            continue

        # ----------------------------------------------------------------
        # Unknown page — abort
        # ----------------------------------------------------------------
        raise RuntimeError(
            f"Login stalled at unexpected URL after {step} steps: {url}"
        )

    raise RuntimeError(
        f"Login did not complete within {_MAX_REDIRECTS} redirect steps. "
        f"Last URL: {url}"
    )


def _abs(portal: PortalSession, url: str) -> str:
    """Make *url* absolute using the portal hostname if needed."""
    return portal.abs_url(url)
