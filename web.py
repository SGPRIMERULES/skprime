import os
import sqlite3
import discord
from discord import app_commands
from flask import Flask
import threading
import requests
import base64

# ================= ENV =================

DISCORD_TOKEN = os.getenv("BOTTOKEN")
GITHUB_TOKEN = os.getenv("PATTOKEN")

if not DISCORD_TOKEN:
    raise ValueError("Missing BOTTOKEN")

if not GITHUB_TOKEN:
    print("Warning: No PATTOKEN provided. GitHub sync disabled.")

# ======== EDIT THESE TWO LINES ONLY ========
GITHUB_USER = "YOUR_USERNAME"
GITHUB_REPO = "YOUR_REPO"
# ===========================================

DB_FILE = "stats.db"
GITHUB_PATH = "stats.db"

# ================= GITHUB SYNC =================

def gh_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }

def download_db():
    if not GITHUB_TOKEN:
        return

    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{GITHUB_PATH}"
    r = requests.get(url, headers=gh_headers())

    if r.status_code == 200:
        content = base64.b64decode(r.json()["content"])
        with open(DB_FILE, "wb") as f:
            f.write(content)
        print("Downloaded stats.db from GitHub")
    else:
        print("No remote DB found. Starting fresh.")

def upload_db():
    if not GITHUB_TOKEN:
        return

    url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{GITHUB_PATH}"

    with open(DB_FILE, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    # Check if file exists to get SHA
    r = requests.get(url, headers=gh_headers())
    sha = r.json()["sha"] if r.status_code == 200 else None

    data = {
        "message": "Update stats.db",
        "content": content
    }

    if sha:
        data["sha"] = sha

    requests.put(url, headers=gh_headers(), json=data)
    print("Uploaded stats.db to GitHub")

# Download latest DB at startup
download_db()

# ================= DATABASE =================

conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS players (
    user_id INTEGER PRIMARY KEY,
    sk_id TEXT UNIQUE,
    kills INTEGER DEFAULT 0,
    deaths INTEGER DEFAULT 0,
    matches INTEGER DEFAULT 0,
    wins INTEGER DEFAULT 0
)
""")
conn.commit()

def save_db():
    conn.commit()
    upload_db()

# ================= DISCORD =================

intents = discord.Intents.default()
intents.members = True

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# ================= FLASK (Render Keep Alive) =================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ================= COMMANDS =================

@tree.command(name="register", description="Register your Smash Karts ID")
@app_commands.describe(sk_id="Your Smash Karts IGN")
async def register(interaction: discord.Interaction, sk_id: str):

    user_id = interaction.user.id

    cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        await interaction.response.send_message("Already registered", ephemeral=True)
        return

    try:
        cursor.execute(
            "INSERT INTO players (user_id, sk_id) VALUES (?, ?)",
            (user_id, sk_id)
        )
        save_db()
    except sqlite3.IntegrityError:
        await interaction.response.send_message("IGN already taken", ephemeral=True)
        return

    await interaction.response.send_message("Registered!", ephemeral=True)

@tree.command(name="editstats", description="Edit your stats")
async def editstats(interaction: discord.Interaction, kills: int, deaths: int, matches: int, wins: int):

    user_id = interaction.user.id

    cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        await interaction.response.send_message("Register first using /register", ephemeral=True)
        return

    cursor.execute("""
        UPDATE players
        SET kills=?, deaths=?, matches=?, wins=?
        WHERE user_id=?
    """, (kills, deaths, matches, wins, user_id))

    save_db()
    await interaction.response.send_message("Stats updated!", ephemeral=True)

@tree.command(name="profile", description="View player stats")
async def profile(interaction: discord.Interaction, member: discord.Member):

    cursor.execute("SELECT * FROM players WHERE user_id = ?", (member.id,))
    data = cursor.fetchone()

    if not data:
        await interaction.response.send_message("Player not registered.", ephemeral=True)
        return

    _, sk_id, kills, deaths, matches, wins = data
    kdr = round(kills / deaths, 2) if deaths > 0 else kills

    embed = discord.Embed(title=f"{member.name}'s Stats", color=discord.Color.blue())
    embed.add_field(name="SK ID", value=sk_id, inline=False)
    embed.add_field(name="Kills", value=kills)
    embed.add_field(name="Deaths", value=deaths)
    embed.add_field(name="Matches", value=matches)
    embed.add_field(name="Wins", value=wins)
    embed.add_field(name="KDR", value=kdr)

    await interaction.response.send_message(embed=embed)

@tree.command(name="leaderboard", description="Top players by kills")
async def leaderboard(interaction: discord.Interaction):

    cursor.execute("SELECT sk_id, kills FROM players ORDER BY kills DESC LIMIT 10")
    data = cursor.fetchall()

    desc = ""
    for i, (sk_id, kills) in enumerate(data, 1):
        desc += f"**{i}. {sk_id}** - {kills} kills\n"

    embed = discord.Embed(title="Kill Leaderboard", description=desc, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

# ================= READY =================

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user}")

# ================= START =================

def run_bot():
    bot.run(DISCORD_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_web).start()
    run_bot()
