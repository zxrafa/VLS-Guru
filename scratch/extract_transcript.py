import json
import os

def main():
    transcript_path = r"C:\Users\MANCER\.gemini\antigravity-cli\brain\6f3407da-60f1-40cf-9119-2ff2190c943c\.system_generated\logs\transcript_full.jsonl"
    out_dir = "scratch"
    os.makedirs(out_dir, exist_ok=True)
    
    found = False
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            if '"step_index":4169' in line or '"step_index": 4169' in line:
                data = json.loads(line)
                with open(os.path.join(out_dir, "step_4169.json"), "w", encoding="utf-8") as out:
                    json.dump(data, out, indent=4)
                print("Extracted step 4169 to scratch/step_4169.json")
                found = True
                break
            if 'CriarJogadorModal2' in line and '"type":"CODE_ACTION"' in line:
                print("Found match in line:", line[:200])
    if not found:
        print("Step 4169 not found.")

if __name__ == "__main__":
    main()
