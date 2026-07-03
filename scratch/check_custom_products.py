import sqlite3
import json

DB_PATH = r"C:\Jogos\VLS Guru New\vls_guru_local.db"

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, data FROM jogadores WHERE id LIKE 'loja_produto_%'")
    rows = cursor.fetchall()
    
    print(f"Total custom products found: {len(rows)}")
    for r in rows:
        print(f"  - ID: {r[0]} | Data: {r[1]}")
        
    conn.close()

if __name__ == "__main__":
    main()
