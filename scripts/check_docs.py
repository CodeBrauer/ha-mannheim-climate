"""
Check that the German documentation mirrors the English source.

    python3 scripts/check_docs.py                     # missing or outdated pages
    python3 scripts/check_docs.py --stamp docs/en/x.md  # translation is up to date

Every page in docs/en/ needs a German page at the same path in docs/de/ with the same
outline: headings, code blocks, tables, images and admonitions in the same order. The
German page starts with a marker holding the git blob id of the English page it was
translated from. For an outdated page the check prints the command that shows what
changed in English since then; once the translation is updated, --stamp sets the marker
to the current English page and runs the check again.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = Path("docs/en")
TRANSLATION_DIR = Path("docs/de")
MARKER = re.compile(r"<!-- source: ([0-9a-f]{40}) -->\n")
FENCE = re.compile(r"\s*(`{3,}|~{3,})\s*([\w-]*)")
HEADING = re.compile(r"(#{1,6})\s")
TABLE_ROW = re.compile(r"\s*\|")
IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
ADMONITION = re.compile(r"\s*(?:!!!|\?\?\?\+?)\s*(\w+)")

type Outline = list[tuple[int, str]]


def blob_id(text: str) -> str:
    """Return the git blob id of a text, as `git hash-object` prints it for the file."""
    data = text.encode()
    header = b"blob %d\0" % len(data)
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def outline(text: str) -> Outline:
    """Return the structural items of a page with their line numbers."""
    items: Outline = []
    fence: str | None = None
    table: int | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        if fence:
            if line.strip().startswith(fence):
                fence = None
            continue
        if TABLE_ROW.match(line):
            if table is None:
                table = len(items)
                items.append((number, "table with 0 rows"))
            rows = int(items[table][1].split()[2]) + 1
            items[table] = (items[table][0], f"table with {rows} rows")
        else:
            table = None
        if match := FENCE.match(line):
            fence = match[1]
            items.append((number, f"code block {match[2] or 'without language'}"))
        elif match := HEADING.match(line):
            items.append((number, f"heading level {len(match[1])}"))
        elif match := ADMONITION.match(line):
            items.append((number, f"admonition {match[1]}"))
        items.extend((number, f"image {target}") for target in IMAGE.findall(line))
    return items


def compare(source: Outline, translation: Outline) -> str | None:
    """Describe the first structural difference, None if the outlines match."""
    for (source_line, source_item), (translation_line, translation_item) in zip(
        source, translation, strict=False
    ):
        if source_item != translation_item:
            return (
                f"English line {source_line} has {source_item}, "
                f"German line {translation_line} has {translation_item}"
            )
    if len(source) > len(translation):
        line, item = source[len(translation)]
        return f"German page lacks English line {line}: {item}"
    if len(translation) > len(source):
        line, item = translation[len(source)]
        return f"German line {line} has {item} without English counterpart"
    return None


def check_page(page: Path) -> list[str]:
    """Return the problems of one German page."""
    source_path, translation_path = SOURCE_DIR / page, TRANSLATION_DIR / page
    if not (ROOT / translation_path).exists():
        return [f"{translation_path}: missing, translate {source_path}"]
    source = (ROOT / source_path).read_text(encoding="utf-8")
    translation = (ROOT / translation_path).read_text(encoding="utf-8")
    problems = []
    marker = MARKER.match(translation)
    if not marker:
        problems.append(
            f"{translation_path}: no source marker, run --stamp {source_path} "
            "once it is translated"
        )
    elif marker[1] != blob_id(source):
        problems.append(
            f"{translation_path}: outdated, English changes since the translation: "
            f"git show {marker[1]} | diff -u - {source_path}"
        )
    if difference := compare(outline(source), outline(translation)):
        problems.append(f"{translation_path}: structure differs, {difference}")
    return problems


def pages(directory: Path) -> set[Path]:
    """Return the Markdown pages of a language, relative to its folder."""
    return {
        path.relative_to(ROOT / directory) for path in (ROOT / directory).rglob("*.md")
    }


def check() -> int:
    """Print all problems and return the exit code."""
    sources = pages(SOURCE_DIR)
    problems = [
        f"{TRANSLATION_DIR / page}: no English page {SOURCE_DIR / page}"
        for page in sorted(pages(TRANSLATION_DIR) - sources)
    ]
    for page in sorted(sources):
        problems.extend(check_page(page))
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"{TRANSLATION_DIR} is in sync with {SOURCE_DIR} ({len(sources)} pages)")
    return 0


def stamp(page: Path) -> None:
    """Record the current English page as the source of its translation."""
    source = (ROOT / SOURCE_DIR / page).read_text(encoding="utf-8")
    translation_path = ROOT / TRANSLATION_DIR / page
    translation = MARKER.sub("", translation_path.read_text(encoding="utf-8"), count=1)
    translation_path.write_text(
        f"<!-- source: {blob_id(source)} -->\n{translation}", encoding="utf-8"
    )


def page_of(path: str, parser: argparse.ArgumentParser) -> Path:
    """Return the page of an English or German path, relative to its language."""
    resolved = (Path.cwd() / path).resolve()
    relative = resolved.relative_to(ROOT) if resolved.is_relative_to(ROOT) else resolved
    for directory in (SOURCE_DIR, TRANSLATION_DIR):
        if relative.is_relative_to(directory):
            page = relative.relative_to(directory)
            if (ROOT / SOURCE_DIR / page).exists() and (
                ROOT / TRANSLATION_DIR / page
            ).exists():
                return page
    parser.error(f"{path}: needs an English page and its German translation")
    return Path()


def main() -> int:
    """Stamp the given pages, then check all pages."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--stamp",
        nargs="+",
        default=[],
        metavar="PAGE",
        help="English or German page whose translation is up to date",
    )
    args = parser.parse_args()
    for page in [page_of(path, parser) for path in args.stamp]:
        stamp(page)
    return check()


if __name__ == "__main__":
    sys.exit(main())
