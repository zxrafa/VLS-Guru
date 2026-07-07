# -*- coding: utf-8 -*-
"""
VLS Guru - Cog Administrativa (Simplificada)
Mantém apenas comandos administrativos que não estão presentes no /admin (Dashboard).
"""
import discord
from discord.ext import commands
from discord import app_commands
import uuid
from datetime import datetime

from database import (
    db_get, db_upsert, db_delete, get_all_players,
    get_user_profile, save_user_profile, db_clear_all
)
from config import VLS_COINS_EMOJI, ALLOWED_ADMIN_IDS

class AdminCog(commands.Cog, name="Admin"):
    def __init__(self, bot):
        self.bot = bot

    # Helper de checagem para permissão de administrador
    def is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.administrator or interaction.user.id in ALLOWED_ADMIN_IDS

    @app_commands.command(name="liberar_tudo", description="[Admin] Adiciona todos os jogadores do catálogo global ao elenco do membro selecionado.")
    @app_commands.describe(usuario="Membro que receberá todas as cartas do catálogo")
    async def liberar_tudo(self, interaction: discord.Interaction, usuario: discord.Member):
        if not self.is_admin(interaction):
            return await interaction.response.send_message("❌ Acesso negado. Apenas administradores podem utilizar este comando.", ephemeral=True)

        await interaction.response.defer()

        players_data = await get_all_players()
        if not players_data:
            return await interaction.followup.send("❌ Nenhum jogador cadastrado no banco global.")

        profile = await get_user_profile(usuario)
        inventory = profile.setdefault("inventory", [])

        existing_keys = {
            (p.get("id"), p.get("col_id")) for p in inventory if p.get("id") and p.get("col_id")
        }

        added_count = 0
        now_str = datetime.utcnow().isoformat()
        for p in players_data:
            key = (p.get("id"), p.get("col_id"))
            if key not in existing_keys:
                instanced = p.copy()
                instanced["instance_id"] = str(uuid.uuid4())[:8]
                instanced["original_pos"] = p.get("pos")
                instanced["acquired_at"] = now_str
                instanced["goals"] = 0
                instanced["assists"] = 0
                instanced["saves"] = 0
                instanced["matches"] = 0
                instanced["mvps"] = 0
                instanced["yellow_cards"] = 0
                instanced["red_cards"] = 0
                
                inventory.append(instanced)
                added_count += 1

        await save_user_profile(usuario.id, profile)

        await interaction.followup.send(
            f"🎁 **Sucesso!** Todos os jogadores do catálogo global foram liberados para {usuario.mention}.\n"
            f"📥 **Novos adicionados:** {added_count}\n"
            f"📋 **Total no elenco:** {len(inventory)} jogadores."
        )

    @app_commands.command(name="resetar_tudo", description="[Admin] Zera todos os dados de usuários e tabelas.")
    async def resetar_tudo(self, interaction: discord.Interaction):
        if not self.is_admin(interaction):
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)

        view = ConfirmResetView(interaction.user.id)
        await interaction.response.send_message(
            "🚨 **ATENÇÃO!** Você está prestes a apagar todos os perfis de usuários, coleções e cartas do banco. Esta ação é **IRREVERSÍVEL**. Confirma?",
            view=view
        )

class ConfirmResetView(discord.ui.View):
    def __init__(self, owner_id):
        super().__init__(timeout=60)
        self.owner_id = owner_id

    @discord.ui.button(label="Apagar Tudo", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Apenas quem disparou o comando pode interagir.", ephemeral=True)

        try:
            count = await db_clear_all()
            await interaction.response.send_message(f"🚨 **Sistema Resetado!** Todos os {count} registros do banco de dados foram removidos com sucesso.")
        except Exception as e:
            await interaction.response.send_message(f"❌ Erro ao apagar registros: {e}")
        self.stop()

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Apenas quem disparou o comando pode interagir.", ephemeral=True)

        await interaction.response.send_message("❌ Operação cancelada com segurança.")
        self.stop()

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
