#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Bump, and validate, the version of a single versioned artifact in this repo.

Usage:
    uv run scripts/bump_version.py bump patch agentic_logging
    uv run scripts/bump_version.py bump minor claude-cli
    uv run scripts/bump_version.py --list
    uv run scripts/bump_version.py --check                 # every artifact
    uv run scripts/bump_version.py --check agentic_logging # one artifact
    uv run scripts/bump_version.py --check-release         # vs origin/release

Why this exists
---------------
A release bumps a version that is written down in more than one file. Doing
that with `sed -i '' "0,/^version = /..."` already went wrong once: BSD sed
does not support the `0,/regex/` address form that GNU sed does, so the edit
landed in `__init__.py`, silently did nothing to `pyproject.toml`, and the
script still printed `0.1.0 -> 0.1.1`. The two files disagreed, which is worse
than not bumping at all, and nothing said so.

So the rule this script is built around is: a write that does not land must
fail loudly. Every location is pre-flighted before anything is written, and
every location is read back from disk afterwards and compared to the target.
A location that does not read back as the target version is an error, not a
warning, and not something the caller can miss.

The second rule follows from the first: a bump either lands everywhere or
nowhere. Every file a bump can touch is snapshotted before the first write,
and any failure, including a `uv lock` that fails after an earlier file was
already rewritten, restores all of them and names what it restored. Otherwise
this tool could leave behind the very half-applied tree it exists to detect.

What it knows about
-------------------
Two kinds of versioned artifact, because two release gates check two kinds:

  * Python packages under lib/python/. Version locations are discovered, not
    hardcoded: the `[project] version` in pyproject.toml, every `__version__`
    assignment in the package's own sources, and every uv.lock in the repo
    that records this distribution's version (its own, and the locks of
    downstream projects such as tests/consumer_contracts, which CI installs
    with `uv sync --locked`).

  * Provider images under providers/workspaces/. The version location is the
    top-level `version:` key of manifest.yaml, which is what
    build-workspace-images.yml turns into the published image tag and what
    _check-version.yml compares against the release branch.

Relationship to .github/workflows/_check-version.yml
----------------------------------------------------
That workflow is still the authority on what the release gate accepts. This
script does not replace it and is not called by it. `--check-release` here is
a local preview of the same question: "did shipped content change without the
version moving". It is the more permissive of the two, because it attributes a
change only to the artifact whose directory it touched, while the gate also
treats shared paths (workspace/, plugins/, lib/python/, build-provider.py) as
provider image content. It also compares committed history, like the gate, so
an uncommitted working-tree edit does not register. If the two ever disagree,
the workflow wins.
"""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent  # scripts/ -> repo root

PY_PACKAGES_DIR = ROOT / "lib" / "python"
PROVIDERS_DIR = ROOT / "providers" / "workspaces"

DEFAULT_BASE_REF = "origin/release"

# Strict three-part release versions. Every artifact in this repo uses this
# form today, and the arithmetic below has no defined answer for a
# pre-release, so anything else is rejected rather than guessed at.
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

# `version = "..."` on its own line. Anchored to the line start so an indented
# key inside a nested table is never mistaken for the project version.
PYPROJECT_VERSION_LINE_RE = re.compile(r'^(version\s*=\s*")([^"]*)(")\s*$')

# `__version__ = "..."` at module level, single or double quoted.
DUNDER_VERSION_LINE_RE = re.compile(
    r'^(__version__\s*[:=][^"\']*["\'])([^"\']*)(["\'])'
)

# Top-level `version:` key of a provider manifest. Anchored to the line start,
# which is what makes it pick the manifest's own version and not the nested
# `version:` keys under the toolchain entries. This is the same shape
# _check-version.yml uses to read these manifests.
MANIFEST_VERSION_LINE_RE = re.compile(r'^(version:\s*"?)([^"\s]+)("?)\s*$')

# Directories that never contain a version this script owns.
SKIP_DIR_NAMES = {".git", ".venv", "venv", "build", "dist", "__pycache__", ".worktrees"}


class BumpError(Exception):
    """A condition the caller must see. Always fatal, never a warning."""


def _rel(path: Path) -> str:
    """Repo-relative path for display, falling back to the absolute path.

    The fallback matters under test, where the discovered tree is a temporary
    directory rather than this checkout.
    """
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# Version arithmetic
# ---------------------------------------------------------------------------


def parse_version(raw: str) -> tuple[int, int, int]:
    match = SEMVER_RE.match(raw.strip())
    if match is None:
        raise BumpError(
            f"version {raw!r} is not a plain MAJOR.MINOR.PATCH release version. "
            f"This script refuses to do arithmetic on a version shape it does "
            f"not understand."
        )
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def next_version(current: str, part: str) -> str:
    major, minor, patch = parse_version(current)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise BumpError(f"unknown version part {part!r}; expected patch, minor or major")


# ---------------------------------------------------------------------------
# Version locations
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Location:
    """One file that records an artifact's version.

    `regenerated` locations (uv.lock) are not text-edited. uv owns their
    contents, so they are refreshed by running `uv lock` and then verified by
    reading back, exactly like the edited ones.
    """

    path: Path
    kind: str  # pyproject | dunder | manifest | lock
    detail: str  # what inside the file carries the version

    @property
    def regenerated(self) -> bool:
        return self.kind == "lock"

    @property
    def rel(self) -> str:
        return _rel(self.path)

    def __str__(self) -> str:
        return f"{self.rel} ({self.detail})"


def _read_pyproject_version(text: str) -> str | None:
    """Read [project].version, tolerating a file that cannot be parsed as TOML.

    Reading through tomllib rather than the write regex is deliberate: the
    check half must not be able to agree with a broken write half by sharing
    its mistake.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise BumpError(f"could not parse TOML: {exc}") from exc
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    version = project.get("version")
    return version if isinstance(version, str) else None


def _read_dunder_version(text: str) -> str | None:
    for line in text.splitlines():
        match = DUNDER_VERSION_LINE_RE.match(line)
        if match is not None:
            return match.group(2)
    return None


def _read_manifest_version(text: str) -> str | None:
    for line in text.splitlines():
        match = MANIFEST_VERSION_LINE_RE.match(line)
        if match is not None:
            return match.group(2)
    return None


def _read_lock_versions(text: str, dist_name: str) -> list[str]:
    """Every version this lock records for `dist_name`.

    A lock can mention the distribution more than once in principle, so all
    occurrences are returned and the caller treats any disagreement as an
    inconsistency rather than picking one.
    """
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise BumpError(f"could not parse uv.lock as TOML: {exc}") from exc
    found: list[str] = []
    for entry in data.get("package", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("name") == dist_name and isinstance(entry.get("version"), str):
            found.append(entry["version"])
    return found


def read_location(location: Location, text: str, dist_name: str) -> str | None:
    if location.kind == "pyproject":
        return _read_pyproject_version(text)
    if location.kind == "dunder":
        return _read_dunder_version(text)
    if location.kind == "manifest":
        return _read_manifest_version(text)
    if location.kind == "lock":
        versions = _read_lock_versions(text, dist_name)
        if not versions:
            return None
        if len(set(versions)) > 1:
            raise BumpError(
                f"{location.rel} records {dist_name} at more than one version: "
                f"{', '.join(sorted(set(versions)))}"
            )
        return versions[0]
    raise BumpError(f"unknown location kind {location.kind!r}")


def render_location(location: Location, text: str, target: str) -> str:
    """Return `text` with the version replaced by `target`.

    Line oriented on purpose. The incident this script exists to prevent came
    from a multi-line regex address form that behaved differently on two seds;
    a single anchored match per line has one behaviour everywhere.
    """
    if location.kind == "pyproject":
        return _render_pyproject(text, target)
    if location.kind == "dunder":
        return _render_line(text, DUNDER_VERSION_LINE_RE, target)
    if location.kind == "manifest":
        return _render_line(text, MANIFEST_VERSION_LINE_RE, target)
    raise BumpError(f"location kind {location.kind!r} is not text-editable")


def _render_pyproject(text: str, target: str) -> str:
    """Replace the version key of the [project] table only."""
    lines = text.splitlines(keepends=True)
    table: str | None = None
    out: list[str] = []
    replaced = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            table = stripped[1:-1].strip()
        elif table == "project" and not replaced:
            match = PYPROJECT_VERSION_LINE_RE.match(line.rstrip("\r\n"))
            if match is not None:
                ending = line[len(line.rstrip("\r\n")) :]
                line = f"{match.group(1)}{target}{match.group(3)}{ending}"
                replaced = True
        out.append(line)
    return "".join(out)


def _render_line(text: str, pattern: re.Pattern[str], target: str) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    replaced = False
    for line in lines:
        if not replaced:
            match = pattern.match(line.rstrip("\r\n"))
            if match is not None:
                ending = line[len(line.rstrip("\r\n")) :]
                line = f"{match.group(1)}{target}{match.group(3)}{ending}"
                replaced = True
        out.append(line)
    return "".join(out)


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Artifact:
    """A thing with a version: a Python package or a provider image."""

    name: str  # how a user names it on the command line
    kind: str  # python | provider
    directory: Path
    dist_name: str  # distribution name for python, image name for provider
    locations: tuple[Location, ...]
    # Files that were scanned as plausible version carriers and found not to
    # declare one. Reported so that a location which quietly stopped
    # declaring a version is visible instead of silently skipped.
    silent_candidates: tuple[Path, ...]

    @property
    def rel(self) -> str:
        return _rel(self.directory)

    @property
    def lock_projects(self) -> tuple[Path, ...]:
        """Directories whose uv.lock records this distribution."""
        return tuple(
            dict.fromkeys(loc.path.parent for loc in self.locations if loc.regenerated)
        )


def _iter_python_sources(package_dir: Path):
    for path in sorted(package_dir.rglob("*.py")):
        if any(part in SKIP_DIR_NAMES for part in path.relative_to(package_dir).parts):
            continue
        # Test sources are not shipped in the wheel, and a fixture that
        # happens to assign __version__ is not a release location.
        if any(
            part in {"tests", "test"} for part in path.relative_to(package_dir).parts
        ):
            continue
        yield path


def _iter_lock_files(root: Path):
    for path in sorted(root.rglob("uv.lock")):
        if any(part in SKIP_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        yield path


def _discover_python_package(package_dir: Path, root: Path) -> Artifact:
    pyproject = package_dir / "pyproject.toml"
    if not pyproject.is_file():
        raise BumpError(f"{package_dir} has no pyproject.toml")
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project", {})
    dist_name = project.get("name")
    if not isinstance(dist_name, str):
        raise BumpError(f"{pyproject} declares no [project] name")

    locations: list[Location] = [Location(pyproject, "pyproject", "[project] version")]
    silent: list[Path] = []

    for source in _iter_python_sources(package_dir):
        text = source.read_text(encoding="utf-8")
        parts = source.relative_to(package_dir).parts
        if _read_dunder_version(text) is not None:
            locations.append(Location(source, "dunder", "__version__"))
        elif len(parts) == 2 and parts[1] == "__init__.py":
            # A top-level module's __init__.py is where this repo puts
            # __version__, so one that has none is worth saying out loud. A
            # nested subpackage __init__.py never carries one and reporting
            # those would bury the signal.
            silent.append(source)

    for lock in _iter_lock_files(root):
        text = lock.read_text(encoding="utf-8")
        if _read_lock_versions(text, dist_name):
            locations.append(Location(lock, "lock", f"[[package]] {dist_name}"))

    return Artifact(
        name=package_dir.name,
        kind="python",
        directory=package_dir,
        dist_name=dist_name,
        locations=tuple(locations),
        silent_candidates=tuple(silent),
    )


def _discover_provider(provider_dir: Path) -> Artifact:
    manifest = provider_dir / "manifest.yaml"
    if not manifest.is_file():
        raise BumpError(f"{provider_dir} has no manifest.yaml")
    return Artifact(
        name=provider_dir.name,
        kind="provider",
        directory=provider_dir,
        dist_name=provider_dir.name,
        locations=(Location(manifest, "manifest", "top-level version:"),),
        silent_candidates=(),
    )


def discover_artifacts(root: Path = ROOT) -> list[Artifact]:
    artifacts: list[Artifact] = []
    py_dir = root / "lib" / "python"
    if py_dir.is_dir():
        for package_dir in sorted(py_dir.iterdir()):
            if (package_dir / "pyproject.toml").is_file():
                artifacts.append(_discover_python_package(package_dir, root))
    providers_dir = root / "providers" / "workspaces"
    if providers_dir.is_dir():
        for provider_dir in sorted(providers_dir.iterdir()):
            if (provider_dir / "manifest.yaml").is_file():
                artifacts.append(_discover_provider(provider_dir))
    return artifacts


def find_artifact(name: str, root: Path = ROOT) -> Artifact:
    artifacts = discover_artifacts(root)
    for artifact in artifacts:
        if name in (artifact.name, artifact.dist_name):
            return artifact
    known = ", ".join(a.name for a in artifacts)
    raise BumpError(f"unknown artifact {name!r}. Known artifacts: {known}")


# ---------------------------------------------------------------------------
# Reading and checking
# ---------------------------------------------------------------------------


def current_versions(artifact: Artifact) -> dict[Location, str | None]:
    found: dict[Location, str | None] = {}
    for location in artifact.locations:
        text = location.path.read_text(encoding="utf-8")
        found[location] = read_location(location, text, artifact.dist_name)
    return found


def declared_version(artifact: Artifact) -> str:
    """The artifact's version according to its primary location."""
    primary = artifact.locations[0]
    text = primary.path.read_text(encoding="utf-8")
    version = read_location(primary, text, artifact.dist_name)
    if version is None:
        raise BumpError(f"{primary} declares no version")
    return version


def check_artifact(artifact: Artifact, *, verbose: bool = True) -> bool:
    """True when every discovered location agrees. Prints the inventory."""
    try:
        found = current_versions(artifact)
    except BumpError as exc:
        print(f"FAIL {artifact.name}: {exc}", file=sys.stderr)
        return False

    missing = [loc for loc, version in found.items() if version is None]
    distinct = {version for version in found.values() if version is not None}

    ok = not missing and len(distinct) == 1

    if ok and verbose:
        version = next(iter(distinct))
        print(f"OK   {artifact.name} at {version} across {len(found)} location(s)")
        for location in artifact.locations:
            print(f"       {location}")
    elif not ok:
        print(f"FAIL {artifact.name}: version locations disagree", file=sys.stderr)
        for location, version in found.items():
            shown = version if version is not None else "NO VERSION FOUND"
            print(f"       {location}: {shown}", file=sys.stderr)

    if verbose and artifact.silent_candidates:
        # Not a failure. A package is allowed not to export __version__. It is
        # reported so that a file which used to declare one and no longer does
        # is visible here rather than quietly dropped from the bump.
        for path in artifact.silent_candidates:
            print(f"       note: {_rel(path)} declares no __version__")

    return ok


def check_all(names: list[str]) -> bool:
    artifacts = (
        [find_artifact(name) for name in names] if names else discover_artifacts()
    )
    if not artifacts:
        raise BumpError("no versioned artifacts discovered; refusing to report success")
    # Every artifact is checked before returning, so one failure does not
    # hide the rest.
    results = [check_artifact(artifact) for artifact in artifacts]
    return all(results)


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------


def _write_text(path: Path, text: str) -> None:
    """Single funnel for every write, so tests can make one write fail.

    Replacement is atomic: the new contents go to a temporary file in the same
    directory and are then moved over the target with os.replace, which is
    atomic within a filesystem. Path.write_text() truncates the target first,
    so a crash between the truncate and the write leaves a half written file,
    which is the same class of outcome this script exists to prevent.
    """
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        # mkstemp creates the temp file 0600, so the original mode has to be
        # carried over or the replacement would silently tighten permissions.
        if path.exists():
            os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _snapshot(paths: Iterable[Path]) -> dict[Path, bytes | None]:
    """Raw contents of every path, before anything is written.

    A path that does not exist yet is recorded as None so that restoring can
    delete it again rather than leaving a file the bump invented.
    """
    snapshots: dict[Path, bytes | None] = {}
    for path in paths:
        snapshots[path] = path.read_bytes() if path.is_file() else None
    return snapshots


def _restore(snapshots: dict[Path, bytes | None]) -> tuple[list[Path], list[str]]:
    """Put every changed path back. Returns (restored paths, restore failures).

    Only paths whose bytes actually differ are touched, so the report names
    what really moved. A restore that itself fails is returned rather than
    raised, because the caller is already handling an error and losing that
    error to a second one would hide the reason the bump failed.
    """
    restored: list[Path] = []
    failures: list[str] = []
    for path, original in snapshots.items():
        try:
            if original is None:
                if path.exists():
                    path.unlink()
                    restored.append(path)
                continue
            if path.is_file() and path.read_bytes() == original:
                continue
            _write_bytes(path, original)
            restored.append(path)
        except OSError as exc:
            failures.append(f"{_rel(path)}: {exc}")
    return restored, failures


def _write_bytes(path: Path, data: bytes) -> None:
    """Atomic byte for byte replacement, used by the rollback path.

    Bytes rather than text because a restore must reproduce the original
    exactly, including any line endings and encoding the reader normalised.
    """
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if path.exists():
            os.chmod(tmp, stat.S_IMODE(path.stat().st_mode))
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _report_rollback(outcome: tuple[list[Path], list[str]]) -> None:
    """Say exactly which files were put back, and which could not be.

    Printed to stderr before the error that caused it is raised, so a failed
    bump reads as "these files moved and were restored" rather than leaving
    the caller to guess what state the tree is in.
    """
    restored, failures = outcome
    if restored:
        print("  restored to their pre-bump contents:", file=sys.stderr)
        for path in restored:
            print(f"    {_rel(path)}", file=sys.stderr)
    elif not failures:
        print(
            "  nothing had been written yet, so nothing was restored", file=sys.stderr
        )
    for failure in failures:
        print(
            f"  COULD NOT RESTORE {failure}. This file must be repaired by hand.",
            file=sys.stderr,
        )


def _refresh_lock(project_dir: Path) -> None:
    result = subprocess.run(
        ["uv", "lock"],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise BumpError(
            f"`uv lock` failed in {project_dir}:\n{result.stdout}{result.stderr}"
        )


def bump_artifact(
    artifact: Artifact,
    part: str,
    *,
    refresh_lock=_refresh_lock,
) -> str:
    """Bump every location of `artifact`, or fail without leaving a lie behind.

    Order is pre-flight, write, read back. The read back is the point: it is
    the step the original sed based bump did not have, and its absence is what
    turned a failed edit into a printed success.
    """
    versions = current_versions(artifact)
    missing = [str(loc) for loc, version in versions.items() if version is None]
    if missing:
        raise BumpError("refusing to bump: no version found in " + ", ".join(missing))
    distinct = set(versions.values())
    if len(distinct) > 1:
        detail = "; ".join(f"{loc}: {v}" for loc, v in versions.items())
        raise BumpError(
            f"refusing to bump {artifact.name}: its locations already disagree "
            f"({detail}). Reconcile them first."
        )

    current = next(iter(distinct))
    assert current is not None
    target = next_version(current, part)

    edited = [loc for loc in artifact.locations if not loc.regenerated]
    regenerated = [loc for loc in artifact.locations if loc.regenerated]

    # Pre-flight. Every edited location must be writable and must actually
    # change under the rendering, before anything is written.
    pending: list[tuple[Location, str]] = []
    problems: list[str] = []
    for location in edited:
        if not os.access(location.path, os.W_OK):
            problems.append(f"{location.rel} is not writable")
            continue
        text = location.path.read_text(encoding="utf-8")
        new_text = render_location(location, text, target)
        if new_text == text:
            problems.append(f"{location.rel} did not change under the version rewrite")
            continue
        pending.append((location, new_text))
    for location in regenerated:
        if not os.access(location.path, os.W_OK):
            problems.append(f"{location.rel} is not writable")
    if problems:
        raise BumpError(
            "refusing to bump, nothing was modified:\n  " + "\n  ".join(problems)
        )

    print(f"{artifact.name}: {current} -> {target}")

    # Everything from here on is transactional. Every file that this bump can
    # touch is snapshotted first, and any failure at all, including one raised
    # from inside `uv lock` or from the read back, puts all of them back. A
    # partially bumped tree is the disagreeing-version state this script exists
    # to detect, so the script must not be able to produce one itself.
    snapshots = _snapshot(loc.path for loc in artifact.locations)
    try:
        for location, new_text in pending:
            _write_text(location.path, new_text)

        for project_dir in artifact.lock_projects:
            refresh_lock(project_dir)

        # Read back from disk. Anything that does not now say `target` is a
        # failure, including a lock that `uv lock` declined to move.
        after = current_versions(artifact)
        wrong = [
            f"{loc}: {version if version is not None else 'NO VERSION FOUND'}"
            for loc, version in after.items()
            if version != target
        ]
        if wrong:
            raise BumpError(
                f"bump of {artifact.name} to {target} did NOT fully apply, so it "
                f"was rolled back (see the restore report above).\n  "
                + "\n  ".join(wrong)
            )
    except BaseException as exc:
        _report_rollback(_restore(snapshots))
        if isinstance(exc, BumpError):
            raise
        # Anything else would reach the caller as a bare traceback that says
        # nothing about what happened to the tree, which is precisely the
        # illegible failure this script is meant to replace.
        raise BumpError(
            f"bump of {artifact.name} to {target} failed and was rolled back: "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    for location in artifact.locations:
        print(f"  updated {location}")
    print(f"  verified {len(after)} location(s) at {target}")
    return target


# ---------------------------------------------------------------------------
# Release comparison
# ---------------------------------------------------------------------------


def _git(*args: str) -> str | None:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else None


def _version_at_ref(artifact: Artifact, ref: str) -> str | None:
    primary = artifact.locations[0]
    blob = _git("show", f"{ref}:{primary.rel}")
    if blob is None:
        return None
    return read_location(primary, blob, artifact.dist_name)


def _shipped_prefixes(artifact: Artifact) -> tuple[str, ...]:
    """Paths whose change means this artifact's shipped content changed.

    For a provider image this is only the provider's own directory. The gate
    also treats shared paths (workspace/, plugins/, lib/python/,
    scripts/build-provider.py) as image content, and this preview deliberately
    does not, because a local run reporting "bump every provider" on any
    library edit would be noise. That makes this the more permissive of the
    two, which is why the workflow, not this script, remains the gate.
    """
    return (f"{artifact.rel}/",)


def check_release(names: list[str], base_ref: str) -> bool:
    artifacts = (
        [find_artifact(name) for name in names] if names else discover_artifacts()
    )
    changed_raw = _git("diff", "--name-only", f"{base_ref}...HEAD")
    if changed_raw is None:
        print(
            f"ERROR: could not diff against {base_ref}. Run "
            f"`git fetch origin release` first.",
            file=sys.stderr,
        )
        return False
    changed = [line for line in changed_raw.splitlines() if line]

    ok = True
    for artifact in artifacts:
        release_version = _version_at_ref(artifact, base_ref)
        if release_version is None:
            print(f"OK   {artifact.name}: not present on {base_ref}, new artifact")
            continue

        head_version = declared_version(artifact)
        prefixes = _shipped_prefixes(artifact)
        test_prefixes = tuple(f"{prefix}tests/" for prefix in prefixes)
        touched = [
            path
            for path in changed
            if path.startswith(prefixes) and not path.startswith(test_prefixes)
        ]

        if not touched:
            print(f"OK   {artifact.name}: unchanged vs {base_ref} at {release_version}")
            continue

        if parse_version(head_version) > parse_version(release_version):
            print(f"OK   {artifact.name}: {release_version} -> {head_version}")
            continue

        ok = False
        print(
            f"FAIL {artifact.name}: content changed vs {base_ref} but the version "
            f"did not move ({release_version} on {base_ref}, {head_version} here). "
            f"Run: uv run scripts/bump_version.py bump patch {artifact.name}",
            file=sys.stderr,
        )

        # A location that declared a version on the release branch and no
        # longer does would silently drop out of every future bump, so it is
        # surfaced against the last released state rather than against nothing.
        for location in artifact.locations:
            if location.regenerated:
                continue
            blob = _git("show", f"{base_ref}:{location.rel}")
            if blob is None:
                continue
            if read_location(location, blob, artifact.dist_name) is None:
                continue
            text = location.path.read_text(encoding="utf-8")
            if read_location(location, text, artifact.dist_name) is None:
                print(
                    f"       {location.rel} declared a version on {base_ref} and "
                    f"no longer does",
                    file=sys.stderr,
                )
    return ok


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_list() -> int:
    for artifact in discover_artifacts():
        version = declared_version(artifact)
        print(f"{artifact.name} ({artifact.kind}) {version}")
        for location in artifact.locations:
            print(f"    {location}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bump_version.py",
        description=(
            "Bump or validate the version of one Python package under lib/python/ "
            "or one provider image under providers/workspaces/."
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="validate that every declared version of an artifact agrees",
    )
    parser.add_argument(
        "--check-release",
        action="store_true",
        help=(
            "validate that a changed artifact's version moved relative to the "
            "release branch. Local preview of .github/workflows/_check-version.yml, "
            "which remains the authority."
        ),
    )
    parser.add_argument(
        "--list", action="store_true", help="list artifacts and their locations"
    )
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE_REF,
        help=f"baseline ref for --check-release (default: {DEFAULT_BASE_REF})",
    )
    parser.add_argument(
        "args",
        nargs="*",
        help="`bump <patch|minor|major> <artifact>`, or artifact names for --check",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)

    modes = [ns.check, ns.check_release, ns.list]
    if sum(1 for mode in modes if mode) > 1:
        parser.error("--check, --check-release and --list are mutually exclusive")

    try:
        if ns.list:
            return cmd_list()
        if ns.check:
            return 0 if check_all(ns.args) else 1
        if ns.check_release:
            return 0 if check_release(ns.args, ns.base) else 1

        if not ns.args or ns.args[0] != "bump":
            parser.print_help()
            return 1
        if len(ns.args) != 3:
            parser.error("usage: bump <patch|minor|major> <artifact>")
        _, part, name = ns.args
        if part not in {"patch", "minor", "major"}:
            parser.error(
                f"unknown version part {part!r}; expected patch, minor or major"
            )
        artifact = find_artifact(name)
        bump_artifact(artifact, part)
        return 0
    except BumpError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
