"""
Configuration du logging : format horodaté du sujet, secrets masqués,
messages sur une ligne, stack traces seulement en --debug.
"""

import logging
import sys

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
REDACTED = "********"

# valeurs à ne jamais écrire dans un log (mots de passe de l'inventory)
_secrets = set()


def register_secret(value):
    """
    Déclare 'value' comme secret : il sera masqué dans toute sortie de log.
    """
    if value:
        _secrets.add(str(value))


def redact(text):
    """
    Remplace chaque secret déclaré par REDACTED dans 'text'.
    """
    # les plus longs d'abord, au cas où un secret en contient un autre
    for secret in sorted(_secrets, key=len, reverse=True):
        text = text.replace(secret, REDACTED)
    return text


def flatten(text):
    """
    Ramène 'text' sur une seule ligne : lignes non vides jointes par ' | '.
    """
    if not text:
        return ""
    lines = (line.strip() for line in str(text).splitlines())
    return " | ".join(line for line in lines if line)


def escape_newlines(text):
    """
    Remplace chaque retour à la ligne de 'text' par la séquence littérale
    '\\n', pour afficher une commande sur une ligne sans la dénaturer.
    """
    return "\\n".join(str(text).splitlines())


class SafeFormatter(logging.Formatter):
    """
    Formatter du sujet : message aplati sur une ligne et secrets masqués.
    Seule la stack trace (--debug) reste sur plusieurs lignes.
    """

    def format(self, record):
        # copie : ne pas modifier le record vu par les autres handlers
        """
        Formate 'record' sur une ligne, secrets masqués.
        """
        record = logging.makeLogRecord(record.__dict__)
        record.msg = flatten(record.getMessage())
        record.args = None
        return redact(super().format(record))


def configure_logging(debug=False):
    """
    Configure le logger racine : format horodaté du
    sujet sur stdout, niveau DEBUG si debug sinon INFO.
    """

    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SafeFormatter(LOG_FORMAT))
    logging.basicConfig(level=level, handlers=[handler])
    # même en --debug : la trace SSH de paramiko noierait les logs utiles
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    install_excepthook(debug=debug)


def install_excepthook(debug=False):
    """
    Installer le hook d'exception.
    """
    def hook(exc_type, exc_value, exc_tb):
        """
        Hook d'exception : log l'erreur selon le niveau debug ou non.
        """
        if issubclass(exc_type, KeyboardInterrupt):
            # comportement par défaut de Python
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        if debug:
            # trace complète
            logging.error("unhandled exception",
                          exc_info=(exc_type, exc_value, exc_tb))
        else:
            # juste le message
            logging.error("%s", exc_value)
    sys.excepthook = hook


def truncate_output(text, limit=200):
    """
    Retourne au plus 'limit' caractères de 'text', aplati sur une ligne.
    Masque les secrets avant de couper, pour qu'un secret tronqué ne
    puisse pas échapper au masquage.
    """
    return redact(flatten(text))[:limit]
