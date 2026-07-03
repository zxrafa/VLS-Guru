# -*- coding: utf-8 -*-
"""
VLS Guru - Módulo de Banco de Dados (Suporte SQLite Local / Supabase)
Escolhe a conexão baseada na existência das credenciais no arquivo .env.
"""
import os
import json
import sqlite3
import asyncio
import discord
from dotenv import load_dotenv

# Carrega as variáveis do .env
load_dotenv()

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vls_guru_local.db")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

use_supabase = bool(SUPABASE_URL and SUPABASE_KEY)
supabase_client = None

if use_supabase:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("[Database] Conectado ao Supabase com sucesso!")
    except Exception as e:
        print(f"[Database] Erro ao conectar ao Supabase: {e}. Usando SQLite local.")
        use_supabase = False

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db():
    if not use_supabase:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jogadores (
                id TEXT PRIMARY KEY,
                data TEXT
            )
        """)
        conn.commit()
        conn.close()

# Garante a criação da tabela local se não estiver usando Supabase
init_db()

# Locks por usuário para evitar race conditions
_user_locks = {}

def get_user_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _user_locks:
        _user_locks[user_id] = asyncio.Lock()
    return _user_locks[user_id]

def lock_user():
    """
    Decorator assíncrono para travar ações concorrentes do mesmo usuário.
    """
    def decorator(func):
        import functools
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            interaction = None
            for arg in args:
                if isinstance(arg, discord.Interaction):
                    interaction = arg
                    break

            if interaction:
                user_id = interaction.user.id
                lock = get_user_lock(user_id)
                if lock.locked():
                    return await interaction.response.send_message(
                        "❌ Outra operação sua já está em andamento. Aguarde a conclusão dela.",
                        ephemeral=True
                    )
                async with lock:
                    return await func(*args, **kwargs)
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# ==============================================================================
# OPERAÇÕES GENÉRICAS (DOCUMENT STORE MODEL)
# ==============================================================================
async def db_get(doc_id: str):
    if use_supabase:
        def fetch():
            try:
                res = supabase_client.table("jogadores").select("*").eq("id", doc_id).execute()
                if res.data:
                    row = res.data[0]
                    data_field = row["data"]
                    if isinstance(data_field, str):
                        data_field = json.loads(data_field)
                    return {"id": doc_id, "data": data_field}
                return None
            except Exception as e:
                print(f"Erro ao buscar no Supabase ({doc_id}): {e}")
                return None
        return await asyncio.to_thread(fetch)
    else:
        def fetch():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM jogadores WHERE id = ?", (doc_id,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    return {"id": doc_id, "data": json.loads(row[0])}
                return None
            except Exception as e:
                print(f"Erro ao buscar no banco ({doc_id}): {e}")
                return None
        return await asyncio.to_thread(fetch)

async def db_upsert(doc_id: str, data: dict):
    if use_supabase:
        def push():
            try:
                supabase_client.table("jogadores").upsert({"id": doc_id, "data": data}).execute()
            except Exception as e:
                print(f"Erro ao salvar no Supabase ({doc_id}): {e}")
        await asyncio.to_thread(push)
    else:
        def push():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO jogadores (id, data) VALUES (?, ?)", 
                    (doc_id, json.dumps(data))
                )
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Erro ao salvar no banco ({doc_id}): {e}")
        await asyncio.to_thread(push)

async def db_delete(doc_id: str):
    if use_supabase:
        def remove():
            try:
                supabase_client.table("jogadores").delete().eq("id", doc_id).execute()
            except Exception as e:
                print(f"Erro ao deletar no Supabase ({doc_id}): {e}")
        await asyncio.to_thread(remove)
    else:
        def remove():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM jogadores WHERE id = ?", (doc_id,))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Erro ao deletar no banco ({doc_id}): {e}")
        await asyncio.to_thread(remove)


# ==============================================================================
# HELPERS DE CONTROLE DE PERFIL DE USUÁRIOS
# ==============================================================================
async def get_user_profile(user: discord.abc.User) -> dict:
    doc_id = f"user_{user.id}"
    record = await db_get(doc_id)
    
    if not record:
        default_profile = {
            "user_id": user.id,
            "club_name": f"FC {user.display_name[:20]}",
            "stadium_name": "Arena VLS",
            "money": 15000,
            "premium_coins": 0,
            "inventory": [],
            "starting_xi": [],
            "formation": "4-3-3",
            "tactic": "padrao",
            "acquired_tactics": ["padrao"],
            "scout_level": 0,
            "missions_progress": {
                "semanal": {},
                "mensal": {},
                "last_weekly_reset": "",
                "last_monthly_reset": ""
            },
            "achievements": [],
            "featured_badge": None,
            "last_claim": 0,
            "last_treino": 0,
            "wins": 0,
            "losses": 0,
            "draws": 0,
            "estadio": None,
            "acquired_badges": []
        }
        await db_upsert(doc_id, default_profile)
        return default_profile
    else:
        profile = record["data"]
        changed = False
        defaults = {
            "money": 15000,
            "premium_coins": 0,
            "inventory": [],
            "starting_xi": [],
            "formation": "4-3-3",
            "tactic": "padrao",
            "acquired_tactics": ["padrao"],
            "scout_level": 0,
            "missions_progress": {"semanal": {}, "mensal": {}, "last_weekly_reset": "", "last_monthly_reset": ""},
            "achievements": [],
            "featured_badge": None,
            "acquired_badges": [],
            "wins": 0,
            "losses": 0,
            "draws": 0
        }
        for k, v in defaults.items():
            if k not in profile:
                profile[k] = v
                changed = True
        
        if changed:
            await db_upsert(doc_id, profile)
        return profile

async def save_user_profile(user_id: int, profile: dict):
    doc_id = f"user_{user_id}"
    await db_upsert(doc_id, profile)


# ==============================================================================
# BÚSQUEDA DE REGISTROS EM LOTE
# ==============================================================================
async def get_all_players() -> list[dict]:
    return await db_get_prefix("player_")

async def get_all_users() -> list[dict]:
    return await db_get_prefix("user_")

async def get_all_collections() -> list[dict]:
    return await db_get_prefix("col_")

async def get_missions() -> list[dict]:
    return await db_get_prefix("mission_")

async def db_get_prefix(prefix: str) -> list[dict]:
    """Busca todos os registros cujo ID começa com o prefixo informado."""
    if use_supabase:
        def fetch_all():
            try:
                res = supabase_client.table("jogadores").select("data").like("id", f"{prefix}%").execute()
                out = []
                for r in res.data:
                    data_field = r["data"]
                    if isinstance(data_field, str):
                        data_field = json.loads(data_field)
                    out.append(data_field)
                return out
            except Exception as e:
                print(f"Erro ao buscar com prefixo '{prefix}' no Supabase: {e}")
                return []
        return await asyncio.to_thread(fetch_all)
    else:
        def fetch_all():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT data FROM jogadores WHERE id LIKE ?", (prefix + "%",))
                rows = cursor.fetchall()
                conn.close()
                return [json.loads(r[0]) for r in rows]
            except Exception as e:
                print(f"Erro ao buscar com prefixo '{prefix}': {e}")
                return []
        return await asyncio.to_thread(fetch_all)


async def db_clear_all() -> int:
    """Apaga todos os registros do banco de dados (usado para reset de sistema). Retorna o número de registros apagados."""
    if use_supabase:
        def clear():
            try:
                res_count = supabase_client.table("jogadores").select("id", count="exact").execute()
                count = res_count.count if res_count.count is not None else 0
                supabase_client.table("jogadores").delete().neq("id", "dummy_value_that_does_not_exist").execute()
                return count
            except Exception as e:
                print(f"Erro ao limpar o Supabase: {e}")
                return 0
        return await asyncio.to_thread(clear)
    else:
        def clear():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM jogadores")
                count = cursor.fetchone()[0]
                cursor.execute("DELETE FROM jogadores")
                conn.commit()
                conn.close()
                return count
            except Exception as e:
                print(f"Erro ao limpar o banco SQLite: {e}")
                return 0
        return await asyncio.to_thread(clear)
