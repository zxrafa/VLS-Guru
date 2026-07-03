import sqlite3
import json

def main():
    conn = sqlite3.connect('vls_guru_local.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT COUNT(*) FROM jogadores WHERE id LIKE "player_%"')
    players_count = cursor.fetchone()[0]
    print('Players count:', players_count)
    
    cursor.execute('SELECT COUNT(*) FROM jogadores WHERE id LIKE "user_%"')
    users_count = cursor.fetchone()[0]
    print('Users count:', users_count)
    
    cursor.execute('SELECT id, LENGTH(data) FROM jogadores')
    rows = cursor.fetchall()
    print('Total rows in table:', len(rows))
    
    # Check largest rows
    rows_sorted = sorted(rows, key=lambda x: x[1], reverse=True)
    print('\nTop 5 largest rows in database:')
    for doc_id, length in rows_sorted[:5]:
        print(f'- {doc_id}: {length} bytes')
        
    conn.close()

if __name__ == '__main__':
    main()
