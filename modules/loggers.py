import logging
import os

db_logger = logging.getLogger("dblogger")
db_logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler = logging.FileHandler(os.path.join("logs", "database.log"))
file_handler.setFormatter(formatter)
db_logger.addHandler(file_handler)

bot_logger = logging.getLogger("dblogger")
bot_logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(os.path.join("logs", "bot.log"))
file_handler.setFormatter(formatter)
bot_logger.addHandler(file_handler)