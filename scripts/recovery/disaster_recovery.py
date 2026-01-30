#!/usr/bin/env python3
"""
Disaster recovery utilities: backups, exports, and recovery notes.
"""
import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        content = path.read_text().strip()
        return json.loads(content) if content else default
    except Exception:
        return default


def _copy_target(target: Path, dest: Path) -> None:
    if target.is_dir():
        dest.mkdir(parents=True, exist_ok=True)
        for item in target.rglob("*"):
            if item.is_file():
                rel = item.relative_to(target)
                out = dest / rel
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(item.read_bytes())
    elif target.is_file():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(target.read_bytes())


def create_backup(config: Dict) -> Path:
    root = Path(config.get("backup_root", "backups"))
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / f"backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    for target in config.get("backup_targets", []):
        src = Path(target)
        if not src.exists():
            continue
        dest = backup_dir / src
        _copy_target(src, dest)

    meta = {
        "created_at": datetime.now().isoformat(),
        "targets": config.get("backup_targets", []),
    }
    (backup_dir / "backup_manifest.json").write_text(json.dumps(meta, indent=2))
    return backup_dir


def export_posts(config: Dict) -> Dict[str, str]:
    exports = config.get("exports", {})
    schedule_path = Path("scripts/content_scheduling/schedule/post_schedule.json")
    schedule = _load_json(schedule_path, [])
    export_json = Path(exports.get("post_export_json", "exports/posts.json"))
    export_csv = Path(exports.get("post_export_csv", "exports/posts.csv"))
    export_rss = Path(exports.get("post_export_rss", "exports/posts.xml"))
    export_md_dir = Path(exports.get("post_export_markdown_dir", "exports/markdown"))
    export_json.parent.mkdir(parents=True, exist_ok=True)
    export_csv.parent.mkdir(parents=True, exist_ok=True)
    export_rss.parent.mkdir(parents=True, exist_ok=True)
    export_md_dir.mkdir(parents=True, exist_ok=True)

    export_json.write_text(json.dumps(schedule, indent=2))

    fields = [
        "id",
        "subreddit",
        "title",
        "type",
        "status",
        "created_at",
        "scheduled_for",
        "posted_at",
        "post_url",
        "error",
    ]
    with export_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for post in schedule:
            writer.writerow({k: post.get(k) for k in fields})

    # Markdown bundle per post
    for post in schedule:
        title = post.get("title") or "Untitled"
        safe_title = "".join(ch for ch in title if ch.isalnum() or ch in (" ", "-", "_")).strip().replace(" ", "_")
        if not safe_title:
            safe_title = post.get("id") or "post"
        md_path = export_md_dir / f"{safe_title}.md"
        body = post.get("content") or ""
        meta = [
            f"Title: {title}",
            f"Subreddit: {post.get('subreddit')}",
            f"Type: {post.get('type')}",
            f"Created: {post.get('created_at')}",
            f"Scheduled: {post.get('scheduled_for')}",
            f"Posted: {post.get('posted_at')}",
            f"URL: {post.get('post_url')}",
        ]
        md_path.write_text("\n".join(meta) + "\n\n" + body)

    # Simple RSS export for mirroring
    items = []
    for post in schedule:
        title = post.get("title") or "Untitled"
        link = post.get("post_url") or ""
        pub_date = post.get("posted_at") or post.get("scheduled_for") or post.get("created_at")
        description = (post.get("content") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        items.append(
            "\n".join(
                [
                    "<item>",
                    f"<title>{title}</title>",
                    f"<link>{link}</link>",
                    f"<pubDate>{pub_date}</pubDate>",
                    f"<description>{description}</description>",
                    "</item>",
                ]
            )
        )
    rss = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<rss version=\"2.0\">",
        "<channel>",
        "<title>MCRDSE Posts Export</title>",
        "<description>Automated export feed</description>",
        "<link>https://reddit.com</link>",
        *items,
        "</channel>",
        "</rss>",
    ]
    export_rss.write_text("\n".join(rss))

    return {
        "json": str(export_json),
        "csv": str(export_csv),
        "rss": str(export_rss),
        "markdown_dir": str(export_md_dir),
    }


def write_recovery_notes(config: Dict) -> Path:
    notes = [
        "# Disaster Recovery Notes",
        f"Generated: {datetime.now().isoformat()}",
        "",
        "## Account Replacement",
    ]
    replacement = config.get("account_replacement", {})
    for step in replacement.get("activation_steps", []):
        notes.append(f"- {step}")
    notes.extend(["", "## Community Migration"])
    migration = config.get("community_migration", {})
    for note in migration.get("notes", []):
        notes.append(f"- {note}")
    notes.extend(["", "## Migration Targets"])
    for target in migration.get("targets", []):
        notes.append(f"- {target}")
    out = Path("logs/disaster_recovery_notes.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(notes))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Disaster recovery tools")
    parser.add_argument("--config", default="config/disaster_recovery.json")
    parser.add_argument("--backup", action="store_true")
    parser.add_argument("--export", action="store_true")
    parser.add_argument("--notes", action="store_true")
    args = parser.parse_args()

    config = _load_json(Path(args.config), {})
    if args.backup:
        backup_dir = create_backup(config)
        print(f"Backup created: {backup_dir}")
    if args.export:
        exports = export_posts(config)
        print(f"Exports created: {exports}")
    if args.notes:
        notes = write_recovery_notes(config)
        print(f"Recovery notes: {notes}")
    if not (args.backup or args.export or args.notes):
        create_backup(config)
        export_posts(config)
        write_recovery_notes(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
