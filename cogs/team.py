# -*- coding: utf-8 -*-
"""
VLS Guru - Cog de Equipe e Escalação
Gerencia o time do usuário, escalações, táticas, perfis e estatísticas de jogadores.
"""
import discord
from discord.ext import commands
from discord import app_commands
from io import BytesIO
from datetime import datetime

from database import get_user_profile, save_user_profile, get_all_players, lock_user
from config import FORMATIONS_ALL, TACTICS, POSITION_COMPATIBILITY, PLAYSTYLE_EMOJIS, VLS_COINS_EMOJI, SCOUT_LEVEL_MAX, SCOUT_BASE_UPGRADE_COST
from pitch_generator import generate_team_pitch
from simulation import calculate_chemistry_bonus

def format_stars(active_count: int) -> str:
    active = max(1, min(5, int(active_count)))
    inactive = 5 - active
    return ("<:Estrela:1520370719114920016>" * active) + ("<:naoeumaestrelafeliz:1520371319261368411>" * inactive)


def build_time_embed_and_view(profile: dict, formation: str):
    """Cria o embed e view do /time com botões interativos."""
    tactic_key = profile.get("tactic", "padrao")
    tactic_name = TACTICS.get(tactic_key, TACTICS["padrao"])["name"]

    embed = discord.Embed(
        title=f"📋 {profile.get('club_name', 'Sem Clube')}",
        description=f"Formação: **{formation}** | Tática: **{tactic_name}**",
        color=discord.Color.dark_theme()
    )
    embed.set_image(url="attachment://pitch.png")
    embed.set_footer(text="Use os botões abaixo para gerenciar sua escalação.")
    return embed


class TeamCog(commands.Cog, name="Equipe"):
    def __init__(self, bot):
        self.bot = bot

    # Autocomplete para formações
    async def formation_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=f, value=f)
            for f in FORMATIONS_ALL if current.lower() in f.lower()
        ]

    # Autocomplete para táticas
    async def tactic_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        return [
            app_commands.Choice(name=t_data["name"], value=t_key)
            for t_key, t_data in TACTICS.items() if current.lower() in t_data["name"].lower()
        ]

    # Autocomplete para posições
    async def pos_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        try:
            profile = await get_user_profile(interaction.user)
            formation = profile.get("formation", "4-3-3")
            from formations_coordinates import FORMATIONS
            slots = FORMATIONS.get(formation, FORMATIONS["4-3-3"])
            positions = list(slots.keys())
            return [
                app_commands.Choice(name=p, value=p)
                for p in positions if current.lower() in p.lower()
            ][:25]
        except Exception:
            return []

    @app_commands.command(name="time", description="Exibe a prancheta tática visual do seu clube.")
    async def time(self, interaction: discord.Interaction):
        await interaction.response.defer()
        profile = await get_user_profile(interaction.user)

        starting_xi = profile.get("starting_xi", [])
        formation = profile.get("formation", "4-3-3")
        chem_bonuses = calculate_chemistry_bonus(starting_xi, formation)

        # Calcula Overall do Time
        from formations_coordinates import FORMATIONS
        slots = FORMATIONS.get(formation, FORMATIONS["4-3-3"])
        players_by_pos = {p["pos"]: p for p in starting_xi if "pos" in p}
        total_over = sum(players_by_pos[pos].get("over", 0) for pos in slots.keys() if pos in players_by_pos)
        team_ovr = total_over // 11 if total_over > 0 else 0

        try:
            import asyncio
            buffer = await asyncio.to_thread(
                generate_team_pitch,
                starting_xi=starting_xi,
                formation=formation,
                club_name=profile.get("club_name", "FC VLS"),
                money=profile.get("money", 0),
                overall=team_ovr,
                chemistry_bonuses=chem_bonuses
            )
            file = discord.File(fp=buffer, filename="pitch.png")
            embed = build_time_embed_and_view(profile, formation)
            view = TimeView(interaction.user.id, profile)
            await interaction.followup.send(embed=embed, file=file, view=view)
        except Exception as e:
            await interaction.followup.send(f"❌ Ocorreu um erro ao renderizar o campo: {e}")

    @app_commands.command(name="escalar", description="Escala um jogador do seu banco em uma posição específica usando menus interativos.")
    @lock_user()
    async def escalar(self, interaction: discord.Interaction):
        profile = await get_user_profile(interaction.user)
        formation = profile.get("formation", "4-3-3")
        starting_xi = profile.get("starting_xi", [])

        from formations_coordinates import FORMATIONS
        slots = list(FORMATIONS.get(formation, FORMATIONS["4-3-3"]).keys())

        view = EscalarView(interaction.user.id, slots, starting_xi)
        
        embed = discord.Embed(
            title="🎯 Escalar Jogador",
            description=(
                f"Formação Ativa: **{formation}**\n\n"
                "1. Escolha a **posição** no primeiro menu abaixo.\n"
                "2. Escolha o **jogador** compatível no segundo menu."
            ),
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="banco", description="Remove um jogador da escalação titular.")
    async def banco(self, interaction: discord.Interaction):
        """
        /banco agora funciona como /escalar mas para REMOVER jogadores do time.
        Exibe um select com os jogadores escalados e permite retirar um deles.
        """
        profile = await get_user_profile(interaction.user)
        starting_xi = profile.get("starting_xi", [])

        if not starting_xi:
            return await interaction.response.send_message(
                "❌ Não há nenhum jogador escalado no time titular no momento.", ephemeral=True
            )

        view = BancoView(interaction.user.id, starting_xi)
        await interaction.response.send_message(
            "🪑 **Banco de Reservas** — Selecione um jogador abaixo para removê-lo da escalação:",
            view=view
        )

    @app_commands.command(name="tatico", description="Ajusta o comportamento tático ou muda a formação da equipe.")
    @app_commands.describe(formacao="Escolha uma formação de 11 jogadores", tatica="Escolha a filosofia de jogo")
    @app_commands.autocomplete(formacao=formation_autocomplete, tatica=tactic_autocomplete)
    async def tatico(self, interaction: discord.Interaction, formacao: str = None, tatica: str = None):
        profile = await get_user_profile(interaction.user)
        
        if not formacao and not tatica:
            embed = discord.Embed(
                title="⚙️ Painel de Ajustes Táticos",
                description="Use as opções do comando para alterar sua formação ou tática.",
                color=discord.Color.blue()
            )
            embed.add_field(name="Formação Atual", value=f"📋 **{profile.get('formation', '4-3-3')}**", inline=True)
            embed.add_field(name="Tática Ativa", value=f"🛡️ **{TACTICS[profile.get('tactic', 'padrao')]['name']}**", inline=True)
            embed.add_field(name="Efeito", value=TACTICS[profile.get('tactic', 'padrao')]['desc'], inline=False)
            return await interaction.response.send_message(embed=embed)

        updates = []
        if formacao:
            if formacao not in FORMATIONS_ALL:
                return await interaction.response.send_message("❌ Formação inválida.", ephemeral=True)
            profile["formation"] = formacao
            updates.append(f"Formação alterada para **{formacao}**")
            profile["starting_xi"] = []
            updates.append("⚠️ O elenco titular foi reiniciado para alinhar às novas posições.")

        if tatica:
            if tatica not in TACTICS:
                return await interaction.response.send_message("❌ Tática inválida.", ephemeral=True)
            acquired = profile.get("acquired_tactics", ["padrao"])
            if tatica not in acquired:
                return await interaction.response.send_message(
                    f"❌ Você não possui a filosofia tática **{TACTICS[tatica]['name']}**.\n"
                    f"Adquira-a na `/loja` (Aba: *🧠 Filosofias Táticas*).",
                    ephemeral=True
                )
            profile["tactic"] = tatica
            updates.append(f"Estilo tático alterado para **{TACTICS[tatica]['name']}**")

        await save_user_profile(interaction.user.id, profile)
        embed = discord.Embed(
            title="⚙️ Tática Atualizada!",
            description="\n".join([f"✅ {u}" for u in updates]),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="perfil", description="Exibe informações do seu clube, conquistas e badges.")
    @app_commands.describe(usuario="Membro para consultar o perfil (opcional)")
    async def perfil(self, interaction: discord.Interaction, usuario: discord.User = None):
        target = usuario or interaction.user
        profile = await get_user_profile(target)

        wins = profile.get("wins", 0)
        losses = profile.get("losses", 0)
        draws = profile.get("draws", 0)
        total_games = wins + losses + draws
        win_rate = (wins / max(1, total_games)) * 100

        badge_str = f"[{profile['featured_badge'].upper()}] " if profile.get("featured_badge") else ""

        embed = discord.Embed(
            title=f"🏟️ {badge_str}{profile.get('club_name')}",
            description=f"**Estádio:** {profile.get('stadium_name')} (Nível {profile.get('estadio', 1)})",
            color=discord.Color.purple()
        )
        
        embed.add_field(name="💰 Dinheiro", value=f"R$ {profile.get('money', 0):,}", inline=True)
        embed.add_field(name=f"{VLS_COINS_EMOJI} Coins", value=str(profile.get("premium_coins", 0)), inline=True)
        embed.add_field(name="🔎 Olheiro", value=f"Nível {profile.get('scout_level', 0)}/20", inline=True)
        
        tactic_key = profile.get("tactic", "padrao")
        embed.add_field(name="📋 Tática", value=f"{profile.get('formation')} ({TACTICS.get(tactic_key, TACTICS['padrao'])['name']})", inline=True)
        embed.add_field(name="🎴 Inventário", value=f"{len(profile.get('inventory', []))} cartas", inline=True)
        embed.add_field(name="📊 Aproveitamento", value=f"{wins}V | {draws}E | {losses}D ({win_rate:.1f}%)", inline=True)

        achievements = profile.get("achievements", [])
        embed.add_field(name="🏆 Conquistas Desbloqueadas", value=f"**{len(achievements)}** conquistas", inline=False)

        embed.set_thumbnail(url=target.display_avatar.url)
        embed.set_footer(text=f"ID do Usuário: {target.id}")

        # Se for o próprio perfil, oferece botões de atalho com renomear
        if target.id == interaction.user.id:
            view = PerfilView(profile)
            await interaction.response.send_message(embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="estadio", description="Renomeia ou faz upgrade do seu estádio.")
    @app_commands.describe(nome="Novo nome para o estádio (opcional)", upgrade="Fazer upgrade de nível (custa R$ 100.000, opcional)")
    async def estadio(self, interaction: discord.Interaction, nome: str = None, upgrade: bool = False):
        profile = await get_user_profile(interaction.user)
        updates = []

        if nome:
            if len(nome) > 30:
                return await interaction.response.send_message("❌ Nome muito longo.", ephemeral=True)
            antigo = profile.get("stadium_name")
            profile["stadium_name"] = nome
            updates.append(f"Nome alterado de *{antigo}* para **{nome}**")

        if upgrade:
            cost = 100000
            if profile.get("money", 0) < cost:
                return await interaction.response.send_message(f"❌ Saldo insuficiente. O upgrade de estádio custa R$ {cost:,}.", ephemeral=True)
            profile["money"] -= cost
            current_lvl = profile.get("estadio") or 1
            profile["estadio"] = current_lvl + 1
            updates.append(f"Estádio upado para o **Nível {current_lvl + 1}**")

        if not updates:
            embed = discord.Embed(
                title=f"🏟️ {profile.get('stadium_name')}",
                description="Informações oficiais do estádio do seu clube.",
                color=discord.Color.dark_magenta()
            )
            embed.add_field(name="Nível do Estádio", value=f"⭐ **Nível {profile.get('estadio', 1)}**", inline=True)
            embed.add_field(name="Proprietário", value=interaction.user.mention, inline=True)
            return await interaction.response.send_message(embed=embed)

        await save_user_profile(interaction.user.id, profile)
        embed = discord.Embed(
            title="🏟️ Estádio Atualizado com Sucesso!",
            description="\n".join([f"✅ {u}" for u in updates]),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="elenco", description="Lista o elenco titular em formato de texto organizado.")
    async def elenco(self, interaction: discord.Interaction):
        profile = await get_user_profile(interaction.user)
        starting_xi = profile.get("starting_xi", [])
        
        if not starting_xi:
            return await interaction.response.send_message("❌ Seu clube não possui nenhum jogador escalado. Use `/escalar`.", ephemeral=True)

        # Organiza por setor
        gk_lines, def_lines, mid_lines, att_lines = [], [], [], []
        for p in starting_xi:
            pos = p.get("pos", "?")
            ps_emoji = " ".join([PLAYSTYLE_EMOJIS.get(ps, "") for ps in p.get("playstyles", []) if ps in PLAYSTYLE_EMOJIS])
            line = f"• **{pos}**: {p.get('col_emoji','✨')} {p['name']} _(Rated {p['over']})_ {ps_emoji}"
            if pos == "GK":
                gk_lines.append(line)
            elif pos in ("CB", "LB", "RB", "LWB", "RWB"):
                def_lines.append(line)
            elif pos in ("CM", "CAM", "CDM", "LM", "RM"):
                mid_lines.append(line)
            else:
                att_lines.append(line)

        embed = discord.Embed(
            title=f"📋 Elenco Titular — {profile.get('club_name')}",
            description=f"Formação: **{profile.get('formation', '4-3-3')}**",
            color=discord.Color.blurple()
        )
        if gk_lines:
            embed.add_field(name="🧤 Goleiro", value="\n".join(gk_lines), inline=False)
        if def_lines:
            embed.add_field(name="🛡️ Defesa", value="\n".join(def_lines), inline=False)
        if mid_lines:
            embed.add_field(name="⚙️ Meio-Campo", value="\n".join(mid_lines), inline=False)
        if att_lines:
            embed.add_field(name="🔥 Ataque", value="\n".join(att_lines), inline=False)

        embed.set_footer(text=f"Total de titulares: {len(starting_xi)}/11")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="titular", description="Lista detalhada dos titulares e seus atributos efetivos.")
    async def titular(self, interaction: discord.Interaction):
        profile = await get_user_profile(interaction.user)
        starting_xi = profile.get("starting_xi", [])
        formation = profile.get("formation", "4-3-3")

        if not starting_xi:
            return await interaction.response.send_message("❌ Nenhum jogador escalado no time titular.", ephemeral=True)

        chem_bonuses = calculate_chemistry_bonus(starting_xi, formation)

        embed = discord.Embed(
            title=f"📋 Titulares Detalhado — {profile.get('club_name')}",
            description=f"Formação: **{formation}** | Mostrando Química (+)",
            color=discord.Color.teal()
        )

        gk_lines, def_lines, mid_lines, att_lines = [], [], [], []
        for p in starting_xi:
            chem = chem_bonuses.get(p["instance_id"], 0)
            chem_indicator = f" (+{chem})" if chem > 0 else ""
            ps_str = ", ".join([pstyle.capitalize() for pstyle in p.get("playstyles", [])]) or "Nenhum"
            
            wf_val = p.get('weak_foot', 1)
            sm_val = p.get('skill_moves', 1)
            
            if p.get("pos") == "GK":
                line = (
                    f"🧤 **{p.get('pos')}**: {p.get('col_emoji','✨')} **{p['name']}** `OVR {p['over']}{chem_indicator}`\n"
                    f"↳ `DIV: {p.get('div',75)}` | `HAN: {p.get('han',75)}` | `KIC: {p.get('kic',75)}` | `REF: {p.get('ref',75)}` | `SPD: {p.get('spd',75)}` | `POS: {p.get('pos_stat',75)}`\n"
                    f"↳ <:perna:1520392085360873482> {wf_val}★ | <:Fintas:1520392750548123701> {sm_val}★ | PlayStyles: *{ps_str}*"
                )
                gk_lines.append(line)
            else:
                line = (
                    f"⚽ **{p.get('pos')}**: {p.get('col_emoji','✨')} **{p['name']}** `OVR {p['over']}{chem_indicator}`\n"
                    f"↳ `PAC: {p.get('pac',75)}` | `SHO: {p.get('sho',75)}` | `PAS: {p.get('pas',75)}` | `DRI: {p.get('dri',75)}` | `DEF: {p.get('def',75)}` | `PHY: {p.get('phy',75)}`\n"
                    f"↳ <:perna:1520392085360873482> {wf_val}★ | <:Fintas:1520392750548123701> {sm_val}★ | PlayStyles: *{ps_str}*"
                )
                pos = p.get("pos", "?")
                if pos in ("CB", "LB", "RB", "LWB", "RWB"):
                    def_lines.append(line)
                elif pos in ("CM", "CAM", "CDM", "LM", "RM"):
                    mid_lines.append(line)
                else:
                    att_lines.append(line)

        if gk_lines:
            embed.add_field(name="🧤 Goleiro", value="\n\n".join(gk_lines), inline=False)
        if def_lines:
            embed.add_field(name="🛡️ Defesa", value="\n\n".join(def_lines), inline=False)
        if mid_lines:
            embed.add_field(name="⚙️ Meio-Campo", value="\n\n".join(mid_lines), inline=False)
        if att_lines:
            embed.add_field(name="🔥 Ataque", value="\n\n".join(att_lines), inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="inventario", description="Lista todos os jogadores do seu elenco completo.")
    @app_commands.describe(filtro="Filtrar por posição (ex: ST, CB, GK) ou coleção")
    async def inventario(self, interaction: discord.Interaction, filtro: str = None):
        await interaction.response.defer()
        profile = await get_user_profile(interaction.user)
        inventory = profile.get("inventory", [])

        if not inventory:
            return await interaction.followup.send("❌ Seu elenco está vazio. Use `/recrutar` para contratar jogadores.", ephemeral=True)

        # Filtro opcional
        if filtro:
            filtro_upper = filtro.upper()
            inventory = [p for p in inventory if p.get("pos", "").upper() == filtro_upper or filtro.lower() in p.get("col_nome", "").lower()]

        # Ordena por OVR decrescente
        inventory = sorted(inventory, key=lambda x: x.get("over", 0), reverse=True)

        # Paginação de 15 por página
        starting_ids = {p["instance_id"] for p in profile.get("starting_xi", []) if "instance_id" in p}

        lines = []
        for p in inventory:
            escalado = "🟢" if p.get("instance_id") in starting_ids else "⚪"
            lines.append(
                f"{escalado} **{p.get('over', '?')}** | {p.get('col_emoji','✨')} **{p['name']}** "
                f"({p.get('pos','?')}) — *{p.get('col_nome','Comum')}* | `{p.get('instance_id','')[:8]}`"
            )

        chunks = [lines[i:i + 15] for i in range(0, len(lines), 15)]
        total = len(inventory)

        embeds = []
        for idx, chunk in enumerate(chunks):
            embed = discord.Embed(
                title=f"🎴 Elenco Completo — {profile.get('club_name', 'Seu Clube')}",
                description="\n".join(chunk),
                color=discord.Color.blurple()
            )
            embed.set_footer(text=f"Página {idx+1}/{len(chunks)} • Total: {total} cartas • 🟢 = Escalado | ⚪ = Reserva")
            embeds.append(embed)

        if len(embeds) == 1:
            await interaction.followup.send(embed=embeds[0])
        else:
            await interaction.followup.send(embed=embeds[0], view=SimplePaginationView(embeds))

    @app_commands.command(name="show", description="Exibe a ficha de atributos e estatísticas de um jogador específico.")
    @app_commands.describe(nome="Nome do jogador para buscar no elenco (se omitido, mostra a estrela do time)")
    async def show(self, interaction: discord.Interaction, nome: str = None):
        await interaction.response.defer()
        profile = await get_user_profile(interaction.user)
        inventory = profile.get("inventory", [])

        if not inventory:
            return await interaction.followup.send("❌ Seu elenco está vazio.")

        target_player = None
        if not nome:
            candidates = profile.get("starting_xi", []) or inventory
            target_player = max(candidates, key=lambda x: x.get("over", 0))
        else:
            matches = [p for p in inventory if nome.lower() in p.get("name", "").lower()]
            if not matches:
                return await interaction.followup.send(f"❌ Nenhum jogador contendo `{nome}` foi encontrado no seu elenco.")
            elif len(matches) > 1:
                view = SelectShowPlayerView(interaction.user.id, matches)
                return await interaction.followup.send("🔍 Múltiplos jogadores encontrados. Selecione o desejado abaixo:", view=view)
            else:
                target_player = matches[0]

        view = PlayerShowView(interaction.user.id, target_player, self)
        embed = view.make_embed()
        
        # Exibe imagem da carta se disponível
        card_path = target_player.get("card", "")
        if card_path:
            if card_path.startswith("http://") or card_path.startswith("https://"):
                try:
                    import asyncio
                    from pitch_generator import load_card_image
                    import hashlib
                    import os
                    # Garante que a imagem seja baixada/cacheadas no disco
                    await asyncio.to_thread(load_card_image, card_path)
                    url_hash = hashlib.md5(card_path.encode("utf-8")).hexdigest()
                    local_cache_path = os.path.join("cache_cartas", f"{url_hash}.png")
                    
                    if os.path.exists(local_cache_path):
                        file = discord.File(local_cache_path, filename="card.png")
                        return await interaction.followup.send(embed=embed, file=file, view=view)
                except Exception as e:
                    print(f"Erro ao obter imagem no show: {e}")
            elif __import__('os').path.exists(card_path):
                file = discord.File(card_path, filename="card.png")
                return await interaction.followup.send(embed=embed, file=file, view=view)
                
        await interaction.followup.send(embed=embed, view=view)

    def generate_player_show_embed(self, player: dict) -> discord.Embed:
        """Gera o embed reformulado da ficha de um jogador."""
        wf = player.get("weak_foot", 1)
        sm = player.get("skill_moves", 1)
        xp = player.get("xp", 0)
        affinity_level = xp // 10
        affinity_bonus = min(5.0, affinity_level * 0.5)

        acq_date = "Indisponível"
        if player.get("acquired_at"):
            try:
                dt = datetime.fromisoformat(player["acquired_at"])
                acq_date = dt.strftime("%d/%m/%Y")
            except Exception:
                pass

        matches = player.get("matches", 0)
        goals = player.get("goals", 0)
        assists = player.get("assists", 0)
        saves = player.get("saves", 0)
        mvps = player.get("mvps", 0)
        yellow = player.get("yellow_cards", 0)
        red = player.get("red_cards", 0)
        total_xg = player.get("xg", 0.0)
        xg_per_game = total_xg / max(1, matches)

        ps_list = player.get("playstyles", [])

        col_emoji = player.get("col_emoji", "✨")
        col_nome = player.get("col_nome", "Comum")
        over = player.get("over", "?")
        pos = player.get("pos", "?")
        original_pos = player.get("original_pos", pos)

        # Determina cor do embed por coleção
        col_id = player.get("col_id", "base")
        color_map = {
            "base": discord.Color.from_str("#a0a0a0"),
            "comum": discord.Color.from_str("#4287f5"),
            "premiados": discord.Color.from_str("#9b59b6"),
            "copa_do_mundo": discord.Color.from_str("#f1c40f"),
        }
        embed_color = color_map.get(col_id, discord.Color.gold())

        embed = discord.Embed(
            title=f"{col_emoji} {player.get('name')}",
            description=(
                f"**Coleção:** {col_nome}  •  **Rated:** `{over}`  •  **Posição:** `{pos}`\n"
                f"🏢 {player.get('club','—')}  •  🏳️ {player.get('nationality','—')}  •  📅 Contratado: {acq_date}"
            ),
            color=embed_color
        )

        # Bloco de Atributos
        is_gk = player.get("pos") == "GK"
        if is_gk:
            div = player.get("div", 75)
            han = player.get("han", 75)
            kic = player.get("kic", 75)
            ref = player.get("ref", 75)
            spd = player.get("spd", 75)
            pos_gk = player.get("pos_stat", 75)
            
            val_str = (
                f"```\n"
                f"🧤 DIV: {div:<3}  |  🎯 HAN: {han:<3}  |  👟 KIC: {kic:<3}\n"
                f"⚡ REF: {ref:<3}  |  🏃 SPD: {spd:<3}  |  🛡️ POS: {pos_gk:<3}\n"
                f"```"
            )
            embed.add_field(name="📊 Atributos de Goleiro", value=val_str, inline=False)
        else:
            pac = player.get("pac", 75)
            sho = player.get("sho", 75)
            pas = player.get("pas", 75)
            dri = player.get("dri", 75)
            def_val = player.get("def", 75)
            phy = player.get("phy", 75)
            
            val_str = (
                f"```\n"
                f"🏃 PAC: {pac:<3}  |  🎯 PAS: {pas:<3}  |  ⚡ DRI: {dri:<3}\n"
                f"👟 SHO: {sho:<3}  |  🛡️ DEF: {def_val:<3}  |  💪 PHY: {phy:<3}\n"
                f"```"
            )
            embed.add_field(name="📊 Atributos de Linha", value=val_str, inline=False)

        # Habilidades & Afinidade
        embed.add_field(
            name="✨ Habilidades & Afinidade",
            value=(
                f"<:perna:1520392085360873482> **Perna Ruim:** {format_stars(wf)}\n"
                f"<:Fintas:1520392750548123701> **Fintas:** {format_stars(sm)}\n"
                f"🤝 **Afinidade:** Nível **{affinity_level}** ({xp % 10}/10 XP)  •  **+{affinity_bonus:.1f}%** de bônus"
            ),
            inline=False
        )

        # Ficha Técnica
        preferred_foot = player.get("preferred_foot")
        height = player.get("height")
        weight = player.get("weight")
        league = player.get("league")
        
        info_parts = []
        if preferred_foot:
            info_parts.append(f"🦶 Pé: **{preferred_foot}**")
        if height:
            info_parts.append(f"📏 Altura: **{height}cm**")
        if weight:
            info_parts.append(f"⚖️ Peso: **{weight}kg**")
        if league:
            info_parts.append(f"🏆 Liga: **{league}**")
            
        if info_parts:
            embed.add_field(
                name="📋 Informações do Atleta",
                value="  •  ".join(info_parts),
                inline=False
            )

        # PlayStyles
        if ps_list:
            ps_str = "  ".join([f"{PLAYSTYLE_EMOJIS.get(ps, '✨')} {ps.capitalize()}" for ps in ps_list])
        else:
            ps_str = "*Nenhum PlayStyle ativo*"
        embed.add_field(name="🎭 PlayStyles", value=ps_str, inline=False)

        # Estatísticas
        embed.add_field(
            name="📈 Desempenho em Campo",
            value=(
                f"👕 Partidas: **{matches}**  •  ⚽ Gols: **{goals}**  •  🎯 Assists: **{assists}**\n"
                f"🧤 Defesas: **{saves}**  •  👑 MVP: **{mvps}**  •  🟨 Cartões: **{yellow}🟨 {red}🟥**"
            ),
            inline=False
        )

        embed.set_footer(text=f"Instância: {player.get('instance_id','?')}  •  Posição Original: {original_pos}")
        return embed


# ─── Views do /time ───────────────────────────────────────────────────────────

class TimeView(discord.ui.View):
    """View com botões interativos para o /time."""
    def __init__(self, owner_id: int, profile: dict):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.profile = profile
        self.confirming_clear = False

    @discord.ui.button(label="⚡ Auto Escalar", style=discord.ButtonStyle.success, row=0)
    async def auto_escalar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Apenas o dono pode usar estes botões.", ephemeral=True)

        await interaction.response.defer()
        profile = await get_user_profile(interaction.user)
        formation = profile.get("formation", "4-3-3")

        from formations_coordinates import FORMATIONS
        slots = list(FORMATIONS.get(formation, FORMATIONS["4-3-3"]).keys())
        inventory = profile.get("inventory", [])

        if not inventory:
            return await interaction.followup.send("❌ Você não tem jogadores no elenco.", ephemeral=True)

        # ── Grupos posicionais para fallback controlado ──────────────────────
        _POS_GROUPS = {
            "GK":  ["GK"],
            "DEF": ["CB", "LB", "RB", "LWB", "RWB"],
            "MID": ["CDM", "CM", "CAM", "LM", "RM", "LW", "RW"],
            "ATK": ["ST", "CF"],
        }

        def _get_group(pos: str) -> str:
            pu = (pos or "").upper()
            for grp, members in _POS_GROUPS.items():
                if pu in members:
                    return grp
            return "MID"

        def _player_pos(p: dict) -> str:
            return (p.get("original_pos") or p.get("pos") or "").upper()

        def _base(slot: str) -> str:
            return ''.join(c for c in slot if not c.isdigit())

        used_ids = set()
        new_xi = []

        for slot_pos in slots:
            base = _base(slot_pos)
            base_up = base.upper()
            slot_group = _get_group(base_up)

            # Camada 1 — posição exata
            candidates = [
                p for p in inventory
                if _player_pos(p) == base_up
                and p.get("instance_id") not in used_ids
            ]

            # Camada 2 — posições compatíveis (POSITION_COMPATIBILITY)
            if not candidates:
                compat = [t.upper() for t in POSITION_COMPATIBILITY.get(base, [base])]
                candidates = [
                    p for p in inventory
                    if _player_pos(p) in compat
                    and p.get("instance_id") not in used_ids
                ]

            # Camada 3 — mesmo grupo posicional (DEF / MID / ATK / GK)
            if not candidates:
                candidates = [
                    p for p in inventory
                    if _get_group(_player_pos(p)) == slot_group
                    and p.get("instance_id") not in used_ids
                ]

            # Camada 4 — qualquer jogador de campo (NUNCA escala GK fora do gol nem mistura grupos)
            if not candidates:
                if slot_group == "GK":
                    # Slot de GK sem GK disponível → deixa vazio
                    candidates = []
                else:
                    # Qualquer jogador que não seja GK
                    candidates = [
                        p for p in inventory
                        if _player_pos(p) != "GK"
                        and p.get("instance_id") not in used_ids
                    ]

            if candidates:
                best = max(candidates, key=lambda x: x.get("over", 0))
                player_copy = best.copy()
                player_copy["pos"] = slot_pos
                new_xi.append(player_copy)
                used_ids.add(best["instance_id"])

        profile["starting_xi"] = new_xi
        await save_user_profile(interaction.user.id, profile)

        # Recalcula e re-renderiza
        chem_bonuses = calculate_chemistry_bonus(new_xi, formation)
        players_by_pos = {p["pos"]: p for p in new_xi if "pos" in p}
        from formations_coordinates import FORMATIONS as F2
        _slots = F2.get(formation, F2["4-3-3"])
        total_over = sum(players_by_pos[pos].get("over", 0) for pos in _slots.keys() if pos in players_by_pos)
        team_ovr = total_over // 11 if total_over > 0 else 0

        import asyncio
        from pitch_generator import generate_team_pitch
        buffer = await asyncio.to_thread(
            generate_team_pitch,
            starting_xi=new_xi,
            formation=formation,
            club_name=profile.get("club_name", "FC VLS"),
            money=profile.get("money", 0),
            overall=team_ovr,
            chemistry_bonuses=chem_bonuses
        )
        file = discord.File(fp=buffer, filename="pitch.png")
        embed = build_time_embed_and_view(profile, formation)
        await interaction.followup.send(f"⚡ **Auto Escalação aplicada!** {len(new_xi)}/11 posições preenchidas.", embed=embed, file=file)

    @discord.ui.button(label="📋 Formação", style=discord.ButtonStyle.primary, row=0)
    async def mudar_formacao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Apenas o dono pode usar estes botões.", ephemeral=True)
        view = FormacaoSelectView(self.owner_id)
        await interaction.response.send_message("Selecione a nova formação:", view=view, ephemeral=True)

    @discord.ui.button(label="🗑️ Limpar Escalação", style=discord.ButtonStyle.danger, row=0)
    async def limpar_escalacao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Apenas o dono pode usar estes botões.", ephemeral=True)

        if not self.confirming_clear:
            self.confirming_clear = True
            button.label = "⚠️ Confirmar Limpeza"
            button.style = discord.ButtonStyle.danger
            await interaction.response.edit_message(
                content="⚠️ **Você tem certeza?** Clique em 'Confirmar Limpeza' novamente para remover todos os jogadores do time titular.",
                view=self
            )
        else:
            self.confirming_clear = False
            profile = await get_user_profile(interaction.user)
            profile["starting_xi"] = []
            await save_user_profile(interaction.user.id, profile)
            button.label = "🗑️ Limpar Escalação"
            button.style = discord.ButtonStyle.danger
            await interaction.response.edit_message(
                content="✅ **Escalação limpa!** Todos os jogadores foram movidos para o banco de reservas.",
                view=self
            )


class FormacaoSelectView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=60)
        self.owner_id = owner_id
        options = [discord.SelectOption(label=f, value=f) for f in FORMATIONS_ALL]
        self.add_item(FormacaoDropdown(owner_id, options))


class FormacaoDropdown(discord.ui.Select):
    def __init__(self, owner_id: int, options):
        self.owner_id = owner_id
        super().__init__(placeholder="Escolha uma formação", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        chosen = self.values[0]
        profile = await get_user_profile(interaction.user)
        profile["formation"] = chosen
        profile["starting_xi"] = []
        await save_user_profile(interaction.user.id, profile)
        await interaction.response.send_message(
            f"✅ Formação alterada para **{chosen}**! A escalação foi reiniciada. Use `/escalar` para montar o time.",
            ephemeral=True
        )


# ─── Views do /escalar ────────────────────────────────────────────────────────

class PositionSelect(discord.ui.Select):
    def __init__(self, owner_id: int, formation_positions: list, starting_xi: list):
        self.owner_id = owner_id
        options = []
        for pos in formation_positions:
            player_in_pos = next((p for p in starting_xi if p.get("pos") == pos), None)
            if player_in_pos:
                label = f"{pos} — {player_in_pos['name']} (OVR {player_in_pos.get('over', '?')})"
                description = f"Substituir {player_in_pos['name']}"
            else:
                label = f"{pos} — [Vazio]"
                description = "Nenhum jogador escalado"
            options.append(
                discord.SelectOption(
                    label=label,
                    value=pos,
                    description=description
                )
            )
        super().__init__(placeholder="Selecione a posição para escalar", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Apenas o dono deste comando pode interagir com o menu.", ephemeral=True)

        try:
            chosen_pos = self.values[0]
            base_pos = ''.join([c for c in chosen_pos if not c.isdigit()])
            profile = await get_user_profile(interaction.user)
            eligible_tags = POSITION_COMPATIBILITY.get(base_pos, [base_pos])
            
            eligible_players = [
                p for p in profile.get("inventory", [])
                if p.get("original_pos", p.get("pos")).upper() in [t.upper() for t in eligible_tags]
            ][:25]

            if not eligible_players:
                return await interaction.response.send_message(
                    f"❌ Você não possui jogadores compatíveis com a posição **{chosen_pos}** (Requer: {', '.join(eligible_tags)}).",
                    ephemeral=True
                )

            view: EscalarView = self.view
            view.set_player_select(chosen_pos, eligible_players)
            await interaction.response.edit_message(view=view)
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Erro ao selecionar posição: {e}", ephemeral=True)
            except Exception:
                pass


class PlayerSelect(discord.ui.Select):
    def __init__(self, owner_id: int, target_pos: str, players: list):
        self.owner_id = owner_id
        self.target_pos = target_pos
        options = [
            discord.SelectOption(
                label=f"{p['name']} — Rated {p['over']} ({p.get('original_pos', p['pos'])})",
                value=p["instance_id"],
                description=f"ID: {p['instance_id'][:8]}..."
            )
            for p in players
        ]
        super().__init__(placeholder=f"Selecione o jogador para {target_pos}", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Permissão negada.", ephemeral=True)

        try:
            profile = await get_user_profile(interaction.user)
            
            chosen = next(
                (p for p in profile.get("inventory", []) if p.get("instance_id") == self.values[0]), None
            )
            if not chosen:
                return await interaction.response.send_message("❌ Jogador não localizado no inventário.", ephemeral=True)

            # Remove do slot atual e do slot alvo
            xi = [p for p in profile.get("starting_xi", []) if p.get("instance_id") != chosen["instance_id"]]
            xi = [p for p in xi if p.get("pos") != self.target_pos]

            chosen_copy = chosen.copy()
            chosen_copy["pos"] = self.target_pos
            xi.append(chosen_copy)
            
            profile["starting_xi"] = xi
            await save_user_profile(interaction.user.id, profile)

            view: EscalarView = self.view
            for child in view.children:
                child.disabled = True

            embed = discord.Embed(
                title="✅ Jogador Escalado!",
                description=f"**{chosen['name']}** foi escalado com sucesso na posição **{self.target_pos}**!",
                color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Erro ao escalar jogador: {e}", ephemeral=True)
            except Exception:
                pass


class EscalarView(discord.ui.View):
    def __init__(self, owner_id: int, formation_positions: list, starting_xi: list):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.add_item(PositionSelect(owner_id, formation_positions, starting_xi))

    def set_player_select(self, target_pos: str, players: list):
        for child in list(self.children):
            if isinstance(child, PlayerSelect):
                self.remove_item(child)
        self.add_item(PlayerSelect(self.owner_id, target_pos, players))


# ─── Views do /banco ──────────────────────────────────────────────────────────

class BancoSelect(discord.ui.Select):
    def __init__(self, owner_id: int, starting_xi: list):
        self.owner_id = owner_id
        options = [
            discord.SelectOption(
                label=f"{p.get('pos','?')} — {p['name']} (Rated {p.get('over','?')})",
                value=p["instance_id"],
                description=f"Coleção: {p.get('col_nome','?')} | ID: {p['instance_id'][:8]}"
            )
            for p in starting_xi if "instance_id" in p
        ]
        super().__init__(placeholder="Selecione o jogador para retirar da escalação", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Permissão negada.", ephemeral=True)

        try:
            chosen_id = self.values[0]
            profile = await get_user_profile(interaction.user)

            player_name = None
            new_xi = []
            for p in profile.get("starting_xi", []):
                if p.get("instance_id") == chosen_id:
                    player_name = p.get("name", "Jogador")
                else:
                    new_xi.append(p)

            if player_name is None:
                return await interaction.response.send_message("❌ Jogador não encontrado na escalação atual.", ephemeral=True)

            profile["starting_xi"] = new_xi
            await save_user_profile(interaction.user.id, profile)
            await interaction.response.send_message(
                f"✅ **{player_name}** foi removido da escalação titular e voltou para o banco de reservas.",
                ephemeral=True
            )
        except Exception as e:
            try:
                await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)
            except Exception:
                pass


class BancoView(discord.ui.View):
    def __init__(self, owner_id: int, starting_xi: list):
        super().__init__(timeout=120)
        self.add_item(BancoSelect(owner_id, starting_xi))


# ─── Views do /perfil ─────────────────────────────────────────────────────────

class RenomearModal(discord.ui.Modal, title="Renomear Clube"):
    novo_nome = discord.ui.TextInput(
        label="Novo Nome do Clube",
        placeholder="Ex: FC Atlético VLS",
        min_length=2,
        max_length=30
    )

    async def on_submit(self, interaction: discord.Interaction):
        nome = str(self.novo_nome).strip()
        profile = await get_user_profile(interaction.user)
        antigo = profile.get("club_name", "")
        profile["club_name"] = nome
        await save_user_profile(interaction.user.id, profile)
        await interaction.response.send_message(
            f"⚽ **Clube Renomeado!** De *{antigo}* para **{nome}**.",
            ephemeral=True
        )


class PerfilView(discord.ui.View):
    def __init__(self, profile):
        super().__init__(timeout=60)
        self.profile = profile

    @discord.ui.button(label="✏️ Renomear Clube", style=discord.ButtonStyle.secondary, emoji="✏️", row=0)
    async def renomear_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenomearModal())

    @discord.ui.button(label="Upar Olheiro", style=discord.ButtonStyle.primary, emoji="🔎", row=0)
    async def upar_olheiro_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        profile = await get_user_profile(interaction.user)
        scout_level = profile.get("scout_level", 0)
        
        if scout_level >= SCOUT_LEVEL_MAX:
            return await interaction.response.send_message("❌ Seu olheiro já está no nível máximo (20).", ephemeral=True)

        cost = max(25000, scout_level * SCOUT_BASE_UPGRADE_COST)

        if profile.get("money", 0) < cost:
            return await interaction.response.send_message(f"❌ Saldo insuficiente. Upar o olheiro para o nível {scout_level + 1} custa R$ {cost:,}.", ephemeral=True)

        profile["money"] -= cost
        profile["scout_level"] += 1
        await save_user_profile(interaction.user.id, profile)

        await interaction.response.send_message(
            f"🔎 **Upgrade Realizado!** Seu olheiro subiu para o **Nível {scout_level + 1}**.\n"
            f"💸 Custo: R$ {cost:,} (Sorte de cartas raras no /recrutar aumentada!)",
            ephemeral=True
        )
        self.stop()

    @discord.ui.button(label="Conquistas & Badges", style=discord.ButtonStyle.secondary, emoji="🏆", row=1)
    async def ver_badges_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        profile = await get_user_profile(interaction.user)
        badges = profile.get("acquired_badges", [])
        
        if not badges:
            return await interaction.response.send_message("🏆 Você não possui nenhuma badge conquistada ainda.", ephemeral=True)

        view = BadgesSelectView(interaction.user.id, badges, profile.get("featured_badge"))
        await interaction.response.send_message(
            "🏆 **Badges Conquistadas**\nSelecione uma badge abaixo para colocá-la em destaque no seu perfil:",
            view=view,
            ephemeral=True
        )


class BadgesSelectView(discord.ui.View):
    def __init__(self, owner_id, badges, current_featured):
        super().__init__(timeout=60)
        self.owner_id = owner_id
        options = [
            discord.SelectOption(
                label=badge.upper(),
                value=badge,
                default=(badge == current_featured)
            ) for badge in badges
        ]
        self.add_item(BadgeSelectDropdown(owner_id, options))


class BadgeSelectDropdown(discord.ui.Select):
    def __init__(self, owner_id, options):
        self.owner_id = owner_id
        super().__init__(placeholder="Escolha a badge em destaque", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
            
        profile = await get_user_profile(interaction.user)
        chosen = self.values[0]
        profile["featured_badge"] = chosen
        await save_user_profile(interaction.user.id, profile)

        await interaction.response.send_message(f"🏆 Badge **[{chosen.upper()}]** definida em destaque no seu perfil!", ephemeral=True)


# ─── Paginação ────────────────────────────────────────────────────────────────

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
        else:
            await interaction.response.defer()

    @discord.ui.button(label="Próximo ▶️", style=discord.ButtonStyle.blurple)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page])
        else:
            await interaction.response.defer()


# ─── Show com seleção múltipla ────────────────────────────────────────────────

class CategorySelect(discord.ui.Select):
    def __init__(self, owner_id: int):
        self.owner_id = owner_id
        options = [
            discord.SelectOption(label="Atributos", value="atributos", emoji="📊", description="Ver atributos técnicos e estrelas"),
            discord.SelectOption(label="Estatísticas", value="stats", emoji="📈", description="Ver partidas, gols, assistências, cartões e xG"),
            discord.SelectOption(label="Ficha Técnica", value="bio", emoji="📋", description="Ver clube, nacionalidade, liga, pé e dimensões"),
            discord.SelectOption(label="PlayStyles & Afinidade", value="playstyles", emoji="🎭", description="Ver habilidades especiais e progresso de afinidade")
        ]
        super().__init__(placeholder="Selecione a categoria para visualizar...", options=options)

    async def callback(self, interaction: discord.Interaction):
        view: PlayerShowView = self.view
        await view.handle_tab(interaction, self.values[0])


class PlayerShowView(discord.ui.View):
    def __init__(self, owner_id: int, player: dict, cog):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.player = player
        self.cog = cog
        self.current_tab = "atributos"
        self.add_item(CategorySelect(owner_id))

    def make_embed(self) -> discord.Embed:
        col_id = self.player.get("col_id", "base")
        color_map = {
            "base": discord.Color.from_str("#a0a0a0"),
            "comum": discord.Color.from_str("#4287f5"),
            "premiados": discord.Color.from_str("#9b59b6"),
            "copa_do_mundo": discord.Color.from_str("#f1c40f"),
        }
        embed_color = color_map.get(col_id, discord.Color.gold())
        
        col_emoji = self.player.get("col_emoji", "✨")
        col_nome = self.player.get("col_nome", "Comum")
        over = self.player.get("over", "?")
        pos = self.player.get("pos", "?")
        
        title_tab = {
            "atributos": "📊 Atributos",
            "stats": "📈 Estatísticas",
            "bio": "📋 Ficha Técnica",
            "playstyles": "🎭 PlayStyles & Afinidade"
        }
        
        embed = discord.Embed(
            title=f"{col_emoji} {self.player.get('name')} — {title_tab[self.current_tab]}",
            description=(
                f"**Coleção:** {col_nome}  •  **Rated:** `{over}`  •  **Posição:** `{pos}`"
            ),
            color=embed_color
        )
        
        card_path = self.player.get("card", "")
        if card_path:
            embed.set_image(url="attachment://card.png")
            
        if self.current_tab == "atributos":
            # Attributes Block
            is_gk = self.player.get("pos") == "GK"
            if is_gk:
                div = self.player.get("div", 75)
                han = self.player.get("han", 75)
                kic = self.player.get("kic", 75)
                ref = self.player.get("ref", 75)
                spd = self.player.get("spd", 75)
                pos_gk = self.player.get("pos_stat", 75)
                
                val_str = (
                    f"```swift\n"
                    f"🧤 DIV: {div:<3}  │  🎯 HAN: {han:<3}  │  👟 KIC: {kic:<3}\n"
                    f"⚡ REF: {ref:<3}  │  🏃 SPD: {spd:<3}  │  🛡️ POS: {pos_gk:<3}\n"
                    f"```"
                )
                embed.add_field(name="Atributos de Goleiro", value=val_str, inline=False)
            else:
                pac = self.player.get("pac", 75)
                sho = self.player.get("sho", 75)
                pas = self.player.get("pas", 75)
                dri = self.player.get("dri", 75)
                def_val = self.player.get("def", 75)
                phy = self.player.get("phy", 75)
                
                val_str = (
                    f"```swift\n"
                    f"🏃 PAC: {pac:<3}  │  🎯 PAS: {pas:<3}  │  ⚡ DRI: {dri:<3}\n"
                    f"👟 SHO: {sho:<3}  │  🛡️ DEF: {def_val:<3}  │  💪 PHY: {phy:<3}\n"
                    f"```"
                )
                embed.add_field(name="Atributos de Linha", value=val_str, inline=False)
                
            wf = self.player.get("weak_foot", 1)
            sm = self.player.get("skill_moves", 1)
            embed.add_field(
                name="✨ Estrelas de Habilidade",
                value=(
                    f"<:perna:1520392085360873482> **Perna Ruim:** {format_stars(wf)}\n"
                    f"<:Fintas:1520392750548123701> **Fintas:** {format_stars(sm)}"
                ),
                inline=False
            )
            
        elif self.current_tab == "stats":
            matches = self.player.get("matches", 0)
            goals = self.player.get("goals", 0)
            assists = self.player.get("assists", 0)
            saves = self.player.get("saves", 0)
            mvps = self.player.get("mvps", 0)
            yellow = self.player.get("yellow_cards", 0)
            red = self.player.get("red_cards", 0)
            total_xg = self.player.get("xg", 0.0)
            xg_per_game = total_xg / max(1, matches)
            
            embed.add_field(
                name="📈 Histórico em Campo",
                value=(
                    f"👕 Partidas: **{matches}**\n"
                    f"⚽ Gols: **{goals}**\n"
                    f"🎯 Assistências: **{assists}**\n"
                    f"🧤 Defesas (GK): **{saves}**\n"
                    f"👑 Melhor em Campo (MVP): **{mvps}**"
                ),
                inline=True
            )
            embed.add_field(
                name="⚖️ Disciplina & xG",
                value=(
                    f"🟨 Amarelos: **{yellow}**\n"
                    f"🟥 Vermelhos: **{red}**\n"
                    f"🎯 Expected Goals (xG): **{total_xg:.2f}**\n"
                    f"⚡ xG por Partida: **{xg_per_game:.2f}**"
                ),
                inline=True
            )
            
        elif self.current_tab == "bio":
            acq_date = "Indisponível"
            if self.player.get("acquired_at"):
                try:
                    dt = datetime.fromisoformat(self.player["acquired_at"])
                    acq_date = dt.strftime("%d/%m/%Y")
                except Exception:
                    pass
                    
            preferred_foot = self.player.get("preferred_foot", "—")
            height = f"{self.player.get('height')} cm" if self.player.get("height") else "—"
            weight = f"{self.player.get('weight')} kg" if self.player.get("weight") else "—"
            league = self.player.get("league", "—")
            club = self.player.get("club", "—")
            nationality = self.player.get("nationality", "—")
            
            embed.add_field(name="🏢 Clube", value=f"**{club}**", inline=True)
            embed.add_field(name="🏳️ Nacionalidade", value=f"**{nationality}**", inline=True)
            embed.add_field(name="🏆 Liga", value=f"**{league}**", inline=True)
            embed.add_field(name="🦶 Pé Preferido", value=f"**{preferred_foot}**", inline=True)
            embed.add_field(name="📏 Altura", value=f"**{height}**", inline=True)
            embed.add_field(name="⚖️ Peso", value=f"**{weight}**", inline=True)
            embed.add_field(name="📅 Contratado em", value=f"📅 **{acq_date}**", inline=False)
            
        elif self.current_tab == "playstyles":
            xp = self.player.get("xp", 0)
            affinity_level = xp // 10
            affinity_bonus = min(5.0, affinity_level * 0.5)
            
            embed.add_field(
                name="🤝 Afinidade com o Clube",
                value=(
                    f"Nível de Afinidade: 📈 **{affinity_level}**\n"
                    f"Progresso: **{xp % 10}/10 XP** para o próximo nível\n"
                    f"Bônus de Atributo: ✨ **+{affinity_bonus:.1f}%**"
                ),
                inline=False
            )
            
            ps_list = self.player.get("playstyles", [])
            if ps_list:
                ps_str = "  •  ".join([f"{PLAYSTYLE_EMOJIS.get(ps, '✨')} **{ps.capitalize()}**" for ps in ps_list])
            else:
                ps_str = "*Nenhum PlayStyle ativo*"
            embed.add_field(name="🎭 PlayStyles Habilitados", value=ps_str, inline=False)
            
        embed.set_footer(text=f"Instância: {self.player.get('instance_id','?')}  •  Posição Original: {self.player.get('original_pos', pos)}")
        return embed

    async def handle_tab(self, interaction: discord.Interaction, tab: str):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Apenas o dono pode navegar nas abas.", ephemeral=True)
            
        self.current_tab = tab
        embed = self.make_embed()
        await interaction.response.edit_message(embed=embed, view=self)


class SelectShowPlayerView(discord.ui.View):
    def __init__(self, owner_id, players):
        super().__init__(timeout=60)
        self.owner_id = owner_id
        options = [
            discord.SelectOption(
                label=f"{p['name']} — Rated {p['over']}",
                value=p["instance_id"],
                description=f"Posição: {p['pos']} | ID: {p['instance_id'][:8]}"
            ) for p in players
        ]
        self.add_item(PlayerShowDropdown(owner_id, options, players))


class PlayerShowDropdown(discord.ui.Select):
    def __init__(self, owner_id, options, players):
        self.owner_id = owner_id
        self.players = {p["instance_id"]: p for p in players}
        super().__init__(placeholder="Selecione o jogador específico", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
            
        chosen_id = self.values[0]
        player = self.players.get(chosen_id)
        
        cog = interaction.client.get_cog("Equipe")
        if cog:
            view = PlayerShowView(self.owner_id, player, cog)
            embed = view.make_embed()
            
            # Exibe imagem da carta se disponível
            card_path = player.get("card", "")
            file = None
            if card_path:
                if card_path.startswith("http://") or card_path.startswith("https://"):
                    try:
                        import asyncio
                        from pitch_generator import load_card_image
                        import hashlib
                        import os
                        # Garante que a imagem seja baixada/cacheadas no disco
                        await asyncio.to_thread(load_card_image, card_path)
                        url_hash = hashlib.md5(card_path.encode("utf-8")).hexdigest()
                        local_cache_path = os.path.join("cache_cartas", f"{url_hash}.png")
                        
                        if os.path.exists(local_cache_path):
                            file = discord.File(local_cache_path, filename="card.png")
                    except Exception as e:
                        print(f"Erro ao obter imagem no callback dropdown: {e}")
                elif __import__('os').path.exists(card_path):
                    file = discord.File(card_path, filename="card.png")
            
            if file:
                await interaction.response.edit_message(embed=embed, view=view, attachments=[file])
            else:
                await interaction.response.edit_message(embed=embed, view=view)
        else:
            await interaction.response.send_message("❌ Ocorreu um erro interno de carregamento.", ephemeral=True)

class PlayerScaleCarouselView(discord.ui.View):
    def __init__(self, owner_id, target_pos, matches, profile):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.target_pos = target_pos
        self.matches = matches
        self.profile = profile
        self.current_index = 0

    def make_embed(self) -> tuple[discord.Embed, discord.File | None]:
        import os
        player = self.matches[self.current_index]
        col_emoji = player.get("col_emoji", "✨")
        col_nome = player.get("col_nome", "Comum")
        
        embed = discord.Embed(
            title="🎮 Escalar Jogador",
            description=f"Navegue pelas setas e confirme a escalação na posição **{self.target_pos}** com o botão do meio.",
            color=discord.Color.blue()
        )
        embed.add_field(name="Jogador", value=f"{col_emoji} **{player['name']}**", inline=True)
        embed.add_field(name="Posição Original / Rated", value=f"⚽ {player.get('original_pos', player.get('pos','?'))}  •  ⭐ {player.get('over','?')}", inline=True)
        embed.add_field(name="Coleção", value=col_nome, inline=True)
        
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

    @discord.ui.button(label="Escalar", emoji="✅", style=discord.ButtonStyle.success)
    @lock_user()
    async def scale_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Você não pode interagir aqui.", ephemeral=True)
            
        player = self.matches[self.current_index]
        profile = await get_user_profile(interaction.user)
        
        xi = [p for p in profile.get("starting_xi", []) if p.get("instance_id") != player["instance_id"]]
        xi = [p for p in xi if p.get("pos") != self.target_pos]
        
        player_copy = player.copy()
        player_copy["pos"] = self.target_pos
        xi.append(player_copy)
        
        profile["starting_xi"] = xi
        await save_user_profile(interaction.user.id, profile)
        
        for child in self.children:
            child.disabled = True
            
        embed = discord.Embed(
            title="✅ Jogador Escalado!",
            description=f"**{player['name']}** foi escalado na posição **{self.target_pos}** com sucesso!",
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
        self.update_buttons()
        embed, file = self.make_embed()
        if file:
            await interaction.response.edit_message(embed=embed, attachments=[file], view=self)
        else:
            await interaction.response.edit_message(embed=embed, attachments=[], view=self)


async def setup(bot):
    await bot.add_cog(TeamCog(bot))
