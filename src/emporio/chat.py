"""Minimal terminal chat. Run with: python -m emporio.chat  (use --trace to see tool calls)."""
import logging
import sys

from emporio.agent.factory import build_agent
from emporio.agent.providers import ProviderError
from emporio.settings import SettingsError, load_settings

EXIT_COMMANDS = {"sair", "exit", "quit"}


def main() -> int:
    show_trace = "--trace" in sys.argv
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    try:
        settings = load_settings()
        agent = build_agent(settings)
    except (SettingsError, FileNotFoundError) as exc:
        print(f"Erro de configuração: {exc}")
        return 1

    print(f"Empório da Música — assistente virtual ({settings.provider}/{settings.model}). Digite 'sair' para encerrar.\n")
    history: list = []
    while True:
        try:
            user_text = input("Você: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not user_text:
            continue
        if user_text.lower() in EXIT_COMMANDS:
            return 0
        try:
            reply = agent.run(history, user_text)
        except ProviderError as exc:
            print(f"[erro do provedor] {exc}\n")
            continue
        if show_trace:
            for step in reply.tool_trace:
                print(f"  ↳ {step['tool']}({step['arguments']}) {'ok' if step['ok'] else 'ERRO'}")
        print(f"Mel: {reply.text}\n")


if __name__ == "__main__":
    sys.exit(main())
