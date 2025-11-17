# Projeto Pulseira Epilepsia

Sistema de monitoramento de crises epilépticas baseado em **IoT** e **web**, utilizando:

- **Hardware**: ESP32 + sensor de batimentos (HW‑827) + MPU6050 + LEDs.
- **Backend**: Python / **FastAPI** + **PostgreSQL**.
- **Frontend**: **React** + **Vite**.

O objetivo é monitorar o paciente em tempo real, detectar crises a partir de movimento e batimentos cardíacos, emitir alertas imediatos e registrar um histórico detalhado para análise clínica.

---

## Sumário

- [Arquitetura Geral](#arquitetura-geral)
- [Tecnologias Utilizadas](#tecnologias-utilizadas)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Backend (FastAPI + PostgreSQL)](#backend-fastapi--postgresql)
  - [Modelagem de Dados](#modelagem-de-dados)
  - [Endpoints](#endpoints)
- [Frontend (React + Vite)](#frontend-react--vite)
- [Firmware (ESP32)](#firmware-esp32)
  - [Configuração do Wi‑Fi e Backend](#configuração-do-wi-fi-e-backend)
  - [Lógica de Detecção de Crise na Pulseira](#lógica-de-detecção-de-crise-na-pulseira)
- [Passo a Passo de Instalação](#passo-a-passo-de-instalação)
- [Próximos Passos e Melhorias](#próximos-passos-e-melhorias)

---

## Arquitetura Geral

Fluxo simplificado da solução:

1. **Pulseira (ESP32)** coleta continuamente:
   - Sinal de batimentos cardíacos pelo sensor HW‑827.
   - Dados de aceleração/giroscópio com o MPU6050.
2. A partir desses sinais, o firmware calcula:
   - `currentBPM` (BPM atual filtrado).
   - `baselineBPM` (BPM em repouso).
   - Estados:
     - `crise_ativa` (movimento compatível com crise).
     - `crise_confirmada` (movimento + BPM compatível com crise).
3. O ESP32 envia, a cada ~1 segundo, um **POST HTTP com JSON** para o backend:
   - `device_id`
   - `bpm`
   - `baseline_bpm`
   - `status` (`NORMAL`, `MOVIMENTO_SUSPEITO`, `CRISE_CONFIRMADA`).
4. **Backend FastAPI**:
   - Persiste as leituras em um banco **PostgreSQL** (`telemetry`).
   - Mantém/atualiza registros de crises (`crises`: início, fim, BPM, duração).
   - Repassa os dados em tempo real via **WebSocket** para as dashboards conectadas.
5. **Frontend React**:
   - Tela de **tempo real**: exibe BPM, estado da crise e alertas visuais/sonoros.
   - Tela de **histórico**: lista crises com data/hora, duração e estatísticas básicas.

---

## Tecnologias Utilizadas

**Hardware**
- ESP32
- Sensor de batimentos HW‑827
- MPU6050 (acelerômetro + giroscópio)
- LEDs de indicação (GPIOs 4, 5, 18)

**Backend**
- Python 3.10+
- FastAPI
- SQLAlchemy
- PostgreSQL

**Frontend**
- React 18
- Vite

---

## Estrutura do Projeto

```text
projeto-pulseira-epilepsia/
  backend/
    app/
      main.py               # API FastAPI + WebSocket
      db/
        session.py          # conexão com PostgreSQL
        models.py           # modelos SQLAlchemy (Device, Telemetry, Crisis)
        schemas.py          # schemas Pydantic (entrada/saída)
      services/
        crisis_service.py   # lógica de controle de crises
    requirements.txt        # dependências do backend

  frontend/
    index.html
    vite.config.mts
    package.json
    src/
      main.jsx
      App.jsx               # layout principal e seleção de abas
      components/
        RealtimeDashboard.jsx  # painel em tempo real
      pages/
        HistoryPage.jsx        # página de histórico de crises

  firmware/
    esp32_pulseira_backend_example.ino  # firmware de referência para o ESP32
```

---

## Backend (FastAPI + PostgreSQL)

O backend expõe uma API REST e um WebSocket para consumo pelo frontend e por qualquer cliente autorizado (por exemplo, apps móveis no futuro).

### Configuração do Banco

Por padrão, a conexão está configurada para um PostgreSQL local (Windows):

`backend/app/db/session.py`:

```python
DATABASE_URL = "postgresql://postgres:123456@localhost:5432/pulseira"
```

Requisitos:

- Serviço PostgreSQL ativo em `localhost:5432`.
- Usuário: `postgres`
- Senha: `123456` (ajustar se necessário)
- Banco: `pulseira`

Criação do banco (uma única vez, via `psql` ou pgAdmin):

```sql
CREATE DATABASE pulseira OWNER postgres;
```

Se você utilizar outro usuário/senha, basta ajustar a `DATABASE_URL` de acordo.

### Modelagem de Dados

Local: `backend/app/db/models.py`

- **Device**
  - `id`: string (ex.: `"bracelet-01"`)
  - `name`: nome amigável do dispositivo

- **Telemetry**
  - `id`: UUID
  - `device_id`: FK → `Device.id`
  - `timestamp`: data/hora da leitura
  - `bpm`: batimentos por minuto
  - `baseline_bpm`: BPM médio de repouso
  - `status`: enum (`NORMAL`, `MOVIMENTO_SUSPEITO`, `CRISE_CONFIRMADA`)

- **Crisis**
  - `id`: UUID
  - `device_id`: FK → `Device.id`
  - `start_time`: início da crise
  - `end_time`: fim da crise (nulo enquanto ativa)
  - `avg_bpm`: BPM médio durante a crise (modelo simplificado)
  - `max_bpm`: BPM máximo observado na crise

### Endpoints

Principais rotas em `backend/app/main.py`:

- `GET /health`  
  - Verifica se a API está no ar.

- `POST /api/telemetry`  
  - Recebe telemetria enviada pelo ESP32.
  - Corpo (JSON):

    ```json
    {
      "device_id": "bracelet-01",
      "bpm": 110,
      "baseline_bpm": 80,
      "status": "CRISE_CONFIRMADA"
    }
    ```

  - Cria/atualiza registros em `telemetry` e `crises`.
  - Notifica todos dashboards conectados via WebSocket.

- `GET /api/crises?device_id=bracelet-01`  
  - Retorna o histórico de crises para o `device_id` informado.
  - Resposta: lista de objetos com `start_time`, `end_time`, `avg_bpm`, `max_bpm` etc.

- `WS /ws/dashboard`  
  - WebSocket utilizado pelo frontend.
  - Cada nova leitura recebida em `/api/telemetry` é difundida para todas as conexões ativas.

### Lógica de Crise no Backend

Local: `backend/app/services/crisis_service.py`

Regras simplificadas:

- Se chega uma leitura com `status = CRISE_CONFIRMADA` e **não existe crise aberta** para o dispositivo:
  - Cria um novo registro em `crises` com `start_time` e `max_bpm` inicial.
- Se há crise aberta:
  - Atualiza `max_bpm` com o maior BPM observado.
- Se chega uma leitura com `status = NORMAL` e há crise aberta:
  - Fecha a crise (`end_time`).
  - Preenche `avg_bpm` (modelo simplificado, usando `max_bpm` como aproximação).

---

## Frontend (React + Vite)

O frontend oferece uma dashboard web unificada para monitoramento.

### Estrutura das telas

Local: `frontend/src/App.jsx`

- Campo para escolher o **dispositivo** (`device_id`), com valor padrão `bracelet-01`.
- Abas:
  - **Tempo real** (`RealtimeDashboard`)
  - **Histórico** (`HistoryPage`)

### Tempo real – `RealtimeDashboard.jsx`

Local: `frontend/src/components/RealtimeDashboard.jsx`

Funcionalidades:

- Conecta ao WebSocket em `ws://localhost:8000/ws/dashboard`.
- Exibe:
  - Data e hora atuais.
  - Status da crise (com cor de fundo por estado):
    - Verde → `NORMAL`
    - Amarelo → `MOVIMENTO_SUSPEITO`
    - Vermelho → `CRISE_CONFIRMADA`
  - BPM atual e BPM baseline.
  - Horário da última atualização recebida.
- Quando recebe `status = "CRISE_CONFIRMADA"`:
  - Toca som (se existir `public/sounds/alert.mp3`).
  - Mostra alerta visual ao usuário.

### Histórico – `HistoryPage.jsx`

Local: `frontend/src/pages/HistoryPage.jsx`

Funcionalidades:

- Consulta `GET /api/crises?device_id=<id>`.
- Exibe tabela com:
  - Início da crise.
  - Fim da crise.
  - Duração (minutos e segundos).
  - BPM médio.
  - BPM máximo.
- Botão **Recarregar** para atualizar os dados sob demanda.

---

## Firmware (ESP32)

O firmware oficial de referência está em:  
`firmware/esp32_pulseira_backend_example.ino`

Ele integra:

- Leitura do sensor de batimentos HW‑827 com filtros (EMA, rejeição de ruídos, proteção contra IBIs inválidos).
- Cálculo de `currentBPM` e `baselineBPM` com base em uma janela de IBIs recentes.
- Leitura do MPU6050 (aceleração + giroscópio) via I2C.
- Análise de movimento com janelas de 1 segundo:
  - RMS de aceleração (`acc_rms_g`).
  - RMS de giroscópio (`gyr_rms_dps`).
  - Frequência estimada de oscilação (2–8 Hz).
- Estados globais:
  - `crise_ativa` – movimento compatível com crise.
  - `crise_confirmada` – movimento + BPM compatível com crise.
- Controle de LEDs:
  - Vermelho: crise confirmada.
  - Amarelo (vermelho+verde): movimento suspeito.
  - Verde/Azul: direção dominante do movimento quando sem crise.
- Envio de telemetria para o backend a cada 1 segundo.

### Configuração do Wi‑Fi e Backend

No início do arquivo `.ino`, você encontra:

```cpp
const char *WIFI_SSID     = "SUA_REDE_WIFI";
const char *WIFI_PASSWORD = "SUA_SENHA_WIFI";

const char *BACKEND_HOST = "192.168.0.10"; // IP do PC com o backend
const int   BACKEND_PORT = 8000;

const char *DEVICE_ID = "bracelet-01";
```

Edite para refletir o seu ambiente:

- `WIFI_SSID` / `WIFI_PASSWORD`: rede Wi‑Fi disponível para o ESP32.
- `BACKEND_HOST`: IP do computador na mesma rede que está rodando o backend (obtido via `ipconfig`).
- `DEVICE_ID`: identificador lógico da pulseira (usado no banco e no frontend).

A função `enviaTelemetria(...)` monta o JSON e faz um `POST` em:

```text
http://BACKEND_HOST:BACKEND_PORT/api/telemetry
```

### Lógica de Detecção de Crise na Pulseira

Aspectos principais:

- **Crise de movimento (`crise_ativa`)**:
  - Avalia janelas de movimento (RMS de aceleração, RMS de giroscópio, frequência).
  - Considera crise de movimento quando sucessivas janelas atendem critérios de amplitude e frequência.
  - Emite logs via `Serial`:
    - `CRISE_MOVIMENTO_DETECTADA`
    - `FIM_DA_CRISE_MOVIMENTO`

- **Crise confirmada (`crise_confirmada`)**:
  - Quando `crise_ativa` é verdadeira, o firmware verifica se o BPM está compatível com crise.
  - Critério simples (pode ser ajustado no futuro):
    - `currentBPM >= ~110` **e**
    - `currentBPM` pelo menos ~30% acima de `baselineBPM`.
  - Em caso positivo, marca `crise_confirmada = true` e registra log:
    - `[ALERTA] CRISE CONFIRMADA! BPM=... baseline=...`

Esses estados são enviados ao backend e refletem diretamente no dashboard (tempo real e histórico).

---

## Passo a Passo de Instalação

### 1. Banco de Dados (PostgreSQL)

1. Instale o PostgreSQL no Windows (se ainda não tiver).
2. Crie o banco:

   ```sql
   CREATE DATABASE pulseira OWNER postgres;
   ```

3. Ajuste a senha do usuário `postgres` para `123456` ou atualize a `DATABASE_URL` em `backend/app/db/session.py`.

### 2. Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Verifique:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Abra `http://localhost:5173` no navegador.

### 4. Firmware ESP32

1. Abra o **Arduino IDE**.
2. Instale o pacote da placa ESP32 (Boards Manager), se necessário.
3. Abra `firmware/esp32_pulseira_backend_example.ino`.
4. Configure:
   - `WIFI_SSID`, `WIFI_PASSWORD`.
   - `BACKEND_HOST` (IP do backend).
   - `DEVICE_ID` (ex.: `bracelet-01`).
5. Compile e faça upload para o ESP32.
6. Monitore os logs no Serial Monitor (115200 baud).

### 5. Visualizar Dados

- Com backend, frontend e firmware rodando:
  - Aba **Tempo real**: mostra BPM e status da crise em tempo quase imediato.
  - Aba **Histórico**: selecione o `device_id` e clique em **Recarregar** para ver as crises registradas.

---

## Próximos Passos e Melhorias

Algumas extensões naturais deste projeto:

- Autenticação de usuários (login) e controle de acesso à dashboard.
- Notificações por e‑mail/SMS/WhatsApp em caso de crise confirmada.
- Gráficos avançados de histórico (tendências, correlação horário/crises, etc.).
- Containerização com Docker (backend, frontend, banco).
- Ajuste fino dos limiares de detecção (movimento e BPM) com base em dados reais e feedback clínico.

Este repositório está estruturado para servir como base de um sistema de monitoramento de saúde mais amplo, podendo ser integrado futuramente a prontuários eletrônicos, apps móveis ou plataformas hospitalares.

