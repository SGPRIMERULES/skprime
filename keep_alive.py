# keep_alive.py
from flask import Flask
from threading import Thread
import os

app = Flask("")

@app.route("/")
def home():
    return "Bot is alive!"

def run():
    # Use the PORT Render provides (environment variable), default 10000
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()
