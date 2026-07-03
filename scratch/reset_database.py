import sqlite3

DB_PATH = r"C:\Jogos\VLS Guru New\vls_guru_local.db"

def main():
    print("Conectando ao banco de dados SQLite...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ativa WAL no banco
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    
    # 1. Conta registros antes de deletar
    cursor.execute("SELECT COUNT(*) FROM jogadores WHERE id LIKE 'user_%'")
    users_before = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jogadores WHERE id LIKE 'champ_%'")
    champs_before = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jogadores WHERE id = 'tournament_state'")
    state_before = cursor.fetchone()[0]
    
    print(f"Registros encontrados para delecao:")
    print(f"  - Perfis de Usuarios (user_*): {users_before}")
    print(f"  - Campeonatos (champ_*): {champs_before}")
    print(f"  - Estado de Torneio (tournament_state): {state_before}")
    
    # 2. Executa as delecoes
    print("\nExecutando limpeza...")
    cursor.execute("DELETE FROM jogadores WHERE id LIKE 'user_%'")
    users_deleted = cursor.rowcount
    
    cursor.execute("DELETE FROM jogadores WHERE id LIKE 'champ_%'")
    champs_deleted = cursor.rowcount
    
    cursor.execute("DELETE FROM jogadores WHERE id = 'tournament_state'")
    state_deleted = cursor.rowcount
    
    conn.commit()
    
    # 3. Conta o que sobrou no banco
    cursor.execute("SELECT COUNT(*) FROM jogadores WHERE id LIKE 'player_%'")
    players_left = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jogadores WHERE id LIKE 'col_%'")
    cols_left = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM jogadores")
    total_left = cursor.fetchone()[0]
    
    conn.close()
    
    print("\n==========================================")
    print("Reset de Dados Concluido!")
    print(f"Perfis de usuarios deletados: {users_deleted}")
    print(f"Campeonatos deletados: {champs_deleted}")
    print(f"Estados de torneio deletados: {state_deleted}")
    print("------------------------------------------")
    print(f"Cartas preservadas (player_*): {players_left}")
    print(f"Colecoes preservadas (col_*): {cols_left}")
    print(f"Total de registros restantes no banco: {total_left}")
    print("==========================================")

if __name__ == "__main__":
    main()
