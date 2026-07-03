# -*- coding: utf-8 -*-
import os
import re
import uuid
import random
import asyncio
import sqlite3
from database import DB_PATH, db_upsert

# Coleções padrão
COLECOES = [
    {"id": "base", "nome": "Base", "emoji": "⚪", "preco_adicional_pct": 0, "max_playstyles": 0},
    {"id": "comum", "nome": "Comum", "emoji": "🟢", "preco_adicional_pct": 10, "max_playstyles": 1},
    {"id": "premiados", "nome": "Premiados", "emoji": "🔵", "preco_adicional_pct": 25, "max_playstyles": 2},
    {"id": "copa_do_mundo", "nome": "Copa do Mundo", "emoji": "🟡", "preco_adicional_pct": 50, "max_playstyles": 3}
]

# Nomes de coleções para ID
COL_NAME_MAP = {
    "base": "base",
    "comum": "comum",
    "premiados": "premiados",
    "copa do mundo": "copa_do_mundo"
}

# Playstyles por posição para gerar aleatoriamente quando elegível
PLAYSTYLES_LINE = ["tecnica", "trivela", "rapid", "anjo", "acrobata", "superchute", "malvadeza", "perde_pressiona", "ima_no_pe"]
PLAYSTYLES_GK = ["arremesso_especial", "encaixada"]

def generate_attributes(pos, over):
    # Gera atributos balanceados baseados na posição e overall
    if pos == "GK":
        shoot = random.randint(10, 20)
        pass_stat = random.randint(50, over - 5)
        dribble = random.randint(30, 50)
        defense = random.randint(over - 10, over + 2)
        physical = random.randint(over - 8, over + 2)
    elif pos in ["CB", "LB", "RB", "LWB", "RWB"]:
        shoot = random.randint(30, 55)
        pass_stat = random.randint(55, over - 5)
        dribble = random.randint(50, over - 10)
        defense = random.randint(over - 5, over + 5)
        physical = random.randint(over - 5, over + 5)
    elif pos in ["CDM", "CM", "CAM", "LM", "RM"]:
        shoot = random.randint(over - 10, over)
        pass_stat = random.randint(over - 5, over + 5)
        dribble = random.randint(over - 5, over + 5)
        defense = random.randint(over - 15, over)
        physical = random.randint(over - 10, over)
    else:  # ST, CF, LW, RW
        shoot = random.randint(over - 2, over + 7)
        pass_stat = random.randint(over - 12, over)
        dribble = random.randint(over - 5, over + 5)
        defense = random.randint(15, 45)
        physical = random.randint(over - 10, over + 2)

    # Limita valores entre 1 e 99
    return {
        "shoot": max(1, min(99, shoot)),
        "pass_stat": max(1, min(99, pass_stat)),
        "dribble": max(1, min(99, dribble)),
        "defense": max(1, min(99, defense)),
        "physical": max(1, min(99, physical)),
    }

async def seed():
    # 1. Inserir Coleções
    print("Semeando Coleções...")
    for col in COLECOES:
        doc_id = f"col_{col['id']}"
        try:
            await db_upsert(doc_id, col)
            print(f"  Coleção cadastrada: {col['nome']}")
        except Exception as e:
            print(f"  Erro ao cadastrar coleção {col['nome']}: {e}")

    # 2. Ler e Inserir Jogadores
    txt_path = "../VLS Guru/jogadores.txt"
    if not os.path.exists(txt_path):
        print(f"[Erro] jogadores.txt não localizado em {txt_path}!")
        return

    print("Semeando Jogadores...")
    lines = open(txt_path, "r", encoding="utf-8").readlines()
    count = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Exemplo de linha: "1. Myru | OVR: 78 | POS: GK | Colecao: Base"
        parts = line.split("|")
        if len(parts) < 4:
            continue

        # Nome
        name_part = parts[0].split(".")
        name = name_part[1].strip() if len(name_part) > 1 else name_part[0].strip()

        # Overall
        over_match = re.search(r"\d+", parts[1])
        over = int(over_match.group()) if over_match else 75

        # Posição
        pos = parts[2].replace("POS:", "").strip().upper()

        # Coleção
        col_raw = parts[3].replace("Colecao:", "").strip().lower()
        col_id = COL_NAME_MAP.get(col_raw, "base")

        # Busca dados da coleção
        col_data = next((c for c in COLECOES if c["id"] == col_id), COLECOES[0])

        # Gera atributos detalhados
        attrs = generate_attributes(pos, over)

        # Gera Playstyles elegíveis
        max_ps = col_data["max_playstyles"]
        playstyles = []
        if max_ps > 0:
            pool = PLAYSTYLES_GK if pos == "GK" else PLAYSTYLES_LINE
            chosen_ps = random.sample(pool, k=min(max_ps, len(pool)))
            playstyles = chosen_ps

        player_id = f"player_{name.lower().replace(' ', '_')}_{pos.lower()}"
        
        # Garante ID único
        if len(player_id) > 50:
            player_id = player_id[:40] + "_" + str(uuid.uuid4())[:8]

        player_data = {
            "id": player_id,
            "name": name,
            "over": over,
            "pos": pos,
            "col_id": col_data["id"],
            "col_nome": col_data["nome"],
            "col_emoji": col_data["emoji"],
            "shoot": attrs["shoot"],
            "pass_stat": attrs["pass_stat"],
            "dribble": attrs["dribble"],
            "defense": attrs["defense"],
            "physical": attrs["physical"],
            "weak_foot": random.randint(2, 5),
            "skill_moves": random.randint(2, 5),
            "playstyles": playstyles,
            "nationality": random.choice(["Brasil", "Argentina", "Portugal", "França", "Inglaterra", "Espanha", "Itália", "Alemanha"]),
            "club": random.choice(["VLS FC", "Guru SC", "Dream Team", "Néon FC", "Ultimate SC"]),
            "card": "",
            "xp": 0
        }

        try:
            await db_upsert(player_id, player_data)
            count += 1
            if count % 10 == 0:
                print(f"  {count} jogadores cadastrados...")
        except Exception as e:
            print(f"  Erro ao cadastrar jogador {name}: {e}")

    print(f"Sucesso! Banco semeado com {count} jogadores.")

if __name__ == "__main__":
    asyncio.run(seed())
