import os
import json
import re
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters, ChatMemberHandler
)
from dotenv import load_dotenv
 
load_dotenv()

BOT_TOK = os.getenv("BOT_TOK")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_ID = int(os.getenv("GROUP_ID"))
BAN_FILE = "banned.txt"
TOPICS_FILE = "topics.json"
 
DEBUG = False  # set False in production
 
white_list = {"messages": GROUP_ID}

# ── persistence ────────────────────────────────────────────────────────────────
 
def load_banned():
    if not os.path.exists(BAN_FILE):
        return set()
    with open(BAN_FILE, encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())
 
def save_banned(users):
    with open(BAN_FILE, "w", encoding="utf-8") as f:
        for u in users:
            f.write(str(u) + "\n")
 
def load_topics():
    if not os.path.exists(TOPICS_FILE):
        return {}
    with open(TOPICS_FILE, encoding="utf-8") as f:
        return json.load(f)  # { "user_id": thread_id }
 
def save_topics(topics):
    with open(TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(topics, f)
 
 
banned_users = load_banned()
user_topics = load_topics()   # survives restarts, no RAM-only state
 
 
# ── helpers ─────────────────────────────────────────────────────────────────────
 
async def left_group(update: Update, context: CallbackContext):
    chat = update.my_chat_member.chat
    new_status = update.my_chat_member.new_chat_member.status
    if new_status in ["member", "administrator"] and chat.id != GROUP_ID:
        await context.bot.leave_chat(chat.id)
        return

def get_sender_name(user):
    return f"@{user.username}" if user.username else f"{user.first_name} {user.last_name or ''}".strip()
 
async def get_or_create_topic(context, user):
    """Return existing thread_id for user, or create a new topic."""
    uid = str(user.id)
    if uid in user_topics:
        return user_topics[uid]
 
    topic = await context.bot.create_forum_topic(
        chat_id=GROUP_ID,
        name=f"{get_sender_name(user)} [{user.id}]"
    )
    thread_id = topic.message_thread_id
    user_topics[uid] = thread_id
    save_topics(user_topics)
    await context.bot.send_message(GROUP_ID, f"{get_sender_name(user)}:", message_thread_id=thread_id)
    return thread_id
 
async def forward_to_group(context, user, msg, thread_id):
    """Forward any message type into the correct topic."""
    caption = msg.caption or ""
 
    if msg.photo:
        await context.bot.send_photo(GROUP_ID, msg.photo[-1].file_id,
            caption=caption, message_thread_id=thread_id)
    elif msg.video:
        await context.bot.send_video(GROUP_ID, msg.video.file_id,
            caption=caption, message_thread_id=thread_id)
    elif msg.document:
        await context.bot.send_document(GROUP_ID, msg.document.file_id,
            caption=caption, message_thread_id=thread_id)
    elif msg.voice:
        await context.bot.send_voice(GROUP_ID, msg.voice.file_id,
            message_thread_id=thread_id)
    elif msg.audio:
        await context.bot.send_audio(GROUP_ID, msg.audio.file_id,
            caption=caption, message_thread_id=thread_id)
    elif msg.sticker:
        await context.bot.send_sticker(GROUP_ID, msg.sticker.file_id,
            message_thread_id=thread_id)
    elif msg.video_note:
        await context.bot.send_video_note(GROUP_ID, msg.video_note.file_id,
            message_thread_id=thread_id)
    elif msg.text:
        await context.bot.send_message(GROUP_ID, msg.text,
            message_thread_id=thread_id)
 
async def forward_to_user(context, user_id, msg):
    """Forward any message type back to the user."""
    caption = msg.caption or ""
 
    if msg.photo:
        await context.bot.send_photo(user_id, msg.photo[-1].file_id, caption=caption)
    elif msg.video:
        await context.bot.send_video(user_id, msg.video.file_id, caption=caption)
    elif msg.document:
        await context.bot.send_document(user_id, msg.document.file_id, caption=caption)
    elif msg.voice:
        await context.bot.send_voice(user_id, msg.voice.file_id)
    elif msg.audio:
        await context.bot.send_audio(user_id, msg.audio.file_id, caption=caption)
    elif msg.sticker:
        await context.bot.send_sticker(user_id, msg.sticker.file_id)
    elif msg.video_note:
        await context.bot.send_video_note(user_id, msg.video_note.file_id)
    elif msg.text:
        await context.bot.send_message(user_id, msg.text)
 
 
# ── commands ────────────────────────────────────────────────────────────────────
 
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привіт! Напиши своє повідомлення.")
 
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ban: reply to any message in a topic. Works from group or bot chat."""
    if update.effective_user.id != ADMIN_ID:
        return
 
    # extract user_id from topic name  "[12345678]"  or from forwarded text
    user_id = None
 
    # try topic name first (most reliable)
    if update.message.message_thread_id:
        thread_id = update.message.message_thread_id
        # reverse-lookup user_id from topics map
        for uid, tid in user_topics.items():
            if tid == thread_id:
                user_id = uid
                break
 
    if not user_id:
        await update.message.reply_text("Не можу знайти користувача.")
        return
 
    banned_users.add(user_id)
    save_banned(banned_users)
    await update.message.reply_text(f"Користувач {user_id} забанений.")
 
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
 
    user_id = None
    if update.message.message_thread_id:
        thread_id = update.message.message_thread_id
        for uid, tid in user_topics.items():
            if tid == thread_id:
                user_id = uid
                break
 
    if not user_id:
        await update.message.reply_text("Не можу знайти користувача.")
        return
 
    if user_id in banned_users:
        banned_users.remove(user_id)
        save_banned(banned_users)
        await update.message.reply_text(f"Користувач {user_id} розбанений.")
    else:
        await update.message.reply_text(f"Користувача {user_id} немає в бані.")
 
 
async def delete_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not update.message.message_thread_id or update.message.chat_id != GROUP_ID:
        await update.message.reply_text("Виконай команду всередині топіку.")
        return

    thread_id = update.message.message_thread_id

    # find and remove from json
    user_id = None
    for uid, tid in user_topics.items():
        if tid == thread_id:
            user_id = uid
            break

    if not user_id:
        await update.message.reply_text("Топік не знайдено в базі.")
        return

    try:
        await context.bot.delete_forum_topic(
            chat_id=GROUP_ID,
            message_thread_id=thread_id
        )
        del user_topics[user_id]
        save_topics(user_topics)
        # can't reply to a deleted topic so send to general chat
        await context.bot.send_message(GROUP_ID, f"Топік користувача {user_id} видалено.")
    except Exception as e:
        await update.message.reply_text(f"Помилка: {e}")

# ── main handler ────────────────────────────────────────────────────────────────
 
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg:
        return
 
    user = msg.from_user
    is_admin = user.id == ADMIN_ID
 
    # ── admin replying inside a topic → forward to user ──────────────────────
    if is_admin and msg.message_thread_id and msg.chat_id == GROUP_ID:
        thread_id = msg.message_thread_id
        user_id = None
        for uid, tid in user_topics.items():
            if tid == thread_id:
                user_id = int(uid)
                break
 
        if user_id:
            try:
                await forward_to_user(context, user_id, msg)
            except Exception as e:
                await msg.reply_text(f"Помилка: {e}")
        return
 

    # ── ban check ────────────────────────────────────────────────────────────
    if str(user.id) in banned_users:
        return
 
    # ── user → forward to group topic ────────────────────────────────────────
    try:
        thread_id = await get_or_create_topic(context, user)
        await forward_to_group(context, user, msg, thread_id)
 
        if DEBUG and is_admin:
            await msg.reply_text("[DEBUG] Повідомлення переслано в групу.")
        else:
            await update.effective_message.set_reaction(reaction="👌")
    except Exception as e:
        await msg.reply_text(f"Помилка: {e}")
 
 
# ── app setup ───────────────────────────────────────────────────────────────────
 
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOK).build()
 
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("delete", delete_topic))
    app.add_handler(ChatMemberHandler(left_group, chat_member_types="my_chat_member"))

    media_filter = (
        filters.TEXT | filters.PHOTO | filters.VIDEO |
        filters.Document.ALL | filters.VOICE | filters.AUDIO |
        filters.Sticker.ALL | filters.VIDEO_NOTE
    ) & ~filters.COMMAND
 
    app.add_handler(MessageHandler(media_filter, message_handler))
 
    app.run_polling()
