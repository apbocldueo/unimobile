import os
import logging


# set logger
def setup_logging(log_file="app.log", log_level=logging.INFO):
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    formatter = logging.Formatter("%(message)s - %(asctime)s - %(name)s - %(levelname)s")
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.addHandler(file_handler)


    return logger