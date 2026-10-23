import pytest

from mla.modules import MODULES

# valeurs par défaut documentées par le sujet (+ permanent de sysctl)
EXPECTED = {
    "apt": {"state": "present"},
    "copy": {"backup": False},
    "command": {"shell": "/bin/bash"},
    "sysctl": {"permanent": False},
    "service": {},
    "template": {},
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_module_declares_its_defaults(name):
    assert MODULES[name].DEFAULTS == EXPECTED[name]
