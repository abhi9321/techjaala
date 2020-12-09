import logging


def loggers(log_path):
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s  %(name)s  %(levelname)s  %(message)s',
                        filename=log_path,
                        filemode='a')
    logging.info('-----logging initialized-----')
