# -*- coding: utf-8 -*-
import sqlite3
import json

COLECOES = [
    {"id": "base", "nome": "Base", "emoji": "⚪", "preco_adicional_pct": 0, "max_playstyles": 0},
    {"id": "comum", "nome": "Comum", "emoji": "🟢", "preco_adicional_pct": 10, "max_playstyles": 1},
    {"id": "premiados", "nome": "Premiados", "emoji": "🔵", "preco_adicional_pct": 25, "max_playstyles": 2},
    {"id": "copa_do_mundo", "nome": "Copa do Mundo", "emoji": "🟡", "preco_adicional_pct": 50, "max_playstyles": 3}
]

def main():
    conn = sqlite3.connect("vls_guru_local.db")
    for col in COLECOES:
        conn.execute(
            "INSERT OR REPLACE INTO jogadores (id, data) VALUES (?, ?)",
            (f"col_{col['id']}", json.dumps(col, ensure_ascii=False))
        )
    conn.commit()
    conn.close()
    print("Coleções base cadastradas!")

if __name__ == "__main__":
    main()
