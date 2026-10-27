"""Helper script to build release notes from CHANGELOG.md and GitHub auto-generated notes."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def extract_changelog_notes(changelog_path: Path, tag: str) -> str:
    """Extract release notes for a given tag from CHANGELOG.md."""
    version = tag.lstrip("v")
    if not changelog_path.exists():
        return ""

    lines = changelog_path.read_text(encoding="utf-8").splitlines()
    in_version = False
    version_lines: list[str] = []

    for line in lines:
        header_match = re.match(r"^##\s+\[?v?([0-9]+\.[0-9]+\.[0-9]+[^\]\s]*)\]?", line)
        if header_match:
            if header_match.group(1) == version:
                in_version = True
                continue
            elif in_version:
                break
        elif in_version:
            if re.match(r"^\[[^\]]+\]:\s*http", line):
                break
            version_lines.append(line)

    return "\n".join(version_lines).strip()


def extract_contributors_section(auto_notes: str) -> str:
    """Extract ## New Contributors or ## Contributors block from GitHub auto-notes."""
    if not auto_notes.strip():
        return ""

    match_new = re.search(r"(## (?:New )?Contributors.*)", auto_notes, re.DOTALL)
    if match_new:
        return match_new.group(1).strip()

    contributors = sorted(set(re.findall(r"@([a-zA-Z0-9_-]+)", auto_notes)))
    sections: list[str] = []
    if contributors:
        contributor_lines = [f"* @{c}" for c in contributors]
        sections.append("## Contributors\n" + "\n".join(contributor_lines))

    match_changelog = re.search(r"(\*\*Full Changelog\*\*:.*)", auto_notes)
    if match_changelog:
        sections.append(match_changelog.group(1).strip())

    return "\n\n".join(sections).strip()


def build_release_notes(
    tag: str, auto_notes: str = "", root: Path | None = None
) -> str:
    """Build complete release notes by combining curated changelog notes with contributor attribution."""
    if root is None:
        root = Path(__file__).resolve().parent.parent
    changelog_path = root / "CHANGELOG.md"

    curated = extract_changelog_notes(changelog_path, tag)
    contributors = extract_contributors_section(auto_notes)

    final_sections: list[str] = []
    if curated:
        final_sections.append(curated)
    elif auto_notes.strip():
        final_sections.append(auto_notes.strip())

    if curated and contributors:
        final_sections.append(contributors)

    return "\n\n".join(final_sections).strip()


def main() -> None:
    """Main CLI entrypoint."""
    if len(sys.argv) < 2:
        print(
            "Usage: python -m devtools.release_notes <tag> [auto_notes_file]",
            file=sys.stderr,
        )
        sys.exit(1)

    tag = sys.argv[1]
    root = Path(__file__).resolve().parent.parent
    release_notes_path = root / "RELEASE_NOTES.md"

    auto_notes = ""
    if len(sys.argv) >= 3 and sys.argv[2] != "-":
        auto_file = Path(sys.argv[2])
        if auto_file.exists():
            auto_notes = auto_file.read_text(encoding="utf-8")
    elif not sys.stdin.isatty():
        auto_notes = sys.stdin.read()

    result = build_release_notes(tag, auto_notes=auto_notes, root=root)
    if result:
        release_notes_path.write_text(result + "\n", encoding="utf-8")
        print(f"Successfully generated {release_notes_path}")
    else:
        print("No release notes generated.", file=sys.stderr)


if __name__ == "__main__":
    main()
