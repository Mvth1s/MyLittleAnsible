"""
Module Template: rend un template Jinja2 en local avec des variables
et pousse le résultat sur l'hôte.
"""

import hashlib
import logging
import os
import shlex

import jinja2

from mla.modules.base import (
    BaseModule,
    ModuleError,
    ModuleResult,
    upload,
    upload_commands,
)
from mla.modules.copy import local_mode
from mla.ssh import run_remote_cmd

logger = logging.getLogger()


class Template(BaseModule):
    name = "template"

    def _params(self):
        src = self.params.get("src")
        dest = self.params.get("dest")
        vars = self.params.get("vars", {})
        if not src or not dest:
            raise ModuleError(
                "template: src and dest are required"
            )
        if not os.path.exists(src):
            raise ModuleError(
                f"template: src not found: {src}"
            )
        if not isinstance(vars, dict):
            raise ModuleError(
                "template: vars must be a dict"
            )
        return src, dest, vars

    def _render(self, src, vars):
        """
        Lit 'src', rend le template avec 'vars', retourne le texte obtenu.
        Lève ModuleError si le template a une erreur de syntaxe.
        Une variable absente de 'vars' est rendue vide (warning).
        """
        with open(src) as f:
            text = f.read()

        try:
            rendered = jinja2.Template(
                text, undefined=jinja2.make_logging_undefined(
                    logger=logger, base=jinja2.Undefined),
                keep_trailing_newline=True).render(vars)
            return rendered
        except jinja2.TemplateError as exc:
            raise ModuleError(f"template: {exc}")

    def _remote_matches(self, ssh_client, dest, digest):
        """
        Compare 'digest' (sha256 du rendu local) au sha256sum de 'dest'
        côté distant.
        """
        result = run_remote_cmd(
            f"sha256sum {shlex.quote(dest)}", ssh_client)
        if result.exit_code != 0:
            return False
        return result.stdout.split()[0] == digest

    def process(self, ssh_client, dry_run=False, sudo_password=None):
        src, dest, vars = self._params()
        rendered = self._render(src, vars).encode()
        digest = hashlib.sha256(rendered).hexdigest()

        if self._remote_matches(ssh_client, dest, digest):
            return ModuleResult(changed=False)

        mode = local_mode(src)
        if dry_run:
            # le rendu est en mémoire : on affiche le template source
            return ModuleResult(
                changed=True,
                commands=upload_commands([(src, dest, mode)], sudo_password))

        upload(ssh_client, [(rendered, dest, mode)], sudo_password)

        return ModuleResult(changed=True)
