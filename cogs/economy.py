# -*- coding: utf-8 -*-
"""
VLS Guru - Cog de Economia e Progresso
Gerencia pacotes de cartas, mercado de transferências, olheiro e missões.
"""
import discord
import asyncio
import time
import os
import hashlib
from discord.ext import commands
from discord import app_commands
import random
import uuid
from datetime import datetime

from database import (
    db_get, db_upsert, db_delete, get_user_profile, save_user_profile,
    get_all_collections, get_all_players, get_missions, lock_user,
    db_get_prefix
)
from config import SCOUT_LEVEL_MAX, SCOUT_BASE_UPGRADE_COST, ACHIEVEMENTS_LIST, PLAYSTYLE_EMOJIS
VLS_COINS_EMOJI = '<:VLScoins:1517258837004914848>'


async def calculate_price(player: dict) -> int:
    over = player.get("over", 75)
    
    fixed_prices = {
        77: 50000,
        78: 120000,
        79: 250000,
        80: 600000,
        81: 1300000,
        82: 1900000,
        83: 3000000,
        84: 5000000,
        85: 10000000
    }

    if over in fixed_prices:
        base = fixed_prices[over]
    else:
        base = max(5000, (over - 50) * 15000)
        if over >= 84:
            base = base * 1.85
        elif 80 <= over <= 83:
            base = base * 1.15
        else:
            base = base * 0.40

    col_id = player.get("col_id")
    col_pct = 0
    if col_id:
        col_rec = await db_get(f"col_{col_id}")
        if col_rec:
            col_pct = col_rec["data"].get("preco_adicional_pct", 0)

    multiplier = 1.0 + (col_pct / 100.0)
    return max(5000, int(base * multiplier))

def get_player_by_rarity(rarity_name, all_players):
    mapping = {
        "Comum": "base",
        "Rara": "comum",
        "Épica": "premiados",
        "TOTW": "premiados",
        "TOTS": "copa_do_mundo",
        "Lendária": "copa_do_mundo"
    }
    col_id = mapping.get(rarity_name, "base")
    filtered = [p for p in all_players if p.get("col_id") == col_id]
    if not filtered:
        return __import__('random').choice(all_players).copy()
    return __import__('random').choice(filtered).copy()

def get_pos_group(pos: str) -> str:
    pos = pos.upper()
    if pos in ["ST", "LW", "RW", "CF"]: return "ATA"
    if pos in ["CAM", "CM", "CDM", "LM", "RM"]: return "MEI"
    if pos in ["CB", "LB", "RB", "LWB", "RWB"]: return "DEF"
    return "GK"

class EconomyCog(commands.Cog, name="Economia"):
    def __init__(self, bot):
        self.bot = bot

    # Helper para atualizar missões do usuário
    async def increment_mission(self, user_id: int, profile: dict, criterion: str, amount: int = 1):
        """
        Incrementa o progresso de missões do usuário com base em um critério específico.
        """
        now = datetime.utcnow()
        current_week = now.strftime("%Y-%W")
        current_month = now.strftime("%Y-%m")

        mp = profile.setdefault("missions_progress", {"diario": {}, "semanal": {}, "mensal": {}, "last_weekly_reset": "", "last_monthly_reset": ""})
        if "diario" not in mp:
            mp["diario"] = {}

        if mp.get("last_weekly_reset") != current_week:
            mp["semanal"] = {}
            mp["last_weekly_reset"] = current_week

        if mp.get("last_monthly_reset") != current_month:
            mp["mensal"] = {}
            mp["last_monthly_reset"] = current_month

        # 1. Incrementa Missões Diárias (Salvas no perfil)
        for dm in profile.get("daily_missions", []):
            if dm.get("criterion") == criterion:
                dm_id = dm["id"]
                current_val = mp["diario"].get(dm_id, 0)
                if isinstance(current_val, int):
                    mp["diario"][dm_id] = current_val + amount

        # 2. Incrementa Missões do Banco de Dados (semanais/mensais)
        missions = await get_missions()
        for m in missions:
            m_id = m["id"]
            m_type = m.get("type", "semanal")
            m_crit = m["criterion"]
            
            if m_crit == criterion:
                current_val = mp.setdefault(m_type, {}).get(m_id, 0)
                if isinstance(current_val, int):
                    mp[m_type][m_id] = current_val + amount

        profile["missions_progress"] = mp

    # Helper para checar conquistas pós-evento
    async def check_achievements(self, user_id: int, profile: dict, interaction: discord.Interaction):
        """
        Verifica se alguma conquista foi alcançada e concede recompensas.
        """
        unlocked_any = False
        unlocked_names = []

        # Categorias de dados acumulados
        goals_total = sum(p.get("goals", 0) for p in profile.get("inventory", []))
        inv_size = len(profile.get("inventory", []))
        scout_lvl = profile.get("scout_level", 0)
        money = profile.get("money", 0)

        # Copia conquistas já completas
        completed = set(profile.get("achievements", []))

        for ach in ACHIEVEMENTS_LIST:
            ach_id = ach["id"]
            if ach_id in completed:
                continue

            reached = False
            if ach["category"] == "gols" and goals_total >= ach["threshold"]:
                reached = True
            elif ach["category"] == "economia" and money >= ach["threshold"]:
                reached = True
            elif ach["category"] == "colecao" and inv_size >= ach["threshold"]:
                reached = True
            elif ach["category"] == "olheiro" and scout_lvl >= ach["threshold"]:
                reached = True

            if reached:
                completed.add(ach_id)
                unlocked_any = True
                unlocked_names.append(ach["name"])
                
                # Conceder recompensas
                if ach["reward_type"] == "money":
                    profile["money"] += ach["reward_value"]
                elif ach["reward_type"] == "coins":
                    profile["premium_coins"] += ach["reward_value"]

                # Dar badge correspondente
                if ach_id not in profile.get("acquired_badges", []):
                    if "acquired_badges" not in profile:
                        profile["acquired_badges"] = []
                    profile["acquired_badges"].append(ach_id)

        if unlocked_any:
            profile["achievements"] = list(completed)
            await save_user_profile(user_id, profile)
            
            # Notifica o usuário no chat
            embed = discord.Embed(
                title="🏆 CONQUISTAS DESBLOQUEADAS!",
                description=f"Parabéns! Você alcançou novos marcos em seu clube:\n" + "\n".join([f"✨ **{name}**" for name in unlocked_names]),
                color=discord.Color.gold()
            )
            embed.set_footer(text="Confira as novas badges utilizando /perfil.")
            await interaction.channel.send(embed=embed)

    @app_commands.command(name="saldo", description="Exibe o saldo atual de dinheiro e moedas premium de seu clube.")
    async def saldo(self, interaction: discord.Interaction):
        profile = await get_user_profile(interaction.user)
        
        embed = discord.Embed(
            title=f"💰 Finanças — {profile.get('club_name')}",
            color=discord.Color.green()
        )
        embed.add_field(name=f"{VLS_COINS_EMOJI} Saldo Bancário", value=f"R$ {profile.get('money', 0):,}", inline=True)
        embed.add_field(name=f"💎 Moedas Premium", value=str(profile.get("premium_coins", 0)), inline=True)
        embed.set_footer(text="VLS Guru • Gestão Financeira")
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="sobre", description="Exibe informações sobre o bot VLS Guru Reboot e seus desenvolvedores.")
    async def sobre(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🎮 VLS Guru — Reboot",
            description=(
                "Bem-vindo ao reboot do simulador esportivo mais completo do Discord!\n\n"
                "Desenvolvido sob um padrão profissional e moderno, o bot foi construído do zero, "
                "reunindo o melhor de inteligência tática, Pillow Design tático de 11 jogadores e "
                "uma engine de simulação imersiva baseada em PlayStyles e atributos específicos."
            ),
            color=discord.Color.blurple()
        )
        embed.add_field(name="🛠️ Tecnologias", value="Python (Discord.py) | Supabase (PostgreSQL) | Pillow (Canvas Graphics)", inline=False)
        embed.add_field(name="👑 Feito por", value="<@338704196180115458>", inline=False)
        embed.set_footer(text="Versão 2.0.0 Reboot • Todos os direitos reservados")
        await interaction.response.send_message(embed=embed)


    @app_commands.command(name="loja", description="Abre a loja de pacotes e produtos do VLS Guru.")
    async def loja(self, interaction: discord.Interaction):
        await interaction.response.defer()
        all_players = await get_all_players()
        if not all_players:
            return await interaction.followup.send("❌ Nenhum jogador cadastrado no mercado.")

        custom_products = await db_get_prefix("loja_produto_")
        view = LojaView(interaction.user, all_players, custom_products, cog=self)
        embed = await view.make_category_embed()
        await interaction.edit_original_response(embed=embed, view=view)

    @app_commands.command(name="caixa", description="Abre uma caixa misteriosa grátis a cada 8 horas.")
    @lock_user()
    async def caixa(self, interaction: discord.Interaction):
        profile = await get_user_profile(interaction.user)
        now = time.time()

        last_sobre = profile.get("last_sobre", 0)
        if last_sobre > now:
            last_sobre = 0

        # Cooldown de 8 horas (4 horas para boosters)
        is_booster = getattr(interaction.user, "premium_since", None) is not None
        cooldown = 14400 if is_booster else 28800
        if now - last_sobre < cooldown:
            restante = cooldown - (now - last_sobre)
            horas = int(restante // 3600)
            minutos = int((restante % 3600) // 60)
            segundos = int(restante % 60)
            booster_msg = "⚡ **Bônus Booster ativo!** " if is_booster else ""
            time_str = f"{horas}h {minutos}m" if horas > 0 else f"{minutos}m {segundos}s"
            return await interaction.response.send_message(
                f"⏳ {booster_msg}Aguarde mais **{time_str}** para abrir outra caixa.", ephemeral=True
            )

        await interaction.response.defer()

        caixas = ["Bronze Box", "Silver Box", "Gold Box", "Esmerald Box", "Diamond Box", "VLS Box"]
        BOX_EMOJIS = {
            "Bronze Box": "<:bronzebox:1518696081838571761>",
            "Silver Box": "<:silverbox:1518696479802523722>",
            "Gold Box": "<:goldbox:1518697326464466995>",
            "Esmerald Box": "<:Emeraldbox:1518698387589824552>",
            "Diamond Box": "<:Diamondbox:1518697775037022272>",
            "VLS Box": "<:vlsbox:1518695516857438460>"
        }
        BOX_THUMBNAILS = {
            "Bronze Box": "https://cdn.discordapp.com/emojis/1518696081838571761.png",
            "Silver Box": "https://cdn.discordapp.com/emojis/1518696479802523722.png",
            "Gold Box": "https://cdn.discordapp.com/emojis/1518697326464466995.png",
            "Esmerald Box": "https://cdn.discordapp.com/emojis/1518698387589824552.png",
            "Diamond Box": "https://cdn.discordapp.com/emojis/1518697775037022272.png",
            "VLS Box": "https://cdn.discordapp.com/emojis/1518695516857438460.png"
        }

        pesos = [30, 25, 20, 12, 8, 5]
        obtida = random.choices(caixas, weights=pesos, k=1)[0]
        idx = caixas.index(obtida)

        faixas_moedas = [
            (15_000, 25_000),
            (25_000, 45_000),
            (45_000, 80_000),
            (80_000, 150_000),
            (150_000, 300_000),
            (300_000, 600_000)
        ]
        min_moedas, max_moedas = faixas_moedas[idx]
        recompensa_dinheiro = random.randint(min_moedas, max_moedas)
        premium_drops = [(1, 3), (3, 6), (6, 12), (12, 25), (25, 50), (50, 100)]
        recompensa_premium = random.randint(premium_drops[idx][0], premium_drops[idx][1])

        profile["money"] += recompensa_dinheiro
        profile["premium_coins"] = profile.get("premium_coins", 0) + recompensa_premium
        profile["last_sobre"] = now
        await save_user_profile(interaction.user.id, profile)

        emoji_obtido = BOX_EMOJIS.get(obtida, "🎁")
        thumb_url = BOX_THUMBNAILS.get(obtida)

        embed = discord.Embed(
            title=f"{emoji_obtido} Caixa Aberta: {obtida}",
            description=f"Você abriu uma {emoji_obtido} **{obtida}**.",
            color=discord.Color.brand_green()
        )
        if thumb_url:
            embed.set_thumbnail(url=thumb_url)
        embed.add_field(
            name="Recompensas",
            value=f"💰 **R$ {recompensa_dinheiro:,}**\n💎 **{recompensa_premium} Moedas Premium**"
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="roleta", description="Gira a roleta diária da sorte para ganhar prêmios incríveis!")
    @lock_user()
    async def roleta(self, interaction: discord.Interaction):
        profile = await get_user_profile(interaction.user)
        now = time.time()
        
        last_roleta = profile.get("last_roleta", 0)
        extras = profile.get("roleta_extra", 0)
        
        usar_extra = False
        if extras > 0:
            usar_extra = True
        elif now - last_roleta < 86400:
            is_booster = getattr(interaction.user, "premium_since", None) is not None
            cooldown = 43200 if is_booster else 86400
            if now - last_roleta < cooldown:
                restante = cooldown - (now - last_roleta)
                horas = int(restante // 3600)
                minutos = int((restante % 3600) // 60)
                segundos = int(restante % 60)
                booster_msg = "⚡ **Bônus Booster ativo!** " if is_booster else ""
                time_str = f"{horas}h {minutos}m" if horas > 0 else f"{minutos}m {segundos}s"
                return await interaction.response.send_message(
                    f"⏳ {booster_msg}Você já girou a roleta hoje! Aguarde mais **{time_str}** ou consiga um Giro Extra.",
                    ephemeral=True
                )
            
        await interaction.response.defer()
        
        msg = await interaction.followup.send("🎡 **Preparando a Roleta da Sorte...**")
        await asyncio.sleep(1.0)
        
        itens_roleta = ["🎰", "🎰", "🎰"]
        
        await msg.edit(content=f"🎡 **Girando a Roleta...**\n\n[ {itens_roleta[0]} | {itens_roleta[1]} | {itens_roleta[2]} ]")
        await asyncio.sleep(1.2)
        
        premios = ["comum", "incomum", "giro_extra", "raro", "lendario"]
        pesos = [30, 29, 25, 15, 1]
        ganhou = random.choices(premios, weights=pesos, k=1)[0]
        
        itens_roleta[0] = "💵" if ganhou in ["comum", "incomum"] else ("🌟" if ganhou == "giro_extra" else "💎")
        await msg.edit(content=f"🎡 **Desacelerando...**\n\n[ {itens_roleta[0]} | 🎰 | 🎰 ]")
        await asyncio.sleep(1.2)
        
        itens_roleta[1] = itens_roleta[0]
        await msg.edit(content=f"🎡 **Quase parando...**\n\n[ {itens_roleta[0]} | {itens_roleta[1]} | 🎰 ]")
        await asyncio.sleep(1.2)
        
        desc_premio = ""
        color = discord.Color.light_grey()
        if ganhou == "comum":
            profile["money"] += 10_000
            desc_premio = "💵 **Prêmio Comum:** R$ **10.000** adicionados à sua conta!"
            itens_roleta[2] = "⚪"
            color = discord.Color.light_grey()
        elif ganhou == "incomum":
            profile["money"] += 25_000
            desc_premio = "💵 **Prêmio Incomum:** R$ **25.000** adicionados à sua conta!"
            itens_roleta[2] = "🟢"
            color = discord.Color.green()
        elif ganhou == "giro_extra":
            profile["roleta_extra"] = profile.get("roleta_extra", 0) + 1
            desc_premio = "🌟 **Giro Extra:** Você ganhou mais 1 tentativa grátis para usar quando quiser!"
            itens_roleta[2] = "🌟"
            color = discord.Color.gold()
        elif ganhou == "raro":
            profile["premium_coins"] = profile.get("premium_coins", 0) + 10
            desc_premio = f"💎 **Prêmio Raro:** **10 VLS Coins** ({VLS_COINS_EMOJI}) adicionadas à sua conta!"
            itens_roleta[2] = "🔵"
            color = discord.Color.blue()
        elif ganhou == "lendario":
            profile["premium_coins"] = profile.get("premium_coins", 0) + 50
            desc_premio = f"👑 **PRÊMIO LENDÁRIO:** **50 VLS Coins** ({VLS_COINS_EMOJI}) adicionadas à sua conta!"
            itens_roleta[2] = "👑"
            color = discord.Color.purple()
            
        if usar_extra:
            profile["roleta_extra"] -= 1
        else:
            profile["last_roleta"] = now
            
        await save_user_profile(interaction.user.id, profile)
        
        embed = discord.Embed(
            title="🎡 Roleta da Sorte VLS",
            description=f"**Resultado:**\n\n[ {itens_roleta[0]} | {itens_roleta[1]} | {itens_roleta[2]} ]\n\n{desc_premio}",
            color=color
        )
        embed.set_footer(text=f"Giros extras restantes: {profile.get('roleta_extra', 0)}")
        await msg.edit(content="🎉 **A roleta parou!**", embed=embed)


    @app_commands.command(name="recrutar", description="Envia olheiros para recrutar um jogador aleatório (cooldown 10 min).")
    async def recrutar(self, interaction: discord.Interaction):
        await interaction.response.defer()

        from database import get_user_lock
        lock = get_user_lock(interaction.user.id)
        async with lock:
            profile = await get_user_profile(interaction.user)
            now = datetime.now().timestamp()

            # Cooldown de 10 minutos (5 minutos para boosters)
            is_booster = getattr(interaction.user, "premium_since", None) is not None
            cooldown = 300 if is_booster else 600
            if now - profile.get("last_claim", 0) < cooldown:
                restante = cooldown - (now - profile.get("last_claim", 0))
                minutos = int(restante // 60)
                segundos = int(restante % 60)
                booster_msg = "⚡ **Bônus Booster ativo!** " if is_booster else ""
                return await interaction.followup.send(
                    f"⏳ {booster_msg}Olheiros ainda em campo! Aguarde **{minutos}m {segundos}s**."
                )

            players_data = await get_all_players()

            if not players_data:
                return await interaction.followup.send("❌ Nenhum jogador cadastrado na liga ainda.")

            # Scout bonus: reduz o expoente de decaimento com base no nível do olheiro
            # Nível 0 = expoente 0.65 (cartas comuns dominam)
            # Nível 20 = expoente 0.82 (cartas raras têm 30% mais chance)
            scout_level = profile.get("scout_level", 0)
            scout_exponent = 0.65 + (scout_level / 20) * 0.17  # varia de 0.65 a 0.82

            needs_weights = []
            for p in players_data:
                over = p.get("over", 50)
                peso = max(1, int(1_000_000_000_000 * (scout_exponent ** (over - 50))))
                needs_weights.append(peso)

            obtido = random.choices(players_data, weights=needs_weights, k=1)[0]

            profile["last_claim"] = now
            await save_user_profile(interaction.user.id, profile)

        preco = await calculate_price(obtido)
        col_emoji_tag = obtido.get("col_emoji", "✨")

        embed = discord.Embed(
            title="🌟 Novo Reforço no Gramado!",
            description=f"O atleta {col_emoji_tag} **{obtido['name']}** aceitou os termos contratuais e acabou de fechar com o seu clube!",
            color=discord.Color.purple()
        )
        embed.add_field(name="Posição", value=f"⚽ {obtido.get('pos', '?')}", inline=True)
        embed.add_field(name="Rated", value=f"⭐ {obtido.get('over', '?')}", inline=True)
        embed.add_field(name="Coleção", value=f"{col_emoji_tag} {obtido.get('col_nome', 'Comum')}", inline=True)
        embed.add_field(name="Valor de Mercado", value=f"{VLS_COINS_EMOJI} R$ {preco:,}", inline=False)
        if scout_level > 0:
            embed.add_field(name="🔎 Bônus do Olheiro", value=f"Nível {scout_level} ativo (+{int(scout_level * 1.5)}% sorte)", inline=False)

        # Animação de Revelação da Carta
        msg = await interaction.followup.send("🔎 **Olheiros voltando de campo com notícias...**")
        await asyncio.sleep(1.2)
        
        await msg.edit(content=f"🔎 **Olheiros encontraram um reforço!**\n\n⭐ Overall: **[ {obtido['over']} ]**")
        await asyncio.sleep(1.2)
        
        await msg.edit(content=f"🔎 **Olheiros encontraram um reforço!**\n\n⭐ Overall: **[ {obtido['over']} ]**\n⚽ Posição: **[ {obtido.get('pos', '?')} ]**")
        await asyncio.sleep(1.2)
        
        await msg.edit(content=f"🔎 **Olheiros encontraram um reforço!**\n\n⭐ Overall: **[ {obtido['over']} ]**\n⚽ Posição: **[ {obtido.get('pos', '?')} ]**\n🌌 Coleção: **[ {obtido.get('col_nome', 'Comum')} ]**")
        await asyncio.sleep(1.2)

        # Exibe imagem da carta se disponível
        card_path = obtido.get("card", "")
        view = ClaimView(interaction.user, obtido, preco, self)
        
        if card_path:
            if card_path.startswith("http://") or card_path.startswith("https://"):
                try:
                    from pitch_generator import load_card_image
                    # Garante que a imagem seja baixada/cacheadas no disco
                    await asyncio.to_thread(load_card_image, card_path)
                    url_hash = hashlib.md5(card_path.encode("utf-8")).hexdigest()
                    local_cache_path = os.path.join("cache_cartas", f"{url_hash}.png")
                    
                    if os.path.exists(local_cache_path):
                        file = discord.File(local_cache_path, filename="card.png")
                        embed.set_image(url="attachment://card.png")
                        await msg.edit(content="**O que você quer fazer com este jogador?**", embed=embed, view=view, attachments=[file])
                    else:
                        embed.set_image(url=card_path)
                        await msg.edit(content="**O que você quer fazer com este jogador?**", embed=embed, view=view)
                except Exception as e:
                    print(f"Erro ao obter imagem no recrutar: {e}")
                    embed.set_image(url=card_path)
                    await msg.edit(content="**O que você quer fazer com este jogador?**", embed=embed, view=view)
            elif __import__('os').path.exists(card_path):
                file = discord.File(card_path, filename="card.png")
                embed.set_image(url="attachment://card.png")
                await msg.edit(content="**O que você quer fazer com este jogador?**", embed=embed, view=view, attachments=[file])
            else:
                await msg.edit(content="**O que você quer fazer com este jogador?**", embed=embed, view=view)
        else:
            await msg.edit(content="**O que você quer fazer com este jogador?**", embed=embed, view=view)
        
        view.message = msg

        # Anúncio de Mitada (OVR >= 83)
        if obtido.get("over", 0) >= 83:
            try:
                import os
                import hashlib
                guild = interaction.guild
                if guild:
                    mitadas_channel = None
                    chan_settings = await db_get("settings_channels")
                    if chan_settings and "mitadas_channel_id" in chan_settings["data"]:
                        mitadas_channel = guild.get_channel(chan_settings["data"]["mitadas_channel_id"])
                        if not mitadas_channel:
                            try:
                                mitadas_channel = await guild.fetch_channel(chan_settings["data"]["mitadas_channel_id"])
                            except Exception:
                                pass
                                
                    if not mitadas_channel:
                        mitadas_channel = discord.utils.get(guild.channels, name="mitadas") or discord.utils.get(guild.channels, name="geral-mitadas")
                        
                    if mitadas_channel:
                        col_emoji_tag = obtido.get("col_emoji", "✨")
                        embed_mitada = discord.Embed(
                            title="🔥 MITADA HISTÓRICA NO RECRUTAR! 🔥",
                            description=f"O manager {interaction.user.mention} acaba de mitar e tirou uma carta acima de **83 OVR**!\n\n"
                                        f"🏃 Atleta: {col_emoji_tag} **{obtido['name']}**\n"
                                        f"⭐ Rated: **{obtido['over']}**\n"
                                        f"⚽ Posição: **{obtido['pos']}**\n"
                                        f"🌌 Coleção: **{obtido.get('col_nome', 'Comum')}**",
                            color=discord.Color.gold()
                        )
                        embed_mitada.set_thumbnail(url=interaction.user.display_avatar.url)
                        
                        # Tratamento da imagem do card
                        if card_path:
                            if card_path.startswith("http://") or card_path.startswith("https://"):
                                url_hash = hashlib.md5(card_path.encode("utf-8")).hexdigest()
                                local_cache_path = os.path.join("cache_cartas", f"{url_hash}.png")
                                if os.path.exists(local_cache_path):
                                    file_mitada = discord.File(local_cache_path, filename="card_mitada.png")
                                    embed_mitada.set_image(url="attachment://card_mitada.png")
                                    await mitadas_channel.send(embed=embed_mitada, file=file_mitada)
                                else:
                                    embed_mitada.set_image(url=card_path)
                                    await mitadas_channel.send(embed=embed_mitada)
                            elif os.path.exists(card_path):
                                file_mitada = discord.File(card_path, filename="card_mitada.png")
                                embed_mitada.set_image(url="attachment://card_mitada.png")
                                await mitadas_channel.send(embed=embed_mitada, file=file_mitada)
                            else:
                                await mitadas_channel.send(embed=embed_mitada)
                        else:
                            await mitadas_channel.send(embed=embed_mitada)
            except Exception as me:
                print(f"Erro ao anunciar mitada: {me}")

    @app_commands.command(name="transferir", description="Transfere fundos para outro membro (limite: R$ 100.000 por vez).")
    @app_commands.describe(usuario="Usuário que receberá os fundos", valor="Quantidade a transferir", tipo="Tipo de moeda")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Dinheiro (R$)", value="money"),
        app_commands.Choice(name="VLS Coins", value="coins")
    ])
    async def transferir(self, interaction: discord.Interaction, usuario: discord.User, valor: int, tipo: str = "money"):
        LIMITE_TRANSFER = 100_000

        if usuario.id == interaction.user.id:
            return await interaction.response.send_message("❌ Você não pode transferir para si mesmo.", ephemeral=True)
        if valor <= 0:
            return await interaction.response.send_message("❌ Insira um valor positivo.", ephemeral=True)
        if tipo == "money" and valor > LIMITE_TRANSFER:
            return await interaction.response.send_message(
                f"❌ Limite de transferência excedido. O máximo por operação é **R$ {LIMITE_TRANSFER:,}**.",
                ephemeral=True
            )

        profile = await get_user_profile(interaction.user)

        if tipo == "coins":
            if profile.get("premium_coins", 0) < valor:
                return await interaction.response.send_message("❌ Saldo de VLS Coins insuficiente.", ephemeral=True)
            profile["premium_coins"] -= valor
            dest_label = f"{VLS_COINS_EMOJI} {valor} VLS Coins"
        else:
            if profile.get("money", 0) < valor:
                return await interaction.response.send_message("❌ Saldo insuficiente.", ephemeral=True)
            profile["money"] -= valor
            dest_label = f"R$ {valor:,}"

        await save_user_profile(interaction.user.id, profile)

        dest_profile = await get_user_profile(usuario)
        if tipo == "coins":
            dest_profile["premium_coins"] += valor
        else:
            dest_profile["money"] += valor
        await save_user_profile(usuario.id, dest_profile)

        await interaction.response.send_message(
            f"✅ **Transferência Realizada!** Você enviou **{dest_label}** para o clube de {usuario.mention}."
        )

    @app_commands.command(name="upar_olheiro", description="Melhora o nível do seu olheiro para obter cartas melhores.")
    async def upar_olheiro(self, interaction: discord.Interaction):
        profile = await get_user_profile(interaction.user)
        scout_level = profile.get("scout_level", 0)

        if scout_level >= SCOUT_LEVEL_MAX:
            return await interaction.response.send_message("❌ Seu olheiro já se encontra no nível máximo (20).", ephemeral=True)

        cost = scout_level * SCOUT_BASE_UPGRADE_COST
        if scout_level == 0:
            cost = 25000  # Custo inicial

        if profile.get("money", 0) < cost:
            return await interaction.response.send_message(f"❌ Saldo de dinheiro insuficiente. Custo de upgrade: R$ {cost:,}.", ephemeral=True)

        profile["money"] -= cost
        profile["scout_level"] += 1
        
        await save_user_profile(interaction.user.id, profile)
        await self.check_achievements(interaction.user.id, profile, interaction)

        await interaction.response.send_message(
            f"🔎 **Upgrade de Olheiro!** Nível aumentado de **{scout_level}** para **{scout_level + 1}**.\n"
            f"💸 Custo: R$ {cost:,} | Multiplicador de sorte no `/recrutar` atualizado."
        )

    @app_commands.command(name="upar_torcida", description="Melhora o nível da sua torcida para apoiar mais o seu time nos jogos.")
    async def upar_torcida(self, interaction: discord.Interaction):
        profile = await get_user_profile(interaction.user)
        torcida_level = profile.get("torcida_level", 1)
        
        TORCIDA_LEVEL_MAX = 20
        if torcida_level >= TORCIDA_LEVEL_MAX:
            return await interaction.response.send_message("❌ Sua torcida já se encontra no nível máximo (20).", ephemeral=True)
            
        cost = torcida_level * 50000
        if torcida_level == 1:
            cost = 25000  # Custo inicial
            
        if profile.get("money", 0) < cost:
            return await interaction.response.send_message(f"❌ Saldo de dinheiro insuficiente. Custo de upgrade: R$ {cost:,}.", ephemeral=True)
            
        profile["money"] -= cost
        profile["torcida_level"] = torcida_level + 1
        
        await save_user_profile(interaction.user.id, profile)
        await interaction.response.send_message(
            f"📣 **Upgrade de Torcida!** Nível aumentado de **{torcida_level}** para **{torcida_level + 1}**.\n"
            f"💸 Custo: R$ {cost:,} | Sua torcida apoiará com mais vigor reduzindo penalidades e aumentando bônus!"
        )

    @app_commands.command(name="missoes", description="Exibe suas missões ativas com progresso em tempo real.")
    async def missoes(self, interaction: discord.Interaction):
        profile = await get_user_profile(interaction.user)
        
        now = datetime.utcnow()
        current_day = now.strftime("%Y-%m-%d")
        current_week = now.strftime("%Y-%W")
        current_month = now.strftime("%Y-%m")
        
        DAILY_POOL = [
            {"id": "meta_gols", "nome": "Goleador Nato — Marcar 30 gols", "criterion": "gols", "threshold": 30, "reward_type": "money", "reward_value": 50000, "type": "diario"},
            {"id": "vitorias", "nome": "Espírito Vencedor — Vencer 15 partidas", "criterion": "vitorias", "threshold": 15, "reward_type": "money", "reward_value": 60000, "type": "diario"},
            {"id": "clean_sheets", "nome": "Muralha Impenetrável — 10 clean sheets", "criterion": "clean_sheets", "threshold": 10, "reward_type": "money", "reward_value": 80000, "type": "diario"},
            {"id": "recrutar", "nome": "Futebol de Base — Recrutar 15 jogadores", "criterion": "recrutar", "threshold": 15, "reward_type": "money", "reward_value": 40000, "type": "diario"},
            {"id": "recrutar_80", "nome": "Olho Clínico — Recrutar um jogador 80+ OVR", "criterion": "recrutar_80", "threshold": 1, "reward_type": "coins", "reward_value": 15, "type": "diario"},
            {"id": "treinos", "nome": "Foco no Preparo — Jogar 6 treinos", "criterion": "treinos", "threshold": 6, "reward_type": "money", "reward_value": 30000, "type": "diario"},
            {"id": "desafios", "nome": "Desafiante Nato — Jogar 4 desafios/X1", "criterion": "desafios", "threshold": 4, "reward_type": "money", "reward_value": 25000, "type": "diario"},
            {"id": "x1_apostado", "nome": "Quem Não Arrisca... — Jogar 1 X1 apostado", "criterion": "x1_apostado", "threshold": 1, "reward_type": "coins", "reward_value": 10, "type": "diario"},
            {"id": "x1_apostado_500k", "nome": "Tudo ou Nada — Jogar X1 apostado acima de 500k", "criterion": "x1_apostado_500k", "threshold": 1, "reward_type": "coins", "reward_value": 25, "type": "diario"}
        ]
        
        mp = profile.setdefault("missions_progress", {"diario": {}, "semanal": {}, "mensal": {}, "last_weekly_reset": "", "last_monthly_reset": ""})
        if "diario" not in mp:
            mp["diario"] = {}
            
        changed = False
        
        if profile.get("last_mission_reset") != current_day or not profile.get("daily_missions"):
            profile["daily_missions"] = random.sample(DAILY_POOL, 3)
            mp["diario"] = {}
            profile["last_mission_reset"] = current_day
            changed = True
            
        if mp.get("last_weekly_reset") != current_week:
            mp["semanal"] = {}
            mp["last_weekly_reset"] = current_week
            changed = True
            
        if mp.get("last_monthly_reset") != current_month:
            mp["mensal"] = {}
            mp["last_monthly_reset"] = current_month
            changed = True
            
        if changed:
            await save_user_profile(interaction.user.id, profile)
            
        db_missions = await get_missions() or []
        combined_missions = profile.get("daily_missions", []) + db_missions
        
        if not combined_missions:
            return await interaction.response.send_message("📋 Não há nenhuma missão ativa no momento.", ephemeral=True)
            
        embed = discord.Embed(
            title="📋 Quadro de Missões",
            description="Selecione uma missão no menu abaixo para ver detalhes ou resgatar a recompensa.",
            color=discord.Color.blue()
        )
        
        for m in combined_missions:
            m_id = m["id"]
            m_type = m.get("type", "semanal")
            m_nome = m.get("nome", m_id.replace("_", " ").title())
            m_threshold = m["threshold"]
            m_crit = m.get("criterion", "?")
            progress_val = mp.setdefault(m_type, {}).get(m_id, 0)
            
            if progress_val == "claimed":
                status_icon = "✅"
                prog_str = "Reivindicada"
            elif isinstance(progress_val, int) and progress_val >= m_threshold:
                status_icon = "⭐"
                prog_str = f"{m_threshold}/{m_threshold}"
            else:
                status_icon = "⏳"
                val = progress_val if isinstance(progress_val, int) else 0
                prog_str = f"{val}/{m_threshold}"
                
            rew_label = ""
            if m.get("reward_type") == "money":
                rew_label = f"R$ {m.get('reward_value', 0):,}"
            elif m.get("reward_type") == "coins":
                rew_label = f"{m.get('reward_value', 0)} {VLS_COINS_EMOJI}"
                
            tipo_badge = "☀️" if m_type == "diario" else ("📅" if m_type == "semanal" else "📆")
            embed.add_field(
                name=f"{status_icon} {tipo_badge} {m_nome}",
                value=f"`{prog_str}` {m_crit.capitalize()} • 🏆 {rew_label}",
                inline=False
            )
            
        view = MissoesView(interaction.user.id, combined_missions, mp, profile)
        await interaction.response.send_message(embed=embed, view=view)


class CustomProductSelect(discord.ui.Select):
    def __init__(self, products):
        options = []
        for p in products:
            p_data = p
            emoji_obj = p_data.get("emoji", "📦")
            options.append(discord.SelectOption(
                label=f"{p_data['name']} ({p_data['price']} Coins)",
                value=p_data["id"],
                description=p_data.get("description", "")[:100],
                emoji=emoji_obj if len(emoji_obj) == 1 else None
            ))
        super().__init__(placeholder="🛍️ Adquirir produto personalizado...", options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        prod_id = self.values[0]
        record = await db_get(f"loja_produto_{prod_id}")
        if not record:
            return await interaction.response.send_message("❌ Produto não encontrado.", ephemeral=True)
            
        p_data = record["data"]
        cost = p_data["price"]
        
        await interaction.response.defer()
        # Acessa a view dona do select
        tienda_view = self.view
        profile = await get_user_profile(tienda_view.user)
        
        if profile.get("premium_coins", 0) < cost:
            return await interaction.followup.send(
                f"💸 Você não tem VLS Coins suficientes. Custo: {VLS_COINS_EMOJI} {cost} Coins.",
                ephemeral=True
            )
            
        profile["premium_coins"] -= cost
        
        if p_data["type"] == "jogador":
            chosen_id = p_data["items"][0]
        else:
            chosen_id = random.choice(p_data["items"])
            
        j_rec = await db_get(f"player_{chosen_id}")
        if not j_rec:
            return await interaction.followup.send(
                f"❌ Erro crítico: Carta `{chosen_id}` não foi encontrada no banco global.",
                ephemeral=True
            )
            
        player_template = j_rec["data"]
        instanced = player_template.copy()
        instanced["instance_id"] = str(uuid.uuid4())[:8]
        instanced["original_pos"] = player_template["pos"]
        instanced["acquired_at"] = datetime.utcnow().isoformat()
        instanced.update({"goals": 0, "assists": 0, "saves": 0, "matches": 0, "mvps": 0, "yellow_cards": 0, "red_cards": 0, "xp": 0})
        
        profile.setdefault("inventory", []).append(instanced)
        await save_user_profile(tienda_view.user.id, profile)
        
        col_emoji = player_template.get("col_emoji", "✨")
        
        embed = discord.Embed(
            title=f"🎉 Produto Adquirido!",
            description=(
                f"Você comprou **{p_data['name']}** por {VLS_COINS_EMOJI} **{cost} Coins**!\n\n"
                f"**Item Recebido:**\n"
                f"{col_emoji} **{player_template['name']}** (Rated: {player_template['over']} | Posição: {player_template['pos']})"
            ),
            color=discord.Color.green()
        )
        
        card_path = player_template.get("card", "")
        if card_path:
            if card_path.startswith("http://") or card_path.startswith("https://"):
                try:
                    from pitch_generator import load_card_image
                    # Garante que a imagem seja baixada/cacheadas no disco
                    await asyncio.to_thread(load_card_image, card_path)
                    url_hash = hashlib.md5(card_path.encode("utf-8")).hexdigest()
                    local_cache_path = os.path.join("cache_cartas", f"{url_hash}.png")
                    
                    if os.path.exists(local_cache_path):
                        file = discord.File(local_cache_path, filename="card.png")
                        embed.set_image(url="attachment://card.png")
                        await interaction.followup.send(embed=embed, file=file)
                    else:
                        embed.set_image(url=card_path)
                        await interaction.followup.send(embed=embed)
                except Exception as e:
                    print(f"Erro ao obter imagem no produto da loja: {e}")
                    embed.set_image(url=card_path)
                    await interaction.followup.send(embed=embed)
            elif __import__('os').path.exists(card_path):
                file = discord.File(card_path, filename="card.png")
                embed.set_image(url="attachment://card.png")
                await interaction.followup.send(embed=embed, file=file)
            else:
                await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(embed=embed)


# View auxiliar para abrir pacotes de cartas

# View auxiliar para abrir pacotes de cartas e comprar táticas

class LojaCategorySelect(discord.ui.Select):
    def __init__(self, all_players, custom_products):
        options = [
            discord.SelectOption(label="📦 Pacotes de Cartas", value="packs", description="Compre pacotes de atletas usando VLS Coins."),
            discord.SelectOption(label="🧠 Filosofias Táticas", value="tactics", description="Desbloqueie novas filosofias táticas usando Dinheiro (R$)."),
        ]
        if custom_products:
            options.append(discord.SelectOption(label="🛍️ Produtos da Liga", value="custom", description="Produtos adicionais criados pela liga."))
            
        super().__init__(placeholder="🛍️ Navegar pelas categorias da loja...", options=options, row=4)
        self.all_players = all_players
        self.custom_products = custom_products

    async def callback(self, interaction: discord.Interaction):
        cat = self.values[0]
        view: LojaView = self.view
        await view.switch_category(interaction, cat)


class BuyPackButton(discord.ui.Button):
    def __init__(self, label, style, pack_type, cost, row):
        super().__init__(label=label, style=style, row=row)
        self.pack_type = pack_type
        self.cost = cost

    async def callback(self, interaction: discord.Interaction):
        view: LojaView = self.view
        if interaction.user.id != view.user.id:
            return await interaction.response.send_message("❌ Esta loja não é sua.", ephemeral=True)
            
        if self.pack_type == "basico":
            probs = {"Comum": 0.66, "Rara": 0.25, "Épica": 0.03, "TOTW": 0.03, "TOTS": 0.02, "Lendária": 0.01}
            await view.process_purchase(interaction, "Básico", 20, 1, probs, coin_reward=(12000, 30000))
        elif self.pack_type == "padrao":
            probs = {"Comum": 0.51, "Rara": 0.35, "Épica": 0.05, "TOTW": 0.05, "TOTS": 0.02, "Lendária": 0.02}
            await view.process_purchase(interaction, "Padrão", 50, 2, probs, coin_reward=(23000, 40000))
        elif self.pack_type == "premium":
            probs = {"Comum": 0.36, "Rara": 0.45, "Épica": 0.07, "TOTW": 0.07, "TOTS": 0.02, "Lendária": 0.03}
            await view.process_purchase(interaction, "Premium", 100, 3, probs, coin_reward=(30000, 50000))
        elif self.pack_type == "elite":
            probs = {"Comum": 0.21, "Rara": 0.50, "Épica": 0.10, "TOTW": 0.10, "TOTS": 0.04, "Lendária": 0.05}
            guaranteed = ["Lendária"]
            await view.process_purchase(interaction, "Elite", 250, 3, probs, guaranteed, coin_reward=(50000, 100000))


class BuyTacticSelect(discord.ui.Select):
    def __init__(self):
        options = []
        from config import TACTICS
        for t_key, t_data in TACTICS.items():
            if t_key == "padrao":
                continue
            preco = 150000 if t_key != "futebol_total" else 200000
            if t_key == "park_the_bus":
                preco = 100000
            options.append(discord.SelectOption(
                label=f"{t_data['name']} (R$ {preco:,})",
                value=t_key,
                description=t_data["desc"][:100]
            ))
        super().__init__(placeholder="🧠 Escolha uma tática para comprar...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        t_key = self.values[0]
        view: LojaView = self.view
        if interaction.user.id != view.user.id:
            return await interaction.response.send_message("❌ Esta loja não é sua.", ephemeral=True)
            
        await interaction.response.defer()
        from config import TACTICS
        profile = await get_user_profile(interaction.user)
        acquired = profile.setdefault("acquired_tactics", ["padrao"])
        
        if t_key in acquired:
            return await interaction.followup.send("❌ Você já possui esta filosofia tática.", ephemeral=True)
            
        preco = 150000 if t_key != "futebol_total" else 200000
        if t_key == "park_the_bus":
            preco = 100000
            
        if profile.get("money", 0) < preco:
            return await interaction.followup.send(
                f"❌ Saldo de dinheiro insuficiente. Custa R$ {preco:,} e seu saldo é R$ {profile.get('money', 0):,}.",
                ephemeral=True
            )
            
        profile["money"] -= preco
        profile["acquired_tactics"].append(t_key)
        await save_user_profile(interaction.user.id, profile)
        
        embed = await view.make_category_embed()
        await interaction.edit_original_response(embed=embed, view=view)
        await interaction.followup.send(
            f"🎉 **Tática Adquirida!** Filosofia **{TACTICS[t_key]['name']}** comprada por R$ {preco:,}!"
        )


class LojaView(discord.ui.View):
    def __init__(self, user, all_players, custom_products=None, cog=None):
        super().__init__(timeout=180)
        self.user = user
        self.all_players = all_players
        self.custom_products = custom_products or []
        self.current_category = "packs"
        self.cog = cog
        
        # Adiciona a seleção de categoria
        self.add_item(LojaCategorySelect(all_players, self.custom_products))
        self.setup_category_components()

    def setup_category_components(self):
        category_select = None
        for item in list(self.children):
            if isinstance(item, LojaCategorySelect):
                category_select = item
            else:
                self.remove_item(item)
                
        if self.current_category == "packs":
            self.add_item(BuyPackButton(label="Básico (20 Coins)", style=discord.ButtonStyle.secondary, pack_type="basico", cost=20, row=0))
            self.add_item(BuyPackButton(label="Padrão (50 Coins)", style=discord.ButtonStyle.primary, pack_type="padrao", cost=50, row=0))
            self.add_item(BuyPackButton(label="Premium (100 Coins)", style=discord.ButtonStyle.success, pack_type="premium", cost=100, row=1))
            self.add_item(BuyPackButton(label="Elite (250 Coins)", style=discord.ButtonStyle.danger, pack_type="elite", cost=250, row=1))
        elif self.current_category == "tactics":
            self.add_item(BuyTacticSelect())
        elif self.current_category == "custom":
            self.add_item(CustomProductSelect(self.custom_products))

    async def switch_category(self, interaction: discord.Interaction, category: str):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌ Esta loja não é sua.", ephemeral=True)
            
        self.current_category = category
        self.setup_category_components()
        
        embed = await self.make_category_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def make_category_embed(self) -> discord.Embed:
        from config import TACTICS
        profile = await get_user_profile(self.user)
        
        if self.current_category == "packs":
            embed = discord.Embed(
                title="📦 Loja Oficial VLS — Pacotes",
                description=f"Selecione abaixo o pacote que deseja abrir usando VLS Coins ({VLS_COINS_EMOJI}).\n"
                            f"Seu Saldo: {VLS_COINS_EMOJI} **{profile.get('premium_coins', 0)} Coins**",
                color=discord.Color.purple()
            )
            embed.add_field(name="📦 Pacote Básico", value=f"💰 Preço: **20 {VLS_COINS_EMOJI}**\n*Atleta base/comum/raro/etc.*", inline=True)
            embed.add_field(name="🎒 Pacote Padrão", value=f"💰 Preço: **50 {VLS_COINS_EMOJI}**\n*2 cartas, chances melhoradas.*", inline=True)
            embed.add_field(name="🎁 Pacote Premium", value=f"💰 Preço: **100 {VLS_COINS_EMOJI}**\n*3 cartas, excelentes chances.*", inline=True)
            embed.add_field(name="👑 Pacote Elite", value=f"💰 Preço: **250 {VLS_COINS_EMOJI}**\n⚡ *3 cartas com 1 Épica+ garantida!*", inline=False)
            
        elif self.current_category == "tactics":
            embed = discord.Embed(
                title="🧠 Loja Oficial VLS — Filosofias Táticas",
                description=f"Adquira novas filosofias táticas para o seu clube usando Dinheiro (R$).\n"
                            f"Seu Saldo: **R$ {profile.get('money', 0):,}**\n\n"
                            f"**Táticas Disponíveis:**",
                color=discord.Color.blue()
            )
            for t_key, t_data in TACTICS.items():
                if t_key == "padrao":
                    continue
                preco = 150000 if t_key != "futebol_total" else 200000
                if t_key == "park_the_bus":
                    preco = 100000
                
                owned = t_key in profile.get("acquired_tactics", ["padrao"])
                status = "✅ Adquirida" if owned else f"🛒 R$ {preco:,}"
                embed.add_field(name=f" Filosofia: {t_data['name']} ({status})", value=f"*{t_data['desc']}*", inline=False)
                
        elif self.current_category == "custom":
            embed = discord.Embed(
                title="🛍️ Loja Oficial VLS — Produtos da Liga",
                description=f"Produtos e itens personalizados da Liga.\n"
                            f"Seu Saldo: {VLS_COINS_EMOJI} **{profile.get('premium_coins', 0)} Coins**",
                color=discord.Color.green()
            )
            prod_desc = ""
            for p in self.custom_products:
                p_data = p
                prod_desc += f"{p_data.get('emoji', '📦')} **{p_data['name']}** — **{p_data['price']} Coins**\n*{p_data.get('description', '')}*\n\n"
            embed.description += "\n\n" + (prod_desc or "*Nenhum produto cadastrado.*")
            
        return embed

    @lock_user()
    async def process_purchase(self, interaction, pack_name, cost, num_cards, probs, guaranteed=None, coin_reward=(0, 0)):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("❌ Esta loja não é sua.", ephemeral=True)

        await interaction.response.defer()
        profile = await get_user_profile(self.user)

        if profile.get("premium_coins", 0) < cost:
            return await interaction.followup.send(
                f"💸 Você não tem VLS Coins suficientes. Precisa de {VLS_COINS_EMOJI} {cost} Coins.",
                ephemeral=True
            )

        profile["premium_coins"] -= cost
        moedas_ganhas = 0
        if coin_reward[1] > 0:
            moedas_ganhas = random.randint(coin_reward[0], coin_reward[1])
            profile["money"] += moedas_ganhas

        drawn_players = []
        rarities = list(probs.keys())
        weights = list(probs.values())

        rarity_emojis = {
            "Comum": "⚪", "Rara": "🔵", "Épica": "🟣",
            "TOTW": "🔴", "TOTS": "🏆", "Lendária": "👑"
        }

        for i in range(num_cards):
            if guaranteed and i == num_cards - 1:
                chosen_rarity = random.choice(guaranteed)
            else:
                chosen_rarity = random.choices(rarities, weights=weights, k=1)[0]

            player = get_player_by_rarity(chosen_rarity, self.all_players)
            player["instance_id"] = str(uuid.uuid4())[:8]
            player["xp"] = 0
            profile["inventory"].append(player)
            drawn_players.append((chosen_rarity, player))

        # Incrementa missões de recrutamento
        if self.cog:
            await self.cog.increment_mission(interaction.user.id, profile, "recrutar", num_cards)
            for rarity, p in drawn_players:
                if p.get("over", 0) >= 80:
                    await self.cog.increment_mission(interaction.user.id, profile, "recrutar_80", 1)

        await save_user_profile(interaction.user.id, profile)

        msg = await interaction.followup.send("⏳ **Processando compra do pacote...**")
        await asyncio.sleep(1.0)
        
        # Revelação animada de cada carta
        for idx, (rarity, p) in enumerate(drawn_players, 1):
            base_content = f"📦 **Abrindo Pacote {pack_name} (Carta {idx}/{num_cards}):**\n\n"
            
            await msg.edit(content=base_content + f"⭐ Overall: **[ {p['over']} ]**")
            await asyncio.sleep(1.2)
            
            await msg.edit(content=base_content + f"⭐ Overall: **[ {p['over']} ]**\n⚽ Posição: **[ {p.get('pos', '?')} ]**")
            await asyncio.sleep(1.2)
            
            await msg.edit(content=base_content + f"⭐ Overall: **[ {p['over']} ]**\n⚽ Posição: **[ {p.get('pos', '?')} ]**\n🌌 Coleção: **[ {p.get('col_nome', 'Comum')} ]**")
            await asyncio.sleep(1.2)
            
            emoji = rarity_emojis.get(rarity, "⚪")
            await msg.edit(content=base_content + f"🎉 **{emoji} {p['name']}!**\n⭐ Overall: `{p['over']}` | ⚽ Posição: `{p.get('pos', '?')}` | 🌌 Coleção: `{p.get('col_nome', 'Comum')}`")
            await asyncio.sleep(1.5)

        embed = discord.Embed(title=f"📦 Pacote {pack_name} Aberto!", color=discord.Color.gold())
        desc = ""
        for rarity, p in drawn_players:
            emoji = rarity_emojis.get(rarity, "⚪")
            col_emoji = p.get("col_emoji", "✨")
            desc += f"{emoji} **{rarity}** | ⭐ `{p['over']}` — {p['pos']} | {col_emoji} **{p['name']}** | Coleção: {p.get('col_nome', 'Comum')}\n"
        
        if moedas_ganhas > 0:
            desc += f"\n💵 **Bônus:** R$ {moedas_ganhas:,}\n"

        embed.description = desc
        embed.set_footer(text=f"VLS Coins restantes: {profile['premium_coins']} Coins")
        await msg.edit(content="✅ **Abertura concluída!**", embed=embed)


class ClaimView(discord.ui.View):
    def __init__(self, user, player, preco, cog):
        super().__init__(timeout=60)
        self.user = user
        self.player = player
        self.preco_venda = int(preco * 0.25)
        self.processed = False
        self.confirming_sale = False
        self.message = None
        self.cog = cog

    async def on_timeout(self):
        if not self.processed:
            self.processed = True
            try:
                profile = await get_user_profile(self.user)
                player_copy = self.player.copy()
                player_copy["instance_id"] = str(uuid.uuid4())[:8]
                profile["inventory"].append(player_copy)
                
                # Incrementa missões
                await self.cog.increment_mission(self.user.id, profile, "recrutar", 1)
                if player_copy.get("over", 0) >= 80:
                    await self.cog.increment_mission(self.user.id, profile, "recrutar_80", 1)

                await save_user_profile(self.user.id, profile)
                if self.message:
                    col_icon = self.player.get("col_emoji", "✨")
                    embed = discord.Embed(
                        title=f"🎉 {col_icon} {self.player['name']} Adicionado ao Clube!",
                        description=f"✅ Jogador salvo automaticamente no inventário por inatividade.\nColeção: **{self.player.get('col_nome', 'Comum')}**",
                        color=discord.Color.green()
                    )
                    for child in self.children:
                        child.disabled = True
                    await self.message.edit(content="⏱️ Tempo esgotado. Jogador salvo.", embed=embed, view=self)
            except Exception:
                pass

    @discord.ui.button(label="✅ Ficar no Clube", style=discord.ButtonStyle.success)
    @lock_user()
    async def keep_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.processed:
            return await interaction.response.defer()
        self.processed = True

        profile = await get_user_profile(self.user)
        player_copy = self.player.copy()
        player_copy["instance_id"] = str(uuid.uuid4())[:8]
        player_copy["xp"] = 0
        profile["inventory"].append(player_copy)
        
        # Incrementa missões
        await self.cog.increment_mission(interaction.user.id, profile, "recrutar", 1)
        if player_copy.get("over", 0) >= 80:
            await self.cog.increment_mission(interaction.user.id, profile, "recrutar_80", 1)

        await save_user_profile(interaction.user.id, profile)

        col_icon = self.player.get("col_emoji", "✨")
        embed = discord.Embed(
            title=f"🎉 {col_icon} {self.player['name']} Adicionado!",
            description=f"✅ Jogador salvo no seu inventário.\nColeção: **{self.player.get('col_nome', 'Comum')}**",
            color=discord.Color.green()
        )
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="💰 Vender Imediatamente", style=discord.ButtonStyle.danger)
    @lock_user()
    async def sell_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user.id or self.processed:
            return await interaction.response.defer()

        if not self.confirming_sale:
            self.confirming_sale = True
            button.label = "⚠️ Confirmar Venda"
            button.style = discord.ButtonStyle.danger
            
            col_icon = self.player.get("col_emoji", "✨")
            embed = discord.Embed(
                title=f"⚠️ Confirmar Venda: {self.player['name']}?",
                description=f"Você está prestes a vender este jogador por **{VLS_COINS_EMOJI} R$ {self.preco_venda:,}**.\nClique novamente no botão vermelho para confirmar a venda.",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=self)
            return

        self.processed = True

        profile = await get_user_profile(self.user)
        profile["money"] += self.preco_venda
        await save_user_profile(interaction.user.id, profile)

        embed = discord.Embed(
            title=f"💰 {self.player['name']} Vendido!",
            description=f"Recebeu **{VLS_COINS_EMOJI} R$ {self.preco_venda:,}** pela venda imediata do card da coleção **{self.player.get('col_nome', 'Comum')}**.",
            color=discord.Color.gold()
        )
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(embed=embed, view=self)

class SimplePaginationView(discord.ui.View):
    def __init__(self, embeds):
        super().__init__(timeout=60)
        self.embeds = embeds
        self.current_page = 0

    @discord.ui.button(label="◀️ Anterior", style=discord.ButtonStyle.blurple)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page])

    @discord.ui.button(label="Próximo ▶️", style=discord.ButtonStyle.blurple)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page])


# View principal de Missões com dropdown de detalhes + claim
class MissoesView(discord.ui.View):
    def __init__(self, owner_id: int, missions: list, mp: dict, profile: dict):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.missions = missions
        self.mp = mp
        self.profile = profile

        options = []
        for m in missions[:25]:
            m_id = m["id"]
            m_type = m.get("type", "semanal")
            m_nome = m.get("nome", m_id.replace("_", " ").title())
            progress_val = mp.get(m_type, {}).get(m_id, 0)

            if progress_val == "claimed":
                emoji = "✅"
            elif isinstance(progress_val, int) and progress_val >= m["threshold"]:
                emoji = "⭐"
            else:
                emoji = "⏳"

            options.append(discord.SelectOption(label=m_nome[:100], value=m_id, emoji=emoji))

        self.add_item(MissaoDetailDropdown(owner_id, missions, mp, profile, options))

    @discord.ui.button(label="🏆 Resgatar Completas", style=discord.ButtonStyle.success, row=1)
    async def claim_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)

        fresh_profile = await get_user_profile(interaction.user)
        fresh_mp = fresh_profile.get("missions_progress", {})
        db_missions = await get_missions() or []
        combined = fresh_profile.get("daily_missions", []) + db_missions
        claimed_names = []

        for m in combined:
            m_id = m["id"]
            m_type = m.get("type", "semanal")
            progress_val = fresh_mp.setdefault(m_type, {}).get(m_id, 0)
            if not (isinstance(progress_val, int) and progress_val >= m["threshold"]):
                continue

            # Concede recompensa
            if m.get("reward_type") == "money":
                fresh_profile["money"] = fresh_profile.get("money", 0) + m.get("reward_value", 0)
            elif m.get("reward_type") == "coins":
                fresh_profile["premium_coins"] = fresh_profile.get("premium_coins", 0) + m.get("reward_value", 0)
            elif m.get("reward_type") == "player":
                p_rec = await __import__('database').db_get(f"player_{m.get('reward_player_id','')}")
                if p_rec:
                    import uuid as _uuid
                    from datetime import datetime as _dt
                    inst = p_rec["data"].copy()
                    inst["instance_id"] = str(_uuid.uuid4())[:8]
                    inst["acquired_at"] = _dt.utcnow().isoformat()
                    inst.update({"goals":0,"assists":0,"saves":0,"matches":0,"mvps":0,"yellow_cards":0,"red_cards":0,"xp":0})
                    fresh_profile.setdefault("inventory", []).append(inst)

            fresh_mp[m_type][m_id] = "claimed"
            nome = m.get("nome", m_id.replace("_"," ").title())
            claimed_names.append(nome)

        if not claimed_names:
            return await interaction.response.send_message("ℹ️ Nenhuma missão concluída para resgatar.", ephemeral=True)

        fresh_profile["missions_progress"] = fresh_mp
        await save_user_profile(interaction.user.id, fresh_profile)

        await interaction.response.send_message(
            f"✅ **{len(claimed_names)} missão(ões) resgatada(s)!**\n" +
            "\n".join([f"• {n}" for n in claimed_names]),
            ephemeral=True
        )


class MissaoDetailDropdown(discord.ui.Select):
    def __init__(self, owner_id, missions, mp, profile, options):
        self.owner_id = owner_id
        self.missions = {m["id"]: m for m in missions}
        self.mp = mp
        self.profile = profile
        super().__init__(placeholder="Selecione uma missão para ver detalhes...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)

        m_id = self.values[0]
        m = self.missions.get(m_id)
        if not m:
            return await interaction.response.send_message("❌ Missão não encontrada.", ephemeral=True)

        m_type = m.get("type", "semanal")
        m_nome = m.get("nome", m_id.replace("_", " ").title())
        m_crit = m.get("criterion", "?")
        m_threshold = m.get("threshold", 1)
        progress_val = self.mp.setdefault(m_type, {}).get(m_id, 0)

        if progress_val == "claimed":
            status = "✅ Já reivindicada"
            prog_str = f"{m_threshold}/{m_threshold}"
        elif isinstance(progress_val, int) and progress_val >= m_threshold:
            status = "⭐ Pronta para resgatar!"
            prog_str = f"{m_threshold}/{m_threshold}"
        else:
            val = progress_val if isinstance(progress_val, int) else 0
            prog_str = f"{val}/{m_threshold}"
            status = "⏳ Em progresso"

        rew_label = ""
        if m.get("reward_type") == "money":
            rew_label = f"R$ {m.get('reward_value', 0):,}"
        elif m.get("reward_type") == "coins":
            rew_label = f"{m.get('reward_value', 0)} VLS Coins"
        elif m.get("reward_type") == "player":
            rew_label = f"Carta: `{m.get('reward_player_id','?')}`"

        tipo_badge = "☀️ Diário" if m_type == "diario" else ("📅 Semanal" if m_type == "semanal" else "📆 Mensal")

        embed = discord.Embed(
            title=f"📌 {m_nome}",
            color=discord.Color.gold() if "⭐" in status else discord.Color.blue()
        )
        embed.add_field(name="🎯 Objetivo", value=f"Atingir **{m_threshold}** em **{m_crit.capitalize()}**", inline=True)
        embed.add_field(name="🏆 Recompensa", value=rew_label, inline=True)
        embed.add_field(name="🕐 Tipo", value=tipo_badge, inline=True)
        embed.add_field(name="📊 Progresso", value=f"**{prog_str}** {m_crit.capitalize()}", inline=False)
        embed.add_field(name="Status", value=status, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)


# View para reivindicar missões concluídas
class ClaimMissionsView(discord.ui.View):
    def __init__(self, owner_id, missions):
        super().__init__(timeout=60)
        self.owner_id = owner_id
        options = [
            discord.SelectOption(label=m["id"].replace("_", " ").title(), value=m["id"])
            for m in missions
        ]
        self.add_item(ClaimDropdown(owner_id, options, missions))


class ClaimDropdown(discord.ui.Select):
    def __init__(self, owner_id, options, missions):
        self.owner_id = owner_id
        self.missions = {m["id"]: m for m in missions}
        super().__init__(placeholder="Selecione a missão para reivindicar", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)

        chosen_id = self.values[0]
        mission = self.missions[chosen_id]

        profile = await get_user_profile(interaction.user)
        m_type = mission["type"]

        # Concede recompensa
        rew_label = ""
        if mission["reward_type"] == "money":
            profile["money"] += mission["reward_value"]
            rew_label = f"R$ {mission['reward_value']:,}"
        elif mission["reward_type"] == "coins":
            profile["premium_coins"] += mission["reward_value"]
            rew_label = f"{mission['reward_value']} VLS Coins"
        elif mission["reward_type"] == "player":
            player_id = mission["reward_player_id"]
            # Busca jogador global
            p_record = await db_get(f"player_{player_id}")
            if p_record:
                player_template = p_record["data"]
                instanced = player_template.copy()
                instanced["instance_id"] = str(uuid.uuid4())
                instanced["original_pos"] = player_template["pos"]
                instanced["acquired_at"] = datetime.utcnow().isoformat()
                instanced["goals"] = 0
                instanced["assists"] = 0
                instanced["saves"] = 0
                instanced["matches"] = 0
                instanced["mvps"] = 0
                instanced["yellow_cards"] = 0
                instanced["red_cards"] = 0
                profile["inventory"].append(instanced)
                rew_label = f"Carta de {player_template['name']}"
            else:
                rew_label = "Jogador não localizado (CPU creditou R$ 10.000 como reembolso)"
                profile["money"] += 10000

        # Marca como reivindicada
        profile["missions_progress"][m_type][chosen_id] = "claimed"
        
        await save_user_profile(interaction.user.id, profile)

        # Checa conquistas
        cog = interaction.client.get_cog("Economia")
        if cog:
            await cog.check_achievements(interaction.user.id, profile, interaction)

        await interaction.response.send_message(
            f"🎁 **Missão Reivindicada!** Você concluiu a missão e recebeu a recompensa: **{rew_label}**."
        )

async def setup(bot):
    await bot.add_cog(EconomyCog(bot))
