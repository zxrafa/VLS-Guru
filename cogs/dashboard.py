# -*- coding: utf-8 -*-
"""
VLS Guru - Cog de Dashboard Administrativo
Painel centralizado para gerenciar Jogadores, Coleções, Missões, Economia e Usuários.
Todos os fluxos via Discord UI (botões, selects, modals).
"""
import discord
from discord.ext import commands
from discord import app_commands
import uuid
from datetime import datetime

from database import (
    db_get, db_upsert, db_delete, get_all_collections,
    get_all_players, get_user_profile, save_user_profile,
    db_get_prefix, get_missions, get_all_users
)
from config import PLAYSTYLE_EMOJIS, POSITIONS_ALL, VLS_COINS_EMOJI, ALLOWED_ADMIN_IDS
# Removido gerador automático de cartas
import asyncio

# Armazena dados parciais entre steps de modals (em memória)
_PENDING_PLAYER: dict = {}  # user_id -> partial data


# Views auxiliares para transicionar entre Modais em cadeia de forma compatível com a API do Discord

class ContinuarJogador2View(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="▶️ Ir para Etapa 2/3 (Atributos)", style=discord.ButtonStyle.primary)
    async def continuar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        
        pending = _PENDING_PLAYER.get(interaction.user.id)
        if not pending:
            return await interaction.response.send_message("❌ Sessão expirada. Comece novamente.", ephemeral=True)
        
        is_gk = pending.get("pos") == "GK"
        if is_gk:
            await interaction.response.send_modal(CriarGoleiroModal2())
        else:
            await interaction.response.send_modal(CriarJogadorModal2())


class ContinuarJogador3View(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="▶️ Ir para Etapa 3/3 (Extras)", style=discord.ButtonStyle.primary)
    async def continuar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        
        pending = _PENDING_PLAYER.get(interaction.user.id)
        if not pending:
            return await interaction.response.send_message("❌ Sessão expirada. Comece novamente.", ephemeral=True)
        
        is_gk = pending.get("pos") == "GK"
        if is_gk:
            await interaction.response.send_modal(CriarGoleiroModal3())
        else:
            await interaction.response.send_modal(CriarJogadorModal3())


class ContinuarMissao2View(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="🎁 Definir Recompensa (Etapa 2/2)", style=discord.ButtonStyle.primary)
    async def continuar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(CriarMissaoModal2())


def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.guild_permissions.administrator or interaction.user.id in ALLOWED_ADMIN_IDS


# ══════════════════════════════════════════════════════════
# MAIN DASHBOARD VIEW
# ══════════════════════════════════════════════════════════

class DashboardCog(commands.Cog, name="Dashboard"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="admin", description="[Admin] Painel administrativo centralizado do VLS Guru.")
    async def admin_panel(self, interaction: discord.Interaction):
        if not is_admin(interaction):
            return await interaction.response.send_message("❌ Acesso negado. Apenas administradores.", ephemeral=True)

        embed = discord.Embed(
            title="⚙️ Painel Administrativo — VLS Guru",
            description=(
                "Bem-vindo ao painel centralizado.\n"
                "Selecione uma categoria abaixo para gerenciar o sistema."
            ),
            color=discord.Color.from_str("#5865F2")
        )
        embed.add_field(name="🃏 Jogadores", value="Criar, editar, deletar cartas globais e distribuir para membros.", inline=True)
        embed.add_field(name="✨ Coleções", value="Criar, editar e excluir coleções de raridade.", inline=True)
        embed.add_field(name="📋 Missões", value="Criar e remover missões semanais/mensais.", inline=True)
        embed.add_field(name="💰 Economia", value="Adicionar/remover dinheiro e VLS Coins de membros.", inline=True)
        embed.add_field(name="👥 Usuários", value="Dar ou retirar jogadores do inventário de um membro.", inline=True)
        embed.add_field(name="🛍️ Loja Custom", value="Criar e gerenciar produtos e pacotes personalizados.", inline=True)
        embed.set_footer(text="VLS Guru Admin • Apenas administradores")

        view = CategorySelectView(interaction.user.id)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ══════════════════════════════════════════════════════════
# CATEGORY SELECT
# ══════════════════════════════════════════════════════════

class CategorySelectView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.add_item(CategoryDropdown(owner_id))


class CategoryDropdown(discord.ui.Select):
    def __init__(self, owner_id: int):
        self.owner_id = owner_id
        options = [
            discord.SelectOption(label="🃏 Jogadores",  value="jogadores",  description="Gerenciar cartas globais"),
            discord.SelectOption(label="✨ Coleções",   value="colecoes",   description="Gerenciar coleções de raridade"),
            discord.SelectOption(label="📋 Missões",    value="missoes",    description="Criar e remover missões"),
            discord.SelectOption(label="💰 Economia",   value="economia",   description="Gerenciar saldo dos membros"),
            discord.SelectOption(label="👥 Usuários",   value="usuarios",   description="Distribuir/retirar jogadores"),
            discord.SelectOption(label="🛍️ Loja",       value="loja",       description="Gerenciar produtos personalizados"),
        ]
        super().__init__(placeholder="Selecione uma categoria...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)

        cat = self.values[0]
        if cat == "jogadores":
            embed, view = build_jogadores_panel(self.owner_id)
        elif cat == "colecoes":
            embed, view = build_colecoes_panel(self.owner_id)
        elif cat == "missoes":
            embed, view = build_missoes_panel(self.owner_id)
        elif cat == "economia":
            embed, view = build_economia_panel(self.owner_id)
        elif cat == "usuarios":
            embed, view = build_usuarios_panel(self.owner_id)
        elif cat == "loja":
            embed, view = build_loja_panel(self.owner_id)
        else:
            return await interaction.response.defer()

        await interaction.response.edit_message(embed=embed, view=view)


# ══════════════════════════════════════════════════════════
# JOGADORES PANEL
# ══════════════════════════════════════════════════════════

def build_jogadores_panel(owner_id: int):
    embed = discord.Embed(
        title="🃏 Painel de Jogadores",
        description="Gerencie as cartas globais disponíveis no sistema.",
        color=discord.Color.gold()
    )
    embed.add_field(name="➕ Criar Jogador", value="Adiciona uma nova carta ao banco global (3 etapas).", inline=True)
    embed.add_field(name="✏️ Editar Jogador", value="Edita dados de um jogador existente por ID.", inline=True)
    embed.add_field(name="🗑️ Deletar Jogador", value="Remove permanentemente uma carta do sistema.", inline=True)
    embed.add_field(name="📋 Listar Jogadores", value="Lista todos os jogadores cadastrados.", inline=True)
    embed.set_footer(text="← Voltar: use /admin novamente")
    return embed, JogadoresView(owner_id)


class JogadoresView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="➕ Criar Jogador", style=discord.ButtonStyle.success, row=0)
    async def criar_jogador(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(CriarJogadorModal1())

    @discord.ui.button(label="✏️ Editar Jogador", style=discord.ButtonStyle.primary, row=0)
    async def editar_jogador(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(EditarJogadorModal())

    @discord.ui.button(label="🗑️ Deletar Jogador", style=discord.ButtonStyle.danger, row=0)
    async def deletar_jogador(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(DeletarJogadorModal())

    @discord.ui.button(label="📋 Listar Jogadores", style=discord.ButtonStyle.secondary, row=0)
    async def listar_jogadores(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.defer(thinking=True, ephemeral=True)
        players = await get_all_players()
        if not players:
            return await interaction.followup.send("Nenhum jogador cadastrado.", ephemeral=True)

        players = sorted(players, key=lambda x: x.get("over", 0), reverse=True)
        lines = [f"`{p.get('id','?')}` | **{p['name']}** | {p.get('pos','?')} | ★{p.get('over','?')} | {p.get('col_nome','?')}" for p in players]
        chunks = [lines[i:i+20] for i in range(0, len(lines), 20)]

        for idx, chunk in enumerate(chunks[:3]):  # máx 3 mensagens
            await interaction.followup.send(
                f"**📋 Jogadores ({idx+1}/{len(chunks)}):**\n" + "\n".join(chunk),
                ephemeral=True
            )


# ─── Criar Jogador: 3 modals encadeados ───────────────────


class VLSModal(discord.ui.Modal):
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        import traceback
        traceback.print_exc()
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"❌ Ocorreu um erro: {error}", ephemeral=True)
            else:
                await interaction.followup.send(f"❌ Ocorreu um erro: {error}", ephemeral=True)
        except Exception:
            pass


class CriarJogadorModal1(VLSModal, title="Criar Jogador — Etapa 1/3: Dados Básicos"):
    p_nome      = discord.ui.TextInput(label="Nome completo", placeholder="Ex: Lionel Messi", max_length=50)
    p_overall   = discord.ui.TextInput(label="Overall (Rated)", placeholder="Ex: 91", max_length=3)
    p_posicao   = discord.ui.TextInput(label="Posição (GK, CB, CM, ST...)", placeholder="Ex: ST", max_length=5)
    p_colecao   = discord.ui.TextInput(label="ID da Coleção", placeholder="Ex: base, comum, premiados", max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            overall = int(str(self.p_overall))
        except ValueError:
            return await interaction.response.send_message("❌ Overall deve ser um número inteiro.", ephemeral=True)

        pos_upper = str(self.p_posicao).upper().strip()
        if pos_upper not in POSITIONS_ALL:
            return await interaction.response.send_message(
                f"❌ Posição inválida. Válidas: {', '.join(POSITIONS_ALL)}", ephemeral=True
            )

        col_doc = f"col_{str(self.p_colecao).lower().strip()}"
        col_record = await db_get(col_doc)
        if not col_record:
            return await interaction.response.send_message(
                f"❌ Coleção `{self.p_colecao}` não existe. Crie primeiro em Coleções.", ephemeral=True
            )

        # Gera o ID dinamicamente a partir do nome do jogador
        import re
        import unicodedata

        nome_original = str(self.p_nome).strip()
        # Normaliza removendo acentos
        nome_normalizado = unicodedata.normalize('NFKD', nome_original).encode('ASCII', 'ignore').decode('ASCII')
        nome_normalizado = nome_normalizado.lower()
        # Remove caracteres especiais e substitui espaços por underlines
        nome_normalizado = re.sub(r'[^a-z0-9\s-]', '', nome_normalizado)
        slug_id = re.sub(r'[\s-]+', '_', nome_normalizado).strip('_')

        if not slug_id:
            return await interaction.response.send_message("❌ Nome inválido para geração de ID do jogador.", ephemeral=True)

        # Verifica se o ID já existe e adiciona um sufixo numérico (_2, _3...) se necessário
        final_id = slug_id
        suffix = 2
        while True:
            doc_id = f"player_{final_id}"
            existing = await db_get(doc_id)
            if not existing:
                break
            final_id = f"{slug_id}_{suffix}"
            suffix += 1

        _PENDING_PLAYER[interaction.user.id] = {
            "id": final_id,
            "name": nome_original,
            "over": overall,
            "pos": pos_upper,
            "col_id": col_record["data"]["id"],
            "col_nome": col_record["data"]["nome"],
            "col_emoji": col_record["data"]["emoji"],
            "max_playstyles": col_record["data"].get("max_playstyles", 0),
        }

        view = ContinuarJogador2View(interaction.user.id)
        await interaction.response.send_message(
            "✅ **Dados básicos salvos!** Clique no botão abaixo para preencher os atributos (Etapa 2/3).",
            view=view,
            ephemeral=True
        )



class CriarJogadorModal2(VLSModal, title="Criar Jogador — Etapa 2/3: Atributos"):
    p_pac = discord.ui.TextInput(label="Velocidade (PAC)", placeholder="0-99", max_length=2, default="75")
    p_sho = discord.ui.TextInput(label="Chute (SHO)", placeholder="0-99", max_length=2, default="75")
    p_pas = discord.ui.TextInput(label="Passe (PAS)", placeholder="0-99", max_length=2, default="75")
    p_dri = discord.ui.TextInput(label="Drible (DRI)", placeholder="0-99", max_length=2, default="75")
    p_def = discord.ui.TextInput(label="Defesa (DEF)", placeholder="0-99", max_length=2, default="75")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            attrs = {
                "pac": int(str(self.p_pac)),
                "sho": int(str(self.p_sho)),
                "pas": int(str(self.p_pas)),
                "dri": int(str(self.p_dri)),
                "def": int(str(self.p_def)),
            }
            for v in attrs.values():
                if not (0 <= v <= 99):
                    raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Todos os atributos devem ser números de 0 a 99.", ephemeral=True)

        pending = _PENDING_PLAYER.get(interaction.user.id, {})
        if not pending:
            return await interaction.response.send_message("❌ Sessão expirada.", ephemeral=True)
        pending.update(attrs)
        _PENDING_PLAYER[interaction.user.id] = pending

        view = ContinuarJogador3View(interaction.user.id)
        await interaction.response.send_message(
            "✅ **Atributos salvos!** Clique no botão abaixo para ir para os Extras (Etapa 3/3).",
            view=view,
            ephemeral=True
        )


class CriarGoleiroModal2(VLSModal, title="Criar Goleiro — Etapa 2/3: Atributos GK"):
    p_div = discord.ui.TextInput(label="Elasticidade (DIV)", placeholder="0-99", max_length=2, default="75")
    p_han = discord.ui.TextInput(label="Manejo (HAN)", placeholder="0-99", max_length=2, default="75")
    p_kic = discord.ui.TextInput(label="Chute (KIC)", placeholder="0-99", max_length=2, default="75")
    p_ref = discord.ui.TextInput(label="Reflexo (REF)", placeholder="0-99", max_length=2, default="75")
    p_spd = discord.ui.TextInput(label="Velocidade (SPD)", placeholder="0-99", max_length=2, default="75")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            attrs = {
                "div": int(str(self.p_div)),
                "han": int(str(self.p_han)),
                "kic": int(str(self.p_kic)),
                "ref": int(str(self.p_ref)),
                "spd": int(str(self.p_spd)),
            }
            for v in attrs.values():
                if not (0 <= v <= 99):
                    raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Todos os atributos devem ser números de 0 a 99.", ephemeral=True)

        pending = _PENDING_PLAYER.get(interaction.user.id, {})
        if not pending:
            return await interaction.response.send_message("❌ Sessão expirada.", ephemeral=True)
        pending.update(attrs)
        _PENDING_PLAYER[interaction.user.id] = pending

        view = ContinuarJogador3View(interaction.user.id)
        await interaction.response.send_message(
            "✅ **Atributos de GK salvos!** Clique no botão abaixo para ir para os Extras (Etapa 3/3).",
            view=view,
            ephemeral=True
        )


class CriarJogadorModal3(VLSModal, title="Criar Jogador — Etapa 3/3: Extras"):
    p_phy   = discord.ui.TextInput(label="Físico (PHY)", placeholder="0-99", max_length=2, default="75")
    p_wf    = discord.ui.TextInput(label="Perna Ruim (1-5)", placeholder="Ex: 3", max_length=1, default="3")
    p_sm    = discord.ui.TextInput(label="Fintas (1-5)", placeholder="Ex: 3", max_length=1, default="3")
    p_nation= discord.ui.TextInput(label="Nacionalidade", placeholder="Ex: Brasileiro", max_length=30)
    p_club  = discord.ui.TextInput(label="Clube", placeholder="Ex: FC Barcelona", max_length=40)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            phy = int(str(self.p_phy))
            wf = int(str(self.p_wf))
            sm = int(str(self.p_sm))
            if not (0 <= phy <= 99) or not (1 <= wf <= 5) or not (1 <= sm <= 5):
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Físico deve ser de 0-99, e Perna Ruim/Fintas devem ser entre 1 e 5.", ephemeral=True)

        pending = _PENDING_PLAYER.pop(interaction.user.id, {})
        if not pending:
            return await interaction.response.send_message("❌ Sessão expirada.", ephemeral=True)

        pending.update({
            "phy": phy,
            "weak_foot": wf,
            "skill_moves": sm,
            "nationality": str(self.p_nation).strip(),
            "club": str(self.p_club).strip(),
            "shoot": pending["sho"],
            "pass_stat": pending["pas"],
            "dribble": pending["dri"],
            "defense": pending["def"],
            "physical": phy
        })

        await finalizar_modal(interaction, pending)


class CriarGoleiroModal3(VLSModal, title="Criar Goleiro — Etapa 3/3: Extras"):
    p_pos_stat = discord.ui.TextInput(label="Posicionamento (POS)", placeholder="0-99", max_length=2, default="75")
    p_wf       = discord.ui.TextInput(label="Perna Ruim (1-5)", placeholder="Ex: 3", max_length=1, default="3")
    p_sm       = discord.ui.TextInput(label="Fintas (1-5)", placeholder="Ex: 3", max_length=1, default="3")
    p_nation   = discord.ui.TextInput(label="Nacionalidade", placeholder="Ex: Brasileiro", max_length=30)
    p_club     = discord.ui.TextInput(label="Clube", placeholder="Ex: FC Barcelona", max_length=40)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            pos_stat = int(str(self.p_pos_stat))
            wf = int(str(self.p_wf))
            sm = int(str(self.p_sm))
            if not (0 <= pos_stat <= 99) or not (1 <= wf <= 5) or not (1 <= sm <= 5):
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("❌ Posicionamento deve ser de 0-99, e Perna Ruim/Fintas devem ser entre 1 e 5.", ephemeral=True)

        pending = _PENDING_PLAYER.pop(interaction.user.id, {})
        if not pending:
            return await interaction.response.send_message("❌ Sessão expirada.", ephemeral=True)

        pending.update({
            "pos_stat": pos_stat,
            "weak_foot": wf,
            "skill_moves": sm,
            "nationality": str(self.p_nation).strip(),
            "club": str(self.p_club).strip(),
            "shoot": pending["kic"],
            "pass_stat": pending["han"],
            "dribble": pending["ref"],
            "defense": pending["div"],
            "physical": pos_stat
        })

        await finalizar_modal(interaction, pending)


async def finalizar_modal(interaction: discord.Interaction, pending: dict):
    max_ps = pending.get("max_playstyles", 0)
    if max_ps <= 0:
        doc_id = f"player_{pending['id']}"
        if await db_get(doc_id):
            return await interaction.response.send_message(
                f"❌ Jogador com ID `{pending['id']}` já existe.", ephemeral=True
            )
        pending["playstyles"] = []
        pending["card"] = ""
        pending["xp"] = 0
        
        await interaction.response.defer(ephemeral=True)
        await solicitar_foto_e_salvar(interaction, pending)
    else:
        view = PlaystyleSelectView(interaction.user.id, pending, max_ps)
        await interaction.response.send_message(
            f"🎨 **Etapa Final:** Selecione até **{max_ps}** PlayStyles para o jogador e clique em **Finalizar Cadastro**.",
            view=view,
            ephemeral=True
        )


class PlaystyleSelect(discord.ui.Select):
    def __init__(self, max_playstyles: int, is_gk: bool):
        options = []
        gk_styles = ["arremesso_especial", "encaixada"]
        for ps, emoji in PLAYSTYLE_EMOJIS.items():
            if is_gk and ps not in gk_styles:
                continue
            if not is_gk and ps in gk_styles:
                continue
            label = ps.replace("_", " ").title()
            options.append(discord.SelectOption(
                label=label,
                value=ps,
                emoji=emoji,
                description=f"PlayStyle: {label}"
            ))

        super().__init__(
            placeholder=f"Selecione até {max_playstyles} PlayStyles...",
            min_values=0,
            max_values=min(max_playstyles, len(options)),
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_playstyles = self.values
        ps_str = ", ".join([PLAYSTYLE_EMOJIS[ps] + " " + ps.replace("_", " ").title() for ps in self.values])
        await interaction.response.send_message(
            f"✅ Selecionado(s): {ps_str or 'Nenhum'}. Clique em '💾 Finalizar Cadastro' para concluir.",
            ephemeral=True
        )


class PlaystyleSelectView(discord.ui.View):
    def __init__(self, owner_id: int, pending_data: dict, max_playstyles: int):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.pending_data = pending_data
        self.max_playstyles = max_playstyles
        self.selected_playstyles = []

        is_gk = pending_data.get("pos") == "GK"
        if max_playstyles > 0:
            self.add_item(PlaystyleSelect(max_playstyles, is_gk))

    @discord.ui.button(label="💾 Finalizar Cadastro", style=discord.ButtonStyle.success, row=1)
    async def finalizar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)

        self.pending_data["playstyles"] = self.selected_playstyles
        doc_id = f"player_{self.pending_data['id']}"

        if await db_get(doc_id):
            return await interaction.response.send_message(
                f"❌ Jogador com ID `{self.pending_data['id']}` já existe.", ephemeral=True
            )

        self.pending_data["card"] = ""
        self.pending_data["xp"] = 0

        await interaction.response.defer(ephemeral=True)
        await solicitar_foto_e_salvar(interaction, self.pending_data)
        self.stop()


async def solicitar_foto_e_salvar(interaction: discord.Interaction, pending: dict):
    prompt_msg = await interaction.followup.send(
        "📸 **Envie a Imagem da Carta Personalizada**\n"
        "Envie a imagem como anexo (upload direto) ou cole o link de uma imagem nesta conversa.\n"
        "*(A imagem é obrigatória para cartas personalizadas)*",
        ephemeral=True
    )

    def check(m):
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

    card_url = ""
    user_msg = None
    try:
        msg = await interaction.client.wait_for("message", check=check, timeout=120)
        user_msg = msg
        content_stripped = msg.content.strip()
        
        if msg.attachments:
            # É anexo! Baixar e hospedar no ImgBB
            attachment = msg.attachments[0]
            img_bytes = await attachment.read()
            
            def upload_imgbb():
                try:
                    from PIL import Image
                    from io import BytesIO
                    import requests
                    img = Image.open(BytesIO(img_bytes)).convert("RGBA")
                    bbox = img.getbbox()
                    if bbox:
                        img = img.crop(bbox)
                    buf = BytesIO()
                    img.save(buf, format="PNG")
                    buf.seek(0)
                    resp = requests.post(
                        "https://api.imgbb.com/1/upload?key=617c898158c94ac25ddaf2491ee7d0b4",
                        files={"image": buf.read()},
                        timeout=20
                    )
                    if resp.status_code == 200:
                        return resp.json()["data"]["url"]
                except Exception as e:
                    print(f"Erro no upload do anexo: {e}")
                return ""
            
            progress_msg = await interaction.followup.send("⏳ Processando e hospedando imagem no ImgBB...", ephemeral=True)
            card_url = await asyncio.to_thread(upload_imgbb)
            try:
                await progress_msg.delete()
            except Exception:
                pass
        elif content_stripped.startswith("http"):
            card_url = content_stripped
    except asyncio.TimeoutError:
        return await interaction.followup.send("❌ Tempo limite esgotado. Criação do jogador cancelada.", ephemeral=True)

    if not card_url:
        return await interaction.followup.send("❌ Nenhuma imagem ou link válido fornecido. Criação cancelada.", ephemeral=True)

    pending["card"] = card_url
    pending["xp"] = 0

    doc_id = f"player_{pending['id']}"
    await db_upsert(doc_id, pending)

    # Deleta a mensagem do usuário contendo o anexo/link
    if user_msg:
        try:
            await user_msg.delete()
        except Exception as e:
            print(f"Não foi possível deletar a mensagem do usuário: {e}")

    # Deleta a mensagem do prompt
    if prompt_msg:
        try:
            await prompt_msg.delete()
        except Exception:
            pass

    col_emoji = pending.get("col_emoji", "✨")
    ps_list = pending.get("playstyles", [])
    ps_str = ", ".join([PLAYSTYLE_EMOJIS[ps] + " " + ps.replace("_", " ").title() for ps in ps_list]) if ps_list else "Nenhum"

    await interaction.followup.send(
        f"✅ **Jogador criado com sucesso!**\n"
        f"{col_emoji} **{pending['name']}** | {pending['pos']} | ★ {pending['over']}\n"
        f"PlayStyles: {ps_str}\n"
        f"Coleção: {pending['col_nome']} | ID: `{pending['id']}`",
        ephemeral=True
    )

class EditPlaystyleSelect(discord.ui.Select):
    def __init__(self, max_playstyles: int, is_gk: bool):
        options = []
        gk_styles = ["arremesso_especial", "encaixada"]
        for ps, emoji in PLAYSTYLE_EMOJIS.items():
            if is_gk and ps not in gk_styles:
                continue
            if not is_gk and ps in gk_styles:
                continue
            label = ps.replace("_", " ").title()
            options.append(discord.SelectOption(
                label=label,
                value=ps,
                emoji=emoji,
                description=f"PlayStyle: {label}"
            ))

        super().__init__(
            placeholder=f"Selecione até {max_playstyles} PlayStyles...",
            min_values=0,
            max_values=min(max_playstyles, len(options)),
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.player_data["playstyles"] = self.values
        ps_str = ", ".join([PLAYSTYLE_EMOJIS[ps] + " " + ps.replace("_", " ").title() for ps in self.values])
        await interaction.response.send_message(
            f"✅ PlayStyles alterados para: {ps_str or 'Nenhum'}.",
            ephemeral=True
        )


class EditarJogadorOpcoesView(discord.ui.View):
    def __init__(self, owner_id: int, doc_id: str, player_data: dict):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.doc_id = doc_id
        self.player_data = player_data

    @discord.ui.button(label="🎭 Mudar PlayStyles", style=discord.ButtonStyle.primary, row=1)
    async def mudar_playstyles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        
        col_id = self.player_data.get("col_id", "base")
        col_rec = await db_get(f"col_{col_id}")
        max_ps = col_rec["data"].get("max_playstyles", 3) if col_rec else 3
        if max_ps <= 0:
            max_ps = 3
            
        is_gk = self.player_data.get("pos") == "GK"
        
        sub_view = discord.ui.View(timeout=120)
        sub_view.player_data = self.player_data
        sub_view.add_item(EditPlaystyleSelect(max_ps, is_gk))
        
        await interaction.followup.send(
            f"Selecione até **{max_ps}** PlayStyles para o jogador:",
            view=sub_view,
            ephemeral=True
        )

    @discord.ui.button(label="📸 Mudar Foto", style=discord.ButtonStyle.primary, row=1)
    async def mudar_foto(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
            
        await interaction.response.defer(ephemeral=True)
        
        prompt_msg = await interaction.followup.send(
            "📸 **Envie a Nova Imagem da Carta**\n"
            "Envie a imagem como anexo (upload direto) ou cole o link de uma imagem nesta conversa.",
            ephemeral=True
        )

        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        card_url = ""
        user_msg = None
        try:
            msg = await interaction.client.wait_for("message", check=check, timeout=120)
            user_msg = msg
            content_stripped = msg.content.strip()
            
            if msg.attachments:
                attachment = msg.attachments[0]
                img_bytes = await attachment.read()
                
                def upload_imgbb():
                    try:
                        from PIL import Image
                        from io import BytesIO
                        import requests
                        img = Image.open(BytesIO(img_bytes)).convert("RGBA")
                        bbox = img.getbbox()
                        if bbox:
                            img = img.crop(bbox)
                        buf = BytesIO()
                        img.save(buf, format="PNG")
                        buf.seek(0)
                        resp = requests.post(
                            "https://api.imgbb.com/1/upload?key=617c898158c94ac25ddaf2491ee7d0b4",
                            files={"image": buf.read()},
                            timeout=20
                        )
                        if resp.status_code == 200:
                            return resp.json()["data"]["url"]
                    except Exception as e:
                        print(f"Erro no upload do anexo: {e}")
                    return ""
                
                progress_msg = await interaction.followup.send("⏳ Processando e hospedando imagem no ImgBB...", ephemeral=True)
                card_url = await asyncio.to_thread(upload_imgbb)
                try:
                    await progress_msg.delete()
                except Exception:
                    pass
            elif content_stripped.startswith("http"):
                card_url = content_stripped
        except asyncio.TimeoutError:
            return await interaction.followup.send("❌ Tempo limite esgotado. Alteração de foto cancelada.", ephemeral=True)

        if not card_url:
            return await interaction.followup.send("❌ Nenhuma imagem ou link válido fornecido. Foto mantida.", ephemeral=True)

        self.player_data["card"] = card_url
        
        if user_msg:
            try:
                await user_msg.delete()
            except Exception:
                pass
        try:
            await prompt_msg.delete()
        except Exception:
            pass

        await interaction.followup.send("✅ Nova imagem configurada com sucesso!", ephemeral=True)

    @discord.ui.button(label="💾 Salvar e Concluir", style=discord.ButtonStyle.success, row=2)
    async def salvar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
            
        await db_upsert(self.doc_id, self.player_data)
        
        for child in self.children:
            child.disabled = True
            
        embed = discord.Embed(
            title="✅ Jogador Atualizado com Sucesso!",
            description=f"Todas as modificações de atributos, PlayStyles e Foto foram salvas para **{self.player_data['name']}**.",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


class PlayerSelectDropdown(discord.ui.Select):
    def __init__(self, action_type: str, matches: list, user_id: int, extra_data: dict = None):
        self.action_type = action_type
        self.user_id = user_id
        self.extra_data = extra_data or {}
        
        options = []
        for p in matches[:25]:
            options.append(
                discord.SelectOption(
                    label=p["name"][:100],
                    description=f"Pos: {p.get('pos','?')} | Over: {p.get('over','?')} | {p.get('col_nome','Base')}",
                    value=p["id"]
                )
            )
        super().__init__(placeholder="Selecione o jogador...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
            
        doc_id = self.values[0]
        record = await db_get(doc_id)
        if not record:
            return await interaction.response.send_message("❌ Jogador não encontrado no banco.", ephemeral=True)
            
        data = record["data"]
        
        if self.action_type == "edit":
            changed = self.extra_data.get("changed", [])
            basic_changes = self.extra_data.get("basic_changes", {})
            for k, v in basic_changes.items():
                data[k] = v
                
            # Atualiza atributos
            over = data.get("over", 75)
            pos = data.get("pos", "ST")
            if pos == "GK":
                data.update({
                    "div": over, "han": over, "kic": over, "ref": over, "spd": over, "pos_stat": over,
                    "shoot": over, "pass_stat": over, "dribble": over, "defense": over, "physical": over
                })
            else:
                data.update({
                    "pac": over, "sho": over, "pas": over, "dri": over, "def": over, "phy": over,
                    "shoot": over, "pass_stat": over, "dribble": over, "defense": over, "physical": over
                })
                
            await db_upsert(doc_id, data)
            
            view = EditarJogadorOpcoesView(self.user_id, doc_id, data)
            embed = discord.Embed(
                title=f"✏️ Editar: {data['name']}",
                description=(
                    f"Modificações básicas aplicadas:\n" + 
                    ("\n".join([f"• {c}" for c in changed]) if changed else "• Nenhuma alteração básica\n") +
                    "\nUse as opções abaixo para atualizar os PlayStyles ou a Foto do jogador."
                ),
                color=discord.Color.blue()
            )
            await interaction.response.edit_message(embed=embed, view=view)
            
        elif self.action_type == "delete":
            nome = data.get("name", doc_id)
            await _delete_player_everywhere(doc_id, nome)
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🗑️ Jogador Deletado",
                    description=f"O jogador **{nome}** foi removido do catálogo e de todos os inventários.",
                    color=discord.Color.red()
                ),
                view=None
            )
            
        elif self.action_type == "give":
            target_user_id = self.extra_data.get("target_user_id")
            target_record = await db_get(f"user_{target_user_id}")
            if not target_record:
                return await interaction.response.send_message(f"❌ Usuário `{target_user_id}` não encontrado.", ephemeral=True)
                
            profile = target_record["data"]
            instanced = data.copy()
            instanced["instance_id"] = str(uuid.uuid4())[:8]
            instanced["original_pos"] = data["pos"]
            instanced["acquired_at"] = datetime.utcnow().isoformat()
            instanced.update({"goals": 0, "assists": 0, "saves": 0, "matches": 0, "mvps": 0, "yellow_cards": 0, "red_cards": 0, "xp": 0})
            
            profile.setdefault("inventory", []).append(instanced)
            await save_user_profile(target_user_id, profile)
            
            col_emoji = data.get("col_emoji", "✨")
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="🎁 Jogador Enviado",
                    description=f"**{col_emoji} {data['name']}** enviado para o usuário `{target_user_id}`!\nInstance ID: `{instanced['instance_id']}`",
                    color=discord.Color.green()
                ),
                view=None
            )

class PlayerSelectDropdownView(discord.ui.View):
    def __init__(self, action_type: str, matches: list, user_id: int, extra_data: dict = None):
        super().__init__(timeout=180)
        self.add_item(PlayerSelectDropdown(action_type, matches, user_id, extra_data))


class EditarJogadorModal(VLSModal, title="Editar Jogador"):
    p_busca   = discord.ui.TextInput(label="Nome ou busca do Jogador", placeholder="Ex: Tarik ou Tar", max_length=50)
    p_nome    = discord.ui.TextInput(label="Novo Nome (deixe vazio para manter)", required=False, max_length=50)
    p_overall = discord.ui.TextInput(label="Novo Overall (deixe vazio para manter)", required=False, max_length=3)
    p_pos     = discord.ui.TextInput(label="Nova Posição (deixe vazio para manter)", required=False, max_length=5)
    p_colecao = discord.ui.TextInput(label="Nova Coleção ID (deixe vazio para manter)", required=False, max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        players = await get_all_players()
        search_term = str(self.p_busca).strip().lower()
        matches = [p for p in players if search_term in p.get("name", "").lower() or search_term in p.get("id", "").lower()]
        
        if not matches:
            return await interaction.response.send_message(f"❌ Nenhum jogador encontrado contendo `{self.p_busca}`.", ephemeral=True)
            
        basic_changes = {}
        changed = []
        
        if str(self.p_nome).strip():
            basic_changes["name"] = str(self.p_nome).strip()
            changed.append(f"Nome → {basic_changes['name']}")
            
        if str(self.p_overall).strip():
            try:
                basic_changes["over"] = int(str(self.p_overall).strip())
                changed.append(f"Overall → {basic_changes['over']}")
            except ValueError:
                return await interaction.response.send_message("❌ Overall inválido.", ephemeral=True)
                
        if str(self.p_pos).strip():
            pos_upper = str(self.p_pos).strip().upper()
            if pos_upper not in POSITIONS_ALL:
                return await interaction.response.send_message(f"❌ Posição inválida: {pos_upper}", ephemeral=True)
            basic_changes["pos"] = pos_upper
            changed.append(f"Posição → {pos_upper}")
            
        if str(self.p_colecao).strip():
            col_id = str(self.p_colecao).strip().lower()
            col_rec = await db_get(f"col_{col_id}")
            if not col_rec:
                return await interaction.response.send_message(f"❌ Coleção `{col_id}` não existe.", ephemeral=True)
            basic_changes["col_id"] = col_rec["data"]["id"]
            basic_changes["col_nome"] = col_rec["data"]["nome"]
            basic_changes["col_emoji"] = col_rec["data"]["emoji"]
            changed.append(f"Coleção → {basic_changes['col_nome']}")
            
        extra_data = {
            "basic_changes": basic_changes,
            "changed": changed
        }
        
        if len(matches) == 1:
            doc_id = matches[0]["id"]
            data = matches[0]
            
            for k, v in basic_changes.items():
                data[k] = v
                
            over = data.get("over", 75)
            pos = data.get("pos", "ST")
            if pos == "GK":
                data.update({
                    "div": over, "han": over, "kic": over, "ref": over, "spd": over, "pos_stat": over,
                    "shoot": over, "pass_stat": over, "dribble": over, "defense": over, "physical": over
                })
            else:
                data.update({
                    "pac": over, "sho": over, "pas": over, "dri": over, "def": over, "phy": over,
                    "shoot": over, "pass_stat": over, "dribble": over, "defense": over, "physical": over
                })
                
            await db_upsert(doc_id, data)
            
            view = EditarJogadorOpcoesView(interaction.user.id, doc_id, data)
            embed = discord.Embed(
                title=f"✏️ Editar: {data['name']}",
                description=(
                    f"Modificações básicas aplicadas:\n" + 
                    ("\n".join([f"• {c}" for c in changed]) if changed else "• Nenhuma alteração básica\n") +
                    "\nUse as opções abaixo para atualizar os PlayStyles ou a Foto do jogador."
                ),
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            view = PlayerSelectDropdownView("edit", matches, interaction.user.id, extra_data)
            embed = discord.Embed(
                title="🔍 Múltiplos jogadores encontrados",
                description=f"Encontrei {len(matches)} jogadores correspondentes ao termo `{self.p_busca}`. Selecione qual deseja editar:",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


async def _delete_player_everywhere(player_id: str, player_name: str):
    """Remove o jogador do catálogo e de todos os inventários/XIs de usuários."""
    db_id = player_id if player_id.startswith("player_") else f"player_{player_id}"
    clean_id = player_id.replace("player_", "")
    await db_delete(db_id)
    users = await get_all_users()
    for u_data in users:
        uid = u_data.get("user_id")
        if not uid:
            continue
        inventory = u_data.get("inventory", [])
        # inventory items têm "id" copiado do catálogo
        new_inv = [item for item in inventory if item.get("id") != clean_id]
        if len(new_inv) != len(inventory):
            u_data["inventory"] = new_inv
            u_data["starting_xi"] = [
                p for p in u_data.get("starting_xi", [])
                if p.get("id") != clean_id
            ]
            await save_user_profile(uid, u_data)

class DeletarJogadorModal(VLSModal, title="Deletar Jogador"):
    p_busca = discord.ui.TextInput(label="Nome ou busca do Jogador", placeholder="Ex: Tarik", max_length=50)
    confirmacao = discord.ui.TextInput(label="Digite CONFIRMAR para prosseguir", placeholder="CONFIRMAR", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        if str(self.confirmacao).strip() != "CONFIRMAR":
            return await interaction.response.send_message("❌ Operação cancelada. Você não digitou CONFIRMAR.", ephemeral=True)

        players = await get_all_players()
        search_term = str(self.p_busca).strip().lower()
        matches = [p for p in players if search_term in p.get("name", "").lower() or search_term in p.get("id", "").lower()]
        
        if not matches:
            return await interaction.response.send_message(f"❌ Nenhum jogador encontrado contendo `{self.p_busca}`.", ephemeral=True)
            
        if len(matches) == 1:
            doc_id = matches[0]["id"]
            nome = matches[0].get("name", doc_id)
            await _delete_player_everywhere(doc_id, nome)
            await interaction.response.send_message(f"🗑️ Jogador **{nome}** removido do catálogo e de todos os inventários.", ephemeral=True)
        else:
            view = PlayerSelectDropdownView("delete", matches, interaction.user.id)
            embed = discord.Embed(
                title="🔍 Múltiplos jogadores encontrados",
                description=f"Encontrei {len(matches)} jogadores correspondentes ao termo `{self.p_busca}`. Selecione qual deseja deletar:",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# ══════════════════════════════════════════════════════════
# COLEÇÕES PANEL
# ══════════════════════════════════════════════════════════

def build_colecoes_panel(owner_id: int):
    embed = discord.Embed(
        title="✨ Painel de Coleções",
        description="Gerencie as coleções de raridade do sistema.",
        color=discord.Color.purple()
    )
    embed.add_field(name="➕ Criar Coleção", value="Cadastra uma nova raridade.", inline=True)
    embed.add_field(name="✏️ Editar Coleção", value="Altera dados de uma coleção existente.", inline=True)
    embed.add_field(name="🗑️ Deletar Coleção", value="Remove uma coleção permanentemente.", inline=True)
    embed.add_field(name="📋 Listar Coleções", value="Exibe todas as coleções cadastradas.", inline=True)
    embed.set_footer(text="← Voltar: use /admin novamente")
    return embed, ColecoesView(owner_id)


class ColecoesView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="➕ Criar Coleção", style=discord.ButtonStyle.success, row=0)
    async def criar_colecao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(CriarColecaoModal())

    @discord.ui.button(label="✏️ Editar Coleção", style=discord.ButtonStyle.primary, row=0)
    async def editar_colecao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(EditarColecaoModal())

    @discord.ui.button(label="🗑️ Deletar Coleção", style=discord.ButtonStyle.danger, row=0)
    async def deletar_colecao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(DeletarColecaoModal())

    @discord.ui.button(label="📋 Listar Coleções", style=discord.ButtonStyle.secondary, row=0)
    async def listar_colecoes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.defer(thinking=True, ephemeral=True)
        cols = await get_all_collections()
        if not cols:
            return await interaction.followup.send("Nenhuma coleção cadastrada.", ephemeral=True)

        lines = [
            f"{c.get('emoji','?')} **{c['nome']}** | ID: `{c['id']}` | "
            f"PlayStyles Máx: {c.get('max_playstyles',0)} | Preço +{c.get('preco_adicional_pct',0)}%"
            for c in cols
        ]
        await interaction.followup.send("**✨ Coleções cadastradas:**\n" + "\n".join(lines), ephemeral=True)


class CriarColecaoModal(VLSModal, title="Criar Coleção"):
    c_id           = discord.ui.TextInput(label="ID único (ex: lendaria, base)", placeholder="Sem espaços, minúsculo", max_length=30)
    c_nome         = discord.ui.TextInput(label="Nome de exibição", placeholder="Ex: Lendária", max_length=40)
    c_emoji        = discord.ui.TextInput(label="Emoji", placeholder="Ex: 👑 ou <:custom:123>", max_length=50)
    c_max_ps       = discord.ui.TextInput(label="Máx de PlayStyles", placeholder="Ex: 2", max_length=2, default="0")
    c_preco_pct    = discord.ui.TextInput(label="Aumento de preço %", placeholder="Ex: 50", max_length=5, default="0")

    async def on_submit(self, interaction: discord.Interaction):
        try:
            max_ps = int(str(self.c_max_ps).strip())
            preco_pct = int(str(self.c_preco_pct).strip())
        except ValueError:
            return await interaction.response.send_message("❌ Máx de PlayStyles e Preço % devem ser números.", ephemeral=True)

        col_id = str(self.c_id).lower().strip()
        doc_id = f"col_{col_id}"
        if await db_get(doc_id):
            return await interaction.response.send_message(f"❌ Coleção `{col_id}` já existe.", ephemeral=True)

        data = {
            "id": col_id,
            "nome": str(self.c_nome).strip(),
            "emoji": str(self.c_emoji).strip(),
            "max_playstyles": max_ps,
            "preco_adicional_pct": preco_pct,
        }
        await db_upsert(doc_id, data)
        await interaction.response.send_message(
            f"✅ Coleção **{data['nome']}** {data['emoji']} criada!\n"
            f"ID: `{col_id}` | PlayStyles Máx: {max_ps} | Preço +{preco_pct}%",
            ephemeral=True
        )


class EditarColecaoModal(VLSModal, title="Editar Coleção"):
    c_id     = discord.ui.TextInput(label="ID da Coleção", placeholder="Ex: base", max_length=30)
    c_nome   = discord.ui.TextInput(label="Novo Nome (vazio = manter)", required=False, max_length=40)
    c_emoji  = discord.ui.TextInput(label="Novo Emoji (vazio = manter)", required=False, max_length=50)
    c_max_ps = discord.ui.TextInput(label="Novo Máx PlayStyles (vazio = manter)", required=False, max_length=2)
    c_preco  = discord.ui.TextInput(label="Novo Preço % (vazio = manter)", required=False, max_length=5)

    async def on_submit(self, interaction: discord.Interaction):
        col_id = str(self.c_id).lower().strip()
        doc_id = f"col_{col_id}"
        record = await db_get(doc_id)
        if not record:
            return await interaction.response.send_message(f"❌ Coleção `{col_id}` não encontrada.", ephemeral=True)

        data = record["data"]
        changed = []

        if str(self.c_nome).strip():
            data["nome"] = str(self.c_nome).strip()
            changed.append(f"Nome → {data['nome']}")
        if str(self.c_emoji).strip():
            data["emoji"] = str(self.c_emoji).strip()
            changed.append(f"Emoji → {data['emoji']}")
        if str(self.c_max_ps).strip():
            try:
                data["max_playstyles"] = int(str(self.c_max_ps).strip())
                changed.append(f"Máx PS → {data['max_playstyles']}")
            except ValueError:
                pass
        if str(self.c_preco).strip():
            try:
                data["preco_adicional_pct"] = int(str(self.c_preco).strip())
                changed.append(f"Preço % → {data['preco_adicional_pct']}")
            except ValueError:
                pass

        if not changed:
            return await interaction.response.send_message("ℹ️ Nenhuma alteração foi feita.", ephemeral=True)

        await db_upsert(doc_id, data)
        await interaction.response.send_message(
            f"✅ Coleção `{col_id}` atualizada:\n" + "\n".join([f"• {c}" for c in changed]),
            ephemeral=True
        )


class DeletarColecaoModal(VLSModal, title="Deletar Coleção"):
    c_id        = discord.ui.TextInput(label="ID da Coleção", placeholder="Ex: base", max_length=30)
    confirmacao = discord.ui.TextInput(label="Digite CONFIRMAR para prosseguir", placeholder="CONFIRMAR", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        if str(self.confirmacao).strip() != "CONFIRMAR":
            return await interaction.response.send_message("❌ Operação cancelada.", ephemeral=True)

        col_id = str(self.c_id).lower().strip()
        doc_id = f"col_{col_id}"
        record = await db_get(doc_id)
        if not record:
            return await interaction.response.send_message(f"❌ Coleção `{col_id}` não encontrada.", ephemeral=True)

        await db_delete(doc_id)
        await interaction.response.send_message(f"🗑️ Coleção `{col_id}` removida.", ephemeral=True)


# ══════════════════════════════════════════════════════════
# MISSÕES PANEL
# ══════════════════════════════════════════════════════════

def build_missoes_panel(owner_id: int):
    embed = discord.Embed(
        title="📋 Painel de Missões",
        description="Crie e gerencie missões semanais e mensais.",
        color=discord.Color.blue()
    )
    embed.add_field(name="➕ Criar Missão", value="Define uma nova missão com nome, meta e recompensa.", inline=True)
    embed.add_field(name="🗑️ Deletar Missão", value="Remove uma missão pelo ID.", inline=True)
    embed.add_field(name="📋 Listar Missões", value="Exibe todas as missões ativas.", inline=True)
    embed.set_footer(text="← Voltar: use /admin novamente")
    return embed, MissoesView(owner_id)


class MissoesView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="➕ Criar Missão", style=discord.ButtonStyle.success, row=0)
    async def criar_missao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(CriarMissaoModal())

    @discord.ui.button(label="🗑️ Deletar Missão", style=discord.ButtonStyle.danger, row=0)
    async def deletar_missao(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(DeletarMissaoModal())

    @discord.ui.button(label="📋 Listar Missões", style=discord.ButtonStyle.secondary, row=0)
    async def listar_missoes(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.defer(thinking=True, ephemeral=True)
        missions = await get_missions()
        if not missions:
            return await interaction.followup.send("Nenhuma missão cadastrada.", ephemeral=True)

        lines = []
        for m in missions:
            rew = f"R$ {m.get('reward_value',0):,}" if m.get('reward_type') == 'money' else f"{m.get('reward_value',0)} coins" if m.get('reward_type') == 'coins' else "Jogador"
            lines.append(
                f"📌 **{m.get('nome', m['id'])}** (`{m['id']}`)\n"
                f"   {m['type'].upper()} | Meta: {m['threshold']} {m['criterion']} | Recompensa: {rew}"
            )
        await interaction.followup.send("**📋 Missões ativas:**\n" + "\n".join(lines), ephemeral=True)


class CriarMissaoModal(VLSModal, title="Criar Missão"):
    m_id         = discord.ui.TextInput(label="ID único (ex: gols_50)", placeholder="Sem espaços", max_length=40)
    m_nome       = discord.ui.TextInput(label="Nome de exibição", placeholder="Ex: Artilheiro da Semana", max_length=60)
    m_tipo       = discord.ui.TextInput(label="Tipo: semanal ou mensal", placeholder="semanal", max_length=8)
    m_criterio   = discord.ui.TextInput(label="Critério: vitorias/gols/partidas/recrutamentos", placeholder="gols", max_length=15)
    m_threshold  = discord.ui.TextInput(label="Meta numérica", placeholder="Ex: 50", max_length=6)

    async def on_submit(self, interaction: discord.Interaction):
        tipo = str(self.m_tipo).strip().lower()
        criterio = str(self.m_criterio).strip().lower()

        if tipo not in ["semanal", "mensal"]:
            return await interaction.response.send_message("❌ Tipo deve ser `semanal` ou `mensal`.", ephemeral=True)
        if criterio not in ["vitorias", "gols", "partidas", "recrutamentos"]:
            return await interaction.response.send_message("❌ Critério inválido.", ephemeral=True)
        try:
            threshold = int(str(self.m_threshold).strip())
        except ValueError:
            return await interaction.response.send_message("❌ Meta deve ser um número.", ephemeral=True)

        m_id = str(self.m_id).strip().lower().replace(" ", "_")
        doc_id = f"mission_{m_id}"

        # Pede recompensa em etapa 2
        _PENDING_PLAYER[interaction.user.id] = {
            "id": m_id,
            "nome": str(self.m_nome).strip(),
            "type": tipo,
            "criterion": criterio,
            "threshold": threshold,
        }
        view = ContinuarMissao2View(interaction.user.id)
        await interaction.response.send_message(
            "✅ **Dados básicos da missão salvos!** Clique no botão abaixo para definir as recompensas (Etapa 2/2).",
            view=view,
            ephemeral=True
        )

class CriarMissaoModal2(VLSModal, title="Criar Missão — Recompensa"):
    r_type     = discord.ui.TextInput(label="Tipo de recompensa: money, coins ou player", placeholder="money", max_length=10)
    r_value    = discord.ui.TextInput(label="Valor (dinheiro ou coins)", placeholder="Ex: 50000", max_length=10, default="0")
    r_player   = discord.ui.TextInput(label="ID do jogador (se reward=player, senão deixe vazio)", required=False, max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        r_type = str(self.r_type).strip().lower()
        if r_type not in ["money", "coins", "player"]:
            return await interaction.response.send_message("❌ Tipo de recompensa inválido.", ephemeral=True)
        try:
            r_value = int(str(self.r_value).strip())
        except ValueError:
            r_value = 0

        pending = _PENDING_PLAYER.pop(interaction.user.id, {})
        if not pending:
            return await interaction.response.send_message("❌ Sessão expirada. Comece novamente.", ephemeral=True)

        r_player = str(self.r_player).strip().lower() or None

        data = {
            **pending,
            "reward_type": r_type,
            "reward_value": r_value,
            "reward_player_id": r_player,
        }
        doc_id = f"mission_{pending['id']}"
        await db_upsert(doc_id, data)

        await interaction.response.send_message(
            f"✅ Missão **{data['nome']}** criada!\n"
            f"Tipo: {data['type']} | Meta: {data['threshold']} {data['criterion']} | "
            f"Recompensa: {r_type} {r_value}",
            ephemeral=True
        )

class DeletarMissaoModal(VLSModal, title="Deletar Missão"):
    m_id = discord.ui.TextInput(label="ID da Missão", placeholder="Ex: gols_50", max_length=40)
    confirmacao = discord.ui.TextInput(label="Digite CONFIRMAR", placeholder="CONFIRMAR", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        if str(self.confirmacao).strip() != "CONFIRMAR":
            return await interaction.response.send_message("❌ Operação cancelada.", ephemeral=True)

        doc_id = f"mission_{str(self.m_id).strip().lower()}"
        if not await db_get(doc_id):
            return await interaction.response.send_message("❌ Missão não encontrada.", ephemeral=True)

        await db_delete(doc_id)
        await interaction.response.send_message(f"🗑️ Missão `{self.m_id}` removida.", ephemeral=True)

# ══════════════════════════════════════════════════════════
# ECONOMIA PANEL
# ══════════════════════════════════════════════════════════

def build_economia_panel(owner_id: int):
    embed = discord.Embed(
        title="💰 Painel de Economia",
        description="Adicione ou remova saldo de membros do servidor.",
        color=discord.Color.green()
    )
    embed.add_field(name="➕ Add Dinheiro", value="Credita R$ no clube de um membro.", inline=True)
    embed.add_field(name="➖ Remover Dinheiro", value="Debita R$ do clube de um membro.", inline=True)
    embed.add_field(name="💎 Add VLS Coins", value="Credita Moedas Premium.", inline=True)
    embed.add_field(name="💎 Remover Coins", value="Debita Moedas Premium.", inline=True)
    embed.set_footer(text="← Voltar: use /admin novamente")
    return embed, EconomiaView(owner_id)


class EconomiaView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="➕ Add Dinheiro", style=discord.ButtonStyle.success, row=0)
    async def add_money(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(EconomiaModal(tipo="add_money"))

    @discord.ui.button(label="➖ Remover Dinheiro", style=discord.ButtonStyle.danger, row=0)
    async def rem_money(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(EconomiaModal(tipo="rem_money"))

    @discord.ui.button(label="💎 Add Coins", style=discord.ButtonStyle.primary, row=1)
    async def add_coins(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(EconomiaModal(tipo="add_coins"))

    @discord.ui.button(label="💎 Remover Coins", style=discord.ButtonStyle.danger, row=1)
    async def rem_coins(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(EconomiaModal(tipo="rem_coins"))


class EconomiaModal(VLSModal):
    user_id_input = discord.ui.TextInput(label="ID do usuário no Discord", placeholder="Ex: 123456789012345678", max_length=25)
    valor_input   = discord.ui.TextInput(label="Valor", placeholder="Ex: 50000", max_length=12)

    def __init__(self, tipo: str):
        labels = {
            "add_money": "Adicionar Dinheiro",
            "rem_money": "Remover Dinheiro",
            "add_coins": "Adicionar VLS Coins",
            "rem_coins": "Remover VLS Coins",
        }
        super().__init__(title=labels.get(tipo, "Economia"))
        self.tipo = tipo

    async def on_submit(self, interaction: discord.Interaction):
        try:
            uid = int(str(self.user_id_input).strip())
            valor = int(str(self.valor_input).strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID e Valor devem ser números.", ephemeral=True)

        if valor <= 0:
            return await interaction.response.send_message("❌ Valor deve ser positivo.", ephemeral=True)

        # Busca o perfil
        from database import db_get as _db_get
        record = await _db_get(f"user_{uid}")
        if not record:
            return await interaction.response.send_message(f"❌ Usuário `{uid}` não encontrado no banco.", ephemeral=True)

        profile = record["data"]

        if self.tipo == "add_money":
            profile["money"] = profile.get("money", 0) + valor
            label = f"R$ {valor:,} adicionado"
        elif self.tipo == "rem_money":
            profile["money"] = max(0, profile.get("money", 0) - valor)
            label = f"R$ {valor:,} removido"
        elif self.tipo == "add_coins":
            profile["premium_coins"] = profile.get("premium_coins", 0) + valor
            label = f"{valor} VLS Coins adicionado"
        elif self.tipo == "rem_coins":
            profile["premium_coins"] = max(0, profile.get("premium_coins", 0) - valor)
            label = f"{valor} VLS Coins removido"
        else:
            return

        await save_user_profile(uid, profile)
        await interaction.response.send_message(
            f"✅ **{label}** no clube de `{uid}`.\n"
            f"Saldo atual: R$ {profile.get('money',0):,} | {profile.get('premium_coins',0)} Coins",
            ephemeral=True
        )


# ══════════════════════════════════════════════════════════
# USUÁRIOS PANEL (Dar/Tirar Jogadores)
# ══════════════════════════════════════════════════════════

def build_usuarios_panel(owner_id: int):
    embed = discord.Embed(
        title="👥 Painel de Usuários",
        description="Distribua ou remova jogadores do inventário de membros.",
        color=discord.Color.orange()
    )
    embed.add_field(name="🎁 Dar Jogador", value="Envia uma carta para o inventário de um membro.", inline=True)
    embed.add_field(name="❌ Tirar Jogador", value="Remove uma carta do inventário por Instance ID.", inline=True)
    embed.add_field(name="📊 Ver Perfil", value="Exibe saldo e inventário de um membro.", inline=True)
    embed.set_footer(text="← Voltar: use /admin novamente")
    return embed, UsuariosView(owner_id)


class UsuariosView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="🎁 Dar Jogador", style=discord.ButtonStyle.success, row=0)
    async def dar_jogador(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(DarJogadorModal())

    @discord.ui.button(label="❌ Tirar Jogador", style=discord.ButtonStyle.danger, row=0)
    async def tirar_jogador(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(TirarJogadorModal())

    @discord.ui.button(label="📊 Ver Perfil", style=discord.ButtonStyle.secondary, row=0)
    async def ver_perfil(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(VerPerfilModal())


class DarJogadorModal(VLSModal, title="Dar Jogador a um Membro"):
    uid      = discord.ui.TextInput(label="ID do usuário no Discord", placeholder="Ex: 123456789012345678", max_length=25)
    p_busca  = discord.ui.TextInput(label="Nome ou busca do Jogador", placeholder="Ex: Tarik", max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(str(self.uid).strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID de usuário inválido.", ephemeral=True)

        target_record = await db_get(f"user_{user_id}")
        if not target_record:
            return await interaction.response.send_message(f"❌ Usuário `{user_id}` não encontrado.", ephemeral=True)

        players = await get_all_players()
        search_term = str(self.p_busca).strip().lower()
        matches = [p for p in players if search_term in p.get("name", "").lower() or search_term in p.get("id", "").lower()]
        
        if not matches:
            return await interaction.response.send_message(f"❌ Nenhum jogador encontrado contendo `{self.p_busca}`.", ephemeral=True)
            
        extra_data = {"target_user_id": user_id}
        
        if len(matches) == 1:
            data = matches[0]
            doc_id = data["id"]
            
            profile = target_record["data"]
            instanced = data.copy()
            instanced["instance_id"] = str(uuid.uuid4())[:8]
            instanced["original_pos"] = data["pos"]
            instanced["acquired_at"] = datetime.utcnow().isoformat()
            instanced.update({"goals": 0, "assists": 0, "saves": 0, "matches": 0, "mvps": 0, "yellow_cards": 0, "red_cards": 0, "xp": 0})
            
            profile.setdefault("inventory", []).append(instanced)
            await save_user_profile(user_id, profile)
            
            col_emoji = data.get("col_emoji", "✨")
            await interaction.response.send_message(
                f"🎁 **{col_emoji} {data['name']}** enviado para o usuário `{user_id}`!\n"
                f"Instance ID: `{instanced['instance_id']}`",
                ephemeral=True
            )
        else:
            view = PlayerSelectDropdownView("give", matches, interaction.user.id, extra_data)
            embed = discord.Embed(
                title="🔍 Múltiplos jogadores encontrados",
                description=f"Encontrei {len(matches)} jogadores correspondentes ao termo `{self.p_busca}`. Selecione qual deseja enviar:",
                color=discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class TirarJogadorModal(VLSModal, title="Remover Jogador de um Membro"):
    uid         = discord.ui.TextInput(label="ID do usuário no Discord", placeholder="Ex: 123456789012345678", max_length=25)
    instance_id = discord.ui.TextInput(label="Instance ID do jogador", placeholder="Ex: a1b2c3d4", max_length=36)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(str(self.uid).strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID de usuário inválido.", ephemeral=True)

        inst_id = str(self.instance_id).strip()
        record = await db_get(f"user_{user_id}")
        if not record:
            return await interaction.response.send_message(f"❌ Usuário `{user_id}` não encontrado.", ephemeral=True)

        profile = record["data"]
        original_count = len(profile.get("inventory", []))
        profile["inventory"] = [p for p in profile.get("inventory", []) if not p.get("instance_id", "").startswith(inst_id)]
        profile["starting_xi"] = [p for p in profile.get("starting_xi", []) if not p.get("instance_id", "").startswith(inst_id)]

        if len(profile["inventory"]) == original_count:
            return await interaction.response.send_message(f"❌ Jogador com instance `{inst_id}` não encontrado.", ephemeral=True)

        await save_user_profile(user_id, profile)
        await interaction.response.send_message(f"✅ Jogador `{inst_id}` removido do usuário `{user_id}`.", ephemeral=True)


class VerPerfilModal(VLSModal, title="Ver Perfil de Membro"):
    uid = discord.ui.TextInput(label="ID do usuário no Discord", placeholder="Ex: 123456789012345678", max_length=25)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(str(self.uid).strip())
        except ValueError:
            return await interaction.response.send_message("❌ ID inválido.", ephemeral=True)

        record = await db_get(f"user_{user_id}")
        if not record:
            return await interaction.response.send_message(f"❌ Usuário `{user_id}` não encontrado.", ephemeral=True)

        p = record["data"]
        inv_count = len(p.get("inventory", []))
        xi_count = len(p.get("starting_xi", []))

        embed = discord.Embed(
            title=f"📊 Perfil Admin — {p.get('club_name', '?')}",
            description=f"User ID: `{user_id}`",
            color=discord.Color.blurple()
        )
        embed.add_field(name="💰 Dinheiro", value=f"R$ {p.get('money',0):,}", inline=True)
        embed.add_field(name=f"{VLS_COINS_EMOJI} Coins", value=str(p.get("premium_coins", 0)), inline=True)
        embed.add_field(name="🔎 Olheiro", value=f"Nível {p.get('scout_level', 0)}", inline=True)
        embed.add_field(name="🎴 Inventário", value=f"{inv_count} cartas ({xi_count} escalados)", inline=True)
        embed.add_field(name="📋 Formação", value=p.get("formation", "4-3-3"), inline=True)
        wins = p.get("wins", 0); losses = p.get("losses", 0); draws = p.get("draws", 0)
        embed.add_field(name="📊 Record", value=f"{wins}V {draws}E {losses}D", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════════
# LOJA PANEL (Produtos Personalizados)
# ══════════════════════════════════════════════════════════

def build_loja_panel(owner_id: int):
    embed = discord.Embed(
        title="🛍️ Painel da Loja Customizada",
        description="Crie e gerencie produtos personalizados que os usuários podem comprar na loja.",
        color=discord.Color.brand_green()
    )
    embed.add_field(name="➕ Criar Produto", value="Adiciona um novo produto (pacote ou jogador direto) à loja.", inline=True)
    embed.add_field(name="🗑️ Deletar Produto", value="Remove um produto da loja por ID.", inline=True)
    embed.add_field(name="📋 Listar Produtos", value="Lista os produtos customizados ativos.", inline=True)
    embed.set_footer(text="← Voltar: use /admin novamente")
    return embed, LojaPanelView(owner_id)


class LojaPanelView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=180)
        self.owner_id = owner_id

    @discord.ui.button(label="➕ Criar Produto", style=discord.ButtonStyle.success, row=0)
    async def criar_produto(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(CriarProdutoModal())

    @discord.ui.button(label="🗑️ Deletar Produto", style=discord.ButtonStyle.danger, row=0)
    async def deletar_produto(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.send_modal(DeletarProdutoModal())

    @discord.ui.button(label="📋 Listar Produtos", style=discord.ButtonStyle.secondary, row=0)
    async def listar_produtos(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
        await interaction.response.defer(thinking=True, ephemeral=True)
        
        products = await db_get_prefix("loja_produto_")
        if not products:
            return await interaction.followup.send("⚠️ Nenhum produto personalizado cadastrado na loja.", ephemeral=True)
            
        desc = ""
        for p in products:
            p_data = p["data"]
            tipo_label = "📦 Pacote" if p_data.get("type") == "pacote" else "👤 Jogador Direto"
            desc += (
                f"🔹 **ID:** `{p_data['id']}`\n"
                f"**Produto:** {p_data.get('emoji', '📦')} **{p_data['name']}**\n"
                f"**Tipo:** {tipo_label} | **Preço:** {VLS_COINS_EMOJI} {p_data['price']:,} Coins\n"
                f"**Descrição:** {p_data.get('description', '')}\n"
                f"**Conteúdo:** `{p_data.get('items', [])}`\n\n"
            )
        
        embed = discord.Embed(
            title="🛍️ Produtos Customizados da Loja",
            description=desc,
            color=discord.Color.brand_green()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


class ProductTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Pacote (Pack)", value="pacote", emoji="📦", description="Contém múltiplos jogadores (aleatório ou todos)"),
            discord.SelectOption(label="Jogador Direto", value="jogador", emoji="👤", description="Vende um jogador específico diretamente")
        ]
        super().__init__(placeholder="Selecione o tipo de produto...", options=options, min_values=1, max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.view.product_type = self.values[0]
        await interaction.response.defer()


class ProductPlayersSelect(discord.ui.Select):
    def __init__(self, players):
        options = [
            discord.SelectOption(
                label=f"{p['name']} (Rated {p['over']})",
                value=p["id"].replace("player_", ""),
                description=f"Posição: {p.get('pos')} | Coleção: {p.get('col_nome', 'Comum')}"
            ) for p in players[:25]
        ]
        super().__init__(
            placeholder="Selecione os jogadores inclusos...",
            options=options,
            min_values=1,
            max_values=min(len(options), 25),
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_players = self.values
        await interaction.response.defer()


class ConfirmProductView(discord.ui.View):
    def __init__(self, owner_id: int, prod_name: str, prod_emoji: str, prod_desc: str, prod_price: int, players_pool: list):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.prod_name = prod_name
        self.prod_emoji = prod_emoji
        self.prod_desc = prod_desc
        self.prod_price = prod_price
        
        self.product_type = None
        self.selected_players = []
        
        self.add_item(ProductTypeSelect())
        self.add_item(ProductPlayersSelect(players_pool))

    @discord.ui.button(label="Confirmar Criação", emoji="✅", style=discord.ButtonStyle.success, row=2)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            return await interaction.response.send_message("❌ Acesso negado.", ephemeral=True)
            
        if not self.product_type:
            return await interaction.response.send_message("❌ Selecione o tipo de produto (Pacote ou Jogador Direto) primeiro.", ephemeral=True)
            
        if not self.selected_players:
            return await interaction.response.send_message("❌ Selecione pelo menos um jogador para o produto.", ephemeral=True)
            
        prod_id = str(uuid.uuid4())[:8]
        prod_data = {
            "id": prod_id,
            "name": self.prod_name,
            "emoji": self.prod_emoji,
            "description": self.prod_desc,
            "price": self.prod_price,
            "type": self.product_type,
            "items": self.selected_players
        }
        
        await db_upsert(f"loja_produto_{prod_id}", prod_data)
        
        for child in self.children:
            child.disabled = True
            
        embed = discord.Embed(
            title="🛍️ Produto Criado com Sucesso!",
            description=(
                f"O produto foi registrado na Loja Customizada.\n\n"
                f"**Nome:** {self.prod_emoji} {self.prod_name}\n"
                f"**ID:** `{prod_id}`\n"
                f"**Preço:** {VLS_COINS_EMOJI} {self.prod_price:,} Coins\n"
                f"**Tipo:** `{self.product_type}`\n"
                f"**Jogadores Inclusos:** {', '.join(self.selected_players)}"
            ),
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=self)


class CriarProdutoModal(VLSModal, title="Criar Produto Personalizado"):
    name        = discord.ui.TextInput(label="Nome do Produto", placeholder="Ex: Pacote Especial Copa", max_length=50)
    emoji       = discord.ui.TextInput(label="Emoji do Produto", placeholder="Ex: 📦 ou 🏆", max_length=50, required=False)
    description = discord.ui.TextInput(label="Descrição", placeholder="Ex: Pacote contendo jogadores lendários", style=discord.TextStyle.paragraph, max_length=150, required=False)
    price       = discord.ui.TextInput(label="Preço em VLS Coins", placeholder="Ex: 150", max_length=10)

    async def on_submit(self, interaction: discord.Interaction):
        p_name = str(self.name).strip()
        p_emoji = str(self.emoji).strip() if self.emoji else "📦"
        p_desc = str(self.description).strip() if self.description else ""
        
        try:
            p_price = int(str(self.price).strip())
            if p_price < 0:
                raise ValueError()
        except ValueError:
            return await interaction.response.send_message("❌ Preço inválido. Digite um número positivo.", ephemeral=True)
            
        players = await get_all_players()
        if not players:
            return await interaction.response.send_message("❌ Cadastre jogadores no banco de dados primeiro antes de criar produtos na loja.", ephemeral=True)
            
        view = ConfirmProductView(interaction.user.id, p_name, p_emoji, p_desc, p_price, players)
        embed = discord.Embed(
            title="🛍️ Configurar Conteúdo do Produto",
            description="Selecione o tipo do produto e quais jogadores estarão inclusos na loja usando os menus abaixo:",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class DeletarProdutoModal(VLSModal, title="Deletar Produto"):
    prod_id = discord.ui.TextInput(label="ID do Produto (8 caracteres)", placeholder="Ex: a1b2c3d4", max_length=8)

    async def on_submit(self, interaction: discord.Interaction):
        p_id = str(self.prod_id).strip()
        record = await db_get(f"loja_produto_{p_id}")
        if not record:
            return await interaction.response.send_message(f"❌ Produto `{p_id}` não encontrado.", ephemeral=True)
            
        await db_delete(f"loja_produto_{p_id}")
        await interaction.response.send_message(f"🗑️ Produto `{p_id}` removido da loja com sucesso.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(DashboardCog(bot))