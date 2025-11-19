#include <Arduino.h>
#include "esp_wifi.h"
#include "esp_bt.h"
#include <Wire.h>
#include <vector>
#include <math.h>

// ===========================================================================
// ====================== IDENTIFICAÇÃO / DEVICE ID ==========================
// ===========================================================================

// ID lógico da pulseira (aparece no backend / dashboard)
const char *DEVICE_ID = "bracelet-01";

// ===========================================================================
// =============== ESTADOS GLOBAIS DE CRISE / BATIMENTO ======================
// ===========================================================================

bool crise_ativa      = false; // Detectada pelo MPU (movimento tipo crise)
bool crise_confirmada = false; // Movimento + batimento compatível

// ==================== PULSE (HW-827) =======================================

constexpr int PULSE_PIN = 34; // Sensor de batimento no GPIO34 (ADC1)

// Filtro EMA do sinal bruto
float pulseEMA = 0.0f;
const float PULSE_ALPHA_WARM = 0.10f;
const float PULSE_ALPHA      = 0.005f;
bool  pulseEmaWarmed         = false;
unsigned long pulseEmaStartMs = 0;

// Detecção de pico
bool Pulse = false;
int  IBI   = 600;
unsigned long lastBeatMs = 0;
int thresh = 512;
int peakv  = 512;
int trough = 512;
int amp    = 100;

// Limites de intervalo entre batimentos (IBI)
const int MIN_IBI_MS = 500;   // 500 ms  -> ~120 bpm máximo
const int MAX_IBI_MS = 1500;  // 1500 ms -> ~40 bpm mínimo

// Armazena IBIs recentes
std::vector<int> ibiList;
const size_t MAX_IBI_SAMPLES = 20;

float currentBPM    = 0.0f;  // BPM após filtros (valor usado/enviado)
float baselineBPM   = 0.0f;  // BPM médio em repouso
bool  baselineReady = false;

// Filtro extra para remover ruídos de BPM
float filteredBPM       = 0.0f;
bool  filteredBPMReady  = false;
int   bpmSpikeCount     = 0;      // quantos batimentos seguidos parecem "pico absurdo"
const float BPM_MAX_JUMP = 30.0f; // variação máxima aceitável entre medidas
const int   BPM_SPIKE_TOLERANCE = 3; // depois de N leituras "altas" seguidas, aceita

// ===========================================================================
// ================== Função que atualiza o batimento ========================
// ===========================================================================

void updatePulse() {
  unsigned long now = millis();
  int raw = analogRead(PULSE_PIN);

  // Filtro EMA para estabilizar o sinal
  float alpha = pulseEmaWarmed ? PULSE_ALPHA : PULSE_ALPHA_WARM;
  pulseEMA = (1.0f - alpha) * pulseEMA + alpha * (float)raw;
  if (!pulseEmaWarmed && (now - pulseEmaStartMs) > 1500) {
    pulseEmaWarmed = true;
  }

  float ac = (float)raw - pulseEMA;
  int Signal = (int)(ac + 2048.0f);
  if (Signal < 0)    Signal = 0;
  if (Signal > 4095) Signal = 4095;

  // Atualiza pico e vale (ajuste de threshold)
  if (Signal < thresh && (now - lastBeatMs) > (unsigned long)(IBI * 3 / 5)) {
    if (Signal < trough) trough = Signal;
  }
  if (Signal > thresh && Signal > peakv) {
    peakv = Signal;
  }

  // Proteção: se ficar muito tempo sem batida, reseta
  if (lastBeatMs != 0 && (now - lastBeatMs) > 3000) { // >3s sem batida válida
    lastBeatMs = 0;
    ibiList.clear();
    baselineReady      = false;
    currentBPM         = 0.0f;
    filteredBPMReady   = false;
    bpmSpikeCount      = 0;
  }

  // Detecção de pico
  if (!Pulse && Signal > thresh) {

    if (lastBeatMs == 0) {
      // Primeiro batimento: só marca o tempo, não calcula IBI ainda
      lastBeatMs = now;
      Pulse = true;
      return;
    }

    unsigned long dt = now - lastBeatMs;

    // Verifica se o intervalo está dentro do aceitável
    if (dt >= (unsigned long)MIN_IBI_MS && dt <= (unsigned long)MAX_IBI_MS) {
      IBI = (int)dt;

      // Calcula BPM candidato (antes do filtro anti-ruído)
      float bpmCandidate = 60000.0f / (float)IBI;

      // Descarta BPM muito absurdos (ruído extremo)
      if (bpmCandidate >= 40.0f && bpmCandidate <= 160.0f) {
        ibiList.push_back(IBI);
        if (ibiList.size() > MAX_IBI_SAMPLES) {
          ibiList.erase(ibiList.begin());
        }

        // ================== Atualiza baseline (repouso) ==================
        // Atualiza baseline só quando NÃO há crise de movimento
        if (!crise_ativa && ibiList.size() >= 8) {
          long sum = 0;
          for (int v : ibiList) sum += v;
          float avgIBI = (float)sum / ibiList.size();
          float bpmAvg = 60000.0f / avgIBI;

          // Baseline com EMA bem lento
          if (!baselineReady) {
            baselineBPM   = bpmAvg;
            baselineReady = true;
          } else {
            baselineBPM = baselineBPM * 0.95f + bpmAvg * 0.05f;
          }
        }

        // ================== Filtro extra anti-ruído de BPM ==================
        float newBpm = bpmCandidate;

        if (!filteredBPMReady) {
          // Primeira medida confiável
          filteredBPM      = newBpm;
          filteredBPMReady = true;
          bpmSpikeCount    = 0;
        } else {
          float diff = fabs(newBpm - filteredBPM);

          if (diff > BPM_MAX_JUMP) {
            // Suspeita de pico (saltou demais de uma vez)
            bpmSpikeCount++;
            if (bpmSpikeCount >= BPM_SPIKE_TOLERANCE) {
              // Se esse valor "alto" se repetiu várias vezes, aceitamos
              filteredBPM   = newBpm;
              bpmSpikeCount = 0;
            } else {
              // Considera ruído: mantém filteredBPM (não atualiza aqui)
            }
          } else {
            // Diferença aceitável -> suaviza com EMA
            bpmSpikeCount = 0;
            filteredBPM = filteredBPM * 0.7f + newBpm * 0.3f;
          }
        }

        // currentBPM usado no resto do código + telemetria
        currentBPM = filteredBPMReady ? filteredBPM : newBpm;
      }

      lastBeatMs = now;
      Pulse = true;
    } else {
      // dt muito curto ou muito longo -> ruído
      Pulse = true;
    }
  }

  // Quando o sinal volta abaixo do limiar, ajusta threshold
  if (Pulse && Signal < thresh) {
    Pulse = false;
    amp = peakv - trough;
    if (amp < 20) amp = 20;
    thresh = trough + (amp / 2);
    peakv = thresh;
    trough = thresh;
  }
}

// ===========================================================================
// ===== Verifica se o BPM é compatível com crise ============================
// ===========================================================================

bool hrConsistenteComCrise() {
  if (!baselineReady) return false;
  if (currentBPM < 40.0f || currentBPM > 200.0f) return false;

  float ratio = currentBPM / baselineBPM;

  // Critério simples:
  // - BPM atual >= 110
  // - Pelo menos 30% acima do baseline
  if (currentBPM >= 110.0f && ratio >= 1.30f) {
    return true;
  }
  return false;
}

// ===========================================================================
// ====================== MPU6050 (SEM LEDS) =================================
// ===========================================================================

constexpr int SDA_PIN = 21;
constexpr int SCL_PIN = 22;
constexpr uint8_t MPU_ADDR = 0x68;

constexpr uint8_t REG_WHO_AM_I     = 0x75;
constexpr uint8_t REG_PWR_MGMT_1   = 0x6B;
constexpr uint8_t REG_SMPLRT_DIV   = 0x19;
constexpr uint8_t REG_CONFIG       = 0x1A;
constexpr uint8_t REG_GYRO_CONFIG  = 0x1B;
constexpr uint8_t REG_ACCEL_CONFIG = 0x1C;
constexpr uint8_t REG_ACCEL_XOUT_H = 0x3B;

constexpr float G = 9.80665f;
#define ACC_LSB_PER_G   4096.0f  // FSR +/- 8g
#define GYR_LSB_PER_DPS 65.5f    // FSR +/- 500dps

// ---------------------------------------------------------------------------
// JANELA E PADRÕES DE CRISE (CALIBRAÇÃO BASEADA EM LITERATURA)
// ---------------------------------------------------------------------------

#define FS_HZ              100
#define WINDOW_SECONDS     1.0f
#define WINDOW_SAMPLES     (int)(FS_HZ*WINDOW_SECONDS)

// Estudos com pulseira no punho sugerem que a maior parte da energia de
// crises tônico-clônicas fica ali por volta de 4–8 Hz, enquanto movimentos
// normais ficam < ~0.8–1 Hz. Aqui usamos uma faixa 3–8 Hz para tolerar
// um pouco de variação, mas focar em tremor convulsivo real.
#define FREQ_MIN_HZ        2.0f
#define FREQ_MAX_HZ        10.0f

// Mais sensível para detectar crises tônico-clônicas com base em janelas
// de 1 s, mas exigindo alguns segundos em sequência para considerar "crise".
#define REQUIRED_WINDOWS_ON  2   // ≈ 3 s seguidos padrão crise para ativar
#define REQUIRED_WINDOWS_OFF 2   // ≈ 2 s limpos para encerrar crise

// Limiares de amplitude baseados nos padrões de repouso que você mediu
// (repouso ~0,007 g / ~3 dps) e em descrições de crises com amplitude bem
// maior. 0.35 g RMS e 50 dps RMS filtram muito movimento leve/ambulatorial.
#define ACC_RMS_MIN_G      0.30f
#define GYR_RMS_MIN_DPS    40.0f

#define HP_A            0.97f
#define DIR_MIN_G_HP    0.12f

#define PRINT_WINDOW_SUMMARY 1
#define PRINT_CRISE_EVENTS   1
#define DEBUG_DIR            0
#define DIR_LOG_EVERY_MS     400

static float smv_buf[WINDOW_SAMPLES];
static float gyrmag_buf[WINDOW_SAMPLES];
static int   widx = 0;

static int   windows_ok    = 0;
static int   windows_clear = 0;

static float ax_prev_g = 0, ay_prev_g = 0;
static float ax_hp_g = 0, ay_hp_g = 0;

unsigned long lastDirLogMs = 0;

// I2C helpers
inline void writeReg(uint8_t reg, uint8_t data) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  Wire.write(data);
  Wire.endTransmission(true);
}

inline bool readBytes(uint8_t reg, uint8_t *buf, uint8_t len) {
  Wire.beginTransmission(MPU_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  uint8_t n = Wire.requestFrom((int)MPU_ADDR, (int)len, (int)true);
  if (n != len) return false;
  for (uint8_t i = 0; i < len; i++) buf[i] = Wire.read();
  return true;
}

float rms(const float *x, int n) {
  double acc = 0.0;
  for (int i = 0; i < n; ++i) acc += (double)x[i]*(double)x[i];
  acc /= (double)n;
  return (float)sqrt(acc);
}

float estimateFreqByZeroCross(const float *x, int n, float fs) {
  int zc = 0;
  for (int i = 1; i < n; ++i) {
    if ((x[i-1] <= 0 && x[i] > 0) || (x[i-1] >= 0 && x[i] < 0)) zc++;
  }
  float seconds = n / fs;
  if (seconds <= 0) return 0.0f;
  float cycles = zc / 2.0f;
  return cycles / seconds;
}

bool windowLooksLikeSeizure_ACC_GYR(float &acc_rms_g, float &freq_hz, float &gyr_rms_dps) {
  static float smv_local[WINDOW_SAMPLES];
  static float gyr_local[WINDOW_SAMPLES];
  for (int i = 0; i < WINDOW_SAMPLES; ++i) {
    smv_local[i] = smv_buf[i];
    gyr_local[i] = gyrmag_buf[i];
  }

  // RMS do módulo de aceleração dinâmica em "g"
  acc_rms_g   = rms(smv_local, WINDOW_SAMPLES) / G;
  // Frequência estimada (zero-cross) do tremor
  freq_hz     = estimateFreqByZeroCross(smv_local, WINDOW_SAMPLES, (float)FS_HZ);
  // RMS da magnitude do giroscópio
  gyr_rms_dps = rms(gyr_local, WINDOW_SAMPLES);

  bool acc_ok  = (acc_rms_g   >= ACC_RMS_MIN_G);
  bool freq_ok = (freq_hz     >= FREQ_MIN_HZ && freq_hz <= FREQ_MAX_HZ);
  bool gyr_ok  = (gyr_rms_dps >= GYR_RMS_MIN_DPS);

  // Só consideramos "janela com cara de crise" se:
  // - amplitude de aceleração for alta
  // - frequência estiver na banda típica de tremor convulsivo
  // - giroscópio indicar rotação forte
  return (acc_ok && freq_ok && gyr_ok);
}

// ===========================================================================
// =================== TELEMETRIA VIA SERIAL (COM4) ==========================
// ===========================================================================

void enviaTelemetriaSerial(float bpm,
                           float baselineBpm,
                           bool criseMovimento,
                           bool criseConfirmada) {
  // Mapeia os estados para o backend
  String status = "NORMAL";
  if (criseConfirmada) {
    status = "CRISE_CONFIRMADA";
  } else if (criseMovimento) {
    status = "MOVIMENTO_SUSPEITO";
  }

  String payload = "{";
  payload += "\"device_id\":\"" + String(DEVICE_ID) + "\",";
  payload += "\"bpm\":" + String((int)bpm) + ",";
  payload += "\"baseline_bpm\":" + String((int)baselineBpm) + ",";
  payload += "\"status\":\"" + status + "\"";
  payload += "}";

  // Linha específica para o bridge ler e mandar ao backend
  Serial.println(payload);
}

// ===========================================================================
// ============================ SETUP ========================================
// ===========================================================================

void setup() {
  Serial.begin(115200);
  delay(200);

  // Desliga Wi-Fi e Bluetooth para reduzir ruído no ADC
  esp_wifi_stop();
  esp_bt_controller_disable();

  // Pulse sensor
  analogReadResolution(12);
  analogSetAttenuation(ADC_6db);
  pinMode(PULSE_PIN, INPUT);
  pulseEmaStartMs = millis();

  // I2C + MPU6050
  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  delay(200);

  uint8_t who = 0xFF;
  readBytes(REG_WHO_AM_I, &who, 1);
  if (who != 0x68 && who != 0x70) {
    Serial.println("ERRO: MPU-6050 não encontrado!");
    while (true) {
      delay(1000); // trava aqui, sem usar LEDs
    }
  }

  writeReg(REG_PWR_MGMT_1, 0x00);
  delay(100);
  writeReg(REG_SMPLRT_DIV, 0x07);      // ~125 Hz
  writeReg(REG_CONFIG,     0x04);      // DLPF ~20 Hz
  writeReg(REG_GYRO_CONFIG,(1 << 3));  // ±500 dps
  writeReg(REG_ACCEL_CONFIG,(2 << 3)); // ±8 g
  Wire.setClock(400000);

  for (int i = 0; i < WINDOW_SAMPLES; ++i) {
    smv_buf[i]     = 0.0f;
    gyrmag_buf[i]  = 0.0f;
  }

  Serial.println("Setup completo. Detecção de crise (movimento + BPM) iniciada.");
}

// ===========================================================================
// ============================== LOOP =======================================
// ===========================================================================

void loop() {
  // 1) Atualiza batimento (HW-827)
  updatePulse();

  // 2) Lê MPU6050
  uint8_t buf[14];
  if (!readBytes(REG_ACCEL_XOUT_H, buf, 14)) {
    delay(10);
    return;
  }

  auto toInt16 = [](uint8_t hi, uint8_t lo) -> int16_t { return (int16_t)((hi << 8) | lo); };
  int16_t ax_raw = toInt16(buf[0],  buf[1]);
  int16_t ay_raw = toInt16(buf[2],  buf[3]);
  int16_t az_raw = toInt16(buf[4],  buf[5]);
  int16_t gx_raw = toInt16(buf[8],  buf[9]);
  int16_t gy_raw = toInt16(buf[10], buf[11]);
  int16_t gz_raw = toInt16(buf[12], buf[13]);

  float ax_g = (ax_raw / ACC_LSB_PER_G);
  float ay_g = (ay_raw / ACC_LSB_PER_G);
  float az_g = (az_raw / ACC_LSB_PER_G);

  float ax_ms2 = ax_g * G;
  float ay_ms2 = ay_g * G;
  float az_ms2 = az_g * G;

  float smv = sqrtf(ax_ms2*ax_ms2 + ay_ms2*ay_ms2 + az_ms2*az_ms2) - G;

  float gx_dps = (gx_raw / GYR_LSB_PER_DPS);
  float gy_dps = (gy_raw / GYR_LSB_PER_DPS);
  float gz_dps = (gz_raw / GYR_LSB_PER_DPS);
  float gyr_mag_dps = sqrtf(gx_dps*gx_dps + gy_dps*gy_dps + gz_dps*gz_dps);

  smv_buf[widx]     = smv;
  gyrmag_buf[widx]  = gyr_mag_dps;
  widx = (widx + 1) % WINDOW_SAMPLES;

  // Passa-alta para direção (sem LEDs)
  float ax_hp = HP_A * (ax_hp_g + (ax_g - ax_prev_g));
  float ay_hp = HP_A * (ay_hp_g + (ay_g - ay_prev_g));
  ax_prev_g = ax_g;
  ay_prev_g = ay_g;
  ax_hp_g   = ax_hp;
  ay_hp_g   = ay_hp;

  // 3) Janela de análise
  static int sampleCount = 0;
  sampleCount++;
  if (sampleCount >= WINDOW_SAMPLES) {
    sampleCount = 0;

    float acc_rms_g, freq_hz, gyr_rms_dps;
    bool looks = windowLooksLikeSeizure_ACC_GYR(acc_rms_g, freq_hz, gyr_rms_dps);

    if (looks) {
      windows_ok++;
      windows_clear = 0;
    } else {
      windows_clear++;
      if (windows_ok > 0) windows_ok--;
    }

    // Ativa crise de movimento se tiver N janelas seguidas com padrão de crise
    if (!crise_ativa && windows_ok >= REQUIRED_WINDOWS_ON) {
      crise_ativa = true;
      crise_confirmada = false;
      if (PRINT_CRISE_EVENTS) Serial.println("CRISE_MOVIMENTO_DETECTADA");
    }

    // Encerra crise de movimento após janelas limpas
    if (crise_ativa && windows_clear >= REQUIRED_WINDOWS_OFF) {
      crise_ativa = false;
      crise_confirmada = false;
      if (PRINT_CRISE_EVENTS) Serial.println("FIM_DA_CRISE_MOVIMENTO");
    }

    // Se há movimento tipo crise, checa batimento
    if (crise_ativa) {
      bool hrOK = hrConsistenteComCrise();
      if (hrOK && !crise_confirmada) {
        crise_confirmada = true;
        Serial.print("[ALERTA] CRISE CONFIRMADA! BPM=");
        Serial.print(currentBPM, 1);
        Serial.print(" baseline=");
        Serial.println(baselineBPM, 1);
      } else if (!hrOK && crise_confirmada) {
        crise_confirmada = false;
        Serial.println("[INFO] Batimento deixou de estar em padrão de crise.");
      }

      // Log durante crise de movimento
      Serial.print("[CRISE] acc=");
      Serial.print(acc_rms_g, 3);
      Serial.print("g  f=");
      Serial.print(freq_hz, 2);
      Serial.print("Hz  gyr=");
      Serial.print(gyr_rms_dps, 1);
      Serial.print("dps  BPM=");
      Serial.print(currentBPM, 1);
      Serial.print("  base=");
      Serial.print(baselineBPM, 1);
      Serial.print("  hrOK=");
      Serial.println(hrOK ? "1" : "0");
    } else {
      if (PRINT_WINDOW_SUMMARY) {
        Serial.print("[WIN] acc=");
        Serial.print(acc_rms_g, 3);
        Serial.print("g  f=");
        Serial.print(freq_hz, 2);
        Serial.print("Hz  gyr=");
        Serial.print(gyr_rms_dps, 1);
        Serial.print("dps  ok=");
        Serial.print(looks ? "1" : "0");
        Serial.print("  cnt=");
        Serial.print(windows_ok);
        Serial.print("  BPM=");
        Serial.print(currentBPM, 1);
        Serial.print("  base=");
        Serial.println(baselineBPM, 1);
      }
    }
  }

  // 4) Direção apenas para debug opcional (sem LEDs)
  float absx = fabs(ax_hp_g);
  float absy = fabs(ay_hp_g);
  bool x_domina = (absx > absy) && (absx >= DIR_MIN_G_HP);
  bool y_domina = (absy > absx) && (absy >= DIR_MIN_G_HP);
  (void)x_domina;
  (void)y_domina;

  // Debug opcional de direção
  if (DEBUG_DIR) {
    unsigned long now = millis();
    if (now - lastDirLogMs >= DIR_LOG_EVERY_MS) {
      lastDirLogMs = now;
      Serial.print("[DIR] |Xhp|=");
      Serial.print(absx, 3);
      Serial.print("g  |Yhp|=");
      Serial.print(absy, 3);
      Serial.println("g");
    }
  }

  // 5) Envio de telemetria a cada 1 segundo (via Serial / COM4)
  static unsigned long lastSendMs = 0;
  unsigned long nowMs = millis();
  if (nowMs - lastSendMs >= 1000) { // 1s
    lastSendMs = nowMs;
    enviaTelemetriaSerial(currentBPM, baselineBPM, crise_ativa, crise_confirmada);
  }

  delay(10);
}