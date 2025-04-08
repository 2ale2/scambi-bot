import os
import re

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from globals import bot_data
from datetime import datetime
import pytz

from modules.database import add_to_table
from modules.loggers import db_logger


async def start(client: Client, message: Message):
    global bot_data
    if message.chat.id == bot_data["owner_id"] or message.chat.id == bot_data["admin_id"]:
        await client.send_message(
            chat_id=message.chat.id,
            text=f"Ciao, {message.from_user.first_name}.\n\n"
                 f"Questo messaggio conferma che il bot ti sta riconoscendo come admin."
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
        await send_message_with_close_button(
            client=client,
            chat_id=os.getenv("NOTIFICATION_CHAT_ID"),  # DA METTERE IL CANALE DELLE NOTIFICHE
            message=message,
            text=f"🎯 L'utente {sender.mention} ha ottenuto 6 punti."
        )

    if points_recipient == 0:
        await send_message_with_close_button(
            client=client,
            chat_id=os.getenv("NOTIFICATION_CHAT_ID"),  # DA METTERE IL CANALE DELLE NOTIFICHE
            message=message,
            text=f"🎯 L'utente {sender.mention} ha ottenuto 6 punti."
        )

    text = f"✅ <b>Scambio Registrato Correttamente</b>\n\n"
    if points_sender == 0:
        text += f"🎁 <u><i>Sender</i></u> {message.from_user.mention} ({sender.id}) 🡒 6 (+1)\n"
    else:
        text += f"🔸 <u><i>Sender</i></u> {message.from_user.mention} ({sender.id}) 🡒 {points_sender} (+1)\n"

    if points_recipient == 0:
        text += f"🎁 <u><i>Recipient</i></u> {recipient.user.mention} ({recipient.user.id}) 🡒 6 (+1)\n"
    else:
        text += f"🔹 <u><i>Recipient</i></u> {recipient.user.mention} ({recipient.user.id}) 🡒 {points_recipient} (+1)\n"

    keyboard = [
        [
            InlineKeyboardButton("🖍 Annulla Scambio", callback_data=f"cancel_exchange_{added_id}"),
            InlineKeyboardButton("🗃 Conferma e Chiudi", callback_data=f"close_exchange_notification"),
        ]
    ]

    await client.send_message(
        chat_id=message.chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await message.delete()


async def send_message_with_close_button(client: Client, message: Message, text: str, chat_id=None):
    keyboard = [
        [
            InlineKeyboardButton("🚮 Chiudi", callback_data=f"close")
        ]
    ]
    await client.send_message(
        chat_id=int(chat_id) if chat_id is not None else message.chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# serve per evitare eccezioni
# noinspection PyUnusedLocal
async def close_message(client: Client, callback_query: CallbackQuery):
    await callback_query.message.delete()
