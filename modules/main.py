import os
import logging
import json
from utils import db_logger, bot_logger, save_persistence, add_handlers, connect_to_database
from database import is_table_empty

from pyrogram import Client
import asyncio

import pyrogram.errors
from dotenv import load_dotenv
from globals import bot_data

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

httpx_logger = logging.getLogger('httpx')
httpx_logger.setLevel(logging.WARNING)


async def post_init(app: Client):
    global bot_data
    conn = await connect_to_database()

    if await is_table_empty():
        await conn.execute("INSERT INTO persistence (data) VALUES (DEFAULT);")
        db_logger.warning("Persistence table was empty. Trying env Group ID.")
        bot_data["group_id"] = os.getenv("GROUP_ID")
        try:
            await app.get_chat_member(int(bot_data["group_id"]), "me")
        except pyrogram.errors.RPCError:
            bot_logger.error("Group ID not actual! Change it in the .env file.")
            exit(1)
        else:
            bot_logger.info("Group ID was correct. Editing DB...")
            for el in ["owner_id", "admin_id"]:
                if (el_id := os.getenv(el.upper())) is not None:
                    bot_data[el] = int(el_id)

            await save_persistence(json.dumps({"jsondata": bot_data}))
    else:
        res = await conn.fetch("SELECT data FROM persistence;")
        data = json.loads(next(res[0].values()))["jsondata"]
        for el in ["group_id", "owner_id", "admin_id"]:
            bot_data[el] = int(data[el]) if el in data else int(os.getenv(el.upper()))

    await add_handlers(app)


async def main():
    app = Client(
        "scambi_bot",
        api_id=os.getenv("API_ID"),
        api_hash=os.getenv("API_HASH"),
        bot_token=os.getenv("BOT_TOKEN")
    )

    async with app:
        await post_init(app)
        await asyncio.Event().wait()


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
