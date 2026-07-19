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
            ("`/upar_torcida`", "Melhora o nível da sua torcida para apoiar o time nos jogos."),
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
            ("`/playstyle`", "Exibe informações e efeitos de todos os Playstyles."),
        ]
    },
]

PLAYSTYLE_INFO = {
    "tecnica": {
        "name": "Técnica",
        "desc": "Aumenta em 3% a chance de assistência e reduz em 10% a chance de errar domínios e passes.",
        "effect": "🔮 +3% assist; -10% erro controle/passe",
        "narration": [
            "*\"QUE JOGADA!!! (Player) fez uma jogada impressionante e desconcertou (inimigo)\"*",
            "*\"INCRIVEL!!! (Player) fez um DOMINIO impressionante e organizou o jogo\"*"
        ]
    },
    "trivela": {
        "name": "Trivela",
        "desc": "Aumenta a precisão de passes em 5% com efeito de trivela.",
        "effect": "🎯 +5% precisão de passes",
        "narration": [
            "*\"ESPETACULAR!!! (jogador) deu uma trivela na bola e deu um LIIIIIIINDO passe para (jogador 2)\"*",
            "*\"QUE GOLAÇOOOOO DE (jogador) DE TRIVELA COM BASTANTE CURVA ENCOBRIU (GK)\"*"
        ]
    },
    "rapid": {
        "name": "Rapid",
        "desc": "Garante 15% a mais de chance de vencer duelos na velocidade contra defensores.",
        "effect": "⚡ +15% de velocidade nos duelos",
        "narration": [
            "*\"JA FOI!!! (player) deixou (inimigo) pra trás na velocidade\"*",
            "*\"TCHAUU!!! (Player) ganhou de (inimigo) na velocidade e fez ele comer poeira\"*"
        ]
    },
    "anjo": {
        "name": "Anjo",
        "desc": "Garante 25% de chance de afastar cruzamentos e jogadas de cabeça na defesa.",
        "effect": "🛡️ +25% de corte aéreo defensivo",
        "narration": [
            "*\"DE CABEÇA! (player) afastou a bola\"*"
        ]
    },
    "arremesso_especial": {
        "name": "Arremesso Especial (GK)",
        "desc": "Goleiros ganham 15% de chance de dar um arremesso longo gerando assistência rápida de contra-ataque.",
        "effect": "👐 15% chance assistência direta no rebote",
        "narration": [
            "*\"ARREMEÇO LONGO DO (GOLEIRO) PARA DEIXAR (JOGADOR) NA CARA DO GOL E MANDAR PARA AS REDES!\"*"
        ]
    },
    "encaixada": {
        "name": "Encaixada (GK)",
        "desc": "Goleiros ganham 25% a mais de chance de segurar e reter a bola sem dar rebote.",
        "effect": "🧤 +25% de encaixe seguro",
        "narration": [
            "*\"DEFESAÇA DO GOLEIRO!!! (goleiro) encaixa a bola no chute de (jogador inimigo) e sai jogando\"*",
            "*\"DEFENDEU (goleiro) Encaixou com facilidade o chute de (jogador) e botou a bola pra campo\"*"
        ]
    },
    "acrobata": {
        "name": "Acrobata",
        "desc": "Aumenta chance de finalizações acrobáticas: +5% voleio, +3% tesoura e +2% bicicleta.",
        "effect": "🤸 +5% Voleio | +3% Tesoura | +2% Bicicleta",
        "narration": [
            "*\"QUE GOLAÇOOOOO!!! (JOGADOR) METEU UM LINDO VOLEIO E MANDOU PRO FUNDO DO GOL!\"*",
            "*\"GOLAÇOOOOOOOOO (JOGADOR) DOMINOU E CHUTOU COM A BOLA NO AR E FEZ O GOL\"*",
            "*\"(JOGADOR) DE BICILETA MINHA NOSSA! MIIINHA NOSSA SENHORA!!! GOOOOOOOOOOL\"*"
        ]
    },
    "superchute": {
        "name": "SuperChute",
        "desc": "Aumenta a precisão de finalizações de fora da área em 10% (xG do chute).",
        "effect": "🚀 +10% precisão fora da área",
        "narration": [
            "*\"GOLAÇOOOOOOO!!! (Player) Chutou com uma força fenomenal de fora da area semmm chance pro (goleiro)\"*",
            "*\"GOLLLLLLL!! (Player) Chutou de longe com força e fuzilooou (goleiro)\"*"
        ]
    },
    "malvadeza": {
        "name": "Malvadeza",
        "desc": "Aumenta a chance de dribles plásticos bem sucedidos em 35%.",
        "effect": "🕺 +35% sucesso em dribles",
        "narration": [
            "*\"QUE JOGADA LINDA!!! (Player) Deu um drible magistral em (inimigo) e fez ele comer poeira\"*",
            "*\"(Inimigo) abriu as pernas e tomou uma CANETAÇA LINDA de (Player)\"*",
            "*\"Chapéu lindo de (jogador) em (inimigo)\"*",
            "*\"JOGADA LINDA!!! (Player) cortou (inimigo 1) e (inimigo 2) e agilizou o jogo\"*"
        ]
    },
    "perde_pressiona": {
        "name": "Perde-Pressiona",
        "desc": "Dá 60% de chance de o jogador recuperar a bola logo após perdê-la.",
        "effect": "🔄 60% chance de recuperação pós-perda",
        "narration": [
            "*\"DESARMOU E SAIU JOGANDO! (PLAYER) fez um lindo desarme em (Inimigo) apos o time perder a bola\"*"
        ]
    },
    "ima_no_pe": {
        "name": "Ímã no Pé",
        "desc": "Garante 95% de chance de o jogador dominar com sucesso passes longos ou bolas cruzadas.",
        "effect": "🧲 95% chance de domínio perfeito",
        "narration": [
            "*\"Dominio espetacular de (jogador)\"*",
            "*\"MATADA NO PEITO! (jogador) pos a bola para dormir\"*",
            "*\"Categoria refinada (jogador)! dominou e saiu jogando\"*"
        ]
    },
    "bola_parada": {
        "name": "Bola Parada",
        "desc": "Aumenta a taxa de conversão de faltas diretas em gol para 60%.",
        "effect": "🎯 60% precisão de cobrança de falta",
        "narration": [
            "*\"BATIDA DE CATEGORIA GOLAÇO DE FALTA de (jogador)\"*"
        ]
    },
    "interceptacao": {
        "name": "Interceptação",
        "desc": "Dá 85% de chance de interceptar e cortar passes adversários.",
        "effect": "🛡️ 85% chance de cortar passe",
        "narration": [
            "*\"Jogada interceptada! (jogador) Sai jogando normalmente\"*"
        ]
    },
    "solidez": {
        "name": "Solidez",
        "desc": "Jogadores defensivos ganham 80% de chance de realizar desarmes rápidos logo após o atacante tentar um drible.",
        "effect": "🧱 80% de chance de desarme anti-drible",
        "narration": [
            "*\"Desarme providencial de (jogador)\"*",
            "*\"Belo Desarme! (jogador) Acabou com o ataque de (adversario)\"*"
        ]
    },
    "soco": {
        "name": "Soco (GK)",
        "desc": "Goleiros ganham 80% de chance de afastar cruzamentos e escanteios dando um soco na bola.",
        "effect": "👊 80% chance afastar cruzamento",
        "narration": [
            "*\"DE SOCO! saiu (Goleiro) no cruzamento\"*"
        ]
    },
    "chapada": {
        "name": "Chapada",
        "desc": "Garante 70% de acerto em finalizações colocadas mirando a gaveta (ângulo).",
        "effect": "☄️ 70% precisão de chute colocado",
        "narration": [
            "*\"CHAPADA! GOLAÇO NA GAVETA de (jogador)\"*"
        ]
    },
    "achada": {
        "name": "Achada",
        "desc": "Garante 40% de chance de dar um passe genial, aumentando em 20% o xG do chute do companheiro.",
        "effect": "👁️ 40% chance passe genial (+20% xG)",
        "narration": [
            "*\"QUE PASSE! ACHADA IMPRESSIONANTE DE (jogador)\"*"
        ]
    },
    "cabeceio_preciso": {
        "name": "Cabeceio Preciso",
        "desc": "Dá 80% de precisão de cabeceio direcionado ao gol em cruzamentos de escanteios ou laterais.",
        "effect": "💥 80% chance gol de cabeceio",
        "narration": [
            "*\"CABECEIO ! GOL DE CABEÇA DE (jogador)\"*"
        ]
    },
    "espalmada": {
        "name": "Espalmada (GK)",
        "desc": "Goleiros ganham 60% de chance de desviar ou espalmar a bola pro lado em chutes cara a cara (1v1).",
        "effect": "🧤 60% chance de espalmar em chutes cara a cara",
        "narration": [
            "*\"ESPALMOU! DEFESAÇA DE (Goleiro)\"*"
        ]
    }
}

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


class PlaystyleDropdown(discord.ui.Select):
    def __init__(self):
        options = []
        from config import PLAYSTYLE_EMOJIS
        for key, value in PLAYSTYLE_INFO.items():
            emoji = PLAYSTYLE_EMOJIS.get(key, "✨")
            options.append(discord.SelectOption(
                label=value["name"],
                value=key,
                description=value["effect"][:100],
                emoji=emoji if not emoji.startswith("<") else None
            ))
        super().__init__(placeholder="Escolha um Playstyle para ver detalhes...", options=options)

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        value = PLAYSTYLE_INFO[key]
        from config import PLAYSTYLE_EMOJIS
        emoji = PLAYSTYLE_EMOJIS.get(key, "✨")
        
        embed = discord.Embed(
            title=f"{emoji} Playstyle: {value['name']}",
            description=f"**Descrição:**\n{value['desc']}\n\n**Efeito em Jogo:**\n`{value['effect']}`",
            color=discord.Color.gold()
        )
        narr_text = "\n".join(value["narration"])
        embed.add_field(name="🎙️ Narrações em Jogo", value=narr_text, inline=False)
        
        # Mantém o dropdown ativo para trocar de playstyle
        view = discord.ui.View(timeout=120)
        view.add_item(PlaystyleDropdown())
        await interaction.response.edit_message(embed=embed, view=view)


class HelpCog(commands.Cog, name="Ajuda"):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="ajuda", description="Central de ajuda com todos os comandos organizados por categoria.")
    async def ajuda(self, interaction: discord.Interaction):
        embed = build_help_embed(0, len(HELP_CATEGORIES))
        view = HelpView(current=0)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="playstyle", description="Mostra detalhes e efeitos de todos os Playstyles em jogo.")
    async def playstyle(self, interaction: discord.Interaction):
        if interaction.user.id != 338704196180115458:
            return await interaction.response.send_message("❌ Este comando está em fase de testes e indisponível no momento.", ephemeral=True)
        embed = discord.Embed(
            title="✨ Catálogo de Playstyles - VLS Guru",
            description="Selecione um Playstyle no menu abaixo para ver sua descrição detalhada, efeitos em jogo e narrações correspondentes.",
            color=discord.Color.gold()
        )
        view = discord.ui.View(timeout=120)
        view.add_item(PlaystyleDropdown())
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
