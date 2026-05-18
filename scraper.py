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
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                locale="fr-FR"
            )
            page = context.new_page()

            # Try to load the page
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(3)

            # Handle cookie consent if present
            try:
                consent_btn = page.locator('button:has-text("Tout accepter"), button:has-text("Accept all"), [data-cookiebanner="accept_button"]')
                if consent_btn.count() > 0:
                    consent_btn.first.click()
                    time.sleep(2)
            except Exception:
                pass

            # If login wall appears and credentials provided
            page_content = page.content()
            if "login" in page_content.lower() and fb_email and fb_password:
                log.info("Facebook login wall detected — logging in...")
                page.goto("https://www.facebook.com/login", wait_until="networkidle")
                page.fill("#email", fb_email)
                page.fill("#pass", fb_password)
                page.click("[name='login']")
                page.wait_for_load_state("networkidle")
                time.sleep(3)
                page.goto(url, wait_until="networkidle", timeout=30000)
                time.sleep(3)

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
