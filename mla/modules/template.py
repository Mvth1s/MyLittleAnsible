"""
Module Template: rend un template Jinja2 en local avec des variables
et pousse le résultat sur l'hôte.
"""

import hashlib
import io
import jinja2
import logging
import os
import shlex

from mla.modules.base import BaseModule, ModuleError, ModuleResult
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

    def process(self, ssh_client, dry_run=False):
        src, dest, vars = self._params()
        rendered = self._render(src, vars)
        digest = hashlib.sha256(rendered.encode()).hexdigest()

        if self._remote_matches(ssh_client, dest, digest):
            return ModuleResult(changed=False)

        if dry_run:
            logger.info("dry run : template %s -> %s", src, dest)
            return ModuleResult(changed=True)

        parent = os.path.dirname(dest)
        run_remote_cmd(f"mkdir -p {shlex.quote(parent)}", ssh_client)

        sftp = ssh_client.open_sftp()
        file_obj = io.BytesIO(rendered.encode())
        sftp.putfo(file_obj, dest)
        sftp.close()

        return ModuleResult(changed=True)
