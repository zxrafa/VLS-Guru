# -*- coding: utf-8 -*-
"""
VLS Guru - Fábrica de Coleções de Cartas
Gera variações de coleções de cartas para um jogador (Comum, Raro, TOTW, Icon, Hero, etc.)
e cria versões em tamanho emoji (128x128) para uso no Discord ou WhatsApp.
"""
import os
import io
import re
import sys
import requests
from PIL import Image, ImageDraw, ImageFont

# Reconfigura streams padrão para UTF-8 (corrige crashes de emojis no console do Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# CONFIGURAÇÃO DO JOGADOR ALVO
NOME_JOGADOR_BUSCA = "Vinicius" 

# LISTA DE COLEÇÕES PARA GERAR (Nome da Coleção : ID do Shield na EA)
COLECOES = {
    "1_Padrao": 1,        # Ouro Raro
    "2_TOTW": 3,          # Team of the Week (Preto)
    "3_Icon": 12,         # Icon Legend (Branco)
    "4_Hero": 21,         # Hero (Colorido)
    "5_Event": 45         # Evento Especial
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.ea.com/'
}

def get_default_font(size):
    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/tahoma.ttf"
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def criar_fabrica_de_cartas():
    pasta_cartas = "Colecao_Cartas"
    pasta_emojis = "Colecao_Emojis"
    os.makedirs(pasta_cartas, exist_ok=True)
    os.makedirs(pasta_emojis, exist_ok=True)

    print(f"🔍 Buscando dados de: {NOME_JOGADOR_BUSCA} na API da EA...")
    url_api = "https://drop-api.ea.com/rating/ea-sports-fc"
    params = {"locale": "pt-br", "limit": 10, "search": NOME_JOGADOR_BUSCA} 
    
    try:
        res = requests.get(url_api, params=params, headers=HEADERS, timeout=10)
        if res.status_code != 200:
            print(f"❌ Erro ao conectar na API da EA: HTTP {res.status_code}")
            return
        
        jogadores = res.json().get("items", [])
    except Exception as e:
        print(f"❌ Erro na requisição da API: {e}")
        return
    
    if not jogadores:
        print(f"❌ Nenhum jogador encontrado para o termo '{NOME_JOGADOR_BUSCA}'")
        return
        
    jogador_alvo = None
    for p in jogadores:
        if NOME_JOGADOR_BUSCA.lower() in (p.get("commonName") or "").lower() or \
           NOME_JOGADOR_BUSCA.lower() in p.get("lastName", "").lower() or \
           NOME_JOGADOR_BUSCA.lower() in p.get("firstName", "").lower():
            jogador_alvo = p
            break
            
    if not jogador_alvo:
        jogador_alvo = jogadores[0]
        
    print(f"✅ Jogador encontrado: {jogador_alvo.get('firstName')} {jogador_alvo.get('lastName')} (ID: {jogador_alvo.get('id')})")
    
    # Extrai o ID real do jogador para buscar a foto
    avatar_url = jogador_alvo.get("avatarUrl", "")
    match = re.search(r'/p(\d+)\.png', avatar_url)
    if match:
        ea_id = match.group(1)
    else:
        ea_id = str(jogador_alvo.get("id"))
        
    nome = jogador_alvo.get("commonName") or jogador_alvo.get("lastName") or NOME_JOGADOR_BUSCA
    overall = jogador_alvo.get("overallRating", 80)
    
    # Baixar a foto do rosto (avatar transparente)
    print("📸 Baixando foto de avatar transparente...")
    url_avatar = jogador_alvo.get("avatarUrl") or f"https://ratings-images-prod.pulse.ea.com/FC25/full/player-portraits/p{ea_id}.png"
    try:
        r_avatar = requests.get(url_avatar, headers=HEADERS, timeout=10)
        if r_avatar.status_code == 200:
            avatar_img = Image.open(io.BytesIO(r_avatar.content)).convert("RGBA")
        else:
            print("❌ Avatar não encontrado com URL padrão. Tentando URL alternativa...")
            url_fallback = f"https://ratings-images-prod.pulse.ea.com/FC25/full/player-portraits/p{ea_id}.png"
            r_fallback = requests.get(url_fallback, headers=HEADERS, timeout=10)
            avatar_img = Image.open(io.BytesIO(r_fallback.content)).convert("RGBA")
    except Exception as e:
        print(f"❌ Não foi possível obter o rosto do jogador: {e}")
        return

    # Loop para gerar as cartas de coleções
    for nome_colecao, id_shield in COLECOES.items():
        print(f"🎨 Gerando versão: {nome_colecao} (Shield ID {id_shield})...")
        url_shield = f"https://ratings-images-prod.pulse.ea.com/FC25/full/shields/p/{id_shield}.png"
        
        try:
            resp_shield = requests.get(url_shield, headers=HEADERS, timeout=10)
            if resp_shield.status_code != 200:
                print(f"   ⚠️ Escudo ID {id_shield} indisponível. Pulando.")
                continue
                
            fundo = Image.open(io.BytesIO(resp_shield.content)).convert("RGBA")
        except Exception as e:
            print(f"   ⚠️ Erro ao baixar escudo {id_shield}: {e}")
            continue

        largura, altura = fundo.size
        
        # Ajusta e redimensiona o rosto para centralizar na carta
        rosto_redim = avatar_img.resize((int(largura * 0.70), int(largura * 0.70)), Image.Resampling.LANCZOS)
        
        # Cria a carta final e posiciona o rosto
        carta_final = fundo.copy()
        pos_x = int((largura - rosto_redim.width) / 2)
        pos_y = int(altura * 0.15)
        
        carta_final.paste(rosto_redim, (pos_x, pos_y), rosto_redim)
        
        # Desenha textos (Overall e Nome)
        draw = ImageDraw.Draw(carta_final)
        
        # Se for uma carta especial, dá um boost no Overall
        over_ficticio = overall + (2 if id_shield > 10 else 0)
        
        # Cor de texto adequada para o fundo
        cor_texto = (255, 255, 255, 255) if id_shield in [3, 12, 21] else (20, 20, 20, 255)
        
        # Fontes
        font_over = get_default_font(int(altura * 0.10))
        font_nome = get_default_font(int(altura * 0.05))
        
        # Escreve Overall
        draw.text((int(largura * 0.15), int(altura * 0.15)), str(over_ficticio), fill=cor_texto, font=font_over)
        
        # Escreve Nome (centralizado horizontalmente no rodapé)
        nome_str = nome.upper()
        nome_w = draw.textlength(nome_str, font=font_nome)
        pos_nome_x = int((largura - nome_w) / 2)
        pos_nome_y = int(altura * 0.62)
        draw.text((pos_nome_x, pos_nome_y), nome_str, fill=cor_texto, font=font_nome)

        # Salva a carta grande
        nome_arq = f"{nome.replace(' ', '_')}_{nome_colecao}.png"
        caminho_carta = os.path.join(pasta_cartas, nome_arq)
        carta_final.save(caminho_carta, "PNG")
        print(f"   💾 Salvo em: {caminho_carta}")

        # Salva a miniatura (Emoji)
        emoji = carta_final.copy()
        emoji.thumbnail((128, 128), Image.Resampling.LANCZOS)
        caminho_emoji = os.path.join(pasta_emojis, f"emoji_{nome_arq}")
        emoji.save(caminho_emoji, "PNG")

    print("\n🎉 Todas as variações de cartas e emojis foram geradas com sucesso!")
    print(f"📁 Pasta de cartas completas: {os.path.abspath(pasta_cartas)}")
    print(f"📁 Pasta de emojis do Discord: {os.path.abspath(pasta_emojis)}")

if __name__ == "__main__":
    criar_fabrica_de_cartas()
