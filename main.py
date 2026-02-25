import os
import json
import time
import hashlib
import sys
import tempfile

import win32print

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, WebDriverException, SessionNotCreatedException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from webdriver_manager.chrome import ChromeDriverManager


# ================= CONFIGURAÇÃO =================
WA_URL = "https://web.whatsapp.com"
CONFIG_FILE = "config.json"
STATE_FILE = "state.json"
PROFILE_DIR = "wa_profile"  # guarda sessão (não precisa logar todo dia)
POLL_SECONDS = 4
MAX_CHATS_SCAN = 12         # quantas conversas recentes varrer por ciclo
# ================================================


def get_base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def p(path: str) -> str:
    return os.path.join(get_base_dir(), path)


def load_json(path: str, default: dict) -> dict:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default


def save_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_printers() -> list[str]:
    flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
    printers = win32print.EnumPrinters(flags)
    names = []
    for pr in printers:
        try:
            names.append(pr[2])
        except Exception:
            pass
    return names


def has_interactive_stdin() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def pick_printer_for_non_interactive(printers: list[str]) -> str:
    env_printer = os.getenv("PRINTER_NAME", "").strip()
    if env_printer:
        return env_printer

    try:
        default_printer = (win32print.GetDefaultPrinter() or "").strip()
    except Exception:
        default_printer = ""

    if default_printer:
        return default_printer

    if len(printers) == 1:
        return printers[0]

    return ""


def ensure_config() -> dict:
    cfg_path = p(CONFIG_FILE)
    cfg = load_json(cfg_path, default={})

    # defaults
    cfg.setdefault("printer_name", "")
    cfg.setdefault("trigger", "#IMPRESSAO")  # gatilho pra imprimir
    cfg.setdefault("remove_trigger_from_print", True)
    cfg.setdefault("scan_chats", MAX_CHATS_SCAN)

    if not cfg["printer_name"]:
        print("\n=== CONFIG INICIAL ===")
        print("Impressoras detectadas no Windows:")
        printers = list_printers()
        if printers:
            for i, name in enumerate(printers, start=1):
                print(f"  {i}) {name}")
        else:
            print("  (não consegui listar; configure manualmente no config.json)")

        if has_interactive_stdin():
            try:
                cfg["printer_name"] = input("\nDigite o NOME EXATO da impressora: ").strip()
                trig = input(f"Trigger para imprimir (padrão {cfg['trigger']}): ").strip()
                if trig:
                    cfg["trigger"] = trig
            except EOFError:
                print("[WARN] Entrada interativa indisponível. Tentando modo automático.")
                cfg["printer_name"] = ""

        if not cfg["printer_name"]:
            auto_printer = pick_printer_for_non_interactive(printers)
            if not auto_printer:
                raise RuntimeError(
                    "Sem stdin interativo e sem impressora configurada. "
                    "Defina 'printer_name' no config.json ou a variável PRINTER_NAME."
                )
            cfg["printer_name"] = auto_printer
            print(f"[OK] Modo não interativo: usando impressora '{auto_printer}'.")

        save_json(cfg_path, cfg)
        print(f"[OK] Config salva em: {cfg_path}")

    return cfg


def ensure_state() -> dict:
    st_path = p(STATE_FILE)
    st = load_json(st_path, default={})
    st.setdefault("printed_ids", [])  # lista de hashes
    st.setdefault("received_ids", [])  # mensagens recebidas confirmadas
    st.setdefault("received_bootstrap_done", False)
    # limita tamanho pra não crescer infinito
    st["printed_ids"] = st["printed_ids"][-5000:]
    st["received_ids"] = st["received_ids"][-5000:]
    return st


def remember_printed(state: dict, msg_id: str) -> None:
    state["printed_ids"].append(msg_id)
    state["printed_ids"] = state["printed_ids"][-5000:]
    save_json(p(STATE_FILE), state)


def is_printed(state: dict, msg_id: str) -> bool:
    return msg_id in set(state.get("printed_ids", []))


def remember_received(state: dict, msg_id: str) -> None:
    state["received_ids"].append(msg_id)
    state["received_ids"] = state["received_ids"][-5000:]
    save_json(p(STATE_FILE), state)


def is_received(state: dict, msg_id: str) -> bool:
    return msg_id in set(state.get("received_ids", []))


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", errors="ignore")).hexdigest()


def imprimir_cupom(conteudo: str, nome_impressora: str) -> None:
    try:
        hPrinter = win32print.OpenPrinter(nome_impressora)
        try:
            win32print.StartDocPrinter(hPrinter, 1, ("Cupom WhatsApp", None, "RAW"))
            win32print.StartPagePrinter(hPrinter)

            # ESC/POS básicos
            CMD_INIT        = b"\x1b\x40"
            CMD_CENTRO      = b"\x1b\x61\x01"
            CMD_ESQ         = b"\x1b\x61\x00"
            CMD_BOLD_ON     = b"\x1b\x45\x01"
            CMD_BOLD_OFF    = b"\x1b\x45\x00"
            CMD_CORTE       = b"\x1d\x56\x00"

            win32print.WritePrinter(hPrinter, CMD_INIT)
            win32print.WritePrinter(hPrinter, CMD_CENTRO + CMD_BOLD_ON)
            win32print.WritePrinter(hPrinter, "=== NOVO PEDIDO ===\n\n".encode("cp850", errors="ignore"))
            win32print.WritePrinter(hPrinter, CMD_BOLD_OFF + CMD_ESQ)

            win32print.WritePrinter(hPrinter, conteudo.encode("cp850", errors="ignore"))
            win32print.WritePrinter(hPrinter, b"\n\n-------------------\n\n\n\n\n")
            win32print.WritePrinter(hPrinter, CMD_CORTE)

            win32print.EndPagePrinter(hPrinter)
            win32print.EndDocPrinter(hPrinter)

            print("[OK] Impresso!")
        finally:
            win32print.ClosePrinter(hPrinter)

    except Exception as e:
        print(f"[ERRO IMPRESSORA] {e}")
        print("Confirme o nome EXATO da impressora no config.json.")


def make_driver() -> webdriver.Chrome:
    def build_options(profile_path: str) -> webdriver.ChromeOptions:
        options = webdriver.ChromeOptions()
        options.add_argument(f"--user-data-dir={profile_path}")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--remote-debugging-port=0")
        return options

    def start_with_profile(profile_path: str) -> webdriver.Chrome:
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=build_options(profile_path))

    profile_path = p(PROFILE_DIR)
    os.makedirs(profile_path, exist_ok=True)

    try:
        return start_with_profile(profile_path)
    except (SessionNotCreatedException, WebDriverException) as e:
        msg = str(e)
        recoverable = (
            "DevToolsActivePort file doesn't exist" in msg
            or "user data directory is already in use" in msg
            or "chrome failed to start" in msg.lower()
        )
        if not recoverable:
            raise

        temp_profile = os.path.join(
            tempfile.gettempdir(),
            f"wbot_wa_profile_{int(time.time())}",
        )
        os.makedirs(temp_profile, exist_ok=True)
        print("[WARN] Falha ao abrir o Chrome com perfil persistente.")
        print(f"[WARN] Tentando perfil temporário: {temp_profile}")
        return start_with_profile(temp_profile)


def wait_for_whatsapp_ready(driver: webdriver.Chrome, timeout=120) -> None:
    driver.get(WA_URL)

    # Confirma UI pronta e sessão logada.
    wait = WebDriverWait(driver, timeout)

    try:
        wait.until(
            lambda d: (
                d.find_elements(By.CSS_SELECTOR, "div#pane-side")
                or d.find_elements(By.CSS_SELECTOR, "div[data-testid='chat-list']")
            )
        )
        print("[CONFIRMACAO] WhatsApp Web aberto e logado com sucesso.")
        return
    except TimeoutException:
        print("[ERRO] Não consegui detectar o WhatsApp Web pronto.")
        print("Se for a primeira vez, faça login pelo QR Code e aguarde.")
        raise


def get_recent_chat_items(driver: webdriver.Chrome) -> list:
    # A lista de conversas costuma ter itens com role="listitem"
    items = driver.find_elements(By.CSS_SELECTOR, "div[role='listitem']")
    return items


def open_chat(driver: webdriver.Chrome, chat_el) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView(true);", chat_el)
        chat_el.click()
        return True
    except Exception:
        return False


def extract_last_outgoing_messages(driver: webdriver.Chrome, limit=8) -> list[dict]:
    """
    Retorna as últimas mensagens ENVIADAS (message-out).
    Usa data-pre-plain-text quando existir pra gerar um id estável.
    """
    results = []

    # Mensagens enviadas geralmente têm classe 'message-out'
    out_msgs = driver.find_elements(By.CSS_SELECTOR, "div.message-out")
    if not out_msgs:
        return results

    for el in out_msgs[-limit:]:
        try:
            # Texto
            # Nem tudo é texto (pode ser imagem). Tentamos pegar innerText.
            text = el.text.strip()
            if not text:
                continue

            # Um atributo bem útil quando existe:
            # dentro existe div.copyable-text com data-pre-plain-text
            pre = ""
            try:
                copyable = el.find_element(By.CSS_SELECTOR, "div.copyable-text")
                pre = copyable.get_attribute("data-pre-plain-text") or ""
            except Exception:
                pre = ""

            msg_key = (pre + "\n" + text).strip()
            msg_id = sha(msg_key)

            results.append({
                "id": msg_id,
                "pre": pre,
                "text": text
            })
        except Exception:
            continue

    return results


def extract_last_incoming_messages(driver: webdriver.Chrome, limit=8) -> list[dict]:
    """
    Retorna as últimas mensagens RECEBIDAS (message-in).
    Usa data-pre-plain-text quando existir pra gerar um id estável.
    """
    results = []

    in_msgs = driver.find_elements(By.CSS_SELECTOR, "div.message-in")
    if not in_msgs:
        return results

    for el in in_msgs[-limit:]:
        try:
            text = el.text.strip()
            if not text:
                continue

            pre = ""
            try:
                copyable = el.find_element(By.CSS_SELECTOR, "div.copyable-text")
                pre = copyable.get_attribute("data-pre-plain-text") or ""
            except Exception:
                pre = ""

            msg_key = (pre + "\n" + text).strip()
            msg_id = sha(msg_key)

            results.append({
                "id": msg_id,
                "pre": pre,
                "text": text,
            })
        except Exception:
            continue

    return results


def should_print(text: str, trigger: str) -> bool:
    return trigger in text


def sanitize_for_print(text: str, trigger: str, remove_trigger: bool) -> str:
    if remove_trigger:
        return text.replace(trigger, "").strip()
    return text


def loop(driver: webdriver.Chrome, cfg: dict, state: dict) -> None:
    trigger = cfg.get("trigger", "#IMPRESSAO")
    printer = cfg["printer_name"]
    remove_trigger = bool(cfg.get("remove_trigger_from_print", True))
    scan_chats = int(cfg.get("scan_chats", MAX_CHATS_SCAN))
    received_bootstrap_done = bool(state.get("received_bootstrap_done", False))

    print("\n=== BOT ATIVO ===")
    print(f"Trigger: {trigger}")
    print(f"Impressora: {printer}")
    print("Dica: coloque o trigger no final da mensagem que você envia ao cliente.\n")

    while True:
        try:
            chat_items = get_recent_chat_items(driver)
            if not chat_items:
                time.sleep(POLL_SECONDS)
                continue

            # Varre as conversas mais recentes
            for chat_el in chat_items[:scan_chats]:
                if not open_chat(driver, chat_el):
                    continue

                time.sleep(0.8)  # pequeno tempo pra renderizar a conversa

                outgoing = extract_last_outgoing_messages(driver, limit=10)
                for msg in outgoing:
                    msg_id = msg["id"]
                    text = msg["text"]

                    if is_printed(state, msg_id):
                        continue

                    if should_print(text, trigger):
                        to_print = sanitize_for_print(text, trigger, remove_trigger)
                        print("\n[PEDIDO] Detectado para impressão!")
                        print("---------------------------------")
                        print(to_print)
                        print("---------------------------------")
                        imprimir_cupom(to_print, printer)
                        remember_printed(state, msg_id)

                incoming = extract_last_incoming_messages(driver, limit=10)
                for msg in incoming:
                    msg_id = msg["id"]
                    if is_received(state, msg_id):
                        continue

                    remember_received(state, msg_id)
                    if received_bootstrap_done:
                        print("[CONFIRMACAO] Nova mensagem recebida no WhatsApp.")

            if not received_bootstrap_done:
                state["received_bootstrap_done"] = True
                save_json(p(STATE_FILE), state)
                received_bootstrap_done = True
                print("[OK] Monitor de mensagens recebidas inicializado.")

            time.sleep(POLL_SECONDS)

        except WebDriverException as e:
            print(f"[ERRO] Selenium/Chrome: {e}")
            print("Reabra o Chrome/WhatsApp Web ou reinicie o bot.")
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n[ENCERRADO] Pelo usuário.")
            break
        except Exception as e:
            print(f"[ERRO] {e}")
            time.sleep(2)


def main():
    cfg = ensure_config()
    state = ensure_state()
    save_json(p(STATE_FILE), state)

    driver = make_driver()
    try:
        wait_for_whatsapp_ready(driver, timeout=180)
        loop(driver, cfg, state)
    except TimeoutException:
        print("[ERRO] WhatsApp Web não ficou pronto no tempo esperado.")
        print("Faça login no QR Code e execute o bot novamente.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    main()
