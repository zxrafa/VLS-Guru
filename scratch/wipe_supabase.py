# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def main():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        print("Erro: Credenciais do Supabase não encontradas no .env!")
        return

    supabase = create_client(url, key)
    
    # Executa a limpeza de todas as linhas
    res = supabase.table("jogadores").delete().neq("id", "dummy_value_that_does_not_exist").execute()
    print("Sucesso! Todos os registros (jogadores, coleções, perfis) foram apagados do Supabase.")

if __name__ == "__main__":
    main()
