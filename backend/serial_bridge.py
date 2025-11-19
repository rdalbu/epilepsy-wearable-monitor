import json
import threading
import time
from typing import Any, Dict

import requests
import serial

# Porta e baudrate do ESP32
SERIAL_PORT = "COM4"
BAUD_RATE = 115200

# Endpoints do backend FastAPI
BACKEND_URL = "http://localhost:8000/api/telemetry"
CONFIG_URL = "http://localhost:8000/api/device-config"


def _send_payload(payload: Dict[str, Any], prefix: str = "") -> None:
    """
    Envia o payload de telemetria para o backend.
    """
    try:
        resp = requests.post(BACKEND_URL, json=payload, timeout=2)
        print(f"{prefix}Enviado:", payload, "HTTP:", resp.status_code)
    except Exception as e:  # noqa: BLE001
        print(f"{prefix}Erro ao enviar para backend:", e)


def main() -> None:
    print(f"Abrindo porta serial {SERIAL_PORT} em {BAUD_RATE} baud...")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

    # Dá tempo pro ESP32 resetar e começar a mandar dados
    time.sleep(2)

    # Limpa qualquer lixo de boot que ainda esteja no buffer
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    last_payload: Dict[str, Any] = {}
    last_config_value: Dict[str, Any] = {"device_id": "bracelet-01", "use_hr_check": False}
    last_config_check = 0.0

    def keyboard_loop() -> None:
        """
        Modo de teste manual:
        - m: MOVIMENTO_SUSPEITO
        - c: CRISE_CONFIRMADA
        - n: NORMAL
        - q: sair
        """
        nonlocal last_payload
        print(
            "Modo teste (teclado) ativado:\n"
            "  m = enviar MOVIMENTO_SUSPEITO\n"
            "  c = enviar CRISE_CONFIRMADA\n"
            "  n = enviar NORMAL\n"
            "  q = sair do modo teste\n"
        )
        while True:
            try:
                cmd = input().strip().lower()
            except EOFError:
                break

            if cmd == "q":
                print("Saindo do modo teste de teclado.")
                break

            if cmd not in {"m", "c", "n"}:
                print("Comando inválido. Use m / c / n / q.")
                continue

            status = {
                "m": "MOVIMENTO_SUSPEITO",
                "c": "CRISE_CONFIRMADA",
                "n": "NORMAL",
            }[cmd]

            base = last_payload or {
                "device_id": "bracelet-01",
                "bpm": 100,
                "baseline_bpm": 80,
            }

            test_payload = {
                "device_id": base.get("device_id", "bracelet-01"),
                "bpm": base.get("bpm", 100),
                "baseline_bpm": base.get("baseline_bpm", 80),
                "status": status,
            }
            _send_payload(test_payload, prefix="[TESTE] ")

    def poll_and_send_config() -> None:
        """
        Pergunta periodicamente ao backend se o device deve usar
        checagem de batimento (use_hr_check) e envia comando para o ESP32.
        """
        nonlocal last_config_check, last_config_value, last_payload

        now = time.time()
        # Verifica a cada ~2 segundos
        if now - last_config_check < 2.0:
            return
        last_config_check = now

        device_id = last_payload.get("device_id", last_config_value["device_id"])
        try:
            resp = requests.get(CONFIG_URL, params={"device_id": device_id}, timeout=2)
            if resp.status_code != 200:
                return
            data = resp.json()
        except Exception as e:  # noqa: BLE001
            print("Erro ao buscar config do backend:", e)
            return

        use_hr = bool(data.get("use_hr_check", False))
        # Se nada mudou, não precisa reenviar
        if (
            data.get("device_id") == last_config_value.get("device_id")
            and use_hr == last_config_value.get("use_hr_check")
        ):
            return

        last_config_value = {"device_id": device_id, "use_hr_check": use_hr}
        cmd = {"cmd": "SET_USE_HR", "value": use_hr}
        try:
            ser.write((json.dumps(cmd) + "\n").encode("utf-8"))
            print("Comando enviado para ESP:", cmd)
        except Exception as e:  # noqa: BLE001
            print("Erro ao enviar comando para ESP:", e)

    # Thread separada para o modo de teste via teclado
    kb_thread = threading.Thread(target=keyboard_loop, daemon=True)
    kb_thread.start()

    print(f"Lendo de {SERIAL_PORT} e enviando para {BACKEND_URL}...")
    while True:
        try:
            line_bytes = ser.readline()

            # Nada lido nessa iteração
            if not line_bytes:
                poll_and_send_config()
                continue

            # 1) Ignora linhas só com zeros (lixo binário)
            if all(b == 0x00 for b in line_bytes):
                # opcional: descomentar se quiser ver quando isso ocorre
                # print("Linha ignorada (apenas 0x00).")
                poll_and_send_config()
                continue

            # 2) Decodifica em texto, ignorando caracteres estranhos
            try:
                line = line_bytes.decode("utf-8", errors="ignore").strip()
            except Exception:
                line = line_bytes.decode("latin-1", errors="ignore").strip()

            if not line:
                poll_and_send_config()
                continue

            # 3) Ignora mensagens de boot do ESP32 (bootloader)
            if line.startswith("ets ") or line.startswith("rst:") or "ets Jul 29 2019" in line:
                print("Boot/Reset ESP32 (ignorado):", repr(line))
                poll_and_send_config()
                continue

            # A partir daqui é dado como você veria no Serial Monitor do Arduino
            print("RAW:", repr(line))

            # 4) Extrai JSON mesmo se vier misturado com logs ([WIN], [CRISE], etc.)
            if "{" in line and "}" in line:
                json_part = line[line.find("{") : line.rfind("}") + 1]
                try:
                    payload = json.loads(json_part)
                except json.JSONDecodeError:
                    print("JSON inválido, ignorando:", line)
                else:
                    # Normaliza status para evitar problemas com Enum no backend
                    if "status" in payload and isinstance(payload["status"], str):
                        payload["status"] = payload["status"].strip().upper()

                    last_payload = payload
                    _send_payload(payload)

            # Sempre tenta sincronizar configuração periodicamente
            poll_and_send_config()

        except KeyboardInterrupt:
            print("Interrompido pelo usuário.")
            break
        except Exception as e:  # noqa: BLE001
            print("Erro geral no loop:", e)


if __name__ == "__main__":
    main()
