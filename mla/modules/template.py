"""
Module Template: rend un template Jinja2 en local avec des variables
et pousse le résultat sur l'hôte.
"""


import jinja2
import logging
import os
from datetime import datetime

from mla.modules.base import BaseModule, ModuleError, ModuleResult

logger = logging.getLogger()


class Template(BaseModule):
    name = "template"

    def _params(self):
        src = self.params.get("src")
        dest = self.params.get("dest")
        vars = self.params.get("vars", {})
        if not src or not dest:
            raise ModuleError(
                "template: src et dest sont obligatoires"
            )
        if not os.path.exists(src):
            raise ModuleError(
                f"template: src introuvable : {src} "
            )
        if not isinstance(vars, dict):
            raise ModuleError(
                "template: vars doit être un dictionnaire"
            )
        return src, dest, vars

    def _render(self, src, vars):
        """
        Lit 'src', rend le template avec 'vars', retourne le texte obtenu.
        Lève ModuleError si le template a une erreur de syntaxe ou
        référence une variable absente de 'vars'.
        """
        with open(src) as f:
            text = f.read()

        try:
            rendered = jinja2.Template(
                text, undefined=jinja2.StrictUndefined).render(vars)
            return rendered
        except jinja2.TemplateError as exc:
            raise ModuleError(f"template : {exc}")
