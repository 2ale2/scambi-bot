import os
import asyncio
import logging
import json

import pyrogram.errors
from dotenv import load_dotenv
from pyrogram import Client
from utils import *

bot_data = {}

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
        db_logger.warn("Persistence table was empty. Trying env Group ID.")
        bot_data["group_id"] = os.getenv("GROUP_ID")
        try:
            await app.get_chat_member(bot_data["group_id"], "me")
        except pyrogram.errors.RPCError:
            bot_logger.error("Group ID not actual! Change it in the .env file.")
            exit(1)
        else:
            bot_logger.info("Group ID was correct. Editing DB...")
            await save_persistence(json.dumps(bot_data))
    else:
        res = await conn.execute("SELECT data FROM persistence;")
        bot_data["group_id"] = res

    pass


async def main():
    app = Client(
        "scambi_bot",
        api_id=os.getenv("API_ID"),
        api_hash=os.getenv("API_HASH"),
        bot_token=os.getenv("BOT_TOKEN")
    )
    await post_init(app)


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
