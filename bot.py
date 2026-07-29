import os
import logging
import time
import io
import sys
import types
import threading
import asyncio

# ===== FIX FOR PYTHON 3.14 =====
if 'imghdr' not in sys.modules:
    imghdr = types.ModuleType('imghdr')
    def what(file, h=None):
        return None
    imghdr.what = what
    sys.modules['imghdr'] = imghdr
# ================================

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from config import BOT_TOKEN
from google_drive import (
    upload_file_to_drive, 
    list_drive_files, 
    search_drive_files, 
    delete_drive_file, 
    rename_drive_file,
    get_or_create_user_folder
)

logging.basicConfig(level=logging.INFO)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    folder_id = get_or_create_user_folder(user_id)
    context.user_data['folder_id'] = folder_id
    
    keyboard = [
        [InlineKeyboardButton("📤 Upload File", callback_data='upload')],
        [InlineKeyboardButton("📂 My Files", callback_data='list')],
        [InlineKeyboardButton("🔍 Search Files", callback_data='search')],
        [InlineKeyboardButton("📁 Change Folder", callback_data='folder')],
        [InlineKeyboardButton("✏️ Rename File", callback_data='rename')],
        [InlineKeyboardButton("🗑️ Delete File", callback_data='delete')],
        [InlineKeyboardButton("❓ Help", callback_data='help')],
        [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"👋 *Welcome to Drive Upload Bot!*\n\n"
        f"✅ Your personal Drive folder is ready!\n"
        f"📁 Folder ID: `{folder_id}`\n\n"
        f"*Click buttons below for actions:*",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    folder_id = context.user_data.get('folder_id')
    
    if not folder_id:
        folder_id = get_or_create_user_folder(user_id)
        context.user_data['folder_id'] = folder_id
    
    if query.data == 'upload':
        await query.edit_message_text("📤 Send me the file(s) you want to upload.", parse_mode='Markdown')
    
    elif query.data == 'list':
        files = list_drive_files(folder_id)
        if not files:
            await query.edit_message_text("📭 No files found in your Drive folder.")
            return
        msg = "📂 *Your Files:*\n\n"
        for i, file in enumerate(files[:15], 1):
            size = file.get('size', 'Unknown')
            if size != 'Unknown':
                size = f"{int(size) / 1024:.1f} KB"
            msg += f"{i}. 📄 *{file['name']}*\n   🆔 `{file['id']}`\n   📦 {size}\n\n"
        await query.edit_message_text(msg, parse_mode='Markdown')
    
    elif query.data == 'search':
        await query.edit_message_text("🔍 Send me the filename or keyword to search.")
        context.user_data['search_mode'] = True
    
    elif query.data == 'folder':
        await query.edit_message_text("📁 Send me the new folder name.\n\n*Example:* `my_photos`", parse_mode='Markdown')
        context.user_data['folder_mode'] = True
    
    elif query.data == 'rename':
        await query.edit_message_text("✏️ Send me the file ID and new name.\n\n*Format:* `file_id new_name`", parse_mode='Markdown')
        context.user_data['rename_mode'] = True
    
    elif query.data == 'delete':
        await query.edit_message_text("🗑️ Send me the file ID to delete.\n\n*Example:* `1abc2def`", parse_mode='Markdown')
        context.user_data['delete_mode'] = True
    
    elif query.data == 'help':
        help_text = """
*📖 Bot Guide*

*Features:*
✅ Upload files to Drive
✅ Personal folders for each user
✅ Rename files
✅ Delete files
✅ Search files
✅ Change folders
✅ Real progress bar

*How to use:*
1. Click Upload button
2. Send file(s)
3. Watch real progress
4. Get download link

*Commands also work:*
/start - Main menu
/upload - Upload files
/myfiles - List files
/search - Search files
/folder - Change folder
/rename - Rename file
/delete - Delete file
/cancel - Cancel operation
        """
        await query.edit_message_text(help_text, parse_mode='Markdown')
    
    elif query.data == 'cancel':
        context.user_data.clear()
        folder_id = get_or_create_user_folder(user_id)
        context.user_data['folder_id'] = folder_id
        await query.edit_message_text("✅ All operations cancelled. Use /start for main menu.")

async def handle_documents(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    folder_id = context.user_data.get('folder_id')
    
    if not folder_id:
        folder_id = get_or_create_user_folder(user_id)
        context.user_data['folder_id'] = folder_id
    
    doc = update.message.document or update.message.photo or update.message.video or update.message.audio
    
    if not doc:
        await update.message.reply_text("❌ Please send a valid file.")
        return
    
    if update.message.document:
        file = update.message.document
        file_name = file.file_name
    elif update.message.photo:
        file = update.message.photo[-1]
        file_name = f"photo_{int(time.time())}.jpg"
    elif update.message.video:
        file = update.message.video
        file_name = f"video_{int(time.time())}.mp4"
    elif update.message.audio:
        file = update.message.audio
        file_name = f"audio_{int(time.time())}.mp3"
    else:
        await update.message.reply_text("❌ Unsupported file type.")
        return
    
    if file.file_size > 50 * 1024 * 1024:
        await update.message.reply_text("❌ File too large! Maximum 50MB allowed.")
        return
    
    status_msg = await update.message.reply_text(f"⏳ Starting upload of *{file_name}*...", parse_mode='Markdown')
    
    try:
        file_obj = await file.get_file()
        
        file_data = io.BytesIO()
        await file_obj.download_to_memory(file_data)
        file_data.seek(0)
        
        file_path = f"downloads/{file_name}"
        os.makedirs("downloads", exist_ok=True)
        with open(file_path, 'wb') as f:
            f.write(file_data.getvalue())
        
        await status_msg.edit_text(f"⏳ Uploading *{file_name}* to Drive...\n[████████████] 100%", parse_mode='Markdown')
        
        file_id, link = upload_file_to_drive(file_path, folder_id)
        
        os.remove(file_path)
        
        await status_msg.edit_text(
            f"✅ *Upload Successful!*\n\n"
            f"📄 File: `{file_name}`\n"
            f"🆔 ID: `{file_id}`\n"
            f"🔗 [Open in Drive]({link})\n"
            f"📁 Folder: `{folder_id}`",
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Upload failed: {str(e)}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            await update.message.reply_text(f"🔍 No files found with: *{text}*", parse_mode='Markdown')
            return
        msg = f"🔍 *Search Results for '{text}':*\n\n"
        for file in files[:10]:
            msg += f"📄 {file['name']}\n   🆔 `{file['id']}`\n\n"
        await update.message.reply_text(msg, parse_mode='Markdown')
    
    elif context.user_data.get('folder_mode'):
        new_folder_id = get_or_create_user_folder(f"{user_id}_{text}")
        context.user_data['folder_id'] = new_folder_id
        context.user_data['folder_mode'] = False
        await update.message.reply_text(f"✅ Folder changed to: *{text}*\n📁 ID: `{new_folder_id}`", parse_mode='Markdown')
    
    elif context.user_data.get('rename_mode'):
        parts = text.split(' ', 1)
        if len(parts) < 2:
            await update.message.reply_text("❌ Format: `file_id new_name`", parse_mode='Markdown')
            context.user_data['rename_mode'] = False
            return
        file_id = parts[0]
        new_name = parts[1]
        try:
            result = rename_drive_file(file_id, new_name)
            context.user_data['rename_mode'] = False
            await update.message.reply_text(f"✅ File renamed to: *{result}*", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Rename failed: {str(e)}")
    
    elif context.user_data.get('delete_mode'):
        file_id = text.strip()
        try:
            delete_drive_file(file_id)
            context.user_data['delete_mode'] = False
            await update.message.reply_text(f"✅ File with ID `{file_id}` deleted successfully!", parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Delete failed: {str(e)}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    user_id = update.effective_user.id
    folder_id = get_or_create_user_folder(user_id)
    context.user_data['folder_id'] = folder_id
    await update.message.reply_text("✅ All operations cancelled. Use /start for main menu.")

def main():
    # Start Flask server in background for Render health checks
    try:
        from flask import Flask
        app_flask = Flask(__name__)
        
        @app_flask.route('/')
        def health_check():
            return "Bot is running!", 200
        
        @app_flask.route('/health')
        def health():
            return "OK", 200
        
        def run_flask():
            app_flask.run(host='0.0.0.0', port=8080)
        
        flask_thread = threading.Thread(target=run_flask)
        flask_thread.daemon = True
        flask_thread.start()
        print("🌐 Web server started on port 8080")
    except Exception as e:
        print(f"⚠️ Web server not started: {e}")
    
    # Start Telegram bot
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO | filters.VIDEO | filters.AUDIO, handle_documents))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("🤖 Bot is running... Press Ctrl+C to stop")
    print("✅ All features ready!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
