"""
Registre des modules disponibles : {nom: classe}.
"""

from mla.modules.command import Command
from mla.modules.apt import Apt


MODULES = {
    Command.name: Command,
    Apt.name: Apt,
}
