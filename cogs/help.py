# -*- coding: utf-8 -*-
"""
VLS Guru - Cog de Ajuda
Central de comandos para jogadores, com navegação por categorias.
"""
import discord
from discord.ext import commands
from discord import app_commands

# Categorias do /ajuda — apenas comandos de jogadores, sem admin
HELP_CATEGORIES = [
    {
        "name": "💵 Economia & Mercado",
        "emoji": "💵",
        "commands": [
            ("`/saldo`", "Consulta seu saldo bancário e VLS Coins."),
            ("`/caixa`", "Abre uma caixa misteriosa gratuita (cooldown 8h)."),
            ("`/recrutar`", "Envia olheiros para recrutar um jogador aleatório (cooldown 10min)."),
            ("`/loja`", "Abre a loja de pacotes premium com 💎 Moedas."),
            ("`/transferir`", "Envia dinheiro ou VLS Coins para outro manager."),
            ("`/upar_olheiro`", "Melhora o nível do Olheiro para ter mais sorte no /recrutar."),
            ("`/missoes`", "Exibe missões ativas e permite resgatar recompensas."),
        ]
    },
    {
        "name": "🏪 Mercado de Transferências",
        "emoji": "🏪",
        "commands": [
            ("`/vender`", "Vende um jogador do seu inventário diretamente para a CPU (Quick Sell por 25%)."),
            ("`/mercado`", "Lista todos os jogadores disponíveis no catálogo global de transferências."),
            ("`/contratar`", "Pesquisa e contrata um jogador do catálogo global."),
        ]
    },
    {
        "name": "📋 Gestão do Clube",
        "emoji": "📋",
        "commands": [
            ("`/time`", "Exibe a prancheta tática visual com botões de Auto Escalar e Formação."),
            ("`/escalar`", "Escala jogadores nas posições da formação ativa."),
            ("`/banco`", "Remove um jogador da escalação titular."),
            ("`/elenco`", "Lista os titulares organizados por setor (Defesa, Meio, Ataque)."),
            ("`/titular`", "Detalhes dos titulares com atributos efetivos e química."),
            ("`/inventario`", "Lista todo o seu elenco com filtros por posição."),
            ("`/show`", "Ficha técnica completa de um jogador com atributos e stats."),
            ("`/tatico`", "Muda a formação ou a tática do time."),
            ("`/estadio`", "Renomeia ou faz upgrade do seu estádio."),
            ("`/perfil`", "Perfil do clube com conquistas, badges e botão de renomear."),
        ]
    },
    {
        "name": "⚔️ Partidas & Competições",
        "emoji": "⚔️",
        "commands": [
            ("`/desafio`", "Desafia outro clube para um amistoso PvP."),
            ("`/x1_aposta`", "Partida valendo dinheiro contra outro manager (wager)."),
            ("`/treino`", "Treina contra a CPU para ganhar XP de Afinidade (cooldown 1h)."),
            ("`/ranking`", "Classificação dos melhores managers do servidor."),
            ("`/campeonato`", "Informações e chaveamento do torneio ativo."),
        ]
    },
    {
        "name": "ℹ️ Informações",
        "emoji": "ℹ️",
        "commands": [
            ("`/sobre`", "Informações sobre o VLS Guru e seus desenvolvedores."),
        ]
    },
]


def build_help_embed(category_idx: int, total: int) -> discord.Embed:
    cat = HELP_CATEGORIES[category_idx]
    embed = discord.Embed(
        title=f"{cat['emoji']} {cat['name']}",
        description="Todos os comandos disponíveis nesta categoria:",
        color=discord.Color.blurple()
    )
    for cmd_name, cmd_desc in cat["commands"]:
        embed.add_field(name=cmd_name, value=cmd_desc, inline=False)

    embed.set_footer(text=f"Categoria {category_idx + 1}/{total} • VLS Guru 2026 • Use / para autocompletar")
    return embed


class HelpCog(commands.Cog, name="Ajuda"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ajuda", description="Central de ajuda com todos os comandos organizados por categoria.")
    async def ajuda(self, interaction: discord.Interaction):
        embed = build_help_embed(0, len(HELP_CATEGORIES))
        view = HelpView(current=0)
        await interaction.response.send_message(embed=embed, view=view)


class HelpView(discord.ui.View):
    def __init__(self, current: int = 0):
        super().__init__(timeout=120)
        self.current = current
        self.total = len(HELP_CATEGORIES)
        self._update_buttons()

    def _update_buttons(self):
        # Atualiza estado dos botões de navegação
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "prev":
                    child.disabled = self.current == 0
                elif child.custom_id == "next":
                    child.disabled = self.current == self.total - 1

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.blurple, custom_id="prev", row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current > 0:
            self.current -= 1
            self._update_buttons()
            embed = build_help_embed(self.current, self.total)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.blurple, custom_id="next", row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current < self.total - 1:
            self.current += 1
            self._update_buttons()
            embed = build_help_embed(self.current, self.total)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.defer()


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
