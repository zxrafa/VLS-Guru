import json

def main():
    playstyles = ["tecnica", "trivela", "rapid", "anjo", "arremesso_especial", "encaixada", "acrobata", "superchute", "malvadeza", "perde_pressiona", "ima_no_pe"]
    results = []
    with open("simulation.py", "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            line_lower = line.lower()
            found_ps = [ps for ps in playstyles if ps in line_lower]
            if "playstyle" in line_lower or found_ps:
                results.append({
                    "line_number": idx + 1,
                    "content": line.strip(),
                    "matched_playstyles": found_ps
                })
                
    with open("scratch/playstyle_sim_results.json", "w", encoding="utf-8") as out:
        json.dump(results, out, indent=2)
    print("Done")

if __name__ == "__main__":
    main()
