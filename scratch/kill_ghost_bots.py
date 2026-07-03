# -*- coding: utf-8 -*-
import subprocess
import os
import sys
import json

def main():
    my_pid = os.getpid()
    print(f"PID do Script de Limpeza: {my_pid}")
    
    cmd = [
        "powershell", 
        "-NoProfile", 
        "-ExecutionPolicy", "Bypass", 
        "-Command", 
        "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%'\" | Select-Object ProcessId, CommandLine | ConvertTo-Json"
    ]
    try:
        out = subprocess.check_output(cmd).decode("utf-8", errors="ignore").strip()
        if not out:
            print("Nenhum processo python em execução encontrado.")
            return
            
        try:
            processes = json.loads(out)
            if not isinstance(processes, list):
                processes = [processes]
        except Exception:
            # Caso seja um único dicionário em string ou formato não-JSON
            processes = []
            
        killed_count = 0
        for p in processes:
            pid = p.get("ProcessId")
            cmdline = p.get("CommandLine") or ""
            
            if not pid or pid == my_pid:
                continue
                
            # Identifica se é o bot de discord VLS Guru (que roda o main.py)
            if "main.py" in cmdline.lower():
                print(f"Identificado processo fantasma (PID {pid}): {cmdline}")
                try:
                    subprocess.call(f"taskkill /F /PID {pid}", shell=True)
                    print(f"  -> PID {pid} derrubado com sucesso!")
                    killed_count += 1
                except Exception as e:
                    print(f"  -> Erro ao derrubar PID {pid}: {e}")
                    
        print(f"\nLimpeza finalizada! {killed_count} instâncias fantasmas de bots foram encerradas.")
    except Exception as e:
        print(f"Erro ao listar e gerenciar processos: {e}")

if __name__ == "__main__":
    main()
