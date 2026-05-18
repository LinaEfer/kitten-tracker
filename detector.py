"""
detector.py — Compares page snapshots and detects keyword matches.
Saves/loads snapshots as JSON files.
"""

import json
import logging
from pathlib import Path
from datetime import datetime

log = logging.getLogger(__name__)

SNAPSHOT_VERSION = 1


def get_snapshot_path(snapshots_dir: str, target_name: str) -> Path:
    safe_name = "".join(c if c.isalnum() else "_" for c in target_name)
    return Path(snapshots_dir) / f"{safe_name}.json"


def load_snapshot(snapshots_dir: str, target_name: str):
    path = get_snapshot_path(snapshots_dir, target_name)
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Could not load snapshot for {target_name}: {e}")
        return None


def save_snapshot(snapshots_dir: str, target_name: str, result: dict):
    Path(snapshots_dir).mkdir(parents=True, exist_ok=True)
    path = get_snapshot_path(snapshots_dir, target_name)
    snapshot = {
        "version": SNAPSHOT_VERSION,
        "target_name": target_name,
        "hash": result["hash"],
        "text": result["text"],
        "saved_at": datetime.utcnow().isoformat()
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    log.info(f"Snapshot saved for {target_name}")


def find_matching_lines(text: str, keywords: dict):
    """
    Scan text for lines that contain a relevant keyword combo.
    Returns list of matches with context.
    """
    lines = text.split("\n")
    matches = []

    breed_words = keywords.get("breed_siberian", []) + keywords.get("breed_maine_coon", [])
    sex_words = keywords.get("sex", [])
    availability_words = keywords.get("availability", [])
    color_words = keywords.get("color", [])

    # Build a sliding window of 5 lines for context matching
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        if not line_lower:
            continue

        # Check context window (current line ± 2)
        window_start = max(0, i - 2)
        window_end = min(len(lines), i + 3)
        window = " ".join(lines[window_start:window_end]).lower()

        has_breed = any(w in window for w in breed_words)
        has_sex = any(w in window for w in sex_words)
        has_avail = any(w in window for w in availability_words)
        has_color = any(w in window for w in color_words)

        # Match: breed + (sex or availability)
        if has_breed and (has_sex or has_avail or has_color):
            context = "\n".join(lines[window_start:window_end]).strip()
            matched_keywords = []
            for w in breed_words:
                if w in window:
                    matched_keywords.append(w)
            for w in sex_words:
                if w in window:
                    matched_keywords.append(w)
            for w in availability_words:
                if w in window:
                    matched_keywords.append(w)
            for w in color_words:
                if w in window:
                    matched_keywords.append(w)

            matches.append({
                "line_index": i,
                "context": context,
                "matched_keywords": list(set(matched_keywords))
            })

    # Deduplicate overlapping windows
    deduped = []
    last_index = -10
    for m in matches:
        if m["line_index"] - last_index > 3:
            deduped.append(m)
            last_index = m["line_index"]

    return deduped


def detect_changes(target_name: str, new_result: dict, config: dict) -> dict:
    """
    Compare new fetch result against stored snapshot.
    Returns a detection report.
    """
    snapshots_dir = config.get("snapshots_dir", "snapshots")
    keywords = config.get("keywords", {})

    old_snapshot = load_snapshot(snapshots_dir, target_name)

    report = {
        "target_name": target_name,
        "url": new_result.get("url"),
        "checked_at": datetime.utcnow().isoformat(),
        "is_first_run": old_snapshot is None,
        "content_changed": False,
        "keyword_matches": [],
        "new_keyword_matches": [],
        "should_notify": False
    }

    if not new_result.get("success"):
        report["error"] = new_result.get("error", "Unknown error")
        return report

    # Detect content change
    new_hash = new_result["hash"]
    old_hash = old_snapshot["hash"] if old_snapshot else None
    report["content_changed"] = (new_hash != old_hash)

    # Find keyword matches in new content
    report["keyword_matches"] = find_matching_lines(new_result["text"], keywords)

    # Find NEW matches (not present in old snapshot)
    if old_snapshot and report["keyword_matches"]:
        old_matches = find_matching_lines(old_snapshot.get("text", ""), keywords)
        old_contexts = {m["context"] for m in old_matches}
        report["new_keyword_matches"] = [
            m for m in report["keyword_matches"]
            if m["context"] not in old_contexts
        ]
    else:
        # First run: all matches are "new"
        report["new_keyword_matches"] = report["keyword_matches"]

    # Notify if there are new keyword matches (not just any content change)
    report["should_notify"] = len(report["new_keyword_matches"]) > 0

    # Save new snapshot
    save_snapshot(snapshots_dir, target_name, new_result)

    log.info(
        f"[{target_name}] changed={report['content_changed']} "
        f"matches={len(report['keyword_matches'])} "
        f"new_matches={len(report['new_keyword_matches'])}"
    )

    return report
