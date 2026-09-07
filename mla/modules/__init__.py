"""
Registre des modules disponibles : {nom: classe}.
"""

from mla.modules.command import Command
from mla.modules.apt import Apt
from mla.modules.copy import Copy


MODULES = {
    Command.name: Command,
    Apt.name: Apt,
    Copy.name: Copy,
}
