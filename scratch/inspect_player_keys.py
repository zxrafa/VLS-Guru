import sqlite3
import json

db_path = r"C:\Jogos\VLS Guru New\vls_guru_local.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get one goalkeeper and one outfield player
cursor.execute("SELECT id, data FROM jogadores WHERE id LIKE 'player_%'")
rows = cursor.fetchall()

players = [json.loads(r[1]) for r in rows]

print("Outfield Player Sample:")
outfield = [p for p in players if p.get("pos") != "GK"]
if outfield:
    print(json.dumps(outfield[0], indent=2))

print("\nGoalkeeper Player Sample:")
gk = [p for p in players if p.get("pos") == "GK"]
if gk:
    print(json.dumps(gk[0], indent=2))

conn.close()
