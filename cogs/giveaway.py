# -*- coding: utf-8 -*-
"""
VLS Guru - Cog de Sorteios (Giveaways)
Permite a criação de sorteios de cartas, coins e dinheiro com duração e restrição para apoiadores (Boosters).
O sorteio é salvo no banco de dados e finalizado automaticamente por uma task em background.
"""
import discord
import asyncio
import time
import uuid
from datetime import datetime
from discord.ext import commands, tasks
from discord import app_commands

from database import db_get, db_upsert, db_get_prefix, get_user_profile, save_user_profile
from config import VLS_COINS_EMOJI, ALLOWED_ADMIN_IDS

def parse_duration(duration_str: str) -> int | None:
    duration_str = duration_str.strip().lower()
    if not duration_str:
        return None
    try:
        if duration_str.endswith("m"):
            return int(duration_str[:-1]) * 60
        elif duration_str.endswith("h"):
            return int(duration_str[:-1]) * 3600
        elif duration_str.endswith("d"):
            return int(duration_str[:-1]) * 86400
        else:
            return int(duration_str) * 60
    except ValueError:
        return None

class DummyUser:
    def __init__(self, uid: int):
        self.id = uid

class GiveawayJoinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Participar",
        style=discord.ButtonStyle.success,
        custom_id="vls_giveaway:join",
        emoji="🎉"
    )
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        doc_id = f"giveaway_{interaction.message.id}"
        doc = await db_get(doc_id)
        if not doc:
            return await interaction.response.send_message("❌ Sorteio não encontrado no banco de dados.", ephemeral=True)
            
        data = doc["data"]
        if not data.get("active", True):
            return await interaction.response.send_message("❌ Este sorteio já foi encerrado.", ephemeral=True)
            
        user_id = interaction.user.id
        participants = data.get("participants", [])
        
        # Verifica se é exclusivo para boosters
        if data.get("only_boosters", False):
            is_booster = getattr(interaction.user, "premium_since", None) is not None
            if not is_booster and user_id not in ALLOWED_ADMIN_IDS:
                return await interaction.response.send_message(
                    "❌ Este sorteio é exclusivo para **Apoiadores do Servidor** (Server Boosters)! "
                    "Dê boost no servidor para poder participar.",
                    ephemeral=True
                )
                
        if user_id in participants:
            participants.remove(user_id)
            await db_upsert(doc_id, data)
            
            embed = interaction.message.embeds[0]
            embed.set_field_at(
                index=1,
                name="👥 Participantes",
                value=f"**{len(participants)}** managers",
                inline=True
            )
            await interaction.response.edit_message(embed=embed)
            await interaction.followup.send("⚠️ Você saiu do sorteio.", ephemeral=True)
            return
            
        participants.append(user_id)
        await db_upsert(doc_id, data)
        
        embed = interaction.message.embeds[0]
        embed.set_field_at(
            index=1,
            name="👥 Participantes",
            value=f"**{len(participants)}** managers",
            inline=True
        )
        await interaction.response.edit_message(embed=embed)
        await interaction.followup.send("✅ Você entrou no sorteio com sucesso! Boa sorte! 🎉", ephemeral=True)


class GiveawayCog(commands.Cog, name="Sorteios"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(GiveawayJoinView())
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    @tasks.loop(seconds=10)
    async def check_giveaways(self):
        try:
            now = int(time.time())
            giveaways = await db_get_prefix("giveaway_")
            for g in giveaways:
                if g.get("active", True) and g.get("end_time", 0) <= now:
                    await self.resolve_giveaway(g)
        except Exception as e:
            print(f"[Giveaways Task] Erro na verificação de sorteios: {e}")

    @check_giveaways.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    async def resolve_giveaway(self, g: dict):
        g["active"] = False
        doc_id = f"giveaway_{g['message_id']}"
        await db_upsert(doc_id, g)
        
        channel = self.bot.get_channel(g["channel_id"])
        if not channel:
            try:
                channel = await self.bot.fetch_channel(g["channel_id"])
            except Exception:
                print(f"[Giveaway] Canal {g['channel_id']} não encontrado ao resolver sorteio.")
                return
                
        try:
            message = await channel.fetch_message(g["message_id"])
        except Exception:
            print(f"[Giveaway] Mensagem {g['message_id']} não encontrada para resolver sorteio.")
            return

        participants = g.get("participants", [])
        tipo = g.get("tipo", "carta")
        premio = g["premio"]
        
        if not participants:
            embed = message.embeds[0]
            embed.title = "❌ SORTEIO ENCERRADO ❌"
            embed.color = discord.Color.red()
            embed.set_field_at(index=2, name="⏳ Status", value="Encerrado (Sem participantes)", inline=True)
            
            try:
                view = discord.ui.View.from_message(message)
                for child in view.children:
                    child.disabled = True
                await message.edit(embed=embed, view=view)
            except Exception as ve:
                print(f"[Giveaway] Erro ao desabilitar botões: {ve}")
                await message.edit(embed=embed)
                
            await channel.send(f"⚠️ O sorteio encerrou sem participantes.")
            return

        import random
        winner_id = random.choice(participants)
        
        try:
            winner_user = self.bot.get_user(winner_id)
            if not winner_user:
                winner_user = await self.bot.fetch_user(winner_id)
        except Exception:
            winner_user = None
            
        winner_mention = f"<@{winner_id}>" if not winner_user else winner_user.mention
        winner_profile = await get_user_profile(DummyUser(winner_id))
        
        # Processa o prêmio com base no tipo
        desc_premio = ""
        if tipo == "carta":
            p_doc = await db_get(f"player_{premio}")
            if not p_doc:
                await channel.send(f"❌ Erro ao finalizar sorteio: Carta `{premio}` não encontrada no catálogo.")
                return
            player_template = p_doc["data"]
            col_emoji = player_template.get("col_emoji", "✨")
            
            instanced = player_template.copy()
            instanced["instance_id"] = str(uuid.uuid4())[:8]
            instanced["original_pos"] = player_template["pos"]
            instanced["acquired_at"] = datetime.utcnow().isoformat()
            instanced.update({
                "goals": 0, "assists": 0, "saves": 0, "matches": 0, "mvps": 0,
                "yellow_cards": 0, "red_cards": 0, "xp": 0
            })
            
            winner_profile.setdefault("inventory", []).append(instanced)
            desc_premio = f"a carta {col_emoji} **{player_template['name']}** (OVR {player_template['over']})"
            
        elif tipo == "coins":
            amount = int(premio)
            winner_profile["premium_coins"] = winner_profile.get("premium_coins", 0) + amount
            desc_premio = f"**{amount:,}** {VLS_COINS_EMOJI} VLScoins"
            
        elif tipo == "dinheiro":
            amount = int(premio)
            winner_profile["money"] = winner_profile.get("money", 0) + amount
            desc_premio = f"**R$ {amount:,}** em dinheiro"
            
        await save_user_profile(winner_id, winner_profile)
        
        embed = message.embeds[0]
        embed.title = "🎉 SORTEIO CONCLUÍDO 🎉"
        if g.get("only_boosters", False):
            embed.title = "⚡ SORTEIO DE APOIADORES CONCLUÍDO ⚡"
        embed.color = discord.Color.gold()
        embed.set_field_at(index=2, name="⏳ Status", value=f"Concluído\n🏆 Vencedor: {winner_mention}", inline=True)
        
        try:
            view = discord.ui.View.from_message(message)
            for child in view.children:
                child.disabled = True
            await message.edit(embed=embed, view=view)
        except Exception as ve:
            print(f"[Giveaway] Erro ao desabilitar botões: {ve}")
            await message.edit(embed=embed)
        
        await channel.send(
            f"🎉 **Parabéns!** {winner_mention} foi o vencedor do sorteio e ganhou {desc_premio}! "
            f"O prêmio já foi adicionado à sua conta!"
        )

    @app_commands.command(name="sorteio_criar", description="Inicia um novo sorteio de jogador, coins ou dinheiro.")
    @app_commands.describe(
        tipo="Tipo de prêmio do sorteio",
        premio="ID do jogador (ex: messi), quantidade de coins (ex: 50) ou valor em dinheiro (ex: 10000)",
        duracao="Tempo de duração do sorteio (ex: 30m, 2h, 1d)",
        apenas_boosters="Se True, somente apoiadores (Server Boosters) podem participar"
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Carta de Jogador", value="carta"),
        app_commands.Choice(name="Coins (VLScoins)", value="coins"),
        app_commands.Choice(name="Dinheiro (R$)", value="dinheiro")
    ])
    async def sorteio_criar(self, interaction: discord.Interaction, tipo: str, premio: str, duracao: str, apenas_boosters: bool = False):
        if interaction.user.id not in ALLOWED_ADMIN_IDS:
            return await interaction.response.send_message("❌ Apenas administradores do bot podem criar sorteios.", ephemeral=True)

        seconds = parse_duration(duracao)
        if not seconds or seconds <= 0:
            return await interaction.response.send_message("❌ Duração inválida. Use formatos como `30m`, `2h`, `1d`.", ephemeral=True)

        # Valida prêmio
        label_premio = ""
        if tipo == "carta":
            p_doc = await db_get(f"player_{premio}")
            if not p_doc:
                return await interaction.response.send_message(f"❌ Jogador `{premio}` não encontrado no catálogo global.", ephemeral=True)
            player = p_doc["data"]
            col_emoji = player.get("col_emoji", "✨")
            label_premio = f"{col_emoji} **{player['name']}** (OVR {player['over']} | {player['pos']})"
        elif tipo == "coins":
            try:
                amount = int(premio)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                return await interaction.response.send_message("❌ Quantidade de coins inválida. Insira um número inteiro positivo.", ephemeral=True)
            label_premio = f"{VLS_COINS_EMOJI} **{amount:,}** VLScoins"
        elif tipo == "dinheiro":
            try:
                amount = int(premio)
                if amount <= 0:
                    raise ValueError
            except ValueError:
                return await interaction.response.send_message("❌ Quantidade de dinheiro inválida. Insira um número inteiro positivo.", ephemeral=True)
            label_premio = f"💵 **R$ {amount:,}**"

        end_time = int(time.time()) + seconds

        embed = discord.Embed(
            title="🎉 SORTEIO ATIVO VLS GURU 🎉",
            description=f"Um novo sorteio foi iniciado no clube!\nClique no botão abaixo para participar.",
            color=discord.Color.purple()
        )
        if apenas_boosters:
            embed.title = "⚡ SORTEIO DE APOIADORES (BOOSTERS) ⚡"
            embed.description = "🔥 **Sorteio exclusivo para Server Boosters!**\nClique no botão abaixo para participar."
            embed.color = discord.Color.magenta()

        embed.add_field(name="🎁 Prêmio", value=label_premio, inline=False)
        embed.add_field(name="👥 Participantes", value="**0** managers", inline=True)
        embed.add_field(name="⏳ Término", value=f"<t:{end_time}:F> (<t:{end_time}:R>)", inline=True)

        view = GiveawayJoinView()
        
        await interaction.response.send_message("✅ Criando sorteio...", ephemeral=True)
        msg = await interaction.channel.send(embed=embed, view=view)

        # Salva o sorteio no banco
        giveaway_data = {
            "message_id": msg.id,
            "channel_id": msg.channel.id,
            "guild_id": msg.guild.id if msg.guild else 0,
            "tipo": tipo,
            "premio": premio,
            "end_time": end_time,
            "only_boosters": apenas_boosters,
            "participants": [],
            "active": True
        }
        await db_upsert(f"giveaway_{msg.id}", giveaway_data)


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))
