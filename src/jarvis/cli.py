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
from .approval import ApprovalPolicy
from .service import JarvisService
from .plugins import load_plugins
from .tools import DEFAULT_REGISTRY

def confirm(action):
    print(f"\n⚠️  AUTORIZAÇÃO NECESSÁRIA: {action}")
    try:
        return input("Autorizar esta operação? Digite SIM: ").strip().casefold() == "sim"
    except EOFError:
        return False

def main():
    parser = argparse.ArgumentParser(description="JARVIS + Free Claude Code")
    parser.add_argument("--locate-target", metavar="ALVO", help="Localiza visualmente alvo e salva imagem anotada; nunca clica")
    parser.add_argument("--guided-click", metavar="ALVO", help="Clique visual supervisionado com cursor posicionado pelo usuário e verificação posterior")
    parser.add_argument("--see-screen", nargs="?", const="Descreva o conteúdo visível nesta tela.", metavar="PERGUNTA", help="Analisa captura Wayland com modelo visual explícito e permissões do portal")
    parser.add_argument("--doctor", action="store_true", help="Diagnóstico local da instalação, sem precisar do servidor FCC")
    parser.add_argument("--models-diagnostic", action="store_true", help="Comparar catálogos Responses, padrão e admin sem inferência")
    parser.add_argument("--models", action="store_true", help="Mostrar modelos disponíveis no FCC")
    parser.add_argument("--health", action="store_true", help="Verificar conexão com FCC")
    parser.add_argument("--windows-diagnostic", action="store_true", help="Diagnóstico parcial de janelas acessíveis via AT-SPI, sem FCC")
    parser.add_argument("--desktop-info", action="store_true", help="Inspeciona portais e compositor Wayland sem iniciar FCC")
    parser.add_argument("--desktop-click-test", action="store_true", help="Teste autorizado: um clique esquerdo na posição do cursor")
    parser.add_argument("--desktop-keyboard-test", action="store_true", help="Teste autorizado: digitar apenas letra j no campo em foco")
    parser.add_argument("--desktop-remote-test", action="store_true", help="Solicita permissão RemoteDesktop e testa pequeno movimento de ponteiro")
    parser.add_argument("--desktop-screenshot", action="store_true", help="Solicita captura de tela via portal Wayland com confirmação")
    parser.add_argument("--check-fcc", action="store_true", help="Teste real da API e modelo com failover")
    parser.add_argument("--audio-devices", action="store_true", help="Listar entradas de áudio sem conectar ao FCC")
    parser.add_argument("--audio-device", metavar="NOME", help="Nome inequívoco da entrada SoundDevice")
    parser.add_argument("--voice", action="store_true", help="Conversa contínua: diga Jarvis seguido do comando, sem Enter")
    parser.add_argument("--text-only", action="store_true", help="Somente mensagens; não inicia microfone")
    parser.add_argument("--push-to-talk", action="store_true", help="Modo antigo: Enter grava e permite revisar a transcrição")
    parser.add_argument("--gui", action="store_true", help="Abrir interface gráfica com conversa de voz opcional")
    approval_group = parser.add_mutually_exclusive_group()
    approval_group.add_argument("--auto-approve", action="store_true", help="Modo automático (padrão; mantido por compatibilidade)")
    approval_group.add_argument("--manual-approve", action="store_true", help="Pedir confirmação no terminal para cada ação")
    args = parser.parse_args()
    if args.audio_devices:
        from .voice import VoiceIO, VoiceError
        try:
            for index, name in VoiceIO.input_devices():
                print(f"{index}: {name}")
        except VoiceError as exc:
            parser.exit(1, str(exc) + "\n")
        return
    if args.audio_device is not None:
        os.environ["JARVIS_AUDIO_DEVICE"] = args.audio_device
    c = Config.from_env()
    approval = ApprovalPolicy(auto=not args.manual_approve, manual_callback=globals()["confirm"])
    confirm = approval
    if args.gui:
        if args.text_only:
            os.environ["JARVIS_GUI_VOICE"] = "0"
        from .gui import main_gui
        main_gui(c, auto=not args.manual_approve)
        return
    if args.doctor:
        from pathlib import Path
        import importlib.util
        print(json.dumps({
            "application": "jarvis-fcc",
            "module": str(Path(__file__).resolve()),
            "python": sys.executable,
            "workspace": str(c.workspace),
            "fcc_url": c.url,
            "browser_package_installed": importlib.util.find_spec("playwright") is not None,
            "voice_package_installed": importlib.util.find_spec("faster_whisper") is not None,
            "desktop_package_installed": importlib.util.find_spec("dbus_next") is not None,
        }, ensure_ascii=False, indent=2))
        return
    if args.windows_diagnostic:
        from .desktop_windows import desktop_windows
        print(json.dumps(desktop_windows(), ensure_ascii=False, indent=2))
        return
    if args.desktop_info:
        from .wayland import desktop_info
        print(json.dumps(desktop_info(), indent=2, ensure_ascii=False))
        return
    if args.desktop_click_test or args.desktop_keyboard_test:
        from .remote_desktop import test_input
        from .wayland import WaylandError
        try:
            result = test_input(confirm, "click" if args.desktop_click_test else "keyboard")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except (WaylandError, OSError) as exc:
            print("Erro no teste de entrada Wayland:", exc, file=sys.stderr)
            sys.exit(1)
        return
    if args.desktop_remote_test:
        from .remote_desktop import test_remote_pointer
        from .wayland import WaylandError
        try:
            print(json.dumps(test_remote_pointer(confirm), ensure_ascii=False, indent=2))
        except (WaylandError, OSError) as exc:
            print(f"Erro RemoteDesktop: {exc}", file=sys.stderr)
            sys.exit(1)
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
    if args.locate_target is not None:
        from .targeting import locate_target
        from .wayland import WaylandError
        try:
            result = locate_target(client, c.model, c.workspace, confirm, args.locate_target)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except (FCCError, WaylandError, OSError) as exc:
            print("Erro ao localizar alvo:", exc, file=sys.stderr)
            sys.exit(1)
        return
    if args.guided_click is not None:
        from .guided_desktop import guided_click
        from .wayland import WaylandError
        if not c.model:
            parser.error("Defina FCC_MODEL=ollama/<modelo> para usar clique guiado.")
        try:
            result = guided_click(client, c.model, c.workspace, confirm, args.guided_click)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except (FCCError, WaylandError, OSError) as exc:
            print("Erro no clique guiado:", exc, file=sys.stderr)
            sys.exit(1)
        return
    if args.see_screen is not None:
        from .vision import analyze_screen
        from .wayland import WaylandError
        if not c.model:
            parser.error("Para analisar imagens, defina FCC_MODEL com modelo explícito com suporte a visão.")
        try:
            result = analyze_screen(client, c.model, c.workspace, confirm, args.see_screen)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        except (FCCError, WaylandError) as exc:
            print("Erro na análise da tela:", exc, file=sys.stderr)
            sys.exit(1)
        return
    try:
        if args.models_diagnostic:
            from .catalog_diagnostic import inspect_catalog
            print(json.dumps(inspect_catalog(client), ensure_ascii=False, indent=2))
            return
        if args.health:
            print(json.dumps(client.request("GET", "/health"), ensure_ascii=False))
            return
        if args.models:
            catalog = client.models()
            print("Modelo padrão:", catalog.get("default_model_id", "não informado"))
            for number, model in enumerate(catalog.get("data", []), 1):
                print(f"{number:>2}. {model.get('id', '?')}")
            return
        auto = AutoModelClient(client, preferred=c.model,
                               backups=[x.strip() for x in os.getenv("FCC_FALLBACK_MODELS", "").split(",") if x.strip()],
                               allow_cross_provider=os.getenv("FCC_ALLOW_CROSS_PROVIDER", "") == "1",
                               on_switch=lambda model: print(f"⚠️ FCC: modelo alterado automaticamente para {model}"))
        if args.check_fcc:
            print(json.dumps({"health": client.health(), "inference": auto.diagnostic()}, ensure_ascii=False, indent=2))
            return
        auto.initialize()
        mem = Memory(c.db)
        try:
            registry = load_plugins(DEFAULT_REGISTRY, os.getenv("JARVIS_PLUGINS", ""))
            toolkit = Toolkit(c.workspace, approve=confirm, layout_db=c.db,
                              registry=registry)
        except ValueError as exc:
            parser.error(str(exc))
        agent = Agent(auto, toolkit, mem, auto.active_model)
        from .planner import TaskPlanner
        from .plan_store import PlanStore
        from .plan_view import format_plan, format_history
        plan_store = PlanStore(c.db)
        planner = TaskPlanner(auto, agent, store=plan_store)
        service = JarvisService(auto, agent, toolkit, mem, planner, approval)
        voice = None
        mixed = None
        if not args.text_only or args.push_to_talk:
            from .voice import VoiceIO
            voice = VoiceIO(model=os.getenv("JARVIS_WHISPER_MODEL", "base"),
                            language=os.getenv("JARVIS_LANGUAGE", "pt"),
                            piper_model=os.getenv("JARVIS_PIPER_MODEL", ""))
            if args.push_to_talk:
                print("MODO VOZ: Enter inicia fala até silêncio; digite sair para encerrar.")
        print(f"JARVIS ativa | Workspace: {c.workspace} | Modelo inicial: {auto.active_model}")
        print("Modelos: /modelos, /modelo ID, /modelo atual, /modelo auto, /modelo todos")
        print("Desempenho: /rapido, /normal, /acoes, /metricas")
        print("Autorizações: /permissoes auto | manual | revogar | status  (atual: " + approval.mode + ")")
        if approval.auto:
            print("⚡ AUTOAPROVAÇÃO ATIVA: ferramentas atuais executam sem pedir SIM. "
                  "Limites do workspace, comandos e permissões GNOME continuam valendo.")
        print("Tarefas: /planejar OBJETIVO, /plano, /historico-planos, /selecionar-plano ID, /resolver-etapa skip|retry, /retomar-plano, /executar-plano")
        if voice is not None and not args.push_to_talk:
            from .voice_session import MixedInput
            mixed = MixedInput(voice)
            mixed.start()
        try:
            while True:
                try:
                    if mixed is not None:
                        msg = mixed.read(sys.stdin)
                    elif voice is not None:
                        command = input("Você [Enter = falar / sair] > ").strip()
                        if command.lower() in {"sair", "/quit", "exit"}:
                            break
                        if command:
                            msg = command
                        else:
                            print("🎙️ Ouvindo até um segundo de silêncio...")
                            try:
                                recording = voice.record_turn()
                                try:
                                    msg = voice.transcribe(recording)
                                finally:
                                    recording.unlink(missing_ok=True)
                            except Exception as exc:
                                print(f"Falha de gravação/transcrição: {exc}", file=sys.stderr)
                                continue
                            print("Você (voz) >", msg or "[nenhuma fala reconhecida]")
                            if msg:
                                correction = input("Corrigir transcrição [Enter = enviar, /cancelar = descartar] > ").strip()
                                if correction.casefold() == "/cancelar":
                                    continue
                                if correction:
                                    msg = correction
                    else:
                        msg = input("Você > ").strip()
                except (KeyboardInterrupt, EOFError):
                    print("\nEncerrando.")
                    break
                if msg.lower() in {"sair", "/quit", "exit"}:
                    break
                if not msg:
                    continue
                if msg.lower().startswith("/selecionar-plano "):
                    try:
                        plan_id = int(msg.split(maxsplit=1)[1])
                        print(format_plan(planner.select(plan_id)))
                    except (ValueError, OverflowError) as exc:
                        print("Plano não selecionado:", exc, file=sys.stderr)
                    continue
                if msg.lower().startswith("/resolver-etapa "):
                    try:
                        choice = msg.split(maxsplit=1)[1].strip().lower()
                        if choice not in ("skip", "retry"):
                            raise ValueError("Use skip (ignorar) ou retry (reexecutar).")
                        pending = planner.snapshot()
                        affected = next((x for x in pending.get("steps", [])
                                         if x.get("status") in ("interrupted", "failed", "blocked", "running")), None)
                        if not affected:
                            raise ValueError("Nenhuma etapa incerta neste plano.")
                        if confirm("RESOLVER etapa #" + str(affected["id"]) + " (" + affected["description"] + ") como " + choice + "?"):
                            print(format_plan(planner.resolve_step(choice)))
                        else:
                            print("Operação cancelada.")
                    except ValueError as exc:
                        print("Etapa não alterada:", exc, file=sys.stderr)
                    continue
                if msg.lower() == "/retomar-plano":
                    try:
                        print(format_plan(planner.ready_to_resume()))
                        print("Use /executar-plano para confirmar e executar apenas as pendentes.")
                    except ValueError as exc:
                        print("Retomada indisponível:", exc, file=sys.stderr)
                    continue
                if msg.lower().startswith("/planejar "):
                    try:
                        prepared = planner.prepare(msg[len("/planejar "):].strip())
                        print(format_plan(prepared, show_results=False))
                    except (FCCError, ValueError) as exc:
                        print("Erro ao planejar:", exc, file=sys.stderr)
                    continue
                if msg.lower() == "/plano":
                    print(format_plan(planner.snapshot()))
                    continue
                if msg.lower() == "/cancelar-plano":
                    print(format_plan(planner.cancel()))
                    continue
                if msg.lower() == "/executar-plano":
                    try:
                        result = planner.execute(confirm)
                        print(format_plan(result))
                    except (FCCError, ValueError) as exc:
                        print("Erro na execução:", exc, file=sys.stderr)
                    continue
                if msg.lower() == "/historico-planos":
                    print(format_history(planner.history()))
                    continue
                if msg.lower() in ("/permissoes", "/permissões",
                                   "/permissoes status", "/permissões status"):
                    print("Autorizações:", approval.mode,
                          "| automaticamente autorizadas:", approval.auto_approved)
                    continue
                if msg.lower() in ("/permissoes auto", "/permissões auto"):
                    approval.set_mode("auto")
                    print("⚡ Autoaprovação ativada nesta sessão; "
                          "operações das ferramentas não pedirão SIM. "
                          "Isso inclui alterações de arquivos e navegação. "
                          "Restrições locais e permissões GNOME permanecem.")
                    continue
                if msg.lower() in ("/permissoes manual", "/permissões manual"):
                    approval.set_mode("manual")
                    print("Autorizações manuais restauradas. As próximas "
                          "operações voltarão a pedir SIM.")
                    continue
                if msg.lower() in ("/permissoes revogar", "/permissões revogar"):
                    approval.revoke()
                    print("Sessão revogada. Novas ações locais serão recusadas até "
                          "você escolher /permissoes manual ou /permissoes auto.")
                    continue
                if msg.lower() == "/rapido":
                    agent.mode = "fast"
                    print("Modo rápido: sem ferramentas e com geração curta.")
                    continue
                if msg.lower() == "/normal":
                    agent.mode = "auto"
                    print("Modo automático: ferramentas quando necessárias.")
                    continue
                if msg.lower() == "/acoes":
                    agent.mode = "tools"
                    print("Modo ações: sempre oferece ferramentas ao modelo.")
                    continue
                if msg.lower() in ("/metricas", "/metrics"):
                    print(json.dumps(agent.last_metrics or {"status":"sem execução ainda"}, ensure_ascii=False, indent=2))
                    continue
                # Comandos começando por / são controle local; nunca enviar
                # erros de digitação à IA (poderia iniciar inferência lenta).
                if msg.lower().startswith(("/modelos ", "/models ")):
                    print("Para selecionar um modelo use /modelo ID (sem s). "
                          "Para listar todos, digite /modelos.")
                    continue
                if msg.lower() in ("/modelo", "/modelos?", "/models?"):
                    print("Uso: /modelo ID | /modelo atual | /modelo auto | "
                          "/modelos (listar).")
                    continue
                if msg.lower() in ("/modelos", "/models"):
                    try:
                        for model_id in auto.available_models():
                            print(("* " if model_id == auto.active_model else "  ") + model_id)
                    except FCCError as exc:
                        print("Erro no catálogo FCC:", exc, file=sys.stderr)
                    continue
                if msg.lower() == "/modelo atual":
                    print("Modelo atual:", auto.active_model)
                    continue
                if msg.lower() == "/modelo todos":
                    try:
                        models = auto.use_all_models()
                        print("Modelos como alternativas (nem todos aceitam tools/visão):", len(models))
                    except FCCError as exc:
                        print("FCC:", exc, file=sys.stderr)
                    continue
                if msg.lower() == "/modelo auto":
                    auto.preferred = ""
                    auto.initialize()
                    agent.model = auto.active_model
                    print("Modo seleção automática:", auto.active_model)
                    continue
                if msg.lower().startswith("/modelo "):
                    selected = msg[8:].strip()
                    try:
                        auto.select_model(selected)
                        agent.model = selected
                        print("Modelo atual:", selected)
                    except FCCError as exc:
                        print("Modelo não selecionado:", exc, file=sys.stderr)
                    continue
                if msg.lower().startswith("/localizar "):
                    from .targeting import locate_target
                    from .wayland import WaylandError
                    try:
                        result = locate_target(client, auto.active_model, c.workspace, confirm, msg[len("/localizar "):])
                        print("JARVIS (localização) >", json.dumps(result, ensure_ascii=False), "\\n")
                    except (FCCError, WaylandError, OSError) as exc:
                        print("Erro ao localizar alvo:", exc, file=sys.stderr)
                    continue
                if msg.lower().startswith("/clicar-guiado "):
                    from .guided_desktop import guided_click
                    from .wayland import WaylandError
                    try:
                        result = guided_click(client, auto.active_model, c.workspace, confirm, msg[len("/clicar-guiado "):])
                        print("JARVIS (clique guiado) >", json.dumps(result, ensure_ascii=False), "\\n")
                    except (FCCError, WaylandError, OSError) as exc:
                        print("Erro no clique guiado:", exc, file=sys.stderr)
                    continue
                if msg.lower() == "/tela" or msg.lower().startswith("/tela "):
                    from .vision import analyze_screen
                    from .wayland import WaylandError
                    question = msg[6:].strip() or "Descreva o conteúdo visível nesta tela."
                    try:
                        observation = analyze_screen(client, auto.active_model, c.workspace, confirm, question)
                        print("JARVIS (visão) >", observation.get("answer", observation), "\\n")
                    except (FCCError, WaylandError) as exc:
                        print("Erro na análise da tela:", exc, file=sys.stderr)
                    continue
                if msg.startswith("/"):
                    print("Comando desconhecido. Digite /modelos para listar, "
                          "/modelo ID para selecionar, /metricas para métricas, "
                          "/plano para o plano atual.")
                    continue
                try:
                    answer = service.ask(msg)
                    print("JARVIS >", answer, "\n")
                    if os.getenv("JARVIS_SHOW_TIMING") == "1":
                        print("Tempo:", agent.last_metrics, "\n")
                    if voice:
                        try:
                            status = voice.speak(answer)
                            if status == "disabled":
                                print("Para ouvir respostas, configure JARVIS_PIPER_MODEL.")
                        except Exception as exc:
                            print(f"Falha ao falar resposta: {exc}", file=sys.stderr)
                except (FCCError, ValueError) as exc:
                    print("Erro de modelo/protocolo:", exc, file=sys.stderr)
                except KeyboardInterrupt:
                    print("\\nRequisição interrompida. Uma ação local já autorizada pode ter ocorrido; "
                          "confira o resultado antes de repetir. Use /metricas para ver o tempo parcial.")
        finally:
            if mixed is not None:
                mixed.close()
            service.close()
    except FCCError as exc:
        print("Erro:", exc, file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
