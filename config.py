import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "8929555984:AAEVLnYzg6wVmFrpuxICgoLg7t0ttFJcdTg")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8903157513"))
WEB_URL = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:8000")
PORT = int(os.getenv("PORT", 8000))
DB_NAME = "bot_database.db"
