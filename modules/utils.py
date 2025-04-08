import logging
import asyncpg
import os

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler

from globals import bot_data
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


async def connect_to_database():
    try:
        conn = await asyncpg.connect(
            host=os.getenv("DB_HOST"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            database=os.getenv("DB_NAME")
        )
    except asyncpg.exceptions.PostgresError as err:
        db_logger.error(err)
        raise
    else:
        return conn
