"""Tests for bump_version.py.

The cases that matter here are the ones that would have caught the incident
the script exists to prevent: a write that does not land, and two locations
that disagree. Both are constructed deliberately below.

Most tests build a synthetic repo in tmp_path rather than touching the real
one, so they can create states (an unwritable file, a disagreeing pair) that
must never exist in the checkout.
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import bump_version as bv

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


PYPROJECT = """\
[build-system]
requires = ["hatchling"]

[project]
name = "demo-package"
version = "{version}"
description = "A demo"

[tool.demo]
version = "not-the-project-version"
"""

INIT_PY = '''\
"""Demo package."""

__version__ = "{version}"
'''

UV_LOCK = """\
version = 1
requires-python = ">=3.11"

[[package]]
name = "demo-package"
version = "{version}"
source = {{ editable = "." }}
"""

MANIFEST = """\
# Demo provider
name: demo-provider
version: "{version}"

toolchain:
  node:
    version: "22"
"""


def make_package(root: Path, version: str = "0.1.0") -> Path:
    """A synthetic lib/python package with all three location kinds."""
    package_dir = root / "lib" / "python" / "demo_package"
    (package_dir / "demo_package").mkdir(parents=True)
    (package_dir / "pyproject.toml").write_text(PYPROJECT.format(version=version))
    (package_dir / "demo_package" / "__init__.py").write_text(
        INIT_PY.format(version=version)
    )
    (package_dir / "uv.lock").write_text(UV_LOCK.format(version=version))
    return package_dir


def make_provider(root: Path, version: str = "1.0.0") -> Path:
    provider_dir = root / "providers" / "workspaces" / "demo-provider"
    provider_dir.mkdir(parents=True)
    (provider_dir / "manifest.yaml").write_text(MANIFEST.format(version=version))
    return provider_dir


def no_lock_refresh(project_dir: Path) -> None:
    """Stand-in for `uv lock` that regenerates nothing.

    Used where the test drives the lock's content itself.
    """


def fake_lock_refresh(target: str):
    """A `uv lock` that rewrites the lock to `target`, without needing uv."""

    def refresh(project_dir: Path) -> None:
        lock = project_dir / "uv.lock"
        lock.write_text(UV_LOCK.format(version=target))

    return refresh


# ---------------------------------------------------------------------------
# Version arithmetic
# ---------------------------------------------------------------------------


class TestNextVersion:
    @pytest.mark.parametrize(
        ("current", "part", "expected"),
        [
            ("0.1.0", "patch", "0.1.1"),
            ("0.1.9", "patch", "0.1.10"),  # rollover, not 0.2.0
            ("0.9.9", "patch", "0.9.10"),
            ("1.2.3", "patch", "1.2.4"),
            ("0.5.1", "minor", "0.6.0"),
            ("0.9.9", "minor", "0.10.0"),  # rollover, not 1.0.0
            ("1.2.3", "minor", "1.3.0"),
            ("0.5.1", "major", "1.0.0"),
            ("1.2.3", "major", "2.0.0"),
            ("9.9.9", "major", "10.0.0"),
        ],
    )
    def test_arithmetic(self, current, part, expected):
        assert bv.next_version(current, part) == expected

    def test_unknown_part_rejected(self):
        with pytest.raises(bv.BumpError):
            bv.next_version("0.1.0", "pathc")

    @pytest.mark.parametrize("bad", ["1.2", "1.2.3-rc1", "v1.2.3", "", "1.2.3.4"])
    def test_non_release_version_rejected(self, bad):
        with pytest.raises(bv.BumpError):
            bv.next_version(bad, "patch")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_finds_every_location_kind(self, tmp_path):
        make_package(tmp_path)
        artifact = bv.find_artifact("demo_package", root=tmp_path)
        kinds = sorted(loc.kind for loc in artifact.locations)
        assert kinds == ["dunder", "lock", "pyproject"]

    def test_finds_downstream_locks(self, tmp_path):
        """A lock outside the package that records its version is a location.

        tests/consumer_contracts/uv.lock is the real instance of this, and CI
        installs it with `uv sync --locked`, so a bump that ignored it would
        break CI.
        """
        make_package(tmp_path)
        downstream = tmp_path / "tests" / "consumer_contracts"
        downstream.mkdir(parents=True)
        (downstream / "uv.lock").write_text(UV_LOCK.format(version="0.1.0"))

        artifact = bv.find_artifact("demo_package", root=tmp_path)
        lock_paths = {loc.path for loc in artifact.locations if loc.kind == "lock"}
        assert downstream / "uv.lock" in lock_paths

    def test_notices_an_init_that_declares_no_version(self, tmp_path, capsys):
        package_dir = make_package(tmp_path)
        (package_dir / "demo_package" / "__init__.py").write_text('"""No version."""\n')

        artifact = bv.find_artifact("demo_package", root=tmp_path)
        assert artifact.silent_candidates  # reported, not silently skipped
        bv.check_artifact(artifact)
        assert "declares no __version__" in capsys.readouterr().out

    def test_unknown_artifact_is_an_error(self, tmp_path):
        make_package(tmp_path)
        with pytest.raises(bv.BumpError, match="unknown artifact"):
            bv.find_artifact("nope", root=tmp_path)

    def test_provider_manifest_is_discovered(self, tmp_path):
        make_provider(tmp_path, "2.0.0")
        artifact = bv.find_artifact("demo-provider", root=tmp_path)
        assert artifact.kind == "provider"
        assert bv.declared_version(artifact) == "2.0.0"


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------


class TestCheck:
    def test_passes_when_locations_agree(self, tmp_path):
        make_package(tmp_path)
        artifact = bv.find_artifact("demo_package", root=tmp_path)
        assert bv.check_artifact(artifact) is True

    def test_fails_when_two_locations_disagree(self, tmp_path, capsys):
        """The state the sed incident left behind, constructed deliberately."""
        package_dir = make_package(tmp_path, "0.1.0")
        (package_dir / "pyproject.toml").write_text(PYPROJECT.format(version="0.1.1"))

        artifact = bv.find_artifact("demo_package", root=tmp_path)
        assert bv.check_artifact(artifact) is False

        err = capsys.readouterr().err
        assert "disagree" in err
        assert "0.1.0" in err and "0.1.1" in err

    def test_fails_when_the_lock_lags_behind(self, tmp_path):
        package_dir = make_package(tmp_path, "0.2.0")
        (package_dir / "uv.lock").write_text(UV_LOCK.format(version="0.1.0"))
        artifact = bv.find_artifact("demo_package", root=tmp_path)
        assert bv.check_artifact(artifact) is False

    def test_ignores_a_version_key_in_another_table(self, tmp_path):
        """[tool.demo] version must not be read as the project version."""
        make_package(tmp_path, "0.3.0")
        artifact = bv.find_artifact("demo_package", root=tmp_path)
        assert bv.declared_version(artifact) == "0.3.0"
        assert bv.check_artifact(artifact) is True


# ---------------------------------------------------------------------------
# bump
# ---------------------------------------------------------------------------


class TestBump:
    def test_updates_every_location(self, tmp_path):
        package_dir = make_package(tmp_path, "0.1.9")
        artifact = bv.find_artifact("demo_package", root=tmp_path)

        target = bv.bump_artifact(
            artifact, "patch", refresh_lock=fake_lock_refresh("0.1.10")
        )

        assert target == "0.1.10"
        # Read back from disk rather than trusting the return value.
        assert 'version = "0.1.10"' in (package_dir / "pyproject.toml").read_text()
        assert (
            '__version__ = "0.1.10"'
            in (package_dir / "demo_package" / "__init__.py").read_text()
        )
        assert 'version = "0.1.10"' in (package_dir / "uv.lock").read_text()
        assert (
            bv.check_artifact(bv.find_artifact("demo_package", root=tmp_path)) is True
        )

    def test_leaves_unrelated_version_keys_alone(self, tmp_path):
        package_dir = make_package(tmp_path)
        artifact = bv.find_artifact("demo_package", root=tmp_path)
        bv.bump_artifact(artifact, "minor", refresh_lock=fake_lock_refresh("0.2.0"))
        assert (
            'version = "not-the-project-version"'
            in (package_dir / "pyproject.toml").read_text()
        )

    def test_provider_manifest_bump_preserves_quoting(self, tmp_path):
        provider_dir = make_provider(tmp_path, "1.0.0")
        artifact = bv.find_artifact("demo-provider", root=tmp_path)
        bv.bump_artifact(artifact, "major", refresh_lock=no_lock_refresh)
        text = (provider_dir / "manifest.yaml").read_text()
        assert 'version: "2.0.0"' in text
        assert 'version: "22"' in text  # the nested toolchain key is untouched

    def test_a_write_that_does_not_land_fails(self, tmp_path, monkeypatch):
        """The incident itself: one file edited, one silently not.

        The pyproject write is turned into a no-op after the pre-flight has
        passed, which is the closest reproduction of BSD sed accepting the
        command and changing nothing. The bump must fail, not report success.
        """
        package_dir = make_package(tmp_path, "0.1.0")
        pyproject = package_dir / "pyproject.toml"
        real_write = bv._write_text

        def sabotaged(path, text):
            if path == pyproject:
                return  # accepted, wrote nothing, said nothing
            real_write(path, text)

        monkeypatch.setattr(bv, "_write_text", sabotaged)

        artifact = bv.find_artifact("demo_package", root=tmp_path)
        with pytest.raises(bv.BumpError, match="did NOT fully apply"):
            bv.bump_artifact(artifact, "patch", refresh_lock=fake_lock_refresh("0.1.1"))

        assert 'version = "0.1.0"' in pyproject.read_text()

    def test_a_lock_that_does_not_refresh_fails(self, tmp_path):
        """`uv lock` succeeding without moving the version is still a failure."""
        make_package(tmp_path, "0.1.0")
        artifact = bv.find_artifact("demo_package", root=tmp_path)
        with pytest.raises(bv.BumpError, match="did NOT fully apply"):
            bv.bump_artifact(artifact, "patch", refresh_lock=no_lock_refresh)

    @pytest.mark.skipif(
        not hasattr(os, "geteuid") or os.geteuid() == 0,
        reason="needs POSIX file permissions and a non-root user",
    )
    def test_an_unwritable_location_fails_before_anything_is_written(self, tmp_path):
        package_dir = make_package(tmp_path, "0.1.0")
        init_py = package_dir / "demo_package" / "__init__.py"
        init_py.chmod(stat.S_IRUSR)
        try:
            artifact = bv.find_artifact("demo_package", root=tmp_path)
            with pytest.raises(bv.BumpError, match="not writable"):
                bv.bump_artifact(
                    artifact, "patch", refresh_lock=fake_lock_refresh("0.1.1")
                )
            # Pre-flight failed, so no location moved.
            assert 'version = "0.1.0"' in (package_dir / "pyproject.toml").read_text()
            assert 'version = "0.1.0"' in (package_dir / "uv.lock").read_text()
        finally:
            init_py.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def test_refuses_to_bump_an_already_inconsistent_package(self, tmp_path):
        package_dir = make_package(tmp_path, "0.1.0")
        (package_dir / "pyproject.toml").write_text(PYPROJECT.format(version="0.2.0"))
        artifact = bv.find_artifact("demo_package", root=tmp_path)
        with pytest.raises(bv.BumpError, match="already disagree"):
            bv.bump_artifact(artifact, "patch", refresh_lock=fake_lock_refresh("0.2.1"))

    def test_a_lock_that_never_mentions_the_distribution_is_not_a_location(
        self, tmp_path
    ):
        package_dir = make_package(tmp_path)
        (package_dir / "uv.lock").write_text(
            'version = 1\n\n[[package]]\nname = "other"\nversion = "9.9.9"\n'
        )
        artifact = bv.find_artifact("demo_package", root=tmp_path)
        assert [loc.kind for loc in artifact.locations] == ["pyproject", "dunder"]
        assert bv.check_artifact(artifact) is True

    def test_refuses_when_the_primary_location_has_no_version(self, tmp_path):
        package_dir = make_package(tmp_path)
        (package_dir / "pyproject.toml").write_text(
            '[project]\nname = "demo-package"\n'
        )
        artifact = bv.find_artifact("demo_package", root=tmp_path)
        with pytest.raises(bv.BumpError, match="no version found"):
            bv.bump_artifact(artifact, "patch", refresh_lock=no_lock_refresh)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli:
    def test_bad_part_is_rejected(self, tmp_path):
        with pytest.raises(SystemExit):
            bv.main(["bump", "sideways", "agentic_logging"])

    def test_mutually_exclusive_modes(self):
        with pytest.raises(SystemExit):
            bv.main(["--check", "--list"])


# ---------------------------------------------------------------------------
# The real repository
# ---------------------------------------------------------------------------


class TestThisRepository:
    def test_check_passes_for_every_artifact(self):
        """Guards the checkout itself: no artifact may have drifting versions."""
        artifacts = bv.discover_artifacts()
        assert artifacts, "discovery found nothing, so this test proves nothing"
        failures = [
            a.name for a in artifacts if not bv.check_artifact(a, verbose=False)
        ]
        assert failures == []

    def test_every_artifact_has_a_parseable_version(self):
        for artifact in bv.discover_artifacts():
            bv.parse_version(bv.declared_version(artifact))

    def test_runs_as_a_script(self):
        result = subprocess.run(
            [sys.executable, "scripts/bump_version.py", "--check"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
