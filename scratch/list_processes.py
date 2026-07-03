import subprocess

def main():
    try:
        out = subprocess.check_output("tasklist", shell=True).decode("utf-8", errors="ignore")
        for line in out.split("\n"):
            if "py" in line.lower() or "python" in line.lower():
                print(line)
    except Exception as e:
        print("Erro:", e)

if __name__ == "__main__":
    main()
