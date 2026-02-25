from keep_alive import keep_alive
keep_alive()

import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import random
import asyncio
import os
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import html
from flask import Flask
from threading import Thread

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

# ================== XP SYSTEM ================== #

import random
import asyncio
from PIL import Image, ImageDraw, ImageFont
import aiohttp
import io

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

    return leveled_up, level, xp


# ================== RANK CARD IMAGE ================== #

async def create_rank_card(member, xp, level):
    width, height = 900, 300
    bg = Image.new("RGB", (width, height), (15, 15, 25))
    draw = ImageDraw.Draw(bg)

    # Fetch avatar
    async with aiohttp.ClientSession() as session:
        async with session.get(member.display_avatar.url) as resp:
            avatar_bytes = await resp.read()

    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    avatar = avatar.resize((200, 200))

    mask = Image.new("L", avatar.size, 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 200, 200), fill=255)
    bg.paste(avatar, (50, 50), mask)

    font_big = ImageFont.load_default()
    font_small = ImageFont.load_default()

    draw.text((300, 60), member.name, fill=(255, 255, 255), font=font_big)
    draw.text((300, 100), f"Level: {level}", fill=(180, 180, 255), font=font_small)

    xp_needed = xp_required(level)
    bar_width = 500
    filled = int((xp / xp_needed) * bar_width)

    draw.rectangle((300, 150, 300 + bar_width, 190), fill=(40, 40, 60))
    draw.rectangle((300, 150, 300 + filled, 190), fill=(100, 100, 255))

    draw.text((300, 200), f"{xp}/{xp_needed} XP", fill=(200, 200, 200), font=font_small)

    buffer = io.BytesIO()
    bg.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# ================== LEADERBOARD IMAGE ================== #

async def create_leaderboard(guild):
    width, height = 900, 600
    bg = Image.new("RGB", (width, height), (20, 20, 30))
    draw = ImageDraw.Draw(bg)
    font = ImageFont.load_default()

    cursor.execute(
        "SELECT user_id, level, xp FROM users ORDER BY level DESC, xp DESC LIMIT 10"
    )
    top_users = cursor.fetchall()

    draw.text((350, 20), "SERVER LEADERBOARD", fill=(255, 255, 255), font=font)

    y = 80
    position = 1

    for user_id, level, xp in top_users:
        member = guild.get_member(user_id)
        if not member:
            continue

        draw.text(
            (100, y),
            f"#{position}  {member.name}  |  Level {level}  ({xp} XP)",
            fill=(200, 200, 255),
            font=font
        )
        y += 45
        position += 1

    buffer = io.BytesIO()
    bg.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# ================== XP MESSAGE EVENT ================== #

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = asyncio.get_event_loop().time()

    if message.author.id not in xp_cooldown or now - xp_cooldown[message.author.id] > 30:
        xp_cooldown[message.author.id] = now

        leveled_up, level, xp = add_xp(
            message.author.id,
            random.randint(10, 20)
        )

        if leveled_up:
            card = await create_rank_card(message.author, xp, level)
            await message.channel.send(
                content=f"🎉 {message.author.mention} leveled up!",
                file=discord.File(card, "levelup.png")
            )

    await bot.process_commands(message)


# ================== /PROFILE COMMAND ================== #

@tree.command(name="profile", description="View your rank card")
async def profile(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user

    cursor.execute("SELECT xp, level FROM users WHERE user_id=?", (member.id,))
    data = cursor.fetchone()

    if not data:
        await interaction.response.send_message("No XP data found.", ephemeral=True)
        return

    xp, level = data
    card = await create_rank_card(member, xp, level)

    await interaction.response.send_message(file=discord.File(card, "rank.png"))


# ================== /LEADERBOARD COMMAND ================== #

@tree.command(name="leaderboard", description="View top XP users")
async def leaderboard(interaction: discord.Interaction):
    card = await create_leaderboard(interaction.guild)
    await interaction.response.send_message(file=discord.File(card, "leaderboard.png"))
    )

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

infected = {}

@bot.tree.command(name="infection_start")
async def infection_start(interaction: discord.Interaction):

    infected[interaction.guild.id] = {interaction.user.id}
    await interaction.response.send_message(
        f"🧟 Infection started! {interaction.user.mention} is infected!"
    )

# ---------------- COURT ---------------- #

@bot.tree.command(name="accuse")
async def accuse(interaction: discord.Interaction, member: discord.Member, reason: str):

    embed = discord.Embed(
        title="⚖ Court Case",
        description=f"{member.mention} is accused of {reason}!\n\nReact 👍 Innocent | 👎 Guilty",
        color=discord.Color.red()
    )

    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")

    await interaction.response.send_message("Case started!", ephemeral=True)

# ---------------- READY ---------------- #

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

keep_alive()
bot.run(TOKEN)
