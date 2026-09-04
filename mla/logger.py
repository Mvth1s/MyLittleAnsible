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


class HostLoggerAdapter(logging.LoggerAdapter):
    """
    Logger qui préfixe les messages par 'host=<ip>'.
    """
    def process(self, msg, kwargs):
        """
        Préfixe le message avec 'host=<ip>'.
        """
        return f"host={self.extra['host']} {msg}", kwargs


def get_host_logger(host):
    """
    Retourne un logger lié à l'adresse 'host'.
    """
    return HostLoggerAdapter(logging.getLogger(), {"host": host})
