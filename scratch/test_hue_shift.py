import os
from PIL import Image
import colorsys

# Paths
input_card = r"C:\Jogos\VLS Guru New\static\cartas\player_messi.png"
if not os.path.exists(input_card):
    # Try another one
    input_card = r"C:\Jogos\VLS Guru New\static\cartas\player_lionel_messi_rw.png"

artifact_dir = r"C:\Users\MANCER\.gemini\antigravity-cli\brain\6f3407da-60f1-40cf-9119-2ff2190c943c"

def shift_card_color(img_path, target_hue, name):
    if not os.path.exists(img_path):
        print(f"Error: {img_path} not found")
        return
        
    img = Image.open(img_path).convert("RGBA")
    width, height = img.size
    pixels = img.load()
    
    # We will iterate and shift yellow/gold hues to the target hue
    # Gold hue is typically between 30 and 60 degrees (0.08 to 0.17 in colorsys 0-1 range)
    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
                
            # Convert to HSV
            h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
            
            # Gold color range in HSV:
            # Hue ~ 0.08 to 0.16 (30 to 58 degrees)
            # Saturation > 0.15
            # Value > 0.15
            if 0.08 <= h <= 0.18 and s > 0.15 and v > 0.15:
                # Calculate new hue (shifted to target)
                # Keep original saturation and value for shading/gradients
                new_r, new_g, new_b = colorsys.hsv_to_rgb(target_hue, s, v)
                pixels[x, y] = (int(new_r * 255), int(new_g * 255), int(new_b * 255), a)
                
    out_path = os.path.join(artifact_dir, f"test_card_{name}.png")
    img.save(out_path, "PNG")
    print(f"Saved: {out_path}")

# Hues:
# Green (comum): ~120 degrees (0.33)
# Blue (premiados): ~220 degrees (0.61)
# Pink (eai): ~320 degrees (0.89)
# Gold (original): ~45 degrees (0.12)
# TOTS (Cyan/Blue gradient): we can shift to cyan (0.50) or do a dual-tone shift

print("Shifting colors of Messi's card...")
shift_card_color(input_card, 0.33, "comum_green")
shift_card_color(input_card, 0.61, "premiados_blue")
shift_card_color(input_card, 0.89, "eai_pink")
