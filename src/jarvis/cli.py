"""Interface de terminal para primeira fase da JARVIS."""
import argparse
import json
import sys
from .config import Config
from .fcc import FCCClient, FCCError
from .tools import Toolkit
from .memory import Memory
from .agent import Agent

def confirm(action):
    print(f"\n⚠️  AUTORIZAÇÃO NECESSÁRIA: {action}")
    try:
        return input("Autorizar esta operação? Digite SIM: ").strip() == "SIM"
    except EOFError:
        return False

def main():
    parser = argparse.ArgumentParser(description="JARVIS + Free Claude Code")
    parser.add_argument("--models", action="store_true", help="Mostrar modelos disponíveis no FCC")
    parser.add_argument("--health", action="store_true", help="Verificar conexão com FCC")
    args = parser.parse_args()
    c = Config.from_env()
    client = FCCClient(c.url, c.token)
    try:
        if args.health:
            print(json.dumps(client.request("GET", "/health"), ensure_ascii=False))
            return
        if args.models:
            print(json.dumps(client.models(), indent=2, ensure_ascii=False))
            return
        if not c.model:
            parser.error("Defina FCC_MODEL com um ID retornado por 'jarvis --models'")
        mem = Memory(c.db)
        toolkit = Toolkit(c.workspace, approve=confirm)
        agent = Agent(client, toolkit, mem, c.model)
        print(f"JARVIS ativa | Workspace: {c.workspace} | Modelo: {c.model}\nDigite 'sair' para encerrar.")
        while True:
            try:
                msg = input("Você > ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nEncerrando.")
                break
            if msg.lower() in {"sair", "/quit", "exit"}:
                break
            if not msg:
                continue
            try:
                print("JARVIS >", agent.ask(msg), "\n")
            except FCCError as exc:
                print("Erro de conexão:", exc, file=sys.stderr)
        toolkit.close()
        mem.close()
    except FCCError as exc:
        print("Erro:", exc, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
