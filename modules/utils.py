import json
import asyncpg
import os
from pyrogram import Client
from pyrogram.enums import ChatType
from pyrogram.errors import MessageDeleteForbidden
from pyrogram.types import Message, ChatMember
from loggers import db_logger, bot_logger
from globals import bot_data


async def save_persistence(json_dict: dict):
    if "confirmations" in json_dict:
        del json_dict["confirmations"]
    json_content = json.dumps({"jsondata": json_dict})
    conn = await connect_to_database()
    try:
        # noinspection SqlWithoutWhere
        await conn.execute("UPDATE persistence SET data = $1;", json_content)
    except asyncpg.exceptions.PostgresError as err:
        db_logger.error(err)
    finally:
        await conn.close()


async def is_admin(user_id: int | str) -> bool:
    return int(user_id) in [538590507, 8101457635, 6710922454, 6602225958]


async def safe_delete(client, message):
    try:
        await message.delete()
    except MessageDeleteForbidden:
        bot_logger.error("❌ Il bot non ha i permessi per cancellare il messaggio.")
    except Exception as e:
        bot_logger.error(f"❌ Altro errore durante la cancellazione: {e}")


async def safety_check(client: Client, message: Message):
    if message.chat.type == ChatType.PRIVATE:
        return await is_admin(message.from_user.id)

    elif message.chat.id == int(os.getenv("GROUP_ID")):
        return True

    text = ("⚠️ <b>Attenzione</b>\n\n"
            "È stato mandato un messaggio su un altro gruppo e il bot è stato in grado di vederlo; questo "
            "significa che <b>molto probabilmente il bot è stato aggiunto in un'altra chat</b> (vedi sotto).\n\n"
            f"Chat: {message.chat.title} ({str(message.chat.id)})\n")
    if message.chat.invite_link is not None:
        text += f"Invite link: {message.chat.invite_link}\n"
    text += f"User ID: {str(message.from_user.id)}\n"
    if message.from_user.username is not None:
        text += f"Username: {message.from_user.username}\n"
    text += f"Message: {message.text}\n\n"

    try:
        await client.leave_chat(message.chat.id)
        text += "✅ Il bot è automaticamente uscito da tale chat.\n\n"
    except Exception as e:
        bot_logger.error("❌ Non è stato possibile uscire da tale chat: " + str(e))
        text += "❌ Non è stato possibile uscire da tale chat: " + str(e)
    try:
        sender = await client.get_chat_member(
            chat_id=os.getenv("GROUP_ID"),
            user_id=message.from_user.id
        )
        if not isinstance(sender, ChatMember):
            raise Exception
    except Exception:
        text += "\n\nSembra che tale utente non sia nel gruppo ufficiale."
    finally:
        bot_logger.warning(text)
        try:
            await client.send_message(
                chat_id=bot_data["admin_id"],
                text=text
            )
        except Exception as e:
            bot_logger.error(f"Non è stato possibile mandare il messaggio all'admin {e}")
        finally:
            return False


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
