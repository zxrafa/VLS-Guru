import sqlite3
import json

DB_PATH = r"C:\Jogos\VLS Guru New\vls_guru_local.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, data FROM jogadores WHERE id LIKE 'player_%'")
    rows = cursor.fetchall()
    
    wc_players = []
    for r in rows:
        p_id = r[0]
        data = json.loads(r[1])
        # Jogadores de Copa do Mundo (OVR >= 90 ou colecao copa_do_mundo)
        if data.get("over", 0) >= 90 or data.get("col_id") == "copa_do_mundo":
            # O ID que vai no modal é o que vem depois de 'player_'
            item_id = p_id.replace("player_", "", 1)
            wc_players.append((data.get("name"), item_id, data.get("over"), data.get("pos")))
            
    conn.close()
    
    # Ordena por Overall decrescente
    wc_players.sort(key=lambda x: x[2], reverse=True)
    
    print(f"Total World Cup Players (OVR >= 90): {len(wc_players)}")
    for name, item_id, over, pos in wc_players:
        print(f"  - {name} ({pos} - OVR {over}) -> ID para usar: {item_id}")

if __name__ == "__main__":
    main()
