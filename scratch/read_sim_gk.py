import re
import json

def main():
    gk_terms = ["div", "han", "kic", "ref", "spd", "pos", "gk", "goleiro"]
    results = []
    with open("simulation.py", "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line_lower = line.lower()
            matched = [t for t in gk_terms if t in line_lower]
            if matched:
                results.append({
                    "line_number": idx + 1,
                    "content": line.strip(),
                    "matched": matched
                })
    with open("scratch/gk_sim_results.json", "w", encoding="utf-8") as out:
        json.dump(results, out, indent=2)
    print("Done")

if __name__ == "__main__":
    main()
