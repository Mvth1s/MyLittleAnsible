"""Tests du module mla.logger.

Chaque cas s'exécute dans un sous-processus : `configure_logging` ne configure
le logging qu'une fois par process, et `sys.excepthook` ne se déclenche que sur
une exception non rattrapée en haut du programme.
"""

import io
import logging
import os
import re
import subprocess
import sys
import textwrap

import pytest

from mla.logger import (
    LOG_FORMAT,
    REDACTED,
    SafeFormatter,
    escape_newlines,
    flatten,
    redact,
    register_secret,
    truncate_output,
)

# Racine du projet : passée aux sous-processus comme cwd pour qu'ils trouvent
# le paquet `mla`, quel que soit le dossier depuis lequel pytest est lancé.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PY = sys.executable


def _run(code):
    return subprocess.run(
        [PY, "-c", code], capture_output=True, text=True, cwd=ROOT
    )


def test_format_info():
    r = _run(
        "import logging; from mla.logger import configure_logging;"
        " configure_logging(); logging.getLogger().info('hello')"
    )
    pattern = r"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} - root - INFO - hello$"
    assert re.search(pattern, r.stdout.strip()), repr(r.stdout)
    assert r.stderr == "", repr(r.stderr)


def test_debug_level():
    r = _run(
        "import logging; from mla.logger import configure_logging;"
        " configure_logging(debug=True); logging.getLogger().debug('dbg')"
    )
    assert " - DEBUG - dbg" in r.stdout, repr(r.stdout)


def test_error_without_debug_has_no_traceback():
    r = _run(
        "from mla.logger import configure_logging;"
        " configure_logging(); raise ValueError('boom')"
    )
    assert "boom" in r.stdout and "Traceback" not in r.stdout, repr(r.stdout)


def test_error_with_debug_has_traceback():
    r = _run(
        "from mla.logger import configure_logging;"
        " configure_logging(debug=True); raise ValueError('boom')"
    )
    assert "Traceback" in r.stdout and "ValueError: boom" in r.stdout, \
        repr(r.stdout)


def test_keyboard_interrupt_is_native():
    r = _run(
        "from mla.logger import configure_logging;"
        " configure_logging(); raise KeyboardInterrupt"
    )
    assert r.returncode != 0
    assert "KeyboardInterrupt" in r.stderr and "ERROR" not in r.stderr, \
        (r.returncode, repr(r.stderr))


def test_paramiko_logger_is_quiet():
    r = _run(
        "import logging; from mla.logger import configure_logging;"
        " configure_logging();"
        " print(logging.getLogger('paramiko').level)"
    )
    assert r.stdout.strip() == str(logging.WARNING), repr(r.stdout)


def test_paramiko_logger_stays_quiet_in_debug():
    r = _run(
        "import logging; from mla.logger import configure_logging;"
        " configure_logging(debug=True);"
        " print(logging.getLogger('paramiko').level,"
        " logging.getLogger().level)"
    )
    assert r.stdout.split() == [str(logging.WARNING), str(logging.DEBUG)], \
        repr(r.stdout)


def test_truncate_output():
    assert truncate_output(None) == ""
    assert truncate_output("") == ""
    assert truncate_output("  hi\n") == "hi"
    assert len(truncate_output("x" * 500)) == 200


# --- secrets : état global, remis à zéro pour chaque test ----------------


@pytest.fixture(autouse=True)
def no_secrets(monkeypatch):
    monkeypatch.setattr("mla.logger._secrets", set())


def format_record(msg, *args, exc_info=None):
    record = logging.LogRecord("root", logging.INFO, __file__, 1, msg, args,
                               exc_info)
    return SafeFormatter("%(message)s").format(record)


# --- aplatissement ---------------------------------------------------------


def test_flatten_joins_lines_with_pipe():
    text = "Job failed.\n\n  See systemctl status  \r\nfor details\n"

    assert flatten(text) == "Job failed. | See systemctl status | for details"


def test_flatten_empty():
    assert flatten(None) == ""
    assert flatten("\n\n") == ""


def test_truncate_output_flattens_before_truncating():
    out = truncate_output("a\nb\n" + "x" * 500)

    assert out.startswith("a | b | x")
    assert "\n" not in out
    assert len(out) == 200


def test_formatter_flattens_message_and_args():
    out = format_record("host=%s %s", "10.0.0.1",
                        "Job for nginx.service failed.\n"
                        "See 'systemctl status nginx.service'.\n")

    assert out == ("host=10.0.0.1 Job for nginx.service failed. | "
                   "See 'systemctl status nginx.service'.")


def test_escape_newlines_uses_literal_backslash_n():
    out = escape_newlines("touch /tmp/x\ntest -f /tmp/x\r\n\necho ok")

    assert out == "touch /tmp/x\\ntest -f /tmp/x\\n\\necho ok"
    assert "\n" not in out


def test_escape_newlines_single_line_is_unchanged():
    assert escape_newlines("systemctl start nginx") == "systemctl start nginx"


def test_formatter_keeps_escaped_newlines():
    out = format_record("dry run: %s", escape_newlines("a\nb"))

    assert out == "dry run: a\\nb"


def test_formatter_does_not_alter_original_record():
    record = logging.LogRecord("root", logging.INFO, __file__, 1,
                               "a\nb", None, None)
    SafeFormatter("%(message)s").format(record)

    assert record.getMessage() == "a\nb"


# --- masquage des secrets --------------------------------------------------


def test_redact_masks_registered_secrets():
    register_secret("s3cret")
    register_secret(None)
    register_secret("")

    assert redact("printf s3cret | sudo") == f"printf {REDACTED} | sudo"


def test_formatter_masks_secret_in_message():
    register_secret("s3cret")

    assert "s3cret" not in format_record("password is %s", "s3cret")


def test_formatter_masks_secret_in_traceback():
    register_secret("s3cret")
    try:
        raise RuntimeError("printf s3cret | sudo -S")
    except RuntimeError:
        out = format_record("boom", exc_info=sys.exc_info())

    assert "Traceback" in out
    assert "s3cret" not in out
    assert REDACTED in out


def test_truncate_output_masks_secret_cut_by_the_limit():
    register_secret("s3cret")

    out = truncate_output("x" * 197 + "s3cret")

    assert "s3c" not in out


def test_safe_formatter_uses_subject_format():
    handler = logging.StreamHandler(io.StringIO())
    handler.setFormatter(SafeFormatter(LOG_FORMAT))
    record = logging.LogRecord("root", logging.INFO, __file__, 1, "a\nb",
                               None, None)

    assert handler.format(record).endswith(" - root - INFO - a | b")


# --- bout en bout : run_todos en dry-run + --debug, sortie réelle -------


def test_dry_run_end_to_end_on_stdout_with_host_and_no_password():
    code = textwrap.dedent("""
        from unittest.mock import MagicMock

        import mla.modules.apt as apt
        import mla.modules.base as base
        import mla.ssh as ssh
        from mla.inventory import Host
        from mla.logger import configure_logging
        from mla.modules import MODULES
        from mla.ssh import CmdResult
        from mla.todos import Todo, run_todos

        not_installed = lambda cmd, c: CmdResult("", "", 1)
        apt.run_remote_cmd = base.run_remote_cmd = not_installed
        ssh.connect = lambda host: MagicMock()

        configure_logging(debug=True)
        host = Host(name="w", address="10.0.0.1", password="Sup3r-S3cret")
        run_todos([Todo("apt", {"name": "nginx"}),
                   Todo("command", {"command": "echo a\\necho b\\n"})],
                  [host], registry=MODULES, dry_run=True)
    """)
    r = _run(code)

    assert r.returncode == 0, r.stderr
    assert r.stderr == "", repr(r.stderr)
    lines = r.stdout.splitlines()
    assert any(line.endswith(
        "INFO - host=10.0.0.1 dry run: apt-get update -qq && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y nginx")
        for line in lines), r.stdout
    assert any(line.endswith(
        "INFO - host=10.0.0.1 dry run: /bin/bash -c 'echo a\\necho b'")
        for line in lines), r.stdout
    assert "Sup3r-S3cret" not in r.stdout


def test_debug_traceback_never_shows_ssh_password():
    code = textwrap.dedent("""
        from unittest.mock import MagicMock

        import mla.ssh as ssh
        from mla.inventory import Host
        from mla.logger import configure_logging
        from mla.todos import Todo, run_todos

        class Leaky:
            def __init__(self, params):
                pass

            def process(self, ssh_client, dry_run=False,
                        sudo_password=None):
                raise RuntimeError(f"printf {sudo_password} | sudo -S")

        ssh.connect = lambda host: MagicMock()
        configure_logging(debug=True)
        host = Host(name="w", address="10.0.0.1", password="Sup3r-S3cret")
        run_todos([Todo("leaky")], [host], registry={"leaky": Leaky})
    """)
    r = _run(code)

    assert "Traceback" in r.stdout, r.stdout
    assert "RuntimeError: printf ******** | sudo -S" in r.stdout
    assert "Sup3r-S3cret" not in r.stdout + r.stderr
