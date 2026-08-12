import pathlib
import re

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


def test_absent_provider_returns_none():
    assert SessionStoreContract.from_env({}) is None
    assert SessionStoreContract.from_env({Env.PROVIDER: ""}) is None
    assert SessionStoreContract.from_env({Env.PROVIDER: "none"}) is None
    assert SessionStoreContract.from_env({Env.PROVIDER: "NONE"}) is None


def test_full_contract_parses():
    c = SessionStoreContract.from_env({
        Env.PROVIDER: "seshmagic",
        Env.URL: "http://store:8080",
        Env.AUTH: "tok",
        Env.TAGS: "workflow:w1,phase:p2",
        Env.SPOOL: "/spool",
        Env.PARTITION: "w1/p2",
    })
    assert c is not None
    assert c.provider == "seshmagic"
    assert c.url == "http://store:8080"
    assert c.auth == "tok"
    assert c.tags == "workflow:w1,phase:p2"
    assert c.spool == "/spool"
    assert c.partition == "w1/p2"


def test_spool_defaults_and_partition_falls_back_to_hostname():
    c = SessionStoreContract.from_env({
        Env.PROVIDER: "seshmagic",
        Env.URL: "http://store:8080",
        "HOSTNAME": "ctr-abc123",
    })
    assert c is not None
    assert c.spool == "/spool"
    assert c.partition == "ctr-abc123"


def test_url_is_required():
    with pytest.raises(ValueError, match=str(Env.URL)):
        SessionStoreContract.from_env({Env.PROVIDER: "seshmagic"})


@pytest.mark.parametrize("bad", ["../../evil", "a/b", ".hidden", "has space", "semi;colon"])
def test_provider_name_rejects_path_escape(bad):
    with pytest.raises(ValueError, match="provider"):
        SessionStoreContract.from_env({
            Env.PROVIDER: bad,
            Env.URL: "http://store:8080",
        })


@pytest.mark.parametrize("bad", ["../escape", "/absolute", "a/../../b"])
def test_partition_rejects_traversal(bad):
    with pytest.raises(ValueError, match="partition"):
        SessionStoreContract.from_env({
            Env.PROVIDER: "seshmagic",
            Env.URL: "http://store:8080",
            Env.PARTITION: bad,
        })


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
    assert not offenders, "use Env.<NAME> instead of a literal:\n" + "\n".join(offenders)
