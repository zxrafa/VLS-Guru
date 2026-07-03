# -*- coding: utf-8 -*-
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

def main():
    print("🔒 CONFIGURAÇÃO PROTEGIDA - VLS GURU")
    print("=====================================")
    
    senha = input("Digite a senha de acesso: ")
    
    if senha == "1304":
        print("\n✅ Acesso concedido!")
        print("Conteúdo guardado:")
        print("------------------")
        print("@vlsguruotavio")
        print("------------------")
    else:
        print("\n❌ Senha incorreta. Acesso negado.")

if __name__ == "__main__":
    main()
