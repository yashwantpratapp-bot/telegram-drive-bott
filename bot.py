import os
import sys
import types
import logging
import time
import io
from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, Filters, CallbackQueryHandler
from config import BOT_TOKEN
from google_drive import (
    upload_file_to_drive,
    list_drive_files,
    search_drive_files,
    delete_drive_file,
    rename_drive_file,
    get_or_create_user_folder
)

# ===== FIX FOR PYTHON 3.14 / imghdr missing =====
if 'imghdr' not in sys.modules:
    imghdr = types.ModuleType('imghdr')
    imghdr.what = lambda f, h=None: None
    sys.modules['imghdr'] = imghdr
# ================================================

app = Flask(__name__)
bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot, None, workers=0)

# ========== HANDLERS ==========

def start(update, context):
    user_id = update.effective_user.id
    folder_id = get_or_create_user_folder(user_id)
    context.user_data['folder_id'] = folder_id

    keyboard = [
        [InlineKeyboardButton("📤 Upload File", callback_data='upload')],
        [InlineKeyboardButton("📂 My Files", callback_data='list')],
        [InlineKeyboardButton("🔍 Search", callback_data='search')],
        [InlineKeyboardButton("📁 Change Folder", callback_data='folder')],
        [InlineKeyboardButton("✏️ Rename", callback_data='rename')],
        [InlineKeyboardButton("🗑️ Delete", callback_data='delete')],
        [InlineKeyboardButton("❓ Help", callback_data='help')],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    update.message.reply_text(
        f"👋 Welcome!\n✅ Folder ready: `{folder_id}`",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def button_handler(update, context):
    query = update.callback_query
    query.answer()
    user_id = update.effective_user.id
    folder_id = context.user_data.get('folder_id')
    if not folder_id:
        folder_id = get_or_create_user_folder(user_id)
        context.user_data['folder_id'] = folder_id

    if query.data == 'upload':
        query.edit_message_text("📤 Send me the file.")
    elif query.data == 'list':
        files = list_drive_files(folder_id)
        if not files:
            query.edit_message_text("📭 No files.")
            return
        msg = "📂 *Files:*\n"
        for f in files[:10]:
            msg += f"• {f['name']} (ID: `{f['id']}`)\n"
        query.edit_message_text(msg, parse_mode='Markdown')
    elif query.data == 'search':
        query.edit_message_text("🔍 Send keyword.")
        context.user_data['search_mode'] = True
    elif query.data == 'folder':
        query.edit_message_text("📁 Send new folder name.")
        context.user_data['folder_mode'] = True
    elif query.data == 'rename':
        query.edit_message_text("✏️ Send: `file_id new_name`")
        context.user_data['rename_mode'] = True
    elif query.data == 'delete':
        query.edit_message_text("🗑️ Send file ID to delete.")
        context.user_data['delete_mode'] = True
    elif query.data == 'help':
        query.edit_message_text("*Help*\n/start - Menu\n/cancel - Cancel", parse_mode='Markdown')
    elif query.data == 'cancel':
        context.user_data.clear()
        folder_id = get_or_create_user_folder(user_id)
        context.user_data['folder_id'] = folder_id
        query.edit_message_text("✅ Cancelled.")

def handle_documents(update, context):
    user_id = update.effective_user.id
    folder_id = context.user_data.get('folder_id')
    if not folder_id:
        folder_id = get_or_create_user_folder(user_id)
        context.user_data['folder_id'] = folder_id

    doc = update.message.document or update.message.photo or update.message.video or update.message.audio
    if not doc:
        update.message.reply_text("❌ Invalid file.")
        return

    if update.message.document:
        file_name = doc.file_name
    elif update.message.photo:
        file_name = f"photo_{int(time.time())}.jpg"
    elif update.message.video:
        file_name = f"video_{int(time.time())}.mp4"
    elif update.message.audio:
        file_name = f"audio_{int(time.time())}.mp3"
    else:
        update.message.reply_text("❌ Unsupported.")
        return

    if doc.file_size > 50 * 1024 * 1024:
        update.message.reply_text("❌ Max 50MB.")
        return

    status_msg = update.message.reply_text(f"⏳ Uploading {file_name}...")
    try:
        file_obj = bot.get_file(doc.file_id)
        file_data = io.BytesIO()
        file_obj.download_to_memory(file_data)
        file_data.seek(0)

        file_path = f"/tmp/{file_name}"
        with open(file_path, 'wb') as f:
            f.write(file_data.getvalue())

        file_id, link = upload_file_to_drive(file_path, folder_id)
        os.remove(file_path)

        status_msg.edit_text(
            f"✅ Uploaded!\n📄 {file_name}\n🔗 [Drive]({link})",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    except Exception as e:
        status_msg.edit_text(f"❌ Failed: {e}")

def handle_text(update, context):
    text = update.message.text
    user_id = update.effective_user.id
    folder_id = context.user_data.get('folder_id')
    if not folder_id:
        folder_id = get_or_create_user_folder(user_id)
        context.user_data['folder_id'] = folder_id

    if context.user_data.get('search_mode'):
        files = search_drive_files(text, folder_id)
        context.user_data['search_mode'] = False
        if not files:
            update.message.reply_text("No files found.")
            return
        msg = "🔍 Results:\n"
        for f in files[:10]:
            msg += f"• {f['name']} (ID: `{f['id']}`)\n"
        update.message.reply_text(msg, parse_mode='Markdown')

    elif context.user_data.get('folder_mode'):
        new_id = get_or_create_user_folder(f"{user_id}_{text}")
        context.user_data['folder_id'] = new_id
        context.user_data['folder_mode'] = False
        update.message.reply_text(f"✅ Folder changed to: {text}")

    elif context.user_data.get('rename_mode'):
        parts = text.split(' ', 1)
        if len(parts) < 2:
            update.message.reply_text("❌ Format: `file_id new_name`")
            context.user_data['rename_mode'] = False
            return
        try:
            new_name = rename_drive_file(parts[0], parts[1])
            context.user_data['rename_mode'] = False
            update.message.reply_text(f"✅ Renamed to: {new_name}")
        except Exception as e:
            update.message.reply_text(f"❌ {e}")

    elif context.user_data.get('delete_mode'):
        try:
            delete_drive_file(text.strip())
            context.user_data['delete_mode'] = False
            update.message.reply_text("✅ Deleted.")
        except Exception as e:
            update.message.reply_text(f"❌ {e}")

def cancel(update, context):
    context.user_data.clear()
    user_id = update.effective_user.id
    folder_id = get_or_create_user_folder(user_id)
    context.user_data['folder_id'] = folder_id
    update.message.reply_text("✅ Cancelled.")

# ========== REGISTER ==========
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("cancel", cancel))
dispatcher.add_handler(MessageHandler(Filters.document | Filters.photo | Filters.video | Filters.audio, handle_documents))
dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))
dispatcher.add_handler(CallbackQueryHandler(button_handler))

# ========== FLASK ROUTE ==========
@app.route('/', methods=['GET', 'POST'])
def webhook():
    if request.method == 'GET':
        return "Bot is running!", 200
    if request.method == 'POST':
        update = Update.de_json(request.get_json(force=True), bot)
        dispatcher.process_update(update)
        return "OK", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
