# ===============================
# 🔹 IMPORTS
# ===============================
import asyncio
import uuid
import discord
from discord.ext import commands, tasks
from discord import Embed, app_commands
from groq import Groq

import os
import time
import random
import sqlite3
from dotenv import load_dotenv

# ===============================
# 🔹 ENV
# ===============================
load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
FEEDBACK_CHANNEL_ID = int(os.getenv("FEEDBACK_CHANNEL_ID"))
OWNER_ID = int(os.getenv("OWNER_ID"))

# ===============================
# 🔹 BOT CONFIG
# ===============================
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="~", intents=intents)
groq = Groq(api_key=GROQ_API_KEY)

START_TIME = time.time()
BOT_VERSION = "v5.1.0 PUBLIC PREMIUM"
# ===============================
# 🏴‍☠️ CAÇA AO TESOURO
# ===============================
TESOURO_COOLDOWN = 6 * 60 * 60  # 6 horas

# ===============================
# 🔹 DATABASE (SQLITE)
# ===============================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "bot.db")

db = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    coins INTEGER DEFAULT 0,
    banco INTEGER DEFAULT 0,
    xp INTEGER DEFAULT 0,
    last_daily REAL DEFAULT 0,
    last_weekly REAL DEFAULT 0,
    last_work REAL DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS vip (
    user_id INTEGER PRIMARY KEY,
    nivel INTEGER,
    expires REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS ia_memoria (
    user_id INTEGER,
    role TEXT,
    content TEXT
)
""")

db.commit()
cursor.execute("""
CREATE TABLE IF NOT EXISTS investimentos (
    user_id INTEGER,
    valor INTEGER,
    timestamp REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS modlog (
    guild_id INTEGER,
    channel_id INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS ia_personalidade (
    user_id INTEGER PRIMARY KEY,
    prompt TEXT
)
""")

db.commit()
# ===============================
# 🔹 MODERAÇÃO / AUTOMATIZAÇÃO
# ===============================

cursor.execute("""
CREATE TABLE IF NOT EXISTS warns (
    user_id INTEGER,
    staff_id INTEGER,
    motivo TEXT,
    data REAL
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS auto_anuncios (
    guild_id INTEGER,
    channel_id INTEGER,
    mensagem TEXT,
    intervalo INTEGER
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS clans (
    clan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT UNIQUE,
    lider_id INTEGER,
    xp INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS clan_membros (
    clan_id INTEGER,
    user_id INTEGER
)
""")

db.commit()
cursor.execute("""
CREATE TABLE IF NOT EXISTS cacador (
    user_id INTEGER PRIMARY KEY,
    last_hunt REAL DEFAULT 0
)
""")
db.commit()


# ===============================
# 🔹 VIP CONFIG
# ===============================
VIP_NOMES = {
    1: "Bronze",
    2: "Ouro",
    3: "Diamante",
    4: "Ultimate"
}

VIP_MULTIPLIER = {
    1: 1.2,
    2: 1.4,
    3: 1.7,
    4: 2.0
}

# ===============================
# 🔹 ECONOMIA BASE (PixCoin)
# ===============================
def get_user(uid: int):
    cursor.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (uid,)
    )
    db.commit()

def saldo(uid: int) -> int:
    get_user(uid)
    cursor.execute("SELECT coins FROM users WHERE user_id=?", (uid,))
    return cursor.fetchone()[0]

def banco(uid: int) -> int:
    get_user(uid)
    cursor.execute("SELECT banco FROM users WHERE user_id=?", (uid,))
    return cursor.fetchone()[0]

def add_saldo(uid: int, valor: int):
    get_user(uid)
    cursor.execute(
        "UPDATE users SET coins = coins + ? WHERE user_id=?",
        (valor, uid)
    )
    db.commit()

def add_banco(uid: int, valor: int):
    get_user(uid)
    cursor.execute(
        "UPDATE users SET banco = banco + ? WHERE user_id=?",
        (valor, uid)
    )
    db.commit()

# ===============================
# 🔹 VIP FUNÇÕES
# ===============================
def is_vip(uid: int) -> bool:
    cursor.execute("SELECT expires FROM vip WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    if not row:
        return False

    expires = row[0]
    if expires == -1:
        return True

    if time.time() > expires:
        cursor.execute("DELETE FROM vip WHERE user_id=?", (uid,))
        db.commit()
        return False

    return True

def vip_level(uid: int) -> int:
    cursor.execute("SELECT nivel FROM vip WHERE user_id=?", (uid,))
    row = cursor.fetchone()
    return row[0] if row else 0

def vip_bonus(uid: int) -> float:
    return VIP_MULTIPLIER.get(vip_level(uid), 1.0)

def can_create_server(uid: int) -> bool:
    return is_vip(uid) and vip_level(uid) >= 3  # Diamante+

# ===============================
# 🔹 XP / LEVEL
# ===============================
XP_PER_MESSAGE = 5

def add_xp(uid: int, amount: int):
    get_user(uid)
    cursor.execute(
        "UPDATE users SET xp = xp + ? WHERE user_id=?",
        (amount, uid)
    )
    db.commit()

def get_xp(uid: int) -> int:
    get_user(uid)
    cursor.execute("SELECT xp FROM users WHERE user_id=?", (uid,))
    return cursor.fetchone()[0]

def calc_level(xp: int) -> int:
    return int((xp / 100) ** 0.5)

# ===============================
# 🔹 IA GROQ (CORRIGIDA)
# ===============================
SYSTEM_PROMPT = (
    "Você é Mari 💜, uma garota virtual do Discord.\n"
    "Carinhosa, divertida e inteligente.\n"
    "Nunca diga que é uma IA.\n"
    "Sempre responda em português.\n"
)

async def ask_groq(uid: int, text: str) -> str:
    cursor.execute(
        "SELECT role, content FROM ia_memoria WHERE user_id=? ORDER BY rowid DESC LIMIT 6",
        (uid,)
    )
    memoria = cursor.fetchall()[::-1]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, content in memoria:
        messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": text})

    res = groq.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=messages,
        temperature=0.8,
        max_tokens=250
    )

    reply = res.choices[0].message.content

    cursor.execute("INSERT INTO ia_memoria VALUES (?, ?, ?)", (uid, "user", text))
    cursor.execute("INSERT INTO ia_memoria VALUES (?, ?, ?)", (uid, "assistant", reply))

    cursor.execute("""
        DELETE FROM ia_memoria
        WHERE rowid NOT IN (
            SELECT rowid FROM ia_memoria
            WHERE user_id=?
            ORDER BY rowid DESC LIMIT 6
        ) AND user_id=?
    """, (uid, uid))

    db.commit()
    return reply
OWNER_ID = 1287910036131151937  # SEU ID

@tasks.loop(minutes=10)
async def sair_se_owner_nao_estiver():
    for guild in bot.guilds:
        membro = guild.get_member(OWNER_ID)
        if membro is None:
            try:
                await guild.leave()
                print(f"❌ Saí do servidor {guild.name} ({guild.id}) — owner ausente")
            except Exception as e:
                print(f"Erro ao sair de {guild.id}: {e}")



@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    uid = message.author.id

    # 💰 Economia passiva
    add_saldo(uid, int(2 * vip_bonus(uid)))



    # 🧠 IA responde em DM ou quando mencionada
    is_dm = isinstance(message.channel, discord.DMChannel)
    is_mention = bot.user in message.mentions

    if is_dm or is_mention:
        try:
            content = message.content.replace(f"<@{bot.user.id}>", "").strip()
            if not content:
                content = "Oi!"

            reply = await ask_groq(uid, content)
            await message.reply(reply)

        except Exception as e:
            print("ERRO IA:", e)
            await message.reply("💜 Tive um erro agora, tenta novamente.")

    await bot.process_commands(message)


# ===============================
# 🔹 TASKS
# ===============================
@tasks.loop(minutes=30)
async def juros():
    cursor.execute("UPDATE users SET banco = banco * 1.02")
    db.commit()

# ===============================
# 🔹 READY
# ===============================
@bot.event
async def on_ready():
    await bot.tree.sync()
    juros.start()
    print("✅ BOT ONLINE | SISTEMA PREMIUM ATIVO")
# ===============================
# 🤖 UTILIDADE
# ===============================

@bot.tree.command(description="⏱️ Tempo online do bot")
async def uptime(i: discord.Interaction):
    secs = int(time.time() - START_TIME)
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    await i.response.send_message(
        f"⏱️ Bot online há **{h}h {m}m {s}s**",
        ephemeral=True
    )


@bot.tree.command(description="🔗 Convidar o bot")
async def invite(i: discord.Interaction):
    link = discord.utils.oauth_url(
        bot.user.id,
        permissions=discord.Permissions(administrator=True)
    )
    await i.response.send_message(link, ephemeral=True)


@bot.tree.command(description="🆘 Servidor de suporte")
async def support(i: discord.Interaction):
    await i.response.send_message(
        "🆘 Servidor de suporte:\nhttps://discord.gg/UY9eVV2j",
        ephemeral=True
    )


@bot.tree.command(description="💡 Enviar feedback")
async def feedback(i: discord.Interaction, mensagem: str):
    canal = bot.get_channel(FEEDBACK_CHANNEL_ID)
    if not canal:
        return await i.response.send_message(
            "❌ Canal de feedback não configurado.",
            ephemeral=True
        )

    embed = discord.Embed(
        title="💡 Feedback recebido",
        description=mensagem,
        color=discord.Color.green()
    )
    embed.set_author(
        name=f"{i.user} ({i.user.id})",
        icon_url=i.user.display_avatar.url
    )

    await canal.send(embed=embed)
    await i.response.send_message(
        "✅ Feedback enviado com sucesso!",
        ephemeral=True
    )

# ===============================
# 💰 ECONOMIA (PixCoin)
# ===============================

@bot.tree.command(description="💰 Ver saldo")
async def saldo_cmd(i: discord.Interaction):
    await i.response.send_message(
        f"💰 Carteira: **{saldo(i.user.id)}**\n"
        f"🏦 Banco: **{banco(i.user.id)}**",
        ephemeral=True
    )


@bot.tree.command(description="🎁 Daily")
async def daily(i: discord.Interaction):
    cursor.execute("SELECT last_daily FROM users WHERE user_id=?", (i.user.id,))
    last = cursor.fetchone()[0]
    now = time.time()

    if now - last < 86400:
        return await i.response.send_message("⏳ Daily já coletado.", ephemeral=True)

    ganho = int(500 * vip_bonus(i.user.id))
    add_saldo(i.user.id, ganho)

    cursor.execute(
        "UPDATE users SET last_daily=? WHERE user_id=?",
        (now, i.user.id)
    )
    db.commit()

    await i.response.send_message(f"🎁 Você ganhou **{ganho} PixCoins**!")


@bot.tree.command(description="🎁 Weekly")
async def weekly(i: discord.Interaction):
    cursor.execute("SELECT last_weekly FROM users WHERE user_id=?", (i.user.id,))
    last = cursor.fetchone()[0]
    now = time.time()

    if now - last < 604800:
        return await i.response.send_message("⏳ Weekly já coletado.", ephemeral=True)

    ganho = int(2500 * vip_bonus(i.user.id))
    add_saldo(i.user.id, ganho)

    cursor.execute(
        "UPDATE users SET last_weekly=? WHERE user_id=?",
        (now, i.user.id)
    )
    db.commit()

    await i.response.send_message(f"🎁 Você ganhou **{ganho} PixCoins**!")


@bot.tree.command(description="💼 Trabalhar")
async def work(i: discord.Interaction):
    cursor.execute("SELECT last_work FROM users WHERE user_id=?", (i.user.id,))
    last = cursor.fetchone()[0]
    now = time.time()

    if now - last < 3600:
        return await i.response.send_message("⏳ Você já trabalhou.", ephemeral=True)

    ganho = int(random.randint(300, 700) * vip_bonus(i.user.id))
    add_saldo(i.user.id, ganho)

    cursor.execute(
        "UPDATE users SET last_work=? WHERE user_id=?",
        (now, i.user.id)
    )
    db.commit()

    await i.response.send_message(f"💼 Você ganhou **{ganho} PixCoins**!")


@bot.tree.command(description="🚔 Crime")
async def crime(i: discord.Interaction):
    if random.random() < 0.5:
        perda = random.randint(200, 500)
        add_saldo(i.user.id, -perda)
        await i.response.send_message(f"🚔 Você perdeu **{perda} PixCoins**!")
    else:
        ganho = random.randint(400, 900)
        add_saldo(i.user.id, ganho)
        await i.response.send_message(f"💰 Você ganhou **{ganho} PixCoins**!")


@bot.tree.command(description="💸 Pagar usuário")
async def pay(i: discord.Interaction, user: discord.Member, valor: int):
    if valor <= 0 or saldo(i.user.id) < valor:
        return await i.response.send_message("❌ Valor inválido.", ephemeral=True)

    add_saldo(i.user.id, -valor)
    add_saldo(user.id, valor)
    await i.response.send_message(
        f"💸 Você transferiu **{valor} PixCoins** para {user.mention}"
    )


@bot.tree.command(description="🏦 Depositar")
async def deposit(i: discord.Interaction, valor: int):
    if valor <= 0 or saldo(i.user.id) < valor:
        return await i.response.send_message("❌ Valor inválido.", ephemeral=True)

    add_saldo(i.user.id, -valor)
    add_banco(i.user.id, valor)
    await i.response.send_message(f"🏦 Depositado **{valor} PixCoins**!")


@bot.tree.command(description="🏧 Sacar")
async def withdraw(i: discord.Interaction, valor: int):
    if valor <= 0 or banco(i.user.id) < valor:
        return await i.response.send_message("❌ Valor inválido.", ephemeral=True)

    add_banco(i.user.id, -valor)
    add_saldo(i.user.id, valor)
    await i.response.send_message(f"🏧 Sacado **{valor} PixCoins**!")


@bot.tree.command(description="🏆 Ranking de PixCoins")
async def ranking(i: discord.Interaction):
    cursor.execute(
        "SELECT user_id, coins + banco FROM users ORDER BY coins + banco DESC LIMIT 10"
    )
    rows = cursor.fetchall()

    desc = ""
    for pos, (uid, total) in enumerate(rows, 1):
        user = bot.get_user(uid)
        desc += f"**{pos}.** {user.name if user else uid} — {int(total)}\n"

    embed = discord.Embed(
        title="🏆 Ranking Global",
        description=desc,
        color=discord.Color.gold()
    )
    await i.response.send_message(embed=embed)


@bot.tree.command(description="🎲 Apostar (cara ou coroa)")
@app_commands.describe(
    escolha="Escolha cara ou coroa"
)
async def apostar(
    i: discord.Interaction,
    valor: int,
    escolha: str
):
    escolha = escolha.lower()

    if escolha not in ("cara", "coroa"):
        return await i.response.send_message(
            "❌ Escolha **cara** ou **coroa**.",
            ephemeral=True
        )

    if valor <= 0 or saldo(i.user.id) < valor:
        return await i.response.send_message("❌ Aposta inválida.", ephemeral=True)

    add_saldo(i.user.id, -valor)
    resultado = random.choice(["cara", "coroa"])

    if escolha == resultado:
        ganho = int(valor * 2 * vip_bonus(i.user.id))
        add_saldo(i.user.id, ganho)
        await i.response.send_message(
            f"🎉 Deu **{resultado}**!\nVocê ganhou **{ganho} PixCoins**!"
        )
    else:
        await i.response.send_message(
            f"😢 Deu **{resultado}**...\nVocê perdeu **{valor} PixCoins**."
        )

# ===============================
# 👑 VIP
# ===============================

@bot.tree.command(description="👑 Informações do VIP")
async def vip_info(i: discord.Interaction):
    nivel = vip_level(i.user.id)
    nome = VIP_NOMES.get(nivel, "Nenhum")

    await i.response.send_message(
        f"👑 VIP: **{nome}**\n"
        f"📈 Multiplicador: **{vip_bonus(i.user.id)}x**",
        ephemeral=True
    )


@bot.tree.command(description="🛒 Loja VIP")
async def vip_loja(i: discord.Interaction):
    texto = ""
    for n, nome in VIP_NOMES.items():
        texto += f"**{nome}**\n"

    await i.response.send_message(texto, ephemeral=True)


@bot.tree.command(description="🪙 Comprar VIP (Admin)")
@app_commands.checks.has_permissions(administrator=True)
async def vip_comprar(
    i: discord.Interaction,
    user: discord.Member,
    nivel: app_commands.Range[int, 1, 4],
    dias: int
):
    exp = -1 if dias <= 0 else time.time() + dias * 86400

    cursor.execute(
        "REPLACE INTO vip (user_id, nivel, expires) VALUES (?, ?, ?)",
        (user.id, nivel, exp)
    )
    db.commit()

    await i.response.send_message(
        f"✅ {user.mention} recebeu VIP **{VIP_NOMES[nivel]}**!"
    )

# ===============================
# ⭐ XP / LEVEL
# ===============================

@bot.tree.command(description="⭐ Ver nível")
async def level(i: discord.Interaction):
    xp = get_xp(i.user.id)
    lvl = calc_level(xp)

    await i.response.send_message(
        f"⭐ XP: **{xp}**\n🎖️ Nível: **{lvl}**",
        ephemeral=True
    )


@bot.tree.command(description="⭐ Ranking de XP")
async def ranking_xp(i: discord.Interaction):
    cursor.execute(
        "SELECT user_id, xp FROM users ORDER BY xp DESC LIMIT 10"
    )
    rows = cursor.fetchall()

    desc = ""
    for pos, (uid, xp) in enumerate(rows, 1):
        user = bot.get_user(uid)
        desc += f"**{pos}.** {user.name if user else uid} — {xp} XP\n"

    embed = discord.Embed(
        title="⭐ Ranking de XP",
        description=desc,
        color=discord.Color.purple()
    )
    await i.response.send_message(embed=embed)

# ===============================
# 🛡️ MODERAÇÃO
# ===============================

@bot.tree.command(description="🧹 Limpar mensagens")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear(i: discord.Interaction, quantidade: app_commands.Range[int, 1, 100]):
    await i.channel.purge(limit=quantidade)
    await i.response.send_message(
        f"🧹 **{quantidade} mensagens apagadas**.",
        ephemeral=True
    )


@bot.tree.command(description="🔨 Banir usuário")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(i: discord.Interaction, user: discord.Member, motivo: str = "Não informado"):
    await user.ban(reason=motivo)
    await i.response.send_message(
        f"🔨 {user.mention} banido.\n📄 Motivo: {motivo}"
    )


@bot.tree.command(description="👢 Expulsar usuário")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(i: discord.Interaction, user: discord.Member, motivo: str = "Não informado"):
    await user.kick(reason=motivo)
    await i.response.send_message(
        f"👢 {user.mention} expulso.\n📄 Motivo: {motivo}"
    )


@bot.tree.command(description="⏳ Timeout")
@app_commands.checks.has_permissions(moderate_members=True)
async def timeout(i: discord.Interaction, user: discord.Member, minutos: int):
    until = discord.utils.utcnow() + discord.timedelta(minutes=minutos)
    await user.timeout(until)
    await i.response.send_message(
        f"⏳ {user.mention} em timeout por **{minutos} minutos**."
    )


@bot.tree.command(description="⏱️ Remover timeout")
@app_commands.checks.has_permissions(moderate_members=True)
async def untimeout(i: discord.Interaction, user: discord.Member):
    await user.timeout(None)
    await i.response.send_message(
        f"⏱️ Timeout removido de {user.mention}."
    )


@bot.tree.command(description="🐌 Slowmode")
@app_commands.checks.has_permissions(manage_channels=True)
async def slowmode(i: discord.Interaction, segundos: int):
    await i.channel.edit(slowmode_delay=segundos)
    await i.response.send_message(
        f"🐌 Slowmode definido para **{segundos}s**."
    )


@bot.tree.command(description="🔒 Trancar canal")
@app_commands.checks.has_permissions(manage_channels=True)
async def lock(i: discord.Interaction):
    await i.channel.set_permissions(
        i.guild.default_role,
        send_messages=False
    )
    await i.response.send_message("🔒 Canal trancado.")


@bot.tree.command(description="🔓 Destrancar canal")
@app_commands.checks.has_permissions(manage_channels=True)
async def unlock(i: discord.Interaction):
    await i.channel.set_permissions(
        i.guild.default_role,
        send_messages=True
    )
    await i.response.send_message("🔓 Canal destrancado.")
# ===============================
# 📖 HELP COM BOTÕES (MENU PREMIUM)
# ===============================

class HelpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="🤖 Utilidade", style=discord.ButtonStyle.primary)
    async def util(self, i: discord.Interaction, _):
        embed = discord.Embed(
            title="🤖 Utilidade",
            description="/uptime\n/invite\n/support\n/feedback",
            color=discord.Color.blurple()
        )
        await i.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="💰 Economia", style=discord.ButtonStyle.success)
    async def eco(self, i: discord.Interaction, _):
        embed = discord.Embed(
            title="💰 Economia • PixCoin",
            description=(
                "/saldo\n/daily\n/weekly\n/work\n/crime\n"
                "/pay\n/deposit\n/withdraw\n/ranking\n/apostar\n/mines"
            ),
            color=discord.Color.green()
        )
        await i.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="👑 VIP", style=discord.ButtonStyle.secondary)
    async def vip(self, i: discord.Interaction, _):
        embed = discord.Embed(
            title="👑 VIP",
            description=(
                "🥉 Bronze\n🥈 Ouro\n💎 Diamante\n👑 Ultimate\n\n"
                "**Comandos:**\n"
                "/vip_info\n/vip_loja\n/vip_comprar\n\n"
                "💎 Diamante+ → /criar_servidor"
            ),
            color=discord.Color.gold()
        )
        await i.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="⭐ XP", style=discord.ButtonStyle.primary)
    async def xp(self, i: discord.Interaction, _):
        embed = discord.Embed(
            title="⭐ XP / Level",
            description="/level\n/ranking_xp",
            color=discord.Color.purple()
        )
        await i.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🛡️ Moderação", style=discord.ButtonStyle.danger)
    async def mod(self, i: discord.Interaction, _):
        embed = discord.Embed(
            title="🛡️ Moderação",
            description=(
                "/clear\n/ban\n/kick\n/unban\n"
                "/timeout\n/untimeout\n"
                "/slowmode\n/lock\n/unlock"
            ),
            color=discord.Color.red()
        )
        await i.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🎫 Tickets", style=discord.ButtonStyle.secondary)
    async def tickets(self, i: discord.Interaction, _):
        embed = discord.Embed(
            title="🎫 Tickets",
            description="/ticket\n/close\n/adduser\n/removeuser",
            color=discord.Color.blurple()
        )
        await i.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🎉 Diversão", style=discord.ButtonStyle.success)
    async def fun(self, i: discord.Interaction, _):
        embed = discord.Embed(
            title="🎉 Diversão",
            description="/dice\n/8ball\n/ship\n/mines",
            color=discord.Color.green()
        )
        await i.response.edit_message(embed=embed, view=self)


@bot.tree.command(description="📖 Central de ajuda interativa")
async def help(i: discord.Interaction):
    embed = discord.Embed(
        title="📖 Central de Ajuda",
        description="Use os botões abaixo para navegar.",
        color=discord.Color.blurple()
    )
    embed.set_footer(text=BOT_VERSION)
    await i.response.send_message(embed=embed, view=HelpView(), ephemeral=True)


# ===============================
# 🎫 TICKETS
# ===============================

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Abrir Ticket", style=discord.ButtonStyle.primary)
    async def abrir(self, i: discord.Interaction, _):
        guild = i.guild

        categoria = discord.utils.get(guild.categories, name="🎫 Tickets")
        if not categoria:
            categoria = await guild.create_category("🎫 Tickets")

        canal = await guild.create_text_channel(
            f"ticket-{i.user.name}".lower(),
            category=categoria,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                i.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
        )

        embed = discord.Embed(
            title="🎫 Ticket aberto",
            description="Explique seu problema e aguarde atendimento.",
            color=discord.Color.blurple()
        )
        await canal.send(embed=embed)

        await i.response.send_message(
            f"✅ Ticket criado: {canal.mention}",
            ephemeral=True
        )


@bot.tree.command(description="🎫 Painel de tickets")
async def ticket(i: discord.Interaction):
    embed = discord.Embed(
        title="🎫 Central de Suporte",
        description="Clique no botão abaixo para abrir um ticket.",
        color=discord.Color.blurple()
    )
    await i.response.send_message(embed=embed, view=TicketView())


@bot.tree.command(description="🔒 Fechar ticket")
@app_commands.checks.has_permissions(manage_channels=True)
async def close(i: discord.Interaction):
    await i.response.send_message("🔒 Ticket será fechado em 3 segundos...")
    await asyncio.sleep(3)
    await i.channel.delete()


@bot.tree.command(description="➕ Adicionar usuário ao ticket")
@app_commands.checks.has_permissions(manage_channels=True)
async def adduser(i: discord.Interaction, user: discord.Member):
    await i.channel.set_permissions(user, view_channel=True, send_messages=True)
    await i.response.send_message(f"➕ {user.mention} adicionado.")


@bot.tree.command(description="➖ Remover usuário do ticket")
@app_commands.checks.has_permissions(manage_channels=True)
async def removeuser(i: discord.Interaction, user: discord.Member):
    await i.channel.set_permissions(user, view_channel=False)
    await i.response.send_message(f"➖ {user.mention} removido.")

class SorteioView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.participantes = set()

    @discord.ui.button(label="🎉 Participar", style=discord.ButtonStyle.success)
    async def participar(self, i: discord.Interaction, _):
        if i.user.id in self.participantes:
            return await i.response.send_message(
                "❌ Você já está participando!", ephemeral=True
            )

        self.participantes.add(i.user.id)
        await i.response.send_message(
            "✅ Você entrou no sorteio!", ephemeral=True
        )
@bot.tree.command(description="🎉 Criar um sorteio")
@app_commands.checks.has_permissions(manage_guild=True)
async def criar_sorteio(
    i: discord.Interaction,
    premio: str,
    duracao_minutos: app_commands.Range[int, 1, 10080]
):
    view = SorteioView()

    embed = discord.Embed(
        title="🎉 SORTEIO ATIVO!",
        description=(
            f"🎁 **Prêmio:** {premio}\n"
            f"⏳ **Duração:** {duracao_minutos} minutos\n\n"
            "Clique no botão abaixo para participar!"
        ),
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Criado por {i.user}")

    await i.response.send_message(embed=embed, view=view)
    msg = await i.original_response()

    await asyncio.sleep(duracao_minutos * 60)

    if not view.participantes:
        return await msg.reply("❌ Sorteio encerrado sem participantes.")

    vencedor_id = random.choice(list(view.participantes))
    vencedor = await bot.fetch_user(vencedor_id)

    embed_final = discord.Embed(
        title="🎊 SORTEIO ENCERRADO!",
        description=f"🏆 Vencedor: {vencedor.mention}\n🎁 Prêmio: **{premio}**",
        color=discord.Color.green()
    )

    await msg.reply(embed=embed_final)

@bot.tree.command(description="⛔ Encerrar sorteio manualmente")
@app_commands.checks.has_permissions(manage_guild=True)
async def encerrar_sorteio(i: discord.Interaction):
    await i.response.send_message(
        "⛔ Sorteio encerrado manualmente.\n⚠️ Use **/reroll** se quiser sortear novamente."
    )

@bot.tree.command(description="🔁 Sortear novo vencedor (reroll)")
@app_commands.checks.has_permissions(manage_guild=True)
async def reroll(
    i: discord.Interaction,
    usuarios: str
):
    lista = [int(u.strip()) for u in usuarios.split(",") if u.strip().isdigit()]

    if not lista:
        return await i.response.send_message("❌ Nenhum usuário válido.")

    vencedor_id = random.choice(lista)
    vencedor = await bot.fetch_user(vencedor_id)

    await i.response.send_message(
        f"🔁 **REROLL!**\n🏆 Novo vencedor: {vencedor.mention}"
    )

class EmbedButtonView(discord.ui.View):
    def __init__(self, label: str, url: str):
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.link,
                url=url
            )
        )
class MultiButtonView(discord.ui.View):
    def __init__(self, botoes: list):
        super().__init__(timeout=None)
        for label, url in botoes:
            self.add_item(
                discord.ui.Button(
                    label=label,
                    style=discord.ButtonStyle.link,
                    url=url
                )
            )
class ColorSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.color = discord.Color.blurple()

    @discord.ui.button(label="🔴 Vermelho", style=discord.ButtonStyle.danger)
    async def red(self, i: discord.Interaction, _):
        self.color = discord.Color.red()
        await i.response.defer()

    @discord.ui.button(label="🟢 Verde", style=discord.ButtonStyle.success)
    async def green(self, i: discord.Interaction, _):
        self.color = discord.Color.green()
        await i.response.defer()

    @discord.ui.button(label="🔵 Azul", style=discord.ButtonStyle.primary)
    async def blue(self, i: discord.Interaction, _):
        self.color = discord.Color.blue()
        await i.response.defer()

    @discord.ui.button(label="🟣 Roxo", style=discord.ButtonStyle.secondary)
    async def purple(self, i: discord.Interaction, _):
        self.color = discord.Color.purple()
        await i.response.defer()

# ===============================
# 🎉 DIVERSÃO
# ===============================

@bot.tree.command(description="🎲 Rolar dado")
async def dice(i: discord.Interaction):
    n = random.randint(1, 6)
    await i.response.send_message(f"🎲 Você tirou **{n}**!")


@bot.tree.command(name="8ball", description="🎱 Bola mágica")
async def eightball(i: discord.Interaction, pergunta: str):
    respostas = ["Sim ✅", "Não ❌", "Talvez 🤔", "Com certeza 🔥", "Pergunte depois ⏳"]
    await i.response.send_message(
        f"🎱 **Pergunta:** {pergunta}\n**Resposta:** {random.choice(respostas)}"
    )


@bot.tree.command(description="💞 Shipar usuários")
async def ship(i: discord.Interaction, u1: discord.Member, u2: discord.Member):
    porcentagem = random.randint(0, 100)
    await i.response.send_message(
        f"💞 **{u1.display_name} + {u2.display_name}**\n"
        f"❤️ Compatibilidade: **{porcentagem}%**"
    )


# ===============================
# 💣 MINES 4x4 (ESCOLHE MINAS)
# ===============================

@bot.tree.command(description="💣 Mines 4x4 (escolha minas)")
async def mines(
    i: discord.Interaction,
    posicao: app_commands.Range[int, 1, 16],
    minas: app_commands.Range[int, 1, 15],
    aposta: int
):
    if aposta <= 0 or saldo(i.user.id) < aposta:
        return await i.response.send_message(
            "❌ Aposta inválida.",
            ephemeral=True
        )

    add_saldo(i.user.id, -aposta)

    bombas = random.sample(range(1, 17), minas)
    multiplicador = (1 + minas * 0.35) * vip_bonus(i.user.id)

    tab = ""
    for n in range(1, 17):
        if n == posicao:
            tab += "💣 " if n in bombas else "💎 "
        else:
            tab += "⬜ "
        if n % 4 == 0:
            tab += "\n"

    if posicao in bombas:
        embed = discord.Embed(
            title="💥 BOOM!",
            description=tab,
            color=discord.Color.red()
        )
        embed.add_field(
            name="Resultado",
            value=f"Você perdeu **{aposta} PixCoins**"
        )
    else:
        ganho = int(aposta * multiplicador)
        add_saldo(i.user.id, ganho)

        embed = discord.Embed(
            title="💎 Vitória!",
            description=tab,
            color=discord.Color.green()
        )
        embed.add_field(
            name="Resultado",
            value=f"Você ganhou **{ganho} PixCoins**"
        )

    embed.add_field(name="💣 Minas", value=minas)
    embed.add_field(name="📈 Multiplicador", value=f"x{multiplicador:.2f}")
    await i.response.send_message(embed=embed)


@bot.tree.command(description="🚀 Criar servidor completo (VIP Diamante+)")
async def criar_servidor(i: discord.Interaction):
    if not can_create_server(i.user.id):
        return await i.response.send_message(
            "❌ Apenas VIP **Diamante ou Ultimate**.",
            ephemeral=True
        )

    guild = i.guild

    info = await guild.create_category("📢 Informações")
    chat = await guild.create_category("💬 Chat")
    voz = await guild.create_category("🔊 Voz")
    staff = await guild.create_category("🛡️ Staff")

    regras = await guild.create_text_channel("📜-regras", category=info)
    anuncios = await guild.create_text_channel("📣-anuncios", category=info)
    logs = await guild.create_text_channel("📂-logs", category=staff)

    await guild.create_text_channel("💬-geral", category=chat)
    await guild.create_text_channel("📸-midia", category=chat)

    await guild.create_voice_channel("🔊 Geral", category=voz)
    await guild.create_voice_channel("🎮 Games", category=voz)

    embed_regras = discord.Embed(
        title="📜 Regras do Servidor",
        description=(
            "1️⃣ Respeite todos\n"
            "2️⃣ Sem spam\n"
            "3️⃣ Sem conteúdo proibido\n"
            "4️⃣ Siga as diretrizes do Discord"
        ),
        color=discord.Color.blurple()
    )
    embed_regras.set_footer(text="Servidor criado automaticamente")

    await regras.send(embed=embed_regras)

    await i.response.send_message(
        "🚀 **Servidor criado com sucesso!**\n"
        "📌 Estrutura completa configurada.",
        ephemeral=True
    )

@bot.tree.command(description="✨ Criar embed profissional (ADMIN)")
@app_commands.checks.has_permissions(administrator=True)
async def criar_embed(
    i: discord.Interaction,
    titulo: str,
    descricao: str,
    footer: str,
    autor: str,
    campo_nome: str = None,
    campo_valor: str = None,
    imagem: str = None,
    thumbnail: str = None,
    botao1_texto: str = None,
    botao1_link: str = None,
    botao2_texto: str = None,
    botao2_link: str = None
):
    color_view = ColorSelectView()

    await i.response.send_message(
        "🎨 **Escolha a cor da embed:**",
        view=color_view,
        ephemeral=True
    )

    await color_view.wait()

    embed = discord.Embed(
        title=titulo,
        description=descricao,
        color=color_view.color
    )

    embed.set_footer(text=footer)
    embed.set_author(name=autor, icon_url=i.user.display_avatar.url)

    if campo_nome and campo_valor:
        embed.add_field(name=campo_nome, value=campo_valor, inline=False)

    if imagem:
        embed.set_image(url=imagem)

    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    botoes = []
    if botao1_texto and botao1_link:
        botoes.append((botao1_texto, botao1_link))
    if botao2_texto and botao2_link:
        botoes.append((botao2_texto, botao2_link))

    view = MultiButtonView(botoes) if botoes else None

    await i.channel.send(embed=embed, view=view)


@bot.tree.command(description="📈 Investir PixCoins")
async def investir(i: discord.Interaction, valor: int):
    if valor <= 0 or saldo(i.user.id) < valor:
        return await i.response.send_message("❌ Valor inválido.")

    add_saldo(i.user.id, -valor)

    if random.random() < 0.45:
        perda = int(valor * random.uniform(0.3, 0.7))
        await i.response.send_message(f"📉 Investimento falhou! Você perdeu **{perda}**")
    else:
        ganho = int(valor * random.uniform(1.4, 2.5))
        add_saldo(i.user.id, ganho)
        await i.response.send_message(f"📈 Investimento deu certo! Lucro: **{ganho}**")

@bot.tree.command(description="👑 Transferir VIP")
async def vip_transferir(
    i: discord.Interaction,
    user: discord.Member
):
    if not is_vip(i.user.id):
        return await i.response.send_message(
            "❌ Você não possui VIP.",
            ephemeral=True
        )

    cursor.execute(
        "SELECT nivel, expires FROM vip WHERE user_id=?",
        (i.user.id,)
    )
    nivel, expires = cursor.fetchone()

    cursor.execute("DELETE FROM vip WHERE user_id=?", (i.user.id,))
    cursor.execute(
        "REPLACE INTO vip VALUES (?, ?, ?)",
        (user.id, nivel, expires)
    )
    db.commit()

    await i.response.send_message(
        f"👑 VIP **{VIP_NOMES[nivel]}** transferido para {user.mention}"
    )
@bot.tree.command(description="🛡️ Definir canal de modlog")
@app_commands.checks.has_permissions(administrator=True)
async def modlog(i: discord.Interaction, canal: discord.TextChannel):
    cursor.execute(
        "REPLACE INTO modlog VALUES (?, ?)",
        (i.guild.id, canal.id)
    )
    db.commit()

    await i.response.send_message(
        f"🛡️ ModLog definido para {canal.mention}",
        ephemeral=True
    )
@bot.tree.command(description="🧠 Definir personalidade da IA")
async def ia_personalidade(i: discord.Interaction, personalidade: str):
    cursor.execute(
        "REPLACE INTO ia_personalidade VALUES (?, ?)",
        (i.user.id, personalidade)
    )
    db.commit()

    await i.response.send_message(
        "🧠 Personalidade da IA atualizada!",
        ephemeral=True
    )
# ===============================
# 🧠 QUIZ GERAL (TUDO EM UM BLOCO)
# ===============================

@bot.tree.command(description="🧠 Quiz múltipla escolha com recompensa")
@app_commands.choices(categoria=[
    app_commands.Choice(name="Clássico 🌍", value="classico"),
    app_commands.Choice(name="Anime 🍥", value="anime"),
    app_commands.Choice(name="Matemática ➗", value="matematica"),
    app_commands.Choice(name="Jogos 🎮", value="jogos"),
])
async def quiz(
    i: discord.Interaction,
    categoria: app_commands.Choice[str],
    rodadas: app_commands.Range[int, 1, 20]
):
    perguntas = {
        "classico": [
            ("Qual é a capital do Brasil?",
             ["Brasília", "Rio de Janeiro", "São Paulo", "Salvador"], "a"),
            ("Qual é o maior planeta do sistema solar?",
             ["Júpiter", "Marte", "Saturno", "Terra"], "a"),
            ("Qual país tem a maior população?",
             ["Índia", "Estados Unidos", "China", "Rússia"], "c"),
            ("Quem pintou a Mona Lisa?",
             ["Van Gogh", "Picasso", "Michelangelo", "Leonardo da Vinci"], "d"),
            ("Qual é o maior oceano do mundo?",
             ["Atlântico", "Índico", "Ártico", "Pacífico"], "d"),
            ("Em que continente fica o Egito?",
             ["Europa", "Ásia", "África", "América"], "c"),
            ("Qual é o maior país do mundo?",
             ["Canadá", "China", "Estados Unidos", "Rússia"], "d"),
            ("Qual animal é o mais rápido?",
             ["Leão", "Guepardo", "Tigre", "Cavalo"], "b"),
            ("Qual planeta é o vermelho?",
             ["Marte", "Júpiter", "Vênus", "Mercúrio"], "a"),
            ("Qual gás é essencial para respiração?",
             ["Gás Carbônico", "Oxigênio", "Nitrogênio", "Hélio"], "b"),
        ],
        "anime": [
            ("Quem é o protagonista de Naruto?",
             ["Sasuke", "Kakashi", "Naruto", "Itachi"], "c"),
            ("Capitão dos Chapéus de Palha?",
             ["Zoro", "Luffy", "Sanji", "Ace"], "b"),
            ("Anime das Esferas do Dragão?",
             ["Naruto", "One Piece", "Dragon Ball", "Bleach"], "c"),
            ("Anime com caderno mortal?",
             ["Death Note", "Tokyo Ghoul", "Another", "Erased"], "a"),
            ("Rival do Goku?",
             ["Freeza", "Broly", "Vegeta", "Cell"], "c"),
            ("Pokémon do Ash?",
             ["Charmander", "Bulbasaur", "Pikachu", "Squirtle"], "c"),
            ("Autor de One Piece?",
             ["Kishimoto", "Oda", "Toriyama", "Togashi"], "b"),
            ("Anime com Titãs?",
             ["Naruto", "One Piece", "Attack on Titan", "Bleach"], "c"),
            ("Anime de caçadores?",
             ["Jujutsu", "HxH", "DBZ", "Black Clover"], "b"),
            ("Anime de heróis?",
             ["Berserk", "Baki", "One Punch Man", "Death Note"], "c"),
        ],
        "matematica": [
            ("Quanto é 9 x 7?",
             ["54", "56", "63", "72"], "c"),
            ("Quanto é 8 x 8?",
             ["64", "72", "56", "48"], "a"),
            ("Raiz de 81?",
             ["7", "8", "9", "10"], "c"),
            ("Quanto é 12 x 3?",
             ["30", "36", "24", "18"], "b"),
            ("Quanto é 100 - 45?",
             ["65", "45", "55", "50"], "c"),
            ("Quanto é 10 / 2?",
             ["2", "10", "8", "5"], "d"),
            ("Quanto é 6²?",
             ["12", "18", "36", "42"], "c"),
            ("Quanto é 7 x 6?",
             ["42", "36", "48", "40"], "a"),
            ("Quanto é 50 + 25?",
             ["65", "70", "75", "80"], "c"),
            ("Quanto é 4³?",
             ["16", "64", "32", "12"], "b"),
        ],
        "jogos": [
            ("Qual jogo tem blocos?",
             ["Terraria", "Roblox", "Minecraft", "Rust"], "c"),
            ("Mascote da Nintendo?",
             ["Sonic", "Crash", "Mario", "Link"], "c"),
            ("Battle Royale famoso?",
             ["CS", "GTA", "Fortnite", "Valorant"], "c"),
            ("Empresa do GTA?",
             ["Ubisoft", "EA", "Rockstar", "Valve"], "c"),
            ("Jogo com creepers?",
             ["Ark", "Minecraft", "Rust", "Raft"], "b"),
            ("Console da Sony?",
             ["Xbox", "Switch", "PlayStation", "Wii"], "c"),
            ("Jogo da Valve?",
             ["LoL", "Dota", "Fortnite", "Valorant"], "b"),
            ("FPS tático famoso?",
             ["Overwatch", "Valorant", "Apex", "PUBG"], "b"),
            ("Jogo com Ender Dragon?",
             ["Terraria", "Minecraft", "ARK", "Raft"], "b"),
            ("Jogo MOBA famoso?",
             ["CS", "LoL", "GTA", "Rust"], "b"),
        ],
    }

    total = 0
    letras = ["a", "b", "c", "d"]

    for rodada in range(1, rodadas + 1):
        pergunta, alternativas, correta = random.choice(perguntas[categoria.value])

        texto_alt = "\n".join([
            f"**{letras[i].upper()})** {alternativas[i]}"
            for i in range(4)
        ])

        await i.channel.send(
            f"🧠 **QUIZ — {categoria.name}**\n"
            f"🔁 Rodada **{rodada}/{rodadas}**\n\n"
            f"❓ {pergunta}\n\n"
            f"{texto_alt}\n\n"
            "✍️ Responda com **A/B/C/D** ou o texto"
        )

        def check(m):
            return m.author.id == i.user.id and m.channel.id == i.channel.id

        try:
            msg = await bot.wait_for("message", timeout=30.0, check=check)
            resp = msg.content.lower().strip()

            correta_texto = alternativas[letras.index(correta)].lower()

            if resp == correta or resp == correta_texto:
                ganho = random.randint(400, 500)
                premio = int(ganho * vip_bonus(i.user.id))
                add_saldo(i.user.id, premio)
                total += premio

                await msg.add_reaction("⭐")
                await i.channel.send(f"✅ **Correto!** ⭐ +{premio} PixCoins")
            else:
                await i.channel.send(
                    f"❌ Errado!\n"
                    f"✅ Resposta correta: **{correta.upper()}) {correta_texto.capitalize()}**"
                )

        except asyncio.TimeoutError:
            await i.channel.send(
                f"⏳ Tempo esgotado!\n"
                f"✅ Resposta correta: **{correta.upper()}) {correta_texto.capitalize()}**"
            )

        await i.channel.send("⏳ Próxima pergunta em **15 segundos**...")
        await asyncio.sleep(15)

    await i.channel.send(
        f"🏁 **Quiz finalizado!**\n"
        f"💰 Total ganho: **{total} PixCoins**"
    )

@bot.tree.command(description="👤 Informações do usuário")
async def userinfo(i: discord.Interaction, user: discord.Member = None):
    user = user or i.user
    xp = get_xp(user.id)

    embed = discord.Embed(
        title="👤 User Info",
        color=discord.Color.blurple()
    )
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="🆔 ID", value=user.id)
    embed.add_field(name="⭐ XP", value=xp)
    embed.add_field(name="🎖️ Level", value=calc_level(xp))
    embed.add_field(name="💰 PixCoin", value=saldo(user.id))
    embed.add_field(name="🏦 Banco", value=banco(user.id))
    embed.add_field(
        name="👑 VIP",
        value=VIP_NOMES.get(vip_level(user.id), "Nenhum")
    )

    await i.response.send_message(embed=embed)

@bot.tree.command(description="➕ Adicionar PixCoin a um usuário (ADMIN)")
@app_commands.checks.has_permissions(administrator=True)
async def add_pixcoin(
    i: discord.Interaction,
    user: discord.Member,
    valor: int
):
    if valor <= 0:
        return await i.response.send_message(
            "❌ O valor precisa ser maior que zero.",
            ephemeral=True
        )

    add_saldo(user.id, valor)

    await i.response.send_message(
        f"✅ **{valor} PixCoins** adicionados para {user.mention} 💰",
        ephemeral=True
    )
@bot.tree.command(description="🚫 Colocar usuário na blacklist (bloqueia mensagens)")
@app_commands.checks.has_permissions(administrator=True)
async def blacklist(i: discord.Interaction, user: discord.Member):
    guild = i.guild

    cargo = discord.utils.get(guild.roles, name="🚫 Blacklist")
    if not cargo:
        cargo = await guild.create_role(
            name="🚫 Blacklist",
            color=discord.Color.dark_red(),
            reason="Cargo de blacklist criado automaticamente"
        )

        for canal in guild.channels:
            await canal.set_permissions(
                cargo,
                send_messages=False,
                add_reactions=False,
                speak=False
            )

    if cargo in user.roles:
        return await i.response.send_message(
            "❌ Esse usuário já está na blacklist.",
            ephemeral=True
        )

    await user.add_roles(cargo)
    await i.response.send_message(
        f"🚫 {user.mention} foi colocado na **Blacklist**.",
        ephemeral=True
    )
@bot.tree.command(description="✅ Remover usuário da blacklist")
@app_commands.checks.has_permissions(administrator=True)
async def unblacklist(i: discord.Interaction, user: discord.Member):
    cargo = discord.utils.get(i.guild.roles, name="🚫 Blacklist")

    if not cargo or cargo not in user.roles:
        return await i.response.send_message(
            "❌ Esse usuário não está na blacklist.",
            ephemeral=True
        )

    await user.remove_roles(cargo)
    await i.response.send_message(
        f"✅ {user.mention} foi removido da **Blacklist**.",
        ephemeral=True
    )

@bot.tree.command(description="⚠️ Avisar um usuário")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(i: discord.Interaction, user: discord.Member, motivo: str):
    cursor.execute(
        "INSERT INTO warns VALUES (?, ?, ?, ?)",
        (user.id, i.user.id, motivo, time.time())
    )
    db.commit()

    embed = discord.Embed(
        title="⚠️ Aviso aplicado",
        color=discord.Color.orange()
    )
    embed.add_field(name="Usuário", value=user.mention)
    embed.add_field(name="Motivo", value=motivo)
    embed.set_footer(text=f"Staff: {i.user}")

    await i.response.send_message(embed=embed)
@bot.tree.command(description="🧹 Limpar mensagens de um usuário")
@app_commands.checks.has_permissions(manage_messages=True)
async def clear_user(
    i: discord.Interaction,
    user: discord.Member,
    quantidade: app_commands.Range[int, 1, 100]
):
    def check(m):
        return m.author == user

    await i.channel.purge(limit=quantidade, check=check)

    await i.response.send_message(
        f"🧹 {quantidade} mensagens de {user.mention} apagadas.",
        ephemeral=True
    )
@bot.tree.command(description="🚨 Lockdown geral (anti-raid)")
@app_commands.checks.has_permissions(administrator=True)
async def lockdown(i: discord.Interaction):
    for channel in i.guild.text_channels:
        await channel.set_permissions(
            i.guild.default_role,
            send_messages=False
        )

    embed = discord.Embed(
        title="🚨 LOCKDOWN ATIVO",
        description="Todos os canais foram trancados.",
        color=discord.Color.red()
    )

    await i.response.send_message(embed=embed)
@bot.tree.command(description="🕵️ Detectar contas suspeitas")
@app_commands.checks.has_permissions(moderate_members=True)
async def anti_fake(i: discord.Interaction, dias: int = 7):
    suspeitos = []

    for member in i.guild.members:
        if (discord.utils.utcnow() - member.created_at).days < dias:
            suspeitos.append(member.mention)

    desc = "\n".join(suspeitos) or "Nenhuma conta suspeita."

    embed = discord.Embed(
        title="🕵️ Anti-Fake",
        description=desc,
        color=discord.Color.dark_gold()
    )

    await i.response.send_message(embed=embed)
@bot.tree.command(description="🏰 Criar clã")
async def criar_cla(i: discord.Interaction, nome: str):
    try:
        cursor.execute(
            "INSERT INTO clans (nome, lider_id) VALUES (?, ?)",
            (nome, i.user.id)
        )
        clan_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO clan_membros VALUES (?, ?)",
            (clan_id, i.user.id)
        )
        db.commit()

        await i.response.send_message(f"🏰 Clã **{nome}** criado!")
    except:
        await i.response.send_message("❌ Nome já em uso.")
@bot.tree.command(description="📊 Informações do clã")
async def cla_info(i: discord.Interaction, nome: str):
    cursor.execute(
        "SELECT clan_id, lider_id, xp FROM clans WHERE nome=?",
        (nome,)
    )
    clan = cursor.fetchone()
    if not clan:
        return await i.response.send_message("❌ Clã não encontrado.")

    clan_id, lider, xp = clan
    cursor.execute(
        "SELECT COUNT(*) FROM clan_membros WHERE clan_id=?",
        (clan_id,)
    )
    membros = cursor.fetchone()[0]

    embed = discord.Embed(
        title=f"🏰 Clã {nome}",
        color=discord.Color.green()
    )
    embed.add_field(name="👑 Líder", value=f"<@{lider}>")
    embed.add_field(name="👥 Membros", value=membros)
    embed.add_field(name="⭐ XP", value=xp)

    await i.response.send_message(embed=embed)
@bot.tree.command(description="👮 Mostrar toda a equipe (staff) do servidor")
async def staffs(i: discord.Interaction):
    # ===============================
    # 🔹 NOMES FIXOS DEFINIDOS POR VOCÊ
    # ===============================
    admin_fixo = ["Araujrsx_XZZ"]

    ajudantes_fixos = [
        "<Mega pitbull> #Megadolobão",
        "@polares @ nyanratt",
        
    ]

    staffs_fixos = [
        "@polares @ nyanratt",
        "Drxzin",
        
    ]

    # ===============================
    # 🔹 DETECÇÃO AUTOMÁTICA
    # ===============================
    admins = set(admin_fixo)
    mods = set()
    helpers = set(ajudantes_fixos)
    staffs = set(staffs_fixos)

    for member in i.guild.members:
        if member.bot:
            continue

        perms = member.guild_permissions
        name = member.display_name

        if perms.administrator:
            admins.add(member.mention)
        elif perms.moderate_members or perms.ban_members or perms.kick_members:
            mods.add(member.mention)
        elif perms.manage_messages:
            helpers.add(member.mention)

    # ===============================
    # 🔹 EMBED FINAL
    # ===============================
    embed = discord.Embed(
        title="👮 Equipe do Servidor",
        description="Lista oficial da staff do servidor",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="👑 Administrador",
        value="\n".join(admins) if admins else "Nenhum",
        inline=False
    )

    embed.add_field(
        name="🛡️ Moderadores",
        value="\n".join(mods) if mods else "Nenhum",
        inline=False
    )

    embed.add_field(
        name="🔰 Ajudantes",
        value="\n".join(helpers) if helpers else "Nenhum",
        inline=False
    )

    embed.add_field(
        name="⚙️ Staffs",
        value="\n".join(staffs) if staffs else "Nenhum",
        inline=False
    )

    embed.set_footer(
        text=f"Solicitado por {i.user}",
        icon_url=i.user.display_avatar.url
    )

    await i.response.send_message(embed=embed)
@bot.tree.command(description="🎨 Escolher cor do nome (VIP Diamante+)")
async def cor_nome(i: discord.Interaction, cor: str):
    if not is_vip(i.user.id) or vip_level(i.user.id) < 3:
        return await i.response.send_message(
            "❌ Apenas VIP **Diamante ou Ultimate**.",
            ephemeral=True
        )

    CORES = {
        "vermelho": discord.Color.red(),
        "verde": discord.Color.green(),
        "azul": discord.Color.blue(),
        "roxo": discord.Color.purple(),
        "amarelo": discord.Color.gold(),
        "preto": discord.Color.dark_gray(),
        "branco": discord.Color.light_grey()
    }

    cor = cor.lower()

    if cor not in CORES:
        return await i.response.send_message(
            "❌ Cor inválida. Use o autocomplete.",
            ephemeral=True
        )

    role_name = f"🎨 Cor • {i.user.name}"
    role = discord.utils.get(i.guild.roles, name=role_name)

    if not role:
        role = await i.guild.create_role(
            name=role_name,
            color=CORES[cor],
            reason="Cor VIP"
        )
        await i.user.add_roles(role)
    else:
        await role.edit(color=CORES[cor])

    await i.response.send_message(
        f"🎨 Sua cor foi alterada para **{cor}**!",
        ephemeral=True
    )
@cor_nome.autocomplete("cor")
async def cor_autocomplete(
    i: discord.Interaction,
    current: str
):
    cores = [
        "vermelho",
        "verde",
        "azul",
        "roxo",
        "amarelo",
        "preto",
        "branco"
    ]

    return [
        app_commands.Choice(name=cor, value=cor)
        for cor in cores
        if current.lower() in cor
    ]
@bot.tree.command(description="♻️ Resetar a cor do seu nome (VIP Diamante+)")
async def reset_cor(i: discord.Interaction):
    # ===============================
    # 🔒 VERIFICA VIP
    # ===============================
    if not is_vip(i.user.id) or vip_level(i.user.id) < 3:
        return await i.response.send_message(
            "❌ Apenas VIP **Diamante ou Ultimate** podem usar este comando.",
            ephemeral=True
        )

    # ===============================
    # 🔎 BUSCAR CARGO
    # ===============================
    role_name = f"🎨 Cor • {i.user.name}"
    role = discord.utils.get(i.guild.roles, name=role_name)

    if not role:
        return await i.response.send_message(
            "⚠️ Você não possui nenhuma cor personalizada ativa.",
            ephemeral=True
        )

    # ===============================
    # ❌ REMOVER CARGO
    # ===============================
    try:
        await i.user.remove_roles(role)
        await role.delete(reason="Reset de cor VIP")
    except discord.Forbidden:
        return await i.response.send_message(
            "❌ Não tenho permissão para remover o cargo.",
            ephemeral=True
        )

    # ===============================
    # ✅ CONFIRMAÇÃO
    # ===============================
    embed = discord.Embed(
        title="♻️ Cor resetada!",
        description="Sua cor personalizada foi removida com sucesso.",
        color=discord.Color.dark_gray()
    )
    embed.set_footer(text="VIP Diamante+ 💎")

    await i.response.send_message(embed=embed, ephemeral=True)
@bot.tree.command(description="🌐 Ver quantos servidores o bot está")
async def servers(i: discord.Interaction):
    total = len(bot.guilds)

    embed = discord.Embed(
        title="🌐 Servidores do Bot",
        description=f"🤖 Estou atualmente em **{total} servidores**!",
        color=discord.Color.blurple()
    )
    embed.set_footer(text=BOT_VERSION)

    await i.response.send_message(embed=embed, ephemeral=True)

OWNER_ID = 1287910036131151937  # seu ID do Discord

@bot.tree.command(description="🚪 Fazer o bot sair de um servidor")
async def leave_server(i: discord.Interaction, server_id: str):
    if i.user.id != OWNER_ID:
        return await i.response.send_message(
            "❌ Apenas o dono do bot pode usar este comando.",
            ephemeral=True
        )

    guild = bot.get_guild(int(server_id))
    if not guild:
        return await i.response.send_message(
            "❌ Servidor não encontrado.",
            ephemeral=True
        )

    await guild.leave()
    await i.response.send_message(
        f"✅ Saí do servidor **{guild.name}** ({guild.id})",
        ephemeral=True
    )
@bot.tree.command(description="📊 Lista de servidores onde o bot está")
async def list_servers(i: discord.Interaction):
    if i.user.id != OWNER_ID:
        return await i.response.send_message(
            "❌ Apenas o **dono do bot** pode usar este comando.",
            ephemeral=True
        )

    guilds = bot.guilds
    total = len(guilds)

    desc = ""
    for g in guilds:
        desc += f"🏠 **{g.name}**\n🆔 `{g.id}`\n👥 {g.member_count} membros\n\n"

    embed = discord.Embed(
        title="📊 Servidores do Bot",
        description=desc if desc else "Nenhum servidor encontrado.",
        color=discord.Color.blurple()
    )

    embed.set_footer(text=f"Total de servidores: {total}")

    await i.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(description="🏴‍☠️ Caça ao tesouro")
async def cacatesouro(i: discord.Interaction):
    uid = i.user.id
    now = time.time()

    cursor.execute(
        "INSERT OR IGNORE INTO cacador (user_id) VALUES (?)",
        (uid,)
    )
    db.commit()

    cursor.execute(
        "SELECT last_hunt FROM cacador WHERE user_id=?",
        (uid,)
    )
    last = cursor.fetchone()[0]

    if now - last < TESOURO_COOLDOWN:
        restante = int((TESOURO_COOLDOWN - (now - last)) / 60)
        return await i.response.send_message(
            f"⏳ Você já caçou recentemente.\nTente novamente em **{restante} minutos**.",
            ephemeral=True
        )

    chance = random.random()

    if chance < 0.55:
        ganho = int(random.randint(800, 1500) * vip_bonus(uid))
        add_saldo(uid, ganho)
        resultado = f"💎 Você encontrou um tesouro!\n💰 **+{ganho} PixCoins**"
    elif chance < 0.80:
        ganho = int(random.randint(200, 600) * vip_bonus(uid))
        add_saldo(uid, ganho)
        resultado = f"🪙 Achado comum!\n💰 **+{ganho} PixCoins**"
    else:
        perda = random.randint(200, 500)
        add_saldo(uid, -perda)
        resultado = f"💥 Armadilha!\n❌ **-{perda} PixCoins**"

    cursor.execute(
        "UPDATE cacador SET last_hunt=? WHERE user_id=?",
        (now, uid)
    )
    db.commit()

    embed = discord.Embed(
        title="🏴‍☠️ Caça ao Tesouro",
        description=resultado,
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Multiplicador VIP: x{vip_bonus(uid)}")

    await i.response.send_message(embed=embed)

# ===============================
# 🏴‍☠️ CAÇA AO TESOURO AUTOMÁTICO
# ===============================

TESOURO_CODIGO = [
    "CA", "ÇA", "DOR", "ES", "2026",
    "VIP", "GOLD", "PIX", "COINS",
    "ADMS", "FELIZES"
]

CODIGO_FINAL = "CA-ÇA-DOR-ES-2026-VIP-GOLD-PIX-COINS-ADMS-FELIZES"

# pistas verdadeiras (todas em minúsculo)
PISTAS_VERDADEIRAS = [
    "os adms ficaram muito tristes com o desempenho do server",
    "o vip gold foi muito comentado na staff",
    "o pix demorou mas chegou",
    "algumas coins sumiram do banco",
    "o ano de 2026 vai marcar o servidor",
    "o caçador sempre encontra o dor escondido",
    "os felizes nem sempre parecem felizes",
    "tudo começa com ca e termina bem",
    "o gold não vale nada sem vip",
    "administradores também gostam de pix",
    "coins não caem do céu"
]

# pistas falsas
PISTAS_FALSAS = [
    "o código começa com vip",
    "não existe pix no prêmio",
    "o ano correto é 2025",
    "não tem hífens",
    "termina em gold",
    "não envolve adms",
    "felizes é só modo de falar",
    "é tudo em inglês"
]

TESOURO_INTERVALO = 3 * 60 * 60  # 3 horas
TESOURO_MAX_VENCEDORES = 3

# ===============================
# 📦 BANCO DE DADOS
# ===============================

cursor.execute("""
CREATE TABLE IF NOT EXISTS tesouro (
    etapa INTEGER DEFAULT 0,
    vencedores INTEGER DEFAULT 0
)
""")
db.commit()

cursor.execute("INSERT OR IGNORE INTO tesouro (rowid) VALUES (1)")
db.commit()

# ===============================
# 🔧 FUNÇÕES AUXILIARES
# ===============================

def horario_permitido():
    hora = time.localtime().tm_hour
    return 6 <= hora <= 23  # sem madrugada


def destacar_codigo(frase: str):
    frase_final = frase
    for parte in TESOURO_CODIGO:
        frase_final = frase_final.replace(
            parte.lower(),
            parte.upper()
        )
    return frase_final

# ===============================
# ⏰ TASK AUTOMÁTICA DE PISTAS
# ===============================

@tasks.loop(seconds=TESOURO_INTERVALO)
async def enviar_pista_tesouro():
    if not horario_permitido():
        return

    cursor.execute("SELECT etapa, vencedores FROM tesouro")
    etapa, vencedores = cursor.fetchone()

    if vencedores >= TESOURO_MAX_VENCEDORES:
        return

    if etapa >= len(PISTAS_VERDADEIRAS):
        return

    # sorteia pista (real ou falsa)
    pista = random.choice(PISTAS_VERDADEIRAS + PISTAS_FALSAS)

    # destaca SOMENTE as partes do código
    pista = destacar_codigo(pista)

    for guild in bot.guilds:
        canal = discord.utils.get(
            guild.text_channels, name="🏴‍☠️caça-ao-tesouro"
        )
        if not canal:
            canal = await guild.create_text_channel("🏴‍☠️caça-ao-tesouro")

        await canal.send(
            f"🏴‍☠️ **CAÇA AO TESOURO**\n"
            f"🧩 Pista #{etapa + 1}:\n"
            f"> {pista}"
        )

    cursor.execute("UPDATE tesouro SET etapa = etapa + 1")
    db.commit()

# ===============================
# 🏆 COMANDO DE RESGATE
# ===============================

@bot.tree.command(description="🏆 Tentar resgatar o tesouro")
async def tesouro(i: discord.Interaction, codigo: str):
    codigo = codigo.upper().strip()

    cursor.execute("SELECT vencedores FROM tesouro")
    vencedores = cursor.fetchone()[0]

    if vencedores >= TESOURO_MAX_VENCEDORES:
        return await i.response.send_message(
            "❌ O tesouro já foi totalmente resgatado."
        )

    if codigo != CODIGO_FINAL:
        return await i.response.send_message("❌ Código incorreto.")

    # prêmio
    add_saldo(i.user.id, 100_000)

    cursor.execute(
        "REPLACE INTO vip VALUES (?, ?, ?)",
        (i.user.id, 2, -1)  # VIP OURO
    )

    cargo = discord.utils.get(i.guild.roles, name="🏴‍☠️ Caçador de Tesouros")
    if not cargo:
        cargo = await i.guild.create_role(
            name="🏴‍☠️ Caçador de Tesouros",
            color=discord.Color.gold()
        )

    await i.user.add_roles(cargo)

    cursor.execute(
        "UPDATE tesouro SET vencedores = vencedores + 1"
    )
    db.commit()

    await i.response.send_message(
        "🏆 **PARABÉNS!**\n"
        "💰 +100.000 PixCoins\n"
        "👑 VIP Ouro\n"
        "🏷️ Cargo: Caçador de Tesouros"
    )

# ===============================
# 🚀 INICIAR NO READY
# ===============================

@bot.event
async def on_ready():
    if not enviar_pista_tesouro.is_running():
        enviar_pista_tesouro.start()

bot.run(DISCORD_TOKEN)
