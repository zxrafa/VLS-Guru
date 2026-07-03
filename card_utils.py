# -*- coding: utf-8 -*-
"""
VLS Guru - Utilitários de Cartas de Jogadores
Faz download das cartas oficiais da EA e aplica transformações de cores (Pillow/HSV)
para cada coleção (Verde para Comum, Azul para Premiados, Rosa para Eai, etc.).
"""
import os
import re
import json
import sqlite3
import requests
import colorsys
from io import BytesIO
from PIL import Image

# Mapeamento manual para jogadores famosos/especiais
SPECIAL_MAP = {
    "endrick": "272505",
    "l. messi": "158023",
    "lionel messi": "158023",
    "c. ronaldo": "20801",
    "cristiano ronaldo": "20801"
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.ea.com/'
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_CARTAS_DIR = os.path.join(BASE_DIR, "static", "cartas")
CACHE_DIR = os.path.join(BASE_DIR, "cache_cartas")

def search_ea_id(player_name):
    url = "https://drop-api.ea.com/rating/ea-sports-fc"
    params = {
        "locale": "pt-br",
        "limit": 5,
        "search": player_name
    }
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=5)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if items:
                avatar_url = items[0].get("avatarUrl", "")
                match = re.search(r'/p(\d+)\.png', avatar_url)
                if match:
                    return match.group(1)
                return str(items[0].get("id"))
    except Exception as e:
        print(f"[CardUtils] Erro ao buscar ID EA para {player_name}: {e}")
    return None

def get_ea_id(player_name, old_card=None):
    name_lower = player_name.lower().strip()
    if name_lower in SPECIAL_MAP:
        return SPECIAL_MAP[name_lower]
        
    if old_card:
        match = re.search(r'/p(\d+)\.png', old_card)
        if match:
            return match.group(1)
            
    ea_id = search_ea_id(player_name)
    if not ea_id:
        clean_name = re.sub(r'^[A-Z]\.\s+', '', player_name)
        if clean_name != player_name:
            ea_id = search_ea_id(clean_name)
            
    return ea_id

def process_hsv_shift(img, col_id):
    """
    Muda a cor dos tons amarelos/dourados do card de acordo com a coleção.
    """
    width, height = img.size
    # Convert output image to RGBA
    img = img.convert("RGBA")
    pixels = img.load()
    
    target_hue = None
    sat_multiplier = 1.0
    val_multiplier = 1.0
    
    col_id_lower = col_id.lower().strip() if col_id else "base"
    
    if col_id_lower == "comum":
        target_hue = 0.33      # Verde
    elif col_id_lower == "premiados":
        target_hue = 0.61      # Azul
    elif col_id_lower == "eai":
        target_hue = 0.89      # Rosa/Magenta
    elif col_id_lower == "tots":
        target_hue = 0.53      # Ciano (TOTS)
    elif col_id_lower == "base":
        sat_multiplier = 0.05  # Desatura quase tudo, tornando o fundo cinza/prata
    else:
        # copa_do_mundo, wcup ou desconhecidos: mantém dourado original
        return img
        
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
                
            # Converter para HSV
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            
            # Pixels dourados/amarelos do card (Hue entre 30 e 65 graus, com sat/val médios)
            if 0.07 <= h <= 0.18 and s > 0.15 and v > 0.15:
                new_h = target_hue if target_hue is not None else h
                new_s = min(1.0, max(0.0, s * sat_multiplier))
                new_v = min(1.0, max(0.0, v * val_multiplier))
                
                new_r, new_g, new_b = colorsys.hsv_to_rgb(new_h, new_s, new_v)
                pixels[x, y] = (int(new_r * 255), int(new_g * 255), int(new_b * 255), a)
                
    return img

def generate_player_card_sync(player_data):
    """
    Sincroniza o download e processamento da imagem da carta do jogador.
    Retorna o caminho relativo (ex: 'static/cartas/player_abc.png') se sucesso, ou string vazia.
    """
    os.makedirs(STATIC_CARTAS_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    
    p_id = player_data.get("id")
    name = player_data.get("name")
    col_id = player_data.get("col_id", "base")
    old_card = player_data.get("card", "")
    
    # 1. Obter EA ID
    ea_id = get_ea_id(name, old_card)
    if not ea_id:
        print(f"[CardUtils] EA ID não encontrado para {name}. Pulando geração visual.")
        return ""
        
    # 2. Obter base da carta
    cache_base_path = os.path.join(CACHE_DIR, f"base_{ea_id}.png")
    
    if not os.path.exists(cache_base_path) or os.path.getsize(cache_base_path) < 10000:
        # Baixar da EA
        shield_url = f"https://ratings-images-prod.pulse.ea.com/FC25/full/player-shields/pt-br/{ea_id}.png?width=265"
        try:
            r = requests.get(shield_url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                with open(cache_base_path, "wb") as f:
                    f.write(r.content)
            else:
                print(f"[CardUtils] Falha ao baixar base do card para {name} (HTTP {r.status_code})")
                return ""
        except Exception as e:
            print(f"[CardUtils] Erro ao baixar base do card para {name}: {e}")
            return ""
            
    # 3. Carregar e processar a carta com a cor da coleção
    try:
        base_img = Image.open(cache_base_path)
        processed_img = process_hsv_shift(base_img, col_id)
        
        # Salva o arquivo final na pasta de cartas
        dest_filename = f"{p_id}.png"
        dest_filepath = os.path.join(STATIC_CARTAS_DIR, dest_filename)
        processed_img.save(dest_filepath, "PNG")
        
        # Retorna o caminho relativo para salvar no banco
        relative_path = f"static/cartas/{dest_filename}"
        return relative_path
    except Exception as e:
        print(f"[CardUtils] Erro ao processar imagem para {name}: {e}")
        return ""
