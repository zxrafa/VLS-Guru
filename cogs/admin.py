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
from config import VLS_COINS_EMOJI, ALLOWED_ADMIN_IDS, POSITIONS_ALL

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

    @app_commands.command(name="importar_txt", description="[Admin] Importa jogadores em massa a partir de um arquivo TXT.")
    @app_commands.describe(arquivo="O arquivo .txt contendo os jogadores (um por linha)")
    async def importar_txt(self, interaction: discord.Interaction, arquivo: discord.Attachment):
        if not self.is_admin(interaction):
            return await interaction.response.send_message("❌ Acesso negado. Apenas administradores podem utilizar este comando.", ephemeral=True)

        if not arquivo.filename.endswith(".txt"):
            return await interaction.response.send_message("❌ O arquivo enviado deve ser no formato `.txt`.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        try:
            content_bytes = await arquivo.read()
            content = content_bytes.decode("utf-8")
        except Exception as e:
            return await interaction.followup.send(f"❌ Erro ao ler o arquivo: {e}", ephemeral=True)

        linhas = content.splitlines()
        importados = 0
        erros = []
        
        # Cache local de coleções
        colecoes_dict = {}
        
        import re
        import unicodedata
        
        for idx, linha in enumerate(linhas, 1):
            linha_strip = linha.strip()
            if not linha_strip or linha_strip.startswith("#"):
                continue
                
            partes = [p.strip() for p in linha_strip.split("|")]
            if len(partes) < 6:
                erros.append(f"Linha {idx}: Formato incompleto. Deve ter: 'Nome | Overall | Posição | Coleção | Nacionalidade | Clube'")
                continue
                
            nome = partes[0]
            
            try:
                overall = int(partes[1])
            except ValueError:
                erros.append(f"Linha {idx} ({nome}): Overall inválido '{partes[1]}'. Deve ser número.")
                continue
                
            posicao = partes[2].upper()
            if posicao not in POSITIONS_ALL:
                erros.append(f"Linha {idx} ({nome}): Posição inválida '{posicao}'. Válidas: {', '.join(POSITIONS_ALL)}")
                continue
                
            col_id_raw = partes[3].lower()
            col_doc = f"col_{col_id_raw}"
            
            if col_doc not in colecoes_dict:
                col_record = await db_get(col_doc)
                if col_record:
                    colecoes_dict[col_doc] = col_record
                else:
                    colecoes_dict[col_doc] = None
                    
            col_record = colecoes_dict[col_doc]
            if not col_record:
                erros.append(f"Linha {idx} ({nome}): Coleção '{col_id_raw}' não cadastrada.")
                continue
                
            nacionalidade = partes[4]
            clube = partes[5]
            
            card_url = ""
            if len(partes) >= 7 and partes[6].startswith("http"):
                card_url = partes[6]
                
            # Gera slug do ID
            nome_normalizado = unicodedata.normalize('NFKD', nome).encode('ASCII', 'ignore').decode('ASCII')
            nome_normalizado = nome_normalizado.lower()
            nome_normalizado = re.sub(r'[^a-z0-9\s-]', '', nome_normalizado)
            slug_id = re.sub(r'[\s-]+', '_', nome_normalizado).strip('_')
            
            if not slug_id:
                erros.append(f"Linha {idx} ({nome}): Nome inválido para geração de ID.")
                continue
                
            # Resolve ID duplicado
            final_id = slug_id
            suffix = 2
            while True:
                doc_id = f"player_{final_id}"
                existing = await db_get(doc_id)
                if not existing:
                    break
                final_id = f"{slug_id}_{suffix}"
                suffix += 1
                
            is_gk = posicao == "GK"
            player_data = {
                "id": final_id,
                "name": nome,
                "over": overall,
                "pos": posicao,
                "col_id": col_record["data"]["id"],
                "col_nome": col_record["data"]["nome"],
                "col_emoji": col_record["data"]["emoji"],
                "max_playstyles": col_record["data"].get("max_playstyles", 0),
                "card": card_url,
                "xp": 0,
                "weak_foot": 3,
                "skill_moves": 3,
                "nationality": nacionalidade,
                "club": clube,
                "playstyles": []
            }
            
            if is_gk:
                player_data.update({
                    "div": overall - 2 if overall > 2 else 1,
                    "han": overall - 3 if overall > 3 else 1,
                    "kic": overall - 5 if overall > 5 else 1,
                    "ref": overall,
                    "spd": overall - 10 if overall > 10 else 1,
                    "pos_stat": overall - 1 if overall > 1 else 1,
                    "shoot": overall - 5 if overall > 5 else 1,
                    "pass_stat": overall - 3 if overall > 3 else 1,
                    "dribble": overall,
                    "defense": overall - 2 if overall > 2 else 1,
                    "physical": overall - 1 if overall > 1 else 1
                })
            else:
                player_data.update({
                    "pac": overall - 2 if overall > 2 else 1,
                    "sho": overall - 4 if overall > 4 else 1,
                    "pas": overall - 3 if overall > 3 else 1,
                    "dri": overall - 1 if overall > 1 else 1,
                    "def": overall - 15 if overall > 15 else 1,
                    "phy": overall - 5 if overall > 5 else 1,
                    "shoot": overall - 4 if overall > 4 else 1,
                    "pass_stat": overall - 3 if overall > 3 else 1,
                    "dribble": overall - 1 if overall > 1 else 1,
                    "defense": overall - 15 if overall > 15 else 1,
                    "physical": overall - 5 if overall > 5 else 1
                })
                
            await db_upsert(f"player_{final_id}", player_data)
            importados += 1
            
        msg = f"✅ **Importação concluída!**\n📥 Jogadores importados com sucesso: **{importados}**"
        if erros:
            msg += f"\n\n⚠️ **Erros encontrados ({len(erros)}):**\n" + "\n".join(erros[:15])
            if len(erros) > 15:
                msg += f"\n...e mais {len(erros) - 15} erros."
                
        await interaction.followup.send(msg, ephemeral=True)

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
