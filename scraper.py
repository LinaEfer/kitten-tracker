"""
scraper.py — Fetches content from target URLs.
Uses requests+BeautifulSoup for normal websites,
Playwright (headless browser) for Facebook.
"""

import hashlib
import logging
import time
from contextlib import contextmanager
from datetime import datetime

from bs4 import BeautifulSoup
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

FACEBOOK_LOGIN_URL = "https://www.facebook.com/login"
PLACEHOLDER_CREDENTIALS = {
    "YOUR_FACEBOOK_EMAIL",
    "YOUR_FACEBOOK_PASSWORD",
}


def _facebook_credentials_configured(fb_email: str | None, fb_password: str | None) -> bool:
    return bool(
        fb_email
        and fb_password
        and fb_email not in PLACEHOLDER_CREDENTIALS
        and fb_password not in PLACEHOLDER_CREDENTIALS
    )


def _facebook_session_active(context) -> bool:
    return any(cookie.get("name") == "c_user" for cookie in context.cookies())


def _dismiss_facebook_consent(page) -> None:
    """Dismiss cookie/consent dialogs when present."""
    selectors = [
        'button:has-text("Tout accepter")',
        'button:has-text("Accept all")',
        'button:has-text("Autoriser tous les cookies")',
        'button:has-text("Allow all cookies")',
        '[data-cookiebanner="accept_button"]',
        '[aria-label="Autoriser tous les cookies"]',
        '[aria-label="Allow all cookies"]',
    ]
    for selector in selectors:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=1500):
                button.click()
                time.sleep(1.5)
                return
        except Exception:
            continue


def _facebook_checkpoint_page(page) -> bool:
    url = page.url.lower()
    if "checkpoint" in url or "two_step_verification" in url or "two_factor" in url:
        return True

    content = page.content().lower()
    checkpoint_markers = (
        "check your notifications",
        "approve this login",
        "confirmer que c'est vous",
        "vérifiez vos notifications",
        "approbation de la connexion",
        "review recent login",
    )
    return any(marker in content for marker in checkpoint_markers)


def _facebook_login_page(page) -> bool:
    url = page.url.lower()
    return "/login" in url or url.rstrip("/").endswith("facebook.com")


def _facebook_login_form_visible(page) -> bool:
    """True when email and password fields are both visible on the page."""
    try:
        email = page.locator('input[name="email"]').first
        passwd = page.locator('input[name="pass"]').first
        return email.is_visible(timeout=1500) and passwd.is_visible(timeout=1500)
    except Exception:
        return False


def _facebook_access_blocked(page, session_active: bool) -> bool:
    """
    Return True only when the page is genuinely inaccessible.

    Public Facebook pages often include a login widget in the sidebar; those
    should not be treated as a hard block when we already have a session cookie
    or the page has substantial profile content.
    """
    if _facebook_checkpoint_page(page):
        return True

    if session_active:
        return False

    if _facebook_login_page(page) and _facebook_login_form_visible(page):
        return True

    if not _facebook_login_form_visible(page):
        return False

    try:
        body_text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        body_text = ""

    # Short pages with a login form are login walls, not public profiles.
    if len(body_text.strip()) < 400:
        return True

    lowered = body_text.lower()
    profile_markers = (
        "publications",
        "posts",
        "photos",
        "photos et vidéos",
        "à propos",
        "about",
        "followers",
        "abonnés",
    )
    return not any(marker in lowered for marker in profile_markers)


def _fill_facebook_login_fields(page, fb_email: str, fb_password: str) -> None:
    """Fill email/password using several selector and label fallbacks."""
    email_selectors = [
        'input[name="email"]',
        "#email",
        'input[type="email"]',
        'input[autocomplete="username"]',
    ]
    password_selectors = [
        'input[name="pass"]',
        "#pass",
        'input[type="password"]',
        'input[autocomplete="current-password"]',
    ]

    email_field = None
    for selector in email_selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=5000)
            email_field = locator
            break
        except Exception:
            continue

    if email_field is None:
        for label in ("Adresse e-mail", "Email", "E-mail", "Mobile number"):
            try:
                locator = page.get_by_label(label, exact=False).first
                locator.wait_for(state="visible", timeout=3000)
                email_field = locator
                break
            except Exception:
                continue

    if email_field is None:
        raise RuntimeError("Could not find Facebook email field on login page")

    password_field = None
    for selector in password_selectors:
        locator = page.locator(selector).first
        try:
            locator.wait_for(state="visible", timeout=5000)
            password_field = locator
            break
        except Exception:
            continue

    if password_field is None:
        for label in ("Mot de passe", "Password"):
            try:
                locator = page.get_by_label(label, exact=False).first
                locator.wait_for(state="visible", timeout=3000)
                password_field = locator
                break
            except Exception:
                continue

    if password_field is None:
        raise RuntimeError("Could not find Facebook password field on login page")

    email_field.fill(fb_email)
    password_field.fill(fb_password)


def _submit_facebook_login(page) -> None:
    """Submit the login form."""
    submit_selectors = [
        '[data-testid="royal_login_button"]',
        'button[name="login"]',
        'input[name="login"]',
        'input[type="submit"]',
        'button[type="submit"]',
        'div[role="button"]:has-text("Se connecter")',
        'div[role="button"]:has-text("Log in")',
        'button:has-text("Se connecter")',
        'button:has-text("Log in")',
        'button:has-text("Log In")',
        "[name='login']",
    ]
    for selector in submit_selectors:
        try:
            button = page.locator(selector).first
            if button.is_visible(timeout=2000):
                button.click()
                return
        except Exception:
            continue
    raise RuntimeError("Could not find Facebook login submit button")


def _facebook_login(page, fb_email: str, fb_password: str) -> None:
    log.info("Logging into Facebook...")
    page.goto(FACEBOOK_LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
    time.sleep(2)
    _dismiss_facebook_consent(page)
    _fill_facebook_login_fields(page, fb_email, fb_password)
    _submit_facebook_login(page)
    page.wait_for_load_state("domcontentloaded", timeout=45000)
    time.sleep(3)
    _dismiss_facebook_consent(page)

    if _facebook_checkpoint_page(page):
        raise RuntimeError(
            "Facebook security checkpoint — approve the login in the Facebook app, "
            "or run the tracker locally once to establish a session"
        )

    if not _facebook_session_active(page.context) and _facebook_login_form_visible(page):
        raise RuntimeError("Facebook login did not complete — still on login page")

    if _facebook_session_active(page.context):
        log.info("Facebook session established")
    else:
        log.warning("Facebook login finished without session cookie — continuing anyway")


def _html_to_result(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    text_lower = text.lower()
    content_hash = hashlib.sha256(text_lower.encode()).hexdigest()

    return {
        "success": True,
        "url": url,
        "text": text,
        "text_lower": text_lower,
        "hash": content_hash,
        "fetched_at": datetime.utcnow().isoformat(),
        "method": "playwright",
    }


def _scroll_facebook_page(page) -> None:
    for _ in range(3):
        page.keyboard.press("End")
        time.sleep(1.5)


def fetch_website(url: str) -> dict:
    """Fetch a standard website and return text + hash."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "meta", "link", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        text_lower = text.lower()
        content_hash = hashlib.sha256(text_lower.encode()).hexdigest()

        return {
            "success": True,
            "url": url,
            "text": text,
            "text_lower": text_lower,
            "hash": content_hash,
            "fetched_at": datetime.utcnow().isoformat(),
            "method": "requests",
        }

    except Exception as e:
        log.error(f"Failed to fetch {url}: {e}")
        return {"success": False, "url": url, "error": str(e)}


def _launch_facebook_browser():
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=True,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="fr-FR",
        viewport={"width": 1280, "height": 720},
    )
    page = context.new_page()
    return playwright, browser, page


@contextmanager
def facebook_browser(fb_email: str | None = None, fb_password: str | None = None):
    """Reuse one browser session for multiple Facebook targets."""
    try:
        playwright, browser, page = _launch_facebook_browser()
    except ImportError:
        log.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        yield None
        return

    try:
        if _facebook_credentials_configured(fb_email, fb_password):
            try:
                _facebook_login(page, fb_email, fb_password)
            except Exception as e:
                log.error(f"Facebook login failed: {e}")
        yield page
    finally:
        browser.close()
        playwright.stop()


def fetch_facebook_on_page(
    page,
    url: str,
    fb_email: str | None = None,
    fb_password: str | None = None,
) -> dict:
    """Fetch a Facebook page using an existing Playwright page."""
    if page is None:
        return {"success": False, "url": url, "error": "Playwright not installed"}

    has_credentials = _facebook_credentials_configured(fb_email, fb_password)

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        time.sleep(3)
        _dismiss_facebook_consent(page)

        session_active = _facebook_session_active(page.context)
        if _facebook_access_blocked(page, session_active):
            if has_credentials and not session_active:
                log.info("Facebook page blocked — retrying after login...")
                try:
                    _facebook_login(page, fb_email, fb_password)
                except Exception as e:
                    return {"success": False, "url": url, "error": f"Facebook login failed: {e}"}

                page.goto(url, wait_until="domcontentloaded", timeout=45000)
                time.sleep(3)
                _dismiss_facebook_consent(page)
                session_active = _facebook_session_active(page.context)

            if _facebook_access_blocked(page, session_active):
                if _facebook_checkpoint_page(page):
                    error = (
                        "Facebook security checkpoint — approve the login in the Facebook app "
                        "or run the tracker locally"
                    )
                elif has_credentials:
                    error = "Facebook profile is still blocked after sign-in"
                else:
                    error = "Facebook login required — set FACEBOOK_EMAIL and FACEBOOK_PASSWORD"
                return {"success": False, "url": url, "error": error}

        _scroll_facebook_page(page)
        return _html_to_result(url, page.content())

    except Exception as e:
        log.error(f"Failed to fetch Facebook page {url}: {e}")
        return {"success": False, "url": url, "error": str(e)}


def fetch_facebook(url: str, fb_email: str = None, fb_password: str = None) -> dict:
    """Fetch a single Facebook profile page."""
    with facebook_browser(fb_email, fb_password) as page:
        return fetch_facebook_on_page(page, url, fb_email, fb_password)


def fetch_target(target: dict, config: dict) -> dict:
    """Dispatch to the right fetcher based on target type."""
    t = target.get("type", "website")
    if t == "facebook":
        return fetch_facebook(
            target["url"],
            fb_email=config.get("facebook_email"),
            fb_password=config.get("facebook_password"),
        )
    return fetch_website(target["url"])
