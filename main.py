# -*- coding: utf-8 -*-
"""
VLS Guru - Central de Boot e Servidor Web Administrativo (Reboot)
Combina o Discord Bot com a API HTTP REST do Dashboard Administrativo.
"""
import os
import sys
import uuid
import asyncio
import functools
import requests

# Reconfigura streams padrão para UTF-8 (corrige crashes de emojis no console do Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")
from io import BytesIO
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
from aiohttp import web
from PIL import Image
from dotenv import load_dotenv

from database import (
    db_get, db_upsert, db_delete,
    get_user_profile, save_user_profile,
    get_all_players, get_all_users, get_all_collections,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))

DISCORD_TOKEN         = os.getenv("DISCORD_TOKEN")
DISCORD_CLIENT_ID     = os.getenv("DISCORD_CLIENT_ID")
DISCORD_CLIENT_SECRET = os.getenv("DISCORD_CLIENT_SECRET")
DISCORD_REDIRECT_URI  = os.getenv("DISCORD_REDIRECT_URI", "http://localhost:8080/callback")
IMGBB_API_KEY         = "617c898158c94ac25ddaf2491ee7d0b4"

# IDs de usuários com acesso total ao painel admin, mesmo sem ser admin de servidor
ALLOWED_ADMIN_IDS: set[int] = {338704196180115458, 1411893056516391034, 792144300666126336}

# Sessões web em memória
WEB_SESSIONS: dict = {}


# ==============================================================================
# HELPERS DE SESSÃO WEB
# ==============================================================================

def get_session(request: web.Request) -> dict | None:
    cookie = request.cookies.get("session_id")
    if cookie and cookie in WEB_SESSIONS:
        return WEB_SESSIONS[cookie]
    return None


def login_required(func):
    """Decorator que bloqueia rotas da API caso o usuário não esteja autenticado como admin."""
    @functools.wraps(func)
    async def wrapper(request: web.Request, *args, **kwargs):
        session = get_session(request)
        if not session or not session.get("is_admin"):
            return web.json_response(
                {"error": "Acesso negado. Autenticação de administrador obrigatória."},
                status=401,
            )
        request["session"] = session
        return await func(request, *args, **kwargs)
    return wrapper


# ==============================================================================
# INICIALIZAÇÃO DO BOT
# ==============================================================================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="vls!", intents=intents, help_command=None)


# ==============================================================================
# HANDLERS DO SERVIDOR WEB
# ==============================================================================

async def handle_index(request: web.Request) -> web.Response:
    public_index = os.path.join(BASE_DIR, "static", "public", "index.html")
    if os.path.exists(public_index):
        return web.FileResponse(public_index)
    return web.Response(
        text="<h1>Portal da Liga VLS</h1><p>Conexao estabelecida com sucesso.</p>",
        content_type="text/html"
    )


async def handle_paineladm(request: web.Request) -> web.Response:
    admin_index = os.path.join(BASE_DIR, "static", "admin", "index.html")
    if not os.path.exists(admin_index):
        return web.Response(text="Erro: static/admin/index.html não encontrado.", status=404)
    return web.FileResponse(admin_index)


async def handle_login(request: web.Request) -> web.HTTPFound:
    client_id = DISCORD_CLIENT_ID or (str(bot.user.id) if bot.user else None)
    if not client_id:
        return web.Response(text="Erro: DISCORD_CLIENT_ID não configurado no .env.", status=500)

    auth_url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={DISCORD_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope=identify"
    )
    return web.HTTPFound(auth_url)


async def handle_callback(request: web.Request) -> web.Response:
    code = request.query.get("code")
    if not code:
        return web.Response(text="Erro: parâmetro 'code' ausente na requisição.", status=400)

    client_id     = DISCORD_CLIENT_ID or (str(bot.user.id) if bot.user else None)
    client_secret = DISCORD_CLIENT_SECRET
    if not client_id or not client_secret:
        return web.Response(text="Erro: credenciais OAuth2 não configuradas no .env.", status=500)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://discord.com/api/oauth2/token",
                data={
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "grant_type":    "authorization_code",
                    "code":          code,
                    "redirect_uri":  DISCORD_REDIRECT_URI,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    return web.Response(text=f"Erro ao trocar código pelo token Discord: {err}", status=500)
                token_data   = await resp.json()
                access_token = token_data["access_token"]

            async with session.get(
                "https://discord.com/api/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            ) as resp:
                if resp.status != 200:
                    return web.Response(text="Erro ao obter dados do usuário no Discord.", status=500)
                user_data = await resp.json()
    except Exception as exc:
        return web.Response(text=f"Exceção durante o processo de autenticação: {exc}", status=500)

    user_id  = int(user_data["id"])
    is_admin = user_id in ALLOWED_ADMIN_IDS

    if not is_admin:
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member and member.guild_permissions.administrator:
                is_admin = True
                break

    if not is_admin:
        return web.Response(
            text="Acesso negado. Apenas administradores dos servidores autorizados podem acessar este painel.",
            status=403,
        )

    session_token = str(uuid.uuid4())
    WEB_SESSIONS[session_token] = {"user": user_data, "user_id": user_id, "is_admin": True}

    is_secure = (
        request.headers.get("X-Forwarded-Proto", "http") == "https"
        or request.url.scheme == "https"
    )
    response = web.HTTPFound("/paineladm")
    response.set_cookie("session_id", session_token, max_age=60 * 60 * 24 * 7, httponly=True, secure=is_secure, samesite="Lax")
    return response


async def api_auth_status(request: web.Request) -> web.Response:
    session = get_session(request)
    if session:
        return web.json_response({"logged_in": True, "is_admin": session["is_admin"], "user": session["user"]})
    return web.json_response({"logged_in": False})


async def api_auth_logout(request: web.Request) -> web.Response:
    cookie = request.cookies.get("session_id")
    if cookie and cookie in WEB_SESSIONS:
        del WEB_SESSIONS[cookie]
    is_secure = (
        request.headers.get("X-Forwarded-Proto", "http") == "https"
        or request.url.scheme == "https"
    )
    response = web.json_response({"success": True})
    response.set_cookie("session_id", "", max_age=0, httponly=True, secure=is_secure, samesite="Lax")
    return response


# ==============================================================================
# ENDPOINTS DA API — STATS, COLEÇÕES, JOGADORES, MEMBROS
# ==============================================================================

@login_required
async def api_stats(request: web.Request) -> web.Response:
    players = await get_all_players()
    users   = await get_all_users()
    return web.json_response({
        "total_players": len(players),
        "total_users":   len(users),
        "total_money":   sum(u.get("money", 0) for u in users),
    })


@login_required
async def api_get_colecoes(request: web.Request) -> web.Response:
    cols = await get_all_collections()
    return web.json_response([{"id": c["id"], "data": c} for c in cols])


@login_required
async def api_post_colecao(request: web.Request) -> web.Response:
    body = await request.json()
    col_id = body.get("id", "").lower().strip()
    nome   = body.get("nome", "").strip()
    emoji  = body.get("emoji", "").strip()
    max_ps = int(body.get("max_playstyles", 1))

    if not col_id or not nome or not emoji:
        return web.Response(text="Campos obrigatórios ausentes: id, nome, emoji.", status=400)

    doc_id = f"col_{col_id}"
    await db_upsert(doc_id, {
        "id": col_id, "nome": nome, "emoji": emoji,
        "preco_adicional_pct": 0, "max_playstyles": max_ps,
    })
    return web.json_response({"success": True})


@login_required
async def api_delete_colecao(request: web.Request) -> web.Response:
    col_id = request.match_info.get("id")
    await db_delete(f"col_{col_id}")
    return web.json_response({"success": True})


@login_required
async def api_get_jogadores(request: web.Request) -> web.Response:
    players = await get_all_players()
    return web.json_response([{"id": p["id"], "data": p} for p in players])


@login_required
async def api_post_jogador(request: web.Request) -> web.Response:
    data   = await request.post()
    name   = data.get("name", "Jogador")
    over   = int(data.get("over", 75))
    pos    = data.get("pos", "ST").upper()
    col_id = data.get("col_id", "")

    col_name, col_emoji, final_col_id = "Comum", "✨", "comum"
    if col_id:
        c_rec = await db_get(f"col_{col_id.lower().strip()}")
        if c_rec:
            col_name    = c_rec["data"]["nome"]
            col_emoji   = c_rec["data"]["emoji"]
            final_col_id = col_id.lower().strip()

    final_url = await _process_card_upload(data)

    player_id = f"player_{str(uuid.uuid4())[:8]}"
    player_data = {
        "id": player_id, "name": name, "over": over, "pos": pos,
        "card": final_url if final_url else "", "col_id": final_col_id, "col_nome": col_name, "col_emoji": col_emoji,
        "weak_foot": 3, "skill_moves": 3, "playstyles": [],
        "nationality": "Brasil", "club": "VLS FC", "xp": 0,
        # Outfield
        "pac": 75, "sho": 75, "pas": 75, "dri": 75, "def": 75, "phy": 75,
        # GK
        "div": 75, "han": 75, "kic": 75, "ref": 75, "spd": 75, "pos_stat": 75,
        # Compatibility
        "shoot": 75, "pass_stat": 75, "dribble": 75, "defense": 75, "physical": 75,
    }

    if not player_data["card"]:
        return web.json_response({"success": False, "error": "A imagem ou upload da carta é obrigatória."}, status=400)

    await db_upsert(player_id, player_data)
    return web.json_response({"success": True})


async def api_put_jogador(request: web.Request) -> web.Response:
    player_id = request.match_info.get("id")
    data = await request.post()

    old_record = await db_get(player_id)
    if not old_record:
        return web.Response(text="Jogador não localizado.", status=404)

    old_data = old_record["data"]
    col_id   = data.get("col_id", "")
    col_name, col_emoji, final_col_id = old_data.get("col_nome", "Comum"), old_data.get("col_emoji", "✨"), old_data.get("col_id", "comum")

    if col_id:
        c_rec = await db_get(f"col_{col_id.lower().strip()}")
        if c_rec:
            col_name    = c_rec["data"]["nome"]
            col_emoji   = c_rec["data"]["emoji"]
            final_col_id = col_id.lower().strip()

    final_url = await _process_card_upload(data, fallback=old_data.get("card", ""))

    updated = old_data.copy()
    updated.update({
        "name": data.get("name", old_data["name"]),
        "over":  int(data.get("over", old_data["over"])),
        "pos":   data.get("pos", old_data["pos"]).upper(),
        "card":  final_url,
        "col_id": final_col_id, "col_nome": col_name, "col_emoji": col_emoji,
    })

    # Geração automática desabilitada; a imagem da carta é totalmente customizada.

    await db_upsert(player_id, updated)
    return web.json_response({"success": True})


async def api_delete_jogador(request: web.Request) -> web.Response:
    await db_delete(request.match_info.get("id"))
    return web.json_response({"success": True})


@login_required
async def api_get_membros(request: web.Request) -> web.Response:
    db_users    = await get_all_users()
    result_list = []
    for u in db_users:
        user_id  = u["user_id"]
        username = f"Manager #{user_id}"
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                username = member.display_name
                break
        result_list.append({
            "id":            str(user_id),
            "username":      username,
            "avatar":        None,
            "club_name":     u.get("club_name", "FC VLS"),
            "money":         u.get("money", 0),
            "premium_coins": u.get("premium_coins", 0),
            "inventory":     u.get("inventory", []),
        })
    return web.json_response(result_list)


@login_required
async def api_post_member_finance(request: web.Request) -> web.Response:
    user_id = int(request.match_info.get("id"))
    body    = await request.json()
    profile = await get_user_profile(discord.Object(id=user_id))
    profile["money"]         = max(0, int(body.get("money", profile["money"])))
    profile["premium_coins"] = max(0, int(body.get("premium_coins", profile["premium_coins"])))
    await save_user_profile(user_id, profile)
    return web.json_response({"success": True})


@login_required
async def api_post_member_give_player(request: web.Request) -> web.Response:
    user_id = int(request.match_info.get("id"))
    body    = await request.json()
    jogador = body.get("jogador")
    if not jogador:
        return web.Response(text="Dados do jogador ausentes.", status=400)

    profile              = await get_user_profile(discord.Object(id=user_id))
    instanced            = jogador.copy()
    instanced["instance_id"]  = str(uuid.uuid4())
    instanced["original_pos"] = jogador.get("pos", "ST")
    instanced["acquired_at"]  = datetime.utcnow().isoformat()
    instanced["goals"]        = 0
    instanced["assists"]      = 0
    instanced["saves"]        = 0
    instanced["matches"]      = 0
    instanced["mvps"]         = 0
    instanced["yellow_cards"] = 0
    instanced["red_cards"]    = 0
    instanced["xp"]           = 0

    profile["inventory"].append(instanced)
    await save_user_profile(user_id, profile)
    return web.json_response({"success": True})


@login_required
async def api_post_member_remove_player(request: web.Request) -> web.Response:
    user_id   = int(request.match_info.get("id"))
    body      = await request.json()
    idx       = body.get("index")
    profile   = await get_user_profile(discord.Object(id=user_id))
    inventory = profile.get("inventory", [])

    if not isinstance(idx, int) or not (0 <= idx < len(inventory)):
        return web.Response(text="Índice inválido.", status=400)

    removed = inventory.pop(idx)
    profile["starting_xi"] = [
        p for p in profile.get("starting_xi", [])
        if p.get("instance_id") != removed.get("instance_id")
    ]
    profile["inventory"] = inventory
    await save_user_profile(user_id, profile)
    return web.json_response({"success": True})


# ==============================================================================
# HELPER DE UPLOAD DE IMAGEM (ImgBB)
# ==============================================================================

async def _process_general_image_upload(data, url_key: str, file_key: str) -> str:
    """
    Processa um campo de URL ou um arquivo enviado em um form multipart.
    Envia o arquivo para o ImgBB se fornecido, ou retorna a URL direta.
    """
    img_url = data.get(url_key)
    img_file = data.get(file_key)

    if img_url and isinstance(img_url, str) and img_url.strip():
        return img_url.strip()

    if img_file and isinstance(img_file, web.FileField):
        file_bytes = img_file.file.read()

        def _upload() -> str:
            resp = requests.post(
                f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}",
                files={"image": ("image.png", file_bytes)}
            )
            if resp.status_code == 200:
                return resp.json()["data"]["url"]
            print(f"Erro no ImgBB upload: {resp.text}")
            return ""
        return await asyncio.to_thread(_upload)
    return ""

async def _process_card_upload(data, fallback: str = "") -> str:
    """
    Processa o campo 'card_url' ou 'card_file' de um form multipart.
    Retorna a URL final da imagem ou o fallback fornecido.
    """
    card_url  = data.get("card_url")
    card_file = data.get("card_file")

    if card_url and isinstance(card_url, str) and card_url.strip():
        return card_url.strip()

    if card_file and isinstance(card_file, web.FileField):
        file_bytes = card_file.file.read()

        def _upload() -> str:
            img  = Image.open(BytesIO(file_bytes)).convert("RGBA")
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
            buf = BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            resp = requests.post(
                f"https://api.imgbb.com/1/upload?key={IMGBB_API_KEY}",
                files={"image": buf.read()},
            )
            if resp.status_code == 200:
                return resp.json()["data"]["url"]
            return fallback

        return await asyncio.to_thread(_upload)

    return fallback


# ==============================================================================
# ENDPOINTS DE CAMPEONATOS, PARTIDAS E NOTÍCIAS (LIGA VLS)
# ==============================================================================

async def api_get_public_campeonatos(request: web.Request) -> web.Response:
    from database import get_all_campeonatos
    cols = await get_all_campeonatos()
    return web.json_response(cols)


@login_required
async def api_post_campeonato(request: web.Request) -> web.Response:
    from database import save_campeonato
    data = await request.post()
    
    nome = data.get("nome", "").strip()
    c_id = data.get("id", "").strip()
    ativo = data.get("ativo") == "true" or data.get("ativo") == "1" or data.get("ativo") is None

    if not nome:
        return web.Response(text="Nome do campeonato é obrigatório.", status=400)

    if not c_id:
        import uuid
        c_id = str(uuid.uuid4())

    logo_url = await _process_general_image_upload(data, "logo_url", "logo_file")
    
    success = await save_campeonato(c_id, nome, logo_url if logo_url else None, ativo)
    if success:
        return web.json_response({"success": True, "id": c_id})
    return web.Response(text="Erro ao salvar campeonato no banco.", status=500)


@login_required
async def api_delete_campeonato_endpoint(request: web.Request) -> web.Response:
    from database import delete_campeonato
    c_id = request.match_info.get("id")
    success = await delete_campeonato(c_id)
    if success:
        return web.json_response({"success": True})
    return web.Response(text="Erro ao deletar campeonato.", status=500)


async def api_get_public_partidas(request: web.Request) -> web.Response:
    from database import get_all_partidas
    c_id = request.query.get("campeonato_id")
    partidas = await get_all_partidas(c_id)
    return web.json_response(partidas)


@login_required
async def api_post_partida(request: web.Request) -> web.Response:
    from database import save_partida
    body = await request.json()
    
    p_id = body.get("id", "").strip()
    c_id = body.get("campeonato_id", "").strip()
    rodada = body.get("rodada", "").strip()
    time_casa = body.get("time_casa", "").strip()
    time_fora = body.get("time_fora", "").strip()
    
    if not c_id or not rodada or not time_casa or not time_fora:
        return web.Response(text="Campos obrigatórios ausentes para a partida.", status=400)

    if not p_id:
        import uuid
        p_id = str(uuid.uuid4())

    gols_casa = body.get("gols_casa")
    gols_fora = body.get("gols_fora")
    if gols_casa is not None and str(gols_casa).strip() != "":
        gols_casa = int(gols_casa)
    else:
        gols_casa = None

    if gols_fora is not None and str(gols_fora).strip() != "":
        gols_fora = int(gols_fora)
    else:
        gols_fora = None

    partida_data = {
        "id": p_id,
        "campeonato_id": c_id,
        "rodada": rodada,
        "time_casa": time_casa,
        "time_fora": time_fora,
        "gols_casa": gols_casa,
        "gols_fora": gols_fora,
        "encerrada": bool(body.get("encerrada")),
        "video_url": body.get("video_url") if body.get("video_url") else None,
        "data_jogo": body.get("data_jogo") if body.get("data_jogo") else None
    }

    success = await save_partida(partida_data)
    if success:
        return web.json_response({"success": True, "id": p_id})
    return web.Response(text="Erro ao salvar partida.", status=500)


@login_required
async def api_delete_partida_endpoint(request: web.Request) -> web.Response:
    from database import delete_partida
    p_id = request.match_info.get("id")
    success = await delete_partida(p_id)
    if success:
        return web.json_response({"success": True})
    return web.Response(text="Erro ao deletar partida.", status=500)


async def api_get_public_noticias(request: web.Request) -> web.Response:
    from database import get_all_noticias
    noticias = await get_all_noticias()
    return web.json_response(noticias)


@login_required
async def api_post_noticia(request: web.Request) -> web.Response:
    from database import save_noticia
    data = await request.post()
    
    n_id = data.get("id", "").strip()
    titulo = data.get("titulo", "").strip()
    subtitulo = data.get("subtitulo", "").strip()
    conteudo = data.get("conteudo", "").strip()

    if not titulo or not conteudo:
        return web.Response(text="Título e Conteúdo são obrigatórios para a notícia.", status=400)

    if not n_id:
        import uuid
        n_id = str(uuid.uuid4())

    imagem_url = await _process_general_image_upload(data, "imagem_url", "imagem_file")
    
    success = await save_noticia(n_id, titulo, subtitulo if subtitulo else None, conteudo, imagem_url if imagem_url else None)
    if success:
        return web.json_response({"success": True, "id": n_id})
    return web.Response(text="Erro ao salvar notícia no banco.", status=500)


@login_required
async def api_delete_noticia_endpoint(request: web.Request) -> web.Response:
    from database import delete_noticia
    n_id = request.match_info.get("id")
    success = await delete_noticia(n_id)
    if success:
        return web.json_response({"success": True})
    return web.Response(text="Erro ao deletar notícia.", status=500)


async def api_get_public_jogadores_liga(request: web.Request) -> web.Response:
    from database import get_all_jogadores_liga
    c_id = request.query.get("campeonato_id")
    players = await get_all_jogadores_liga(c_id)
    return web.json_response(players)


@login_required
async def api_post_jogador_liga(request: web.Request) -> web.Response:
    from database import save_jogador_liga
    body = await request.json()
    
    p_id = body.get("id", "").strip()
    c_id = body.get("campeonato_id", "").strip()
    nome = body.get("nome", "").strip()
    time_name = body.get("time", "").strip()
    
    if not c_id or not nome or not time_name:
        return web.Response(text="Campos obrigatórios ausentes para o jogador da liga.", status=400)

    if not p_id:
        import uuid
        p_id = str(uuid.uuid4())

    player_data = {
        "id": p_id,
        "campeonato_id": c_id,
        "nome": nome,
        "time": time_name,
        "gols": int(body.get("gols", 0) or 0),
        "assistencias": int(body.get("assistencias", 0) or 0),
        "nota_media": float(body.get("nota_media", 0.0) or 0.0),
        "jogos": int(body.get("jogos", 0) or 0)
    }

    success = await save_jogador_liga(player_data)
    if success:
        return web.json_response({"success": True, "id": p_id})
    return web.Response(text="Erro ao salvar estatísticas do jogador.", status=500)


@login_required
async def api_delete_jogador_liga_endpoint(request: web.Request) -> web.Response:
    from database import delete_jogador_liga
    p_id = request.match_info.get("id")
    success = await delete_jogador_liga(p_id)
    if success:
        return web.json_response({"success": True})
    return web.Response(text="Erro ao deletar estatísticas do jogador.", status=500)


# ==============================================================================
# CONFIGURAÇÃO E INÍCIO DO SERVIDOR WEB
# ==============================================================================

async def start_web_server():
    app = web.Application(client_max_size=1024 ** 2 * 50)

    app.router.add_get("/", handle_index)
    app.router.add_get("/paineladm", handle_paineladm)
    static_path = os.path.join(BASE_DIR, "static")
    app.router.add_static("/static/", path=static_path, name="static")

    # Auth
    app.router.add_get("/login",            handle_login)
    app.router.add_get("/callback",         handle_callback)
    app.router.add_get("/api/auth/status",  api_auth_status)
    app.router.add_get("/api/auth/logout",  api_auth_logout)

    # Stats
    app.router.add_get("/api/stats", api_stats)

    # Campeonatos
    app.router.add_get("/api/public/campeonatos",         api_get_public_campeonatos)
    app.router.add_post("/api/campeonatos",               api_post_campeonato)
    app.router.add_delete("/api/campeonatos/{id}",        api_delete_campeonato_endpoint)

    # Partidas
    app.router.add_get("/api/public/partidas",             api_get_public_partidas)
    app.router.add_post("/api/partidas",                   api_post_partida)
    app.router.add_delete("/api/partidas/{id}",            api_delete_partida_endpoint)

    # Notícias
    app.router.add_get("/api/public/noticias",             api_get_public_noticias)
    app.router.add_post("/api/noticias",                   api_post_noticia)
    app.router.add_delete("/api/noticias/{id}",            api_delete_noticia_endpoint)

    # Jogadores da Liga (Estatísticas)
    app.router.add_get("/api/public/jogadores_liga",       api_get_public_jogadores_liga)
    app.router.add_post("/api/jogadores_liga",             api_post_jogador_liga)
    app.router.add_delete("/api/jogadores_liga/{id}",      api_delete_jogador_liga_endpoint)

    # Coleções
    app.router.add_get("/api/colecoes",          api_get_colecoes)
    app.router.add_post("/api/colecoes",         api_post_colecao)
    app.router.add_delete("/api/colecoes/{id}",  api_delete_colecao)

    # Jogadores
    app.router.add_get("/api/jogadores",          api_get_jogadores)
    app.router.add_post("/api/jogadores",         api_post_jogador)
    app.router.add_put("/api/jogadores/{id}",     api_put_jogador)
    app.router.add_delete("/api/jogadores/{id}",  api_delete_jogador)

    # Membros
    app.router.add_get("/api/membros",                                   api_get_membros)
    app.router.add_post("/api/membros/{id}/finance",                     api_post_member_finance)
    app.router.add_post("/api/membros/{id}/inventario/adicionar",        api_post_member_give_player)
    app.router.add_post("/api/membros/{id}/inventario/remover",          api_post_member_remove_player)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Painel Admin rodando na porta {port}.")


# ==============================================================================
# EVENTOS DO BOT E INICIALIZAÇÃO
# ==============================================================================

@bot.event
async def on_ready():
    print(f"🤖 Bot conectado: {bot.user} (ID: {bot.user.id})")

    cogs_to_load = [
        "cogs.admin",
        "cogs.team",
        "cogs.economy",
        "cogs.market",
        "cogs.matches",
        "cogs.help",
        "cogs.dashboard",
    ]
    for cog_path in cogs_to_load:
        try:
            await bot.load_extension(cog_path)
            print(f"  ✅ Cog carregada: {cog_path}")
        except Exception as exc:
            print(f"  ❌ Falha ao carregar {cog_path}: {exc}")

    try:
        synced = await bot.tree.sync()
        print(f"✨ {len(synced)} comandos slash sincronizados globalmente.")
    except Exception as exc:
        print(f"❌ Erro ao sincronizar comandos: {exc}")

    await start_web_server()


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    import traceback
    print(f"❌ Erro no comando /{interaction.command.name if interaction.command else 'desconhecido'} (Usuário: {interaction.user}): {error}")
    traceback.print_exc()
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(f"❌ Ocorreu um erro ao executar este comando: `{error}`", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ Ocorreu um erro ao executar este comando: `{error}`", ephemeral=True)
    except Exception:
        pass


def kill_duplicate_processes():
    import subprocess
    import os
    import json
    
    my_pid = os.getpid()
    cmd = [
        "powershell", 
        "-NoProfile", 
        "-ExecutionPolicy", "Bypass", 
        "-Command", 
        "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"
    ]
    try:
        out = subprocess.check_output(cmd).decode("utf-8", errors="ignore").strip()
        if not out:
            return
            
        try:
            processes = json.loads(out)
            if not isinstance(processes, list):
                processes = [processes]
        except Exception:
            processes = []
            
        for p in processes:
            pid = p.get("ProcessId")
            cmdline = p.get("CommandLine") or ""
            
            if not pid or pid == my_pid:
                continue
                
            if "main.py" in cmdline.lower():
                print(f"⚠️ [Autoclean] Encerrando bot duplicado em execução (PID {pid})...")
                try:
                    subprocess.call(f"taskkill /F /PID {pid}", shell=True)
                except Exception as e:
                    print(f"❌ [Autoclean] Erro ao derrubar PID {pid}: {e}")
    except Exception as e:
        print(f"❌ [Autoclean] Falha ao executar varredura de processos: {e}")


async def main():
    if not DISCORD_TOKEN:
        print("❌ DISCORD_TOKEN ausente no arquivo .env. Encerrando.")
        return
        
    # Remove qualquer outra instância duplicada do bot rodando em segundo plano antes de iniciar
    kill_duplicate_processes()
    
    await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
