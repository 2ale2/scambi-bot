import asyncpg
import os

from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from loggers import db_logger
from globals import bot_data
import core


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
            filters=filters.command(
                commands="start",
                prefixes=list(".!/")
            )
        )
    )

    app.add_handler(
        MessageHandler(
            callback=core.exchange,
            filters=filters.command(
                commands="feedback",
                prefixes=list(".!/")
            )
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            callback=core.close_message,
            filters=filters.regex(r"^close.*")
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            callback=core.cancel_exchange,
            filters=filters.regex(r"^cancel_exchange.*")
        )
    )

    app.add_handler(
        MessageHandler(
            callback=core.user_exchanges,
            filters=filters.command(
                commands="scambi",
                prefixes=list(".!/")
            )
        )
    )

    app.add_handler(
        MessageHandler(
            callback=core.user_points,
            filters=filters.command(
                commands="punti",
                prefixes=list(".!/")
            )
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
