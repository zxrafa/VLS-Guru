import os
import sys
import re
import json
import sqlite3
import requests
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed

# Reconfigura streams padrão para UTF-8 (corrige crashes de emojis no console do Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

DB_PATH = r"C:\Jogos\VLS Guru New\vls_guru_local.db"
STATIC_CARTAS_DIR = r"C:\Jogos\VLS Guru New\static\cartas"
CACHE_DIR = r"C:\Jogos\VLS Guru New\cache_cartas"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.ea.com/'
}

# Mapping for players without EA ID in their old URLs
SPECIAL_MAP = {
    "endrick": "272505",
    "l. messi": "158023",
    "lionel messi": "158023",
    "c. ronaldo": "20801",
    "cristiano ronaldo": "20801"
}

def clean_directory(directory):
    if os.path.exists(directory):
        for filename in os.listdir(directory):
            file_path = os.path.join(directory, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f'Failed to delete {file_path}. Reason: {e}')
    else:
        os.makedirs(directory, exist_ok=True)

def search_ea_id(player_name):
    url = "https://drop-api.ea.com/rating/ea-sports-fc"
    params = {
        "locale": "pt-br",
        "limit": 5,
        "search": player_name
    }
    try:
        r = requests.get(url, params=params, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if items:
                avatar_url = items[0].get("avatarUrl", "")
                match = re.search(r'/p(\d+)\.png', avatar_url)
                if match:
                    return match.group(1)
    except Exception as e:
        print(f"Error searching EA ID for {player_name}: {e}")
    return None

def process_single_player(p_id, data_str):
    player_data = json.loads(data_str)
    name = player_data.get("name", "")
    card_old = player_data.get("card", "")
    
    # 1. Determinar o ID da EA
    ea_id = None
    
    # Check special map
    name_lower = name.lower().strip()
    if name_lower in SPECIAL_MAP:
        ea_id = SPECIAL_MAP[name_lower]
    
    # Check old URL pattern
    if not ea_id and card_old:
        match = re.search(r'/p(\d+)\.png', card_old)
        if match:
            ea_id = match.group(1)
    
    # Try searching by name if still not found
    if not ea_id:
        ea_id = search_ea_id(name)
        if not ea_id:
            clean_name = re.sub(r'^[A-Z]\.\s+', '', name)
            if clean_name != name:
                ea_id = search_ea_id(clean_name)
                
    if not ea_id:
        return p_id, None, f"❌ ID da EA não encontrado para {name}"
        
    # 2. Baixar a imagem do card oficial completo
    shield_url = f"https://ratings-images-prod.pulse.ea.com/FC25/full/player-shields/pt-br/{ea_id}.png?width=265"
    local_filename = f"{p_id}.png"
    local_filepath = os.path.join(STATIC_CARTAS_DIR, local_filename)
    
    # Se a imagem já existe localmente e tem um tamanho razoável, não precisamos baixar de novo
    if os.path.exists(local_filepath) and os.path.getsize(local_filepath) > 10000:
        relative_path = f"static/cartas/{local_filename}"
        player_data["card"] = relative_path
        return p_id, player_data, f"💾 {name}: Imagem já existente localmente."
        
    try:
        r_img = requests.get(shield_url, headers=headers, timeout=10)
        if r_img.status_code == 200:
            with open(local_filepath, "wb") as f_img:
                f_img.write(r_img.content)
            
            relative_path = f"static/cartas/{local_filename}"
            player_data["card"] = relative_path
            return p_id, player_data, f"✅ {name}: Carta baixada com sucesso!"
        else:
            return p_id, None, f"❌ {name}: Falha HTTP {r_img.status_code}"
    except Exception as e:
        return p_id, None, f"❌ {name}: Erro {e}"

def main():
    print("🧹 Limpando diretórios de cache...")
    os.makedirs(STATIC_CARTAS_DIR, exist_ok=True)
    clean_directory(CACHE_DIR)
    
    # Abrimos a conexão no início apenas para leitura rápida
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, data FROM jogadores WHERE id LIKE 'player_%'")
    rows = cursor.fetchall()
    conn.close()
    
    print(f"Total players found in DB: {len(rows)}")
    print("🚀 Iniciando downloads concorrentes com pool de threads...")
    
    updates_to_make = []
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(process_single_player, p_id, data_str): p_id for p_id, data_str in rows}
        
        for future in as_completed(futures):
            p_id, updated_data, msg = future.result()
            print(msg)
            
            if updated_data:
                updates_to_make.append((json.dumps(updated_data, ensure_ascii=False), p_id))
            else:
                failed_count += 1
                
    print("\n💾 Aplicando alterações no banco de dados SQLite sequencialmente...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Ativa WAL no banco para maior resiliência
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    
    try:
        cursor.executemany("UPDATE jogadores SET data = ? WHERE id = ?", updates_to_make)
        conn.commit()
        print(f"✅ Sucesso! {len(updates_to_make)} jogadores salvos no banco de dados em uma única transação.")
    except Exception as e:
        print(f"❌ Erro ao salvar no banco de dados: {e}")
        conn.rollback()
    finally:
        conn.close()
    
    print("\n==========================================")
    print(f"🎉 Processo concluído!")
    print(f"✅ Cartas atualizadas: {len(updates_to_make)}")
    print(f"❌ Falhas: {failed_count}")
    print("==========================================")

if __name__ == "__main__":
    main()
