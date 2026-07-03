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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS campeonatos (
                id TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                logo_url TEXT,
                ativo INTEGER DEFAULT 1,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS partidas (
                id TEXT PRIMARY KEY,
                campeonato_id TEXT,
                rodada TEXT NOT NULL,
                time_casa TEXT NOT NULL,
                time_fora TEXT NOT NULL,
                gols_casa INTEGER,
                gols_fora INTEGER,
                encerrada INTEGER DEFAULT 0,
                video_url TEXT,
                data_jogo TEXT,
                criado_em TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(campeonato_id) REFERENCES campeonatos(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS noticias (
                id TEXT PRIMARY KEY,
                titulo TEXT NOT NULL,
                subtitulo TEXT,
                conteudo TEXT NOT NULL,
                imagem_url TEXT,
                data_publicacao TEXT DEFAULT CURRENT_TIMESTAMP
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


# ==============================================================================
# OPERAÇÕES DO CAMPEONATO DA LIGA VLS
# ==============================================================================

async def get_all_campeonatos() -> list[dict]:
    if use_supabase:
        def fetch():
            try:
                res = supabase_client.table("campeonatos").select("*").order("criado_em", desc=True).execute()
                return res.data or []
            except Exception as e:
                print(f"Erro ao obter campeonatos: {e}")
                return []
        return await asyncio.to_thread(fetch)
    else:
        def fetch():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, nome, logo_url, ativo, criado_em FROM campeonatos ORDER BY criado_em DESC")
                rows = cursor.fetchall()
                conn.close()
                return [{"id": r[0], "nome": r[1], "logo_url": r[2], "ativo": bool(r[3]), "criado_em": r[4]} for r in rows]
            except Exception as e:
                print(f"Erro ao obter campeonatos local: {e}")
                return []
        return await asyncio.to_thread(fetch)

async def save_campeonato(campeonato_id: str, nome: str, logo_url: str = None, ativo: bool = True) -> bool:
    if use_supabase:
        def save():
            try:
                supabase_client.table("campeonatos").upsert({
                    "id": campeonato_id,
                    "nome": nome,
                    "logo_url": logo_url,
                    "ativo": ativo
                }).execute()
                return True
            except Exception as e:
                print(f"Erro ao salvar campeonato: {e}")
                return False
        return await asyncio.to_thread(save)
    else:
        def save():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO campeonatos (id, nome, logo_url, ativo) VALUES (?, ?, ?, ?)",
                    (campeonato_id, nome, logo_url, 1 if ativo else 0)
                )
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                print(f"Erro ao salvar campeonato local: {e}")
                return False
        return await asyncio.to_thread(save)

async def delete_campeonato(campeonato_id: str) -> bool:
    if use_supabase:
        def remove():
            try:
                supabase_client.table("campeonatos").delete().eq("id", campeonato_id).execute()
                return True
            except Exception as e:
                print(f"Erro ao deletar campeonato: {e}")
                return False
        return await asyncio.to_thread(remove)
    else:
        def remove():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM campeonatos WHERE id = ?", (campeonato_id,))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                print(f"Erro ao deletar campeonato local: {e}")
                return False
        return await asyncio.to_thread(remove)

async def get_all_partidas(campeonato_id: str = None) -> list[dict]:
    if use_supabase:
        def fetch():
            try:
                query = supabase_client.table("partidas").select("*")
                if campeonato_id:
                    query = query.eq("campeonato_id", campeonato_id)
                res = query.order("criado_em", desc=True).execute()
                return res.data or []
            except Exception as e:
                print(f"Erro ao obter partidas: {e}")
                return []
        return await asyncio.to_thread(fetch)
    else:
        def fetch():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                if campeonato_id:
                    cursor.execute("SELECT id, campeonato_id, rodada, time_casa, time_fora, gols_casa, gols_fora, encerrada, video_url, data_jogo, criado_em FROM partidas WHERE campeonato_id = ? ORDER BY criado_em DESC", (campeonato_id,))
                else:
                    cursor.execute("SELECT id, campeonato_id, rodada, time_casa, time_fora, gols_casa, gols_fora, encerrada, video_url, data_jogo, criado_em FROM partidas ORDER BY criado_em DESC")
                rows = cursor.fetchall()
                conn.close()
                return [{
                    "id": r[0], "campeonato_id": r[1], "rodada": r[2],
                    "time_casa": r[3], "time_fora": r[4], "gols_casa": r[5],
                    "gols_fora": r[6], "encerrada": bool(r[7]), "video_url": r[8],
                    "data_jogo": r[9], "criado_em": r[10]
                } for r in rows]
            except Exception as e:
                print(f"Erro ao obter partidas local: {e}")
                return []
        return await asyncio.to_thread(fetch)

async def save_partida(partida_data: dict) -> bool:
    if use_supabase:
        def save():
            try:
                supabase_client.table("partidas").upsert(partida_data).execute()
                return True
            except Exception as e:
                print(f"Erro ao salvar partida: {e}")
                return False
        return await asyncio.to_thread(save)
    else:
        def save():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    """INSERT OR REPLACE INTO partidas (id, campeonato_id, rodada, time_casa, time_fora, gols_casa, gols_fora, encerrada, video_url, data_jogo) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        partida_data.get("id"),
                        partida_data.get("campeonato_id"),
                        partida_data.get("rodada"),
                        partida_data.get("time_casa"),
                        partida_data.get("time_fora"),
                        partida_data.get("gols_casa"),
                        partida_data.get("gols_fora"),
                        1 if partida_data.get("encerrada") else 0,
                        partida_data.get("video_url"),
                        partida_data.get("data_jogo")
                    )
                )
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                print(f"Erro ao salvar partida local: {e}")
                return False
        return await asyncio.to_thread(save)

async def delete_partida(partida_id: str) -> bool:
    if use_supabase:
        def remove():
            try:
                supabase_client.table("partidas").delete().eq("id", partida_id).execute()
                return True
            except Exception as e:
                print(f"Erro ao deletar partida: {e}")
                return False
        return await asyncio.to_thread(remove)
    else:
        def remove():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM partidas WHERE id = ?", (partida_id,))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                print(f"Erro ao deletar partida local: {e}")
                return False
        return await asyncio.to_thread(remove)

async def get_all_noticias() -> list[dict]:
    if use_supabase:
        def fetch():
            try:
                res = supabase_client.table("noticias").select("*").order("data_publicacao", desc=True).execute()
                return res.data or []
            except Exception as e:
                print(f"Erro ao obter noticias: {e}")
                return []
        return await asyncio.to_thread(fetch)
    else:
        def fetch():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id, titulo, subtitulo, conteudo, imagem_url, data_publicacao FROM noticias ORDER BY data_publicacao DESC")
                rows = cursor.fetchall()
                conn.close()
                return [{
                    "id": r[0], "titulo": r[1], "subtitulo": r[2],
                    "conteudo": r[3], "imagem_url": r[4], "data_publicacao": r[5]
                } for r in rows]
            except Exception as e:
                print(f"Erro ao obter noticias local: {e}")
                return []
        return await asyncio.to_thread(fetch)

async def save_noticia(noticia_id: str, titulo: str, subtitulo: str = None, conteudo: str = "", imagem_url: str = None) -> bool:
    if use_supabase:
        def save():
            try:
                supabase_client.table("noticias").upsert({
                    "id": noticia_id,
                    "titulo": titulo,
                    "subtitulo": subtitulo,
                    "conteudo": conteudo,
                    "imagem_url": imagem_url
                }).execute()
                return True
            except Exception as e:
                print(f"Erro ao salvar noticia: {e}")
                return False
        return await asyncio.to_thread(save)
    else:
        def save():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT OR REPLACE INTO noticias (id, titulo, subtitulo, conteudo, imagem_url) VALUES (?, ?, ?, ?, ?)",
                    (noticia_id, titulo, subtitulo, conteudo, imagem_url)
                )
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                print(f"Erro ao salvar noticia local: {e}")
                return False
        return await asyncio.to_thread(save)

async def delete_noticia(noticia_id: str) -> bool:
    if use_supabase:
        def remove():
            try:
                supabase_client.table("noticias").delete().eq("id", noticia_id).execute()
                return True
            except Exception as e:
                print(f"Erro ao deletar noticia: {e}")
                return False
        return await asyncio.to_thread(remove)
    else:
        def remove():
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM noticias WHERE id = ?", (noticia_id,))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                print(f"Erro ao deletar noticia local: {e}")
                return False
        return await asyncio.to_thread(remove)
