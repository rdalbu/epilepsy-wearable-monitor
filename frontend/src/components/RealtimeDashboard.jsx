import React, { useEffect, useState } from "react";

const STATUS_COLORS = {
  NORMAL: "#16a34a",
  MOVIMENTO_SUSPEITO: "#facc15",
  CRISE_CONFIRMADA: "#dc2626",
};

export const RealtimeDashboard = ({ deviceId = "bracelet-01" }) => {
  const [bpm, setBpm] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const [status, setStatus] = useState("NORMAL"); // status vindo do backend
  const [lastUpdate, setLastUpdate] = useState("");
  const [now, setNow] = useState(new Date());
  const [useHrCheck, setUseHrCheck] = useState(true);
  const [bpmHistory, setBpmHistory] = useState([]); // últimos ~25 minutos
  const [crisisEvents, setCrisisEvents] = useState([]); // últimos eventos de crise
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [volume, setVolume] = useState(1);
  const [notifications, setNotifications] = useState([]);

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8000/ws/dashboard");

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);

      // Atualiza estado bruto vindo do backend
      setBpm(data.bpm);
      setBaseline(data.baseline_bpm ?? null);
      setStatus(data.status);
      setLastUpdate(new Date(data.timestamp).toLocaleTimeString());

      // Atualiza histórico de BPM (últimos 25 minutos)
      const ts = new Date(data.timestamp).getTime();
      if (!Number.isNaN(ts) && typeof data.bpm === "number") {
        setBpmHistory((prev) => {
          const cutoff = ts - 25 * 60 * 1000; // 25 min
          const filtered = prev.filter((p) => p.t >= cutoff);
          filtered.push({ t: ts, bpm: data.bpm });
          return filtered;
        });
      }

      // Atualiza painel de eventos de crise
      if (data.crisis_event) {
        setCrisisEvents((prev) => {
          const events = [...prev];
          const ce = data.crisis_event;
          const time = new Date(data.timestamp);

          if (ce.type === "CRISIS_STARTED") {
            events.unshift({
              id: ce.crisis_id,
              startTime: time,
              endTime: null,
              durationSec: null,
            });
          } else if (ce.type === "CRISIS_ENDED") {
            const idx = events.findIndex((e) => e.id === ce.crisis_id);
            if (idx !== -1) {
              const startTime = events[idx].startTime;
              const endTime = time;
              const durationSec =
                startTime != null
                  ? Math.max(
                      1,
                      Math.round((endTime.getTime() - startTime.getTime()) / 1000),
                    )
                  : null;
              events[idx] = { ...events[idx], endTime, durationSec };
            } else {
              events.unshift({
                id: ce.crisis_id,
                startTime: null,
                endTime: time,
                durationSec: null,
              });
            }
          }

          // Mantém só os últimos 5 eventos
          return events.slice(0, 5);
        });
      }
    };

    ws.onclose = () => {
      console.warn("WebSocket desconectado do backend.");
    };

    return () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    const id = setInterval(() => {
      setNow(new Date());
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const effectiveStatus =
    !useHrCheck && status === "MOVIMENTO_SUSPEITO" ? "CRISE_CONFIRMADA" : status;

  // Envia configuração de uso de batimentos para o backend sempre que mudar
  useEffect(() => {
    const controller = new AbortController();

    const sendConfig = async () => {
      try {
        await fetch("http://localhost:8000/api/device-config", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            device_id: deviceId || "bracelet-01",
            use_hr_check: useHrCheck,
          }),
          signal: controller.signal,
        });
      } catch {
        // Silencia erro no dashboard; backend pode estar offline
      }
    };

    sendConfig();

    return () => controller.abort();
  }, [deviceId, useHrCheck]);

  // Dispara alerta sempre que o status efetivo entra em CRISE_CONFIRMADA
  useEffect(() => {
    if (effectiveStatus !== "CRISE_CONFIRMADA") return;

    if (soundEnabled) {
      const audio = new Audio("/sounds/alert.mp3");
      audio.volume = volume;
      audio.play().catch(() => {});
    }

    setNotifications((prev) => [
      {
        id: Date.now(),
        message: "Crise confirmada! Verifique o paciente imediatamente.",
        time: new Date(),
      },
      ...prev,
    ]);
  }, [effectiveStatus, soundEnabled, volume]);

  const bgColor = STATUS_COLORS[effectiveStatus] || "#6b7280";

  const renderBpmChart = () => {
    if (!bpmHistory.length) {
      return <p style={{ marginTop: "8px" }}>Sem dados suficientes ainda.</p>;
    }

    const width = 440;
    const height = 120;
    const margin = 10;

    const xs = bpmHistory.map((p) => p.t);
    const ys = bpmHistory.map((p) => p.bpm);

    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);

    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);

    const spanX = maxX - minX || 1;
    const spanY = maxY - minY || 1;

    const points = bpmHistory
      .map((p) => {
        const x = margin + ((p.t - minX) / spanX) * (width - margin * 2);
        const y =
          height - margin - ((p.bpm - minY) / spanY) * (height - margin * 2);
        return `${x},${y}`;
      })
      .join(" ");

    return (
      <svg
        width={width}
        height={height}
        style={{
          backgroundColor: "rgba(0,0,0,0.25)",
          borderRadius: "8px",
          marginTop: "8px",
        }}
      >
        <polyline
          fill="none"
          stroke="#60a5fa"
          strokeWidth="2"
          points={points}
        />
      </svg>
    );
  };

  return (
    <div
      style={{
        padding: "24px",
        borderRadius: "12px",
        backgroundColor: bgColor,
        color: "#fff",
        maxWidth: "480px",
        margin: "0 auto",
        boxShadow: "0 10px 25px rgba(0,0,0,0.3)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <h2 style={{ marginTop: 0, marginBottom: 0 }}>Monitor em Tempo Real</h2>
        <span
          style={{
            padding: "4px 10px",
            borderRadius: "999px",
            fontSize: "11px",
            fontWeight: 600,
            backgroundColor: useHrCheck ? "#22c55e" : "#f97316",
            color: "#020617",
            whiteSpace: "nowrap",
          }}
        >
          {useHrCheck ? "Crise = movimento + batimento" : "Crise = só movimento"}
        </span>
      </div>

      <div
        style={{
          marginTop: "8px",
          marginBottom: "4px",
          display: "flex",
          flexWrap: "wrap",
          gap: "8px",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <button
          type="button"
          onClick={() => setUseHrCheck((prev) => !prev)}
          style={{
            padding: "6px 12px",
            borderRadius: "999px",
            border: "none",
            cursor: "pointer",
            backgroundColor: useHrCheck ? "#22c55e" : "#4b5563",
            color: "#f9fafb",
            fontSize: "12px",
            fontWeight: 600,
          }}
        >
          {useHrCheck
            ? "Usando verificação de batimentos na crise"
            : "Somente movimento (sem verificação de batimentos)"}
        </button>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            fontSize: "11px",
          }}
        >
          <button
            type="button"
            onClick={() => setSoundEnabled((prev) => !prev)}
            style={{
              padding: "4px 10px",
              borderRadius: "999px",
              border: "none",
              cursor: "pointer",
              backgroundColor: soundEnabled ? "#22c55e" : "#4b5563",
              color: "#f9fafb",
              fontWeight: 600,
              fontSize: "11px",
              whiteSpace: "nowrap",
            }}
          >
            {soundEnabled ? "Som de alerta: ligado" : "Som de alerta: desligado"}
          </button>
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <span>Volume</span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={volume}
              onChange={(e) => setVolume(Number(e.target.value))}
              style={{ cursor: "pointer" }}
            />
          </div>
        </div>
      </div>

      <p style={{ marginTop: 0, marginBottom: "8px" }}>
        {now.toLocaleDateString("pt-BR")} -{" "}
        {now.toLocaleTimeString("pt-BR", { hour12: false })}
      </p>
      <p>
        <strong>Status da crise:</strong> {effectiveStatus}
      </p>
      <p>
        <strong>BPM atual:</strong> {bpm ?? "--"}
      </p>
      <p>
        <strong>BPM baseline:</strong> {baseline ?? "--"}
      </p>
      <p>
        <small>Última atualização: {lastUpdate || "--"}</small>
      </p>

      <div style={{ marginTop: "12px" }}>
        <h3 style={{ margin: 0, fontSize: "14px" }}>
          BPM (últimos ~25 minutos)
        </h3>
        {renderBpmChart()}
      </div>

      <div style={{ marginTop: "16px" }}>
        <h3 style={{ margin: 0, fontSize: "14px" }}>Últimos eventos de crise</h3>
        {crisisEvents.length === 0 ? (
          <p style={{ marginTop: "4px", fontSize: "13px" }}>
            Nenhum evento de crise registrado ainda.
          </p>
        ) : (
          <ul
            style={{
              marginTop: "4px",
              paddingLeft: "18px",
              fontSize: "13px",
            }}
          >
            {crisisEvents.map((ev) => (
              <li key={ev.id}>
                {ev.startTime && (
                  <>
                    Início:{" "}
                    {ev.startTime.toLocaleTimeString("pt-BR", {
                      hour12: false,
                    })}
                    {"; "}
                  </>
                )}
                {ev.endTime ? (
                  <>
                    Fim:{" "}
                    {ev.endTime.toLocaleTimeString("pt-BR", {
                      hour12: false,
                    })}
                    {ev.durationSec != null && (
                      <>
                        ; duração: {Math.floor(ev.durationSec / 60)}m
                        {ev.durationSec % 60}s
                      </>
                    )}
                  </>
                ) : (
                  <span>Crise em andamento</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {notifications.length > 0 && (
        <div
          style={{
            marginTop: "16px",
            padding: "10px 12px",
            borderRadius: "10px",
            backgroundColor: "rgba(15,23,42,0.9)",
            color: "#fef2f2",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "6px",
            }}
          >
            <strong style={{ fontSize: "13px" }}>Alertas recentes</strong>
            <button
              type="button"
              onClick={() => setNotifications([])}
              style={{
                border: "none",
                background: "transparent",
                color: "#f97316",
                cursor: "pointer",
                fontSize: "11px",
                textDecoration: "underline",
              }}
            >
              Limpar
            </button>
          </div>
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              fontSize: "12px",
              maxHeight: "120px",
              overflowY: "auto",
            }}
          >
            {notifications.map((n) => (
              <li
                key={n.id}
                style={{
                  padding: "4px 0",
                  borderTop: "1px solid rgba(248,250,252,0.08)",
                }}
              >
                <span style={{ display: "block" }}>{n.message}</span>
                <span style={{ opacity: 0.7 }}>
                  {n.time.toLocaleTimeString("pt-BR", { hour12: false })}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
