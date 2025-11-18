import json
import threading
import time
from typing import Any, Dict

import requests
import serial


SERIAL_PORT = "COM4"
BAUD_RATE = 115200
BACKEND_URL = "http://localhost:8000/api/telemetry"


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

  kb_thread = threading.Thread(target=keyboard_loop, daemon=True)
  kb_thread.start()

  print(f"Lendo de {SERIAL_PORT} e enviando para {BACKEND_URL}...")
  while True:
    try:
      line_bytes = ser.readline()
      if not line_bytes:
        continue

      line = line_bytes.decode("utf-8", errors="ignore").strip()

      # Só nos interessam as linhas JSON emitidas pelo firmware
      if not line.startswith("{"):
        continue

      try:
        payload = json.loads(line)
      except json.JSONDecodeError:
        print("JSON inválido, ignorando:", line)
        continue

      last_payload = payload
      _send_payload(payload)

    except KeyboardInterrupt:
      print("Interrompido pelo usuário.")
      break
    except Exception as e:  # noqa: BLE001
      print("Erro geral no loop:", e)


if __name__ == "__main__":
  main()

