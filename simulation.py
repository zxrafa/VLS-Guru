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
    if pos in ("ST", "ST1", "ST2", "CF", "LW", "RW"):
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


def get_player_effective_stats(player: dict, chemistry_bonus: int, tactic: str, stamina: float = 100.0) -> dict:
    """
    Calcula os atributos efetivos de um jogador considerando:
    1. Bônus de Química
    2. Bônus de Afinidade (XP/10)
    3. Penalidade de Estamina
    4. Multiplicadores de Tática
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
) -> dict:
    """
    Executa a simulação completa de uma partida de 90 minutos.

    Retorna um dicionário com:
      - p1_goals / p2_goals: placar final
      - scorers: lista de artilheiros com minuto e time
      - stats: estatísticas brutas por equipe (chutes, defesas, etc.)
      - xg: xG acumulado por equipe
      - narration: log completo de lances em ordem cronológica
      - performance: estatísticas individuais por instance_id
      - mvp: nome do melhor em campo
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
        "p1": {"shots": 0, "on_target": 0, "saves": 0, "corners": random.randint(1, 7), "fouls": 0, "yellow": 0, "red": 0},
        "p2": {"shots": 0, "on_target": 0, "saves": 0, "corners": random.randint(1, 7), "fouls": 0, "yellow": 0, "red": 0},
    }
    xg_data = {"p1": 0.0, "p2": 0.0}

    performance: dict = {}
    for p in p1_xi + p2_xi:
        performance[p["instance_id"]] = {
            "name": p.get("name", "?"),
            "goals": 0, "assists": 0, "saves": 0,
            "shots": 0, "on_target": 0, "xg": 0.0, "mvp": False,
        }

    # ── Helpers internos ────────────────────────────────────────────────────
    def active_from(xi: list, groups: list) -> list:
        return [p for p in xi if get_pos_group(p.get("pos", "CM")) in groups and p["instance_id"] not in sent_off]

    def any_active(xi: list) -> list:
        return [p for p in xi if p["instance_id"] not in sent_off]

    def pick(lst: list):
        return random.choice(lst) if lst else None

    # ── Loop de minutos ─────────────────────────────────────────────────────
    minute = 0
    while minute < 90:
        minute += random.randint(3, 8)
        if minute > 90:
            minute = 90

        # Decaimento de estamina
        for pid in p1_stamina:
            decay = 1.30 if p1_tactic == "gegenpress" else 1.00
            p1_stamina[pid] = max(10.0, p1_stamina[pid] - random.uniform(2.0, 4.5) * decay)
        for pid in p2_stamina:
            decay = 1.30 if p2_tactic == "gegenpress" else 1.00
            p2_stamina[pid] = max(10.0, p2_stamina[pid] - random.uniform(2.0, 4.5) * decay)

        # ── Determinação de ataque ───────────────────────────────────────────
        p1_active = [p for p in p1_xi if p["instance_id"] not in sent_off]
        p2_active = [p for p in p2_xi if p["instance_id"] not in sent_off]

        p1_force = sum(
            sum(get_player_effective_stats(p, p1_chem.get(p["instance_id"], 0), p1_tactic, p1_stamina[p["instance_id"]]).values())
            for p in p1_active
        ) or 1
        p2_force = sum(
            sum(get_player_effective_stats(p, p2_chem.get(p["instance_id"], 0), p2_tactic, p2_stamina[p["instance_id"]]).values())
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

        # Escolhe os protagonistas do lance
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

        atk_eff = get_player_effective_stats(atacante, atk_chem.get(atacante["instance_id"], 0), atk_tactic, atk_stamina[atacante["instance_id"]])
        def_eff = get_player_effective_stats(defensor, def_chem.get(defensor["instance_id"], 0), def_tactic, def_stamina[defensor["instance_id"]])
        gk_eff  = get_player_effective_stats(gk,       def_chem.get(gk["instance_id"], 0),       def_tactic, def_stamina[gk["instance_id"]])

        # ── EVENTO: Falta / Cartão ───────────────────────────────────────────
        if random.random() < 0.11:
            stats[def_key]["fouls"] += 1
            roll = random.random()
            def_id = defensor["instance_id"]

            if roll < 0.35:
                # Cartão amarelo
                yellow_cards[def_id] = yellow_cards.get(def_id, 0) + 1
                stats[def_key]["yellow"] += 1
                if yellow_cards[def_id] >= 2:
                    sent_off.add(def_id)
                    stats[def_key]["red"] += 1
                    narration_log.append(
                        f"⏱️ **{minute:02d}'** — 🟥 **SEGUNDO AMARELO!** {_fmt(defensor)} comete nova falta tática e é expulso de campo!"
                    )
                else:
                    narration_log.append(
                        f"⏱️ **{minute:02d}'** — 🟨 **Cartão Amarelo!** {_fmt(defensor)} para o contra-ataque com falta dura e é advertido pelo árbitro."
                    )
            elif roll < 0.40:
                # Vermelho direto
                sent_off.add(def_id)
                stats[def_key]["red"] += 1
                narration_log.append(
                    f"⏱️ **{minute:02d}'** — 🟥 **CARTÃO VERMELHO DIRETO!** {_fmt(defensor)} entra com brutalidade por trás e é expulso imediatamente!"
                )
            continue

        # ── EVENTO: Domínio / Imã no Pé ─────────────────────────────────────
        # PlayStyle "ima_no_pe": 95% de domínio perfeito (evita erro de controle)
        has_ima = "ima_no_pe" in atacante.get("playstyles", [])
        control_fail_chance = 0.10  # 10% base de perder o controle da bola
        if has_ima:
            control_fail_chance = 0.05  # apenas 5% com Imã no Pé
            if random.random() < 0.15:  # 15% de chance de gerar narração do PlayStyle
                narration_log.append(
                    f"⏱️ **{minute:02d}'** — {PLAYSTYLE_EMOJIS['ima_no_pe']} **Imã no Pé!** "
                    f"{_fmt(atacante)} domina de primeira com perfeição técnica e já parte para a jogada seguinte."
                )

        if random.random() < control_fail_chance:
            narration_log.append(
                f"⏱️ **{minute:02d}'** — 💨 **Controle falho!** {_fmt(atacante)} não consegue dominar a bola e perde a posse para {_fmt(defensor)}."
            )
            continue

        # ── EVENTO: Drible ────────────────────────────────────────────────────
        skill_stars = atacante.get("skill_moves", 1)
        dribble_chance = 0.30 + (skill_stars - 1) * 0.12  # 30%–78% (spec)
        has_malvadeza = "malvadeza" in atacante.get("playstyles", [])
        has_rapid     = "rapid"     in atacante.get("playstyles", [])

        if has_malvadeza:
            dribble_chance += 0.35  # spec: +35%
        if has_rapid:
            dribble_chance += 0.15  # spec: +15% disputa de velocidade

        dribble_chance = min(0.95, dribble_chance)
        dribble_ok = random.random() < dribble_chance

        if not dribble_ok:
            # PlayStyle "perde_pressiona" do defensor
            has_perdepress = "perde_pressiona" in defensor.get("playstyles", [])
            if has_perdepress and random.random() < 0.60:
                narration_log.append(
                    f"⏱️ **{minute:02d}'** — {PLAYSTYLE_EMOJIS['perde_pressiona']} **Perde-Pressiona!** "
                    f"{_fmt(defensor)} perde o duelo momentaneamente mas reage em décimos de segundo e rouba a bola de {_fmt(atacante)}."
                )
            else:
                narration_log.append(f"⏱️ **{minute:02d}'** — {random.choice(NARR_DESARME).format(atk=_fmt(atacante), defensor=_fmt(defensor))}")
            continue

        # Narração opcional de drible bem-sucedido com PlayStyle
        if has_malvadeza and random.random() < 0.40:
            narration_log.append(
                f"⏱️ **{minute:02d}'** — {PLAYSTYLE_EMOJIS['malvadeza']} **Malvadeza!** "
                f"{_fmt(atacante)} solta o drible mágico e deixa {_fmt(defensor)} no chão antes de avançar em direção ao gol!"
            )
        elif has_rapid and random.random() < 0.35:
            narration_log.append(
                f"⏱️ **{minute:02d}'** — {PLAYSTYLE_EMOJIS['rapid']} **Velocidade explosiva!** "
                f"{_fmt(atacante)} sai na frente de {_fmt(defensor)} numa arrancada que ninguém consegue acompanhar!"
            )

        # ── EVENTO: Passe / Assistência ───────────────────────────────────────
        # PlayStyle "tecnica": +3% assistência; -10% erro de domínio/passe
        # PlayStyle "trivela": +5% precisão de passe
        has_tecnica = passador and "tecnica" in passador.get("playstyles", [])
        has_trivela = passador and "trivela" in passador.get("playstyles", [])

        pass_success_chance = 0.75
        if has_tecnica:
            pass_success_chance += 0.10
        if has_trivela:
            pass_success_chance += 0.05
        if atk_tactic == "tikitaka":
            pass_success_chance += 0.10

        if random.random() > pass_success_chance:
            # Passe errado — turnover sem chute
            narration_log.append(
                f"⏱️ **{minute:02d}'** — ❌ **Passe interceptado!** {_fmt(passador) if passador else _fmt(atacante)} erra o passe "
                f"e {_fmt(defensor)} limpa o perigo com facilidade."
            )
            continue

        # ── EVENTO: Finalização ───────────────────────────────────────────────
        stats[atk_key]["shots"] += 1
        performance[atacante["instance_id"]]["shots"] += 1

        # Cálculo de xG base
        xg_base = atk_eff["shoot"] / (atk_eff["shoot"] + def_eff["defense"] * 0.5 + gk_eff["defense"] * 0.5)

        # PlayStyle "superchute": +10% xG em chutes de fora da área
        has_superchute = "superchute" in atacante.get("playstyles", [])
        if has_superchute:
            xg_base += 0.10
            if random.random() < 0.25:
                narration_log.append(
                    f"⏱️ **{minute:02d}'** — {PLAYSTYLE_EMOJIS['superchute']} **SuperChute!** "
                    f"{_fmt(atacante)} arma o chute de fora da área — potência máxima!"
                )

        # PlayStyle "acrobata": +5% chance de voleio / +3% tesoura / +2% bicicleta
        has_acrobata = "acrobata" in atacante.get("playstyles", [])
        if has_acrobata and random.random() < 0.10:
            tipo = random.choices(["voleio", "tesoura", "bicicleta"], weights=[5, 3, 2])[0]
            xg_base += 0.07
            narration_log.append(
                f"⏱️ **{minute:02d}'** — {PLAYSTYLE_EMOJIS['acrobata']} **Acrobata!** "
                f"{_fmt(atacante)} prepara um {tipo} sensacional em posição difícil!"
            )

        # PlayStyle "anjo": +25% chance de cabeceio defensivo bem-sucedido
        # (defensivo: quando o defensor vai de cabeça, reduz xG do atacante)
        has_anjo = "anjo" in defensor.get("playstyles", [])
        if has_anjo and random.random() < 0.25:
            xg_base -= 0.12
            narration_log.append(
                f"⏱️ **{minute:02d}'** — {PLAYSTYLE_EMOJIS['anjo']} **Cabeceio defensivo!** "
                f"{_fmt(defensor)} sobe mais alto que {_fmt(atacante)} e afasta o perigo de cabeça!"
            )

        xg_val = min(0.95, max(0.04, xg_base))
        xg_data[atk_key] += xg_val
        performance[atacante["instance_id"]]["xg"] += xg_val

        # Perna ruim — fórmula da spec: 0.40 + (weak_foot - 1) * 0.10
        wf_stars = atacante.get("weak_foot", 1)
        chance_pe_bom = 0.40 + (wf_stars - 1) * 0.10  # 40%–80%
        using_weak_foot = random.random() < 0.40
        if using_weak_foot and random.random() > chance_pe_bom:
            # Finalização com pé ruim mal-executada
            if random.random() < 0.55:
                narration_log.append(
                    f"⏱️ **{minute:02d}'** — 💨 **Chute torto!** "
                    f"{_fmt(atacante)} finaliza com o pé fraco e a bola sai longe do gol."
                )
            else:
                stats[def_key]["saves"] += 1
                performance[gk["instance_id"]]["saves"] += 1
                narration_log.append(
                    f"⏱️ **{minute:02d}'** — 🧤 **Defesa tranquila!** "
                    f"{_fmt(atacante)} bate sem força com o pé ruim e {_fmt(gk)} segura sem dificuldade."
                )
            continue

        # Arremesso Especial do GK: 15% de chance de gerar contra-ataque / assistência
        has_arremesso = "arremesso_especial" in gk.get("playstyles", [])
        # (este PlayStyle é do goleiro; é processado no evento de defesa abaixo)

        # ── Resolução do Chute ────────────────────────────────────────────────
        if random.random() < xg_val:
            # Tentativa de GOL — verificar PlayStyle "encaixada" do goleiro
            has_encaixada = "encaixada" in gk.get("playstyles", [])
            if has_encaixada and random.random() < 0.25:
                # Goleiro encaixa a bola, não dá rebote — e já sai jogando
                stats[def_key]["saves"] += 1
                performance[gk["instance_id"]]["saves"] += 1
                stats[atk_key]["on_target"] += 1
                performance[atacante["instance_id"]]["on_target"] += 1
                narration_log.append(
                    f"⏱️ **{minute:02d}'** — {PLAYSTYLE_EMOJIS['encaixada']} **Encaixada!** "
                    f"{_fmt(gk)} voa no ângulo, agarra firme o chute violento de {_fmt(atacante)} e já inicia o contra-ataque!"
                )
                continue

            # GOL CONFIRMADO
            if is_p1_attack:
                p1_goals += 1
            else:
                p2_goals += 1

            performance[atacante["instance_id"]]["goals"] += 1
            performance[atacante["instance_id"]]["on_target"] += 1
            stats[atk_key]["on_target"] += 1

            # Assistência — PlayStyle "tecnica" aumenta chances
            has_assist = random.random() < (0.75 if has_tecnica else 0.68)
            assist_name = ""
            if has_assist and passador and passador["instance_id"] != atacante["instance_id"]:
                performance[passador["instance_id"]]["assists"] += 1
                assist_name = _fmt(passador)

            scorers.append({"name": _fmt(atacante), "minute": minute, "team": 1 if is_p1_attack else 2})

            if assist_name:
                msg = random.choice(NARR_GOL).format(
                    atk=_fmt(atacante), ast=assist_name, gk=_fmt(gk), defensor=_fmt(defensor)
                )
            else:
                msg = random.choice(NARR_GOL_SEM_AST).format(
                    atk=_fmt(atacante), gk=_fmt(gk), defensor=_fmt(defensor)
                )
            narration_log.append(f"⏱️ **{minute:02d}'** — {msg}")

        else:
            # Não entrou — Defesa, Trave ou Erro
            roll_outcome = random.random()
            if roll_outcome < 0.55:
                # Defesa do goleiro
                stats[def_key]["saves"] += 1
                performance[gk["instance_id"]]["saves"] += 1
                performance[atacante["instance_id"]]["on_target"] += 1
                stats[atk_key]["on_target"] += 1

                # PlayStyle "arremesso_especial": 15% de chance de o arremesso gerar assistência futura
                if has_arremesso and random.random() < 0.15:
                    narration_log.append(
                        f"⏱️ **{minute:02d}'** — {PLAYSTYLE_EMOJIS['arremesso_especial']} "
                        f"**{_fmt(gk)} defende e lança!** Arremesso longo e preciso coloca um companheiro em boa posição de ataque!"
                    )
                else:
                    narration_log.append(
                        f"⏱️ **{minute:02d}'** — "
                        f"{random.choice(NARR_DEFESA).format(atk=_fmt(atacante), gk=_fmt(gk), defensor=_fmt(defensor))}"
                    )
            elif roll_outcome < 0.70:
                # Trave
                narration_log.append(
                    f"⏱️ **{minute:02d}'** — "
                    f"{random.choice(NARR_TRAVE).format(atk=_fmt(atacante), gk=_fmt(gk), defensor=_fmt(defensor))}"
                )
            else:
                # Erro / Para fora
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
    }
