import os
import sqlite3
import discord
from discord import app_commands
from flask import Flask
import threading

# ================= TOKEN =================

TOKEN = os.getenv("BOTTOKEN")
if not TOKEN:
    raise ValueError("No token found. Set BOTTOKEN in Render environment variables.")

# ================= FLASK (Render Keep-Alive) =================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

# ================= DISCORD SETUP =================

intents = discord.Intents.default()
intents.members = True  # Needed for member lookup

bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

# ================= DATABASE =================

conn = sqlite3.connect("stats.db", check_same_thread=False)
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

# ================= REGISTER =================

@tree.command(name="register", description="Register your Smash Karts ID")
@app_commands.describe(sk_id="Your Smash Karts IGN")
async def register(interaction: discord.Interaction, sk_id: str):

    user_id = interaction.user.id

    cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
    if cursor.fetchone():
        await interaction.response.send_message("You are already registered!", ephemeral=True)
        return

    try:
        cursor.execute(
            "INSERT INTO players (user_id, sk_id) VALUES (?, ?)",
            (user_id, sk_id)
        )
        conn.commit()
    except sqlite3.IntegrityError:
        await interaction.response.send_message("This SK ID is already registered!", ephemeral=True)
        return

    await interaction.response.send_message(
        f"✅ Registered with SK ID: **{sk_id}**",
        ephemeral=True
    )

# ================= EDIT STATS =================

@tree.command(name="editstats", description="Edit your own stats")
@app_commands.describe(
    kills="Total kills",
    deaths="Total deaths",
    matches="Total matches",
    wins="Total wins"
)
async def editstats(interaction: discord.Interaction, kills: int, deaths: int, matches: int, wins: int):

    user_id = interaction.user.id

    cursor.execute("SELECT * FROM players WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        await interaction.response.send_message("Register first using /register", ephemeral=True)
        return

    cursor.execute("""
        UPDATE players
        SET kills = ?, deaths = ?, matches = ?, wins = ?
        WHERE user_id = ?
    """, (kills, deaths, matches, wins, user_id))

    conn.commit()

    await interaction.response.send_message("✅ Stats updated!", ephemeral=True)

# ================= PROFILE =================

@tree.command(name="profile", description="View player's stats")
@app_commands.describe(member="Select a member")
async def profile(interaction: discord.Interaction, member: discord.Member):

    cursor.execute("SELECT * FROM players WHERE user_id = ?", (member.id,))
    data = cursor.fetchone()

    if not data:
        await interaction.response.send_message("Player not registered.", ephemeral=True)
        return

    _, sk_id, kills, deaths, matches, wins = data
    kdr = round(kills / deaths, 2) if deaths > 0 else kills

    embed = discord.Embed(
        title=f"{member.name}'s Stats",
        color=discord.Color.blue()
    )
    embed.add_field(name="SK ID", value=sk_id, inline=False)
    embed.add_field(name="Kills", value=kills)
    embed.add_field(name="Deaths", value=deaths)
    embed.add_field(name="Matches", value=matches)
    embed.add_field(name="Wins", value=wins)
    embed.add_field(name="KDR", value=kdr)

    await interaction.response.send_message(embed=embed)

# ================= LEADERBOARD =================

@tree.command(name="leaderboard", description="View leaderboard")
@app_commands.describe(category="Choose leaderboard type")
@app_commands.choices(category=[
    app_commands.Choice(name="Kills", value="kills"),
    app_commands.Choice(name="KDR", value="kdr"),
    app_commands.Choice(name="Wins", value="wins")
])
async def leaderboard(interaction: discord.Interaction, category: app_commands.Choice[str]):

    description = ""

    if category.value == "kills":
        cursor.execute("SELECT sk_id, kills FROM players ORDER BY kills DESC LIMIT 10")
        data = cursor.fetchall()
        title = "🩸 Kill Leaderboard"
        for i, (sk_id, kills) in enumerate(data, 1):
            description += f"**{i}. {sk_id}** - {kills} kills\n"

    elif category.value == "wins":
        cursor.execute("SELECT sk_id, wins FROM players ORDER BY wins DESC LIMIT 10")
        data = cursor.fetchall()
        title = "🏆 Wins Leaderboard"
        for i, (sk_id, wins) in enumerate(data, 1):
            description += f"**{i}. {sk_id}** - {wins} wins\n"

    elif category.value == "kdr":
        cursor.execute("SELECT sk_id, kills, deaths FROM players")
        players = cursor.fetchall()

        kdr_list = []
        for sk_id, kills, deaths in players:
            kdr = kills / deaths if deaths > 0 else kills
            kdr_list.append((sk_id, round(kdr, 2)))

        kdr_list.sort(key=lambda x: x[1], reverse=True)
        top = kdr_list[:10]

        title = "🎯 KDR Leaderboard"
        for i, (sk_id, kdr) in enumerate(top, 1):
            description += f"**{i}. {sk_id}** - {kdr} KDR\n"

    embed = discord.Embed(title=title, description=description, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

# ================= READY =================

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Logged in as {bot.user}")

# ================= START =================

def run_bot():
    bot.run(TOKEN)

if __name__ == "__main__":
    # Run Flask and Discord together
    threading.Thread(target=run_web).start()
    run_bot()
