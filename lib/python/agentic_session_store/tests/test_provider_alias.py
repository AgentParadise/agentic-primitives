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

from pathlib import Path

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
