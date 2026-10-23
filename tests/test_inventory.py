import pytest

from mla.inventory import Host, InventoryError, load_inventory


def test_missing_file():
    with pytest.raises(InventoryError):
        load_inventory("tests/fixtures/does_not_exist.yml")


def test_invalid_yaml(tmp_path):
    f = tmp_path / "inv.yml"
    f.write_text("hosts: [this is not: valid yaml")
    with pytest.raises(InventoryError):
        load_inventory(str(f))


def test_empty_file(tmp_path):
    f = tmp_path / "inv.yml"
    f.write_text("")
    with pytest.raises(InventoryError):
        load_inventory(str(f))


def test_root_is_not_a_dict(tmp_path):
    f = tmp_path / "inv.yml"
    f.write_text("- webserver\n- bastion\n")
    with pytest.raises(InventoryError):
        load_inventory(str(f))


def test_missing_hosts_key(tmp_path):
    f = tmp_path / "inv.yml"
    f.write_text("autre_chose: {}\n")
    with pytest.raises(InventoryError):
        load_inventory(str(f))


def test_hosts_is_not_a_dict(tmp_path):
    f = tmp_path / "inv.yml"
    f.write_text("hosts: [1, 2]\n")
    with pytest.raises(InventoryError):
        load_inventory(str(f))


def test_host_definition_is_not_a_dict(tmp_path):
    f = tmp_path / "inv.yml"
    f.write_text("hosts:\n  webserver: not-a-dict\n")
    with pytest.raises(InventoryError):
        load_inventory(str(f))


def test_host_missing_ssh_address(tmp_path):
    f = tmp_path / "inv.yml"
    f.write_text("hosts:\n  webserver:\n    ssh_port: 22\n")
    with pytest.raises(InventoryError):
        load_inventory(str(f))


def test_valid_inventory_returns_expected_hosts():
    hosts = load_inventory("tests/fixtures/inventory_ok.yml")

    assert hosts == [
        Host(name="webserver", address="192.168.1.22", port=2222),
        Host(
            name="bastion",
            address="192.168.1.24",
            port=22,
            user="bob",
            password="secret",
        ),
    ]


def test_port_is_none_when_absent(tmp_path):
    # None : ~/.ssh/config puis 22 décident au moment de la connexion
    f = tmp_path / "inv.yml"
    f.write_text("hosts:\n  webserver:\n    ssh_address: 10.0.0.1\n")

    hosts = load_inventory(str(f))

    assert hosts == [Host(name="webserver", address="10.0.0.1")]
    assert hosts[0].port is None


def _inventory_with_port(tmp_path, port_yaml):
    f = tmp_path / "inv.yml"
    f.write_text("hosts:\n  web:\n    ssh_address: 10.0.0.1\n"
                 f"    ssh_port: {port_yaml}\n")
    return str(f)


@pytest.mark.parametrize("port_yaml", ["abc", "0", "65536", "-22", "true",
                                       "2222.5", "[22]"])
def test_invalid_ssh_port_raises(tmp_path, port_yaml):
    with pytest.raises(InventoryError, match="web: invalid ssh_port"):
        load_inventory(_inventory_with_port(tmp_path, port_yaml))


@pytest.mark.parametrize("port_yaml, expected", [("2222", 2222),
                                                 ("'2222'", 2222),
                                                 ("65535", 65535)])
def test_valid_ssh_port_is_an_int(tmp_path, port_yaml, expected):
    hosts = load_inventory(_inventory_with_port(tmp_path, port_yaml))

    assert hosts[0].port == expected
