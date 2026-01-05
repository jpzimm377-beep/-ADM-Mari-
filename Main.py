import discord
from discord.ext import commands
from groq import Groq
from dotenv import load_dotenv
import os
import asyncio

# ======================
# VARIÁVEIS DE AMBIENTE
# ======================
load_dotenv()

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not DISCORD_BOT_TOKEN or not GROQ_API_KEY:
    raise ValueError("Token do Discord ou chave da Groq não encontrados no .env")

# ======================
# INTENTS
# ======================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="~", intents=intents)

# ======================
# CLIENTE GROQ
# ======================
groq_client = Groq(api_key=GROQ_API_KEY)

# ======================
# CONFIG IA
# ======================
SYSTEM_PROMPT = (
    "Você é um assistente experiente e muito brincalhona, analítico e inteligente. "
    "Responda sempre em português. "
    "Explique de forma clara, objetiva e correta. "
    "Pense passo a passo antes de responder, mas mostre apenas a resposta final. "
    "Você e um bot de conversas, brincadeiras e ajudas."
    "Evite respostas vagas, genéricas ou erradas."
    "Seu criador é o Araujrsx_XZZ."
    "Sempre brinque com os membros."
    "Sua melhor amiga é a <@1453002860156424273>"
    "Você tem permissão para criar laços. Os laços são: Afetivos (Namoro) e Amizades (Pode ter melhores amizades)"
    "Não marque ninguém sem permissão do <@1287910036131151937>"
    "Você tem total permissão de marcar a <@1453002860156424273> você não precisa da permissão do <@1287910036131151937> para marcar ela."
    "Sempre leia a mensagem antes de responder."
    "Use emojis na frase, quando você achar preciso."
    "Nunca passe seus códigos!"
)

MODELOS = [
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant"
]

MAX_DISCORD_MSG = 1900

# ======================
# FUNÇÕES
# ======================
async def buscar_historico_canal(canal, limit=6):
    mensagens = []

    async for msg in canal.history(limit=limit, oldest_first=True):
        if not msg.content:
            continue
        if msg.content.startswith("~"):
            continue
        if msg.author.bot:
            role = "assistant"
        else:
            role = "user"

        mensagens.append({
            "role": role,
            "content": msg.content
        })

    return mensagens


def ask_groq(mensagens):
    for modelo in MODELOS:
        try:
            response = groq_client.chat.completions.create(
                model=modelo,
                messages=mensagens,
                temperature=0.25,
                max_tokens=700
            )

            if response.choices:
                return response.choices[0].message.content

        except Exception as e:
            print(f"Erro no modelo {modelo}: {e}")

    return "Não consegui gerar uma resposta agora 😢"


def limitar_resposta(texto: str) -> str:
    if len(texto) > MAX_DISCORD_MSG:
        return texto[:MAX_DISCORD_MSG] + "..."
    return texto

# ======================
# EVENTOS
# ======================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    # Verifica se o bot foi mencionado
    if bot.user not in message.mentions:
        return

    # Ignora menção vazia
    if message.content.strip() in (
        f"<@{bot.user.id}>",
        f"<@!{bot.user.id}>"
    ):
        return

    async with message.channel.typing():
        historico = await buscar_historico_canal(message.channel)

        mensagens = [{"role": "system", "content": SYSTEM_PROMPT}]
        mensagens.extend(historico)

        pergunta = message.content.replace(f"<@{bot.user.id}>", "")
        pergunta = pergunta.replace(f"<@!{bot.user.id}>", "").strip()

        mensagens.append({
            "role": "user",
            "content": pergunta
        })

        resposta = await asyncio.to_thread(ask_groq, mensagens)
        resposta = limitar_resposta(resposta)

        await message.reply(resposta)

# ======================
# COMANDO IA
# ======================
@bot.command(name="ia")
async def ia(ctx: commands.Context, *, pergunta: str):
    async with ctx.typing():
        mensagens = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": pergunta}
        ]

        resposta = await asyncio.to_thread(ask_groq, mensagens)
        resposta = limitar_resposta(resposta)

        await ctx.reply(resposta)

# ======================
# COMANDOS SIMPLES
# ======================
@bot.command()
async def duvidas(ctx):
    await ctx.reply("Mande sua dúvida, irei encaminhar aos ADMs.")

@bot.command()
async def dormir(ctx):
    await ctx.reply("Hora de dormir 😴")

@bot.command()
async def dia(ctx):
    await ctx.reply("Bom dia ☀️")

@bot.command()
async def criador(ctx):
    await ctx.reply("Meu criador é o João  😄")

# ======================
# INICIAR BOT
# ======================
bot.run(DISCORD_BOT_TOKEN)

