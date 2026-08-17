"""Validate a generated Tieba HTML archive and its local image references."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def count(pattern: str, text: str) -> int:
    return len(re.findall(pattern, text))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path, help="HTML archive to validate")
    parser.add_argument("--expected-main", type=int)
    parser.add_argument("--expected-nested", type=int)
    parser.add_argument("--expected-assets", type=int)
    args = parser.parse_args()

    html_path = args.html.resolve()
    text = html_path.read_text(encoding="utf-8")
    main_posts = count(r'<article class="post"', text)
    nested_posts = count(r'<div class="lzl-item"', text)
    image_elements = count(r'<img\b', text)

    raw_sources = re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', text)
    local_sources = sorted({src for src in raw_sources if not re.match(r"^(?:https?:)?//|^data:", src)})
    remote_sources = sorted({src for src in raw_sources if src not in local_sources})
    missing = [src for src in local_sources if not (html_path.parent / src).is_file()]

    failures: list[str] = []
    if args.expected_main is not None and main_posts != args.expected_main:
        failures.append(f"main posts: expected {args.expected_main}, got {main_posts}")
    if args.expected_nested is not None and nested_posts != args.expected_nested:
        failures.append(f"nested posts: expected {args.expected_nested}, got {nested_posts}")
    if args.expected_assets is not None and len(local_sources) != args.expected_assets:
        failures.append(f"local assets: expected {args.expected_assets}, got {len(local_sources)}")
    if missing:
        failures.append(f"missing local image files: {len(missing)}")
    if remote_sources:
        failures.append(f"remote image dependencies remain: {len(remote_sources)}")

    result = {
        "html": str(html_path),
        "bytes": html_path.stat().st_size,
        "sha256": hashlib.sha256(html_path.read_bytes()).hexdigest().upper(),
        "main_posts": main_posts,
        "nested_posts": nested_posts,
        "total_records": main_posts + nested_posts,
        "image_elements": image_elements,
        "unique_local_images": len(local_sources),
        "missing_local_images": missing,
        "remote_images": remote_sources,
        "ok": not failures,
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())

