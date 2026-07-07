# -*- coding: utf-8 -*-
"""
VLS Guru - Módulo de Geração de Prancheta Tática (Pillow)
Desenha o campo, os slots vazios (cartas com + e sigla) ou as cartas dos jogadores.
"""
import os
import hashlib
import urllib.request
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from formations_coordinates import FORMATIONS

# Dimensões padrão do canvas
WIDTH, HEIGHT = 1254, 1254
CARD_W, CARD_H = 120, 168

def load_card_image(card_source: str) -> Image.Image:
    if not card_source:
        return None
    
    # Se for URL
    if card_source.startswith("http://") or card_source.startswith("https://"):
        os.makedirs("cache_cartas", exist_ok=True)
        url_hash = hashlib.md5(card_source.encode("utf-8")).hexdigest()
        cache_path = os.path.join("cache_cartas", f"{url_hash}.png")
        
        if os.path.exists(cache_path):
            try:
                img = Image.open(cache_path).convert("RGBA")
                if img.size == (CARD_W, CARD_H):
                    return img
                # Se estiver com tamanho diferente, redimensiona
                img = img.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)
                img.save(cache_path, "PNG")
                return img
            except Exception:
                pass
                
        try:
            req = urllib.request.Request(
                card_source, 
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                img_data = response.read()
            img = Image.open(BytesIO(img_data)).convert("RGBA")
            img = img.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)
            img.save(cache_path, "PNG")
            return img
        except Exception as e:
            print(f"Erro ao baixar carta {card_source}: {e}")
            return None
            
    # Se for arquivo local
    elif os.path.exists(card_source):
        try:
            img = Image.open(card_source).convert("RGBA")
            if img.size != (CARD_W, CARD_H):
                img = img.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)
            return img
        except Exception:
            return None
            
    return None

# Carregamento de fonte com fallbacks para Windows
def get_font(size, bold=True):
    font_names = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/tahoma.ttf",
    ]
    for path in font_names:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()

def draw_tactical_field() -> Image.Image:
    """
    Carrega o background.png (ou content.png) ou desenha um campo de futebol premium no estilo Dark Néon.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Tenta carregar background.png primeiro (fundo personalizado)
    bg_path = os.path.join(base_dir, "background.png")
    if os.path.exists(bg_path):
        try:
            return Image.open(bg_path).convert("RGBA")
        except Exception:
            pass

    # Tenta carregar content.png como fallback
    content_path = os.path.join(base_dir, "content.png")
    if os.path.exists(content_path):
        try:
            return Image.open(content_path).convert("RGBA")
        except Exception:
            pass

    # Criando o campo do zero
    field = Image.new("RGBA", (WIDTH, HEIGHT), (12, 12, 14, 255))
    draw = ImageDraw.Draw(field)

    # Listras verticais do gramado em tons escuros
    stripe_w = WIDTH // 10
    for i in range(10):
        color = (18, 18, 22, 255) if i % 2 == 0 else (12, 12, 14, 255)
        draw.rectangle([i * stripe_w, 0, (i + 1) * stripe_w, HEIGHT], fill=color)

    # Linhas de marcação do campo (Néon Ciano/Azul suave)
    line_color = (0, 206, 209, 120)  # Cyan néon com transparência
    lw = 6

    # Bordas
    draw.rectangle([40, 40, WIDTH - 40, HEIGHT - 40], outline=line_color, width=lw)
    # Linha do meio de campo
    draw.line([40, HEIGHT // 2, WIDTH - 40, HEIGHT // 2], fill=line_color, width=lw)
    # Círculo central
    draw.ellipse([WIDTH // 2 - 150, HEIGHT // 2 - 150, WIDTH // 2 + 150, HEIGHT // 2 + 150], outline=line_color, width=lw)
    # Ponto central
    draw.ellipse([WIDTH // 2 - 8, HEIGHT // 2 - 8, WIDTH // 2 + 8, HEIGHT // 2 + 8], fill=line_color)

    # Grande Área superior
    draw.rectangle([WIDTH // 2 - 300, 40, WIDTH // 2 + 300, 300], outline=line_color, width=lw)
    # Pequena Área superior
    draw.rectangle([WIDTH // 2 - 120, 40, WIDTH // 2 + 120, 120], outline=line_color, width=lw)
    # Meia-lua superior
    draw.arc([WIDTH // 2 - 120, 220, WIDTH // 2 + 120, 380], start=0, end=180, fill=line_color, width=lw)

    # Grande Área inferior
    draw.rectangle([WIDTH // 2 - 300, HEIGHT - 300, WIDTH // 2 + 300, HEIGHT - 40], outline=line_color, width=lw)
    # Pequena Área inferior
    draw.rectangle([WIDTH // 2 - 120, HEIGHT - 120, WIDTH // 2 + 120, HEIGHT - 40], outline=line_color, width=lw)
    # Meia-lua inferior
    draw.arc([WIDTH // 2 - 120, HEIGHT - 380, WIDTH // 2 + 120, HEIGHT - 220], start=180, end=360, fill=line_color, width=lw)

    # Cantos (Escanteios)
    draw.arc([-20, -20, 80, 80], start=0, end=90, fill=line_color, width=lw)
    draw.arc([WIDTH - 80, -20, WIDTH + 20, 80], start=90, end=180, fill=line_color, width=lw)
    draw.arc([-20, HEIGHT - 80, 80, HEIGHT + 20], start=270, end=360, fill=line_color, width=lw)
    draw.arc([WIDTH - 80, HEIGHT - 80, WIDTH + 20, HEIGHT + 20], start=180, end=270, fill=line_color, width=lw)

    # Moldura externa escura para cabeçalhos e base
    draw.rectangle([0, 0, WIDTH, 100], fill=(0, 0, 0, 180))
    draw.rectangle([0, HEIGHT - 100, WIDTH, HEIGHT], fill=(0, 0, 0, 180))

    return field


def generate_team_pitch(
    starting_xi: list, 
    formation: str, 
    club_name: str, 
    money: int, 
    overall: int, 
    chemistry_bonuses: dict = None
) -> BytesIO:
    """
    Compila a imagem final do campo de 11 jogadores.
    Exibe os slots com cartas de jogadores ou slots de 'mais (+)' vazios.
    """
    # 1. Carrega ou desenha o campo base
    field_img = draw_tactical_field()
    draw = ImageDraw.Draw(field_img, "RGBA")
    
    # 2. Carrega as fontes
    title_font = get_font(34, bold=True)
    metric_font = get_font(26, bold=True)
    label_font = get_font(18, bold=True)
    plus_font = get_font(40, bold=True)
    
    # Dicionário de posições escaladas
    players_by_pos = {p["pos"]: p for p in starting_xi if "pos" in p}
    
    # Coordenadas táticas da formação
    slots = FORMATIONS.get(formation, FORMATIONS["4-3-3"])
    
    # CORES ATUALIZADAS
    # Slot vazio: borda roxa #dc5ce6, fundo preto puro
    EMPTY_BORDER_COLOR = (220, 92, 230, 220)   # #dc5ce6 com alpha
    EMPTY_FILL_COLOR   = (0, 0, 0, 220)         # preto puro
    EMPTY_PLUS_COLOR   = "#dc5ce6"              # roxo para o "+"
    EMPTY_POS_COLOR    = "#dc5ce6"              # roxo para sigla da posição

    # 3. Desenhar cada slot
    for pos_name, coords in slots.items():
        cx, cy = coords["center"]
        player = players_by_pos.get(pos_name)
        
        # Bounding box do slot
        x1 = cx - CARD_W // 2
        y1 = cy - CARD_H // 2
        x2 = cx + CARD_W // 2
        y2 = cy + CARD_H // 2
        
        if player:
            card_img = load_card_image(player.get("card"))
            if card_img:
                if card_img.size != (CARD_W, CARD_H):
                    card_img = card_img.resize((CARD_W, CARD_H), Image.Resampling.LANCZOS)
                field_img.paste(card_img, (x1, y1), card_img)
            else:
                # Fallback: Desenha o bloco clássico do jogador
                color = (40, 40, 45, 240)
                draw.rounded_rectangle([x1, y1, x2, y2], radius=12, fill=color, outline=(255, 255, 255, 180), width=3)
                
                # Nome do jogador
                p_name = player.get("name", "Jogador")[:10].upper()
                name_font = get_font(15, bold=True)
                draw.text((cx, cy - 25), p_name, font=name_font, fill="#ffffff", anchor="mm")
                
                # Posição
                draw.text((cx, cy), pos_name, font=label_font, fill="#00ffff", anchor="mm")
                
                # Overall
                over_font = get_font(20, bold=True)
                draw.text((cx, cy + 25), f"OVR {player.get('over', 0)}", font=over_font, fill="#ffffff", anchor="mm")

            # Desenha o indicador visual de Química de Elenco
            if chemistry_bonuses and player.get("instance_id") in chemistry_bonuses:
                bonus = chemistry_bonuses[player["instance_id"]]
                if bonus > 0:
                    dot_color = (255, 30, 30, 255) if bonus == 3 else ((30, 255, 30, 255) if bonus == 2 else (255, 140, 0, 255))
                    draw.ellipse([x2 - 18, y1 - 4, x2 + 2, y1 + 16], fill=dot_color, outline=(255, 255, 255, 200), width=2)
                    bonus_font = get_font(12, bold=True)
                    draw.text((x2 - 8, y1 + 5), f"+{bonus}", font=bonus_font, fill="#ffffff", anchor="mm")
        else:
            # Slot VAZIO: fundo preto, borda roxa #dc5ce6
            draw.rounded_rectangle(
                [x1, y1, x2, y2],
                radius=12,
                fill=EMPTY_FILL_COLOR,
                outline=EMPTY_BORDER_COLOR,
                width=3
            )
            
            # Sinal de +
            draw.text((cx, cy - 10), "+", font=plus_font, fill=EMPTY_PLUS_COLOR, anchor="mm")
            
            # Sigla da Posição
            draw.text((cx, cy + 25), pos_name, font=label_font, fill=EMPTY_POS_COLOR, anchor="mm")
            
    # 4. Cabeçalho e Rodapé
    # Título: Nome do clube e formação — BRANCO
    top_text = f"{club_name.upper()}  |  FORMATO {formation}"
    draw.text((WIDTH // 2, 50), top_text, font=title_font, fill="#ffffff", anchor="mm")
    
    # Rodapé: Saldo e Overall — reposicionados 20px mais para baixo, cor BRANCA
    draw.text((80, HEIGHT - 32), f"SALDO: R$ {money:,}", font=metric_font, fill="#ffffff", anchor="lm")
    draw.text((WIDTH - 80, HEIGHT - 32), f"OVERALL DO TIME: {overall}", font=metric_font, fill="#ffffff", anchor="rm")
    
    # 5. Exportação
    buffer = BytesIO()
    field_img.save(buffer, "PNG")
    buffer.seek(0)
    return buffer
