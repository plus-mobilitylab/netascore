"""Release metadata of NetAScore - used by the release workflow (.github/workflows/release.yml), can be run locally.

The version number is defined in settings.py (NETASCORE_VERSION). For a release, this script
- sets 'version' and 'date-released' in CITATION.cff,
- adds the release date to the heading of the version in CHANGELOG.md ('## [2.1.0]' -> '## [2.1.0] - 2026-10-21'),
  and updates its introduction "Changes since release ..." (comparison with the previous release tag),
- checks that the authors in .zenodo.json match CITATION.cff (Zenodo uses .zenodo.json if present),
- writes the release notes (section of the respective version in CHANGELOG.md) to a file.

Usage (from the repository root):
  python .github/scripts/release_metadata.py version
  python .github/scripts/release_metadata.py prepare [--date YYYY-MM-DD] [--notes-file release_notes.md]
  python .github/scripts/release_metadata.py notes --notes-file release_notes.md
"""
import argparse
import datetime
import json
import re
import subprocess
import sys

import yaml

SETTINGS_FILE = "settings.py"
CITATION_FILE = "CITATION.cff"
CHANGELOG_FILE = "CHANGELOG.md"
ZENODO_FILE = ".zenodo.json"


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def write(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def get_version() -> str:
    match = re.search(r'^NETASCORE_VERSION = "([^"]+)"', read(SETTINGS_FILE), re.MULTILINE)
    if not match:
        fail(f"NETASCORE_VERSION not found in {SETTINGS_FILE}")
    version = match.group(1)
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail(f"NETASCORE_VERSION '{version}' is no version number of the form 1.2.3")
    return version


def update_citation(version: str, date: str) -> None:
    """Sets the version and release date of the software (top-level keys, not those of 'preferred-citation')."""
    text = read(CITATION_FILE)
    for key, value in (("version", version), ("date-released", date)):
        pattern = rf"^{key}: .*$"
        if re.search(pattern, text, re.MULTILINE):
            text = re.sub(pattern, f"{key}: {value}", text, count=1, flags=re.MULTILINE)
        else:
            fail(f"key '{key}' not found in {CITATION_FILE}")
    write(CITATION_FILE, text)


def version_key(version: str) -> tuple:
    return tuple(int(v) for v in version.split("."))


def previous_release(version: str) -> str:
    """Highest released version (Git tag 'v1.2.3') below the given version - None if there is none."""
    tags = subprocess.run(["git", "tag", "--list", "v*"], capture_output=True, text=True, check=True).stdout.split()
    versions = [t[1:] for t in tags if re.fullmatch(r"v\d+\.\d+\.\d+", t) and version_key(t[1:]) < version_key(version)]
    return max(versions, key=version_key) if versions else None


def version_heading(version: str) -> re.Pattern:
    """Heading of the version in CHANGELOG.md, with or without release date ('## [2.1.0]', '## [2.1.0] - 2026-10-21')."""
    return re.compile(rf"^## \[{re.escape(version)}\]( - \d{{4}}-\d{{2}}-\d{{2}})?[ \t]*$", re.MULTILINE)


def release_notes(text: str, version: str) -> str:
    """Section of the version in the changelog text (without heading) up to the next version heading."""
    match = version_heading(version).search(text)
    if not match:
        fail(f"{CHANGELOG_FILE} has no section '## [{version}]' - please describe the changes of the release there")
    end = re.compile(r"^## \[", re.MULTILINE).search(text, match.end())
    return text[match.end():end.start() if end else len(text)].strip() + "\n"


def update_changelog(version: str, date: str) -> str:
    """Adds the release date to the heading of the version, updates the introduction 'Changes since release ...'
    (comparison of the previous release with this one), and returns the section of the version (release notes)."""
    text = read(CHANGELOG_FILE)
    intro = re.compile(r"^Changes since release \[[^\]]*\]\((?P<base>https://github\.com/[^)]+/compare/)[^)]*\)\.[ \t]*$", re.MULTILINE)
    intro_match = intro.search(text)
    previous = previous_release(version)
    if intro_match and previous:
        text = (text[:intro_match.start()] + f"Changes since release [{previous}]({intro_match.group('base')}v{previous}...v{version})."
                + text[intro_match.end():])
    else:
        print(f"note: introduction 'Changes since release [...](...)' not updated "
              f"({'no such line in ' + CHANGELOG_FILE if not intro_match else 'no previous release tag found'})", file=sys.stderr)
    notes = release_notes(text, version)  # also checks that the section exists
    text = version_heading(version).sub(f"## [{version}] - {date}", text, count=1)
    write(CHANGELOG_FILE, text)
    return notes


def check_zenodo_authors() -> None:
    """Zenodo ignores CITATION.cff if .zenodo.json exists - the authors (incl. ORCID) need to match."""
    citation = yaml.safe_load(read(CITATION_FILE))
    zenodo = json.loads(read(ZENODO_FILE))
    cff_authors = [(f"{a['family-names']}, {a['given-names']}", (a.get('orcid') or '').removeprefix("https://orcid.org/") or None)
                   for a in citation['authors']]
    zenodo_authors = [(c['name'], c.get('orcid')) for c in zenodo['creators']]
    if cff_authors != zenodo_authors:
        fail(f"the authors in {ZENODO_FILE} (creators) do not match {CITATION_FILE}:\n"
             f"  {CITATION_FILE}: {cff_authors}\n  {ZENODO_FILE}: {zenodo_authors}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Release metadata of NetAScore")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version", help="print the version number (settings.py)")
    prepare = commands.add_parser("prepare", help="update CITATION.cff and CHANGELOG.md for the release, check .zenodo.json")
    prepare.add_argument("--date", default=datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
                         help="release date (default: today, UTC)")
    prepare.add_argument("--notes-file", help="file to write the release notes to (section of the version in CHANGELOG.md)")
    notes = commands.add_parser("notes", help="write the release notes (section of the version in CHANGELOG.md) without changing any files")
    notes.add_argument("--notes-file", required=True, help="file to write the release notes to")
    args = parser.parse_args()

    version = get_version()
    if args.command == "version":
        print(version)
        return
    if args.command == "notes":
        write(args.notes_file, release_notes(read(CHANGELOG_FILE), version))
        return
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        fail(f"invalid date '{args.date}' (expected YYYY-MM-DD)")
    check_zenodo_authors()
    update_citation(version, args.date)
    notes = update_changelog(version, args.date)
    if args.notes_file:
        write(args.notes_file, notes)
    print(f"prepared release {version} ({args.date})")


if __name__ == "__main__":
    main()
