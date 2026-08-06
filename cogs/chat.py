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

from dotenv import load_dotenv

load_dotenv()

from database import db_get, db_upsert, get_user_profile, save_user_profile, get_all_players
from config import ALLOWED_ADMIN_IDS as ALLOWED_NLP_ADMINS

CHAT_CHANNEL_ID = 1524177774682837022

def get_gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", "").strip()


def get_time_context_str() -> str:
    from datetime import datetime, timezone, timedelta
    tz_br = timezone(timedelta(hours=-3))
    now = datetime.now(tz_br)
    dias_semana = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    dia_semana = dias_semana[now.weekday()]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    mes_nome = meses[now.month - 1]
    
    return (
        f"CONTEXTO TEMPORAL ATUAL:\n"
        f"- Data: {now.day:02d} de {mes_nome} de {now.year}\n"
        f"- Dia da semana: {dia_semana}\n"
        f"- Horário exato: {now.strftime('%H:%M:%S')} (Horário de Brasília / UTC-3)\n"
    )


async def load_chat_memory(channel_id: int, max_items: int = 15) -> list[dict]:
    """Busca o histórico recente de mensagens do canal salvo no Supabase."""
    try:
        doc = await db_get(f"chat_memory_{channel_id}")
        if doc and "data" in doc and "history" in doc["data"]:
            history = doc["data"]["history"]
            return history[-max_items:]
    except Exception as e:
        print(f"[Chat Memory] Erro ao carregar memória do Supabase: {e}")
    return []


async def save_chat_memory(channel_id: int, user: discord.User | discord.Member, user_msg: str, bot_reply: str, max_items: int = 30):
    """Salva uma nova interação na memória de média duração do canal no Supabase."""
    try:
        from datetime import datetime, timezone, timedelta
        tz_br = timezone(timedelta(hours=-3))
        now_str = datetime.now(tz_br).strftime("%Y-%m-%d %H:%M:%S")

        doc = await db_get(f"chat_memory_{channel_id}")
        history = []
        if doc and "data" in doc and "history" in doc["data"]:
            history = doc["data"]["history"]

        entry = {
            "timestamp": now_str,
            "user_id": user.id,
            "user_name": getattr(user, "display_name", str(user)),
            "username": str(user),
            "user_message": user_msg,
            "bot_response": bot_reply
        }

        history.append(entry)
        history = history[-max_items:]

        await db_upsert(f"chat_memory_{channel_id}", {
            "channel_id": channel_id,
            "history": history,
            "last_updated": now_str
        })
    except Exception as e:
        print(f"[Chat Memory] Erro ao salvar memória no Supabase: {e}")


def format_memory_prompt(history: list[dict]) -> str:
    """Formata o histórico para ser injetado como memória no prompt do Gemini."""
    if not history:
        return "MEMÓRIA RECENTE DE CONVERSAS (SUPABASE): Nenhuma conversa anterior registrada ainda."
    
    lines = ["MEMÓRIA RECENTE DE CONVERSAS E HISTÓRICO (SUPABASE):"]
    for item in history:
        ts = item.get("timestamp", "")
        uname = item.get("user_name", "Usuário")
        uid = item.get("user_id", "")
        umsg = item.get("user_message", "")
        breply = item.get("bot_response", "")
        lines.append(f"- [{ts}] {uname} (ID {uid}): \"{umsg}\" -> Guru respondeu: \"{breply}\"")
    
    return "\n".join(lines)


async def load_permanent_memories() -> list[dict]:
    """Busca as memórias permanentes (fatos que não apagam) salvas no Supabase."""
    try:
        doc = await db_get("chat_permanent_memory")
        if doc and "data" in doc and "memories" in doc["data"]:
            return doc["data"]["memories"]
    except Exception as e:
        print(f"[Permanent Memory] Erro ao carregar memórias do Supabase: {e}")
    return []


async def save_permanent_memory(user: discord.User | discord.Member, fact: str) -> dict:
    """Salva um fato ou regra permanente no Supabase."""
    try:
        from datetime import datetime, timezone, timedelta
        tz_br = timezone(timedelta(hours=-3))
        now_str = datetime.now(tz_br).strftime("%Y-%m-%d %H:%M:%S")

        memories = await load_permanent_memories()
        entry = {
            "id": f"mem_{uuid.uuid4().hex[:8]}",
            "timestamp": now_str,
            "author_id": user.id,
            "author_name": getattr(user, "display_name", str(user)),
            "username": str(user),
            "fact": fact
        }
        memories.append(entry)
        await db_upsert("chat_permanent_memory", {
            "memories": memories,
            "last_updated": now_str
        })
        return entry
    except Exception as e:
        print(f"[Permanent Memory] Erro ao salvar memória permanente no Supabase: {e}")
        return {}


async def delete_permanent_memory(search_term: str) -> int:
    """Remove memórias permanentes que contenham o termo de busca."""
    try:
        memories = await load_permanent_memories()
        if not memories:
            return 0

        initial_count = len(memories)
        filtered = [m for m in memories if search_term.lower() not in m.get("fact", "").lower()]
        removed_count = initial_count - len(filtered)

        if removed_count > 0:
            from datetime import datetime, timezone, timedelta
            tz_br = timezone(timedelta(hours=-3))
            now_str = datetime.now(tz_br).strftime("%Y-%m-%d %H:%M:%S")
            await db_upsert("chat_permanent_memory", {
                "memories": filtered,
                "last_updated": now_str
            })
        return removed_count
    except Exception as e:
        print(f"[Permanent Memory] Erro ao remover memória permanente no Supabase: {e}")
        return 0


def format_permanent_memory_prompt(memories: list[dict]) -> str:
    """Formata as memórias permanentes fixas para o prompt do Gemini."""
    if not memories:
        return "MEMÓRIA PERMANENTE FIXA (SUPABASE): Nenhuma memória ou regra permanente fixada ainda."
    
    lines = ["MEMÓRIA PERMANENTE FIXA (FATOS E REGRAS QUE VOCÊ NUNCA DEVE ESQUECER, SALVOS POR ADMINS NO SUPABASE):"]
    for m in memories:
        ts = m.get("timestamp", "")
        uname = m.get("author_name", "Admin")
        fact = m.get("fact", "")
        lines.append(f"- [Fixado por {uname} em {ts}]: \"{fact}\"")
    
    return "\n".join(lines)


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

        # Verificação de comandos de Memória Permanente ("Não esqueça", "Lembre-se", etc.)
        lower_raw = content.lower()
        triggers = ["não esqueça", "nao esqueca", "não se esqueça", "nao se esqueca", "guarde isso", "lembre-se"]
        
        is_authorized = (
            message.author.id in ALLOWED_NLP_ADMINS or 
            (isinstance(message.author, discord.Member) and message.author.guild_permissions.administrator)
        )

        if any(t in lower_raw for t in triggers):
            if not is_authorized:
                return await message.reply("❌ apenas administradores da liga possuem permissão para fixar memórias permanentes no banco mano!")

            fact_text = content
            for t in triggers:
                if t in lower_raw:
                    idx = lower_raw.find(t)
                    fact_text = fact_text[idx + len(t):].strip(" :,.-")
                    break

            if fact_text.lower().startswith("que "):
                fact_text = fact_text[4:].strip()

            if not fact_text:
                return await message.reply("❌ diga o que você quer que eu não esqueça! ex: 'não esqueça que a taxa do mercado é 10%'")

            await save_permanent_memory(message.author, fact_text)
            reply_text = f"blz mano anotado na minha memória permanente do supabase! vo lembrar pra sempre que: '{fact_text}'"
            await message.reply(reply_text)
            await save_chat_memory(message.channel.id, message.author, content, reply_text)
            return

        # Comando para listar memórias permanentes
        if any(term in lower_raw for term in ["quais são as memórias", "quais memorias", "quais memórias", "listar memórias", "listar memorias"]):
            if not is_authorized:
                return await message.reply("❌ apenas administradores da liga podem consultar o banco de memórias permanentes!")

            mems = await load_permanent_memories()
            if not mems:
                return await message.reply("não tenho nenhuma memória permanente registrada ainda mano")
            
            txt = "📌 **Memórias Permanentes Registradas no Supabase:**\n" + "\n".join([f"- **{m['fact']}** (fixado por {m['author_name']})" for m in mems])
            return await message.reply(txt[:1950])

        # Comando para apagar memória permanente
        if any(lower_raw.startswith(t) or f" {t}" in lower_raw for t in ["esqueça ", "esqueca ", "apagar memória ", "apagar memoria "]) and not any(neg in lower_raw for neg in ["não", "nao"]):
            if not is_authorized:
                return await message.reply("❌ apenas administradores da liga podem remover memórias permanentes!")

            search_term = content
            for t in ["esqueça", "esqueca", "apagar memória", "apagar memoria"]:
                if t in search_term.lower():
                    idx = search_term.lower().find(t)
                    search_term = search_term[idx + len(t):].strip(" :,.-")
                    break

            if search_term.lower().startswith("que "):
                search_term = search_term[4:].strip()

            if search_term:
                removed_count = await delete_permanent_memory(search_term)
                if removed_count > 0:
                    reply_text = f"blz mano apaguei {removed_count} memória(s) permanente(s) sobre '{search_term}' do banco!"
                    await message.reply(reply_text)
                    await save_chat_memory(message.channel.id, message.author, content, reply_text)
                    return
                else:
                    return await message.reply(f"não encontrei nenhuma memória permanente contendo '{search_term}' pra apagar mano")

        gemini_api_key = get_gemini_api_key()
        if not gemini_api_key:
            print("[Chat] Erro: GEMINI_API_KEY não configurada no ambiente/env.")
            return

        # Verifica se o usuário pediu modo de resposta normal/detalhada
        is_normal_mode = False
        normal_flags = ["--resposta-normal", "--normal", "--detalhado", "--completo"]
        for flag in normal_flags:
            if flag in content:
                is_normal_mode = True
                content = content.replace(flag, "").strip()

        # Clean prompt content
        content = " ".join(content.split())
        if not content:
            content = "oi"

        # Carrega as memórias do Supabase (Permanentes e Média Duração)
        perm_memories = await load_permanent_memories()
        perm_context = format_permanent_memory_prompt(perm_memories)
        
        history = await load_chat_memory(message.channel.id, max_items=15)
        memory_context = format_memory_prompt(history)
        time_context = get_time_context_str()

        knowledge_base = (
            "MANUAL E CONHECIMENTO COMPLETO DO BOT VLS GURU:\n"
            "Você é a IA oficial do VLS Guru, um bot de futebol de cartas, economia e simulação no Discord.\n\n"
            "COMO FUNCIONA O BOT & DICAS DE EVOLUÇÃO:\n"
            "1. Economia & Moedas: R$ (Dinheiro) e VLS Coins 💎. Ganhe com caixas, partidas, olheiro, roleta e missões.\n"
            "2. Formações & Táticas: 12 formações disponíveis (/time, /escalar, /tatico, /mentalidade). "
            "Táticas: Padrão, Gegenpress (+defesa/físico, mais estamina), Tiki-Taka (+passe/drible), Catenaccio (+defesa, -chute), Futebol Total (+20% geral), Park The Bus (+50% defesa).\n"
            "Mentalidade (/mentalidade): Defensiva (+35% defesa, -25% ataque), Equilibrada (1.0x), Ofensiva (+25% ataque, +15% passe).\n"
            "3. Cartas, Stats & PlayStyles: Atributos de linha (PAC, SHO, PAS, DRI, DEF, PHY) e Goleiro (DIV, KIC, HAN, REF, POS, SPD). "
            "19 PlayStyles no total (15 de linha + 4 de goleiro: Arremesso Especial, Encaixada, Soco, Espalmada). "
            "Titulares ganham +1 XP de afinidade por partida (cada 10 XP = +0.5% bônus, teto +5%).\n"
            "4. Modos de Jogo: /treino (R$ 3.000 + +1 XP pra todos os titulares), /desafio (PvP), /x1_aposta (PvP com aposta), /penalti_desafio, "
            "/liga (Modo Carreira com 7 divisões contra cartas reais), /modo_desafio (Enfrente 9 Times Históricos valendo R$ 50.000 + 10 Coins).\n"
            "5. Olheiro & Treino (/olheiro_treino): Pênalti contra olheiro. Gol = +1 Nível de Olheiro grátis + R$ 25.000 + 2 VLS Coins!\n"
            "6. Estádio & Torcida (/upar_torcida): Torcida reduz penalidade de vaias e aumenta bônus de empolgação nos jogos.\n"
            "7. Dicas de Evolução Rápida: Faça /treino todo dia; faça o /olheiro_treino sempre no cooldown; jogue a /liga para subir de divisão; "
            "enfrente os times históricos no /modo_desafio; venda repetidas no /multisell ou /mercado."
        )

        if is_normal_mode:
            mode_instruction = (
                "O usuário solicitou explicitamente uma RESPOSTA NORMAL E DETALHADA (usando a flag `--resposta-normal`).\n"
                "INSTRUÇÕES OBRIGATÓRIAS PARA ESTE MODO:\n"
                "- Responda de forma completa, didática, bem explicada, clara e sem enrolação.\n"
                "- Se o usuário pedir dicas de como evoluir, como fazer algo, como funciona um comando ou sistema, ENSINE TUDO passo a passo com total clareza.\n"
                "- Use formatação limpa do Discord (títulos, negrito, tópicos, emojis) para ficar muito agradável e fácil de ler.\n"
                "- Forneça detalhes completos sobre os sistemas do bot (treinos, olheiro, táticas, mentalidade, liga, desafios) conforme o contexto."
            )
            max_tokens = 1000
        else:
            mode_instruction = (
                "você é o bot vls guru. responda sempre de forma extremamente direta, curta e informal. "
                "use linguagem super humana da internet: tudo minúsculo, pouquíssimas ou nenhuma vírgula, "
                "abreviações (pq, tbm, vlw, blz, nd, gnt, etc.). responda no máximo com 1 ou 2 frases curtas. "
                "se a mensagem for apenas risadas sem nexo ou spams de letras repetidas sem nexo, responda apenas com a palavra [IGNORE]. "
                "se for uma saudação curta comum (oi, ola, eae, salve, etc), responda normalmente de forma simpática e informal. "
                "dica: lembre o usuário de que se ele quiser uma explicação longa/tutorial completo, ele pode colocar `--resposta-normal` no final do texto."
            )
            max_tokens = 120

        system_instruction = (
            f"{mode_instruction}\n\n"
            f"{knowledge_base}\n\n"
            f"se perguntarem as horas, o dia, a data ou qual o momento atual, use as informações do contexto temporal fornecidas abaixo.\n"
            f"você possui memória permanente (fatos fixados por administradores) e memória de média duração salvas no Supabase.\n\n"
            f"{time_context}\n\n"
            f"{perm_context}\n\n"
            f"{memory_context}"
        )

        models_to_try = [
            os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
            "gemini-2.0-flash",
            "gemini-1.5-flash-latest",
            "gemini-2.5-flash",
            "gemini-2.0-flash-lite"
        ]
        models_to_try = list(dict.fromkeys(models_to_try))

        payload = {
            "contents": [
                {"parts": [{"text": content}]}
            ],
            "systemInstruction": {
                "parts": [{"text": system_instruction}]
            },
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.7
            }
        }

        for model_name in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_api_key}"
            for attempt in range(2):
                try:
                    async with self.session.post(url, json=payload, timeout=12) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts:
                                    reply_text = parts[0].get("text", "").strip()
                                    
                                    if reply_text == "[IGNORE]" or "[IGNORE]" in reply_text:
                                        return

                                    keywords = ["bug", "erro", "sugestao", "sugestão", "reclamacao", "reclamação", "ideia", "melhorar", "mudar", "consertar", "ajuda", "painel", "site"]
                                    is_feedback = any(k in lower_content for k in keywords)

                                    if is_feedback:
                                        await self.save_feedback(message.author, content)

                                    await message.reply(reply_text)
                                    await save_chat_memory(message.channel.id, message.author, content, reply_text)
                                    return
                        elif resp.status == 429:
                            print(f"[Chat AI] Rate limit 429 no modelo {model_name}. Aguardando 2.5s...")
                            await asyncio.sleep(2.5)
                        elif resp.status == 404:
                            print(f"[Chat AI] Modelo {model_name} retornou 404, tentando próximo modelo...")
                            break
                        else:
                            err_txt = await resp.text()
                            print(f"Erro Gemini API (Status {resp.status} - {model_name}): {err_txt}")
                            break
                except Exception as e:
                    print(f"Exceção ao chamar API do Gemini ({model_name}): {e}")
                    await asyncio.sleep(1.5)

    async def handle_admin_nlp(self, message: discord.Message):
        # Remove menções ao bot do conteúdo para a IA focar no comando
        content = message.content.replace(f"<@!{self.bot.user.id}>", "").replace(f"<@{self.bot.user.id}>", "").strip()
        if not content:
            return await message.reply("eae mano blz? q q manda?")

        gemini_api_key = get_gemini_api_key()
        if not gemini_api_key:
            return await message.reply("❌ erro: GEMINI_API_KEY não foi configurada nas variáveis de ambiente")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={gemini_api_key}"
        
        # Carrega memórias do Supabase (Permanentes e Média Duração)
        perm_memories = await load_permanent_memories()
        perm_context = format_permanent_memory_prompt(perm_memories)

        history = await load_chat_memory(message.channel.id, max_items=10)
        memory_context = format_memory_prompt(history)

        time_context = get_time_context_str()
        system_instruction = (
            "você é o assistente administrativo por inteligência artificial do bot vls guru. "
            "seu dever é analisar os pedidos do administrador master e retornar um JSON estrito para executar a ação desejada no banco de dados, além de responder informalmente. "
            f"\n\n{time_context}\n\n{perm_context}\n\n{memory_context}\n\n"
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
                                        await save_chat_memory(message.channel.id, message.author, content, err)
                                        return await message.reply(err)

                                await message.reply(reply_text)
                                await save_chat_memory(message.channel.id, message.author, content, reply_text)
                            except Exception as parse_err:
                                print(f"Erro ao parsear JSON do Gemini Admin: {parse_err}. Raw: {raw_reply}")
                                await message.reply(raw_reply)
                                await save_chat_memory(message.channel.id, message.author, content, raw_reply)
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
