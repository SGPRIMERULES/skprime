from keep_alive import keep_alive
keep_alive()

import os
import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import aiohttp
import html
import io
from PIL import Image, ImageDraw, ImageFont
import databases

# ---------------- BOT SETUP ---------------- #
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
TOKEN = os.environ.get("TOKEN")

# ---------------- DATABASE SETUP (PostgreSQL) ---------------- #
DATABASE_URL = os.environ.get("DATABASE_URL")  # Set in Render Environment Variables
db = databases.Database(DATABASE_URL)
xp_cooldown = {}

async def setup_database():
    await db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        xp INT DEFAULT 0,
        level INT DEFAULT 1
    )
    """)

# ---------------- XP LOGIC ---------------- #
def xp_required(level):
    return int(100 * (level ** 1.5))

async def add_xp(user_id, amount):
    query = "SELECT xp, level FROM users WHERE user_id = :user_id"
    data = await db.fetch_one(query, values={"user_id": user_id})

    if not data:
        xp = 0
        level = 1
        await db.execute(
            "INSERT INTO users(user_id, xp, level) VALUES(:user_id, :xp, :level)",
            values={"user_id": user_id, "xp": xp, "level": level}
        )
    else:
        xp = data["xp"]
        level = data["level"]

    xp += amount
    leveled_up = False
    while xp >= xp_required(level):
        xp -= xp_required(level)
        level += 1
        leveled_up = True

    await db.execute(
        "UPDATE users SET xp=:xp, level=:level WHERE user_id=:user_id",
        values={"xp": xp, "level": level, "user_id": user_id}
    )

    return leveled_up, level, xp

async def get_user_data(user_id):
    query = "SELECT xp, level FROM users WHERE user_id = :user_id"
    return await db.fetch_one(query, values={"user_id": user_id})

# ---------------- RANK CARD ---------------- #
async def create_rank_card(member, xp, level):
    width, height = 900, 300
    bg = Image.new("RGB", (width, height), (15, 15, 25))
    draw = ImageDraw.Draw(bg)

    async with aiohttp.ClientSession() as session:
        async with session.get(member.display_avatar.url) as resp:
            avatar_bytes = await resp.read()

    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((200, 200))
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

# ---------------- LEADERBOARD ---------------- #
async def create_leaderboard(guild):
    width, height = 900, 600
    bg = Image.new("RGB", (width, height), (20, 20, 30))
    draw = ImageDraw.Draw(bg)
    font = ImageFont.load_default()

    query = "SELECT user_id, level, xp FROM users ORDER BY level DESC, xp DESC LIMIT 10"
    top_users = await db.fetch_all(query)

    draw.text((350, 20), "SERVER LEADERBOARD", fill=(255, 255, 255), font=font)

    y = 80
    position = 1

    for user in top_users:
        user_id, level, xp = user["user_id"], user["level"], user["xp"]
        member = guild.get_member(user_id)
        if not member:
            continue
        draw.text((100, y), f"#{position}  {member.name}  |  Level {level}  ({xp} XP)", fill=(200, 200, 255), font=font)
        y += 45
        position += 1

    buffer = io.BytesIO()
    bg.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# ---------------- XP ON MESSAGE ---------------- #
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = asyncio.get_event_loop().time()
    if message.author.id not in xp_cooldown or now - xp_cooldown[message.author.id] > 30:
        xp_cooldown[message.author.id] = now
        leveled_up, level, xp = await add_xp(message.author.id, random.randint(10, 20))
        if leveled_up:
            card = await create_rank_card(message.author, xp, level)
            await message.channel.send(content=f"🎉 {message.author.mention} leveled up!", file=discord.File(card, "levelup.png"))

    await bot.process_commands(message)

# ---------------- KEEP ALL OTHER COMMANDS ---------------- #
# (Paste all your /profile, /leaderboard, /quiz, giveaway, bomb, infection, accuse commands exactly as before)
# Nothing changes here, PostgreSQL handles XP persistence automatically

# ---------------- RUN BOT ---------------- #
async def main():
    await db.connect()        # Connect to PostgreSQL
    await setup_database()    # Setup tables if missing
    async with bot:
        await bot.start(TOKEN)
    await db.disconnect()     # Disconnect safely

asyncio.run(main())
