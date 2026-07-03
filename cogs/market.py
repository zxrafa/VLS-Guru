# -*- coding: utf-8 -*-
"""
VLS Guru - Cog de Mercado de Transferências
Sistema de compra (catálogo global) e venda (quick sell) de jogadores.
"""
import discord
from discord.ext import commands
from discord import app_commands
import uuid
from datetime import datetime

from database import (
    db_get, db_upsert, db_delete, get_all_players,
    get_user_profile, save_user_profile, lock_user, db_get_prefix
)
from config import VLS_COINS_EMOJI


def calculate_player_price(player: dict, col_multipliers: dict) -> int:
    over = player.get("over", 75)
    base = max(5000, (over - 50) * 15000)
    
    if over <= 79:
        base = base * 0.65
    elif 80 <= over <= 82:
        base = base * 1.15
    elif over >= 83:
        base = base * 1.30
        
    col_id = player.get("col_id")
    col_pct = col_multipliers.get(col_id, 0)
    
    multiplier = 1.0 + (col_pct / 100.0)
    return max(5000, int(base * multiplier))

def calculate_quick_sell(player: dict, col_multipliers: dict) -> int:
    market_price = calculate_player_price(player, col_multipliers)
    return int(market_price * 0.15)


class PlayerSellView(discord.ui.View):
    def __init__(self, owner_id, matches, profile, col_multipliers):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.matches = matches
        self.profile = profile
        self.col_multipliers = col_multipliers
        self.current_index = 0
        self.message = None

    def make_embed(self) -> tuple[discord.Embed, discord.File | None]:
        import os
        player = self.matches[self.current_index]
        preco_quick = calculate_quick_sell(player, self.col_multipliers)
        col_emoji = player.get("col_emoji", "✨")
        col_nome = player.get("col_nome", "Comum")
        
        embed = discord.Embed(
            title="💰 Vender Jogador (CPU Quick Sell)",
            description="Navegue pelas setas e confirme a venda com o botão do meio.",
            color=discord.Color.orange()
        )
        embed.add_field(name="Jogador", value=f"{col_emoji} **{player['name']}**", inline=True)
        embed.add_field(name="Posição / Rated", value=f"⚽ {player.get('pos','?')}  •  ⭐ {player.get('over','?')}", inline=True)
        embed.add_field(name="Coleção", value=col_nome, inline=True)
        embed.add_field(name="Valor de Venda (15%)", value=f"R$ **{preco_quick:,}**", inline=False)
        
        file = None
        if player.get("card"):
            card_path = player["card"]
            if card_path.startswith("http://") or card_path.startswith("https://"):
                embed.set_image(url=card_path)
            elif os.path.exists(card_path):
                file = discord.File(card_path, filename="card.png")
                embed.set_image(url="attachment://card.png")
            else:
                embed.set_image(url=card_path)
            
        return embed, file

    def update_buttons(self):
        self.children[0].disabled = (self.current_index == 0)
        self.children[2].disabled = (self.current_index == len(self.matches) - 1)

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Você não pode interagir aqui.", ephemeral=True)
        
        self.current_index -= 1
        self.update_buttons()
        embed, file = self.make_embed()
        if file:
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)
        else:
            await interaction.response.edit_message(embed=embed, attachments=[], view=self)

    @discord.ui.button(label="Vender", emoji="✅", style=discord.ButtonStyle.success)
    @lock_user()
    async def sell_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Você não pode interagir aqui.", ephemeral=True)
        
        player = self.matches[self.current_index]
        preco_quick = calculate_quick_sell(player, self.col_multipliers)
        
        profile = await get_user_profile(interaction.user)
        inventory = profile.get("inventory", [])
        
        idx = next((i for i, p in enumerate(inventory) if p.get("instance_id") == player.get("instance_id")), None)
        if idx is None:
            return await interaction.response.send_message("❌ Jogador não encontrado no seu inventário.", ephemeral=True)
        
        inventory.pop(idx)
        profile["inventory"] = inventory
        profile["starting_xi"] = [
            p for p in profile.get("starting_xi", [])
            if p.get("instance_id") != player.get("instance_id")
        ]
        
        profile["money"] = profile.get("money", 0) + preco_quick
        await save_user_profile(interaction.user.id, profile)
        
        for child in self.children:
            child.disabled = True
            
        embed = discord.Embed(
            title="💰 Jogador Vendido!",
            description=(
                f"Você vendeu **{player['name']}** para a CPU!\n"
                f"**Valor creditado:** R$ **{preco_quick:,}**"
            ),
            color=discord.Color.green()
        )
        
        file = None
        if player.get("card"):
            card_path = player["card"]
            import os
            if card_path.startswith("http://") or card_path.startswith("https://"):
                embed.set_thumbnail(url=card_path)
            elif os.path.exists(card_path):
                file = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
            else:
                embed.set_thumbnail(url=card_path)
            
        if file:
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)
        else:
            await interaction.response.edit_message(embed=embed, attachments=[], view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Você não pode interagir aqui.", ephemeral=True)
        
        self.current_index += 1
        self.update_buttons()
        embed, file = self.make_embed()
        if file:
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)
        else:
            await interaction.response.edit_message(embed=embed, attachments=[], view=self)


class GlobalBuyView(discord.ui.View):
    def __init__(self, owner_id, matches, profile, col_multipliers):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.matches = matches
        self.profile = profile
        self.col_multipliers = col_multipliers
        self.current_index = 0
        self.message = None

    def make_embed(self) -> tuple[discord.Embed, discord.File | None]:
        import os
        player = self.matches[self.current_index]
        preco = calculate_player_price(player, self.col_multipliers)
        col_emoji = player.get("col_emoji", "✨")
        col_nome = player.get("col_nome", "Comum")
        
        owned = any(
            x.get("id") == player.get("id") and x.get("col_id") == player.get("col_id") 
            for x in self.profile.get("inventory", [])
        )
        
        embed = discord.Embed(
            title="🛒 Contratar Jogador",
            description=f"Deseja contratar este jogador do catálogo?" + ("\n\n⚠️ **Você já possui este jogador no seu elenco.**" if owned else ""),
            color=discord.Color.blue()
        )
        embed.add_field(name="Jogador", value=f"{col_emoji} **{player['name']}**", inline=True)
        embed.add_field(name="Posição / Rated", value=f"⚽ {player.get('pos','?')}  •  ⭐ {player.get('over','?')}", inline=True)
        embed.add_field(name="Coleção", value=col_nome, inline=True)
        embed.add_field(name="Valor de Compra", value=f"💰 **R$ {preco:,}**", inline=False)
        
        file = None
        if player.get("card"):
            card_path = player["card"]
            if card_path.startswith("http://") or card_path.startswith("https://"):
                embed.set_image(url=card_path)
            elif os.path.exists(card_path):
                file = discord.File(card_path, filename="card.png")
                embed.set_image(url="attachment://card.png")
            else:
                embed.set_image(url=card_path)
            
        self.children[0].disabled = (self.current_index == 0)
        self.children[1].label = "Contratar" if not owned else "Já Contratado"
        self.children[1].disabled = owned
        self.children[2].disabled = (self.current_index == len(self.matches) - 1)
        
        return embed, file

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Você não pode interagir aqui.", ephemeral=True)
        self.current_index -= 1
        embed, file = self.make_embed()
        if file:
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)
        else:
            await interaction.response.edit_message(embed=embed, attachments=[], view=self)

    @discord.ui.button(label="Contratar", emoji="✅", style=discord.ButtonStyle.success)
    @lock_user()
    async def buy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Você não pode interagir aqui.", ephemeral=True)
            
        player = self.matches[self.current_index]
        preco = calculate_player_price(player, self.col_multipliers)
        
        profile = await get_user_profile(interaction.user)
        owned = any(
            x.get("id") == player.get("id") and x.get("col_id") == player.get("col_id") 
            for x in profile.get("inventory", [])
        )
        if owned:
            return await interaction.response.send_message("❌ Você já possui este jogador no seu elenco.", ephemeral=True)
            
        if profile.get("money", 0) < preco:
            return await interaction.response.send_message(
                f"❌ Saldo insuficiente. Custa R$ {preco:,} e você tem R$ {profile.get('money',0):,}.",
                ephemeral=True
            )
            
        profile["money"] -= preco
        
        new_instance = player.copy()
        new_instance["instance_id"] = str(uuid.uuid4())[:8]
        new_instance["acquired_at"] = datetime.utcnow().isoformat()
        new_instance.update({
            "goals": 0, "assists": 0, "saves": 0, "matches": 0, "mvps": 0,
            "yellow_cards": 0, "red_cards": 0, "xp": 0
        })
        
        profile.setdefault("inventory", []).append(new_instance)
        await save_user_profile(interaction.user.id, profile)
        
        self.profile = profile
        for child in self.children:
            child.disabled = True
        self.children[1].label = "Contratado ✅"
        
        col_emoji = player.get("col_emoji", "✨")
        embed = discord.Embed(
            title="🛒 Contratação Concluída!",
            description=(
                f"Você contratou {col_emoji} **{player['name']}**!\n"
                f"**Preço:** R$ {preco:,}\n"
                f"O jogador foi adicionado ao seu inventário."
            ),
            color=discord.Color.green()
        )
        
        file = None
        if player.get("card"):
            card_path = player["card"]
            import os
            if card_path.startswith("http://") or card_path.startswith("https://"):
                embed.set_thumbnail(url=card_path)
            elif os.path.exists(card_path):
                file = discord.File(card_path, filename="card.png")
                embed.set_thumbnail(url="attachment://card.png")
            else:
                embed.set_thumbnail(url=card_path)
            
        if file:
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)
        else:
            await interaction.response.edit_message(embed=embed, attachments=[], view=self)

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Você não pode interagir aqui.", ephemeral=True)
        self.current_index += 1
        embed, file = self.make_embed()
        if file:
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)
        else:
            await interaction.response.edit_message(embed=embed, attachments=[], view=self)


class MarketCog(commands.Cog, name="Mercado"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="vender", description="Vende um jogador do seu inventário diretamente para a CPU.")
    @app_commands.describe(jogador="Nome do jogador a vender")
    @lock_user()
    async def vender(self, interaction: discord.Interaction, jogador: str):
        profile = await get_user_profile(interaction.user)
        inventory = profile.get("inventory", [])

        if not inventory:
            return await interaction.response.send_message("❌ Seu elenco está vazio.", ephemeral=True)

        matches = [p for p in inventory if jogador.lower() in p.get("name", "").lower()]
        
        if not matches:
            return await interaction.response.send_message(
                f"❌ Você não possui nenhum jogador contendo `{jogador}` no inventário.",
                ephemeral=True
            )

        matches = sorted(matches, key=lambda x: x.get("over", 0), reverse=True)

        collections = await db_get_prefix("col_")
        col_multipliers = {c["id"]: c.get("preco_adicional_pct", 0) for c in collections}

        view = PlayerSellView(interaction.user.id, matches, profile, col_multipliers)
        embed, file = view.make_embed()
        view.update_buttons()
        if file:
            await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="mercado", description="Lista todos os jogadores disponíveis no catálogo global de transferências.")
    async def mercado(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        players_data = await get_all_players()
        if not players_data:
            return await interaction.followup.send("❌ Nenhum jogador cadastrado no catálogo do banco de dados.", ephemeral=True)
            
        players_data = sorted(players_data, key=lambda x: x.get("over", 0), reverse=True)
        
        collections = await db_get_prefix("col_")
        col_multipliers = {c["id"]: c.get("preco_adicional_pct", 0) for c in collections}
        
        lines = []
        for idx, p in enumerate(players_data, 1):
            col_emoji = p.get("col_emoji", "✨")
            col_nome = p.get("col_nome", "Comum")
            preco = calculate_player_price(p, col_multipliers)
            lines.append(
                f"{idx}. {col_emoji} **{p['name']}** (Rated: `{p['over']}` | {p.get('pos','?')}) — *{col_nome}* | 💰 **R$ {preco:,}**"
            )
            
        chunks = [lines[i:i + 15] for i in range(0, len(lines), 15)]
        total = len(players_data)
        
        embeds = []
        for page_idx, chunk in enumerate(chunks):
            embed = discord.Embed(
                title="🏪 Catálogo de Transferências VLS",
                description="Use `/contratar <nome_do_jogador>` para contratar qualquer um dos jogadores abaixo:\n\n" + "\n".join(chunk),
                color=discord.Color.orange()
            )
            embed.set_footer(text=f"Página {page_idx+1}/{len(chunks)} • Total: {total} jogadores no catálogo")
            embeds.append(embed)
            
        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0])
        else:
            from cogs.team import SimplePaginationView
            await interaction.followup.send(embed=embeds[0], view=SimplePaginationView(embeds))

    @app_commands.command(name="contratar", description="Pesquisa e contrata um jogador do catálogo global.")
    @app_commands.describe(nome="Nome do jogador para buscar no catálogo")
    @lock_user()
    async def contratar(self, interaction: discord.Interaction, nome: str):
        await interaction.response.defer()
        
        players_data = await get_all_players()
        matches = [
            p for p in players_data
            if nome.lower() in p.get("name", "").lower()
        ]
        
        if not matches:
            return await interaction.followup.send(
                f"❌ Nenhum jogador contendo `{nome}` foi encontrado no catálogo global.",
                ephemeral=True
            )
            
        matches = sorted(matches, key=lambda x: x.get("over", 0), reverse=True)
        
        collections = await db_get_prefix("col_")
        col_multipliers = {c["id"]: c.get("preco_adicional_pct", 0) for c in collections}
        
        profile = await get_user_profile(interaction.user)
        view = GlobalBuyView(interaction.user.id, matches, profile, col_multipliers)
        
        embed, file = view.make_embed()
        if file:
            view.message = await interaction.followup.send(embed=embed, file=file, view=view)
        else:
            view.message = await interaction.followup.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(MarketCog(bot))
