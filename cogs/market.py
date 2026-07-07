# -*- coding: utf-8 -*-
"""
VLS Guru - Cog de Mercado de Transferências
Sistema de compra (catálogo global) e venda (quick sell) de jogadores.
"""
import discord
import os
from discord.ext import commands
from discord import app_commands
import uuid
from datetime import datetime
import time
import random

from database import (
    db_get, db_upsert, db_delete, get_all_players,
    get_user_profile, save_user_profile, lock_user, db_get_prefix
)
from config import VLS_COINS_EMOJI


def calculate_player_price(player: dict, col_multipliers: dict) -> int:
    over = player.get("over", 75)
    base = max(5000, (over - 50) * 15000)

    # OVR >= 84 → +85% (carta boa vale mais)
    if over >= 84:
        base = base * 1.85
    # OVR 80-83 → referência
    elif 80 <= over <= 83:
        base = base * 1.15
    # OVR <= 79 → -60% (carta barata)
    else:
        base = base * 0.40

    col_id = player.get("col_id")
    col_pct = col_multipliers.get(col_id, 0)

    multiplier = 1.0 + (col_pct / 100.0)
    return max(5000, int(base * multiplier))

def calculate_quick_sell(player: dict, col_multipliers: dict) -> int:
    market_price = calculate_player_price(player, col_multipliers)
    return int(market_price * 0.05)


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
        embed.add_field(name="Valor de Venda (5%)", value=f"R$ **{preco_quick:,}**", inline=False)
        
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

    @app_commands.command(name="multisell", description="Vende vários jogadores de uma vez para a CPU.")
    @lock_user()
    async def multisell(self, interaction: discord.Interaction):
        profile = await get_user_profile(interaction.user)
        inventory = profile.get("inventory", [])

        if not inventory:
            return await interaction.response.send_message("❌ Seu elenco está vazio.", ephemeral=True)

        collections = await db_get_prefix("col_")
        col_multipliers = {c["id"]: c.get("preco_adicional_pct", 0) for c in collections}

        view = MultiSellView(interaction.user.id, inventory, col_multipliers)
        total_pages = view.total_pages
        await interaction.response.send_message(
            f"🗑️ **Venda em Massa** — Selecione os jogadores que deseja vender.\n"
            f"O valor de cada um é **5%** do preço de mercado.\n"
            f"*(Página 1/{total_pages} • {len(inventory)} jogadores no elenco)*",
            view=view,
            ephemeral=True,
        )

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

    @app_commands.command(name="ofertas", description="Lista 10 jogadores aleatórios com 25% de desconto (atualiza de 12h em 12h).")
    @lock_user()
    async def ofertas(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        offers = await db_get("global_offers")
        now = time.time()
        
        if not offers or (now - offers.get("last_update", 0)) >= 43200:
            all_players = await get_all_players()
            if not all_players:
                return await interaction.followup.send("❌ Nenhum jogador cadastrado no catálogo do banco de dados.", ephemeral=True)
                
            drawn = random.sample(all_players, min(10, len(all_players)))
            collections = await db_get_prefix("col_")
            col_multipliers = {c["id"]: c.get("preco_adicional_pct", 0) for c in collections}
            
            ofertas_lista = []
            for p in drawn:
                preco_original = calculate_player_price(p, col_multipliers)
                preco_desconto = int(preco_original * 0.75)
                
                p_copy = p.copy()
                p_copy["preco_original"] = preco_original
                p_copy["preco_desconto"] = preco_desconto
                ofertas_lista.append(p_copy)
                
            offers = {
                "last_update": now,
                "players": ofertas_lista
            }
            await db_upsert("global_offers", offers)
            
        profile = await get_user_profile(interaction.user)
        timestamp_ciclo = offers["last_update"]
        limite = profile.get("ofertas_compradas", {})
        
        qtd_comprada = 0
        if limite.get("ciclo_timestamp") == timestamp_ciclo:
            qtd_comprada = limite.get("qtd", 0)
            
        restante = 43200 - (now - timestamp_ciclo)
        horas = int(restante // 3600)
        minutos = int((restante % 3600) // 60)
        
        embed = discord.Embed(
            title="🛒 Mercado de Ofertas Especiais VLS",
            description=f"Aproveite as ofertas com **25% de desconto**! O ciclo de ofertas atualiza de 12h em 12h.\n"
                        f"⏳ **Atualização das ofertas em:** {horas}h {minutos}m\n"
                        f"💰 Seu Saldo: **R$ {profile.get('money', 0):,}**\n"
                        f"📊 Limite de compras: **{qtd_comprada}/2** comprados neste ciclo.\n\n"
                        f"**Jogadores Disponíveis nesta rodada:**",
            color=discord.Color.brand_green()
        )
        
        for p in offers["players"]:
            col_emoji = p.get("col_emoji", "✨")
            embed.add_field(
                name=f"{col_emoji} {p['name']} (OVR {p.get('over', '?')} | {p.get('pos','?')})",
                value=f"~~R$ {p['preco_original']:,}~~ por **R$ {p['preco_desconto']:,}**",
                inline=True
            )
            
        view = OfertasView(interaction.user.id, offers["players"])
        await interaction.followup.send(embed=embed, view=view)


# ── Multi-Sell: vender vários jogadores de uma vez ────────────────────────────

class MultiSellSelect(discord.ui.Select):
    """Dropdown multi-select com até 25 jogadores do inventário."""
    def __init__(self, owner_id: int, inventory: list, col_multipliers: dict, page: int = 0):
        self.owner_id = owner_id
        self.col_multipliers = col_multipliers
        self.all_players = sorted(inventory, key=lambda x: x.get("over", 0), reverse=True)
        self.page = page

        start = page * 25
        chunk = self.all_players[start : start + 25]

        options = []
        for p in chunk:
            preco = calculate_quick_sell(p, col_multipliers)
            label = f"{p['name'][:50]} (OVR {p.get('over','?')})"
            desc  = f"Vender por R$ {preco:,}"
            options.append(
                discord.SelectOption(label=label, value=p["instance_id"], description=desc)
            )

        super().__init__(
            placeholder="Selecione os jogadores para vender (pode selecionar vários)...",
            options=options,
            min_values=1,
            max_values=len(options),
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Você não pode interagir aqui.", ephemeral=True)

        await interaction.response.defer()

        selected_ids = set(self.values)
        profile = await get_user_profile(interaction.user)
        inventory = profile.get("inventory", [])

        to_sell = [p for p in inventory if p.get("instance_id") in selected_ids]
        if not to_sell:
            return await interaction.followup.send("❌ Nenhum jogador selecionado foi encontrado no seu inventário.", ephemeral=True)

        total = sum(calculate_quick_sell(p, self.col_multipliers) for p in to_sell)

        # Remove do inventário e do XI
        sold_ids = {p["instance_id"] for p in to_sell}
        profile["inventory"]   = [p for p in inventory if p.get("instance_id") not in sold_ids]
        profile["starting_xi"] = [p for p in profile.get("starting_xi", []) if p.get("instance_id") not in sold_ids]
        profile["money"]       = profile.get("money", 0) + total

        await save_user_profile(interaction.user.id, profile)

        names = "\n".join(f"• {p['name']} (OVR {p.get('over','?')})" for p in to_sell)
        embed = discord.Embed(
            title="💰 Venda em Massa Concluída!",
            description=f"**{len(to_sell)} jogadores** vendidos para a CPU por um total de **R$ {total:,}**!\n\n{names}",
            color=discord.Color.green(),
        )
        embed.set_footer(text=f"Saldo atual: R$ {profile['money']:,}")
        await interaction.followup.send(embed=embed, ephemeral=True)


class MultiSellView(discord.ui.View):
    def __init__(self, owner_id: int, inventory: list, col_multipliers: dict, page: int = 0):
        super().__init__(timeout=120)
        self.owner_id       = owner_id
        self.inventory      = inventory
        self.col_multipliers = col_multipliers
        self.page           = page
        self.total_pages    = max(1, (len(inventory) + 24) // 25)
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        self.add_item(MultiSellSelect(self.owner_id, self.inventory, self.col_multipliers, self.page))
        if self.total_pages > 1:
            prev_btn = discord.ui.Button(label="◀ Anterior", style=discord.ButtonStyle.secondary, disabled=(self.page == 0))
            next_btn = discord.ui.Button(label="Próxima ▶", style=discord.ButtonStyle.secondary, disabled=(self.page >= self.total_pages - 1))

            async def prev_cb(interaction: discord.Interaction, btn=prev_btn):
                if interaction.user.id != self.owner_id:
                    return await interaction.response.send_message("❌", ephemeral=True)
                self.page -= 1
                self._rebuild()
                await interaction.response.edit_message(content=f"Página {self.page+1}/{self.total_pages}", view=self)

            async def next_cb(interaction: discord.Interaction, btn=next_btn):
                if interaction.user.id != self.owner_id:
                    return await interaction.response.send_message("❌", ephemeral=True)
                self.page += 1
                self._rebuild()
                await interaction.response.edit_message(content=f"Página {self.page+1}/{self.total_pages}", view=self)

            prev_btn.callback = prev_cb
            next_btn.callback = next_cb
            self.add_item(prev_btn)
            self.add_item(next_btn)



class OfertasSelect(discord.ui.Select):
    def __init__(self, owner_id: int, players: list):
        self.owner_id = owner_id
        self.players = players
        
        options = []
        for p in players:
            label = f"{p['name'][:50]} (OVR {p.get('over', '?')})"
            orig = p["preco_original"]
            desc = p["preco_desconto"]
            desc_text = f"De: R$ {orig:,} por R$ {desc:,}"
            options.append(
                discord.SelectOption(
                    label=label,
                    value=p["id"],
                    description=desc_text,
                    emoji=p.get("col_emoji", "✨")
                )
            )
        super().__init__(placeholder="🛒 Selecione um jogador para contratar com 25% de desconto...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Esta página de ofertas não é sua.", ephemeral=True)

        await interaction.response.defer()
        
        selected_id = self.values[0]
        offers = await db_get("global_offers")
        if not offers:
            return await interaction.followup.send("❌ Ofertas expiradas. Use `/ofertas` novamente para recarregar.", ephemeral=True)
            
        selected_player = next((p for p in offers["players"] if p.get("id") == selected_id), None)
        if not selected_player:
            return await interaction.followup.send("❌ Jogador não encontrado nas ofertas ativas.", ephemeral=True)
            
        profile = await get_user_profile(interaction.user)
        timestamp_ciclo = offers["last_update"]
        limite = profile.get("ofertas_compradas", {})
        
        if limite.get("ciclo_timestamp") == timestamp_ciclo and limite.get("qtd", 0) >= 2:
            return await interaction.followup.send("❌ Você já comprou o limite máximo de 2 jogadores nesta oferta de 12h!", ephemeral=True)
            
        preco = selected_player["preco_desconto"]
        if profile.get("money", 0) < preco:
            return await interaction.followup.send(
                f"❌ Saldo de dinheiro insuficiente. Custa R$ {preco:,} e você possui R$ {profile.get('money', 0):,}.",
                ephemeral=True
            )
            
        # Desconta e atualiza limites
        profile["money"] -= preco
        limite_data = profile.setdefault("ofertas_compradas", {})
        if limite_data.get("ciclo_timestamp") != timestamp_ciclo:
            limite_data["ciclo_timestamp"] = timestamp_ciclo
            limite_data["qtd"] = 0
        limite_data["qtd"] += 1
        
        # Copia jogador para o inventário
        player_copy = selected_player.copy()
        player_copy["instance_id"] = str(uuid.uuid4())[:8]
        player_copy["xp"] = 0
        player_copy.pop("preco_original", None)
        player_copy.pop("preco_desconto", None)
        
        profile["inventory"].append(player_copy)
        await save_user_profile(interaction.user.id, profile)
        
        await interaction.followup.send(
            f"🎉 **Contratação de Oferta Concluída!**\n"
            f"Você comprou **{player_copy['name']}** com 25% de desconto por **R$ {preco:,}**!\n"
            f"*(Compra {limite_data['qtd']}/2 do ciclo de 12h)*"
        )
        
        restante = 43200 - (time.time() - timestamp_ciclo)
        horas = int(restante // 3600)
        minutos = int((restante % 3600) // 60)
        
        embed = discord.Embed(
            title="🛒 Mercado de Ofertas Especiais VLS",
            description=f"Aproveite as ofertas com **25% de desconto**! O ciclo de ofertas atualiza de 12h em 12h.\n"
                        f"⏳ **Atualização das ofertas em:** {horas}h {minutos}m\n"
                        f"💰 Seu Saldo: **R$ {profile.get('money', 0):,}**\n"
                        f"📊 Limite de compras: **{limite_data['qtd']}/2** comprados neste ciclo.\n\n"
                        f"**Jogadores Disponíveis nesta rodada:**",
            color=discord.Color.brand_green()
        )
        for p in offers["players"]:
            col_emoji = p.get("col_emoji", "✨")
            embed.add_field(
                name=f"{col_emoji} {p['name']} (OVR {p.get('over', '?')} | {p.get('pos','?')})",
                value=f"~~R$ {p['preco_original']:,}~~ por **R$ {p['preco_desconto']:,}**",
                inline=True
            )
            
        await interaction.edit_original_response(embed=embed)


class OfertasView(discord.ui.View):
    def __init__(self, owner_id: int, players: list):
        super().__init__(timeout=120)
        self.add_item(OfertasSelect(owner_id, players))


async def setup(bot):
    await bot.add_cog(MarketCog(bot))
