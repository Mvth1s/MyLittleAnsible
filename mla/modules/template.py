"""
Module Template: rend un template Jinja2 en local avec des variables
et pousse le résultat sur l'hôte.
"""

import hashlib
import os
import shlex

import jinja2
from jinja2 import meta, nodes

from mla.modules.base import (
    BaseModule,
    ModuleError,
    ModuleResult,
    upload,
    upload_commands,
)
from mla.modules.copy import local_mode
from mla.ssh import run_remote_cmd

# filtres et tests qui rendent l'absence d'une variable volontaire
DEFAULT_FILTERS = ("default", "d")
DEFINED_TESTS = ("defined", "undefined")


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

    @staticmethod
    def _read(src):
        """
        Contenu texte du template local 'src'.
        """
        with open(src) as f:
            return f.read()

    def _render(self, src, vars):
        """
        Lit 'src', rend le template avec 'vars', retourne le texte obtenu.
        Une variable absente de 'vars' est rendue vide (voir _missing_vars).
        Lève ModuleError si le template a une erreur de syntaxe ou utilise
        un attribut d'une variable absente.
        """
        try:
            return jinja2.Template(
                self._read(src), keep_trailing_newline=True).render(vars)
        except jinja2.TemplateError as exc:
            raise ModuleError(f"template: {exc}")

    @staticmethod
    def _missing_vars(text, vars):
        """
        Noms triés des variables utilisées par 'text' mais absentes de
        'vars', hors variables protégées par un filtre default ou un test
        'is defined', et hors variables définies par le template lui-même
        (set, for).
        """
        try:
            ast = jinja2.Environment().parse(text)
        except jinja2.TemplateSyntaxError:
            return []  # _render lève déjà l'erreur
        undeclared = meta.find_undeclared_variables(ast)

        protected_nodes = set()
        guarded_names = set()
        for node in ast.find_all(nodes.Filter):
            if node.name in DEFAULT_FILTERS and \
                    isinstance(node.node, nodes.Name):
                protected_nodes.add(id(node.node))
        for node in ast.find_all(nodes.Test):
            if node.name in DEFINED_TESTS and \
                    isinstance(node.node, nodes.Name):
                guarded_names.add(node.node.name)

        used = {n.name for n in ast.find_all(nodes.Name)
                if n.ctx == "load" and id(n) not in protected_nodes}
        return sorted((used & undeclared) - guarded_names - set(vars))

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
        warnings = [
            f"template variable '{name}' is undefined (rendered empty)"
            for name in self._missing_vars(self._read(src), vars)]

        if self._remote_matches(ssh_client, dest, digest):
            return ModuleResult(changed=False, warnings=warnings)

        mode = local_mode(src)
        if dry_run:
            # le rendu est en mémoire : on affiche le template source
            return ModuleResult(
                changed=True,
                commands=upload_commands([(src, dest, mode)], sudo_password),
                warnings=warnings)

        upload(ssh_client, [(rendered, dest, mode)], sudo_password)

        return ModuleResult(changed=True, warnings=warnings)
