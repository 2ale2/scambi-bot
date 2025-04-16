import json
import os
import re
from idlelib.window import add_windows_to_menu

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.errors import RPCError
from globals import bot_data
from datetime import datetime
import pytz

from modules.database import add_to_table, get_exchange_infos, decrease_user_points, set_exchange_cancelled, \
    get_user_exchanges
from modules.loggers import db_logger, bot_logger
from modules.utils import save_persistence


async def start(client: Client, message: Message):
    global bot_data
    if not await is_admin(message.from_user.id):
        return

    await message.delete()

    text = (f"🎲 Ciao, {message.from_user.first_name}.\n\n"
            f"🔹 Ecco una lista dei comandi:\n\n"
            f"\t<code>[.!/]scambi [ID/@username]</code> – Elenca gli scambi cui ha preso parte l'utente specificato.\n"
            f"\t<code>[.!/]punti [ID/@username]</code> – Mostra i punti attuali dell'utente specificato.\n\n"
            f"ℹ️ <i>Questo messaggio conferma che il bot ti vede come un admin.</i>")

    await send_message_with_close_button(
        client=client,
        chat_id=message.chat.id,
        message=None,
        text=text
    )


async def exchange(client: Client, message: Message):
    global bot_data
    forwarded = await message.forward(chat_id=os.getenv("DEPOSIT_CHAT_ID"))

    sender = message.from_user

    if message.caption is None:
        text = "⚠️ Ricordati di allegare uno <b>screenshot</b>."
        await send_message_with_close_button(client=client, message=message, text=text)
        return

    pattern = r"[/.!](\w+)(?:\s+(@\w+|(\d{7,})|<a\s+href=\"tg://user\?id=(\d{7,})\">.*?</a>))?\s*(.*)?"

    match = re.match(pattern, message.caption)

    _, mentioned = match.group(1), (match.group(2) or None)
    if mentioned is None:
        text = "⚠️ Indica l'<b>utente</b> con cui hai effettuato lo scambio."
        await send_message_with_close_button(client=client, message=message, text=text)
        return

    user = match.group(3) or match.group(4) or match.group(2)
    feedback = match.group(5) or None
    if feedback is None:
        text = "⚠️ Aggiungi un <b>feedback</b> per assegnare lo scambio."
        await send_message_with_close_button(client=client, message=message, text=text)
        return

    try:
        recipient = await client.get_chat_member(
            chat_id=message.chat.id,
            user_id=user
        )
    except ValueError:
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ Warning\n\n▪️ L'utente sembra non esistere."
        )
        return

    if recipient.user.id == sender.id:
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ Warning\n\n▪️ Tagga l'altro membro con cui hai effettuato lo scambio."
        )
        return

    if recipient.status == "LEFT":
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ Warning\n\n▪️ L'utente non è nel gruppo."
        )
        return

    if recipient.status == "BANNED":
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ Warning\n\n▪️ Non puoi assegnare punti a utenti bannati."
        )
        return

    if recipient.user.is_bot:
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ Warning\n\n▪️ Hai taggato un bot."
        )
        return

    points_sender = await add_to_table(
        table_name="main_table",
        content={
            "user_id": sender.id,
            "username": sender.username
        }
    )

    points_recipient = await add_to_table(
        table_name="main_table",
        content={
            "user_id": recipient.user.id,
            "username": recipient.user.username
        }
    )

    added_id = await add_to_table(
        table_name="exchanges",
        content={
            "member_1": sender.id,
            "member_2": recipient.user.id,
            "feedback": feedback,
            "screenshot": forwarded.link,
            "exchange_time": datetime.now(tz=pytz.timezone("Europe/Rome")).replace(tzinfo=None)
        }
    )

    if points_sender is not None and points_recipient is not None and added_id is not None:
        db_logger.info(msg=f"Wrote Database Correctly (id #{added_id}).")

    if points_sender == 0:
        if added_id not in bot_data:
            bot_data[int(added_id)] = {}
        sent_message = await send_message_with_close_button(
            client=client,
            chat_id=os.getenv("NOTIFICATION_CHAT_ID"),
            message=message,
            text=f"🎯 L'utente {sender.mention} ha ottenuto 6 punti."
        )
        bot_data[int(added_id)]["member_1_gift_notification"] = sent_message.id
        await save_persistence(json.dumps({"jsondata": bot_data}))

    if points_recipient == 0:
        if added_id not in bot_data:
            bot_data[int(added_id)] = {}
        sent_message = await send_message_with_close_button(
            client=client,
            chat_id=os.getenv("NOTIFICATION_CHAT_ID"),
            message=message,
            text=f"🎯 L'utente {recipient.user.mention} ha ottenuto 6 punti."
        )
        bot_data[int(added_id)]["member_2_gift_notification"] = sent_message.id
        await save_persistence(json.dumps({"jsondata": bot_data}))

    text = f"✅ <b>Scambio Registrato Correttamente</b>\n\n"
    if points_sender == 0:
        text += f"🎁 <u><i>Sender</i></u> {message.from_user.mention} (<code>{sender.id}</code>) → 6 (+1)\n"
    else:
        text += f"🔸 <u><i>Sender</i></u> {message.from_user.mention} (<code>{sender.id}</code>) → {points_sender} (+1)\n"

    if points_recipient == 0:
        text += f"🎁 <u><i>Recipient</i></u> {recipient.user.mention} (<code>{recipient.user.id}</code>) → 6 (+1)\n"
    else:
        text += f"🔹 <u><i>Recipient</i></u> {recipient.user.mention} (<code>{recipient.user.id}</code>) → {points_recipient} (+1)\n"

    keyboard = [
        [
            InlineKeyboardButton("🖍 Annulla Scambio", callback_data=f"cancel_exchange_{added_id}")
        ]
    ]

    await client.send_message(
        chat_id=message.chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await message.delete()


async def cancel_exchange(client: Client, callback_query: CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        return
    exchange_infos = await get_exchange_infos(callback_query.data.split("_")[-1])
    points_sender = await decrease_user_points(exchange_infos["member_1"])
    points_recipient = await decrease_user_points(exchange_infos["member_2"])

    if points_sender is None:
        db_logger.error(f"{exchange_infos['member_1']} non trovato!")
        raise Exception(f"{exchange_infos['member_1']} non trovato!")
    if points_recipient is None:
        db_logger.error(f"{exchange_infos['member_2']} non trovato!")
        raise Exception(f"{exchange_infos['member_2']} non trovato!")

    if points_sender == 5:
        await client.delete_messages(
            chat_id=os.getenv("NOTIFICATION_CHAT_ID"),
            message_ids=bot_data[int(exchange_infos["id"])]["member_1_gift_notification"]
        )
    if points_recipient == 5:
        await client.delete_messages(
            chat_id=os.getenv("NOTIFICATION_CHAT_ID"),
            message_ids=bot_data[int(exchange_infos["id"])]["member_2_gift_notification"]
        )

    member_1 = await client.get_chat_member(
        chat_id=callback_query.message.chat.id,
        user_id=exchange_infos["member_1"]
    )

    member_2 = await client.get_chat_member(
        chat_id=callback_query.message.chat.id,
        user_id=exchange_infos["member_2"]
    )

    await set_exchange_cancelled(exchange_infos["id"])

    await send_message_with_close_button(
        client=client,
        message=None,
        chat_id=callback_query.message.chat.id,
        text=f"♻️ Scambio tra {member_1.user.mention} ({points_sender}) "
             f"e {member_2.user.mention} ({points_recipient}) <b>cancellato</b>."
    )

    await callback_query.message.delete()


async def send_message_with_close_button(client: Client, message: Message | None, text: str, chat_id=None):
    if message is None and chat_id is None:
        bot_logger.error("almeno uno tra 'message' e 'chat_id' deve essere definito")
        raise RPCError("almeno uno tra 'message' e 'chat_id' deve essere definito")
    keyboard = [
        [
            InlineKeyboardButton("🚮 Chiudi", callback_data=f"close")
        ]
    ]
    message = await client.send_message(
        chat_id=int(chat_id) if chat_id is not None else message.chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return message


async def user_exchanges(client: Client, message: Message):
    if not await is_admin(message.from_user.id):
        return

    if len(message.command) <= 1:
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ Devi specificare un utente.\n\n"
                 f"<b>Esempio</b>:\n\t<code>/scambi @username</code>\n\t<code>/scambi 7654321</code>"
        )
        return

    user = message.command[1]

    if not user.startswith("@") and not user.isnumeric():
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ Se specifichi un <b>ID</b>, assicurati di <b>non inserire caratteri non numerici</b>. "
                 "Se invece indichi uno <b>username<b>, assicurati di <b>aggiungere \"@\"</b> (es.: "
                 "<code>@username</code>, non <code>username</code>)."
        )
        return

    try:
        tagged = await client.get_chat_member(
            chat_id=os.getenv("GROUP_CHAT_ID"),
            user_id=user
        )
    except RPCError as e:
        bot_logger.error(f"error retrieving user {user} from group: {e}")
        tagged = None
        pass

    if not tagged:
        await send_message_with_close_button(
            client=client,
            message=message,
            text=f"⚠️ L'utente {user} non è stato trovato nel gruppo. Riprova."
        )
        return

    res = await get_user_exchanges(tagged.user.id)
    if res == -1:
        await send_message_with_close_button(
            client=client,
            message=message,
            text="❌ Non è stato possibile interrogare il database."
        )
        return

    if len(res) == 0:
        await send_message_with_close_button(
            client=client,
            message=message,
            text="ℹ️ Sembra che l'utente non abbia fatto alcuno scambio."
        )
        return

    text = f"🔎 <b>Scambi di</b> <code>{tagged.user.mention}</code>\n"
    for count, el in enumerate(res, start=1):
        if count % 6 != 0:
            text += (f"\n{count}. Scambio {dict(el)['id']}\n\n"
                     f"<u>Sender</u>: ")

    # componi il messaggio con gli scambi e invialo


async def is_admin(user_id: int | str) -> bool:
    return int(user_id) in [8101457635, 6710922454, 6602225958]


# serve per evitare eccezioni
# noinspection PyUnusedLocal
async def close_message(client: Client, callback_query: CallbackQuery):
    await callback_query.message.delete()
