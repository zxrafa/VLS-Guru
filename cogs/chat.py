# -*- coding: utf-8 -*-
"""
VLS Guru - Cog de Chat Inteligente (Gemini API)
Responde de forma informal e curta a mensagens no canal específico e salva feedbacks/sugestões/bugs.
Permite também controle do bot via linguagem natural para administradores mestres por menção.
"""
import discord
import asyncio
import aiohttp
import os
import json
import uuid
from discord.ext import commands
from datetime import datetime

from database import db_get, db_upsert, get_user_profile, save_user_profile, get_all_players
from config import ALLOWED_ADMIN_IDS as ALLOWED_NLP_ADMINS

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
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
        # Ignora mensagens de bots
        if message.author.bot:
            return

        # FLUXO 1: Administrador Master marcando o bot em QUALQUER canal (NLP Admin)
        is_admin = message.author.id in ALLOWED_NLP_ADMINS
        is_mentioned = self.bot.user.mentioned_in(message) or (
            message.reference and 
            message.reference.cached_message and 
            message.reference.cached_message.author.id == self.bot.user.id
        )

        if is_admin and is_mentioned:
            await self.handle_admin_nlp(message)
            return

        # FLUXO 2: Canal de chat geral / sugestões
        if message.channel.id != CHAT_CHANNEL_ID:
            return

        content = message.content.strip()
        if not content:
            return

        # Filtro básico contra risadas puras e spams contínuos kkkk / ahaha / rsrs
        lower_content = content.lower()
        if all(c in "k" for c in lower_content) or all(c in "ha" for c in lower_content) or all(c in "rs" for c in lower_content):
            return

        if not GEMINI_API_KEY:
            print("[Chat] Erro: GEMINI_API_KEY não configurada no ambiente/env.")
            return

        # URL do endpoint do Gemini (Lite)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={GEMINI_API_KEY}"
        
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
                else:
                    err_txt = await resp.text()
                    print(f"Erro Gemini API (Status {resp.status}): {err_txt}")
        except Exception as e:
            print(f"Erro ao chamar API do Gemini: {e}")

    async def handle_admin_nlp(self, message: discord.Message):
        # Remove menções ao bot do conteúdo para a IA focar no comando
        content = message.content.replace(f"<@!{self.bot.user.id}>", "").replace(f"<@{self.bot.user.id}>", "").strip()
        if not content:
            return await message.reply("eae mano blz? q q manda?")

        if not GEMINI_API_KEY:
            return await message.reply("❌ erro: GEMINI_API_KEY não foi configurada nas variáveis de ambiente")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={GEMINI_API_KEY}"
        
        system_instruction = (
            "você é o assistente administrativo por inteligência artificial do bot vls guru. "
            "seu dever é analisar os pedidos do administrador master e retornar um JSON estrito para executar a ação desejada no banco de dados, além de responder informalmente. "
            "\n\n"
            "FORMATO DE RETORNO (JSON estrito, não envie nenhum outro texto, markdown, blocos de código ```json ou conversas fora do JSON):\n"
            "{\n"
            '  "action": "NOME_DA_ACAO",\n'
            '  "params": {\n'
            '    "user_id": "id_do_usuario_alvo",\n'
            '    "amount": 10000,\n'
            '    "player_name_or_id": "nome_do_jogador",\n'
            '    "to_user_id": "id_do_destinatario_se_transferir",\n'
            '    "cooldown_type": "all/recrutar/caixa/roleta"\n'
            "  },\n"
            '  "reply": "resposta super curta, informal e tudo minúsculo para o admin confirmando a ação"\n'
            "}\n\n"
            "Ações Suportadas:\n"
            '1. "give_money": dar dinheiro (R$) para um usuário. Parâmetros: "user_id" (menção no formato <@ID>, ID puro ou "self"), "amount" (inteiro positivo).\n'
            '2. "give_coins": dar VLS Coins para um usuário. Parâmetros: "user_id" (menção <@ID> ou "self"), "amount" (inteiro positivo).\n'
            '3. "give_player": dar um jogador para um usuário. Parâmetros: "user_id" (menção <@ID> ou "self"), "player_name_or_id" (nome aproximado do jogador, ex: "messi" ou "neymar").\n'
            '4. "remove_player": remover jogador do elenco de um usuário. Parâmetros: "user_id" (menção <@ID> ou "self"), "player_name_or_id" (nome aproximado do jogador).\n'
            '5. "take_money": tirar/remover/pegar dinheiro (R$) de um usuário. Parâmetros: "user_id" (menção <@ID> ou "self"), "amount" (inteiro positivo).\n'
            '6. "take_coins": tirar/remover/pegar VLS Coins de um usuário. Parâmetros: "user_id" (menção <@ID> ou "self"), "amount" (inteiro positivo).\n'
            '7. "transfer_money": transferir/mandar dinheiro de um usuário para outro. Parâmetros: "user_id" (quem envia, ex: <@ID1> ou "self"), "to_user_id" (quem recebe, ex: <@ID2>), "amount" (inteiro positivo).\n'
            '8. "reset_cooldown": resetar/zerar o cooldown (tempo de espera) de recrutar, caixa ou roleta de alguém. Parâmetros: "user_id" (menção <@ID> ou "self"), "cooldown_type" (pode ser "recrutar", "caixa", "roleta" ou "all").\n'
            '9. "none": apenas responder ao admin sem nenhuma alteração no banco (conversas gerais, dúvidas, etc.).\n\n'
            "Notas importantes:\n"
            "- Se o admin falar 'dar dinheiro para mim' ou similar, use 'self' no user_id.\n"
            "- Se o admin disser 'dar dinheiro para fulano' e houver uma menção tipo <@123456789>, extraia exatamente o ID do usuário (ex: '123456789') e use no user_id.\n"
            "- Sua resposta de texto na chave 'reply' deve sempre ser tudo minúscula, super curta, informal e usar abreviações humanas (ex: 'pronto mano dei 50k pra ele blz', 'vlw tirei a carta do cara', 'cooldowns zerados pro cara', 'eae blz o q manda')."
        )

        payload = {
            "contents": [
                {"parts": [{"text": content}]}
            ],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "maxOutputTokens": 200,
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        try:
            async with self.session.post(url, json=payload, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            raw_reply = parts[0].get("text", "").strip()
                            
                            try:
                                res_json = json.loads(raw_reply)
                                action = res_json.get("action", "none")
                                params = res_json.get("params", {})
                                reply_text = res_json.get("reply", "blz mano feito")
                                
                                if action != "none":
                                    err = await self.execute_admin_action(action, params, message.author.id, message)
                                    if err:
                                        return await message.reply(err)

                                await message.reply(reply_text)
                            except Exception as parse_err:
                                print(f"Erro ao parsear JSON do Gemini Admin: {parse_err}. Raw: {raw_reply}")
                                await message.reply(raw_reply)
                else:
                    err_txt = await resp.text()
                    print(f"Erro Gemini API Admin (Status {resp.status}): {err_txt}")
                    await message.reply("❌ deu erro de comunicação com a api do gemini")
        except Exception as e:
            print(f"Erro ao processar NLP admin: {e}")
            await message.reply("❌ deu erro ao processar o comando administrativo")

    async def execute_admin_action(self, action: str, params: dict, admin_id: int, message: discord.Message) -> str | None:
        user_id_raw = params.get("user_id", "self")
        
        # Resolução do ID do usuário alvo
        if user_id_raw == "self" or str(user_id_raw) == str(admin_id):
            target_id = admin_id
        else:
            target_id = "".join(c for c in str(user_id_raw) if c.isdigit())
            if not target_id:
                return "❌ não encontrei o id de quem vc marcou"
            target_id = int(target_id)

        try:
            target_user = self.bot.get_user(target_id)
            if not target_user:
                target_user = await self.bot.fetch_user(target_id)
        except Exception:
            return "❌ usuário não encontrado no discord"

        # Carrega o perfil do banco
        profile = await get_user_profile(target_user)

        if action == "give_money":
            amount = int(params.get("amount", 0))
            profile["money"] = profile.get("money", 0) + amount
            await save_user_profile(target_id, profile)
            print(f"[Admin NLP] R$ {amount:,} dados para {target_user}")
            return None

        elif action == "give_coins":
            amount = int(params.get("amount", 0))
            profile["premium_coins"] = profile.get("premium_coins", 0) + amount
            await save_user_profile(target_id, profile)
            print(f"[Admin NLP] {amount} VLS Coins dadas para {target_user}")
            return None

        elif action == "take_money":
            amount = int(params.get("amount", 0))
            profile["money"] = max(0, profile.get("money", 0) - amount)
            await save_user_profile(target_id, profile)
            print(f"[Admin NLP] R$ {amount:,} retirados de {target_user}")
            return None

        elif action == "take_coins":
            amount = int(params.get("amount", 0))
            profile["premium_coins"] = max(0, profile.get("premium_coins", 0) - amount)
            await save_user_profile(target_id, profile)
            print(f"[Admin NLP] {amount} VLS Coins retirados de {target_user}")
            return None

        elif action == "transfer_money":
            amount = int(params.get("amount", 0))
            to_user_id_raw = params.get("to_user_id")
            if not to_user_id_raw:
                return "❌ vc não me disse quem vai receber o dinheiro"
            
            to_target_id = "".join(c for c in str(to_user_id_raw) if c.isdigit())
            if not to_target_id:
                return "❌ não encontrei o id de quem vai receber o dinheiro"
            to_target_id = int(to_target_id)
            
            try:
                to_target_user = self.bot.get_user(to_target_id)
                if not to_target_user:
                    to_target_user = await self.bot.fetch_user(to_target_id)
            except Exception:
                return "❌ destinatário não encontrado no discord"
                
            to_profile = await get_user_profile(to_target_user)
            
            if profile.get("money", 0) < amount:
                return f"❌ o usuário {target_user} não tem dinheiro suficiente (possui R$ {profile.get('money', 0):,})"
                
            profile["money"] -= amount
            to_profile["money"] = to_profile.get("money", 0) + amount
            
            await save_user_profile(target_id, profile)
            await save_user_profile(to_target_id, to_profile)
            print(f"[Admin NLP] R$ {amount:,} transferidos de {target_user} para {to_target_user}")
            return None

        elif action == "reset_cooldown":
            cooldown_type = str(params.get("cooldown_type", "all")).lower().strip()
            
            if cooldown_type in ["recrutar", "all"]:
                profile["last_claim"] = 0
            if cooldown_type in ["caixa", "all"]:
                profile["last_sobre"] = 0
            if cooldown_type in ["roleta", "all"]:
                profile["last_roleta"] = 0
                
            await save_user_profile(target_id, profile)
            print(f"[Admin NLP] Cooldowns ({cooldown_type}) zerados para {target_user}")
            return None

        elif action == "give_player":
            player_query = params.get("player_name_or_id", "").strip()
            if not player_query:
                return "❌ vc não me disse o nome do jogador"
            
            all_players = await get_all_players()
            matched_player = None
            for p in all_players:
                if p["id"].lower() == player_query.lower() or player_query.lower() in p["name"].lower():
                    matched_player = p
                    break
                    
            if not matched_player:
                return f"❌ o jogador '{player_query}' não foi encontrado no catálogo"
                
            instanced = matched_player.copy()
            instanced["instance_id"] = str(uuid.uuid4())[:8]
            instanced["original_pos"] = matched_player["pos"]
            instanced["acquired_at"] = datetime.utcnow().isoformat()
            instanced.update({
                "goals": 0, "assists": 0, "saves": 0, "matches": 0, "mvps": 0, 
                "yellow_cards": 0, "red_cards": 0, "xp": 0
            })
            
            profile.setdefault("inventory", []).append(instanced)
            await save_user_profile(target_id, profile)
            print(f"[Admin NLP] Jogador {matched_player['name']} adicionado para {target_user}")
            return None

        elif action == "remove_player":
            player_query = params.get("player_name_or_id", "").strip()
            if not player_query:
                return "❌ vc não disse qual jogador quer remover"
                
            inventory = profile.get("inventory", [])
            matched_idx = -1
            for idx, p in enumerate(inventory):
                if p["id"].lower() == player_query.lower() or player_query.lower() in p["name"].lower():
                    matched_idx = idx
                    break
                    
            if matched_idx == -1:
                return f"❌ o usuário não tem a carta '{player_query}' no elenco"
                
            removed = inventory.pop(matched_idx)
            profile["starting_xi"] = [p for p in profile.get("starting_xi", []) if p.get("instance_id") != removed.get("instance_id")]
            
            await save_user_profile(target_id, profile)
            print(f"[Admin NLP] Jogador {removed['name']} removido de {target_user}")
            return None

        return "❌ ação administrativa não suportada"

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
