import sqlite3

def main():
    conn = sqlite3.connect("vls_guru_local.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM jogadores WHERE id LIKE 'player_%'")
    rows = cursor.fetchall()
    print("Local players count:", len(rows))
    print("IDs:", [r[0] for r in rows])
    conn.close()

if __name__ == "__main__":
    main()
