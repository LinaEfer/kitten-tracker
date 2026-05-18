"""
scraper.py — Fetches content from target URLs.
Uses requests+BeautifulSoup for normal websites,
Playwright (headless browser) for Facebook.
"""

import json
import time
import hashlib
import logging
from datetime import datetime
from pathlib import Path
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


def _facebook_login_form_visible(page) -> bool:
    """Return True when the page is showing Facebook's login form."""
    selectors = [
        'input[name="email"]',
        'input[name="pass"]',
        "#email",
        "#pass",
        'input[type="email"]',
    ]
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible(timeout=1000):
                return True
        except Exception:
            continue

    content = page.content().lower()
    login_markers = (
        "se connecter à facebook",
        "log into facebook",
        "connectez-vous à facebook",
        "email or mobile number",
        "adresse e-mail ou numéro",
        "adresse e-mail ou numero",
    )
    return any(marker in content for marker in login_markers)


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
        'button[name="login"]',
        'button[type="submit"]',
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

    if _facebook_login_form_visible(page):
        raise RuntimeError("Facebook login did not complete — still on login page")


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

        # Remove script/style noise
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
            "method": "requests"
        }

    except Exception as e:
        log.error(f"Failed to fetch {url}: {e}")
        return {"success": False, "url": url, "error": str(e)}


def fetch_facebook(url: str, fb_email: str = None, fb_password: str = None) -> dict:
    """
    Fetch a Facebook profile page using Playwright.
    Tries without login first (public profile).
    Falls back to login if credentials are provided.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return {"success": False, "url": url, "error": "Playwright not installed"}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
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
            has_credentials = _facebook_credentials_configured(fb_email, fb_password)

            if has_credentials:
                try:
                    _facebook_login(page, fb_email, fb_password)
                except Exception as e:
                    browser.close()
                    log.error(f"Facebook login failed: {e}")
                    return {"success": False, "url": url, "error": f"Facebook login failed: {e}"}

            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            time.sleep(3)
            _dismiss_facebook_consent(page)

            if _facebook_login_form_visible(page):
                if has_credentials:
                    browser.close()
                    return {
                        "success": False,
                        "url": url,
                        "error": "Facebook profile requires login but access was denied after sign-in",
                    }
                log.warning(
                    "Facebook login wall detected for %s — configure facebook_email/facebook_password in config.json",
                    url,
                )

            # Scroll to load more content
            for _ in range(3):
                page.keyboard.press("End")
                time.sleep(1.5)

            html = page.content()
            browser.close()

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
            "method": "playwright"
        }

    except Exception as e:
        log.error(f"Failed to fetch Facebook page {url}: {e}")
        return {"success": False, "url": url, "error": str(e)}


def fetch_target(target: dict, config: dict) -> dict:
    """Dispatch to the right fetcher based on target type."""
    t = target.get("type", "website")
    if t == "facebook":
        return fetch_facebook(
            target["url"],
            fb_email=config.get("facebook_email"),
            fb_password=config.get("facebook_password")
        )
    else:
        return fetch_website(target["url"])
