import sqlite3
import json
import re

db_path = r"C:\Jogos\VLS Guru New\vls_guru_local.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT id, data FROM jogadores WHERE id LIKE 'player_%'")
rows = cursor.fetchall()

print(f"Total players: {len(rows)}")
no_ea_id = []
for r in rows:
    p_id = r[0]
    data = json.loads(r[1])
    card = data.get("card", "")
    
    # Tenta extrair o ID numérico da EA
    match = re.search(r'/p(\d+)\.png', card)
    if match:
        ea_id = match.group(1)
    else:
        ea_id = None
        no_ea_id.append((data.get("name"), card, p_id))

print(f"Players with no EA ID: {len(no_ea_id)}")
for name, card, p_id in no_ea_id[:50]:
    print(f"  - Name: {name} | ID: {p_id} | Card URL: {card}")

conn.close()
