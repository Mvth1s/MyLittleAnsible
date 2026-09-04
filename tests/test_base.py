import pytest

from mla.modules.base import BaseModule, ModuleResult


def test_init_stores_params():
    m = BaseModule({"name": "nginx"})
    assert m.params == {"name": "nginx"}


def test_process_not_implemented():
    m = BaseModule({})
    with pytest.raises(NotImplementedError):
        m.process(ssh_client=None)


def test_subclass_can_override_process():
    class DummyModule(BaseModule):
        name = "dummy"

        def process(self, ssh_client):
            return ModuleResult(changed=True)

    result = DummyModule({}).process(ssh_client=None)
    assert result.changed is True
