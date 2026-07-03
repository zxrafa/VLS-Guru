# -*- coding: utf-8 -*-
import os
import json
from dotenv import load_dotenv
from supabase import create_client

# Carrega o .env a partir da pasta do projeto
load_dotenv(dotenv_path="C:/Jogos/VLS Guru New/.env")

url = os.getenv("SUPABASE_URL")
key = os.getenv("SUPABASE_KEY")
supabase = create_client(url, key)

def main():
    print("Iniciando limpeza de coleções no Supabase...")
    
    # 1. Remove todas as coleções antigas (ID começando com 'col_')
    supabase.table("jogadores").delete().like("id", "col_%").execute()
    print("Coleções anteriores apagadas com sucesso.")
    
    # 2. Insere a coleção Base configurada
    col_base = {
        "id": "base",
        "nome": "Base",
        "emoji": "<:comuns:1517258648005509210>",
        "preco_adicional_pct": 0,
        "max_playstyles": 3
    }
    supabase.table("jogadores").upsert({"id": "col_base", "data": col_base}).execute()
    print("Coleção 'Base' cadastrada.")
    
    # 3. Busca todos os jogadores cadastrados no Supabase
    res_players = supabase.table("jogadores").select("*").like("id", "player_%").execute()
    players = res_players.data or []
    print(f"Encontrados {len(players)} jogadores para atualização.")
    
    # 4. Atualiza o cadastro de cada jogador com a coleção Base
    updated_count = 0
    for p in players:
        doc_id = p["id"]
        player_data = p["data"]
        
        # Caso esteja persistido como string serializada
        if isinstance(player_data, str):
            player_data = json.loads(player_data)
            
        player_data["col_id"] = "base"
        player_data["col_nome"] = "Base"
        player_data["col_emoji"] = "<:comuns:1517258648005509210>"
        
        supabase.table("jogadores").upsert({"id": doc_id, "data": player_data}).execute()
        updated_count += 1
        print(f"  -> Jogador {player_data.get('name')} atualizado.")
        
    print(f"\nConcluído! {updated_count} jogadores atualizados com a coleção Base.")

if __name__ == "__main__":
    main()
