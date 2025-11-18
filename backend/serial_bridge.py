import json
import time

import requests
import serial


SERIAL_PORT = "COM4"
BAUD_RATE = 115200
BACKEND_URL = "http://localhost:8000/api/telemetry"


def main() -> None:
    print(f"Abrindo porta serial {SERIAL_PORT} em {BAUD_RATE} baud...")
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    time.sleep(2)

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

            try:
                resp = requests.post(BACKEND_URL, json=payload, timeout=2)
                print("Enviado:", payload, "HTTP:", resp.status_code)
            except Exception as e:  # noqa: BLE001
                print("Erro ao enviar para backend:", e)

        except KeyboardInterrupt:
            print("Interrompido pelo usuário.")
            break
        except Exception as e:  # noqa: BLE001
            print("Erro geral no loop:", e)


if __name__ == "__main__":
    main()

