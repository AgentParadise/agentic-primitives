"""The vendor-neutral provider name and its legacy alias must both resolve.

The adapter directory was renamed from `seshmagic` to `apss` because it
implements APS-V1-0004, not one vendor's store. `seshmagic` stays as a symlink
so existing images and any deployment still setting
AGENTIC_SESSION_STORE_PROVIDER=seshmagic keep working.

The entrypoint resolves a provider by PATH:

    /opt/agentic/capabilities/<capability>/<provider>/init.sh

so the alias is load-bearing at the filesystem level, and a rename that lost it
would break every running deployment silently - the entrypoint's `[ -f ]` test
would simply not find the adapter and the capability would go quiet.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

CAPABILITY = (
    Path(__file__).resolve().parents[4] / "workspace" / "capabilities" / "session-store"
)
SCRIPTS = ("init.sh", "doctor.sh", "finalize.sh")


def test_the_canonical_provider_is_vendor_neutral() -> None:
    assert (CAPABILITY / "apss").is_dir()


def test_the_legacy_name_is_a_symlink_not_a_copy() -> None:
    """A copy would drift: two adapters, one of them quietly stale."""
    legacy = CAPABILITY / "seshmagic"

    assert legacy.is_symlink()
    assert legacy.resolve() == (CAPABILITY / "apss").resolve()


def test_both_names_resolve_to_the_same_scripts() -> None:
    """This is what the entrypoint actually does: build a path and test -f."""
    for script in SCRIPTS:
        canonical = CAPABILITY / "apss" / script
        legacy = CAPABILITY / "seshmagic" / script

        assert canonical.is_file(), f"{script} missing under the canonical name"
        assert legacy.is_file(), f"{script} unreachable through the legacy alias"
        assert canonical.read_bytes() == legacy.read_bytes()


REPO_ROOT = Path(__file__).resolve().parents[4]
BUILD_PROVIDER = REPO_ROOT / "scripts" / "build-provider.py"


def _load_build_provider():
    """Import the build script by path: it is a script, not a package."""
    spec = importlib.util.spec_from_file_location("build_provider", BUILD_PROVIDER)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        pytest.skip("build-provider.py not importable")
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_provider"] = module
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"build-provider.py dependency missing: {exc.name}")
    return module


class TestStagingPreservesTheAlias:
    """The repository tree is NOT what ships. Staging is.

    The first version of this test only inspected workspace/, which passes
    whatever staging does. The real pipeline copies through
    shutil.copytree, whose DEFAULT (symlinks=False) dereferences the link
    into a second real directory. Both provider names still resolve, so
    nothing fails - the images just quietly contain two copies, and the
    "one implementation that cannot drift" guarantee becomes false where it
    actually matters. A test that cannot see that is testing the wrong layer.
    """

    def test_the_staged_tree_keeps_a_symlink_not_a_copy(self, tmp_path: Path) -> None:
        build_provider = _load_build_provider()

        build_provider.stage_workspace_runtime(tmp_path)

        staged = tmp_path / "workspace" / "capabilities" / "session-store"
        legacy = staged / "seshmagic"

        assert legacy.is_symlink(), (
            "staging dereferenced the alias into a real directory; "
            "shutil.copytree needs symlinks=True"
        )
        assert legacy.readlink() == Path("apss")
        assert (legacy / "init.sh").is_file()

    def test_the_staged_alias_is_not_a_second_implementation(
        self, tmp_path: Path
    ) -> None:
        """Editing one must change the other, or they can drift apart."""
        build_provider = _load_build_provider()
        build_provider.stage_workspace_runtime(tmp_path)

        staged = tmp_path / "workspace" / "capabilities" / "session-store"
        canonical = staged / "apss" / "init.sh"
        canonical.write_text("# sentinel\n")

        assert (staged / "seshmagic" / "init.sh").read_text() == "# sentinel\n"


def test_shutil_copytree_still_dereferences_by_default(tmp_path: Path) -> None:
    """Pins the upstream behaviour the staging fix depends on.

    If a future Python changed this default, the symlinks=True argument would
    become redundant rather than wrong - but the reasoning in build-provider.py
    would be stale, and stale reasoning is how a guard gets removed.
    """
    src = tmp_path / "src"
    (src / "real").mkdir(parents=True)
    (src / "real" / "f.txt").write_text("x")
    (src / "alias").symlink_to("real")

    shutil.copytree(src, tmp_path / "dst")

    assert not (tmp_path / "dst" / "alias").is_symlink()
