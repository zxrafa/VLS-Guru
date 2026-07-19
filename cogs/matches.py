# -*- coding: utf-8 -*-
"""
VLS Guru - Cog de Partidas e Campeonatos (Reboot)
Gerencia desafios PvP, apostas, treinos contra CPU, rankings e torneios mata-mata.
"""
import discord
import re
import io
from discord.ext import commands
from discord import app_commands
import random
import time
import asyncio
import uuid
from datetime import datetime

from database import (
    get_user_profile, save_user_profile,
    get_all_users, db_get, db_upsert, db_delete,
    get_user_lock, lock_user,
)
from simulation import run_match_simulation, calculate_chemistry_bonus
from config import VLS_COINS_EMOJI


class MatchesCog(commands.Cog, name="Partidas"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_drafts = {}

    # ──────────────────────────────────────────────────────────────────────────
    # HELPER: Processamento Pós-Jogo
    # ──────────────────────────────────────────────────────────────────────────

    async def process_match_results(
        self,
        interaction: discord.Interaction,
        p1_user: discord.User,
        p2_user: discord.User,
        sim_res: dict,
        wager: int = 0,
    ) -> str:
        """
        Persiste o resultado da partida:
          - Atualiza W/L/D e saldo dos perfis.
          - Atualiza estatísticas das cartas APENAS no inventário (fonte da verdade),
            depois sincroniza o starting_xi para refletir os mesmos objetos.
          - Verifica conquistas secretas.
          - Incrementa missões.
        Retorna a mensagem de recompensa financeira para exibição.
        """
        p1_profile = await get_user_profile(p1_user)
        p2_profile = await get_user_profile(p2_user)

        p1_goals = sim_res["p1_goals"]
        p2_goals = sim_res["p2_goals"]
        perf     = sim_res["performance"]

        # ── Resultado financeiro e placar ──────────────────────────────────────
        if p1_goals > p2_goals:
            p1_profile["wins"]   += 1
            p2_profile["losses"] += 1
            if wager > 0:
                p1_profile["money"] += wager * 2
                wager_msg = f"💸 **{p1_user.display_name}** venceu a aposta e faturou **R$ {wager * 2:,}**!"
            else:
                p1_profile["money"] += 5_000
                p2_profile["money"] += 2_000
                wager_msg = "💸 Mandante recebeu **R$ 5.000** e visitante **R$ 2.000** como bônus de amistoso."

        elif p2_goals > p1_goals:
            p2_profile["wins"]   += 1
            p1_profile["losses"] += 1
            if wager > 0:
                p2_profile["money"] += wager * 2
                wager_msg = f"💸 **{p2_user.display_name}** venceu a aposta e faturou **R$ {wager * 2:,}**!"
            else:
                p2_profile["money"] += 5_000
                p1_profile["money"] += 2_000
                wager_msg = "💸 Visitante recebeu **R$ 5.000** e mandante **R$ 2.000** como bônus de amistoso."

        else:
            p1_profile["draws"] += 1
            p2_profile["draws"] += 1
            if wager > 0:
                p1_profile["money"] += wager
                p2_profile["money"] += wager
                wager_msg = "🤝 Empate. As apostas foram integralmente devolvidas a ambos os clubes."
            else:
                p1_profile["money"] += 3_000
                p2_profile["money"] += 3_000
                wager_msg = "🤝 Empate. Ambos os clubes receberam **R$ 3.000** de premiação."

        # ── Conquista Secreta: Virada Histórica ───────────────────────────────
        current_p1g = current_p2g = 0
        p1_was_down_3 = p2_was_down_3 = False
        for scorer in sim_res["scorers"]:
            if scorer["team"] == 1:
                current_p1g += 1
            else:
                current_p2g += 1
            if (current_p2g - current_p1g) >= 3:
                p1_was_down_3 = True
            if (current_p1g - current_p2g) >= 3:
                p2_was_down_3 = True

        if p1_was_down_3 and p1_goals > p2_goals:
            if "virada_historica" not in p1_profile.get("achievements", []):
                p1_profile.setdefault("achievements", []).append("virada_historica")
                p1_profile["premium_coins"] += 200
                p1_profile.setdefault("acquired_badges", []).append("virada_historica")
                await interaction.channel.send(
                    f"🏆 **CONQUISTA SECRETA DESBLOQUEADA — {p1_user.mention}!**\n"
                    f"✨ *Milagre em Campo* — Virada após estar perdendo por 3+ gols. Recompensa: **+200 VLS Coins**!"
                )

        if p2_was_down_3 and p2_goals > p1_goals:
            if "virada_historica" not in p2_profile.get("achievements", []):
                p2_profile.setdefault("achievements", []).append("virada_historica")
                p2_profile["premium_coins"] += 200
                p2_profile.setdefault("acquired_badges", []).append("virada_historica")
                await interaction.channel.send(
                    f"🏆 **CONQUISTA SECRETA DESBLOQUEADA — {p2_user.mention}!**\n"
                    f"✨ *Milagre em Campo* — Virada após estar perdendo por 3+ gols. Recompensa: **+200 VLS Coins**!"
                )

        # ── Atualização de Estatísticas das Cartas ────────────────────────────
        # Regra: atualiza APENAS o inventário (fonte da verdade) e depois
        # ressincroniza o starting_xi por instance_id para evitar dupla contagem.

        def _update_stats_in_list(card_list: list):
            for card in card_list:
                pid = card.get("instance_id")
                if pid in perf:
                    card["matches"] = card.get("matches", 0) + 1
                    card["goals"]   = card.get("goals",   0) + perf[pid]["goals"]
                    card["assists"] = card.get("assists", 0) + perf[pid]["assists"]
                    card["saves"]   = card.get("saves",   0) + perf[pid]["saves"]
                    card["xg"]      = card.get("xg",    0.0) + perf[pid]["xg"]
                    card["xp"]      = card.get("xp",      0) + 1
                    if perf[pid]["mvp"]:
                        card["mvps"] = card.get("mvps", 0) + 1

        # P1
        _update_stats_in_list(p1_profile["inventory"])
        # Ressincroniza starting_xi do P1 a partir do inventário atualizado
        inv_p1_map = {c["instance_id"]: c for c in p1_profile["inventory"] if "instance_id" in c}
        for slot in p1_profile.get("starting_xi", []):
            pid = slot.get("instance_id")
            if pid and pid in inv_p1_map:
                # Copia só as chaves de estatísticas, preserva "pos" do slot
                for stat_key in ("matches", "goals", "assists", "saves", "xg", "xp", "mvps"):
                    slot[stat_key] = inv_p1_map[pid].get(stat_key, slot.get(stat_key, 0))

        # P2
        _update_stats_in_list(p2_profile["inventory"])
        inv_p2_map = {c["instance_id"]: c for c in p2_profile["inventory"] if "instance_id" in c}
        for slot in p2_profile.get("starting_xi", []):
            pid = slot.get("instance_id")
            if pid and pid in inv_p2_map:
                for stat_key in ("matches", "goals", "assists", "saves", "xg", "xp", "mvps"):
                    slot[stat_key] = inv_p2_map[pid].get(stat_key, slot.get(stat_key, 0))

        # ── Missões ────────────────────────────────────────────────────────────
        econ_cog = self.bot.get_cog("Economia")
        if econ_cog:
            # P1
            await econ_cog.increment_mission(p1_user.id, p1_profile, "partidas", 1)
            await econ_cog.increment_mission(p1_user.id, p1_profile, "gols", p1_goals)
            await econ_cog.increment_mission(p1_user.id, p1_profile, "desafios", 1)
            if p1_goals > p2_goals:
                await econ_cog.increment_mission(p1_user.id, p1_profile, "vitorias", 1)
            if p2_goals == 0:
                await econ_cog.increment_mission(p1_user.id, p1_profile, "clean_sheets", 1)
            if wager > 0:
                await econ_cog.increment_mission(p1_user.id, p1_profile, "x1_apostado", 1)
                if wager > 500000:
                    await econ_cog.increment_mission(p1_user.id, p1_profile, "x1_apostado_500k", 1)

            # P2
            await econ_cog.increment_mission(p2_user.id, p2_profile, "partidas", 1)
            await econ_cog.increment_mission(p2_user.id, p2_profile, "gols", p2_goals)
            await econ_cog.increment_mission(p2_user.id, p2_profile, "desafios", 1)
            if p2_goals > p1_goals:
                await econ_cog.increment_mission(p2_user.id, p2_profile, "vitorias", 1)
            if p1_goals == 0:
                await econ_cog.increment_mission(p2_user.id, p2_profile, "clean_sheets", 1)
            if wager > 0:
                await econ_cog.increment_mission(p2_user.id, p2_profile, "x1_apostado", 1)
                if wager > 500000:
                    await econ_cog.increment_mission(p2_user.id, p2_profile, "x1_apostado_500k", 1)

        # ── Persistência ───────────────────────────────────────────────────────
        await save_user_profile(p1_user.id, p1_profile)
        await save_user_profile(p2_user.id, p2_profile)

        if econ_cog:
            await econ_cog.check_achievements(p1_user.id, p1_profile, interaction)
            await econ_cog.check_achievements(p2_user.id, p2_profile, interaction)

        return wager_msg

    # ──────────────────────────────────────────────────────────────────────────
    # HELPER: Exibição de Páginas de Simulação
    # ──────────────────────────────────────────────────────────────────────────

    async def show_simulation_pages(
        self,
        interaction: discord.Interaction,
        p1_name: str,
        p2_name: str,
        sim_res: dict,
        footer_msg: str,
    ):
        """Exibe a narração da partida ao vivo minuto a minuto e, no final, exibe o placar oficial com paginação."""
        
        logs = sim_res["narration"]
        
        # Configuração de ambientação (como o bot antigo)
        estadios = [
            "Estádio Olímpico Lluís Companys", "Estádio Nacional do Jamor", "Estádio VLS Arena",
            "Camp Nou Virtual", "Santiago Bernabéu Retro", "Maracanã de Rua", "San Siro Classic",
            "Estádio do Dragão", "Estádio da Luz"
        ]
        climas = [
            {"nome": "Céu limpo", "emoji": "☀️"},
            {"nome": "Nublado", "emoji": "☁️"},
            {"nome": "Garoa", "emoji": "🌧️"},
            {"nome": "Chuva Forte", "emoji": "⛈️"}
        ]
        
        estadio = random.choice(estadios)
        clima = random.choice(climas)

        # --- PRELEÇÃO DE VESTIÁRIO ---
        embed_pre = discord.Embed(
            title="🏟️ VESTIÁRIO — Preleção e Aquecimento",
            description=(
                f"🏟️ **Estádio:** {estadio}\n"
                f"{clima['emoji']} **Clima:** {clima['nome']}\n\n"
                f"🔥 **Confronto:** **{p1_name}** x **{p2_name}**\n\n"
                f"📢 **A bola vai rolar em instantes!** Veja as escalações das duas equipes abaixo."
            ),
            color=discord.Color.blue()
        )
        embed_pre.set_footer(text="VLS TV • Ao Vivo")
        
        # Envia as escalações em imagem
        p1_xi = sim_res.get("p1_xi", [])
        p2_xi = sim_res.get("p2_xi", [])
        p1_form = sim_res.get("p1_formation", "4-3-3")
        p2_form = sim_res.get("p2_formation", "4-3-3")
        
        p1_chem = calculate_chemistry_bonus(p1_xi, p1_form)
        p2_chem = calculate_chemistry_bonus(p2_xi, p2_form)
        
        p1_ovr = sum(p.get("over", 0) for p in p1_xi) // len(p1_xi) if p1_xi else 0
        p2_ovr = sum(p.get("over", 0) for p in p2_xi) // len(p2_xi) if p2_xi else 0

        try:
            # Revela titulares por escrito, 1 por 1, mostrando: Coleção, Rated, Posição e Nome de cada lado
            p1_by_pos = {p.get("pos"): p for p in p1_xi if p.get("pos")}
            p2_by_pos = {p.get("pos"): p for p in p2_xi if p.get("pos")}
            
            from formations_coordinates import FORMATIONS
            slots = list(FORMATIONS.get(p1_form, FORMATIONS["4-3-3"]).keys())
            
            reveal_msg = await interaction.followup.send("📋 **Escalações Oficiais — Preparando a revelação dos times...**")
            
            def format_revealed_player(p: dict) -> str:
                if not p:
                    return "*[Vazio]*"
                col_emoji = p.get("col_emoji", "✨")
                over = p.get("over", "?")
                pos = p.get("pos", "?")
                name = p.get("name", "Jogador")
                return f"{col_emoji} **{over}** {pos} - *{name}*"

            revealed_lines = []
            for i, slot in enumerate(slots):
                p1_p = p1_by_pos.get(slot)
                p2_p = p2_by_pos.get(slot)
                
                p1_str = format_revealed_player(p1_p)
                p2_str = format_revealed_player(p2_p)
                
                line = f"`[{slot}]` {p1_str} 🆚 {p2_str}"
                revealed_lines.append(line)
                
                embed_reveal = discord.Embed(
                    title=f"📋 Escalações Oficiais — {p1_name} x {p2_name}",
                    description=f"**Esquemas:** {p1_form} 🆚 {p2_form}\n\n" + "\n".join(revealed_lines),
                    color=discord.Color.blue()
                )
                embed_reveal.set_footer(text=f"Transmissão ao vivo • Revelando titulares... ({i+1}/11)")
                await reveal_msg.edit(content="", embed=embed_reveal)
                await asyncio.sleep(1.0)
                
            # Altera rodapé ao finalizar
            embed_reveal = discord.Embed(
                title=f"📋 Escalações Oficiais — {p1_name} x {p2_name}",
                description=f"**Esquemas:** {p1_form} 🆚 {p2_form}\n\n" + "\n".join(revealed_lines),
                color=discord.Color.blue()
            )
            embed_reveal.set_footer(text="Titulares revelados! Fim da preleção, bola vai rolar!")
            await reveal_msg.edit(embed=embed_reveal)
        except Exception as e:
            print(f"Erro ao exibir revelação das escalações por escrito: {e}")
            
        msg = await interaction.followup.send(embed=embed_pre)
        await asyncio.sleep(6.0)

        # --- SIMULAÇÃO TRANSMISSÃO AO VIVO ---
        current_p1_goals = 0
        current_p2_goals = 0
        scorers_list = sim_res.get("scorers", [])
        
        # Rastreia os gols processados para exibição correta
        scorers_tracked = []
        for s in scorers_list:
            scorers_tracked.append({
                "minute": s.get("minute", 0),
                "team": s.get("team", 1),
                "processed": False
            })

        recent_plays = []
        first_half_done = False
        
        def parse_minute(log_line: str) -> int:
            m = re.search(r"⏱️ \*\*(\d+)'\*\*", log_line)
            return int(m.group(1)) if m else 0

        for play in logs:
            minuto = parse_minute(play)
            
            # Atualiza o placar ao vivo conforme os gols cadastrados nesse minuto
            for s in scorers_tracked:
                if s["minute"] == minuto and not s["processed"]:
                    s["processed"] = True
                    if s["team"] == 1:
                        current_p1_goals += 1
                    else:
                        current_p2_goals += 1

            # Transição de Intervalo
            if minuto > 45 and not first_half_done:
                first_half_done = True
                embed_interval = discord.Embed(
                    title="🟡 INTERVALO — VLS TV",
                    description=(
                        f"🏠 **{p1_name}**  `{current_p1_goals} — {current_p2_goals}`  ✈️ **{p2_name}**\n\n"
                        f"⏸️ O árbitro apita o fim do primeiro tempo! Jogadores vão para o vestiário descansar."
                    ),
                    color=discord.Color.gold()
                )
                embed_interval.set_footer(text="VLS TV • Ao Vivo")
                await msg.edit(embed=embed_interval)
                await asyncio.sleep(5.0)

            # Adiciona o lance na lista de recentes
            recent_plays.append(play)
            if len(recent_plays) > 4:
                recent_plays.pop(0)

            # Barra de progresso visual
            filled = int((minuto / 90.0) * 16)
            progress_bar = "█" * filled + "░" * (16 - filled)
            
            recent_text = "\n\n".join(recent_plays)
            tempo_nome = "1º Tempo" if minuto <= 45 else "2º Tempo"
            
            embed_live = discord.Embed(
                title=f"🎙️ TRANSMISSÃO AO VIVO — VLS TV | {tempo_nome}",
                description=(
                    f"🏟️ **Estádio:** {estadio} | {clima['emoji']} **Clima:** {clima['nome']}\n\n"
                    f"🏠 **{p1_name}**  `{current_p1_goals} — {current_p2_goals}`  ✈️ **{p2_name}**\n\n"
                    f"⏱️ **Tempo:** `[{progress_bar}] {minuto}'`\n\n"
                    f"**Últimos lances:**\n"
                    f"{recent_text}"
                ),
                color=discord.Color.blue()
            )
            
            # Destaca gols mudando a cor do embed para verde
            if "⚽" in play or "GOOOL" in play:
                embed_live.color = discord.Color.brand_green()

            await msg.edit(embed=embed_live)
            await asyncio.sleep(3.5)

        # --- APITO FINAL LIVE ---
        embed_apito = discord.Embed(
            title="🏁 APITO FINAL!",
            description=(
                f"🏠 **{p1_name}**  `{current_p1_goals} — {current_p2_goals}`  ✈️ **{p2_name}**\n\n"
                f"📢 **Fim de jogo!** O árbitro encerra a partida sob vaias e aplausos dos torcedores!"
            ),
            color=discord.Color.red()
        )
        embed_apito.set_footer(text="VLS TV • Ao Vivo")
        await msg.edit(embed=embed_apito)
        await asyncio.sleep(4.0)

        # --- PREPARA RELATÓRIO FINAL COM BOTOES E PAGINAÇÃO ---
        lines_per_page = 8
        pages          = [logs[i : i + lines_per_page] for i in range(0, max(1, len(logs)), lines_per_page)]

        narr_embeds = []
        for idx, page in enumerate(pages):
            embed = discord.Embed(
                title       = f"🏟️ {p1_name}  vs  {p2_name} — Reprise de Lances",
                description = "\n\n".join(page) if page else "*Partida sem lances registrados.*",
                color       = discord.Color.dark_theme(),
            )
            embed.set_footer(text=f"Página {idx + 1}/{len(pages)} • VLS Guru Match Engine")
            narr_embeds.append(embed)

        p1g    = sim_res["p1_goals"]
        p2g    = sim_res["p2_goals"]
        stats  = sim_res["stats"]
        xg     = sim_res["xg"]
        mvp    = sim_res["mvp"]

        final_embed = discord.Embed(
            title       = "🏁 PLACAR OFICIAL — Estatísticas & Prêmios",
            description = f"🏠 **{p1_name}**  `{p1g} — {p2g}`  ✈️ **{p2_name}**",
            color       = discord.Color.brand_green() if p1g != p2g else discord.Color.greyple(),
        )
        final_embed.add_field(
            name  = "📊 Estatísticas da Partida",
            value = (
                f"👟 **Chutes (no Alvo):** {stats['p1']['shots']} ({stats['p1']['on_target']}) vs "
                f"{stats['p2']['shots']} ({stats['p2']['on_target']})\n"
                f"🧤 **Defesas do Goleiro:** {stats['p1']['saves']} vs {stats['p2']['saves']}\n"
                f"🚩 **Escanteios:** {stats['p1']['corners']} vs {stats['p2']['corners']}\n"
                f"⚠️ **Faltas:** {stats['p1']['fouls']} vs {stats['p2']['fouls']}\n"
                f"🟨 **Amarelos:** {stats['p1']['yellow']} vs {stats['p2']['yellow']}\n"
                f"🟥 **Vermelhos:** {stats['p1']['red']} vs {stats['p2']['red']}\n"
                f"📈 **xG Acumulado:** {xg['p1']:.2f} vs {xg['p2']:.2f}\n"
                f"👑 **Melhor em Campo (MVP):** **{mvp}**"
            ),
            inline=False,
        )
        final_embed.add_field(name="💰 Recompensas & Resultado Financeiro", value=footer_msg, inline=False)

        view = MatchReportView(narr_embeds, final_embed)
        await msg.edit(embed=final_embed, view=view)

    # ──────────────────────────────────────────────────────────────────────────
    # COMANDOS: PARTIDAS PvP
    # ──────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="desafio", description="Desafia outro membro para um amistoso de futebol.")
    @app_commands.describe(usuario="O clube que você deseja enfrentar")
    async def desafio(self, interaction: discord.Interaction, usuario: discord.User):
        if usuario.id == interaction.user.id:
            return await interaction.response.send_message("❌ Você não pode desafiar a si mesmo.", ephemeral=True)
        if usuario.bot:
            return await interaction.response.send_message("❌ Bots não podem participar de partidas.", ephemeral=True)

        p1_profile = await get_user_profile(interaction.user)
        p2_profile = await get_user_profile(usuario)

        if len(p1_profile.get("starting_xi", [])) < 11:
            return await interaction.response.send_message("❌ Seu clube precisa de 11 titulares escalados. Use `/escalar`.", ephemeral=True)
        if len(p2_profile.get("starting_xi", [])) < 11:
            return await interaction.response.send_message("❌ O adversário desafiado não possui 11 titulares escalados.", ephemeral=True)

        view = ChallengeResponseView(interaction.user, usuario, self, wager=0)
        await interaction.response.send_message(
            f"\u2694\ufe0f **DESAFIO LANÇADO!** {interaction.user.mention} desafia {usuario.mention} para um confronto amistoso!\n"
            f"*{usuario.display_name}, clique em **Aceitar** para confirmar o confronto.*",
            view=view,
        )
        view.message = await interaction.original_response()

    @app_commands.command(name="x1_aposta", description="Desafia outro membro para uma partida com aposta em dinheiro.")
    @app_commands.describe(usuario="O adversário desafiado", aposta="Valor apostado por cada clube (R$)")
    async def x1_aposta(self, interaction: discord.Interaction, usuario: discord.User, aposta: int):
        if usuario.id == interaction.user.id:
            return await interaction.response.send_message("❌ Operação inválida.", ephemeral=True)
        if usuario.bot:
            return await interaction.response.send_message("❌ Bots não aceitam apostas.", ephemeral=True)
        if aposta <= 0:
            return await interaction.response.send_message("❌ O valor da aposta deve ser positivo.", ephemeral=True)

        p1_profile = await get_user_profile(interaction.user)
        p2_profile = await get_user_profile(usuario)

        if p1_profile.get("money", 0) < aposta:
            return await interaction.response.send_message(f"❌ Seu saldo é insuficiente para apostar R$ {aposta:,}.", ephemeral=True)
        if p2_profile.get("money", 0) < aposta:
            return await interaction.response.send_message("❌ O adversário não possui fundos suficientes para cobrir a aposta.", ephemeral=True)
        if len(p1_profile.get("starting_xi", [])) < 11 or len(p2_profile.get("starting_xi", [])) < 11:
            return await interaction.response.send_message("❌ Ambos os clubes precisam ter 11 titulares escalados.", ephemeral=True)

        view = ChallengeResponseView(interaction.user, usuario, self, wager=aposta)
        await interaction.response.send_message(
            f"⚔️ **X1 APOSTADO!** {interaction.user.mention} desafia {usuario.mention} por **R$ {aposta:,}** de cada clube!\n"
            f"*(O vencedor leva o prêmio total de **R$ {aposta * 2:,}**)*\n"
            f"*{usuario.display_name}, você tem 60 segundos para aceitar.*",
            view=view,
        )
        view.message = await interaction.original_response()

    @app_commands.command(name="treino", description="Realiza um treino contra a CPU para aumentar a afinidade dos titulares (cooldown: 5 min).")
    async def treino(self, interaction: discord.Interaction):
        await interaction.response.defer()
        profile     = await get_user_profile(interaction.user)
        starting_xi = profile.get("starting_xi", [])

        if len(starting_xi) < 11:
            return await interaction.followup.send("❌ Você precisa de 11 titulares escalados para treinar.", ephemeral=True)

        now      = int(time.time())
        last_t   = profile.get("last_treino", 0)
        # Cooldown de 5 minutos (2.5 minutos para boosters)
        is_booster = getattr(interaction.user, "premium_since", None) is not None
        cooldown = 150 if is_booster else 300

        if now - last_t < cooldown:
            remaining = cooldown - (now - last_t)
            minutos = remaining // 60
            segundos = remaining % 60
            booster_msg = "⚡ **Bônus Booster ativo!** " if is_booster else ""
            return await interaction.followup.send(
                f"⏳ {booster_msg}Seu elenco ainda está em recuperação. Aguarde **{minutos}m {segundos}s** para o próximo treino.",
                ephemeral=True,
            )

        profile["last_treino"] = now

        # Calcula o OVR médio do time do jogador
        xi_ovrs = [p.get("over", 70) for p in starting_xi]
        avg_ovr = int(sum(xi_ovrs) / max(1, len(xi_ovrs)))

        # Gera time CPU com OVR proporcional ao do jogador (±10% de variação)
        from database import get_all_players as _get_all_players
        all_players = await _get_all_players()

        cpu_positions = ["GK", "CB", "CB", "LB", "RB", "CM", "CM", "CDM", "LW", "RW", "ST"]

        if all_players and len(all_players) >= 5:
            # Usa jogadores reais como base e varia o OVR ±10%
            cpu_xi = []
            pool = all_players * 3  # replica para ter jogadores suficientes
            random.shuffle(pool)
            used_ids = set()
            for i, cpu_pos in enumerate(cpu_positions):
                candidates = [p for p in pool if p.get("id") not in used_ids]
                if candidates:
                    base_player = random.choice(candidates[:15])
                    used_ids.add(base_player.get("id"))
                else:
                    base_player = random.choice(pool)

                # OVR do adversario varia dentro de +-10% do avg_ovr do jogador
                variation = int(avg_ovr * 0.10)
                cpu_ovr = max(50, min(99, avg_ovr + random.randint(-variation, variation)))

                # Atributos derivados do OVR ajustado
                base_stat = max(50, cpu_ovr - 5)
                cpu_xi.append({
                    "instance_id": f"cpu_{i}",
                    "name": f"CPU {base_player.get('name', 'Jogador')[:12]}",
                    "over": cpu_ovr,
                    "pos": cpu_pos,
                    "shoot":    base_player.get("shoot", base_stat),
                    "pass_stat":base_player.get("pass_stat", base_stat),
                    "dribble":  base_player.get("dribble", base_stat),
                    "defense":  base_player.get("defense", base_stat),
                    "physical": base_player.get("physical", base_stat),
                    "weak_foot":   base_player.get("weak_foot", 3),
                    "skill_moves": base_player.get("skill_moves", 2),
                    "playstyles":  [],
                    "nationality": "CPU",
                    "club":        "CPU FC",
                    "xp":          0,
                })
        else:
            # Fallback se não houver jogadores cadastrados
            cpu_names = ["Araújo","Mendes","Carvalho","Ribeiro","Nunes","Teixeira","Barros","Cardoso","Moreira","Pinto","Sousa"]
            variation = int(avg_ovr * 0.10)
            cpu_xi = [
                {
                    "instance_id": f"cpu_{i}",
                    "name":        f"CPU {cpu_names[i]}",
                    "over":        max(50, min(99, avg_ovr + random.randint(-variation, variation))),
                    "pos":         cpu_positions[i],
                    "shoot":       max(50, avg_ovr - 5),
                    "pass_stat":   max(50, avg_ovr - 5),
                    "dribble":     max(50, avg_ovr - 5),
                    "defense":     max(50, avg_ovr - 5),
                    "physical":    max(50, avg_ovr - 5),
                    "weak_foot":   random.randint(2, 4),
                    "skill_moves": random.randint(1, 3),
                    "playstyles":  [],
                    "nationality": "CPU",
                    "club":        "CPU FC",
                    "xp":          0,
                }
                for i in range(11)
            ]

        p1_chem  = calculate_chemistry_bonus(starting_xi, profile.get("formation", "4-3-3"))
        cpu_chem = {p["instance_id"]: 0 for p in cpu_xi}

        sim_res = run_match_simulation(
            p1_name   = profile["club_name"],
            p2_name   = "CPU — Treino",
            p1_xi     = starting_xi,
            p2_xi     = cpu_xi,
            p1_tactic = profile.get("tactic", "padrao"),
            p2_tactic = "padrao",
            p1_chem   = p1_chem,
            p2_chem   = cpu_chem,
            p1_formation = profile.get("formation", "4-3-3"),
            p2_formation = "4-3-3",
            p1_torcida_level = profile.get("torcida_level", 1),
            p2_torcida_level = 1,
        )

        # Recompensa fixa de treino: R$ 3.000 + +1 XP de afinidade por titular
        profile["money"] += 3_000
        starting_ids = {p["instance_id"] for p in starting_xi}

        # Atualiza APENAS o inventário (fonte da verdade)
        for card in profile["inventory"]:
            if card.get("instance_id") in starting_ids:
                card["xp"] = card.get("xp", 0) + 1

        # Ressincroniza starting_xi
        inv_map = {c["instance_id"]: c for c in profile["inventory"] if "instance_id" in c}
        for slot in profile["starting_xi"]:
            pid = slot.get("instance_id")
            if pid and pid in inv_map:
                slot["xp"] = inv_map[pid].get("xp", slot.get("xp", 0))

        econ_cog = self.bot.get_cog("Economia")
        if econ_cog:
            await econ_cog.increment_mission(interaction.user.id, profile, "treinos", 1)

        await save_user_profile(interaction.user.id, profile)

        footer_msg = "💸 **Recompensa de Treino:** R$ 3.000 creditados | Todos os titulares ganharam **+1 XP de Afinidade**."
        await self.show_simulation_pages(interaction, profile["club_name"], "CPU — Treino", sim_res, footer_msg)

    @app_commands.command(name="ranking", description="Exibe a classificação geral dos clubes do servidor.")
    @app_commands.describe(criterio="Ordenar o ranking por este critério")
    @app_commands.choices(criterio=[
        app_commands.Choice(name="Vitórias",    value="vitorias"),
        app_commands.Choice(name="Dinheiro",    value="dinheiro"),
        app_commands.Choice(name="Conquistas",  value="conquistas"),
    ])
    async def ranking(self, interaction: discord.Interaction, criterio: str = "vitorias"):
        users = await get_all_users()
        if not users:
            return await interaction.response.send_message("❌ Nenhum clube registrado no sistema.", ephemeral=True)

        if criterio == "dinheiro":
            users.sort(key=lambda u: u.get("money", 0), reverse=True)
            label = "💵 Saldo em Caixa"
            lines = [
                f"**#{i + 1}** {u.get('club_name', 'FC')} — R$ {u.get('money', 0):,}"
                for i, u in enumerate(users[:10])
            ]
        elif criterio == "conquistas":
            users.sort(key=lambda u: len(u.get("achievements", [])), reverse=True)
            label = "🏆 Conquistas Desbloqueadas"
            lines = [
                f"**#{i + 1}** {u.get('club_name', 'FC')} — {len(u.get('achievements', []))} conquistas"
                for i, u in enumerate(users[:10])
            ]
        else:
            users.sort(key=lambda u: u.get("wins", 0), reverse=True)
            label = "🛡️ Vitórias"
            lines = [
                f"**#{i + 1}** {u.get('club_name', 'FC')} — {u.get('wins', 0)}V / {u.get('losses', 0)}D"
                for i, u in enumerate(users[:10])
            ]

        embed = discord.Embed(
            title       = f"📊 Ranking Global — Top 10 por {label}",
            description = "\n".join(lines) if lines else "Nenhum dado disponível.",
            color       = discord.Color.gold(),
        )
        embed.set_footer(text="VLS Guru Leaderboard • Atualizado em tempo real")
        await interaction.response.send_message(embed=embed)

    # ──────────────────────────────────────────────────────────────────────────
    # COMANDOS: CAMPEONATO MATA-MATA
    # ──────────────────────────────────────────────────────────────────────────

    @app_commands.command(name="campeonato_admin", description="[Admin] Dashboard central para gerenciar campeonatos.")
    async def campeonato_admin(self, interaction: discord.Interaction):
        """Dashboard centralizado para criacao, visualizacao, cancelamento e inicio de campeonato."""
        ALLOWED_IDS = {338704196180115458, 1411893056516391034, 792144300666126336}
        is_admin = (
            interaction.user.guild_permissions.administrator
            or interaction.user.id in ALLOWED_IDS
        )
        if not is_admin:
            return await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)

        doc_id = f"champ_{interaction.guild.id}"
        record = await db_get(doc_id)
        champ = record["data"] if record else None

        status = champ.get("status", "waiting") if champ else "none"
        parts_count = len(champ.get("participants", [])) if champ else 0
        rodada = champ.get("round", 0) if champ else 0

        embed = discord.Embed(
            title="🏆 Dashboard de Campeonatos",
            color=discord.Color.gold()
        )
        if not champ:
            embed.description = "⚠️ Nenhum campeonato ativo. Crie um novo abaixo."
        elif status == "waiting":
            embed.description = f"📋 **Status:** Inscrições abertas | **Participantes:** {parts_count}"
        elif status == "active":
            embed.description = f"⚔️ **Status:** Em andamento | **Rodada:** {rodada} | **Participantes:** {parts_count}"
        else:
            embed.description = f"Status: `{status}`"

        embed.add_field(
            name="✅ Ações Disponíveis",
            value=(
                "🏃 **Criar** — Abre um novo campeonato com inscrições\n"
                "🗡️ **Iniciar** — Começa as rodadas (fecha inscrições)\n"
                "⏭️ **Rodar Jogo** — Simula a rodada atual\n"
                "🗑️ **Cancelar** — Encerra e apaga o campeonato (dupla confirmação)"
            ),
            inline=False
        )
        embed.set_footer(text="Dashboard restrito a administradores")

        view = CampeonatoAdminView(interaction.user.id, interaction.guild.id, self, champ)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


    @app_commands.command(name="campeonato", description="Exibe o chaveamento e status do campeonato ativo.")
    async def campeonato(self, interaction: discord.Interaction):
        doc_id = f"champ_{interaction.guild.id}"
        record = await db_get(doc_id)
        if not record:
            return await interaction.response.send_message("❌ Nenhum campeonato ativo neste servidor.", ephemeral=True)

        champ  = record["data"]
        status = champ.get("status", "waiting")
        embed  = discord.Embed(title="🏆 Central do Torneio VLS Guru", color=discord.Color.gold())

        if status == "waiting":
            lines = []
            for idx, pid in enumerate(champ["participants"]):
                member = interaction.guild.get_member(pid)
                lines.append(f"{idx + 1}. {member.display_name if member else f'Membro #{pid}'}")
            embed.description = "📋 **Fase de Inscrição** — Clique no botão abaixo para participar!"
            embed.add_field(
                name  = f"Participantes Inscritos ({len(champ['participants'])})",
                value = "\n".join(lines) if lines else "Nenhum participante ainda.",
                inline=False,
            )
            view = ParticipateView(interaction.guild.id)
            return await interaction.response.send_message(embed=embed, view=view)

        elif status == "active":
            embed.description = f"⚔️ **Rodada {champ.get('round', 1)} em Andamento**"
            match_lines = []
            for idx, m in enumerate(champ["matches"]):
                p1_m = interaction.guild.get_member(m["p1"])
                p2_m = interaction.guild.get_member(m["p2"])
                p1_name = p1_m.display_name if p1_m else "Mandante"
                p2_name = p2_m.display_name if p2_m else "Visitante"
                if "p1_goals" in m:
                    winner_mention = f"<@{m['winner']}>"
                    match_lines.append(
                        f"**Jogo #{idx + 1}:** {p1_name} `{m['p1_goals']} — {m['p2_goals']}` {p2_name} — Vencedor: {winner_mention}"
                    )
                else:
                    match_lines.append(f"**Jogo #{idx + 1}:** {p1_name} vs {p2_name} *(Aguardando simulação)*")
            embed.add_field(
                name  = "Confrontos da Rodada",
                value = "\n".join(match_lines) if match_lines else "Nenhum confronto gerado.",
                inline=False,
            )

        else:
            embed.description = "✅ Torneio concluído ou cancelado."

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rodar_jogo", description="[Torneio] Simula os confrontos pendentes da rodada atual.")
    async def rodar_jogo(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)

        doc_id = f"champ_{interaction.guild.id}"
        record = await db_get(doc_id)
        if not record:
            return await interaction.response.send_message("❌ Nenhum campeonato ativo.", ephemeral=True)

        champ = record["data"]

        # ── Fase de espera: gera o primeiro chaveamento ────────────────────────
        if champ.get("status") == "waiting":
            parts = list(champ["participants"])
            if len(parts) < 2:
                return await interaction.response.send_message(
                    "❌ São necessários no mínimo **2 participantes** para iniciar o chaveamento.", ephemeral=True
                )
            random.shuffle(parts)
            bye_player = None
            if len(parts) % 2 != 0:
                bye_player = parts.pop()
            matches = [{"p1": parts[i], "p2": parts[i + 1]} for i in range(0, len(parts), 2)]

            champ.update({"status": "active", "round": 1, "matches": matches, "bye_player": bye_player})
            await db_upsert(doc_id, champ)
            return await interaction.response.send_message(
                "⚔️ **Chaveamento Gerado!** Rodada 1 criada com sucesso.\n"
                "Consulte os confrontos com `/campeonato` e rode os jogos executando `/rodar_jogo` novamente."
            )

        # ── Fase ativa: simula confrontos pendentes ────────────────────────────
        if champ.get("status") == "active":
            await interaction.response.defer()

            has_pending = any("p1_goals" not in m for m in champ["matches"])

            if not has_pending:
                # Todos simulados → avança de fase ou coroa campeão
                winners = [m["winner"] for m in champ["matches"]]
                if champ.get("bye_player"):
                    winners.append(champ["bye_player"])

                if len(winners) == 1:
                    champ["status"] = "finished"
                    await db_upsert(doc_id, champ)
                    winner_id     = winners[0]
                    winner_member = interaction.guild.get_member(winner_id)
                    if winner_member:
                        winner_profile = await get_user_profile(winner_member)
                        winner_profile["money"]         += 150_000
                        winner_profile["premium_coins"] += 100
                        winner_profile.setdefault("achievements", [])
                        if "titulo_primeiro" not in winner_profile["achievements"]:
                            winner_profile["achievements"].append("titulo_primeiro")
                        await save_user_profile(winner_id, winner_profile)

                    embed_win = discord.Embed(
                        title       = "🏆 CAMPEÃO DO TORNEIO VLS GURU!",
                        description = (
                            f"👑 **{winner_member.mention if winner_member else f'<@{winner_id}>'}** "
                            f"se consagrou **campeão** após uma disputa épica!\n\n"
                            f"💰 **Premiação da Taça:**\n"
                            f"• R$ 150.000 depositados no clube vencedor\n"
                            f"• +100 VLS Coins de bônus exclusivo"
                        ),
                        color=discord.Color.gold(),
                    )
                    return await interaction.followup.send(embed=embed_win)

                # Próxima fase
                random.shuffle(winners)
                bye_player = None
                if len(winners) % 2 != 0:
                    bye_player = winners.pop()
                new_matches = [{"p1": winners[i], "p2": winners[i + 1]} for i in range(0, len(winners), 2)]
                champ["round"]      += 1
                champ["matches"]     = new_matches
                champ["bye_player"]  = bye_player
                await db_upsert(doc_id, champ)
                return await interaction.followup.send(
                    f"✅ Rodada anterior concluída! Chaveamento da **Rodada {champ['round']}** gerado. Use `/campeonato`."
                )

            # Simula confrontos pendentes desta rodada
            for m in champ["matches"]:
                if "p1_goals" in m:
                    continue  # Já simulado

                p1_m = interaction.guild.get_member(m["p1"])
                p2_m = interaction.guild.get_member(m["p2"])

                if not p1_m or not p2_m:
                    # W.O. — avança quem está presente
                    m["p1_goals"] = 0
                    m["p2_goals"] = 0
                    m["winner"]   = m["p1"] if p1_m else m["p2"]
                    await interaction.followup.send(
                        f"⚠️ **W.O.:** Um dos participantes não está mais no servidor. O confronto foi encerrado por ausência."
                    )
                    continue

                p1_prof = await get_user_profile(p1_m)
                p2_prof = await get_user_profile(p2_m)

                if len(p1_prof.get("starting_xi", [])) < 11 or len(p2_prof.get("starting_xi", [])) < 11:
                    m["p1_goals"] = 0
                    m["p2_goals"] = 0
                    m["winner"]   = m["p1"] if len(p1_prof.get("starting_xi", [])) >= 11 else m["p2"]
                    await interaction.followup.send(
                        f"⚠️ **W.O.:** Um dos clubes não possui 11 titulares escalados. Vitória por ausência concedida."
                    )
                    continue

                p1_chem = calculate_chemistry_bonus(p1_prof["starting_xi"], p1_prof.get("formation", "4-3-3"))
                p2_chem = calculate_chemistry_bonus(p2_prof["starting_xi"], p2_prof.get("formation", "4-3-3"))

                sim = run_match_simulation(
                    p1_name   = p1_prof["club_name"],
                    p2_name   = p2_prof["club_name"],
                    p1_xi     = p1_prof["starting_xi"],
                    p2_xi     = p2_prof["starting_xi"],
                    p1_tactic = p1_prof.get("tactic", "padrao"),
                    p2_tactic = "padrao",
                    p1_chem   = p1_chem,
                    p2_chem   = p2_chem,
                    p1_formation = p1_prof.get("formation", "4-3-3"),
                    p2_formation = "4-3-3",
                    p1_torcida_level = p1_prof.get("torcida_level", 1),
                    p2_torcida_level = p2_prof.get("torcida_level", 1),
                )

                m["p1_goals"] = sim["p1_goals"]
                m["p2_goals"] = sim["p2_goals"]
                # Empate no torneio: avança o mandante
                m["winner"]   = m["p1"] if sim["p1_goals"] >= sim["p2_goals"] else m["p2"]

                await self.process_match_results(interaction, p1_m, p2_m, sim)

                await interaction.followup.send(
                    f"⚔️ **{p1_prof['club_name']}** `{sim['p1_goals']} — {sim['p2_goals']}` **{p2_prof['club_name']}** "
                    f"→ Avança: <@{m['winner']}>"
                )
                await asyncio.sleep(1)

            await db_upsert(doc_id, champ)
            await interaction.followup.send(
                "🎮 **Todos os confrontos desta rodada foram simulados!**\n"
                "Execute `/rodar_jogo` novamente para avançar para a próxima fase."
            )

        else:
            await interaction.response.send_message("❌ O campeonato não está em um estado ativo. Use `/criar_campeonato`.", ephemeral=True)

    @app_commands.command(name="cancelar_campeonato", description="[Torneio] Cancela e apaga os dados do campeonato corrente.")
    async def cancelar_campeonato(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("❌ Apenas administradores.", ephemeral=True)

        doc_id = f"champ_{interaction.guild.id}"
        record = await db_get(doc_id)
        if not record:
            return await interaction.response.send_message("❌ Nenhum campeonato ativo para cancelar.", ephemeral=True)

        await db_delete(doc_id)
        await interaction.response.send_message(
            "🚨 **Campeonato Cancelado.** Todos os dados do torneio desta edição foram removidos."
        )


    # ── MÓDULO 5: DISPUTA DE PÊNALTIS ──────────────────────────────────────────

    @app_commands.command(name="penalti_treino", description="Disputa de pênaltis contra o goleiro da CPU para treinar.")
    @lock_user()
    async def penalti_treino(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="⚽ Disputa de Pênaltis (Treino CPU) — Rodada 1/5",
            description="👤 **Você:** ⚪ ⚪ ⚪ ⚪ ⚪\n"
                        "🤖 **CPU:** ⚪ ⚪ ⚪ ⚪ ⚪\n\n"
                        "Escolha o canto do seu chute abaixo para iniciar a disputa!",
            color=discord.Color.blue()
        )
        view = PenaltiTreinoView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="modo_7-0", description="Jogue o modo draft 7-0: monte um time de 11 jogadores e jogue 7 partidas contra a CPU!")
    @lock_user()
    async def modo_7_0(self, interaction: discord.Interaction):
        if interaction.user.id != 338704196180115458:
            return await interaction.response.send_message("❌ Este comando está em fase de testes e indisponível no momento.", ephemeral=True)
            
        await interaction.response.defer()
        
        profile = await get_user_profile(interaction.user)
        now = time.time()
        
        # Cooldown diário: 24 horas (12 horas para boosters)
        last_modo = profile.get("last_modo_7_0", 0)
        is_booster = getattr(interaction.user, "premium_since", None) is not None
        cooldown = 43200 if is_booster else 86400
        
        if now - last_modo < cooldown:
            restante = cooldown - (now - last_modo)
            horas = int(restante // 3600)
            minutos = int((restante % 3600) // 60)
            segundos = int(restante % 60)
            booster_msg = "⚡ **Bônus Booster ativo!** " if is_booster else ""
            time_str = f"{horas}h {minutos}m" if horas > 0 else f"{minutos}m {segundos}s"
            return await interaction.followup.send(
                f"⏳ {booster_msg}Você já jogou o Modo 7-0 hoje! Aguarde mais **{time_str}** para jogar novamente."
            )
            
        # Registra o início do draft definindo o timestamp do cooldown (anti-cheat)
        profile["last_modo_7_0"] = now
        await save_user_profile(interaction.user.id, profile)
        
        from database import get_all_players as _get_all_players
        all_players = await _get_all_players()
        if not all_players or len(all_players) < 5:
            return await interaction.followup.send("❌ Não há jogadores catalogados suficientes para jogar o draft.")
            
        # Inicializa a sessão de draft
        view = DraftView(interaction.user.id, all_players, self)
        await view.roll_options()
        
        slot = view.slots[0]
        embed = discord.Embed(
            title="🎮 MODO 7-0 — Draft de Elenco",
            description=(
                f"Monte sua equipe de 11 jogadores e enfrente 7 adversários!\n\n"
                f"**Posição Atual:** 🎯 `[{slot}]`\n"
                f"**Rerolls Restantes:** 🔄 {view.rerolls_left}\n\n"
                f"**Time Escalado (0/11):**\n"
                f"*Nenhum jogador selecionado*"
            ),
            color=discord.Color.purple()
        )
        embed.set_footer(text="VLS Arena • Draft interactivo")
        
        # Mostra opções iniciais
        view.clear_items()
        view.add_item(DraftDropdown(view.current_options))
        view.add_item(RerollButton(view.rerolls_left))
        
        view.message = await interaction.followup.send(embed=embed, view=view)

    @app_commands.command(name="penalti_desafio", description="Desafia outro manager para uma disputa de pênaltis PvP (com ou sem aposta).")
    @app_commands.describe(adversario="Oponente para desafiar", aposta="Valor opcional de aposta em dinheiro")
    @lock_user()
    async def penalti_desafio(self, interaction: discord.Interaction, adversario: discord.Member, aposta: int = 0):
        if adversario.id == interaction.user.id:
            return await interaction.response.send_message("❌ Você não pode desafiar a si mesmo.", ephemeral=True)
            
        if aposta < 0:
            return await interaction.response.send_message("❌ O valor da aposta não pode ser negativo.", ephemeral=True)
            
        p1 = await get_user_profile(interaction.user)
        p2 = await get_user_profile(adversario)
        
        if aposta > 0:
            if p1.get("money", 0) < aposta:
                return await interaction.response.send_message(f"❌ Você não possui saldo de R$ {aposta:,} para apostar.", ephemeral=True)
            if p2.get("money", 0) < aposta:
                return await interaction.response.send_message(f"❌ O adversário não possui saldo de R$ {aposta:,} para apostar.", ephemeral=True)
                
        aposta_txt = f" apostando **R$ {aposta:,}**" if aposta > 0 else ""
        embed = discord.Embed(
            title="⚽ Desafio de Pênaltis PvP!",
            description=f"⚔️ {interaction.user.mention} desafiou {adversario.mention} para uma disputa de pênaltis{aposta_txt}!\n"
                        f"Clique no botão verde abaixo para aceitar o desafio.",
            color=discord.Color.purple()
        )
        
        view = PenaltiAceitarView(self, interaction.user, adversario, aposta)
        await interaction.response.send_message(embed=embed, view=view)

    # ── MÓDULO 6: MODO LIGA ────────────────────────────────────────────────────
    
    @app_commands.command(name="liga", description="Exibe seu status no Modo Liga e permite simular partidas contra a CPU.")
    @app_commands.choices(acao=[
        app_commands.Choice(name="Visualizar Status", value="status"),
        app_commands.Choice(name="Jogar Partida", value="jogar")
    ])
    @lock_user()
    async def liga(self, interaction: discord.Interaction, acao: str):
        await interaction.response.defer()
        
        profile = await get_user_profile(interaction.user)
        div = profile.setdefault("liga_div", "Bronze")
        wins = profile.setdefault("liga_wins", 0)
        losses = profile.setdefault("liga_losses", 0)
        
        LIGAS_CONFIG = {
            "Bronze": {"wins_needed": 3, "losses_cair": None, "ovr_min": 70, "ovr_max": 75, "premio_vitoria": 5_000, "proxima": "Prata", "anterior": None},
            "Prata": {"wins_needed": 5, "losses_cair": None, "ovr_min": 75, "ovr_max": 79, "premio_vitoria": 8_000, "proxima": "Ouro", "anterior": None},
            "Ouro": {"wins_needed": 7, "losses_cair": 10, "ovr_min": 80, "ovr_max": 84, "premio_vitoria": 12_000, "proxima": "Esmeralda", "anterior": "Prata"},
            "Esmeralda": {"wins_needed": 10, "losses_cair": 8, "ovr_min": 84, "ovr_max": 87, "premio_vitoria": 15_000, "proxima": "Diamante", "anterior": "Ouro"},
            "Diamante": {"wins_needed": 13, "losses_cair": 6, "ovr_min": 87, "ovr_max": 90, "premio_vitoria": 20_000, "proxima": "Icone", "anterior": "Esmeralda"},
            "Icone": {"wins_needed": 15, "losses_cair": 5, "ovr_min": 90, "ovr_max": 93, "premio_vitoria": 25_000, "proxima": "Dev", "anterior": "Diamante"},
            "Dev": {"wins_needed": 20, "losses_cair": 3, "ovr_min": 93, "ovr_max": 96, "premio_vitoria": 30_000, "proxima": "VLS", "anterior": "Icone"},
            "VLS": {"wins_needed": None, "losses_cair": None, "ovr_min": 96, "ovr_max": 99, "premio_vitoria": 40_000, "proxima": None, "anterior": None}
        }
        
        config = LIGAS_CONFIG.get(div, LIGAS_CONFIG["Bronze"])
        
        if acao == "status":
            embed = discord.Embed(
                title=f"🔥 Modo Liga VLS — {div}",
                description=(
                    f"🏆 **Divisão Atual:** Liga **{div}**\n\n"
                    f"📈 **Vitórias consecutivas:** `{wins}` de **{config['wins_needed'] or '—'}** para subir.\n"
                    f"📉 **Derrotas consecutivas:** `{losses}` de **{config['losses_cair'] or '—'}** para cair.\n\n"
                    f"💰 **Prêmio por vitória:** R$ {config['premio_vitoria']:,}\n"
                    f"🎮 **Nível da CPU:** OVR {config['ovr_min']} - {config['ovr_max']}\n\n"
                    f"Use `/liga jogar` para disputar a próxima rodada com seu time titular!"
                ),
                color=discord.Color.brand_green()
            )
            embed.set_footer(text="VLS Liga • Suba até o topo")
            return await interaction.followup.send(embed=embed)
            
        starting_xi = profile.get("starting_xi", [])
        if len(starting_xi) < 11:
            return await interaction.followup.send(
                "❌ Você precisa de **11 titulares escalados** no seu `/time` para disputar a liga.",
                ephemeral=True
            )
            
        cpu_names = {
            "Bronze": "Bronze United", "Prata": "Prata FC", "Ouro": "Real Ouro",
            "Esmeralda": "Esmeralda Athletic", "Diamante": "Diamante City",
            "Icone": "Icones F.C.", "Dev": "Devs F.C.", "VLS": "VLS All Stars"
        }
        cpu_name = cpu_names.get(div, "CPU Club")
        
        cpu_xi = []
        posicoes = ["GK", "CB", "CB", "LB", "RB", "CM", "CM", "CAM", "LW", "RW", "ST"]
        for idx, pos in enumerate(posicoes):
            ovr = random.randint(config["ovr_min"], config["ovr_max"])
            cpu_xi.append({
                "instance_id": f"cpu_{idx}",
                "name": f"CPU {pos} #{idx}",
                "pos": pos,
                "over": ovr,
                "pac": ovr, "sho": ovr, "pas": ovr, "dri": ovr, "def": ovr, "phy": ovr,
                "div": ovr, "han": ovr, "kic": ovr, "ref": ovr, "spd": ovr, "pos_stat": ovr,
                "col_nome": "Comum",
                "col_emoji": "⚪"
            })
            
        p1_chem = calculate_chemistry_bonus(starting_xi, profile.get("formation", "4-3-3"))
        cpu_chem = {p["instance_id"]: 0 for p in cpu_xi}
        
        sim_res = run_match_simulation(
            p1_name = profile.get("club_name", "Meu Clube"),
            p2_name = cpu_name,
            p1_xi = starting_xi,
            p2_xi = cpu_xi,
            p1_tactic = profile.get("tactic", "padrao"),
            p2_tactic = "padrao",
            p1_chem = p1_chem,
            p2_chem = cpu_chem,
            p1_formation = profile.get("formation", "4-3-3"),
            p2_formation = "4-3-3",
            p1_torcida_level = profile.get("torcida_level", 1),
            p2_torcida_level = 1,
        )
        
        gols_user = sim_res["p1_goals"]
        gols_cpu = sim_res["p2_goals"]
        
        resultado_txt = ""
        money_earned = 0
        
        if gols_user > gols_cpu:
            money_earned = config["premio_vitoria"]
            profile["money"] += money_earned
            wins += 1
            losses = 0
            
            subiu = False
            msg_subida = ""
            if config["wins_needed"] and wins >= config["wins_needed"]:
                proxima = config["proxima"]
                profile["liga_div"] = proxima
                profile["liga_wins"] = 0
                profile["liga_losses"] = 0
                subiu = True
                msg_subida = f"\n🎉 **UPGRADE DE DIVISÃO!** Você subiu para a **Liga {proxima}**!"
            else:
                profile["liga_wins"] = wins
                profile["liga_losses"] = 0
                
            resultado_txt = f"🟩 **Vitória!** R$ {money_earned:,} ganhos.\n📈 Sequência de vitórias: **{wins}/{config['wins_needed'] or '—'}**.{msg_subida}"
            
        elif gols_user == gols_cpu:
            money_earned = int(config["premio_vitoria"] * 0.30)
            profile["money"] += money_earned
            wins = 0
            losses = 0
            profile["liga_wins"] = 0
            profile["liga_losses"] = 0
            
            resultado_txt = f"🟨 **Empate!** R$ {money_earned:,} de consolação.\nSequências resetadas."
            
        else:
            money_earned = int(config["premio_vitoria"] * 0.10)
            profile["money"] += money_earned
            wins = 0
            losses += 1
            
            caiu = False
            msg_queda = ""
            if config["losses_cair"] and losses >= config["losses_cair"]:
                anterior = config["anterior"]
                profile["liga_div"] = anterior
                profile["liga_wins"] = 0
                profile["liga_losses"] = 0
                caiu = True
                msg_queda = f"\n📉 **REBAIXAMENTO!** Você caiu para a **Liga {anterior}**!"
            else:
                profile["liga_wins"] = 0
                profile["liga_losses"] = losses
                
            cair_info = f"({losses}/{config['losses_cair']})" if config["losses_cair"] else ""
            resultado_txt = f"🟥 **Derrota!** R$ {money_earned:,} de consolação.\n📉 Sequência de derrotas: **{losses}** {cair_info}.{msg_queda}"
            
        await save_user_profile(interaction.user.id, profile)
        
        await self.show_simulation_pages(
            interaction = interaction,
            p1_name     = profile.get("club_name", "Meu Clube"),
            p2_name     = cpu_name,
            sim_res     = sim_res,
            footer_msg  = resultado_txt
        )

    # ── MÓDULO 3: COPA RELÂMPAGO ──────────────────────────────────────────────

    @app_commands.command(name="copa", description="Abre inscrições para uma nova Copa Relâmpago de 8 vagas com prêmio de R$ 500k.")
    @lock_user()
    async def copa(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        doc_id = f"copa_{interaction.guild.id}"
        record = await db_get(doc_id)
        
        if record and record.get("status") in ["waiting", "running"]:
            return await interaction.followup.send("❌ Já existe uma copa ativa ou em andamento neste servidor.", ephemeral=True)
            
        champ = {
            "status": "waiting",
            "participants": [],
            "round": 1,
            "matches": []
        }
        await db_upsert(doc_id, champ)
        
        embed = discord.Embed(
            title="🏆 Copa Relâmpago VLS",
            description=f"Inscrições Abertas! Disputa mata-mata rápida por eliminatórias de 8 vagas.\n"
                        f"💰 **Prêmio do Campeão:** R$ **500.000,00**!\n\n"
                        f"📊 **Inscritos:** **0/8**\n\n"
                        f"Clique no botão verde abaixo para se inscrever grátis!",
            color=discord.Color.gold()
        )
        
        view = CopaParticipateView(interaction.guild.id, self)
        await interaction.followup.send(embed=embed, view=view)


# ==============================================================================
# VIEWS
# ==============================================================================

class ChallengeResponseView(discord.ui.View):
    """View para aceitar ou recusar um desafio PvP (amistoso ou apostado)."""

    def __init__(self, challenger: discord.User, target: discord.User, cog: MatchesCog, wager: int = 0):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.target     = target
        self.cog        = cog
        self.wager      = wager

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(content="⏳ O desafio expirou — nenhuma resposta foi dada.", view=self)
        except Exception:
            pass

    @discord.ui.button(label="Aceitar Desafio", style=discord.ButtonStyle.success, emoji="⚔️")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            return await interaction.response.send_message("❌ Apenas o usuário desafiado pode aceitar o confronto.", ephemeral=True)

        await interaction.response.defer()
        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)
        self.stop()

        p1_profile = await get_user_profile(self.challenger)
        p2_profile = await get_user_profile(self.target)

        # Re-validação de saldo (pode ter mudado desde o envio)
        if self.wager > 0:
            if p1_profile.get("money", 0) < self.wager:
                return await interaction.followup.send("❌ Desafio cancelado: o desafiador não possui saldo suficiente.")
            if p2_profile.get("money", 0) < self.wager:
                return await interaction.followup.send("❌ Desafio cancelado: saldo insuficiente para cobrir a aposta.")

            # Debita de ambos com lock para segurança
            async with get_user_lock(self.challenger.id):
                p1_fresh = await get_user_profile(self.challenger)
                if p1_fresh.get("money", 0) < self.wager:
                    return await interaction.followup.send("❌ Saldo do desafiador mudou. Desafio cancelado.")
                p1_fresh["money"] -= self.wager
                await save_user_profile(self.challenger.id, p1_fresh)

            async with get_user_lock(self.target.id):
                p2_fresh = await get_user_profile(self.target)
                if p2_fresh.get("money", 0) < self.wager:
                    # Devolve ao P1
                    async with get_user_lock(self.challenger.id):
                        p1_refund = await get_user_profile(self.challenger)
                        p1_refund["money"] += self.wager
                        await save_user_profile(self.challenger.id, p1_refund)
                    return await interaction.followup.send("❌ Saldo do adversário é insuficiente. Aposta cancelada e valores devolvidos.")
                p2_fresh["money"] -= self.wager
                await save_user_profile(self.target.id, p2_fresh)

            # Recarrega perfis frescos para a simulação
            p1_profile = await get_user_profile(self.challenger)
            p2_profile = await get_user_profile(self.target)

        p1_xi   = p1_profile.get("starting_xi", [])
        p2_xi   = p2_profile.get("starting_xi", [])
        p1_chem = calculate_chemistry_bonus(p1_xi, p1_profile.get("formation", "4-3-3"))
        p2_chem = calculate_chemistry_bonus(p2_xi, p2_profile.get("formation", "4-3-3"))

        sim_res = run_match_simulation(
            p1_name   = p1_profile.get("club_name", "Mandante"),
            p2_name   = p2_profile.get("club_name", "Visitante"),
            p1_xi     = p1_xi,
            p2_xi     = p2_xi,
            p1_tactic = p1_profile.get("tactic", "padrao"),
            p2_tactic = "padrao",
            p1_chem   = p1_chem,
            p2_chem   = p2_chem,
            p1_formation = p1_profile.get("formation", "4-3-3"),
            p2_formation = "4-3-3",
            p1_torcida_level = p1_profile.get("torcida_level", 1),
            p2_torcida_level = p2_profile.get("torcida_level", 1),
        )

        wager_msg = await self.cog.process_match_results(interaction, self.challenger, self.target, sim_res, self.wager)
        await self.cog.show_simulation_pages(
            interaction = interaction,
            p1_name     = p1_profile["club_name"],
            p2_name     = p2_profile["club_name"],
            sim_res     = sim_res,
            footer_msg  = wager_msg,
        )

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            return await interaction.response.send_message("❌ Apenas o usuário desafiado pode recusar.", ephemeral=True)

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content=f"❌ {self.target.mention} recusou o confronto. O desafio foi encerrado.",
            view=self,
        )
        self.stop()


class MatchReportView(discord.ui.View):
    """View com paginação para navegar pelos lances da partida e acessar o placar final."""

    def __init__(self, embeds: list, final_embed: discord.Embed):
        super().__init__(timeout=300)
        self.embeds       = embeds
        self.final_embed  = final_embed
        self.current_page = 0

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

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
        elif self.current_page == len(self.embeds) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.final_embed)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="🏁 Placar Final", style=discord.ButtonStyle.success)
    async def go_to_final(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = len(self.embeds)
        await interaction.response.edit_message(embed=self.final_embed)


# ══════════════════════════════════════════════════════════
# Dashboard Admin de Campeonatos
# ══════════════════════════════════════════════════════════

class CampeonatoAdminView(discord.ui.View):
    def __init__(self, owner_id: int, guild_id: int, cog, champ: dict | None):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.guild_id = guild_id
        self.cog = cog
        self.champ = champ
        self.canceling = False

    @discord.ui.button(label="🏃 Criar Campeonato", style=discord.ButtonStyle.success, row=0)
    async def criar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)

        doc_id = f"champ_{self.guild_id}"
        existing = await db_get(doc_id)
        if existing and existing["data"].get("status") in ("waiting", "active"):
            return await interaction.response.send_message(
                "❌ Já existe um campeonato ativo. Cancele-o primeiro.", ephemeral=True
            )

        await db_upsert(doc_id, {
            "id": doc_id,
            "participants": [],
            "status": "waiting",
            "matches": [],
            "round": 0,
            "bye_player": None,
        })

        # Envia mensagem pública com botão de participar
        embed = discord.Embed(
            title="🏆 Campeonato VLS Guru — Inscrições Abertas!",
            description=(
                "Um novo torneio foi aberto!\n\n"
                "📋 **Para participar:** Clique no botão abaixo.\n"
                "⚠️ Você precisa ter **11 titulares escalados** no `/time`."
            ),
            color=discord.Color.gold()
        )
        guild = interaction.client.get_guild(self.guild_id)
        channel = interaction.channel
        view = ParticipateView(self.guild_id)
        await channel.send(embed=embed, view=view)

        await interaction.response.send_message(
            "✅ **Campeonato criado!** A mensagem de inscrições foi enviada no canal.",
            ephemeral=True
        )

    @discord.ui.button(label="🗡️ Iniciar Rodadas", style=discord.ButtonStyle.primary, row=0)
    async def iniciar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)

        doc_id = f"champ_{self.guild_id}"
        record = await db_get(doc_id)
        if not record:
            return await interaction.response.send_message("❌ Nenhum campeonato criado.", ephemeral=True)

        champ = record["data"]
        if champ.get("status") != "waiting":
            return await interaction.response.send_message("❌ O campeonato não está na fase de inscrições.", ephemeral=True)
        if len(champ.get("participants", [])) < 2:
            return await interaction.response.send_message("❌ São necessários pelo menos 2 participantes.", ephemeral=True)

        participants = champ["participants"]
        random.shuffle(participants)

        bye_player = None
        if len(participants) % 2 != 0:
            bye_player = participants.pop()

        matches = [{"p1": participants[i], "p2": participants[i+1]} for i in range(0, len(participants), 2)]
        champ["status"] = "active"
        champ["round"] = 1
        champ["matches"] = matches
        champ["bye_player"] = bye_player
        await db_upsert(doc_id, champ)

        await interaction.response.send_message(
            f"⚔️ **Campeonato iniciado!** Rodada 1 com {len(matches)} confrontos gerada.\n"
            f"Use `/rodar_jogo` para simular os jogos desta rodada.",
            ephemeral=True
        )

    @discord.ui.button(label="⏭️ Rodar Jogo", style=discord.ButtonStyle.secondary, row=0)
    async def rodar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        # Delega ao comando /rodar_jogo via simulação interna
        await interaction.response.send_message(
            "▶️ Para rodar os jogos desta rodada, use o comando `/rodar_jogo` no canal.",
            ephemeral=True
        )

    @discord.ui.button(label="🗑️ Cancelar Campeonato", style=discord.ButtonStyle.danger, row=1)
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)

        if not self.canceling:
            self.canceling = True
            button.label = "⚠️ Confirmar Cancelamento"
            await interaction.response.edit_message(
                content="⚠️ **Tem certeza?** Clique novamente para confirmar o cancelamento definitivo.",
                view=self
            )
        else:
            doc_id = f"champ_{self.guild_id}"
            await db_delete(doc_id)
            button.label = "🗑️ Cancelar Campeonato"
            button.style = discord.ButtonStyle.danger
            self.canceling = False
            await interaction.response.edit_message(
                content="🗑️ **Campeonato cancelado.** Todos os dados foram removidos.",
                view=None
            )



    async def run_copa_simulation(self, channel, guild_id: int):
        doc_id = f"copa_{guild_id}"
        record = await db_get(doc_id)
        if not record:
            return
            
        participants = record["participants"]
        
        await channel.send("🏆 **A COPA RELÂMPAGO VLS COMEÇOU!** Gerando confrontos das **Quartas de Final**...")
        await asyncio.sleep(3.0)
        
        random.shuffle(participants)
        confrontos = [{"p1": participants[i], "p2": participants[i+1]} for i in range(0, 8, 2)]
        
        vencedores_quartas = []
        for idx, match in enumerate(confrontos, 1):
            p1_m = channel.guild.get_member(match["p1"])
            p2_m = channel.guild.get_member(match["p2"])
            
            if not p1_m:
                vencedores_quartas.append(match["p2"])
                await channel.send(f"⚠️ **W.O.:** {match['p1']} não encontrado. Vitória de {p2_m.mention if p2_m else match['p2']}!")
                continue
            if not p2_m:
                vencedores_quartas.append(match["p1"])
                await channel.send(f"⚠️ **W.O.:** {match['p2']} não encontrado. Vitória de {p1_m.mention if p1_m else match['p1']}!")
                continue
                
            p1_prof = await get_user_profile(p1_m)
            p2_prof = await get_user_profile(p2_m)
            
            await channel.send(f"⚡ **Jogo #{idx} — Quartas de Final:** **{p1_prof['club_name']}** vs **{p2_prof['club_name']}**")
            await asyncio.sleep(2.0)
            
            p1_chem = calculate_chemistry_bonus(p1_prof["starting_xi"], p1_prof.get("formation", "4-3-3"))
            p2_chem = calculate_chemistry_bonus(p2_prof["starting_xi"], p2_prof.get("formation", "4-3-3"))
            
            sim_res = run_match_simulation(
                p1_name = p1_prof["club_name"],
                p2_name = p2_prof["club_name"],
                p1_xi = p1_prof["starting_xi"],
                p2_xi = p2_prof["starting_xi"],
                p1_tactic = p1_prof.get("tactic", "padrao"),
                p2_tactic = p2_prof.get("tactic", "padrao"),
                p1_chem = p1_chem,
                p2_chem = p2_chem,
                p1_formation = p1_prof.get("formation", "4-3-3"),
                p2_formation = p2_prof.get("formation", "4-3-3"),
                p1_torcida_level = p1_prof.get("torcida_level", 1),
                p2_torcida_level = p2_prof.get("torcida_level", 1),
            )
            
            class MockInteraction:
                def __init__(self, ch):
                    self.channel = ch
                    self.followup = self
                async def send(self, *args, **kwargs):
                    return await self.channel.send(*args, **kwargs)
                    
            mock_inter = MockInteraction(channel)
            vencedor_id = match["p1"] if sim_res["p1_goals"] >= sim_res["p2_goals"] else match["p2"]
            vencedores_quartas.append(vencedor_id)
            
            venc_m = channel.guild.get_member(vencedor_id)
            await self.show_simulation_pages(
                interaction = mock_inter,
                p1_name     = p1_prof["club_name"],
                p2_name     = p2_prof["club_name"],
                sim_res     = sim_res,
                footer_msg  = f"🏆 **Fim de jogo!** {venc_m.mention if venc_m else 'Vencedor'} classificado para as semifinais!"
            )
            await asyncio.sleep(5.0)

        # Semifinal
        await channel.send("🏆 **Quartas de Final concluídas!** Gerando confrontos das **Semifinais**...")
        await asyncio.sleep(3.0)
        
        confrontos_semi = [{"p1": vencedores_quartas[i], "p2": vencedores_quartas[i+1]} for i in range(0, 4, 2)]
        vencedores_semi = []
        
        for idx, match in enumerate(confrontos_semi, 1):
            p1_m = channel.guild.get_member(match["p1"])
            p2_m = channel.guild.get_member(match["p2"])
            
            p1_prof = await get_user_profile(p1_m) if p1_m else {"club_name": "W.O."}
            p2_prof = await get_user_profile(p2_m) if p2_m else {"club_name": "W.O."}
            
            await channel.send(f"⚡ **Jogo #{idx} — Semifinal:** **{p1_prof['club_name']}** vs **{p2_prof['club_name']}**")
            await asyncio.sleep(2.0)
            
            p1_chem = calculate_chemistry_bonus(p1_prof.get("starting_xi", []), p1_prof.get("formation", "4-3-3"))
            p2_chem = calculate_chemistry_bonus(p2_prof.get("starting_xi", []), p2_prof.get("formation", "4-3-3"))
            
            sim_res = run_match_simulation(
                p1_name = p1_prof["club_name"],
                p2_name = p2_prof["club_name"],
                p1_xi = p1_prof.get("starting_xi", []),
                p2_xi = p2_prof.get("starting_xi", []),
                p1_tactic = p1_prof.get("tactic", "padrao"),
                p2_tactic = p2_prof.get("tactic", "padrao"),
                p1_chem = p1_chem,
                p2_chem = p2_chem,
                p1_formation = p1_prof.get("formation", "4-3-3"),
                p2_formation = p2_prof.get("formation", "4-3-3"),
                p1_torcida_level = p1_prof.get("torcida_level", 1),
                p2_torcida_level = p2_prof.get("torcida_level", 1),
            )
            
            class MockInteraction:
                def __init__(self, ch):
                    self.channel = ch
                    self.followup = self
                async def send(self, *args, **kwargs):
                    return await self.channel.send(*args, **kwargs)
                    
            mock_inter = MockInteraction(channel)
            vencedor_id = match["p1"] if sim_res["p1_goals"] >= sim_res["p2_goals"] else match["p2"]
            vencedores_semi.append(vencedor_id)
            
            venc_m = channel.guild.get_member(vencedor_id)
            await self.show_simulation_pages(
                interaction = mock_inter,
                p1_name     = p1_prof["club_name"],
                p2_name     = p2_prof["club_name"],
                sim_res     = sim_res,
                footer_msg  = f"🏆 **Fim de jogo!** {venc_m.mention if venc_m else 'Vencedor'} classificado para a Grande Final!"
            )
            await asyncio.sleep(5.0)

        # Final
        p1_final = channel.guild.get_member(vencedores_semi[0])
        p2_final = channel.guild.get_member(vencedores_semi[1])
        
        p1_prof = await get_user_profile(p1_final)
        p2_prof = await get_user_profile(p2_final)
        
        await channel.send(f"👑 **GRANDE FINAL DA COPA RELÂMPAGO!** 👑\n⚔️ **{p1_prof['club_name']}** vs **{p2_prof['club_name']}**\nA bola vai rolar!")
        await asyncio.sleep(3.0)
        
        p1_chem = calculate_chemistry_bonus(p1_prof["starting_xi"], p1_prof.get("formation", "4-3-3"))
        p2_chem = calculate_chemistry_bonus(p2_prof["starting_xi"], p2_prof.get("formation", "4-3-3"))
        
        sim_res = run_match_simulation(
            p1_name = p1_prof["club_name"],
            p2_name = p2_prof["club_name"],
            p1_xi = p1_prof["starting_xi"],
            p2_xi = p2_prof["starting_xi"],
            p1_tactic = p1_prof.get("tactic", "padrao"),
            p2_tactic = p2_prof.get("tactic", "padrao"),
            p1_chem = p1_chem,
            p2_chem = p2_chem,
            p1_formation = p1_prof.get("formation", "4-3-3"),
            p2_formation = p2_prof.get("formation", "4-3-3"),
            p1_torcida_level = p1_prof.get("torcida_level", 1),
            p2_torcida_level = p2_prof.get("torcida_level", 1),
        )
        
        campeon_id = vencedores_semi[0] if sim_res["p1_goals"] >= sim_res["p2_goals"] else vencedores_semi[1]
        campeao_m = channel.guild.get_member(campeon_id)
        
        p_camp = await get_user_profile(campeao_m)
        p_camp["money"] += 500_000
        await save_user_profile(campeon_id, p_camp)
        
        class MockInteraction:
            def __init__(self, ch):
                self.channel = ch
                self.followup = self
            async def send(self, *args, **kwargs):
                return await self.channel.send(*args, **kwargs)
                
        mock_inter = MockInteraction(channel)
        await self.show_simulation_pages(
            interaction = mock_inter,
            p1_name     = p1_prof["club_name"],
            p2_name     = p2_prof["club_name"],
            sim_res     = sim_res,
            footer_msg  = f"👑 **FIM DA COPA!** {campeao_m.mention} venceu a Copa Relâmpago e faturou **R$ 500.000,00**!"
        )
        
        record["status"] = "finished"
        await db_upsert(doc_id, record)


class CopaParticipateView(discord.ui.View):
    def __init__(self, guild_id: int, cog):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.cog = cog

    @discord.ui.button(label="⚽ Inscrever-se na Copa", style=discord.ButtonStyle.success, emoji="🏆", custom_id="copa_participar")
    @lock_user()
    async def participar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        doc_id = f"copa_{self.guild_id}"
        record = await db_get(doc_id)
        if not record:
            return await interaction.response.send_message("❌ Nenhuma copa ativa.", ephemeral=True)

        champ = record
        if champ.get("status") != "waiting":
            return await interaction.response.send_message("❌ As inscrições para a copa estão encerradas.", ephemeral=True)

        profile = await get_user_profile(interaction.user)
        if len(profile.get("starting_xi", [])) < 11:
            return await interaction.response.send_message(
                "❌ Você precisa de **11 titulares escalados** no `/time` para disputar a Copa.", ephemeral=True
            )

        if interaction.user.id in champ["participants"]:
            return await interaction.response.send_message("✅ Você já está inscrito nesta copa!", ephemeral=True)

        champ["participants"].append(interaction.user.id)
        
        if len(champ["participants"]) >= 8:
            champ["status"] = "running"
            await db_upsert(doc_id, champ)
            await interaction.response.send_message("✅ Inscrição confirmada! Você é o 8º jogador. A Copa vai começar!", ephemeral=True)
            asyncio.create_task(self.cog.run_copa_simulation(interaction.channel, self.guild_id))
        else:
            await db_upsert(doc_id, champ)
            await interaction.response.send_message(
                f"✅ Inscrito com sucesso! Total de inscritos: **{len(champ['participants'])}/8**",
                ephemeral=True
            )
            
            embed = discord.Embed(
                title="🏆 Copa Relâmpago VLS",
                description=f"Inscrições Abertas! Disputa mata-mata rápida por eliminatórias de 8 vagas.\n"
                            f"💰 **Prêmio do Campeão:** R$ **500.000,00**!\n\n"
                            f"📊 **Inscritos:** **{len(champ['participants'])}/8**\n\n"
                            f"Clique no botão verde abaixo para se inscrever grátis!",
                color=discord.Color.gold()
            )
            await interaction.message.edit(embed=embed)


# ══════════════════════════════════════════════════════════
# Botão "Participar" na Mensagem do Campeonato
# ══════════════════════════════════════════════════════════

class ParticipateView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=None)  # Persiste mesmo após reinício
        self.guild_id = guild_id

    @discord.ui.button(label="⚽ Participar do Torneio", style=discord.ButtonStyle.success, emoji="🏆", custom_id="participar_torneio")
    async def participar_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        doc_id = f"champ_{interaction.guild.id}"
        record = await db_get(doc_id)
        if not record:
            return await interaction.response.send_message("❌ Nenhum campeonato ativo.", ephemeral=True)

        champ = record["data"]
        if champ.get("status") != "waiting":
            return await interaction.response.send_message("❌ As inscrições estão encerradas.", ephemeral=True)

        profile = await get_user_profile(interaction.user)
        if len(profile.get("starting_xi", [])) < 11:
            return await interaction.response.send_message(
                "❌ Você precisa ter **11 titulares escalados** no `/time` para participar.", ephemeral=True
            )

        if interaction.user.id in champ["participants"]:
            return await interaction.response.send_message("✅ Você já está inscrito!", ephemeral=True)

        champ["participants"].append(interaction.user.id)
        await db_upsert(doc_id, champ)
        await interaction.response.send_message(
            f"✅ **{interaction.user.display_name}** foi inscrito no torneio!\n"
            f"Total de participantes: **{len(champ['participants'])}**",
            ephemeral=True
        )



class PenaltiTreinoView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.chutes_usuario = [] # lista de bool: True=Gol, False=Defesa/Errou
        self.chutes_cpu = []
        self.rodada = 1 # 1 a 5
        self.fase = "chutar" # "chutar" ou "defender"
        self.user_choice = None
        self.message = None

    def get_placar_status(self) -> str:
        def fmt(lst):
            return " ".join("🟢" if x else "🔴" for x in lst) + " ⚪" * (5 - len(lst))
        return f"👤 **Você:** {fmt(self.chutes_usuario)}\n🤖 **CPU:** {fmt(self.chutes_cpu)}"

    async def process_turn(self, interaction: discord.Interaction):
        cpu_choice = random.choice(["esquerda", "centro", "direita"])
        
        if self.fase == "chutar":
            if self.user_choice == cpu_choice:
                self.chutes_usuario.append(False)
                resultado_txt = f"❌ **Defesa do Goleiro!** Você chutou na **{self.user_choice}** e o goleiro pulou lá!"
            else:
                self.chutes_usuario.append(True)
                resultado_txt = f"⚽ **GOL!** Você chutou na **{self.user_choice}** e o goleiro pulou na **{cpu_choice}**!"
            
            self.fase = "defender"
            embed = discord.Embed(
                title=f"⚽ Disputa de Pênaltis — Rodada {self.rodada}/5 (Sua vez de defender)",
                description=f"{resultado_txt}\n\n{self.get_placar_status()}\n\n🤖 A CPU vai chutar! Escolha para qual lado o seu goleiro deve pular:",
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=self)
            
        else:
            if self.user_choice == cpu_choice:
                self.chutes_cpu.append(False)
                resultado_txt = f"🧤 **DEFENDEU!** A CPU chutou na **{cpu_choice}** e você pulou lá!"
            else:
                self.chutes_cpu.append(True)
                resultado_txt = f"❌ **Gol da CPU.** A CPU chutou na **{cpu_choice}** e você pulou na **{self.user_choice}**!"
                
            fim = False
            vencedor = None
            
            rem_user = 5 - len(self.chutes_usuario)
            rem_cpu = 5 - len(self.chutes_cpu)
            gols_user = sum(self.chutes_usuario)
            gols_cpu = sum(self.chutes_cpu)
            
            if gols_user > (gols_cpu + rem_cpu):
                fim = True
                vencedor = "usuario"
            elif gols_cpu > (gols_user + rem_user):
                fim = True
                vencedor = "cpu"
            elif len(self.chutes_usuario) >= 5 and len(self.chutes_cpu) >= 5:
                if gols_user == gols_cpu:
                    pass
                else:
                    fim = True
                    vencedor = "usuario" if gols_user > gols_cpu else "cpu"
                    
            if not fim and len(self.chutes_usuario) >= 5:
                if len(self.chutes_usuario) == len(self.chutes_cpu):
                    if gols_user != gols_cpu:
                        fim = True
                        vencedor = "usuario" if gols_user > gols_cpu else "cpu"
                    else:
                        self.rodada += 1
                else:
                    pass
            elif not fim and self.fase == "defender":
                self.rodada += 1
                self.fase = "chutar"
                
            if fim:
                for child in self.children:
                    child.disabled = True
                    
                if vencedor == "usuario":
                    profile = await get_user_profile(interaction.user)
                    profile["money"] += 5_000
                    await save_user_profile(interaction.user.id, profile)
                    fim_txt = "🏆 **Você venceu a disputa de pênaltis!** Ganhou **R$ 5.000** como recompensa."
                    color = discord.Color.green()
                else:
                    fim_txt = "💀 **A CPU venceu a disputa de pênaltis!** Mais sorte na próxima vez."
                    color = discord.Color.red()
                    
                embed = discord.Embed(
                    title="🏁 FIM DA DISPUTA DE PÊNALTIS",
                    description=f"{resultado_txt}\n\n{self.get_placar_status()}\n\n{fim_txt}",
                    color=color
                )
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                if self.fase == "chutar":
                    embed = discord.Embed(
                        title=f"⚽ Disputa de Pênaltis — Rodada {self.rodada}/5 (Sua vez de chutar)",
                        description=f"{resultado_txt}\n\n{self.get_placar_status()}\n\nEscolha para onde deseja chutar:",
                        color=discord.Color.blue()
                    )
                    await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Esquerda", style=discord.ButtonStyle.primary, emoji="⬅️")
    async def esq_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌", ephemeral=True)
        self.user_choice = "esquerda"
        await self.process_turn(interaction)

    @discord.ui.button(label="Centro", style=discord.ButtonStyle.secondary, emoji="⏺️")
    async def centro_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌", ephemeral=True)
        self.user_choice = "centro"
        await self.process_turn(interaction)

    @discord.ui.button(label="Direita", style=discord.ButtonStyle.primary, emoji="➡️")
    async def dir_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌", ephemeral=True)
        self.user_choice = "direita"
        await self.process_turn(interaction)


class PenaltiEscolhaView(discord.ui.View):
    def __init__(self, parent_view, role: str):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.role = role

    @discord.ui.button(label="Esquerda", style=discord.ButtonStyle.primary, emoji="⬅️")
    async def esq(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_choice(interaction, "esquerda")

    @discord.ui.button(label="Centro", style=discord.ButtonStyle.secondary, emoji="⏺️")
    async def cen(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_choice(interaction, "centro")

    @discord.ui.button(label="Direita", style=discord.ButtonStyle.primary, emoji="➡️")
    async def dir(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.save_choice(interaction, "direita")

    async def save_choice(self, interaction: discord.Interaction, side: str):
        if self.role == "atk":
            self.parent_view.choice_atk = side
        else:
            self.parent_view.choice_def = side
            
        await interaction.response.send_message(f"✅ Você escolheu o canto **{side}** em segredo!", ephemeral=True)
        await self.parent_view.check_choices(interaction)


class PenaltiPvPView(discord.ui.View):
    def __init__(self, cog, challenger: discord.Member, target: discord.Member, wager: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.challenger = challenger
        self.target = target
        self.wager = wager
        
        self.chutes_challenger = []
        self.chutes_target = []
        self.rodada = 1
        
        self.atk_player = challenger
        self.def_player = target
        
        self.choice_atk = None
        self.choice_def = None
        
        self.message = None

    def get_placar_status(self) -> str:
        def fmt(lst):
            return " ".join("🟢" if x else "🔴" for x in lst) + " ⚪" * (5 - len(lst))
        return (
            f"👤 **{self.challenger.display_name}:** {fmt(self.chutes_challenger)}\n"
            f"👤 **{self.target.display_name}:** {fmt(self.chutes_target)}"
        )

    @discord.ui.button(label="Chutar (Atacante)", style=discord.ButtonStyle.danger, emoji="⚽")
    async def btn_chutar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.atk_player.id:
            return await interaction.response.send_message("❌ Você não é o cobrador desta rodada!", ephemeral=True)
        if self.choice_atk is not None:
            return await interaction.response.send_message("❌ Você já fez sua escolha de chute!", ephemeral=True)
            
        view = PenaltiEscolhaView(self, "atk")
        await interaction.response.send_message("🎯 Escolha o canto do seu chute:", view=view, ephemeral=True)

    @discord.ui.button(label="Defender (Goleiro)", style=discord.ButtonStyle.primary, emoji="🧤")
    async def btn_defender(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.def_player.id:
            return await interaction.response.send_message("❌ Você não é o goleiro desta rodada!", ephemeral=True)
        if self.choice_def is not None:
            return await interaction.response.send_message("❌ Você já escolheu o lado do salto!", ephemeral=True)
            
        view = PenaltiEscolhaView(self, "def")
        await interaction.response.send_message("🧤 Escolha para onde o seu goleiro vai pular:", view=view, ephemeral=True)

    async def check_choices(self, interaction: discord.Interaction):
        status_txt = ""
        if self.choice_atk:
            status_txt += f"✅ **{self.atk_player.display_name}** já preparou o chute.\n"
        if self.choice_def:
            status_txt += f"✅ **{self.def_player.display_name}** já preparou a defesa.\n"
            
        if self.choice_atk is None or self.choice_def is None:
            embed = discord.Embed(
                title=f"⚽ Pênaltis PvP — Rodada {self.rodada}/5",
                description=f"{self.get_placar_status()}\n\n"
                            f"**Cobrador:** {self.atk_player.mention}\n"
                            f"**Goleiro:** {self.def_player.mention}\n\n"
                            f"{status_txt}\n*Clique nos botões abaixo para definir sua jogada em segredo!*",
                color=discord.Color.orange()
            )
            await self.message.edit(embed=embed)
            return

        is_gol = self.choice_atk != self.choice_def
        
        if self.atk_player.id == self.challenger.id:
            self.chutes_challenger.append(is_gol)
        else:
            self.chutes_target.append(is_gol)
            
        if is_gol:
            res_txt = f"⚽ **GOL!** **{self.atk_player.display_name}** chutou na **{self.choice_atk}** e superou **{self.def_player.display_name}** que pulou na **{self.choice_def}**!"
        else:
            res_txt = f"🧤 **DEFENDEU!** **{self.def_player.display_name}** saltou na **{self.choice_def}** e pegou o chute de **{self.atk_player.display_name}**!"
            
        self.choice_atk = None
        self.choice_def = None
        
        if self.atk_player.id == self.challenger.id:
            self.atk_player = self.target
            self.def_player = self.challenger
        else:
            self.atk_player = self.challenger
            self.def_player = self.target
            
        fim = False
        vencedor = None
        
        rem_p1 = 5 - len(self.chutes_challenger)
        rem_p2 = 5 - len(self.chutes_target)
        gols_p1 = sum(self.chutes_challenger)
        gols_p2 = sum(self.chutes_target)
        
        if gols_p1 > (gols_p2 + rem_p2):
            fim = True
            vencedor = self.challenger
        elif gols_p2 > (gols_p1 + rem_p1):
            fim = True
            vencedor = self.target
        elif len(self.chutes_challenger) >= 5 and len(self.chutes_target) >= 5:
            if gols_p1 == gols_p2:
                pass
            else:
                fim = True
                vencedor = self.challenger if gols_p1 > gols_p2 else self.target
                
        if not fim and len(self.chutes_challenger) >= 5:
            if len(self.chutes_challenger) == len(self.chutes_target):
                if gols_p1 != gols_p2:
                    fim = True
                    vencedor = self.challenger if gols_p1 > gols_p2 else self.target
                else:
                    self.rodada += 1
            else:
                pass
        elif not fim and self.atk_player.id == self.challenger.id:
            self.rodada += 1
            
        if fim:
            for child in self.children:
                child.disabled = True
                
            perdedor = self.target if vencedor.id == self.challenger.id else self.challenger
            
            if self.wager > 0:
                p_venc = await get_user_profile(vencedor)
                p_perd = await get_user_profile(perdedor)
                
                p_venc["money"] += self.wager
                p_perd["money"] -= self.wager
                
                await save_user_profile(vencedor.id, p_venc)
                await save_user_profile(perdedor.id, p_perd)
                
                wager_txt = f"\n💰 **Aposta Resolvida:** **{vencedor.display_name}** recebeu **R$ {self.wager:,}** de **{perdedor.display_name}**!"
            else:
                wager_txt = ""
                
            embed = discord.Embed(
                title="🏁 FIM DA DISPUTA DE PÊNALTIS PVP",
                description=f"{res_txt}\n\n{self.get_placar_status()}\n\n🏆 **{vencedor.mention} é o CAMPEÃO da disputa!**{wager_txt}",
                color=discord.Color.green()
            )
            await self.message.edit(embed=embed, view=self)
        else:
            embed = discord.Embed(
                title=f"⚽ Pênaltis PvP — Rodada {self.rodada}/5",
                description=f"{res_txt}\n\n{self.get_placar_status()}\n\n"
                            f"**Cobrador:** {self.atk_player.mention}\n"
                            f"**Goleiro:** {self.def_player.mention}\n\n"
                            f"*Clique nos botões abaixo para definir sua jogada em segredo!*",
                color=discord.Color.orange()
            )
            await self.message.edit(embed=embed, view=self)


class PenaltiAceitarView(discord.ui.View):
    def __init__(self, cog, challenger: discord.Member, target: discord.Member, wager: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.challenger = challenger
        self.target = target
        self.wager = wager

    @discord.ui.button(label="Aceitar Desafio", style=discord.ButtonStyle.success, emoji="⚽")
    @lock_user()
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            return await interaction.response.send_message("❌ Apenas o desafiado pode aceitar o desafio.", ephemeral=True)
            
        await interaction.response.defer()
        
        if self.wager > 0:
            p1 = await get_user_profile(self.challenger)
            p2 = await get_user_profile(self.target)
            
            if p1.get("money", 0) < self.wager:
                return await interaction.followup.send(f"❌ Desafio cancelado. O desafiante {self.challenger.mention} não possui mais o valor da aposta (R$ {self.wager:,}).", ephemeral=True)
            if p2.get("money", 0) < self.wager:
                return await interaction.followup.send(f"❌ Você não possui saldo de R$ {self.wager:,} para aceitar a aposta.", ephemeral=True)

        for child in self.children:
            child.disabled = True
            
        embed = discord.Embed(
            title=f"⚽ Pênaltis PvP — Rodada 1/5",
            description=f"👤 **{self.challenger.display_name}:** ⚪ ⚪ ⚪ ⚪ ⚪\n"
                        f"👤 **{self.target.display_name}:** ⚪ ⚪ ⚪ ⚪ ⚪\n\n"
                        f"**Cobrador:** {self.challenger.mention}\n"
                        f"**Goleiro:** {self.target.mention}\n\n"
                        f"*Clique nos botões abaixo para definir sua jogada em segredo!*",
            color=discord.Color.orange()
        )
        
        view = PenaltiPvPView(self.cog, self.challenger, self.target, self.wager)
        view.message = await interaction.edit_original_response(content="🏁 **Disputa de Pênaltis Iniciada!**", embed=embed, view=view)

    @discord.ui.button(label="Recusar", style=discord.ButtonStyle.danger, emoji="❌")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.id:
            return await interaction.response.send_message("❌", ephemeral=True)
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=f"❌ {self.target.mention} recusou o desafio de pênaltis.", embed=None, view=self)


# ── CLASSES AUXILIARES PARA O DRAFT MODO 7-0 ──────────────────────────────────

class DraftDropdown(discord.ui.Select):
    def __init__(self, options_list: list):
        select_options = []
        for idx, p in enumerate(options_list):
            emoji = p.get("col_emoji", "✨")
            label = f"{p['name']} (OVR {p['over']} | {p['pos']})"
            select_options.append(discord.SelectOption(
                label=label[:100],
                value=str(idx),
                description=f"Coleção: {p.get('col_nome', 'Comum')}",
                emoji=emoji if not emoji.startswith("<") else None
            ))
        super().__init__(placeholder="Selecione um jogador para sua equipe...", options=select_options)

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("❌ Você não está comandando este draft.", ephemeral=True)
            
        selected_idx = int(self.values[0])
        chosen_player = view.current_options[selected_idx]
        
        # Determina a classe de posições e os slots compatíveis
        p_class = get_position_class(chosen_player.get("pos", "CM"))
        class_slots = {
            "GK": ["GK"],
            "DEF": ["CB1", "CB2", "LB", "RB"],
            "MID": ["CDM", "CM1", "CM2"],
            "ATK": ["LW", "RW", "ST"]
        }
        
        target_slots = class_slots.get(p_class, ["CM1", "CM2"])
        empty_slot = None
        for slot in target_slots:
            if view.filled_slots[slot] is None:
                empty_slot = slot
                break
                
        # Se a posição natural estiver cheia, checa se o jogador está completamente travado
        if not empty_slot:
            all_empty_slots = [s for s in view.slots if view.filled_slots[s] is None]
            
            # Checa se todas as 3 opções disponíveis na rodada pertencem a posições que já estão cheias
            all_options_full = True
            for opt in view.current_options:
                opt_class = get_position_class(opt.get("pos", "CM"))
                opt_slots = class_slots.get(opt_class, ["CM1", "CM2"])
                if any(view.filled_slots[s] is None for s in opt_slots):
                    all_options_full = False
                    break
            
            # Se todas as opções estão cheias e ele não tem mais rerolls, permite colocar em qualquer vaga vazia
            if all_options_full and view.rerolls_left <= 0:
                if all_empty_slots:
                    empty_slot = all_empty_slots[0]
                    
        if not empty_slot:
            p_class_name = {"GK": "Goleiro", "DEF": "Defensor", "MID": "Meio-campista", "ATK": "Atacante"}.get(p_class, "Meio-campista")
            return await interaction.response.send_message(
                f"❌ Todas as vagas para a categoria **{p_class_name}** ({chosen_player.get('pos')}) já estão preenchidas!\n"
                "Escolha outro jogador das 3 opções ou use Reroll.",
                ephemeral=True
            )
            
        await interaction.response.defer()
        
        instanced = chosen_player.copy()
        instanced["original_pos"] = chosen_player.get("pos", "CM")
        instanced["pos"] = empty_slot
        instanced["instance_id"] = f"draft_{empty_slot}"
        
        view.filled_slots[empty_slot] = instanced
        
        # Mantém drafted_team atualizado
        view.drafted_team = [view.filled_slots[s] for s in view.slots if view.filled_slots[s] is not None]
        
        empty_count = sum(1 for s in view.slots if view.filled_slots[s] is None)
        if empty_count == 0:
            await view.finish_draft(interaction)
        else:
            await view.roll_options()
            await view.update_message(interaction)


class RerollButton(discord.ui.Button):
    def __init__(self, rerolls_left: int):
        super().__init__(
            label=f"Reroll ({rerolls_left} restantes)",
            style=discord.ButtonStyle.secondary,
            disabled=(rerolls_left <= 0),
            emoji="🔄"
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        view = self.view
        if interaction.user.id != view.user_id:
            return await interaction.followup.send("❌ Você não está comandando este draft.", ephemeral=True)
            
        if view.rerolls_left <= 0:
            return await interaction.followup.send("❌ Você não possui mais rerolls.", ephemeral=True)
            
        view.rerolls_left -= 1
        await view.roll_options()
        await view.update_message(interaction)


class DraftView(discord.ui.View):
    def __init__(self, user_id: int, players_pool: list, cog: MatchesCog):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.players_pool = players_pool
        self.cog = cog
        
        self.slots = ["GK", "CB1", "CB2", "LB", "RB", "CDM", "CM1", "CM2", "LW", "RW", "ST"]
        self.filled_slots = {slot: None for slot in self.slots}
        self.drafted_team = []
        self.rerolls_left = 2
        self.current_options = []
        self.message = None

    async def roll_options(self):
        self.current_options = random.sample(self.players_pool, min(3, len(self.players_pool)))

    async def update_message(self, interaction: discord.Interaction):
        self.clear_items()
        self.add_item(DraftDropdown(self.current_options))
        self.add_item(RerollButton(self.rerolls_left))
        
        drafted_str = ""
        for slot in self.slots:
            p = self.filled_slots[slot]
            if p:
                emoji = p.get("col_emoji", "✨")
                drafted_str += f"🔹 `[{slot}]` {emoji} **{p['over']}** {p['original_pos']} - *{p['name']}*\n"
            else:
                drafted_str += f"🔸 `[{slot}]` *Vazio*\n"
                
        drafted_count = sum(1 for s in self.slots if self.filled_slots[s] is not None)
        embed = discord.Embed(
            title="🎮 MODO 7-0 — Draft de Elenco",
            description=(
                f"Monte sua equipe de 11 jogadores e enfrente 7 adversários!\n\n"
                f"**Rerolls Restantes:** 🔄 {self.rerolls_left}\n\n"
                f"**Time Escalado ({drafted_count}/11):**\n"
                f"{drafted_str}"
            ),
            color=discord.Color.purple()
        )
        embed.set_footer(text="VLS Arena • Draft interactivo")
        await interaction.edit_original_response(embed=embed, view=self)

    async def finish_draft(self, interaction: discord.Interaction):
        self.clear_items()
        
        embed_loading = discord.Embed(
            title="🎮 MODO 7-0 — Iniciando Simulações",
            description="⏱️ **Aguarde...** O bot está simulando as 7 partidas contra os times da CPU!",
            color=discord.Color.gold()
        )
        await interaction.edit_original_response(embed=embed_loading, view=None)
        
        wins = 0
        draws = 0
        losses = 0
        games_log = []
        
        draft_ovrs = [p.get("over", 70) for p in self.drafted_team]
        avg_ovr = int(sum(draft_ovrs) / 11)
        
        p1_chem = calculate_chemistry_bonus(self.drafted_team, "4-3-3")
        
        for game_idx in range(1, 8):
            cpu_positions = ["GK", "CB", "CB", "LB", "RB", "CDM", "CM", "CM", "LW", "RW", "ST"]
            cpu_xi = []
            
            pool = self.players_pool * 3
            random.shuffle(pool)
            used_ids = set()
            
            for i, pos_s in enumerate(cpu_positions):
                candidates = [p for p in pool if p.get("id") not in used_ids]
                if candidates:
                    base_player = random.choice(candidates[:15])
                    used_ids.add(base_player.get("id"))
                else:
                    base_player = random.choice(pool)
                
                cpu_ovr = max(50, min(99, avg_ovr + random.randint(-4, 4)))
                base_stat = max(50, cpu_ovr - 5)
                
                cpu_xi.append({
                    "instance_id": f"cpu_{i}",
                    "name": f"CPU {base_player.get('name', 'Jogador')[:12]}",
                    "over": cpu_ovr,
                    "pos": pos_s,
                    "shoot":    base_player.get("shoot", base_stat),
                    "pass_stat":base_player.get("pass_stat", base_stat),
                    "dribble":  base_player.get("dribble", base_stat),
                    "defense":  base_player.get("defense", base_stat),
                    "physical": base_player.get("physical", base_stat),
                    "weak_foot":   base_player.get("weak_foot", 3),
                    "skill_moves": base_player.get("skill_moves", 2),
                    "playstyles":  [],
                    "nationality": "CPU",
                    "club":        "CPU FC",
                    "xp":          0,
                })
                
            cpu_chem = {p["instance_id"]: 0 for p in cpu_xi}
            
            sim_res = run_match_simulation(
                p1_name = "Draft Team",
                p2_name = f"CPU Adversário #{game_idx}",
                p1_xi = self.drafted_team,
                p2_xi = cpu_xi,
                p1_tactic = "padrao",
                p2_tactic = "padrao",
                p1_chem = p1_chem,
                p2_chem = cpu_chem,
                p1_formation = "4-3-3",
                p2_formation = "4-3-3",
                p1_torcida_level = 1,
                p2_torcida_level = 1,
            )
            
            g_user = sim_res["p1_goals"]
            g_cpu = sim_res["p2_goals"]
            
            if g_user > g_cpu:
                wins += 1
                result_emoji = "✅ Vitória"
            elif g_user == g_cpu:
                draws += 1
                result_emoji = "⚪ Empate"
            else:
                losses += 1
                result_emoji = "❌ Derrota"
                
            games_log.append(f"🎮 **Jogo #{game_idx}:** Draft Team **{g_user}** x **{g_cpu}** {sim_res['p2_name']} — {result_emoji}")
            
        money_prize = 0
        coins_prize = 0
        drawn_card = None
        
        if wins == 0:
            money_prize = 5_000
        elif wins == 1:
            money_prize = 12_000
        elif wins == 2:
            money_prize = 25_000
        elif wins == 3:
            money_prize = 45_000
        elif wins == 4:
            money_prize = 75_000
        elif wins == 5:
            money_prize = 120_000
            coins_prize = 10
        elif wins == 6:
            money_prize = 200_000
            coins_prize = 25
        elif wins == 7:
            money_prize = 400_000
            coins_prize = 70
        profile = await get_user_profile(interaction.user)
        profile["money"] = profile.get("money", 0) + money_prize
        profile["premium_coins"] = profile.get("premium_coins", 0) + coins_prize
        
        await save_user_profile(interaction.user.id, profile)
        
        embed_final = discord.Embed(
            title="🏆 FIM DO MODO 7-0!",
            description=(
                f"Manager: {interaction.user.mention}\n"
                f"Campanha: **{wins} Vitórias / {draws} Empates / {losses} Derrotas**\n\n"
                f"**Resultado dos confrontos:**\n" + "\n".join(games_log) + "\n\n"
                f"🎁 **Premiação Recebida:**\n"
                f"💵 R$ {money_prize:,}\n"
                f"🪙 {coins_prize} VLS Coins"
            ),
            color=discord.Color.green()
        )
        embed_final.set_footer(text="Parabéns pela participação no 7-0! Volte amanhã!")
        await interaction.edit_original_response(embed=embed_final, view=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchesCog(bot))

