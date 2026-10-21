"""CLI de texto e modo de voz opcional e acionado pelo usuário."""
import argparse
import json
import os
import sys
from .config import Config
from .fcc import FCCClient, FCCError, AutoModelClient
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
    parser.add_argument("--desktop-info", action="store_true", help="Inspeciona portais e compositor Wayland sem iniciar FCC")
    parser.add_argument("--desktop-screenshot", action="store_true", help="Solicita captura de tela via portal Wayland com confirmação")
    parser.add_argument("--check-fcc", action="store_true", help="Teste real da API e modelo com failover")
    parser.add_argument("--voice", action="store_true", help="Modo de voz: Enter inicia gravação de 6 segundos")
    args = parser.parse_args()
    c = Config.from_env()
    if args.desktop_info:
        from .wayland import desktop_info
        print(json.dumps(desktop_info(), indent=2, ensure_ascii=False))
        return
    if args.desktop_screenshot:
        from .wayland import screenshot, WaylandError
        try:
            print(json.dumps(screenshot(c.workspace, confirm), ensure_ascii=False, indent=2))
        except WaylandError as exc:
            print(f"Erro do portal Wayland: {exc}", file=sys.stderr)
            sys.exit(1)
        return
    client = FCCClient(c.url, c.token)
    try:
        if args.health:
            print(json.dumps(client.request("GET", "/health"), ensure_ascii=False))
            return
        if args.models:
            print(json.dumps(client.models(), indent=2, ensure_ascii=False))
            return
        auto = AutoModelClient(client, preferred=c.model,
                               backups=[x.strip() for x in os.getenv("FCC_FALLBACK_MODELS", "").split(",") if x.strip()],
                               on_switch=lambda model: print(f"⚠️ FCC: modelo alterado automaticamente para {model}"))
        if args.check_fcc:
            print(json.dumps({"health": client.health(), "inference": auto.diagnostic()}, ensure_ascii=False, indent=2))
            return
        auto.initialize()
        mem = Memory(c.db)
        toolkit = Toolkit(c.workspace, approve=confirm)
        agent = Agent(auto, toolkit, mem, auto.active_model)
        voice = None
        if args.voice:
            from .voice import VoiceIO
            voice = VoiceIO(model=os.getenv("JARVIS_WHISPER_MODEL", "tiny"),
                            language=os.getenv("JARVIS_LANGUAGE", "pt"),
                            piper_model=os.getenv("JARVIS_PIPER_MODEL", ""))
            print("MODO VOZ: pressione Enter para gravar 6 segundos; digite sair para encerrar.")
        print(f"JARVIS ativa | Workspace: {c.workspace} | Modelo inicial: {auto.active_model}")
        try:
            while True:
                try:
                    if voice is not None:
                        command = input("Você [Enter = falar / sair] > ").strip()
                        if command.lower() in {"sair", "/quit", "exit"}:
                            break
                        if command:
                            msg = command
                        else:
                            print("🎙️ Gravando por 6 segundos...")
                            try:
                                msg = voice.listen_once(6)
                            except Exception as exc:
                                print(f"Falha de gravação/transcrição: {exc}", file=sys.stderr)
                                continue
                            print("Você (voz) >", msg or "[nenhuma fala reconhecida]")
                    else:
                        msg = input("Você > ").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\nEncerrando.")
                    break
                if msg.lower() in {"sair", "/quit", "exit"}:
                    break
                if not msg:
                    continue
                try:
                    answer = agent.ask(msg)
                    print("JARVIS >", answer, "\n")
                    if voice:
                        try:
                            status = voice.speak(answer)
                            if status == "disabled":
                                print("Para ouvir respostas, configure JARVIS_PIPER_MODEL.")
                        except Exception as exc:
                            print(f"Falha ao falar resposta: {exc}", file=sys.stderr)
                except (FCCError, ValueError) as exc:
                    print("Erro de modelo/protocolo:", exc, file=sys.stderr)
        finally:
            toolkit.close()
            mem.close()
    except FCCError as exc:
        print("Erro:", exc, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
