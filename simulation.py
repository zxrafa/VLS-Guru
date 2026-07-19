# -*- coding: utf-8 -*-
"""
VLS Guru - Motor de Simulação de Partida (Reboot)
Implementa simulação minuto a minuto com PlayStyles, química, tática, estamina e narração imersiva.
"""
import random
import math
from config import PLAYSTYLE_EMOJIS, TACTICS

# ==============================================================================
# MAPA DE ADJACÊNCIA POR FORMAÇÃO (para cálculo de química por pares)
# ==============================================================================
FORMATION_ADJACENCY = {
    "4-3-3": {
        "GK":  ["CB1", "CB2"],
        "CB1": ["GK", "CB2", "LB", "CDM"],
        "CB2": ["GK", "CB1", "RB", "CDM"],
        "LB":  ["CB1", "CM1"],
        "RB":  ["CB2", "CM2"],
        "CDM": ["CB1", "CB2", "CM1", "CM2"],
        "CM1": ["LB", "CDM", "LW", "ST"],
        "CM2": ["RB", "CDM", "RW", "ST"],
        "LW":  ["CM1", "ST"],
        "RW":  ["CM2", "ST"],
        "ST":  ["CM1", "CM2", "LW", "RW"],
    },
    "3-5-2": {
        "GK":  ["CB2"],
        "CB1": ["CB2", "LM", "CDM"],
        "CB2": ["GK", "CB1", "CB3", "CDM"],
        "CB3": ["CB2", "RM", "CDM"],
        "LM":  ["CB1", "CM1"],
        "RM":  ["CB3", "CM2"],
        "CDM": ["CB1", "CB2", "CB3", "CM1", "CM2"],
        "CM1": ["LM", "CDM", "ST1"],
        "CM2": ["RM", "CDM", "ST2"],
        "ST1": ["CM1", "ST2"],
        "ST2": ["CM2", "ST1"],
    },
    "4-2-4": {
        "GK":  ["CB1", "CB2"],
        "CB1": ["GK", "CB2", "LB", "CM1"],
        "CB2": ["GK", "CB1", "RB", "CM2"],
        "LB":  ["CB1", "LW"],
        "RB":  ["CB2", "RW"],
        "CM1": ["CB1", "CM2", "LW", "ST1"],
        "CM2": ["CB2", "CM1", "RW", "ST2"],
        "LW":  ["LB", "CM1", "ST1"],
        "RW":  ["RB", "CM2", "ST2"],
        "ST1": ["CM1", "LW", "ST2"],
        "ST2": ["CM2", "RW", "ST1"],
    },
    "4-4-2": {
        "GK":  ["CB1", "CB2"],
        "CB1": ["GK", "CB2", "LB", "CDM"],
        "CB2": ["GK", "CB1", "RB", "CDM"],
        "LB":  ["CB1", "LM"],
        "RB":  ["CB2", "RM"],
        "LM":  ["LB", "CM1"],
        "RM":  ["RB", "CM2"],
        "CDM": ["CB1", "CB2", "CAM"],
        "CAM": ["CDM", "CM1", "CM2"],
        "CM1": ["LM", "CAM", "ST1"],
        "CM2": ["RM", "CAM", "ST2"],
        "ST1": ["CM1", "ST2"],
        "ST2": ["CM2", "ST1"],
    },
    "5-4-1": {
        "GK":  ["CB2"],
        "CB1": ["CB2", "LB"],
        "CB2": ["GK", "CB1", "CB3", "CDM"],
        "CB3": ["CB2", "RB"],
        "LB":  ["CB1", "CM"],
        "RB":  ["CB3", "CM"],
        "CM":  ["LB", "RB", "CDM", "ST"],
        "CDM": ["CB2", "CM"],
        "LM":  ["LB", "CM"],
        "RM":  ["RB", "CM"],
        "ST":  ["CM"],
        "CAM1": ["CM", "ST"],
        "CAM2": ["CM", "ST"],
    },
    "3-4-3": {
        "GK":  ["CB2"],
        "CB1": ["CB2", "CM1"],
        "CB2": ["GK", "CB1", "CB3", "CDM"],
        "CB3": ["CB2", "CM2"],
        "CM1": ["CB1", "CAM"],
        "CM2": ["CB3", "CAM"],
        "CAM": ["CM1", "CM2", "CDM", "ST"],
        "CDM": ["CB2", "CAM"],
        "ST":  ["CAM", "LW", "RW"],
        "LW":  ["ST"],
        "RW":  ["ST"],
    },
    "4-2-3-1": {
        "GK":   ["CB1", "CB2"],
        "CB1":  ["GK", "CB2", "LB", "CDM1"],
        "CB2":  ["GK", "CB1", "RB", "CDM2"],
        "LB":   ["CB1", "LM"],
        "RB":   ["CB2", "RM"],
        "CDM1": ["CB1", "CDM2", "CAM", "LM"],
        "CDM2": ["CB2", "CDM1", "CAM", "RM"],
        "LM":   ["LB", "CDM1", "CAM"],
        "RM":   ["RB", "CDM2", "CAM"],
        "CAM":  ["CDM1", "CDM2", "LM", "RM", "ST"],
        "ST":   ["CAM"],
    },
    "4-1-4-1": {
        "GK":  ["CB1", "CB2"],
        "CB1": ["GK", "CB2", "LB", "CDM"],
        "CB2": ["GK", "CB1", "RB", "CDM"],
        "LB":  ["CB1", "LM"],
        "RB":  ["CB2", "RM"],
        "CDM": ["CB1", "CB2", "CM1", "CM2"],
        "LM":  ["LB", "CM1"],
        "RM":  ["RB", "CM2"],
        "CM1": ["LM", "CDM", "CM2", "ST"],
        "CM2": ["RM", "CDM", "CM1", "ST"],
        "ST":  ["CM1", "CM2"],
    },
    "3-2-5": {
        "GK":  ["CB2"],
        "CB1": ["CB2", "CM1"],
        "CB2": ["GK", "CB1", "CB3"],
        "CB3": ["CB2", "CM2"],
        "CM1": ["CB1", "CM2", "LW", "ST1"],
        "CM2": ["CB3", "CM1", "RW", "ST3"],
        "LW":  ["CM1", "ST1"],
        "RW":  ["CM2", "ST3"],
        "ST1": ["CM1", "LW", "ST2"],
        "ST2": ["ST1", "ST3"],
        "ST3": ["CM2", "RW", "ST2"],
    },
    "5-3-2": {
        "GK":  ["CB2"],
        "LB":  ["CB1", "CM1"],
        "CB1": ["LB", "CB2", "CDM"],
        "CB2": ["GK", "CB1", "CB3", "CDM"],
        "CB3": ["CB2", "RB", "CDM"],
        "RB":  ["CB3", "CM2"],
        "CDM": ["CB1", "CB2", "CB3", "CM1", "CM2"],
        "CM1": ["LB", "CDM", "CM2", "ST1"],
        "CM2": ["RB", "CDM", "CM1", "ST2"],
        "ST1": ["CM1", "ST2"],
        "ST2": ["CM2", "ST1"],
    },
    "5-2-3": {
        "GK":  ["CB2"],
        "LB":  ["CB1", "CM1"],
        "CB1": ["LB", "CB2", "CM1"],
        "CB2": ["GK", "CB1", "CB3"],
        "CB3": ["CB2", "RB", "CM2"],
        "RB":  ["CB3", "CM2"],
        "CM1": ["LB", "CB1", "CM2", "LW", "ST"],
        "CM2": ["RB", "CB3", "CM1", "RW", "ST"],
        "LW":  ["CM1", "ST"],
        "RW":  ["CM2", "ST"],
        "ST":  ["CM1", "CM2", "LW", "RW"],
    },
    "4-1-5": {
        "GK":  ["CB1", "CB2"],
        "LB":  ["CB1", "CDM"],
        "CB1": ["GK", "CB2", "LB", "CDM"],
        "CB2": ["GK", "CB1", "RB", "CDM"],
        "RB":  ["CB2", "CDM"],
        "CDM": ["CB1", "CB2", "LB", "RB", "LW", "RW", "ST2"],
        "LW":  ["CDM", "ST1"],
        "RW":  ["CDM", "ST3"],
        "ST1": ["LW", "ST2"],
        "ST2": ["CDM", "ST1", "ST3"],
        "ST3": ["RW", "ST2"],
    },
}

# ==============================================================================
# NARRATIVAS IMERSIVAS
# ==============================================================================
NARR_GOL = [
    "⚽ **GOOOL!** {atk} recebe passe cirúrgico de {ast}, domina no peito e bate cruzado sem chances para {gk}!",
    "⚽ **GOOOL!** Contra-ataque relâmpago! {atk} invade a área em velocidade absurda e toca na saída de {gk}!",
    "⚽ **GOOOL!** {ast} acha {atk} nas costas da zaga, que completa de cabeça para o fundo das redes!",
    "⚽ **GOOOL!** Chute de fora da área! {atk} acerta o ângulo e {gk} nem se mexe!",
    "⚽ **GOOOL!** Jogada de velocidade desconcertante! {atk} passa por {defensor} e encobre o goleiro com categoria!",
    "⚽ **GOOOL!** Cobrança de falta impecável de {atk}! A bola sobe, curva e entra no ângulo que {gk} não alcança!",
]
NARR_GOL_SEM_AST = [
    "⚽ **GOOOL!** {atk} aproveita rebote do goleiro e empurra para o gol vazio em velocidade de reação!",
    "⚽ **GOOOL!** Individual absoluto! {atk} faz fila na marcação e chuta sem ângulo, mas a bola entra!",
    "⚽ **GOOOL!** {atk} recebe de trás, gira em cima de {defensor} e bate no cantinho!",
]
NARR_DEFESA = [
    "🧤 **DEFENDEU!** {atk} bate firme no ângulo, mas {gk} voa e espalma de forma espetacular!",
    "🧤 **MILAGRE!** {atk} finaliza à queima-roupa e {gk} estica o braço para desviar na trave!",
    "🧤 **Goleiro seguro!** Chute de {atk} direto nas mãos de {gk}, que sai jogando com confiança.",
    "🧤 **Que defesa!** {atk} estava livre na área, mas {gk} antecipou o movimento e bloqueou com o corpo!",
]
NARR_DESARME = [
    "🛡️ **MARCAÇÃO IMPECÁVEL!** {atk} tentou o drible, mas {defensor} chegou limpo na bola e cortou o ataque.",
    "🛡️ **DESARMADO!** {defensor} leu a jogada de {atk} com perfeição e roubou a posse no campo defensivo.",
    "🛡️ **Marcação forte!** {defensor} pressiona {atk} e força o erro. A bola volta para o time defensivo.",
]
NARR_ERRO = [
    "💨 **Para fora!** {atk} recebe em boa posição, mas chuta por cima do travessão com a bola quicando mal.",
    "💥 **NA TRAVE!** {atk} acerta o ângulo, a bola supera {gk}, mas explode na trave e sai!",
    "🚩 **Impedimento!** A jogada era bonita, mas {atk} estava dois passos adiantado. Tiro de meta.",
    "💨 **Chute bloqueado!** {defensor} se joga na frente no momento certo e impede a finalização de {atk}.",
]
NARR_TRAVE = [
    "💥 **TRAVE!** {atk} chuta colocado, supera {gk}, e a bola estoura no poste direito! Quase!",
    "💥 **TRAVESSÃO!** Cabeceio potente de {atk}, {gk} não chegou, mas o travessão salvou!",
]


# ==============================================================================
# FUNÇÕES UTILITÁRIAS
# ==============================================================================

def get_pos_group(pos: str) -> str:
    """Agrupa posições em categorias funcionais para a lógica de simulação."""
    if pos == "GK":
        return "PO"
    if pos in ("CB", "LB", "RB", "LWB", "RWB", "CB1", "CB2", "CB3"):
        return "DFC"
    if pos in ("CDM", "CDM1", "CDM2", "CM", "CM1", "CM2", "CAM", "CAM1", "CAM2", "LM", "RM"):
        return "MID"
    if pos in ("ST", "ST1", "ST2", "ST3", "CF", "LW", "RW"):
        return "DC"
    return "MID"


def calculate_chemistry_bonus(starting_xi: list, formation: str) -> dict:
    """
    Calcula o bônus de química por pares de vizinhança na formação.
    Retorna {instance_id: bonus_total_acumulado}.

    Escala de cores (spec):
      - Laranja (+1): mesma nacionalidade
      - Verde   (+2): mesmo clube
      - Vermelha (+3): mesmo clube E mesma nacionalidade (substitui os outros)
    """
    adjacency = FORMATION_ADJACENCY.get(formation, FORMATION_ADJACENCY["4-3-3"])
    bonuses = {p["instance_id"]: 0 for p in starting_xi if "instance_id" in p}
    by_position = {p["pos"]: p for p in starting_xi if "pos" in p}

    for pos_a, neighbors in adjacency.items():
        player_a = by_position.get(pos_a)
        if not player_a:
            continue
        for pos_b in neighbors:
            player_b = by_position.get(pos_b)
            if not player_b or player_a["instance_id"] == player_b["instance_id"]:
                continue

            same_club    = bool(player_a.get("club"))    and player_a.get("club")    == player_b.get("club")
            same_country = bool(player_a.get("nationality")) and player_a.get("nationality") == player_b.get("nationality")

            if same_club and same_country:
                bonuses[player_a["instance_id"]] += 3   # Vermelha
            elif same_club:
                bonuses[player_a["instance_id"]] += 2   # Verde
            elif same_country:
                bonuses[player_a["instance_id"]] += 1   # Laranja

    return bonuses


def get_player_effective_stats(player: dict, chemistry_bonus: int, tactic: str, stamina: float = 100.0, crowd_mood: str = "alegria", torcida_level: int = 1) -> dict:
    """
    Calcula os atributos efetivos de um jogador considerando:
    1. Bônus de Química
    2. Bônus de Afinidade (XP/10)
    3. Penalidade de Estamina
    4. Multiplicadores de Tática
    5. Reações da Torcida e seu Nível (Upgrades)
    """
    is_gk = player.get("pos") == "GK"
    
    if is_gk:
        # GK mapping:
        # div (diving) -> defense
        # han (handling) -> pass_stat
        # kic (kicking) -> shoot
        # ref (reflexes) -> dribble
        # pos_stat (positioning) -> physical
        raw_shoot = player.get("kic", 75)
        raw_pass = player.get("han", 75)
        raw_dribble = player.get("ref", 75)
        raw_defense = player.get("div", 75)
        raw_physical = player.get("pos_stat", 75)
    else:
        # Outfield mapping:
        # sho (shooting) -> shoot
        # pas (passing) -> pass_stat
        # dri (dribbling) -> dribble
        # def (defending) -> defense
        # phy (physical) -> physical
        raw_shoot = player.get("sho", player.get("shoot", 75))
        raw_pass = player.get("pas", player.get("pass_stat", 75))
        raw_dribble = player.get("dri", player.get("dribble", 75))
        raw_defense = player.get("def", player.get("defense", 75))
        raw_physical = player.get("phy", player.get("physical", 75))

    base_vals = {
        "shoot": raw_shoot,
        "pass_stat": raw_pass,
        "dribble": raw_dribble,
        "defense": raw_defense,
        "physical": raw_physical
    }

    chem = max(0, chemistry_bonus)

    # Afinidade: nível = xp // 10, bônus = +0.5% por nível, teto de +5%
    xp = player.get("xp", 0)
    affinity_mult = 1.0 + min(0.05, (xp // 10) * 0.005)

    # Estamina: escala de 50% (vazio) a 100% (cheio) sobre o atributo final
    stamina_mult = 0.50 + 0.50 * (max(0.0, min(100.0, stamina)) / 100.0)

    eff = {}
    for attr, val in base_vals.items():
        val = val + chem
        val = int(val * affinity_mult * stamina_mult)
        eff[attr] = max(1, min(99, val))

    # Modificadores táticos
    t = tactic
    if t == "gegenpress":
        eff["defense"]  = min(99, int(eff["defense"]  * 1.20))
        eff["physical"] = min(99, int(eff["physical"] * 1.10))
    elif t == "tikitaka":
        eff["pass_stat"] = min(99, int(eff["pass_stat"] * 1.15))
        eff["dribble"]   = min(99, int(eff["dribble"]   * 1.10))
    elif t == "catenaccio":
        eff["defense"] = min(99, int(eff["defense"] * 1.30))
        eff["shoot"]   = max(1,  int(eff["shoot"]   * 0.85))
    elif t == "futebol_total":
        for attr in list(eff.keys()):
            eff[attr] = min(99, int(eff[attr] * 1.20))
    elif t == "park_the_bus":
        eff["defense"] = min(99, int(eff["defense"] * 1.50))
        eff["shoot"]   = max(1,  int(eff["shoot"]   * 0.65))

    # Modificadores da torcida (Upgrades reduzem penalidade de vaia e aumentam os bônus)
    if crowd_mood == "vaia":
        penalty = 0.10 - min(0.08, (torcida_level - 1) * 0.004)
        for attr in eff:
            eff[attr] = max(1, int(eff[attr] * (1.0 - penalty)))
    elif crowd_mood == "humor":
        bonus = 0.15 + min(0.10, (torcida_level - 1) * 0.005)
        eff["dribble"] = min(99, int(eff["dribble"] * (1.0 + bonus)))
        eff["pass_stat"] = min(99, int(eff["pass_stat"] * (1.0 + bonus)))
    elif crowd_mood == "empolgação":
        bonus = 0.20 + min(0.10, (torcida_level - 1) * 0.005)
        eff["shoot"] = min(99, int(eff["shoot"] * (1.0 + bonus)))
        eff["defense"] = max(1, int(eff["defense"] * 0.90))

    return eff


def _fmt(player: dict) -> str:
    """Formata o nome do jogador com emoji da coleção para uso na narração."""
    emoji = player.get("col_emoji", "✨")
    return f"{emoji} **{player.get('name', 'Jogador')}**"


# ==============================================================================
# MOTOR PRINCIPAL DE SIMULAÇÃO
# ==============================================================================

def run_match_simulation(
    p1_name: str,
    p2_name: str,
    p1_xi: list,
    p2_xi: list,
    p1_tactic: str,
    p2_tactic: str,
    p1_chem: dict,
    p2_chem: dict,
    p1_formation: str = "4-3-3",
    p2_formation: str = "4-3-3",
    p1_torcida_level: int = 1,
    p2_torcida_level: int = 1,
) -> dict:
    """
    Executa a simulação completa de uma partida de 90 minutos.
    Inclui reações da torcida, escanteios, pênaltis, faltas de bola parada
    e todos os 19 PlayStyles da liga com narrações customizadas.
    """

    # ── Estado do jogo ──────────────────────────────────────────────────────
    p1_goals = 0
    p2_goals = 0
    narration_log: list[str] = []
    scorers: list[dict] = []

    sent_off: set = set()
    yellow_cards: dict = {}

    p1_stamina = {p["instance_id"]: 100.0 for p in p1_xi if "instance_id" in p}
    p2_stamina = {p["instance_id"]: 100.0 for p in p2_xi if "instance_id" in p}

    stats = {
        "p1": {"shots": 0, "on_target": 0, "saves": 0, "corners": 0, "fouls": 0, "yellow": 0, "red": 0},
        "p2": {"shots": 0, "on_target": 0, "saves": 0, "corners": 0, "fouls": 0, "yellow": 0, "red": 0},
    }
    xg_data = {"p1": 0.0, "p2": 0.0}

    performance: dict = {}
    for p in p1_xi + p2_xi:
        performance[p["instance_id"]] = {
            "name": p.get("name", "?"),
            "goals": 0, "assists": 0, "saves": 0,
            "shots": 0, "on_target": 0, "xg": 0.0, "mvp": False,
        }

    from config import PLAYSTYLE_EMOJIS

    def active_from(xi: list, groups: list) -> list:
        return [p for p in xi if get_pos_group(p.get("pos", "CM")) in groups and p["instance_id"] not in sent_off]

    def any_active(xi: list) -> list:
        return [p for p in xi if p["instance_id"] not in sent_off]

    def pick(lst: list):
        return random.choice(lst) if lst else None

    def resolve_corner(minute, is_p1_atk, atk, gk, defensor, atk_k, def_k):
        stats[atk_k]["corners"] += 1
        narration_log.append(f"⏱️ **{minute:02d}'** — 🚩 **Escanteio!** O time do {'mandante' if is_p1_atk else 'visitante'} corre para a cobrança e levanta na área.")
        
        has_soco = "soco" in gk.get("playstyles", [])
        if has_soco and random.random() < 0.80:
            emoji = PLAYSTYLE_EMOJIS.get("soco", "👊")
            narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **DE SOCO!** {emoji} saiu {_fmt(gk)} corajoso no cruzamento e afastou o perigo!")
            return

        has_anjo = "anjo" in defensor.get("playstyles", [])
        if has_anjo and random.random() < 0.25:
            emoji = PLAYSTYLE_EMOJIS.get("anjo", "🛡️")
            narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **DE CABEÇA!** {_fmt(defensor)} afastou a bola {emoji} da área.")
            return

        has_cabeceio = "cabeceio_preciso" in atk.get("playstyles", [])
        cabeceio_success = random.random() < 0.80 if has_cabeceio else random.random() < 0.35
        
        if cabeceio_success:
            stats[atk_k]["shots"] += 1
            performance[atk["instance_id"]]["shots"] += 1
            
            has_espalmada = "espalmada" in gk.get("playstyles", [])
            gk_saved = random.random() < 0.60 if has_espalmada else random.random() < 0.50
            
            if not gk_saved:
                nonlocal p1_goals, p2_goals
                if is_p1_atk:
                    p1_goals += 1
                else:
                    p2_goals += 1
                stats[atk_k]["on_target"] += 1
                performance[atk["instance_id"]]["on_target"] += 1
                performance[atk["instance_id"]]["goals"] += 1
                scorers.append({"name": _fmt(atk), "minute": minute, "team": 1 if is_p1_atk else 2})
                
                if has_cabeceio:
                    emoji = PLAYSTYLE_EMOJIS.get("cabeceio_preciso", "👤")
                    narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **CABECEIO!** {emoji} **GOL DE CABEÇA DE {_fmt(atk)}!** Testada forte sem chances!")
                else:
                    narration_log.append(f"⏱️ **{minute:02d}'** — ⚽ **GOOOL!** {_fmt(atk)} sobe bem e desvia de cabeça para balançar a rede!")
            else:
                stats[def_k]["saves"] += 1
                performance[gk["instance_id"]]["saves"] += 1
                stats[atk_k]["on_target"] += 1
                performance[atk["instance_id"]]["on_target"] += 1
                
                if has_espalmada:
                    emoji = PLAYSTYLE_EMOJIS.get("espalmada", "🧤")
                    narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **ESPALMOU!** {emoji} **DEFESAÇA DE {_fmt(gk)}** no cabeceio de {_fmt(atk)}!")
                else:
                    narration_log.append(f"⏱️ **{minute:02d}'** — 🧤 **Defesaça!** {_fmt(gk)} se estica e espalma a bola aérea cabeceada por {_fmt(atk)}!")
        else:
            narration_log.append(f"⏱️ **{minute:02d}'** — 💨 **Para fora!** O cruzamento foi bom, mas {_fmt(atk)} cabeceia mal e a bola sai por cima.")

    minute = 0
    p1_crowd = "alegria"
    p2_crowd = "alegria"

    while minute < 90:
        minute += random.randint(3, 8)
        if minute > 90:
            minute = 90

        for pid in p1_stamina:
            decay = 1.30 if p1_tactic == "gegenpress" else 1.00
            p1_stamina[pid] = max(10.0, p1_stamina[pid] - random.uniform(2.0, 4.5) * decay)
        for pid in p2_stamina:
            decay = 1.30 if p2_tactic == "gegenpress" else 1.00
            p2_stamina[pid] = max(10.0, p2_stamina[pid] - random.uniform(2.0, 4.5) * decay)

        if p1_goals > p2_goals:
            p1_crowd = random.choices(["alegria", "humor"], weights=[70, 30])[0]
            p2_diff = p1_goals - p2_goals
            if p2_diff == 1:
                p2_crowd = random.choices(["empolgação", "alegria"], weights=[60, 40])[0]
            else:
                p2_crowd = random.choices(["vaia", "empolgação"], weights=[50, 50])[0]
        elif p2_goals > p1_goals:
            p2_crowd = random.choices(["alegria", "humor"], weights=[70, 30])[0]
            p1_diff = p2_goals - p1_goals
            if p1_diff == 1:
                p1_crowd = random.choices(["empolgação", "alegria"], weights=[60, 40])[0]
            else:
                p1_crowd = random.choices(["vaia", "empolgação"], weights=[50, 50])[0]
        else:
            p1_crowd = random.choices(["alegria", "empolgação"], weights=[90, 10])[0]
            p2_crowd = random.choices(["alegria", "empolgação"], weights=[90, 10])[0]

        p1_active = [p for p in p1_xi if p["instance_id"] not in sent_off]
        p2_active = [p for p in p2_xi if p["instance_id"] not in sent_off]

        p1_force = sum(
            sum(get_player_effective_stats(p, p1_chem.get(p["instance_id"], 0), p1_tactic, p1_stamina[p["instance_id"]], p1_crowd, p1_torcida_level).values())
            for p in p1_active
        ) or 1
        p2_force = sum(
            sum(get_player_effective_stats(p, p2_chem.get(p["instance_id"], 0), p2_tactic, p2_stamina[p["instance_id"]], p2_crowd, p2_torcida_level).values())
            for p in p2_active
        ) or 1

        prob_p1_attacks = p1_force / (p1_force + p2_force)
        is_p1_attack = random.random() < prob_p1_attacks

        atk_xi      = p1_xi      if is_p1_attack else p2_xi
        def_xi      = p2_xi      if is_p1_attack else p1_xi
        atk_stamina = p1_stamina if is_p1_attack else p2_stamina
        def_stamina = p2_stamina if is_p1_attack else p1_stamina
        atk_chem    = p1_chem    if is_p1_attack else p2_chem
        def_chem    = p2_chem    if is_p1_attack else p1_chem
        atk_tactic  = p1_tactic  if is_p1_attack else p2_tactic
        def_tactic  = p2_tactic  if is_p1_attack else p1_tactic
        atk_key     = "p1"       if is_p1_attack else "p2"
        def_key     = "p2"       if is_p1_attack else "p1"

        gk_list  = active_from(def_xi, ["PO"])
        def_list = active_from(def_xi, ["DFC", "MID"])
        mid_list = active_from(atk_xi, ["MID"])
        att_list = active_from(atk_xi, ["DC", "MID"])

        gk       = pick(gk_list)  or pick(any_active(def_xi))
        defensor = pick(def_list) or pick(any_active(def_xi))
        atacante = pick(att_list) or pick(any_active(atk_xi))
        passador = pick(mid_list) or pick(any_active(atk_xi))

        if not atacante or not defensor or not gk:
            continue

        if random.random() < 0.10:
            if is_p1_attack and p1_crowd in ["vaia", "empolgação", "humor"]:
                if p1_crowd == "vaia":
                    narration_log.append(f"⏱️ **{minute:02d}'** — 📣 A torcida mandante vaiando e protestando nas arquibancadas! O time joga desconcentrado.")
                elif p1_crowd == "empolgação":
                    narration_log.append(f"⏱️ **{minute:02d}'** — 📣 **Canto ensurdecedor!** A torcida do {p1_name} empurra o time rumo ao ataque!")
                elif p1_crowd == "humor":
                    narration_log.append(f"⏱️ **{minute:02d}'** — 📣 **Olê, Olê!** A torcida se diverte e grita 'Olê' a cada passe do {p1_name}!")
            elif not is_p1_attack and p2_crowd in ["vaia", "empolgação", "humor"]:
                if p2_crowd == "vaia":
                    narration_log.append(f"⏱️ **{minute:02d}'** — 📣 Sob fortes vaias de seus adeptos, o time do {p2_name} tenta se organizar em campo.")
                elif p2_crowd == "empolgação":
                    narration_log.append(f"⏱️ **{minute:02d}'** — 📣 **Pressão total!** A torcida do {p2_name} canta forte exigindo raça e gols!")
                elif p2_crowd == "humor":
                    narration_log.append(f"⏱️ **{minute:02d}'** — 📣 A torcida visitante aplaude de pé o futebol bonito do {p2_name}!")

        atk_eff = get_player_effective_stats(atacante, atk_chem.get(atacante["instance_id"], 0), atk_tactic, atk_stamina[atacante["instance_id"]], p1_crowd if is_p1_attack else p2_crowd, p1_torcida_level if is_p1_attack else p2_torcida_level)
        def_eff = get_player_effective_stats(defensor, def_chem.get(defensor["instance_id"], 0), def_tactic, def_stamina[defensor["instance_id"]], p2_crowd if is_p1_attack else p1_crowd, p2_torcida_level if is_p1_attack else p1_torcida_level)
        gk_eff  = get_player_effective_stats(gk,       def_chem.get(gk["instance_id"], 0),       def_tactic, def_stamina[gk["instance_id"]], p2_crowd if is_p1_attack else p1_crowd, p2_torcida_level if is_p1_attack else p1_torcida_level)

        if random.random() < 0.12:
            stats[def_key]["fouls"] += 1
            roll = random.random()
            def_id = defensor["instance_id"]

            if roll < 0.25:
                yellow_cards[def_id] = yellow_cards.get(def_id, 0) + 1
                stats[def_key]["yellow"] += 1
                if yellow_cards[def_id] >= 2:
                    sent_off.add(def_id)
                    stats[def_key]["red"] += 1
                    narration_log.append(f"⏱️ **{minute:02d}'** — 🟥 **SEGUNDO AMARELO!** {_fmt(defensor)} comete nova falta e é expulso!")
                else:
                    narration_log.append(f"⏱️ **{minute:02d}'** — 🟨 **Cartão Amarelo!** {_fmt(defensor)} é advertido pelo árbitro.")
            elif roll < 0.28:
                sent_off.add(def_id)
                stats[def_key]["red"] += 1
                narration_log.append(f"⏱️ **{minute:02d}'** — 🟥 **CARTÃO VERMELHO DIRETO!** {_fmt(defensor)} entra por trás e é expulso!")

            if random.random() < 0.18:
                narration_log.append(f"⏱️ **{minute:02d}'** — 🚨 **PÊNALTI!** {_fmt(defensor)} derruba {_fmt(atacante)} dentro da grande área!")
                
                batedores = [p for p in atk_xi if p["instance_id"] not in sent_off]
                batedor = max(batedores, key=lambda x: get_player_effective_stats(x, atk_chem.get(x["instance_id"], 0), atk_tactic, atk_stamina[x["instance_id"]])["shoot"])
                
                has_espalmada = "espalmada" in gk.get("playstyles", [])
                gk_save_chance = 0.35 if has_espalmada else 0.24
                
                roll_pen = random.random()
                if roll_pen < 0.76 - gk_save_chance:
                    if is_p1_attack:
                        p1_goals += 1
                    else:
                        p2_goals += 1
                    stats[atk_key]["shots"] += 1
                    stats[atk_key]["on_target"] += 1
                    performance[batedor["instance_id"]]["shots"] += 1
                    performance[batedor["instance_id"]]["on_target"] += 1
                    performance[batedor["instance_id"]]["goals"] += 1
                    scorers.append({"name": _fmt(batedor), "minute": minute, "team": 1 if is_p1_attack else 2})
                    narration_log.append(f"⏱️ **{minute:02d}'** — ⚽ **GOOOL DE PÊNALTI!** {_fmt(batedor)} bate com firmeza no canto e fuzila {_fmt(gk)}!")
                elif roll_pen < 0.76:
                    stats[def_key]["saves"] += 1
                    performance[gk["instance_id"]]["saves"] += 1
                    stats[atk_key]["shots"] += 1
                    stats[atk_key]["on_target"] += 1
                    performance[batedor["instance_id"]]["shots"] += 1
                    performance[batedor["instance_id"]]["on_target"] += 1
                    
                    if has_espalmada:
                        emoji = PLAYSTYLE_EMOJIS.get("espalmada", "🧤")
                        narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **ESPALMOU!** {emoji} **DEFESAÇA DE {_fmt(gk)}** espalmando a cobrança de pênalti de {_fmt(batedor)}!")
                    else:
                        narration_log.append(f"⏱️ **{minute:02d}'** — 🧤 **DEFENDEU!** {_fmt(gk)} pula muito bem e espalha a cobrança de pênalti de {_fmt(batedor)}!")
                    
                    resolve_corner(minute, is_p1_attack, atacante, gk, defensor, atk_key, def_key)
                else:
                    stats[atk_key]["shots"] += 1
                    performance[batedor["instance_id"]]["shots"] += 1
                    narration_log.append(f"⏱️ **{minute:02d}'** — ❌ **PRA FORA!** {_fmt(batedor)} bate mal e manda direto para a linha de fundo!")
                continue

            elif random.random() < 0.25:
                batedores = [p for p in atk_xi if p["instance_id"] not in sent_off]
                batedor = next((p for p in batedores if "bola_parada" in p.get("playstyles", [])), None)
                if not batedor:
                    batedor = max(batedores, key=lambda x: get_player_effective_stats(x, atk_chem.get(x["instance_id"], 0), atk_tactic, atk_stamina[x["instance_id"]])["shoot"])
                
                has_bolaparada = "bola_parada" in batedor.get("playstyles", [])
                foul_goal_chance = 0.60 if has_bolaparada else 0.15
                
                stats[atk_key]["shots"] += 1
                performance[batedor["instance_id"]]["shots"] += 1
                
                if random.random() < foul_goal_chance:
                    if is_p1_attack:
                        p1_goals += 1
                    else:
                        p2_goals += 1
                    stats[atk_key]["on_target"] += 1
                    performance[batedor["instance_id"]]["on_target"] += 1
                    performance[batedor["instance_id"]]["goals"] += 1
                    scorers.append({"name": _fmt(batedor), "minute": minute, "team": 1 if is_p1_attack else 2})
                    
                    if has_bolaparada:
                        emoji = PLAYSTYLE_EMOJIS.get("bola_parada", "🎯")
                        narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **BATIDA DE CATEGORIA! GOLAÇO DE FALTA de {_fmt(batedor)}!** {emoji} Bola no ângulo!")
                    else:
                        narration_log.append(f"⏱️ **{minute:02d}'** — ⚽ **GOOOL DE FALTA!** {_fmt(batedor)} bate com curva por cima da barreira e balança as redes!")
                else:
                    if random.random() < 0.60:
                        stats[def_key]["saves"] += 1
                        performance[gk["instance_id"]]["saves"] += 1
                        stats[atk_key]["on_target"] += 1
                        performance[batedor["instance_id"]]["on_target"] += 1
                        narration_log.append(f"⏱️ **{minute:02d}'** — 🧤 **Defesa segura!** {_fmt(gk)} acompanha bem o voo da bola e segura na falta cobrada por {_fmt(batedor)}.")
                    else:
                        narration_log.append(f"⏱️ **{minute:02d}'** — 💨 **Por cima!** {_fmt(batedor)} cobra forte demais e a bola passa tirando tinta do travessão.")
                continue

        interceptors = [p for p in def_xi if "interceptacao" in p.get("playstyles", []) and p["instance_id"] not in sent_off]
        if interceptors and random.random() < 0.18:
            interceptor = random.choice(interceptors)
            if random.random() < 0.85:
                emoji = PLAYSTYLE_EMOJIS.get("interceptacao", "🛡️")
                narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **Jogada interceptada!** {emoji} {_fmt(interceptor)} corta o passe do adversário e sai jogando normalmente.")
                continue

        has_ima = "ima_no_pe" in atacante.get("playstyles", [])
        control_fail_chance = 0.10
        if has_ima:
            control_fail_chance = 0.05
            if random.random() < 0.20:
                emoji = PLAYSTYLE_EMOJIS.get("ima_no_pe", "🧲")
                narr_options = [
                    f"⏱️ **{minute:02d}'** — {emoji} **Dominio espetacular** de {_fmt(atacante)}!",
                    f"⏱️ **{minute:02d}'** — {emoji} **MATADA NO PEITO!** {_fmt(atacante)} pos a bola para dormir!",
                    f"⏱️ **{minute:02d}'** — {emoji} Categoria refinada {_fmt(atacante)}! dominou e saiu jogando."
                ]
                narration_log.append(random.choice(narr_options))

        if random.random() < control_fail_chance:
            narration_log.append(f"⏱️ **{minute:02d}'** — 💨 **Controle falho!** {_fmt(atacante)} não consegue dominar a bola e perde a posse para {_fmt(defensor)}.")
            continue

        has_solidez = "solidez" in defensor.get("playstyles", [])
        if has_solidez and random.random() < 0.80:
            emoji = PLAYSTYLE_EMOJIS.get("solidez", "🧱")
            if random.random() < 0.50:
                narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **Desarme providencial** de {_fmt(defensor)}!")
            else:
                narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **Belo Desarme!** {_fmt(defensor)} acabou com o ataque de {_fmt(atacante)} {emoji}!")
            continue

        skill_stars = atacante.get("skill_moves", 1)
        dribble_chance = 0.30 + (skill_stars - 1) * 0.12
        has_malvadeza = "malvadeza" in atacante.get("playstyles", [])
        has_rapid     = "rapid"     in atacante.get("playstyles", [])

        if has_malvadeza:
            dribble_chance += 0.35
        if has_rapid:
            dribble_chance += 0.15

        dribble_chance = min(0.95, dribble_chance)
        dribble_ok = random.random() < dribble_chance

        if not dribble_ok:
            has_perdepress = "perde_pressiona" in defensor.get("playstyles", [])
            if has_perdepress and random.random() < 0.60:
                emoji = PLAYSTYLE_EMOJIS.get("perde_pressiona", "🔄")
                narration_log.append(
                    f"⏱️ **{minute:02d}'** — {emoji} **Perde-Pressiona!** "
                    f"{_fmt(defensor)} perde o duelo momentaneamente mas reage em décimos de segundo e rouba a bola de {_fmt(atacante)}."
                )
            else:
                narration_log.append(f"⏱️ **{minute:02d}'** — {random.choice(NARR_DESARME).format(atk=_fmt(atacante), defensor=_fmt(defensor))}")
            continue

        if has_malvadeza and random.random() < 0.40:
            emoji = PLAYSTYLE_EMOJIS.get("malvadeza", "🕺")
            narrs = [
                f"⏱️ **{minute:02d}'** — {emoji} **QUE JOGADA LINDA!** {_fmt(atacante)} deu um drible magistral em {_fmt(defensor)} e fez ele comer poeira!",
                f"⏱️ **{minute:02d}'** — {emoji} {_fmt(defensor)} abriu as pernas e tomou uma **CANETAÇA LINDA** de {_fmt(atacante)}!",
                f"⏱️ **{minute:02d}'** — {emoji} Chapéu lindo de {_fmt(atacante)} em {_fmt(defensor)}!",
                f"⏱️ **{minute:02d}'** — {emoji} **JOGADA LINDA!** {_fmt(atacante)} cortou {def_key} de forma plástica e agilizou o jogo!"
            ]
            narration_log.append(random.choice(narrs))
        elif has_rapid and random.random() < 0.35:
            emoji = PLAYSTYLE_EMOJIS.get("rapid", "⚡")
            narrs = [
                f"⏱️ **{minute:02d}'** — {emoji} **JA FOI!** {_fmt(atacante)} deixou {_fmt(defensor)} pra trás na velocidade!",
                f"⏱️ **{minute:02d}'** — {emoji} **TCHAUU!** {_fmt(atacante)} ganhou de {_fmt(defensor)} na velocidade e fez ele comer poeira!"
            ]
            narration_log.append(random.choice(narrs))

        has_tecnica = passador and "tecnica" in passador.get("playstyles", [])
        has_trivela = passador and "trivela" in passador.get("playstyles", [])
        has_achada  = passador and "achada"  in passador.get("playstyles", [])

        pass_success_chance = 0.75
        if has_tecnica:
            pass_success_chance += 0.10
        if has_trivela:
            pass_success_chance += 0.05
        if atk_tactic == "tikitaka":
            pass_success_chance += 0.10

        if random.random() > pass_success_chance:
            narration_log.append(
                f"⏱️ **{minute:02d}'** — ❌ **Passe interceptado!** {_fmt(passador) if passador else _fmt(atacante)} erra o passe e {_fmt(defensor)} limpa o perigo."
            )
            continue

        xg_boost = 0.0
        if has_achada and random.random() < 0.40:
            emoji = PLAYSTYLE_EMOJIS.get("achada", "👁️")
            xg_boost += 0.20
            narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **QUE PASSE!** **Achada impressionante** de {_fmt(passador)} deixando {_fmt(atacante)} na cara do gol!")
        elif has_trivela and random.random() < 0.20:
            emoji = PLAYSTYLE_EMOJIS.get("trivela", "☄️")
            narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **ESPETACULAR!** {_fmt(passador)} deu uma trivela na bola e deu um lindo passe para {_fmt(atacante)}!")

        stats[atk_key]["shots"] += 1
        performance[atacante["instance_id"]]["shots"] += 1

        xg_base = atk_eff["shoot"] / (atk_eff["shoot"] + def_eff["defense"] * 0.5 + gk_eff["defense"] * 0.5)
        xg_base += xg_boost

        has_chapada = "chapada" in atacante.get("playstyles", [])
        if has_chapada and random.random() < 0.35:
            if random.random() < 0.70:
                emoji = PLAYSTYLE_EMOJIS.get("chapada", "☄️")
                if is_p1_attack:
                    p1_goals += 1
                else:
                    p2_goals += 1
                stats[atk_key]["on_target"] += 1
                performance[atacante["instance_id"]]["on_target"] += 1
                performance[atacante["instance_id"]]["goals"] += 1
                scorers.append({"name": _fmt(atacante), "minute": minute, "team": 1 if is_p1_attack else 2})
                narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **CHAPADA!** {emoji} **GOLAÇO NA GAVETA de {_fmt(atacante)}!** A curva foi perfeita!")
                continue

        has_superchute = "superchute" in atacante.get("playstyles", [])
        if has_superchute:
            xg_base += 0.10
            if random.random() < 0.25:
                emoji = PLAYSTYLE_EMOJIS.get("superchute", "🚀")
                narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **SuperChute!** {_fmt(atacante)} arma o chute potente de fora da área!")

        has_acrobata = "acrobata" in atacante.get("playstyles", [])
        if has_acrobata and random.random() < 0.15:
            tipo_ac = random.choices(["voleio", "tesoura", "bicicleta"], weights=[5, 3, 2])[0]
            xg_base += 0.08
            emoji = PLAYSTYLE_EMOJIS.get("acrobata", "🤸")
            
            if random.random() < 0.40:
                if is_p1_attack:
                    p1_goals += 1
                else:
                    p2_goals += 1
                stats[atk_key]["on_target"] += 1
                performance[atacante["instance_id"]]["on_target"] += 1
                performance[atacante["instance_id"]]["goals"] += 1
                scorers.append({"name": _fmt(atacante), "minute": minute, "team": 1 if is_p1_attack else 2})
                
                if tipo_ac == "voleio":
                    narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **QUE GOLAÇO!!!** {_fmt(atacante)} meteu um lindo **VOLEIO** e mandou pro fundo do gol!")
                elif tipo_ac == "tesoura":
                    narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **GOLAÇO!!!** {_fmt(atacante)} dominou e chutou com a bola no ar (Voleio Lateral/Tesoura)!")
                else:
                    narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **DE BICICLETA MINHA NOSSA! GOOOOOL DE {_fmt(atacante)}!** Pintura espetacular!")
                continue
            else:
                narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} {_fmt(atacante)} arrisca um lindo {tipo_ac} acrobático na área!")

        has_anjo = "anjo" in defensor.get("playstyles", [])
        if has_anjo and random.random() < 0.25:
            xg_base -= 0.12
            emoji = PLAYSTYLE_EMOJIS.get("anjo", "🛡️")
            narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **Cabeceio defensivo!** {_fmt(defensor)} sobe soberano e desvia a bola antes de {_fmt(atacante)}.")

        xg_val = min(0.95, max(0.04, xg_base))
        xg_data[atk_key] += xg_val
        performance[atacante["instance_id"]]["xg"] += xg_val

        wf_stars = atacante.get("weak_foot", 1)
        chance_pe_bom = 0.40 + (wf_stars - 1) * 0.10
        if random.random() < 0.40 and random.random() > chance_pe_bom:
            if random.random() < 0.55:
                narration_log.append(f"⏱️ **{minute:02d}'** — 💨 **Chute torto!** {_fmt(atacante)} finaliza com o pé fraco e a bola sai longe.")
            else:
                stats[def_key]["saves"] += 1
                performance[gk["instance_id"]]["saves"] += 1
                narration_log.append(f"⏱️ **{minute:02d}'** — 🧤 **Defesa tranquila!** {_fmt(atacante)} bate fraco com o pé ruim e {_fmt(gk)} defende.")
            continue

        has_encaixada = "encaixada" in gk.get("playstyles", [])
        has_espalmada = "espalmada" in gk.get("playstyles", [])
        has_arremesso = "arremesso_especial" in gk.get("playstyles", [])

        if random.random() < xg_val:
            if has_encaixada and random.random() < 0.25:
                stats[def_key]["saves"] += 1
                performance[gk["instance_id"]]["saves"] += 1
                stats[atk_key]["on_target"] += 1
                performance[atacante["instance_id"]]["on_target"] += 1
                emoji = PLAYSTYLE_EMOJIS.get("encaixada", "🧤")
                if random.random() < 0.50:
                    narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **Encaixada!** {_fmt(gk)} agarra firme o chute de {_fmt(atacante)} e sai jogando.")
                else:
                    narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **Defendeu {_fmt(gk)}!** Encaixou com facilidade o chute de {_fmt(atacante)} e botou para o campo.")
                continue

            if has_espalmada and random.random() < 0.60:
                stats[def_key]["saves"] += 1
                performance[gk["instance_id"]]["saves"] += 1
                stats[atk_key]["on_target"] += 1
                performance[atacante["instance_id"]]["on_target"] += 1
                emoji = PLAYSTYLE_EMOJIS.get("espalmada", "🧤")
                narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **ESPALMOU!** Defesaça de {_fmt(gk)} salvando o gol cara a cara!")
                resolve_corner(minute, is_p1_attack, atacante, gk, defensor, atk_key, def_key)
                continue

            if is_p1_attack:
                p1_goals += 1
            else:
                p2_goals += 1

            performance[atacante["instance_id"]]["goals"] += 1
            performance[atacante["instance_id"]]["on_target"] += 1
            stats[atk_key]["on_target"] += 1

            has_assist = random.random() < (0.75 if has_tecnica else 0.68)
            assist_name = ""
            if has_assist and passador and passador["instance_id"] != atacante["instance_id"]:
                performance[passador["instance_id"]]["assists"] += 1
                assist_name = _fmt(passador)

            scorers.append({"name": _fmt(atacante), "minute": minute, "team": 1 if is_p1_attack else 2})

            if assist_name:
                if has_tecnica and random.random() < 0.30:
                    emoji = PLAYSTYLE_EMOJIS.get("tecnica", "🔮")
                    msg = f"⏱️ **{minute:02d}'** — {emoji} **QUE JOGADA!!!** {_fmt(passador)} fez jogada impressionante e desconcertou {_fmt(defensor)}, servindo para o gol de {_fmt(atacante)}!"
                elif has_trivela and random.random() < 0.30:
                    emoji = PLAYSTYLE_EMOJIS.get("trivela", "☄️")
                    msg = f"⏱️ **{minute:02d}'** — {emoji} **ESPETACULAR!** {_fmt(passador)} deu uma trivela linda na bola e deu um lindo passe para {_fmt(atacante)} empurrar para as redes!"
                else:
                    msg = random.choice(NARR_GOL).format(atk=_fmt(atacante), ast=assist_name, gk=_fmt(gk), defensor=_fmt(defensor))
            else:
                msg = random.choice(NARR_GOL_SEM_AST).format(atk=_fmt(atacante), gk=_fmt(gk), defensor=_fmt(defensor))
            narration_log.append(f"⏱️ **{minute:02d}'** — {msg}")

        else:
            roll_outcome = random.random()
            if roll_outcome < 0.55:
                stats[def_key]["saves"] += 1
                performance[gk["instance_id"]]["saves"] += 1
                performance[atacante["instance_id"]]["on_target"] += 1
                stats[atk_key]["on_target"] += 1

                if has_arremesso and random.random() < 0.15:
                    emoji = PLAYSTYLE_EMOJIS.get("arremesso_especial", "👐")
                    if random.random() < 0.40:
                        if is_p1_attack:
                            p1_goals += 1
                        else:
                            p2_goals += 1
                        performance[atacante["instance_id"]]["goals"] += 1
                        scorers.append({"name": _fmt(atacante), "minute": minute, "team": 1 if is_p1_attack else 2})
                        narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **ARREMEÇO ESPECIAL!** Lançamento rápido de {_fmt(gk)} para {_fmt(atacante)} fuzilar pro gol!")
                    else:
                        narration_log.append(f"⏱️ **{minute:02d}'** — {emoji} **Lançamento rápido!** {_fmt(gk)} recolhe a bola e dá um arremesso longo colocando o time no ataque.")
                else:
                    narration_log.append(f"⏱️ **{minute:02d}'** — {random.choice(NARR_DEFESA).format(atk=_fmt(atacante), gk=_fmt(gk), defensor=_fmt(defensor))}")
                
                if random.random() < 0.55:
                    resolve_corner(minute, is_p1_attack, atacante, gk, defensor, atk_key, def_key)

            elif roll_outcome < 0.70:
                narration_log.append(
                    f"⏱️ **{minute:02d}'** — "
                    f"{random.choice(NARR_TRAVE).format(atk=_fmt(atacante), gk=_fmt(gk), defensor=_fmt(defensor))}"
                )
                if random.random() < 0.30:
                    resolve_corner(minute, is_p1_attack, atacante, gk, defensor, atk_key, def_key)
            else:
                narration_log.append(
                    f"⏱️ **{minute:02d}'** — "
                    f"{random.choice(NARR_ERRO).format(atk=_fmt(atacante), gk=_fmt(gk), defensor=_fmt(defensor))}"
                )

    # ── MVP da Partida ────────────────────────────────────────────────────────
    best_score = -1.0
    best_pid = None
    for pid, perf_data in performance.items():
        score = (
            perf_data["goals"]     * 3.0 +
            perf_data["assists"]   * 2.0 +
            perf_data["saves"]     * 1.5 +
            perf_data["on_target"] * 0.5
        )
        if score > best_score:
            best_score = score
            best_pid = pid

    mvp_name = "Nenhum destaque"
    if best_pid:
        performance[best_pid]["mvp"] = True
        mvp_name = performance[best_pid]["name"]

    return {
        "p1_goals":   p1_goals,
        "p2_goals":   p2_goals,
        "scorers":    scorers,
        "stats":      stats,
        "xg":         xg_data,
        "narration":  narration_log,
        "performance": performance,
        "mvp":        mvp_name,
        "p1_xi":      p1_xi,
        "p2_xi":      p2_xi,
        "p1_formation": p1_formation,
        "p2_formation": p2_formation,
    }
