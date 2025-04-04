import logging

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler

from globals import bot_data
from database import *
import core

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


async def save_persistence(json_content: str):
    conn = await connect_to_database()
    try:
        # noinspection SqlWithoutWhere
        await conn.execute("UPDATE persistence SET data = $1;", json_content)
    except asyncpg.exceptions.PostgresError as err:
        db_logger.error(err)
    finally:
        await conn.close()


async def add_handlers(app: Client):
    app.add_handler(
        MessageHandler(
            callback=core.start,
            filters=filters.command("start")
        )
    )

    app.add_handler(
        MessageHandler(
            callback=core.exchange,
            filters=filters.command("feedback")
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            callback=core.close_message,
            filters=filters.regex(r"^close.*")
        )
    )
