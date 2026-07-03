# -*- coding: utf-8 -*-
import os
import sys
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed

# Reconfigura standard output para UTF-8 no Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Adiciona o diretório principal ao sys.path para podermos importar card_utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from card_utils import generate_player_card_sync

DB_PATH = r"C:\Jogos\VLS Guru New\vls_guru_local.db"

def process_single_player(p_id, data_str):
    try:
        player_data = json.loads(data_str)
        name = player_data.get("name", "Jogador")
        col_id = player_data.get("col_id", "base")
        
        # Gera e colore a carta
        relative_path = generate_player_card_sync(player_data)
        
        if relative_path:
            player_data["card"] = relative_path
            return p_id, player_data, f"✅ {name} ({col_id}): Carta atualizada -> {relative_path}"
        else:
            return p_id, None, f"❌ {name} ({col_id}): Falha ao gerar carta."
    except Exception as e:
        return p_id, None, f"❌ Erro ao processar jogador {p_id}: {e}"

def main():
    print("🚀 Carregando banco de dados...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, data FROM jogadores WHERE id LIKE 'player_%'")
    rows = cursor.fetchall()
    conn.close()
    
    print(f"Total de {len(rows)} jogadores encontrados. Iniciando processamento concorrente...")
    
    updated_players_map = {}
    
    # Processa jogadores usando ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(process_single_player, p_id, data_str): p_id for p_id, data_str in rows}
        for future in as_completed(futures):
            p_id, updated_data, msg = future.result()
            print(msg)
            if updated_data:
                updated_players_map[p_id] = updated_data
                
    # Salva no banco de dados e atualiza inventários dos managers
    print("\n💾 Salvando alterações globais dos jogadores no banco de dados...")
    conn = sqlite3.connect(DB_PATH)
    # Ativa journal em WAL e synchronous normal para segurança e performance
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    cursor = conn.cursor()
    
    # Transação para atualizar o catálogo global
    try:
        updates = [(json.dumps(data, ensure_ascii=False), p_id) for p_id, data in updated_players_map.items()]
        cursor.executemany("UPDATE jogadores SET data = ? WHERE id = ?", updates)
        conn.commit()
        print(f"✅ {len(updates)} jogadores atualizados no catálogo global.")
    except Exception as e:
        print(f"❌ Erro ao salvar catálogo global: {e}")
        conn.rollback()
        
    # Agora atualizamos os inventários e escalações de todos os managers (user_%)
    print("\n🔍 Atualizando inventários e escalações de todos os managers...")
    cursor.execute("SELECT id, data FROM jogadores WHERE id LIKE 'user_%'")
    users = cursor.fetchall()
    
    user_updates = []
    for u_id, u_data_str in users:
        try:
            profile = json.loads(u_data_str)
            changed = False
            
            # Atualiza inventário
            inventory = profile.get("inventory", [])
            for i, card in enumerate(inventory):
                card_id = card.get("id")
                if card_id in updated_players_map:
                    global_p = updated_players_map[card_id]
                    # Atualiza o link do card e dados da coleção
                    card["card"] = global_p["card"]
                    card["col_id"] = global_p["col_id"]
                    card["col_nome"] = global_p["col_nome"]
                    card["col_emoji"] = global_p["col_emoji"]
                    changed = True
                    
            # Atualiza titulares (starting_xi)
            starting_xi = profile.get("starting_xi", [])
            for card in starting_xi:
                card_id = card.get("id")
                if card_id in updated_players_map:
                    global_p = updated_players_map[card_id]
                    card["card"] = global_p["card"]
                    card["col_id"] = global_p["col_id"]
                    card["col_nome"] = global_p["col_nome"]
                    card["col_emoji"] = global_p["col_emoji"]
                    changed = True
                    
            if changed:
                user_updates.append((json.dumps(profile, ensure_ascii=False), u_id))
        except Exception as e:
            print(f"❌ Erro ao processar manager {u_id}: {e}")
            
    if user_updates:
        try:
            cursor.executemany("UPDATE jogadores SET data = ? WHERE id = ?", user_updates)
            conn.commit()
            print(f"✅ Inventário/Escalação de {len(user_updates)} managers atualizados com sucesso.")
        except Exception as e:
            print(f"❌ Erro ao salvar dados dos managers: {e}")
            conn.rollback()
            
    conn.close()
    print("\n🎉 Migração e geração de cards concluídas com sucesso!")

if __name__ == "__main__":
    main()
