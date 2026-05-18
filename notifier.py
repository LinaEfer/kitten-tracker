"""
notifier.py — Sends email and/or push notifications when a match is detected.

Email: Gmail SMTP (needs App Password, not your real password)
Push:  Pushover (paid, ~$5 one-time) OR ntfy.sh (free, open source)
"""

import smtplib
import logging
import urllib.request
import urllib.parse
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

log = logging.getLogger(__name__)


def _build_email_html(report: dict) -> str:
    target = report["target_name"]
    url = report["url"]
    checked_at = report["checked_at"]
    matches = report["new_keyword_matches"]

    matches_html = ""
    for m in matches:
        kw = ", ".join(f"<code>{k}</code>" for k in m["matched_keywords"])
        context = m["context"].replace("\n", "<br>")
        matches_html += f"""
        <div style="background:#fff8e1;border-left:4px solid #ffc107;padding:12px;margin:12px 0;border-radius:4px;">
            <p style="margin:0 0 6px;font-size:13px;color:#888;">Keywords found: {kw}</p>
            <p style="margin:0;font-size:15px;color:#333;">{context}</p>
        </div>
        """

    return f"""
    <html><body style="font-family:Georgia,serif;max-width:600px;margin:0 auto;padding:20px;color:#222;">
        <div style="background:#1a1a2e;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
            <h1 style="margin:0;font-size:22px;">🐱 Kitten Alert!</h1>
            <p style="margin:6px 0 0;opacity:0.7;font-size:14px;">A potential match was found</p>
        </div>
        <div style="border:1px solid #e0e0e0;border-top:none;padding:20px 24px;border-radius:0 0 8px 8px;">
            <p><strong>Source:</strong> {target}</p>
            <p><strong>URL:</strong> <a href="{url}">{url}</a></p>
            <p><strong>Detected at:</strong> {checked_at} UTC</p>
            <h3 style="margin-top:20px;">Matching content found:</h3>
            {matches_html}
            <hr style="border:none;border-top:1px solid #eee;margin:20px 0;">
            <p style="color:#888;font-size:13px;">
                ⚡ Act quickly — kittens get reserved fast!<br>
                Looking for: <strong>Siberian Neva Masquerade male</strong> or <strong>Maine Coon black smoke male</strong>
            </p>
            <a href="{url}" style="display:inline-block;background:#1a1a2e;color:#fff;padding:12px 24px;border-radius:6px;text-decoration:none;margin-top:8px;font-size:15px;">
                View page now →
            </a>
        </div>
    </body></html>
    """


def send_email(report: dict, email_config: dict) -> bool:
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🐱 Kitten Alert: Match found on {report['target_name']}"
        msg["From"] = email_config["sender_email"]
        msg["To"] = email_config["recipient_email"]

        text_body = (
            f"KITTEN ALERT!\n\n"
            f"Source: {report['target_name']}\n"
            f"URL: {report['url']}\n"
            f"Detected at: {report['checked_at']} UTC\n\n"
            f"Matching content:\n"
        )
        for m in report["new_keyword_matches"]:
            text_body += f"\n--- Keywords: {', '.join(m['matched_keywords'])} ---\n{m['context']}\n"

        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(_build_email_html(report), "html"))

        with smtplib.SMTP(email_config["smtp_host"], email_config["smtp_port"]) as server:
            server.ehlo()
            server.starttls()
            server.login(email_config["sender_email"], email_config["sender_password"])
            server.sendmail(
                email_config["sender_email"],
                email_config["recipient_email"],
                msg.as_string()
            )

        log.info(f"Email sent to {email_config['recipient_email']}")
        return True

    except Exception as e:
        log.error(f"Failed to send email: {e}")
        return False


def send_pushover(report: dict, pushover_config: dict) -> bool:
    """Send push notification via Pushover (https://pushover.net)."""
    try:
        matches_text = "; ".join(
            m["context"][:100] for m in report["new_keyword_matches"]
        )
        message = (
            f"Match on {report['target_name']}!\n"
            f"{matches_text}\n"
            f"Keywords: {', '.join(report['new_keyword_matches'][0]['matched_keywords']) if report['new_keyword_matches'] else ''}"
        )

        data = urllib.parse.urlencode({
            "token": pushover_config["api_token"],
            "user": pushover_config["user_key"],
            "title": "🐱 Kitten Alert!",
            "message": message[:512],
            "url": report["url"],
            "url_title": "View page",
            "priority": 1,  # high priority
            "sound": "magic"
        }).encode()

        req = urllib.request.Request(
            "https://api.pushover.net/1/messages.json",
            data=data
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if result.get("status") == 1:
                log.info("Pushover notification sent")
                return True
            else:
                log.error(f"Pushover error: {result}")
                return False

    except Exception as e:
        log.error(f"Failed to send Pushover notification: {e}")
        return False


def send_ntfy(report: dict, ntfy_config: dict) -> bool:
    """Send push notification via ntfy.sh (free, no account needed)."""
    try:
        matches_text = "; ".join(
            m["context"][:200] for m in report["new_keyword_matches"]
        )
        message = (
            f"Match on {report['target_name']}!\n"
            f"{matches_text}"
        )[:500]

        server = ntfy_config.get("server", "https://ntfy.sh")
        topic = ntfy_config["topic"]
        url = f"{server}/{topic}"

        data = message.encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                # HTTP headers must be latin-1; keep emoji out of header values
                "Title": "Kitten Alert!",
                "Priority": "urgent",
                "Tags": "cat,sparkles",
                "Click": report["url"],
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info(f"ntfy notification sent to topic: {topic}")
            return True

    except Exception as e:
        log.error(f"Failed to send ntfy notification: {e}")
        return False


def notify(report: dict, config: dict):
    """Send all enabled notifications."""
    notif_config = config.get("notifications", {})

    email_cfg = notif_config.get("email", {})
    if email_cfg.get("enabled"):
        send_email(report, email_cfg)

    pushover_cfg = notif_config.get("pushover", {})
    if pushover_cfg.get("enabled"):
        send_pushover(report, pushover_cfg)

    ntfy_cfg = notif_config.get("ntfy", {})
    if ntfy_cfg.get("enabled"):
        send_ntfy(report, ntfy_cfg)
