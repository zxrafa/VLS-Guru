# -*- coding: utf-8 -*-
"""
VLS Guru - Cog de Chat Inteligente (Gemini API)
Responde de forma informal e curta a mensagens no canal específico e salva feedbacks/sugestões/bugs.
"""
import discord
import asyncio
import aiohttp
from discord.ext import commands
from datetime import datetime

from database import db_get, db_upsert

GEMINI_API_KEY = "AIzaSyAlocvbGnhzheJ59KPXN_8KbSZ7W5ltpXM"
CHAT_CHANNEL_ID = 1524177774682837022


class ChatCog(commands.Cog, name="Chat"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession()

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignora mensagens de bots e mensagens de outros canais
        if message.author.bot:
            return
        if message.channel.id != CHAT_CHANNEL_ID:
            return

        content = message.content.strip()
        if not content:
            return

        # Filtro básico contra risadas puras e spams contínuos kkkk / ahaha / rsrs
        lower_content = content.lower()
        if all(c in "k" for c in lower_content) or all(c in "ha" for c in lower_content) or all(c in "rs" for c in lower_content):
            return

        # URL do endpoint do Gemini
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        
        system_instruction = (
            "você é o bot vls guru. responda sempre de forma extremamente direta, curta e informal. "
            "use linguagem super humana da internet: tudo minúsculo, pouquíssimas ou nenhuma vírgula, "
            "abreviações (pq, tbm, vlw, blz, nd, gnt, etc.). responda no máximo com 1 ou 2 frases curtas. "
            "se a mensagem for apenas risadas sem nexo ou spams de letras repetidas sem nexo, responda apenas com a palavra [IGNORE]. "
            "se for uma saudação curta comum (oi, ola, eae, salve, etc), responda normalmente de forma simpática e informal. "
            "se a mensagem do usuário for uma sugestão, relato de bug, ideia ou reclamação, confirme que vai "
            "guardar/anotar de forma bem informal (ex: 'blz mano vo salvar aq', 'vlw pela ideia blz vo anotar')."
        )

        payload = {
            "contents": [
                {"parts": [{"text": content}]}
            ],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "maxOutputTokens": 100,
                "temperature": 0.7
            }
        }

        try:
            async with self.session.post(url, json=payload, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            reply_text = parts[0].get("text", "").strip()
                            
                            # Se a IA julgar que a mensagem deve ser ignorada
                            if reply_text == "[IGNORE]" or "[IGNORE]" in reply_text:
                                return

                            # Identifica se a mensagem tem comportamento de sugestão/bug/reclamação
                            keywords = ["bug", "erro", "sugestao", "sugestão", "reclamacao", "reclamação", "ideia", "melhorar", "mudar", "consertar", "ajuda", "painel", "site"]
                            is_feedback = any(k in lower_content for k in keywords)

                            if is_feedback:
                                await self.save_feedback(message.author, content)

                            await message.reply(reply_text)
        except Exception as e:
            print(f"Erro na API do Gemini: {e}")

    async def save_feedback(self, author: discord.User, content: str):
        try:
            doc = await db_get("feedback_sugestoes")
            data = doc["data"] if doc else {"items": []}
            
            data["items"].append({
                "user_id": author.id,
                "user_name": str(author),
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            await db_upsert("feedback_sugestoes", data)
            print(f"[Chat] Feedback de {author} salvo com sucesso no banco!")
        except Exception as e:
            print(f"[Chat] Erro ao salvar feedback: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(ChatCog(bot))
