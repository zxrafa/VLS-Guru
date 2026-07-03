def main():
    path = "C:/Jogos/VLS Guru New/cogs/dashboard.py"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
        
    lines = content.split("\n")
    results = []
    for idx, line in enumerate(lines):
        if any(w in line.lower() for w in ["editar jogador", "excluir jogador", "editar_jogador", "excluir_jogador", "class "]):
            results.append(f"Linha {idx+1}: {line.strip()}")
            
    with open("scratch/search_output.txt", "w", encoding="utf-8") as out:
        out.write("\n".join(results))

if __name__ == "__main__":
    main()
