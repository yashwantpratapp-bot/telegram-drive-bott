import os

# Environment variable se token lo (secure)
BOT_TOKEN = os.environ.get('BOT_TOKEN', "YOUR_TELEGRAM_BOT_TOKEN")
DRIVE_FOLDER_ID = None
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.pickle"
