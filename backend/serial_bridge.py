import json
import threading
import time
from typing import Any, Dict

import requests
import serial


SERIAL_PORT = "COM4"
BAUD_RATE = 115200
BACKEND_URL = "http://localhost:8000/api/telemetry"
CONFIG_URL = "http://localhost:8000/api/device-config"


def _send_payload(payload: Dict[str, Any], prefix: str = "") -> None:
  try:
    resp = requests.post(BACKEND_URL, json=payload, timeout=2)
    print(f"{prefix}Enviado:", payload, "HTTP:", resp.status_code)
  except Exception as e:  # noqa: BLE001
    print(f"{prefix}Erro ao enviar para backend:", e)


def main() -> None:
  print(f"Abrindo porta serial {SERIAL_PORT} em {BAUD_RATE} baud...")
  ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
  time.sleep(2)

  last_payload: Dict[str, Any] = {}
  last_config_value: Dict[str, Any] = {"device_id": "bracelet-01", "use_hr_check": True}
  last_config_check = 0.0

  def keyboard_loop() -> None:
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
    nonlocal last_config_check, last_config_value, last_payload

    now = time.time()
    # Evita chamar o backend muitas vezes; verifica a cada ~2 segundos
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

    use_hr = bool(data.get("use_hr_check", True))
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

  kb_thread = threading.Thread(target=keyboard_loop, daemon=True)
  kb_thread.start()

  print(f"Lendo de {SERIAL_PORT} e enviando para {BACKEND_URL}...")
  while True:
    try:
      line_bytes = ser.readline()
      if line_bytes:
        line = line_bytes.decode("utf-8", errors="ignore").strip()

        # O firmware imprime várias linhas de debug (ex.: [WIN], [CRISE])
        # misturadas com linhas JSON. Para garantir que não perdemos
        # telemetria, extraímos o trecho que parece JSON mesmo que venha
        # junto com texto de debug.
        if "{" in line and "}" in line:
          json_part = line[line.find("{") : line.rfind("}") + 1]
          try:
            payload = json.loads(json_part)
          except json.JSONDecodeError:
            print("JSON inválido, ignorando:", line)
          else:
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

