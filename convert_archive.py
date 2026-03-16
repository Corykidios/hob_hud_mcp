"""
convert_archive.py
Walks D:/under_rug/remember_me/, reads provider/subject from folder structure
and timestamp/title from filename, prepends YAML frontmatter, writes to
D:/graphrag_gang/docs/ preserving the body content exactly.

Source untouched. Run this once before import_docs.py.
"""

import re
from pathlib import Path

SOURCE_ROOT = Path("D:/under_rug/remember_me")
DEST_ROOT   = Path("D:/graphrag_gang/docs")

def parse_filename(stem: str):
    """
    chatgpt_24.06.28_translate_secret_orphica_by_koryphanes
    -> provider=chatgpt, date=24.06.28, title=translate_secret_orphica_by_koryphanes
    """
    parts = stem.split("_", 2)
    if len(parts) < 3:
        return None, None, stem
    provider  = parts[0]
    date_part = parts[1]
    title     = parts[2]
    m = re.match(r'(\d{2})\.(\d{2})\.(\d{2})', date_part)
    if m:
        updated = f"20{m.group(1)}-{m.group(2)}-{m.group(3)}"
    else:
        updated = date_part
    return provider, updated, title

def build_frontmatter(title, category, updated, provider, subject):
    lines = [
        "---",
        f"title: {title}",
        f"category: {category}",
        f"updated: '{updated}'",
        "related: []",
        "key_concepts:",
        f"  - {subject}",
        f"  - {provider}",
        "---",
        "",
        ""
    ]
    return "\n".join(lines)

def convert():
    converted = 0
    skipped   = 0

    for md_file in SOURCE_ROOT.rglob("*.md"):
        try:
            rel   = md_file.relative_to(SOURCE_ROOT)
            parts = rel.parts
            if len(parts) < 3:
                skipped += 1
                continue

            provider_dir = parts[0]
            subject_dir  = parts[1]
            subject  = subject_dir.replace("_individual", "").replace("_notebooklm", "")
            category = f"{provider_dir}/{subject}"

            stem = md_file.stem
            provider, updated, title = parse_filename(stem)
            if not provider:
                provider = provider_dir

            body = md_file.read_text(encoding="utf-8", errors="replace")

            if body.startswith("---"):
                skipped += 1
                continue

            frontmatter = build_frontmatter(title, category, updated, provider, subject)
            output      = frontmatter + body

            dest_file = DEST_ROOT / rel
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            dest_file.write_text(output, encoding="utf-8")
            converted += 1

            if converted % 500 == 0:
                print(f"  {converted} files converted...")

        except Exception as e:
            print(f"  ERROR {md_file}: {e}")
            skipped += 1

    print(f"\nDone. {converted} converted, {skipped} skipped.")

if __name__ == "__main__":
    convert()