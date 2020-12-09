import logging
import os

from utilities.loggers import loggers

log = logging.getLogger(__name__)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
log_path = os.path.join(ROOT_DIR,'..', 'test.log')
log.info(f' check the status in logs : {log_path}')
loggers(log_path)
