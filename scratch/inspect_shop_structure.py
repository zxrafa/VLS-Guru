with open(r"C:\Jogos\VLS Guru New\cogs\dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

import re
matches = []
for m in re.finditer(r"class [a-zA-Z0-9_]*Loja[a-zA-Z0-9_]*[^\n]*:", content, re.IGNORECASE):
    start = max(0, content.rfind("\n", 0, m.start()))
    end = content.find("\n", m.end())
    matches.append(content[start:end].strip())

print("Classes da Loja:")
for m in matches:
    print("  -", m)

# Procurando campos como "tipo" ou "conteudo" ou "pacote"
print("\nOcorrências de 'conteudo' ou 'tipo' ou 'pacote':")
lines = content.split("\n")
for idx, line in enumerate(lines, 1):
    if any(w in line.lower() for w in ["tipo", "conteudo", "pacote", "loja_custom", "shop"]):
        if any(keyword in line.lower() for keyword in ["select", "button", "input", "modal", "db_"]):
            print(f"L{idx}: {line.strip()}")
