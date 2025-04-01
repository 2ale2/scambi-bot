from pyrogram import Client
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from globals import bot_data


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
    await message.delete()

    sender = message.from_user.id

    if message.caption is None:
        text = "⚠️ Ricordati di allegare uno <b>screenshot</b>."
        await send_message_with_close_button(client, message, text)
        return

    splitted = message.caption.split(maxsplit=2)

    if len(splitted) < 3:
        text = ("⚠️ Usa il <b>formato corretto</b>.\n\n"
                "<code>/scambio @utente feedback</code>\n\n"
                "Ricordati di allegare anche uno screenshot 📸.")
        await send_message_with_close_button(client, message, text)

    # GESTIRE LA MENZIONE SENZA USERNAME
    recipient = await client.get_chat_member(bot_data["group_id"], splitted[1])


async def send_message_with_close_button(client: Client, message: Message, text: str):
    keyboard = [
        [
            InlineKeyboardButton("🚮 Chiudi", callback_data=f"close")
        ]
    ]
    await client.send_message(
        chat_id=message.chat.id,
        text=text,
        parse_mode="html",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def close_message(callback_query: CallbackQuery):
    await callback_query.message.delete()
