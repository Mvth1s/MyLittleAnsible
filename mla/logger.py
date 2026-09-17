import logging
import sys

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


def configure_logging(debug=False):
    """
    Configure le logger racine : format horodaté du
    sujet, niveau DEBUG si debug sinon INFO.
    """

    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT)
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
            logging.error("exception non gérée",
                          exc_info=(exc_type, exc_value, exc_tb))
        else:
            # juste le message
            logging.error("%s", exc_value)
    sys.excepthook = hook


def truncate_output(text, limit=200):
    """
    Retourne au plus 'limit' caractères de 'text'.
    """
    if not text:
        return ""
    return text.strip()[:limit]
