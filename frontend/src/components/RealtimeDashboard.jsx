import React, { useEffect, useState } from "react";

const STATUS_COLORS = {
  NORMAL: "#16a34a",
  MOVIMENTO_SUSPEITO: "#facc15",
  CRISE_CONFIRMADA: "#dc2626",
};

export const RealtimeDashboard = () => {
  const [bpm, setBpm] = useState(null);
  const [baseline, setBaseline] = useState(null);
  const [status, setStatus] = useState("NORMAL");
  const [lastUpdate, setLastUpdate] = useState("");
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:8000/ws/dashboard");

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      setBpm(data.bpm);
      setBaseline(data.baseline_bpm ?? null);
      setStatus(data.status);
      setLastUpdate(new Date(data.timestamp).toLocaleTimeString());

      if (data.status === "CRISE_CONFIRMADA") {
        const audio = new Audio("/sounds/alert.mp3");
        audio.play().catch(() => {});
        alert("Crise confirmada! Verifique o paciente imediatamente.");
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

  const bgColor = STATUS_COLORS[status] || "#6b7280";

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
      <h2 style={{ marginTop: 0 }}>Monitor em Tempo Real</h2>
      <p style={{ marginTop: 0, marginBottom: "8px" }}>
        {now.toLocaleDateString("pt-BR")} -{" "}
        {now.toLocaleTimeString("pt-BR", { hour12: false })}
      </p>
      <p>
        <strong>Status da crise:</strong> {status}
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
    </div>
  );
};

