import logging

LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'


def configure_logging(debug=False):
    """
    Configure le logger racine : format horodaté du
    sujet, niveau DEBUG si debug sinon INFO.
    """

    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT)
