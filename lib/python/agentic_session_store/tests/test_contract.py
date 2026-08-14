import pathlib
import re
import subprocess

import pytest
from agentic_session_store.contract import (
    CAPABILITY,
    Env,
    SessionStoreContract,
    capability_env_name,
)


def test_env_names_follow_the_adr_038_rule():
    """Every name in Env must match AGENTIC_<CAP>_<FIELD>.

    This is what keeps the enum honest: a typo'd literal in Env fails here
    rather than silently reading a variable nobody sets.
    """
    for member in Env:
        assert member == capability_env_name(CAPABILITY, member.name), (
            f"{member.name} = {member!s} violates the AGENTIC_<CAP>_<FIELD> rule"
        )


# --- ADR-040 shell/Python naming conformance ---------------------------------

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
ENTRYPOINT_SH = REPO_ROOT / "workspace" / "entrypoint.sh"
_SHELL_FN = re.compile(r"__capability_env_prefix\(\)\s*\{.*?\n\}", re.DOTALL)


def _shell_capability_env_name(capability: str, field: str) -> str:
    """Run the *actual* `__capability_env_prefix` from entrypoint.sh in a
    bash subprocess and combine it with `field`.

    This is the conformance test ADR-040 and this module's docstring claim
    exists: `__capability_env_prefix` (shell) and `capability_env_name()`
    (Python) are two implementations of one naming rule, and this pins them
    together instead of re-deriving the shell logic in Python, which would
    only test Python against itself.
    """
    source = ENTRYPOINT_SH.read_text()
    match = _SHELL_FN.search(source)
    assert match, f"__capability_env_prefix() not found in {ENTRYPOINT_SH}"
    script = f'{match.group(0)}\n__capability_env_prefix "$1"\n'
    result = subprocess.run(
        ["bash", "-c", script, "bash", capability],
        capture_output=True,
        text=True,
        check=True,
    )
    return f"{result.stdout.strip()}_{field}"


@pytest.mark.parametrize(
    "capability", ["memory", "session-store", "multi-hyphen-cap-name"]
)
def test_shell_and_python_env_naming_agree(capability):
    """ADR-040's `AGENTIC_<CAP>_<FIELD>` rule has two implementations:
    `__capability_env_prefix` in entrypoint.sh and `capability_env_name()`
    here. They must produce identical names or a capability's doctor
    or init.sh silently reads the wrong variable.
    """
    assert _shell_capability_env_name(capability, "PROVIDER") == capability_env_name(
        capability, "PROVIDER"
    )


def test_absent_provider_returns_none():
    assert SessionStoreContract.from_env({}) is None
    assert SessionStoreContract.from_env({Env.PROVIDER: ""}) is None
    assert SessionStoreContract.from_env({Env.PROVIDER: "none"}) is None
    assert SessionStoreContract.from_env({Env.PROVIDER: "NONE"}) is None


def test_full_contract_parses():
    c = SessionStoreContract.from_env(
        {
            Env.PROVIDER: "seshmagic",
            Env.URL: "http://store:8080",
            Env.AUTH: "tok",
            Env.TAGS: "workflow:w1,phase:p2",
            Env.SPOOL: "/spool",
            Env.PARTITION: "w1/p2",
        }
    )
    assert c is not None
    assert c.provider == "seshmagic"
    assert c.url == "http://store:8080"
    assert c.auth == "tok"
    assert c.tags == "workflow:w1,phase:p2"
    assert c.spool == "/spool"
    assert c.partition == "w1/p2"


def test_spool_defaults_and_partition_falls_back_to_hostname():
    c = SessionStoreContract.from_env(
        {
            Env.PROVIDER: "seshmagic",
            Env.URL: "http://store:8080",
            "HOSTNAME": "ctr-abc123",
        }
    )
    assert c is not None
    assert c.spool == "/spool"
    assert c.partition == "ctr-abc123"


def test_url_is_required():
    with pytest.raises(ValueError, match=str(Env.URL)):
        SessionStoreContract.from_env({Env.PROVIDER: "seshmagic"})


@pytest.mark.parametrize(
    "bad", ["../../evil", "a/b", ".hidden", "has space", "semi;colon"]
)
def test_provider_name_rejects_path_escape(bad):
    with pytest.raises(ValueError, match="provider"):
        SessionStoreContract.from_env(
            {
                Env.PROVIDER: bad,
                Env.URL: "http://store:8080",
            }
        )


@pytest.mark.parametrize("bad", ["relative/path", "../escape", "/spool/../etc"])
def test_spool_rejects_non_absolute_or_traversing(bad):
    """The spool is the root of the tree the adapter creates, symlinks into
    and sweeps, so a relative or traversing value has to fail here rather
    than resolve to something unexpected inside the container.

    PARTITION is supplied so the failure is unambiguously the spool's: with
    it absent the partition check would raise first on some orderings.
    """
    with pytest.raises(ValueError, match="spool"):
        SessionStoreContract.from_env(
            {
                Env.PROVIDER: "seshmagic",
                Env.URL: "http://store:8080",
                Env.SPOOL: bad,
                Env.PARTITION: "w/p",
            }
        )


def test_spool_accepts_a_plain_absolute_path():
    c = SessionStoreContract.from_env(
        {
            Env.PROVIDER: "seshmagic",
            Env.URL: "http://store:8080",
            Env.SPOOL: "/spool",
            Env.PARTITION: "w/p",
        }
    )
    assert c is not None and c.spool == "/spool"


def test_empty_spool_is_unset_not_invalid():
    """An empty string is how an unset var arrives from a shell export, so
    it takes the default rather than failing validation. This matches the
    _clean() semantics every other field in this contract already uses.
    """
    c = SessionStoreContract.from_env(
        {
            Env.PROVIDER: "seshmagic",
            Env.URL: "http://store:8080",
            Env.SPOOL: "",
            Env.PARTITION: "w/p",
        }
    )
    assert c is not None and c.spool == "/spool"


@pytest.mark.parametrize("bad", ["../escape", "/absolute", "a/../../b"])
def test_partition_rejects_traversal(bad):
    with pytest.raises(ValueError, match="partition"):
        SessionStoreContract.from_env(
            {
                Env.PROVIDER: "seshmagic",
                Env.URL: "http://store:8080",
                Env.PARTITION: bad,
            }
        )


# --- Credentials in the URL are refused, not carried -------------------------

URL_SECRET = "hunter2-store-write"  # a test fixture, not a real credential


@pytest.mark.parametrize(
    "bad_url",
    [
        f"https://user:{URL_SECRET}@store.example",
        f"https://{URL_SECRET}@store.example",
        f"http://store.example/?token={URL_SECRET}",
        f"http://store.example/healthz#{URL_SECRET}",
        "http://store.example/#",
        "http://store.example/?",
    ],
)
def test_url_carrying_credentials_is_rejected(bad_url):
    """Userinfo, a query string, or a fragment in the store URL is a hard
    contract failure rather than a value the workspace carries around.

    This is the reject half of the reject-versus-redact decision recorded on
    URL_CREDENTIAL_MESSAGE: there is exactly one supported place for the store
    credential, so a URL carrying one is a misconfiguration with a specific
    fix, and refusing it once is an invariant a test can hold where redacting
    at every present and future print site is not.

    The last two cases carry no secret at all: an empty-but-present fragment
    or query parses to a falsy field, so a check on the parsed fields alone
    would let that shape through.
    """
    with pytest.raises(ValueError) as excinfo:
        SessionStoreContract.from_env(
            {
                Env.PROVIDER: "seshmagic",
                Env.URL: bad_url,
                Env.PARTITION: "w1/p2",
            }
        )
    message = str(excinfo.value)
    # The message is the trap this exists to avoid: it reaches stderr AND the
    # durable doctor audit file, so it must name no part of the value.
    assert URL_SECRET not in message, message
    assert bad_url not in message, message
    assert "store.example" not in message, message
    assert str(Env.URL) in message


def test_ordinary_url_still_parses():
    """The rejection must not catch the URLs operators actually configure."""
    c = SessionStoreContract.from_env(
        {
            Env.PROVIDER: "seshmagic",
            Env.URL: "https://store.internal:8443/api",
            Env.PARTITION: "w1/p2",
        }
    )
    assert c is not None and c.url == "https://store.internal:8443/api"


PKG = pathlib.Path(__file__).resolve().parent.parent / "agentic_session_store"
LITERAL = re.compile(r'"AGENTIC_SESSION_STORE_[A-Z_]+"')


def test_no_env_name_literals_outside_the_enum():
    """Only contract.py's Env block may spell these names as literals."""
    offenders = []
    for path in PKG.rglob("*.py"):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if not LITERAL.search(line):
                continue
            # The Env class body is the one legal home for these literals.
            if path.name == "contract.py" and any(
                line.strip().startswith(f"{m.name} =") for m in Env
            ):
                continue
            offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, "use Env.<NAME> instead of a literal:\n" + "\n".join(
        offenders
    )
