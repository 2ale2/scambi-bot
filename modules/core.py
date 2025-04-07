import os
import re

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from globals import bot_data
from copy import deepcopy

from modules.database import add_to_table


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
    original_message = deepcopy(message)
    await message.delete()

    sender = original_message.from_user

    if original_message.caption is None:
        text = "⚠️ Ricordati di allegare uno <b>screenshot</b>."
        await send_message_with_close_button(client, original_message, text)
        return

    pattern = r"[/.!](\w+)(?:\s+(@\w+|(\d{7,})|<a\s+href=\"tg://user\?id=(\d{7,})\">.*?</a>))?\s*(.*)?"

    match = re.match(pattern, original_message.caption)

    action = match.group(1)
    mentioned = match.group(2) or None
    if mentioned is None:
        text = "⚠️ Indica l'<b>utente</b> con cui hai effettuato lo scambio."
        await send_message_with_close_button(client, original_message, text)
        return

    user = match.group(3) or match.group(4) or match.group(2)
    feedback = match.group(5) or None
    if feedback is None:
        text = "⚠️ Aggiungi un <b>feedback</b> per assegnare lo scambio."
        await send_message_with_close_button(client, original_message, text)
        return

    try:
        recipient = await client.get_chat_member(
            chat_id=message.chat.id,
            user_id=user
        )
    except ValueError:
        await send_message_with_close_button(
            client=client,
            message=original_message,
            text="⚠️ Warning\n\n▪️ L'utente sembra non esistere."
        )
        return

    if recipient.status == "LEFT":
        await send_message_with_close_button(
            client=client,
            message=original_message,
            text="⚠️ Warning\n\n▪️ L'utente non è nel gruppo."
        )
        return

    if recipient.status == "BANNED":
        await send_message_with_close_button(
            client=client,
            message=original_message,
            text="⚠️ Warning\n\n▪️ Non puoi assegnare punti a utenti bannati."
        )
        return

    reset_sender = await add_to_table(
        table_name="main_table",
        content={
            "user_id": sender.id,
            "username": sender.username
        }
    )

    reset_recipient = await add_to_table(
        table_name="main_table",
        content={
            "user_id": recipient.user.id,
            "username": recipient.user.username
        }
    )

    if reset_sender:
        await client.send_message(
            chat_id=os.getenv("OWNER_ID"), # DA METTERE IL CANALE DELLE NOTIFICHE
            text=f"🎯 L'utente {sender.mention} ha ottenuto 6 punti."
        )

    if reset_recipient:
        await client.send_message(
            chat_id=os.getenv("OWNER_ID"), # DA METTERE IL CANALE DELLE NOTIFICHE
            text=f"🎯 L'utente {reset_recipient.user.mention} ha ottenuto 6 punti."
        )

    await client.send_message(
        chat_id=original_message.chat.id,
        text=f"Comando: {action}\n"
             f"Utente rilevato: {user}\n"
             f"Feedback: <i>{feedback}</i>",
        parse_mode=ParseMode.HTML
    )


async def send_message_with_close_button(client: Client, message: Message, text: str):
    keyboard = [
        [
            InlineKeyboardButton("🚮 Chiudi", callback_data=f"close")
        ]
    ]
    await client.send_message(
        chat_id=message.chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# serve per evitare eccezioni
# noinspection PyUnusedLocal
async def close_message(client: Client, callback_query: CallbackQuery):
    await callback_query.message.delete()
