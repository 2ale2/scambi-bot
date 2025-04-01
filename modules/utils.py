import json
import logging
import os

import asyncpg

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


async def is_table_empty():
    conn = await connect_to_database()
    try:
        count = await conn.fetchval("SELECT count(*) FROM persistence;")
    except asyncpg.exceptions.PostgresError as err:
        db_logger.error(err)
        raise
    else:
        if count == 1:
            res = await conn.fetch("SELECT data FROM persistence;")
            if len(json.loads(next(res[0].values()))["jsondata"]) == 0:
                # noinspection SqlWithoutWhere
                await conn.execute("DELETE FROM persistence;")
                return True
        await conn.close()
        return count == 0
    

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
        CallbackQueryHandler(
            callback=core.close_message,
            filters=filters.regex(r"^close:")
        )
    )
