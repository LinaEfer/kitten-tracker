"""
main.py — Orchestrates the kitten tracker.

Usage:
    python main.py              # Run all targets once
    python main.py --loop       # Run continuously (respects check_interval_minutes)
    python main.py --test-notify  # Send a test notification
"""

import time
import logging
import argparse
from datetime import datetime, timedelta

from config_loader import load_config
from scraper import fetch_target
from detector import detect_changes
from notifier import notify

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("tracker.log", encoding="utf-8")
    ]
)
log = logging.getLogger(__name__)


def run_check(target: dict, config: dict):
    name = target["name"]
    log.info(f"=== Checking: {name} ===")

    result = fetch_target(target, config)

    if not result.get("success"):
        log.error(f"Fetch failed for {name}: {result.get('error')}")
        return

    report = detect_changes(name, result, config)

    if report.get("is_first_run"):
        log.info(f"[{name}] First run — snapshot saved. No notification sent.")
        # Still log if there are matches on first run
        if report["keyword_matches"]:
            log.info(f"[{name}] Found {len(report['keyword_matches'])} potential matches already on page (not notifying for existing content)")

    elif report["should_notify"]:
        log.info(f"[{name}] 🐱 NEW MATCH FOUND! Sending notifications...")
        notify(report, config)

    elif report["content_changed"]:
        log.info(f"[{name}] Content changed but no keyword matches.")

    else:
        log.info(f"[{name}] No changes detected.")


def run_once(config: dict):
    for target in config["targets"]:
        try:
            run_check(target, config)
        except Exception as e:
            log.error(f"Unexpected error checking {target['name']}: {e}", exc_info=True)


def run_loop(config: dict):
    """
    Continuously monitor targets, respecting each target's check_interval_minutes.
    """
    log.info("Starting continuous monitoring loop...")

    # Track when each target was last checked
    last_checked = {}

    while True:
        config = load_config()  # Reload config on each cycle (allows hot-updating)
        now = datetime.utcnow()

        for target in config["targets"]:
            name = target["name"]
            interval_min = target.get("check_interval_minutes", 60)
            last = last_checked.get(name)

            if last is None or (now - last) >= timedelta(minutes=interval_min):
                try:
                    run_check(target, config)
                    last_checked[name] = now
                except Exception as e:
                    log.error(f"Unexpected error checking {name}: {e}", exc_info=True)

        # Sleep 60 seconds before checking again if it's time
        log.info("Sleeping 60 seconds before next cycle check...")
        time.sleep(60)


def send_test_notification(config: dict):
    """Send a test notification to verify your setup."""
    log.info("Sending test notification...")
    test_report = {
        "target_name": "TEST — Opale Sibérienne",
        "url": "http://opalesiberienne.fr/",
        "checked_at": datetime.utcnow().isoformat(),
        "is_first_run": False,
        "content_changed": True,
        "keyword_matches": [
            {
                "line_index": 1,
                "context": "🐱 TEST: Chaton Neva Masquerade mâle disponible — portée de janvier",
                "matched_keywords": ["neva masquerade", "mâle", "disponible"]
            }
        ],
        "new_keyword_matches": [
            {
                "line_index": 1,
                "context": "🐱 TEST: Chaton Neva Masquerade mâle disponible — portée de janvier",
                "matched_keywords": ["neva masquerade", "mâle", "disponible"]
            }
        ],
        "should_notify": True
    }
    notify(test_report, config)
    log.info("Test notification sent!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kitten Availability Tracker")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--test-notify", action="store_true", help="Send test notification")
    args = parser.parse_args()

    config = load_config()

    if args.test_notify:
        send_test_notification(config)
    elif args.loop:
        run_loop(config)
    else:
        run_once(config)
