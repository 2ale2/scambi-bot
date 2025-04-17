import logging
import os
from logging.handlers import RotatingFileHandler

db_logger = logging.getLogger("dblogger")
db_logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = RotatingFileHandler(os.path.join("logs", "database.log"), maxBytes=10000000, backupCount=0)
file_handler.setFormatter(formatter)
db_logger.addHandler(file_handler)

bot_logger = logging.getLogger("dblogger")
bot_logger.setLevel(logging.INFO)
file_handler = RotatingFileHandler(os.path.join("logs", "bot.log"), maxBytes=10000000, backupCount=0)
file_handler.setFormatter(formatter)
bot_logger.addHandler(file_handler)