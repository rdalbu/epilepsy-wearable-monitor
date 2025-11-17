# Epilepsy Bracelet Project

End‑to‑end epilepsy seizure monitoring system based on **IoT** and **web technologies**, using:

- **Hardware**: ESP32 + heart rate sensor (HW‑827) + MPU6050 + LEDs.
- **Backend**: Python / **FastAPI** + **PostgreSQL**.
- **Frontend**: **React** + **Vite**.

The goal is to continuously monitor the patient, detect seizure‑like patterns from motion and heart rate, trigger real‑time alerts, and store detailed history for later clinical analysis.

---

## Table of Contents

- [High‑Level Architecture](#high-level-architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Backend (FastAPI + PostgreSQL)](#backend-fastapi--postgresql)
  - [Data Model](#data-model)
  - [API Endpoints](#api-endpoints)
- [Frontend (React + Vite)](#frontend-react--vite)
- [Firmware (ESP32)](#firmware-esp32)
  - [Wi‑Fi and Backend Configuration](#wi-fi-and-backend-configuration)
  - [Seizure Detection Logic on the Bracelet](#seizure-detection-logic-on-the-bracelet)
- [Installation Guide](#installation-guide)
- [Next Steps and Improvements](#next-steps-and-improvements)

---

## High‑Level Architecture

End‑to‑end data flow:

1. **Bracelet (ESP32)** continuously reads:
   - Heartbeat signal from the HW‑827 sensor (analog input).
   - Motion from MPU6050 (accelerometer + gyroscope).
2. Based on these signals, the firmware computes:
   - `currentBPM` (filtered current heart rate).
   - `baselineBPM` (resting heart rate).
   - States:
     - `crise_ativa` – seizure‑like movement detected.
     - `crise_confirmada` – seizure‑like movement + heart rate compatible with seizure.
3. The ESP32 periodically (about once per second) sends an **HTTP POST with JSON** to the backend:
   - `device_id`
   - `bpm`
   - `baseline_bpm`
   - `status` (`NORMAL`, `MOVIMENTO_SUSPEITO`, `CRISE_CONFIRMADA`).
4. The **FastAPI backend**:
   - Persists the readings in **PostgreSQL** (`telemetry` table).
   - Manages `crises` records (start, end, heart rate metrics).
   - Broadcasts data in real time to dashboards through **WebSocket**.
5. The **React frontend**:
   - **Real‑time view**: shows live heart rate and crisis status with visual/audio alerts.
   - **History view**: lists past seizures with timestamps, duration, and basic stats.

---

## Tech Stack

**Hardware**
- ESP32
- HW‑827 heart rate sensor
- MPU6050 (accelerometer + gyroscope)
- Status LEDs (GPIOs 4, 5, 18)

**Backend**
- Python 3.10+
- FastAPI
- SQLAlchemy
- PostgreSQL

**Frontend**
- React 18
- Vite

---

## Project Structure

```text
projeto-pulseira-epilepsia/
  backend/
    app/
      main.py               # FastAPI app + WebSocket
      db/
        session.py          # PostgreSQL connection
        models.py           # SQLAlchemy models (Device, Telemetry, Crisis)
        schemas.py          # Pydantic schemas (input/output)
      services/
        crisis_service.py   # crisis state machine / logic
    requirements.txt        # backend dependencies

  frontend/
    index.html
    vite.config.mts
    package.json
    src/
      main.jsx
      App.jsx               # main layout and tab switching
      components/
        RealtimeDashboard.jsx  # real‑time monitoring panel
      pages/
        HistoryPage.jsx        # seizure history page

  firmware/
    esp32_pulseira_backend_example.ino  # reference firmware for the ESP32
```

---

## Backend (FastAPI + PostgreSQL)

The backend exposes a REST API plus a WebSocket endpoint, consumed by the ESP32 and the React dashboard.

### Database Configuration

Default connection (local PostgreSQL on Windows) in `backend/app/db/session.py`:

```python
DATABASE_URL = "postgresql://postgres:123456@localhost:5432/pulseira"
```

Requirements:

- PostgreSQL running at `localhost:5432`.
- User: `postgres`
- Password: `123456` (change if needed).
- Database: `pulseira`

Create the database once (via `psql` or pgAdmin):

```sql
CREATE DATABASE pulseira OWNER postgres;
```

If you change user/password, update `DATABASE_URL` accordingly.

### Data Model

Location: `backend/app/db/models.py`

- **Device**
  - `id` – string (e.g. `"bracelet-01"`)
  - `name` – human‑friendly device name

- **Telemetry**
  - `id` – UUID
  - `device_id` – FK → `Device.id`
  - `timestamp` – reading timestamp
  - `bpm` – heart rate
  - `baseline_bpm` – resting heart rate
  - `status` – enum: `NORMAL`, `MOVIMENTO_SUSPEITO`, `CRISE_CONFIRMADA`

- **Crisis**
  - `id` – UUID
  - `device_id` – FK → `Device.id`
  - `start_time` – crisis start
  - `end_time` – crisis end (null while active)
  - `avg_bpm` – average BPM over the crisis (simplified model)
  - `max_bpm` – maximum BPM observed during the crisis

### API Endpoints

Main routes in `backend/app/main.py`:

- `GET /health`  
  Basic health check to verify the API is running.

- `POST /api/telemetry`  
  Accepts telemetry from the ESP32.

  Example request body:

  ```json
  {
    "device_id": "bracelet-01",
    "bpm": 110,
    "baseline_bpm": 80,
    "status": "CRISE_CONFIRMADA"
  }
  ```

  Behavior:
  - Stores a row in `telemetry`.
  - Opens/updates/closes a crisis in `crises` based on status.
  - Broadcasts the event to all connected WebSocket clients.

- `GET /api/crises?device_id=bracelet-01`  
  Returns the list of crises for a given device.

- `WS /ws/dashboard`  
  WebSocket used by the frontend to receive live telemetry and crisis events.

### Crisis Logic in the Backend

Location: `backend/app/services/crisis_service.py`

Simplified rules:

- On a telemetry event with `status = CRISE_CONFIRMADA` and **no open crisis** for that device:
  - Create a new `Crisis` row with `start_time` and `max_bpm` initialized.

- While a crisis is open:
  - Update `max_bpm` if a higher BPM arrives.

- On a telemetry event with `status = NORMAL` and an open crisis:
  - Set `end_time`.
  - Fill `avg_bpm` (simplified as `max_bpm` for now).

Each step produces a simple event (`CRISIS_STARTED` / `CRISIS_ENDED`) that is forwarded to the WebSocket clients.

---

## Frontend (React + Vite)

The frontend provides a web dashboard to visualize both real‑time and historical data.

### Screen Layout

Location: `frontend/src/App.jsx`

- Device selector:
  - Text input with default `deviceId = "bracelet-01"`.
- Tabs:
  - **Real Time** – live monitoring panel.
  - **History** – table of past crises.

### Real‑Time Panel – `RealtimeDashboard.jsx`

Location: `frontend/src/components/RealtimeDashboard.jsx`

Features:

- Connects to WebSocket at `ws://localhost:8000/ws/dashboard`.
- Displays:
  - Current date/time (local).
  - Crisis status (background color based on status):
    - Green → `NORMAL`
    - Yellow → `MOVIMENTO_SUSPEITO`
    - Red → `CRISE_CONFIRMADA`
  - Current BPM and baseline BPM.
  - Last update time (from the latest telemetry timestamp).
- When `status = "CRISE_CONFIRMADA"`:
  - Optionally plays an alert sound (`public/sounds/alert.mp3`).
  - Shows a visual alert dialog to the user.

### History Page – `HistoryPage.jsx`

Location: `frontend/src/pages/HistoryPage.jsx`

Features:

- Calls `GET /api/crises?device_id=<id>`.
- Displays a table with:
  - Crisis start time.
  - Crisis end time.
  - Duration (minutes and seconds).
  - Average BPM.
  - Maximum BPM.
- **Reload** button to manually refresh data.

---

## Firmware (ESP32)

Reference firmware is located at:  
`firmware/esp32_pulseira_backend_example.ino`

Main responsibilities:

- Read the HW‑827 heart rate sensor on analog GPIO 34.
- Apply filtering (EMA, noise rejection, IBI validation) to derive `currentBPM`.
- Estimate `baselineBPM` from recent IBIs when the patient is not in a crisis.
- Read MPU6050 data via I2C:
  - Acceleration (x, y, z)
  - Angular velocity (x, y, z)
- Analyze 1‑second windows of motion:
  - Acceleration RMS (`acc_rms_g`).
  - Gyroscope RMS (`gyr_rms_dps`).
  - Oscillation frequency (2–8 Hz typical of tonic‑clonic seizures).
- Maintain global states:
  - `crise_ativa` – seizure‑like movement.
  - `crise_confirmada` – movement + heart rate compatible with seizure.
- Drive LEDs to represent state:
  - Red: confirmed crisis.
  - Yellow (red+green): suspicious movement only.
  - Green/Blue: dominant movement direction when no crisis.
- Send telemetry to the backend every 1 second.

### Wi‑Fi and Backend Configuration

At the top of the `.ino` file:

```cpp
const char *WIFI_SSID     = "YOUR_WIFI_SSID";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

const char *BACKEND_HOST = "192.168.0.10"; // PC IP running the backend
const int   BACKEND_PORT = 8000;

const char *DEVICE_ID = "bracelet-01";
```

Set these values to match your environment:

- `WIFI_SSID` / `WIFI_PASSWORD`: Wi‑Fi network reachable by the ESP32.
- `BACKEND_HOST`: IP of the machine running FastAPI (`ipconfig` on Windows).
- `DEVICE_ID`: logical identifier for the bracelet (used across DB and UI).

The `enviaTelemetria(...)` function constructs the JSON payload and sends a POST to:

```text
http://BACKEND_HOST:BACKEND_PORT/api/telemetry
```

### Seizure Detection Logic on the Bracelet

Highlights from the firmware logic:

- **Movement‑based crisis (`crise_ativa`)**:
  - Evaluates motion windows for sufficient acceleration/gyro RMS and frequency range.
  - Maintains counters of “likely seizure” vs “clear” windows to avoid false positives.
  - Emits logs via `Serial`:
    - `CRISE_MOVIMENTO_DETECTADA`
    - `FIM_DA_CRISE_MOVIMENTO`

- **Confirmed crisis (`crise_confirmada`)**:
  - When `crise_ativa` is true, checks if heart rate is compatible with seizure.
  - Basic (tunable) rule:
    - `currentBPM >= ~110`
    - `currentBPM` at least ~30% higher than `baselineBPM`.
  - If criteria are met:
    - Sets `crise_confirmada = true`.
    - Logs `[ALERTA] CRISE CONFIRMADA! BPM=... baseline=...`.

Both states are sent to the backend and directly drive what the dashboard shows in real time and in the crisis history.

---

## Installation Guide

### 1. Database (PostgreSQL)

1. Install PostgreSQL on Windows if you do not have it already.
2. Create the database:

   ```sql
   CREATE DATABASE pulseira OWNER postgres;
   ```

3. Ensure the password for user `postgres` matches what you set in `DATABASE_URL` (default `123456`).

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Check:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open `http://localhost:5173` in a browser.

### 4. ESP32 Firmware

1. Open **Arduino IDE**.
2. Install the ESP32 board package via Boards Manager (if needed).
3. Open `firmware/esp32_pulseira_backend_example.ino`.
4. Configure:
   - `WIFI_SSID`, `WIFI_PASSWORD`.
   - `BACKEND_HOST` (backend IP).
   - `DEVICE_ID` (e.g. `bracelet-01`).
5. Select the correct ESP32 board and serial port.
6. Compile and upload.
7. Use Serial Monitor (115200 baud) to observe logs and telemetry sending.

### 5. Visualizing Data

With backend, frontend and firmware running:

- **Real Time** tab:
  - Shows live BPM, baseline BPM, and crisis state.
  - Background color changes according to status.
  - Alerts on confirmed crises.

- **History** tab:
  - Enter the `device_id` (e.g. `bracelet-01`).
  - Click **Recarregar / Reload** to fetch the list of recorded crises.

---

## Next Steps and Improvements

This project is designed as a solid foundation that can be extended in several directions:

- User authentication and role‑based access control for dashboards.
- Email/SMS/WhatsApp notifications on confirmed crises.
- More advanced analytics and visualizations (trends, time‑of‑day correlation, etc.).
- Dockerization (containers for backend, frontend, and database).
- Clinical calibration of thresholds and potentially ML‑based detection models.

It can also be integrated with EHR systems, mobile apps, or hospital platforms to form part of a broader digital health ecosystem.

