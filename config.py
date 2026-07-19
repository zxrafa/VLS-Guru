# -*- coding: utf-8 -*-
"""
VLS Guru - Configurações e Constantes do Reboot
"""

# IDs de usuários com acesso total ao painel admin, mesmo sem ser admin de servidor
ALLOWED_ADMIN_IDS: set[int] = {338704196180115458, 1411893056516391034, 792144300666126336, 1267656061503143948}

# Emojis e Moedas
VLS_COINS_EMOJI = "<:VLScoins:1517258837004914848>"

PLAYSTYLE_EMOJIS = {
    "tecnica": "<:Tecnica:1517284475057344542>",
    "trivela": "<:Trivela:1517284434670260234>",
    "rapid": "<:Rapid:1517284399765520472>",
    "anjo": "<:Anjo:1517284298087071855>",
    "arremesso_especial": "<:ArremessoEspecial:1517284265233219584>",
    "encaixada": "<:Encaixada:1517284224821104711>",
    "acrobata": "<:Acrobata:1517284020789182576>",
    "superchute": "<:SuperChute:1517283994688028732>",
    "malvadeza": "<:Malvadeza:1517283961762746430>",
    "perde_pressiona": "<:PerdePressiona:1517283755222503615>",
    "ima_no_pe": "<:ImaNoPe:1517283715393257653>",
    "bola_parada": "<:BolaParada:1527128049068544134>",
    "interceptacao": "<:Interceptacao:1527128054760083526>",
    "solidez": "<:Solidez:1527128060501954681>",
    "soco": "<:Soco:1527128074573971506>",
    "chapada": "<:Chapada:1527128080563572779>",
    "achada": "<:Achada:1527128085756117012>",
    "cabeceio_preciso": "<:CabeceioPreciso:1527128090692681748>",
    "espalmada": "<:Espalmada:1527128096631816257>",
}

# Ambientação & Emojis do Jogo
EMOJI_ESTADIO = "🏟️"
EMOJI_CLIMA_SOL = "☀️"
EMOJI_CLIMA_GAROA = "🌦️"
EMOJI_CLIMA_CHUVA = "🌧️"
EMOJI_CLIMA_NUVEM = "☁️"
EMOJI_ESCALACAO = "📋"
EMOJI_MANDANTE = "🏠"
EMOJI_VISITANTE = "✈️"
EMOJI_CHUTE = "👟"
EMOJI_GOL = "⚽"
EMOJI_DEFESA = "🧤"
EMOJI_ERRO = "❌"
EMOJI_TRAVE = "💥"
EMOJI_IMPEDIMENTO = "🚩"
EMOJI_FALTA = "⚠️"
EMOJI_CARTAO_AMARELO = "🟨"
EMOJI_CARTAO_VERMELHO = "🟥"
EMOJI_ESCANTEIO = "🚩"
EMOJI_POSSE = "🔄"
EMOJI_APITO_FINAL = "🏁"
EMOJI_MVP = "👑"

# Categorias de Posições
EMOJI_JOGADOR_GK = "🧤"
EMOJI_JOGADOR_DF = "🛡️"
EMOJI_JOGADOR_MC = "⚙️"
EMOJI_JOGADOR_AT = "🔥"

# Posições e Compatibilidade para Escalação
POSITIONS_ALL = [
    "GK", "CB", "LB", "RB", "LWB", "RWB", "CDM", "CM", "CAM", "LM", "RM", "LW", "RW", "ST", "CF"
]

POSITION_COMPATIBILITY = {
    # Goleiro — só joga de GK
    "GK":  ["GK"],
    # Zagueiros
    "CB":  ["CB", "LB", "RB"],
    "LB":  ["LB", "CB", "CDM"],
    "RB":  ["RB", "CB", "CDM"],
    "LWB": ["LWB", "LB", "LM", "CDM"],
    "RWB": ["RWB", "RB", "RM", "CDM"],
    # Meias defensivos — jogam de CM, Laterais e Meias pelos lados
    "CDM": ["CDM", "CM", "LB", "RB", "LM", "RM"],
    # Meia central — joga de CAM, CDM e meias pelos lados
    "CM":  ["CM", "CAM", "CDM", "LM", "RM", "LW", "RW"],
    # Meia atacante — joga de CM, meias pelos lados e CDM
    "CAM": ["CAM", "CM", "LM", "RM", "CDM"],
    # Meias pelos lados
    "LM":  ["LM", "CM", "CAM", "CDM", "LW"],
    "RM":  ["RM", "CM", "CAM", "CDM", "RW"],
    # Pontas — LW↔RW são intercambiáveis
    "LW":  ["LW", "LM", "RW", "ST"],
    "RW":  ["RW", "RM", "LW", "ST"],
    # Atacantes — ST joga de LW e RW também
    "ST":  ["ST", "CF", "LW", "RW"],
    "CF":  ["CF", "ST", "CAM"],
}

# Táticas de Time
TACTICS = {
    "padrao": {
        "name": "Padrão",
        "desc": "Sem alterações táticas.",
        "effect": "Equilíbrio padrão"
    },
    "gegenpress": {
        "name": "Gegenpress",
        "desc": "+60% desarme pós-perda; dreno de stamina 30% mais rápido.",
        "effect": "+60% desarme, +30% perda de stamina"
    },
    "tikitaka": {
        "name": "Tiki-Taka",
        "desc": "+15% precisão de passe; +10% organização; +25% de vulnerabilidade defensiva se falhar.",
        "effect": "+15% passe, +10% posse, +25% vulnerabilidade"
    },
    "catenaccio": {
        "name": "Catenaccio",
        "desc": "+30% força defensiva; +15% contra-ataque; -15% sucesso ofensivo.",
        "effect": "+30% defesa, +15% contra-ataque, -15% ataque"
    },
    "futebol_total": {
        "name": "Futebol Total",
        "desc": "+20% em finalizações, desarmes, recuperações e passes; -15% precisão defensiva.",
        "effect": "+20% em ações gerais, -15% precisão de linha"
    },
    "park_the_bus": {
        "name": "Park the Bus",
        "desc": "+50% força defensiva; -35% de precisão nos ataques.",
        "effect": "+50% defesa, -35% ataque"
    }
}

# Formações Válidas
FORMATIONS_ALL = [
    "4-3-3", "4-2-4", "4-2-3-1", "4-4-2", "3-5-2", "5-4-1", "3-4-3", "4-1-4-1",
    "3-2-5", "5-3-2", "5-2-3", "4-1-5"
]

# Configurações do Olheiro
SCOUT_LEVEL_MAX = 20
SCOUT_BASE_UPGRADE_COST = 50000  # nivel * 50_000

# Conquistas Padrão
ACHIEVEMENTS_LIST = [
    {"id": "artilheiro_iniciante", "category": "gols", "name": "Artilheiro Iniciante", "description": "Marque 50 gols com seus jogadores", "threshold": 50, "reward_type": "money", "reward_value": 10000, "secret": False},
    {"id": "artilheiro_lendario", "category": "gols", "name": "Artilheiro Lendário", "description": "Marque 500 gols no total", "threshold": 500, "reward_type": "coins", "reward_value": 50, "secret": False},
    {"id": "titulo_primeiro", "category": "titulos", "name": "Primeiro Grito", "description": "Vença 1 campeonato", "threshold": 1, "reward_type": "money", "reward_value": 25000, "secret": False},
    {"id": "rico_milionario", "category": "economia", "name": "Manager Milionário", "description": "Acumule um saldo de 1.000.000 de dinheiro", "threshold": 1000000, "reward_type": "coins", "reward_value": 100, "secret": False},
    {"id": "colecionador_elenco", "category": "colecao", "name": "Elenco Galáctico", "description": "Possua 50 ou mais cartas em seu inventário", "threshold": 50, "reward_type": "money", "reward_value": 30000, "secret": False},
    {"id": "mestre_olheiro", "category": "olheiro", "name": "Olho Clínico", "description": "Atinja o nível 20 de Olheiro", "threshold": 20, "reward_type": "coins", "reward_value": 150, "secret": False},
    {"id": "virada_historica", "category": "secretas", "name": "Milagre em Campo", "description": "Vença uma partida revertendo desvantagem de 3 ou mais gols", "threshold": 1, "reward_type": "coins", "reward_value": 200, "secret": True},
    {"id": "sorte_divina", "category": "secretas", "name": "Sorte dos Deuses", "description": "Obtenha uma carta com overall 90 ou mais no recrutamento", "threshold": 1, "reward_type": "money", "reward_value": 50000, "secret": True}
]
