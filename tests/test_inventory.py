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


def test_default_port_is_22(tmp_path):
    f = tmp_path / "inv.yml"
    f.write_text("hosts:\n  webserver:\n    ssh_address: 10.0.0.1\n")

    hosts = load_inventory(str(f))

    assert hosts == [Host(name="webserver", address="10.0.0.1")]
