import logging
logging.basicConfig(level=logging.INFO)

def configure_logging():
    """
    Configure a simple console logger with the givel level.
    A usecase is to change the formatting of the default handler of the root logger.
    """
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger = logger or logging.getLogger()
    logger.setLevel(level)
    # If the logger has handlers, we configure the first one. Otherwise we add a handler and configure it
    if logger.handlers:
        console = logger.handlers[0]
    else:
        console = logging.StreamHandler()
        logger.addHandler(console)
    console.setFormatter(formatter)
    console.setLevel(level)