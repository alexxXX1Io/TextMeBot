from telethon import TelegramClient, events, functions
import os
from dotenv import load_dotenv
load_dotenv()
API_ID = os.getenv("USERBOT_ID")
API_HASH = os.getenv("USERBOT_HASH")
client = TelegramClient('session_name', API_ID, API_HASH)
client.start()
