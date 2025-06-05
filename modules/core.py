import os
import re
import locale

from pyrogram import Client
from pyrogram.enums import ParseMode, ChatMemberStatus, ChatType
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ChatMemberUpdated
from pyrogram.errors import RPCError
from globals import bot_data, SOGLIA, THREAD_ID, THREAD_LINK
from datetime import datetime
import pytz

from modules.database import add_to_table, get_item_infos, decrease_user_points, set_as_cancelled, \
    get_user_exchanges, get_user_points, retrieve_user, get_user_gifts, execute_query_for_value
from modules.loggers import db_logger, bot_logger
from modules.utils import save_persistence, safe_delete, is_admin, safety_check, delete_user_unaccepted_requests, \
    check_request_requirements


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
                f"🏆 <b>Soglia Punti Attuale</b>: <code>{SOGLIA}</code>\n\n"
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
            text=f"🎯 L'utente {sender.mention} ha ottenuto {SOGLIA} punti."
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
            text=f"🎯 L'utente {recipient.user.mention} ha ottenuto {SOGLIA} punti."
        )
        bot_data[int(added_id)]["member_2_gift_notification"] = sent_message.id
        await save_persistence(bot_data)

    text = f"✅ <b>Scambio Registrato Correttamente</b>\n\n"
    if points_sender == 0:
        text += f"🎁 <u><i>Sender</i></u> {message.from_user.mention} (<code>{sender.id}</code>) → {SOGLIA} (+1)\n"
    else:
        text += (f"🔸 <u><i>Sender</i></u> {message.from_user.mention} (<code>{sender.id}</code>) → {points_sender}"
                 f" (+1)\n")

    if points_recipient == 0:
        text += f"🎁 <u><i>Recipient</i></u> {recipient.user.mention} (<code>{recipient.user.id}</code>) → {SOGLIA} (+1)\n"
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


async def request_gift(client: Client, message: Message):
    global bot_data

    if message.message_thread_id is None or message.message_thread_id != THREAD_ID:
        await safe_delete(message)
        await client.send_message(
            chat_id=message.chat.id,
            text = f"ℹ️ Ciao {message.from_user.mention}. Questo non è il topic adibito alla richiesta di regali.\n\n"
                   f"🧭 <b>Per poter formulare una richiesta, recati nel <a href=\"{THREAD_LINK}\">topic corretto</a></b>.",
            parse_mode=ParseMode.HTML,
            message_thread_id=message.message_thread_id
        )
        return

    if not await safety_check(client, message):
        await safe_delete(message)
        return

    if message.caption is None:
        text = "⚠️ Ricordati di allegare uno <b>screenshot</b>."
        await send_message_with_close_button(client=client, message=message, text=text, thread_id=THREAD_ID)
        return

    if not message.media.PHOTO:
        text = "⚠️ Puoi allegare solo uno <b>screenshot</b>."
        await send_message_with_close_button(client=client, message=message, text=text, thread_id=THREAD_ID)
        return

    await delete_user_unaccepted_requests(user=message.from_user.id)

    if not await check_request_requirements(user_id=message.from_user.id):
        await client.send_message(
            chat_id=message.chat.id,
            text=f"⚠️ <b>Warning</b>\n\n🔸 <b>{message.from_user.mention} ha già ricevuto 2 regali</b>. "
                 "Per poterne chiedere un altro, deve prima farne almeno uno.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚮 Chiudi – Solo Admin", callback_data="close_admin")]
            ]),
            message_thread_id=THREAD_ID
        )
        await safe_delete(message)
        return

    await message.forward(int(os.getenv("DEPOSIT_CHAT_ID")))
    await safe_delete(message)

    added_id = await add_to_table(
        table_name="gifts",
        content={
            "user_id": message.from_user.id,
            "username": message.from_user.username if message.from_user.username else None,
            "gifted_id": None,
            "gifted_username": None,
            "gifted_at": None,
            "request_link": None
        }
    )

    message = await client.send_photo(
        photo=message.photo.file_id,
        chat_id=message.chat.id,
        caption=f"🃏 <b>Richiesta Regalo</b>\n\n🔹 {message.from_user.mention} sta richiedendo un <b>nuovo regalo</b>.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎁 Accetta Richiesta", callback_data=f"accept_gift_for_{added_id}")],
            [InlineKeyboardButton("🚮 Chiudi – Solo Admin", callback_data="close_admin")]
        ]),
        message_thread_id=THREAD_ID
    )

    await execute_query_for_value(
        query=f"UPDATE gifts SET request_link = \'{message.link}\' WHERE id = {added_id}",
        for_value=False
    )


async def accept_gift(client: Client, callback_query: CallbackQuery):
    global bot_data
    gift_id = callback_query.data.split("_")[-1]

    gift = await get_item_infos(table="gifts", identifier=gift_id)

    if gift is False:
        text = "ℹ️ Questa non è l'ultima richiesta fatta dall'utente."
        user_requesting_id = None
        query_message_entities = callback_query.message.entities
        if query_message_entities is None:
            await safe_delete(callback_query.message)
            text = "⚠️ La richiesta con cui hai interagito è rimasta inattiva e non è più disponibile."
            await send_message_with_close_button(
                client=client,
                message=None,
                text=text,
                chat_id=callback_query.message.chat.id
            )
            return
        for el in query_message_entities:
            if el.type.name == "TEXT_MENTION":
                user_requesting_id = el.user.id
                break
        if user_requesting_id:
            query = (f"SELECT request_link FROM gifts "
                     f"WHERE user_id = \'{user_requesting_id}\' "
                     f"AND cancelled = FALSE "
                     f"ORDER BY id DESC LIMIT 1")
            res = await execute_query_for_value(query=query, for_value=True)
            if len(res) > 0:
                text += (f" Usa il link qua sotto per raggiungere l'ultima richiesta fatta dallo stesso utente."
                         f"\n\n🔸 <i>Ultima Richiesta</i>: <a href=\"{res}\">🔗 link</a>\n\n"
                         f"🛟 Se il messaggio linkato non esiste o il link non porta a nessun messaggio, chiedi "
                         f"all'utente di riformulare una richiesta.")
        if "Ultima" not in text:
            text += ("\n\n🛟 Cerca una richiesta più recente fatta dall'utente oppure chiedi all'utente di riformulare "
                     "una richiesta.")
        await send_message_with_close_button(
            client=client,
            message=None,
            chat_id=callback_query.message.chat.id,
            text=text,
            thread_id=THREAD_ID
        )
        await safe_delete(callback_query.message)
        return

    if gift is None:
        return

    if callback_query.data.startswith("accept_gift_for_"):
        if (user_requesting := gift["user_id"]) == (gifting_by_id := int(callback_query.from_user.id)):
            return
        try:
            user_requesting = await client.get_chat_member(
                chat_id=callback_query.message.chat.id,
                user_id=user_requesting
            )
        except Exception as e:
            # l'utente è uscito nel frattempo, loggo l'errore e via
            bot_logger.error(msg=f"Errore durante il reperimento delle informazioni dell'utente {gifting_by_id}: {e}")
            await send_message_with_close_button(
                client=client,
                message=None,
                chat_id=callback_query.message.chat.id,
                text=f"⚠️ C'è stato un errore durante il reperimento "
                     f"delle informazioni dell'utente <code>{gifting_by_id}>/code>.\n\n"
                     f"🆘 Se l'utente che ha formulato la richiesta non è uscito nel frattempo, contatta "
                     f"l'amministratore per assistenza.",
                thread_id=THREAD_ID
            )
            return

        keyboard = [
            [
                InlineKeyboardButton(
                    text=f"✅ Confermo",
                    callback_data=f"accepting_{callback_query.from_user.id}_gift_{gift_id}"
                ),
                InlineKeyboardButton(
                    text=f"❌ Annulla",
                    callback_data=f"abort_{callback_query.from_user.id}_{gift['id']}"
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🚮 Cancella – Solo Admin",
                    callback_data=f"close_admin"
                )
            ]
        ]

        await client.send_photo(
            photo=callback_query.message.photo.file_id,
            chat_id=callback_query.message.chat.id,
            caption=f"❓ <b>Accettazione Richiesta</b>\n\n🎖 {callback_query.from_user.mention}, stai accettando la richiesta "
                 f"di un nuovo regalo da {user_requesting.user.mention}. "
                 f"<b>Se confermi, ti assumi il dovere di fare questo regalo</b>.\n\n"
                 f"🔸 Confermi?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML,
            message_thread_id=THREAD_ID
        )

        await safe_delete(callback_query.message)

    elif "accepting" in callback_query.data and "gift" in callback_query.data:
        listed = callback_query.data.split("_")
        listed.pop(0)
        listed.pop(1)
        listed = {
            "accepting": int(listed[0]),
            "requesting": gift["user_id"]
        }

        try:
            user_requesting = await client.get_chat_member(
                chat_id=callback_query.message.chat.id,
                user_id=gift["user_id"]
            )
        except Exception as e:
            bot_logger.error(msg=f"Errore durante il reperimento delle informazioni dell'utente {gift["user_id"]}: {e}")
            await send_message_with_close_button(
                client=client,
                message=None,
                chat_id=callback_query.message.chat.id,
                text=f"⚠️ C'è stato un errore durante il reperimento "
                     f"delle informazioni dell'utente <code>{gift["user_id"]}>/code>.\n\n"
                     f"🆘 Se l'utente che ha formulato la richiesta non è uscito nel frattempo, contatta "
                     f"l'amministratore per assistenza.",
                thread_id=THREAD_ID
            )
            return

        if not await check_request_requirements(user_id=listed["requesting"]):
            await client.send_message(
                chat_id=callback_query.message.chat.id,
                text=f"⚠️ <b>Warning</b>\n\n🔸 Non puoi accettare questo regalo perché "
                     f"nel frattempo <b>{user_requesting.user.mention} ha raggiunto il limite di 2 regali</b>. "
                     "Per poterne chiedere un altro, deve prima farne almeno uno.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🚮 Chiudi – Solo Admin", callback_data="close_admin")]
                ]),
                message_thread_id=THREAD_ID
            )
            await safe_delete(callback_query.message)
            return

        if listed["accepting"] != callback_query.from_user.id:
            return

        user_accepting = callback_query.from_user

        await execute_query_for_value(
            query=f"UPDATE gifts "
                  f"SET gifted_by_id = {user_accepting.id}, "
                  f"gifted_by_username = {('\'' + user_accepting.username + '\'') if user_accepting.username else 'NULL'}, "
                  f"gifted_at = now() "
                  f"WHERE id = {gift["id"]}",
            for_value=False
        )

        keyboard = [
            [
                InlineKeyboardButton("🖍 Annulla Regalo", callback_data=f"cancel_gift_{gift['id']}")
            ],
            [
                InlineKeyboardButton("🗂 Conferma e Chiudi", callback_data="confirm_and_close")
            ]
        ]

        await client.edit_message_caption(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.id,
            caption=f"✅ <b>Regalo Accettato</b>\n\n"
                 f"🔸 <b>{user_accepting.mention} ha accettato il regalo "
                 f"richiesto da {user_requesting.user.mention}</b>.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    elif callback_query.data.startswith("abort_"):
        if callback_query.from_user.id != int(callback_query.data.split("_")[1]):
            return

        try:
            user_requesting = await client.get_chat_member(
                chat_id=callback_query.message.chat.id,
                user_id=gift["user_id"]
            )
        except Exception as e:
            bot_logger.error(f"Errore durante il reperimento delle informazioni dell'utente {gift["user_id"]}: {e}")
            return

        await client.edit_message_text(
            chat_id=callback_query.message.chat.id,
            message_id=callback_query.message.id,
            text=f"🃏 <b>Richiesta Regalo</b>\n\n🔹 {user_requesting.user.mention} sta richiedendo "
                 f"un <b>nuovo regalo</b>.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎁 Accetta Richiesta", callback_data=f"accept_gift_for_{gift['id']}")],
                [InlineKeyboardButton("🚮 Chiudi – Solo Admin", callback_data="close_admin")]
            ])
        )


async def cancel_gift(client: Client, callback_query: CallbackQuery):
    if not await is_admin(callback_query.from_user.id):
        return

    gift_id = callback_query.data.split("_")[-1]
    gift_infos = await get_item_infos(table="gifts", identifier=gift_id)

    sender = await client.get_chat_member(
        chat_id=callback_query.message.chat.id,
        user_id=("@" + gift_infos["username"]) if gift_infos["username"] else int(gift_infos["user_id"])
    )

    recipient = await client.get_chat_member(
        chat_id=callback_query.message.chat.id,
        user_id=("@" + gift_infos["gifted_by_username"]) if gift_infos["gifted_by_username"] else int(gift_infos["gifted_by_id"])
    )

    await set_as_cancelled(table="gifts", identifier=gift_id)
    await client.send_message(
        chat_id=callback_query.message.chat.id,
        text=f"🌪 Regalo da {sender.user.mention} a {recipient.user.mention} <b>cancellato</b> correttamente.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚮 Chiudi – Solo Admin", callback_data="close_admin")]
        ]),
        message_thread_id=THREAD_ID
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
            text=f"🎯 L'utente {sender.mention} ha ottenuto {SOGLIA} punti."
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
            text=f"🎯 L'utente {recipient.mention} ha ottenuto {SOGLIA} punti."
        )
        bot_data[int(added_id)]["member_2_gift_notification"] = sent_message.id
        await save_persistence(bot_data)

    text = f"✅ <b>Scambio Registrato Correttamente</b>\n\n"
    if points_sender == 0:
        text += f"🎁 <u><i>Sender</i></u> {message.from_user.mention} (<code>{sender.id}</code>) → {SOGLIA} (+1)\n"
    else:
        text += (f"🔸 <u><i>Sender</i></u> {message.from_user.mention} (<code>{sender.id}</code>) → {points_sender}"
                 f" (+1)\n")

    if points_recipient == 0:
        text += f"🎁 <u><i>Recipient</i></u> {recipient.mention} (<code>{recipient.id}</code>) → {SOGLIA} (+1)\n"
    else:
        text += (f"🔹 <u><i>Recipient</i></u> {recipient.mention} (<code>{recipient.id}</code>) → {points_recipient}"
                 f" (+1)\n")

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
                                         chat_id=None,
                                         thread_id=None):
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
        reply_markup=InlineKeyboardMarkup(keyboard),
        message_thread_id=thread_id
    )
    return message


async def user_exchanges(client: Client, message: Message):
    await safe_delete(message)
    if not await safety_check(client, message) or not await is_admin(message.from_user.id):
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
            return

    list_el = callback_query.data.split("_")

    if list_el[-1].isnumeric():
        if callback_query.from_user.id == int(list_el[-1]):
            await safe_delete(callback_query.message)

    else:
        await safe_delete(callback_query.message)
