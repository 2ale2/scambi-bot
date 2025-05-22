import os
import re
import locale

from pyrogram import Client
from pyrogram.enums import ParseMode, ChatMemberStatus, ChatType
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ChatMemberUpdated
from pyrogram.errors import RPCError
from globals import bot_data, soglia
from datetime import datetime
import pytz

from modules.database import add_to_table, get_item_infos, decrease_user_points, set_as_cancelled, \
    get_user_exchanges, get_user_points, retrieve_user, get_user_gifts
from modules.loggers import db_logger, bot_logger
from modules.utils import save_persistence, safe_delete, is_admin, safety_check


async def intercept_user_join(client: Client, chat_member: ChatMemberUpdated):
    if (
            chat_member.new_chat_member and
            not (
                    chat_member.new_chat_member.status == ChatMemberStatus.LEFT or
                    chat_member.new_chat_member.status == ChatMemberStatus.BANNED
            )
    ) and chat_member.new_chat_member.user.username is not None:
        res = await add_to_table(
            table_name="users",
            content={
                "user_id": chat_member.new_chat_member.user.id,
                "username": chat_member.new_chat_member.user.username
            }
        )
        if res is None:
            db_logger.error(f"error adding user {chat_member.from_user.id} to table")


async def intercept_user_message(client: Client, message: Message):
    if not await safety_check(client, message):
        return
    if message.from_user.username is not None:
        res = await add_to_table(
            table_name="users",
            content={
                "user_id": message.from_user.id,
                "username": message.from_user.username
            }
        )
        if res is None:
            db_logger.error(f"error adding user {message.from_user.id} to table")


async def start(client: Client, message: Message):
    global bot_data
    await safe_delete(message)

    if not message.chat.type == ChatType.PRIVATE:
        return

    await safety_check(client, message)

    if not await is_admin(message.from_user.id):
        text = "❌ Non sei admin."
    else:
        text = (f"🎲 Ciao, {message.from_user.first_name}.\n\n"
                f"🔹 Ecco una lista dei comandi:\n\n"
                f"\t<code>[.!/]scambi [ID/@username]</code> – Elenca gli scambi cui ha preso parte l'utente specificato"
                f".\n\t<code>[.!/]punti [ID/@username]</code> – Mostra i punti attuali dell'utente specificato.\n\n"
                f"🏆 <b>Soglia Punti Attuale</b>: <code>{soglia}</code>\n\n"
                f"ℹ️ <i>Questo messaggio conferma che il bot ti vede come un admin.</i>\n\n"
                f"<i>made by @Mera86 e @prof_layton</i>")

    await send_message_with_close_button(
        client=client,
        chat_id=message.chat.id,
        message=None,
        text=text
    )


async def send_confirmation_request(client: Client, message: Message, user: str, gift_bool=False):
    global bot_data
    sender = message.from_user.id
    if not gift_bool:
        keyboard = [
            [
                InlineKeyboardButton(
                    text="🖋 Conferma Scambio",
                    callback_data=f"confirm_exchange_{sender}_{user.replace('@', '')}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🖍 Annulla Scambio",
                    callback_data=f"close_admin_{user.replace('@', '')}"
                )
            ]
        ]
        text = (f"⏳ <b>Attesa Conferma</b>\n\n🔹️Questo scambio <u>necessita di conferma</u> da parte dell'utente "
                f"{user}.")
    else:
        keyboard = [
            [
                InlineKeyboardButton(
                    text="🖋 Conferma Regalo",
                    callback_data=f"confirm_gift_{sender}_{user.replace('@', '')}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🖍 Annulla Regalo",
                    callback_data=f"close_admin_gift_{user.replace('@', '')}"
                )
            ]
        ]
        text = (f"⏳ <b>Attesa Conferma</b>\n\n🔹️Questo regalo <u>necessita di conferma</u> da parte dell'utente "
                f"{user}.")

    if "confirmations" not in bot_data:
        bot_data["confirmations"] = {}

    if (user.replace("@", "") in bot_data["confirmations"] and
            "gift" in bot_data["confirmations"][user.replace("@", "")]):
        try:
            confirm_message = await client.get_messages(
                chat_id=message.chat.id,
                message_ids=bot_data["confirmations"][user.replace("@", "")]["gift"].id
            )
        except Exception:
            pass
        else:
            await confirm_message.reply_text(
                text=f"⚠️ L'utente {'@' + user.replace("@", "")} deve <b>ancora confermare un'altro regalo</b>.\n\n"
                     f"🆘 Se il messaggio della richiesta di conferma è stato rimosso o non produce alcun effetto, "
                     f"chiedi ad un admin di cancellare il messaggio cui sto rispondendo, poi riformula la "
                     f"richiesta usando il comando /gift.",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🚮 Chiudi", callback_data=f"close")]])
            )
            return

    try:
        await message.reply_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        bot_logger.error(f"error sending confirmation request: {e}")
        return

    bot_data["confirmations"][user.replace("@", "")] = {"gift": message}
    return


async def exchange(client: Client, message: Message):
    global bot_data
    if not await safety_check(client, message):
        await safe_delete(message)
        return

    sender = message.from_user

    if message.caption is None:
        await safe_delete(message)
        text = "⚠️ Ricordati di allegare uno <b>screenshot</b>."
        await send_message_with_close_button(client=client, message=message, text=text)
        return

    pattern = r"[/.!](\w+)(?:\s+(@\w+|(\d{7,})|<a\s+href=\"tg://user\?id=(\d{7,})\">.*?</a>))?\s*(.*)?"

    match = re.match(pattern, message.caption)

    _, mentioned = match.group(1), (match.group(2) or None)
    if mentioned is None:
        await safe_delete(message)
        text = "⚠️ Indica l'<b>utente</b> con cui hai effettuato lo scambio."
        await send_message_with_close_button(client=client, message=message, text=text)
        return

    user = match.group(3) or match.group(4) or match.group(2)
    feedback = match.group(5) or None
    if feedback is None:
        await safe_delete(message)
        text = "⚠️ Aggiungi un <b>feedback</b> per assegnare lo scambio."
        await send_message_with_close_button(client=client, message=message, text=text)
        return

    try:
        recipient = await client.get_chat_member(
            chat_id=message.chat.id,
            user_id=user
        )
    except Exception:
        if not user.isnumeric():
            recipient = await retrieve_user(user)
            if not recipient:
                await send_confirmation_request(message=message, user=user)
                return
            else:
                try:
                    recipient = await client.get_chat_member(
                        chat_id=int(os.getenv("GROUP_ID")),
                        user_id=dict(recipient[0])["user_id"]
                    )
                except Exception:
                    await send_confirmation_request(message=message, user=user)
                    return
        else:
            await send_confirmation_request(message=message, user=user)
            return

    if recipient.user.id == sender.id:
        await safe_delete(message)
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ <b>Warning</b>\n\n▪️ Tagga l'altro membro con cui hai effettuato lo scambio."
        )
        return

    if recipient.status == "LEFT":
        await safe_delete(message)
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ <b>Warning</b>\n\n▪️ L'utente non è nel gruppo."
        )
        return

    if recipient.status == "BANNED":
        await safe_delete(message)
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ <b>Warning</b>\n\n▪️ Non puoi assegnare punti a utenti bannati."
        )
        return

    if recipient.user.is_bot:
        await safe_delete(message)
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ <b>Warning</b>\n\n▪️ Hai taggato un bot."
        )
        return

    forwarded = await message.forward(chat_id=int(os.getenv("DEPOSIT_CHAT_ID")))

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
            "username_1": sender.username,
            "username_2": recipient.user.username,
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
            chat_id=int(os.getenv("NOTIFICATION_CHAT_ID")),
            message=message,
            text=f"🎯 L'utente {sender.mention} ha ottenuto {soglia} punti."
        )
        bot_data[int(added_id)]["member_1_gift_notification"] = sent_message.id
        await save_persistence(bot_data)

    if points_recipient == 0:
        if added_id not in bot_data:
            bot_data[int(added_id)] = {}
        sent_message = await send_message_with_close_button(
            client=client,
            chat_id=int(os.getenv("NOTIFICATION_CHAT_ID")),
            message=message,
            text=f"🎯 L'utente {recipient.user.mention} ha ottenuto {soglia} punti."
        )
        bot_data[int(added_id)]["member_2_gift_notification"] = sent_message.id
        await save_persistence(bot_data)

    text = f"✅ <b>Scambio Registrato Correttamente</b>\n\n"
    if points_sender == 0:
        text += f"🎁 <u><i>Sender</i></u> {message.from_user.mention} (<code>{sender.id}</code>) → {soglia} (+1)\n"
    else:
        text += (f"🔸 <u><i>Sender</i></u> {message.from_user.mention} (<code>{sender.id}</code>) → {points_sender}"
                 f" (+1)\n")

    if points_recipient == 0:
        text += f"🎁 <u><i>Recipient</i></u> {recipient.user.mention} (<code>{recipient.user.id}</code>) → {soglia} (+1)\n"
    else:
        text += (f"🔹 <u><i>Recipient</i></u> {recipient.user.mention} (<code>{recipient.user.id}</code>) → "
                 f"{points_recipient} (+1)\n")

    keyboard = [
        [
            InlineKeyboardButton("🖍 Annulla Scambio", callback_data=f"cancel_exchange_{added_id}")
        ],
        [
            InlineKeyboardButton("🗂 Conferma e Chiudi", callback_data="confirm_and_close")
        ]
    ]

    await client.send_message(
        chat_id=message.chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await safe_delete(message)


async def gift(client: Client, message: Message):
    global bot_data
    if not await safety_check(client, message):
        await safe_delete(message)
        return

    sender = message.from_user

    if message.caption is None:
        await safe_delete(message)
        text = "⚠️ Ricordati di allegare uno <b>screenshot</b>."
        await send_message_with_close_button(client=client, message=message, text=text)
        return

    pattern = r"[/.!](\w+)(?:\s+(@\w+|(\d{7,})|<a\s+href=\"tg://user\?id=(\d{7,})\">.*?</a>))?"

    match = re.match(pattern, message.caption.html)

    _, mentioned = match.group(1), (match.group(2) or None)
    if mentioned is None:
        await safe_delete(message)
        text = "⚠️ Indica l'<b>utente</b> a cui hai donato il regalo."
        await send_message_with_close_button(client=client, message=message, text=text)
        return

    user = match.group(3) or match.group(4) or match.group(2)

    try:
        recipient = await client.get_chat_member(
            chat_id=message.chat.id,
            user_id=user
        )
    except Exception:
        if not user.isnumeric():
            recipient = await retrieve_user(user)
            if not recipient:
                await send_confirmation_request(client=client, message=message, user=user, gift_bool=True)
                return
            else:
                try:
                    recipient = await client.get_chat_member(
                        chat_id=int(os.getenv("GROUP_ID")),
                        user_id=dict(recipient[0])["user_id"]
                    )
                except Exception:
                    await send_confirmation_request(client=client, message=message, user=user, gift_bool=True)
                    return
        else:
            await send_confirmation_request(client=client, message=message, user=user, gift_bool=True)
            return

    if recipient.user.id == sender.id:
        await safe_delete(message)
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ <b>Warning</b>\n\n▪️ Tagga l'utente a cui stai facendo la donazione."
        )
        return

    if recipient.status == "LEFT":
        await safe_delete(message)
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ <b>Warning</b>\n\n▪️ L'utente non è nel gruppo."
        )
        return

    if recipient.status == "BANNED":
        await safe_delete(message)
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ <b>Warning</b>\n\n▪️ Non donare ad utenti bannati."
        )
        return

    if recipient.user.is_bot:
        await safe_delete(message)
        await send_message_with_close_button(
            client=client,
            message=message,
            text="⚠️ <b>Warning</b>\n\n▪️ Hai taggato un bot."
        )
        return

    forwarded = await message.forward(chat_id=int(os.getenv("DEPOSIT_CHAT_ID")))

    added_id = await add_to_table(
        table_name="gifts",
        content={
            "user_id": sender.id,
            "username": sender.username,
            "gifted_id": recipient.user.id,
            "gifted_username": recipient.user.username,
            "screenshot": forwarded.link
        }
    )

    keyboard = [
        [
            InlineKeyboardButton("🖍 Annulla Regalo", callback_data=f"cancel_gift_{added_id}")
        ],
        [
            InlineKeyboardButton("🗂 Conferma e Chiudi", callback_data="confirm_and_close")
        ]
    ]

    text = f"🎁 Regalo da {sender.mention} a {recipient.user.mention} <b>correttamente registrato</b>!"

    await client.send_message(
        chat_id=message.chat.id,
        text=text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await safe_delete(message)


async def request_gift(client: Client, message: Message):
    global bot_data
    if not await safety_check(client, message):
        await safe_delete(message)
        return

    gifts = await get_user_gifts(user=message.from_user.id)

    if len(gifts["given"]) == 0 and len(gifts["received"]) >= 2:
        await client.send_message(
            chat_id=message.chat.id,
            text=f"⚠️ <b>Warning</b>\n\n🔸 <b>{message.from_user.mention} ha già ricevuto 2 regali</b>. "
                 "Per poterne chiedere un altro, deve prima farne almeno uno.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚮 Chiudi – Solo Admin", callback_data="close_admin")]
            ])
        )
        await safe_delete(message)
        return

    if len(gifts["given"]) > 0:
        last_given = gifts["given"][0]

        valid_received = [
            dict(item) for item in gifts["received"] if dict(item)["given_at"] > dict(last_given)["given_at"]
        ]

        if len(valid_received) >= 2:
            await client.send_message(
                chat_id=message.chat.id,
                text=f"⚠️ <b>Warning</b>\n\n🔸 <b>{message.from_user.mention} ha già ricevuto 2 regali da quando ha "
                     f"fatto l'ultimo regalo</b>. Per poterne chiedere un altro, deve prima farne almeno uno.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚮 Chiudi – Solo Admin", callback_data="close_admin")]
                ])
            )
            await safe_delete(message)
            return

        await client.send_message(
            chat_id=message.chat.id,
            text=f"🃏 <b>Richiesta Regalo</b>\n\n🔹 {message.from_user.mention} sta richiedendo un <b>nuovo regalo</b>.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚮 Chiudi – Solo Admin", callback_data="close_admin")]
            ])
        )
        await safe_delete(message)



async def cancel_gift(client: Client, callback_query: CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        return

    gift_id = callback_query.data.split("_")[-1]
    gift_infos = await get_item_infos(table="gifts", identifier=gift_id)

    sender = await client.get_chat_member(
        chat_id=callback_query.message.chat.id,
        user_id=gift_infos["username"] if gift_infos["username"] else gift_infos["user_id"]
    )

    recipient = await client.get_chat_member(
        chat_id=callback_query.message.chat.id,
        user_id=gift_infos["gifted_username"] if gift_infos["gifted_username"] else gift_infos["gifted_id"]
    )

    await set_as_cancelled(table="gifts", identifier=gift_id)
    await send_message_with_close_button(
        client=client,
        message=None,
        chat_id=callback_query.message.chat.id,
        text=f"🌪 Regalo da {sender.user.mention} a {recipient.user.mention} <b>cancellato</b> correttamente."
    )

    await safe_delete(callback_query.message)


async def confirm_exchange(client: Client, callback_query: CallbackQuery):
    if (callback_query.from_user.username is None or
            callback_query.from_user.username != callback_query.data.split("_", maxsplit=3)[-1]):
        return
    message = None
    for el in bot_data["confirmations"]:
        message = bot_data["confirmations"][el]
        if message.from_user.id == int(callback_query.data.split("_", maxsplit=3)[-2]):
            break
        message = None

    if message is None:
        bot_data.error(msg="confirm_exchange: message not found")
        return
    message = bot_data["confirmations"][callback_query.data.split("_", maxsplit=3)[-1]]
    forwarded = await message.forward(chat_id=int(os.getenv("DEPOSIT_CHAT_ID")))
    sender = message.from_user
    recipient = callback_query.from_user

    await add_to_table(
        table_name="user",
        content={
            "user_id": recipient.id,
            "username": recipient.username
        }
    )

    await callback_query.message.delete()

    pattern = r"[/.!](\w+)(?:\s+(@\w+|(\d{7,})|<a\s+href=\"tg://user\?id=(\d{7,})\">.*?</a>))?\s*(.*)?"

    match = re.match(pattern, message.caption)

    # ho già controllare se feedback è None (non lo è)

    feedback = match.group(5)

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
            "user_id": recipient.id,
            "username": recipient.username
        }
    )

    added_id = await add_to_table(
        table_name="exchanges",
        content={
            "member_1": sender.id,
            "member_2": recipient.id,
            "username_1": sender.username,
            "username_2": recipient.username,
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
            chat_id=int(os.getenv("NOTIFICATION_CHAT_ID")),
            message=message,
            text=f"🎯 L'utente {sender.mention} ha ottenuto {soglia} punti."
        )
        bot_data[int(added_id)]["member_1_gift_notification"] = sent_message.id
        await save_persistence(bot_data)

    if points_recipient == 0:
        if added_id not in bot_data:
            bot_data[int(added_id)] = {}
        sent_message = await send_message_with_close_button(
            client=client,
            chat_id=int(os.getenv("NOTIFICATION_CHAT_ID")),
            message=message,
            text=f"🎯 L'utente {recipient.mention} ha ottenuto {soglia} punti."
        )
        bot_data[int(added_id)]["member_2_gift_notification"] = sent_message.id
        await save_persistence(bot_data)

    text = f"✅ <b>Scambio Registrato Correttamente</b>\n\n"
    if points_sender == 0:
        text += f"🎁 <u><i>Sender</i></u> {message.from_user.mention} (<code>{sender.id}</code>) → {soglia} (+1)\n"
    else:
        text += (f"🔸 <u><i>Sender</i></u> {message.from_user.mention} (<code>{sender.id}</code>) → {points_sender}"
                 f" (+1)\n")

    if points_recipient == 0:
        text += f"🎁 <u><i>Recipient</i></u> {recipient.mention} (<code>{recipient.id}</code>) → {soglia} (+1)\n"
    else:
        text += (f"🔹 <u><i>Recipient</i></u> {recipient.mention} (<code>{recipient.id}</code>) → {points_recipient}"
                 f" (+1)\n")

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

    del bot_data["confirmations"][callback_query.from_user.username.replace('@', '')]
    await safe_delete(message)


async def cancel_exchange(client: Client, callback_query: CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        return
    exchange_infos = await get_item_infos(table="exchanges", identifier=callback_query.data.split("_")[-1])
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
            chat_id=int(os.getenv("NOTIFICATION_CHAT_ID")),
            message_ids=bot_data[int(exchange_infos["id"])]["member_1_gift_notification"]
        )
    if points_recipient == 5:
        await client.delete_messages(
            chat_id=int(os.getenv("NOTIFICATION_CHAT_ID")),
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

    await set_as_cancelled(table="exchanges", identifier=exchange_infos["id"])

    await send_message_with_close_button(
        client=client,
        message=None,
        chat_id=callback_query.message.chat.id,
        text=f"♻️ Scambio tra {member_1.user.mention} ({points_sender}) "
             f"e {member_2.user.mention} ({points_recipient}) <b>cancellato</b>."
    )

    await callback_query.message.delete()


async def send_message_with_close_button(client: Client,
                                         message: Message | None,
                                         text: str,
                                         chat_id=None):
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
    await safe_delete(message)
    if not await safety_check(client, message):
        await send_message_with_close_button(
            client=client,
            message=message,
            text="❌ Non sei admin."
        )
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

    locale.setlocale(locale.LC_TIME, 'it_IT.UTF-8')

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
            chat_id=int(os.getenv("GROUP_ID")),
            user_id=int(user) if user.isnumeric() else str(user)
        )
    except KeyError as e:
        bot_logger.error(f"error retrieving user {user} from group: {e}")
        await send_message_with_close_button(
            client=client,
            message=message,
            text=f"⚠️ Non ho potuto trovare l'utente <code>{user}</code>. Riprova."
        )
        return
    except Exception:
        tagged = None

    res = await get_user_exchanges(user=str(tagged.user.id) if tagged is not None else str(user).removeprefix('@'))

    if res == -1:
        await send_message_with_close_button(
            client=client,
            message=message,
            text="❌ Non è stato possibile interrogare il database."
        )
        return

    user_text = user if not user.isnumeric() else f'<code>{user}</code>'

    if len(res) == 0:
        await send_message_with_close_button(
            client=client,
            message=message,
            text=f"ℹ️ Sembra che l'utente {user_text} non abbia fatto alcuno scambio."
        )
        return

    text = f"🔎 <b>Scambi di {tagged.user.mention if tagged is not None else user} ({len(res)})</b>\n"
    for count, el in enumerate(res, start=1):
        try:
            sender = await client.get_chat_member(
                chat_id=int(os.getenv("GROUP_ID")),
                user_id=dict(el)['member_1']
            )
        except Exception:
            sender = None
        try:
            recipient = await client.get_chat_member(
                chat_id=int(os.getenv("GROUP_ID")),
                user_id=dict(el)['member_2']
            )
        except Exception:
            recipient = None
        if count % 6 != 0:
            text += f"\n🧩. <b>Scambio {dict(el)['id']}</b>\n\n\t🔹 <u>Sender</u> – "
            if sender is not None and (sender.status.name != "LEFT" and sender.status.name != "BANNED"):
                text += f"{sender.user.mention} (<code>{dict(el)['member_1']}</code>)"
            else:
                text += f"<code>{dict(el)['member_1']}</code>"
            if tagged is not None:
                if sender is not None:
                    if tagged.user.id == sender.user.id:
                        text += " 🔖"
                else:
                    if tagged.user.id == int(dict(el)['member_1']):
                        text += " 🔖"
            else:
                if sender is not None:
                    if user.isnumeric():
                        if int(user) == sender.user.id:
                            text += " 🔖"
                    else:
                        if sender.user.username is not None:
                            if user == sender.user.username:
                                text += " 🔖"
                        elif user == '@' + dict(el)['username_1']:
                            text += " 🔖"
                else:
                    if user.isnumeric():
                        if int(user) == int(dict(el)['member_1']):
                            text += " 🔖"
                    else:
                        if user == '@' + dict(el)['username_1']:
                            text += " 🔖"

            text += "\n\t🔸 <u>Recipient</u> – "
            if recipient is not None and (recipient.status.name != "LEFT" and recipient.status.name != "BANNED"):
                text += f"{recipient.user.mention} (<code>{dict(el)['member_2']}</code>)"
            else:
                text += f"<code>{dict(el)['member_2']}</code>"
            if tagged is not None:
                if recipient is not None:
                    if tagged.user.id == recipient.user.id:
                        text += " 🔖"
                else:
                    if tagged.user.id == int(dict(el)['member_2']):
                        text += " 🔖"
            else:
                if recipient is not None:
                    if user.isnumeric():
                        if int(user) == recipient.user.id:
                            text += " 🔖"
                    else:
                        if recipient.user.username is not None:
                            if user == recipient.user.username:
                                text += " 🔖"
                        elif user == '@' + dict(el)['username_2']:
                            text += " 🔖"
                else:
                    if user.isnumeric():
                        if int(user) == int(dict(el)['member_2']):
                            text += " 🔖"
                    else:
                        if user == '@' + dict(el)['username_2']:
                            text += " 🔖"
            text += f"\n\t🔹 <u>Feedback</u> – <i>{dict(el)['feedback']}</i>"
            text += f"\n\t🔸 <u>Screenshot</u> – 🔗 <a href=\"{dict(el)['screenshot']}\">Link</a>"
            text += f"\n\t🔹 <u>Exchange Time</u> – {dict(el)['exchange_time'].strftime('%a %d %b %Y, %H:%M')}"
            text += f"\n\t🔸 <u>Cancelled</u> – <code>{dict(el)['cancelled']}</code>\n"
        else:
            await send_message_with_close_button(
                client=client,
                message=message,
                text=text + "\n\n🆘 Usa il tuo <b>bot di moderazione</b> per maggiori info sugli utenti citati."
            )
            text = f"\n🧩. <b>Scambio {dict(el)['id']}</b>\n\n\t🔹 <u>Sender</u> – "
            if sender is not None and (sender.status.name != "LEFT" and sender.status.name != "BANNED"):
                text += f"{sender.user.mention} (<code>{dict(el)['member_1']}</code>)"
            else:
                text += f"<code>{dict(el)['member_1']}</code>"
            if tagged is not None:
                if sender is not None:
                    if tagged.user.id == sender.user.id:
                        text += " 🔖"
                else:
                    if tagged.user.id == dict(el)['member_1']:
                        text += " 🔖"
            else:
                if sender is not None:
                    if user.isnumeric():
                        if user == sender.user.id:
                            text += " 🔖"
                    else:
                        if sender.user.username is not None:
                            if user == sender.user.username:
                                text += " 🔖"
                        elif user == '@' + dict(el)['username_1']:
                            text += " 🔖"
                else:
                    if user.isnumeric():
                        if int(user) == dict(el)['member_1']:
                            text += " 🔖"
                    else:
                        if user == '@' + dict(el)['username_1']:
                            text += " 🔖"

            text += "\n\t🔸 <u>Recipient</u> – "
            if recipient is not None and (recipient.status.name != "LEFT" and recipient.status.name != "BANNED"):
                text += f"{recipient.user.mention} (<code>{dict(el)['member_2']}</code>)"
            else:
                text += f"<code>{dict(el)['member_2']}</code>"
            if tagged is not None:
                if recipient is not None:
                    if tagged.user.id == recipient.user.id:
                        text += " 🔖"
                else:
                    if tagged.user.id == dict(el)['member_2']:
                        text += " 🔖"
            else:
                if recipient is not None:
                    if user.isnumeric():
                        if user == recipient.user.id:
                            text += " 🔖"
                    else:
                        if recipient.user.username is not None:
                            if user == recipient.user.username:
                                text += " 🔖"
                        elif user == '@' + dict(el)['username_2']:
                            text += " 🔖"
                else:
                    if user.isnumeric():
                        if int(user) == dict(el)['member_2']:
                            text += " 🔖"
                    else:
                        if user == '@' + dict(el)['username_2']:
                            text += " 🔖"
            text += f"\n\t🔹 <u>Feedback</u> – <i>{dict(el)['feedback']}</i>"
            text += f"\n\t🔸 <u>Screenshot</u> – 🔗 <a href=\"{dict(el)['screenshot']}\">Link</a>"
            text += f"\n\t🔹 <u>Exchange Time</u> – {dict(el)['exchange_time'].strftime('%a %d %b %Y, %H:%M')}"
            text += f"\n\t🔸 <u>Cancelled</u> – <code>{dict(el)['cancelled']}</code>\n"

    await send_message_with_close_button(
        client=client,
        message=message,
        text=text + "\n\n🆘 Usa il tuo <b>bot di moderazione</b> per maggiori info sugli utenti citati."
    )


async def user_points(client: Client, message: Message):
    await safe_delete(message)
    if not await safety_check(client, message):
        if message.chat.type == ChatType.PRIVATE:
            await send_message_with_close_button(
                client=client,
                message=message,
                text="❌ Non sei admin. Puoi usare <code>/punti</code> nel gruppo per conoscere il tuo punteggio."
            )
            return
        res = await get_user_points(message.from_user.id)
        if len(res) == 0:
            await send_message_with_close_button(
                client=client,
                message=message,
                text="⚠️ Non ti ho trovato nel database (🎯 <b>0</b> punti)."
            )
            return

        res = res[0]

        text = f"🎯 Hai <b>{dict(res)['points']}</b> punti (🎰 Totale: <b>{dict(res)['total']}</b>)."

        await send_message_with_close_button(
            client=client,
            message=message,
            text=text
        )
        return

    if len(message.command) <= 1:
        user = str(message.from_user.id)
    else:
        user = message.command[1]

    try:
        tagged = await client.get_chat_member(
            chat_id=int(os.getenv("GROUP_ID")),
            user_id=int(user) if user.isnumeric() else str(user)
        )
    except KeyError as e:
        bot_logger.error(f"error retrieving user {user} from group: {e}")
        await send_message_with_close_button(
            client=client,
            message=message,
            text=f"⚠️ Non ho potuto trovare l'utente <code>{user}</code>. Riprova."
        )
        return
    except Exception:
        tagged = None

    if tagged is not None:
        res = await get_user_points(str(tagged.user.id))
    else:
        res = await get_user_points(str(user).removeprefix('@'))

    if len(res) == 0:
        if len(message.command) > 1:
            text = ("⚠️ <b>Non ho trovato l'utente nel database</b>.\n\n"
                     "🆘 Se hai usato uno username, prova col relativo user ID.")
        else:
            text = "⚠️ Non ti ho trovato nel database (🎯 <b>0</b> punti)."
        await send_message_with_close_button(
            client=client,
            message=message,
            text=text
        )
        return

    res = res[0]

    text = "🎯 Punti utente "

    if tagged is not None:
        if (username := tagged.user.username) or (username := dict(res)['username']):
            text += (f"@{username} (<code>{tagged.user.id}</code>): "
                     f"<b>{dict(res)['points']}</b> (🎰 Totale: <b>{dict(res)['total']}</b>)")
        else:
            text += (f"<code>{tagged.user.id}</code>: "
                     f"<b>{dict(res)['points']}</b> (🎰 Totale: <b>{dict(res)['total']}</b>)"
                     f"\n\n🆘 Usa il tuo <b>bot di moderazione</b> per maggiori info sugli utenti citati.")
    else:
        if user.isnumeric():
            if (username := dict(res)['username']) is not None:
                text += (f"@{username} (<code>{user}</code>): <b>{dict(res)['points']}</b> "
                         f"(🎰 Totale: <b>{dict(res)['total']}</b>)\n\n"
                         f"🆘 Usa il tuo <b>bot di moderazione</b> per maggiori info sugli utenti citati.")
            else:
                text += (f"<code>{user}</code>: <b>{dict(res)['points']}</b> "
                         f"(🎰 Totale: <b>{dict(res)['total']}</b>)\n\n"
                         f"🆘 Usa il tuo <b>bot di moderazione</b> per maggiori info sugli utenti citati.")
        else:
            text += (f"{user}: <b>{dict(res)['points']}</b> "
                     f"(🎰 Totale: <b>{dict(res)['total']}</b>)\n\n"
                     f"🆘 Usa il tuo <b>bot di moderazione</b> per maggiori info sugli utenti citati.")

    await send_message_with_close_button(
        client=client,
        message=message,
        text=text
    )


# serve per evitare eccezioni
# noinspection PyUnusedLocal
async def close_message(client: Client, callback_query: CallbackQuery):
    global bot_data
    if callback_query.data.startswith("close_admin"):
        if not await is_admin(callback_query.from_user.id):
            return
        if user := (callback_query.data.split("_", maxsplit=3)[-1]):
            if "confirmations" in bot_data and user in bot_data["confirmations"]:
                del bot_data["confirmations"][user]
        await safe_delete(callback_query.message)
    elif callback_query.data.startswith("confirm_and_close"):
        if await is_admin(callback_query.from_user.id):
            await safe_delete(callback_query.message)
    else:
        await safe_delete(callback_query.message)
