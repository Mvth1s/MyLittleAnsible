"""Tests du module mla.logger.

Chaque cas s'exécute dans un sous-processus : `configure_logging` ne configure
le logging qu'une fois par process, et `sys.excepthook` ne se déclenche que sur
une exception non rattrapée en haut du programme.
"""

import logging
import os
import re
import subprocess
import sys

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
    assert re.search(pattern, r.stderr.strip()), repr(r.stderr)


def test_host_prefix():
    r = _run(
        "from mla.logger import configure_logging, get_host_logger;"
        " configure_logging();"
        " get_host_logger('1.2.3.4').info('op=apt status=OK')"
    )
    assert "host=1.2.3.4 op=apt status=OK" in r.stderr, repr(r.stderr)


def test_debug_level():
    r = _run(
        "import logging; from mla.logger import configure_logging;"
        " configure_logging(debug=True); logging.getLogger().debug('dbg')"
    )
    assert " - DEBUG - dbg" in r.stderr, repr(r.stderr)


def test_error_without_debug_has_no_traceback():
    r = _run(
        "from mla.logger import configure_logging;"
        " configure_logging(); raise ValueError('boom')"
    )
    assert "boom" in r.stderr and "Traceback" not in r.stderr, repr(r.stderr)


def test_error_with_debug_has_traceback():
    r = _run(
        "from mla.logger import configure_logging;"
        " configure_logging(debug=True); raise ValueError('boom')"
    )
    assert "Traceback" in r.stderr and "ValueError: boom" in r.stderr, \
        repr(r.stderr)


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


def test_truncate_output():
    from mla.logger import truncate_output

    assert truncate_output(None) == ""
    assert truncate_output("") == ""
    assert truncate_output("  hi\n") == "hi"
    assert len(truncate_output("x" * 500)) == 200
