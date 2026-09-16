"""
Registre des modules disponibles : {nom: classe}.
"""

from mla.modules.command import Command
from mla.modules.apt import Apt
from mla.modules.copy import Copy
from mla.modules.service import Service
from mla.modules.sysctl import Sysctl
from mla.modules.template import Template

MODULES = {
    Command.name: Command,
    Apt.name: Apt,
    Copy.name: Copy,
    Service.name: Service,
    Sysctl.name: Sysctl,
    Template.name: Template,
}
