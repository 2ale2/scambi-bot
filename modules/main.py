import os
import logging

from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler

from core import *

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

httpx_logger = logging.getLogger('httpx')
httpx_logger.setLevel(logging.WARNING)


def main():
    application = ApplicationBuilder().token(os.getenv("BOT_TOKEN")).build()

    application.add_handler(
        CommandHandler(
            command="start",
            callback=start
        )
    )

    application.run_polling()


if __name__ == "__main__":
    load_dotenv()
    main()
