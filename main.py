from keep_alive
import keep_alive keep_alive()

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random
import asyncio
import os
import aiohttp
import html
from flask import Flask
from threading import Thread
from PIL import Image, ImageDraw, ImageFont
import io
# ---------------- KEEP ALIVE (RENDER) ---------------- #

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    Thread(target=run).start()

# ---------------- BOT SETUP ---------------- #

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
TOKEN = os.environ.get("TOKEN")

# ---------------- DATABASE ---------------- #

conn = sqlite3.connect("database.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1
)
""")
conn.commit()

# ---------------- XP SYSTEM ---------------- #

xp_cooldown = {}

def xp_required(level):
    return int(100 * (level ** 1.5))

def add_xp(user_id, amount):
    cursor.execute("SELECT xp, level FROM users WHERE user_id=?", (user_id,))
    data = cursor.fetchone()

    if not data:
        xp, level = 0, 1
        cursor.execute("INSERT INTO users VALUES (?, ?, ?)", (user_id, xp, level))
    else:
        xp, level = data

    xp += amount
    leveled_up = False

    while xp >= xp_required(level):
        xp -= xp_required(level)
        level += 1
        leveled_up = True

    cursor.execute("UPDATE users SET xp=?, level=? WHERE user_id=?", (xp, level, user_id))
    conn.commit()

    return level if leveled_up else None, xp, level

async def generate_xp_card(user: discord.User, xp: int, level: int):
    # Create an image
    width, height = 400, 150
    card = Image.new("RGB", (width, height), color=(30, 30, 30))
    draw = ImageDraw.Draw(card)

    # Fonts (you can download a .ttf font file and put the path here)
    font_large = ImageFont.truetype("arial.ttf", 30)
    font_small = ImageFont.truetype("arial.ttf", 20)

    # Background rectangle
    draw.rectangle([(0,0),(width,height)], fill=(40,40,40))

    # Draw user name
    draw.text((150, 20), user.name, font=font_large, fill=(255, 255, 255))

    # Draw level
    draw.text((150, 60), f"Level: {level}", font=font_small, fill=(255, 215, 0))

    # Draw XP bar
    bar_x, bar_y = 150, 100
    bar_width, bar_height = 200, 20
    progress = xp / xp_required(level)
    draw.rectangle([bar_x, bar_y, bar_x+bar_width, bar_y+bar_height], fill=(100,100,100))
    draw.rectangle([bar_x, bar_y, bar_x+int(bar_width*progress), bar_y+bar_height], fill=(255,215,0))

    # Draw XP text
    draw.text((bar_x, bar_y-25), f"XP: {xp}/{xp_required(level)}", font=font_small, fill=(255,255,255))

    # Optional: user avatar
    asset = user.display_avatar.with_size(64)
    buffer = io.BytesIO()
    await asset.save(buffer, format="PNG")
    buffer.seek(0)
    avatar = Image.open(buffer).convert("RGBA")
    avatar = avatar.resize((100, 100))
    card.paste(avatar, (20, 25), avatar)

    # Save to bytes
    buffer_out = io.BytesIO()
    card.save(buffer_out, format="PNG")
    buffer_out.seek(0)
    return buffer_out

# ---------------- LEADERBOARD ---------------- #

@bot.tree.command(name="leaderboard")
async def leaderboard(interaction: discord.Interaction):

    cursor.execute("SELECT user_id, level, xp FROM users ORDER BY level DESC, xp DESC LIMIT 10")
    top = cursor.fetchall()

    embed = discord.Embed(title="🏆 Level Leaderboard", color=discord.Color.gold())

    for i, (user_id, level, xp) in enumerate(top, start=1):
        user = await bot.fetch_user(user_id)
        embed.add_field(
            name=f"#{i} {user.name}",
            value=f"Level {level} | XP: {xp}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

# ---------------- PROFILE ---------------- #

@bot.tree.command(name="profile")
async def profile(interaction: discord.Interaction):
    cursor.execute("SELECT xp, level FROM users WHERE user_id=?", (interaction.user.id,))
    data = cursor.fetchone()

    if not data:
        await interaction.response.send_message("No data yet.")
        return

    xp, level = data
    card_image = await generate_xp_card(interaction.user, xp, level)
    await interaction.response.send_message(file=discord.File(card_image, filename="profile.png"))

# ---------------- INTERNET QUIZ ---------------- #

@bot.tree.command(name="quiz")
async def quiz(interaction: discord.Interaction):

    await interaction.response.defer()

    async with aiohttp.ClientSession() as session:
        async with session.get("https://opentdb.com/api.php?amount=1&type=multiple") as resp:
            data = await resp.json()

    q = data["results"][0]

    question = html.unescape(q["question"])
    correct = html.unescape(q["correct_answer"])
    incorrect = [html.unescape(i) for i in q["incorrect_answers"]]

    options = incorrect + [correct]
    random.shuffle(options)

    class QuizView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=15)

        async def interaction_check(self, i):
            return i.user == interaction.user

    view = QuizView()

    for option in options:
        async def callback(i, opt=option):
            if opt == correct:
                add_xp(i.user.id, 100)
                await i.response.edit_message(content="✅ Correct! +100 XP", view=None)
            else:
                await i.response.edit_message(content=f"❌ Wrong! Answer: {correct}", view=None)

        button = discord.ui.Button(label=option, style=discord.ButtonStyle.primary)
        button.callback = callback
        view.add_item(button)

    await interaction.followup.send(f"🤯 **{question}**", view=view)

# ---------------- GIVEAWAY ---------------- #

class GiveawayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.entries = set()

    @discord.ui.button(label="🎉 Join Giveaway", style=discord.ButtonStyle.green)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.entries.add(interaction.user.id)
        await interaction.response.send_message("You joined!", ephemeral=True)

@bot.tree.command(name="giveaway")
@app_commands.describe(prize="Prize", minutes="Duration in minutes", winners="Number of winners")
async def giveaway(interaction: discord.Interaction, prize: str, minutes: int, winners: int):

    view = GiveawayView()
    end_time = asyncio.get_event_loop().time() + minutes * 60

    embed = discord.Embed(
        title="🎁 Giveaway",
        description=f"Prize: {prize}\nEnds in: {minutes}m",
        color=discord.Color.blurple()
    )

    msg = await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Giveaway started!", ephemeral=True)

    while True:
        remaining = int(end_time - asyncio.get_event_loop().time())
        if remaining <= 0:
            break

        embed.description = f"Prize: {prize}\nEnds in: {remaining // 60}m {remaining % 60}s\nEntries: {len(view.entries)}"
        await msg.edit(embed=embed)
        await asyncio.sleep(30)

    view.stop()
    await msg.edit(view=None)

    if view.entries:
        winners_list = random.sample(list(view.entries), min(winners, len(view.entries)))
        mentions = " ".join(f"<@{w}>" for w in winners_list)
        await interaction.channel.send(f"🏆 Winner(s): {mentions}")
    else:
        await interaction.channel.send("No participants.")

# ---------------- BOMB GAME ---------------- #

active_bomb = {}

@bot.tree.command(name="bomb_start")
async def bomb_start(interaction: discord.Interaction):

    if interaction.guild.id in active_bomb:
        await interaction.response.send_message("Game already running.")
        return

    holder = interaction.user
    active_bomb[interaction.guild.id] = holder.id

    await interaction.response.send_message(f"💣 {holder.mention} has the bomb!")

    await asyncio.sleep(30)

    if interaction.guild.id in active_bomb:
        loser_id = active_bomb.pop(interaction.guild.id)
        await interaction.channel.send(f"💥 <@{loser_id}> exploded!")

@bot.tree.command(name="bomb_pass")
async def bomb_pass(interaction: discord.Interaction, member: discord.Member):

    if interaction.guild.id not in active_bomb:
        await interaction.response.send_message("No active game.")
        return

    if active_bomb[interaction.guild.id] != interaction.user.id:
        await interaction.response.send_message("You don't have the bomb!", ephemeral=True)
        return

    active_bomb[interaction.guild.id] = member.id
    await interaction.response.send_message(f"💣 Bomb passed to {member.mention}")

# ---------------- INFECTION ---------------- #

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = message.guild.id
    if guild_id in infected:
        # Check if the message mentions someone infected
        if any(user_id in [u.id for u in message.mentions] for user_id in infected[guild_id]):
            infected[guild_id].add(message.author.id)
            await message.channel.send(f"🧟 {message.author.mention} just got infected!")mention} is infected!"
    )

# ---------------- COURT ---------------- #

@bot.tree.command(name="accuse")
async def accuse(interaction: discord.Interaction, member: discord.Member, reason: str):

    embed = discord.Embed(
        title="⚖ Court Case",
        description=f"{member.mention} is accused of {reason}!\n\nReact 👍 Criminal | 👎 Innocent",
        color=discord.Color.red()
    )

    # Send embed as interaction response
    await interaction.response.send_message(embed=embed)

    # Fetch the message object just sent
    msg = await interaction.original_response()
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

# ---------------- READY ---------------- #

@bot.event
async def on_ready():
    # Only sync once
    try:
        await bot.tree.sync()
        print(f"Commands synced!")
    except Exception as e:
        print(e)

keep_alive()
bot.run(TOKEN)
