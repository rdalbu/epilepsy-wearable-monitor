import React, { useEffect, useState } from "react";

export const HistoryPage = ({ deviceId }) => {
  const [crises, setCrises] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const fetchCrises = async () => {
    try {
      setLoading(true);
      setError("");
      const res = await fetch(
        `http://localhost:8000/api/crises?device_id=${encodeURIComponent(
          deviceId || "",
        )}`,
      );
      if (!res.ok) {
        throw new Error("Erro ao buscar crises");
      }
      const data = await res.json();
      setCrises(data);
    } catch (err) {
      setError(err.message || "Erro inesperado");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (deviceId) {
      fetchCrises();
    }
  }, [deviceId]);

  const formatDateTime = (value) => {
    if (!value) return "--";
    const d = new Date(value);
    return d.toLocaleString("pt-BR");
  };

  const formatDuration = (start, end) => {
    if (!start || !end) return "--";
    const s = new Date(start);
    const e = new Date(end);
    const diffSec = Math.round((e - s) / 1000);
    const min = Math.floor(diffSec / 60);
    const sec = diffSec % 60;
    return `${min}m ${sec}s`;
  };

  return (
    <div
      style={{
        maxWidth: "960px",
        margin: "0 auto",
        backgroundColor: "#020617",
        borderRadius: "12px",
        padding: "24px",
        boxShadow: "0 10px 25px rgba(0,0,0,0.4)",
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "16px",
        }}
      >
        <h2 style={{ margin: 0 }}>Histórico de Crises</h2>
        <button
          type="button"
          onClick={fetchCrises}
          disabled={loading}
          style={{
            padding: "8px 16px",
            borderRadius: "999px",
            border: "none",
            cursor: "pointer",
            backgroundColor: "#22c55e",
            color: "#020617",
            fontWeight: 600,
          }}
        >
          {loading ? "Atualizando..." : "Recarregar"}
        </button>
      </div>

      {error && (
        <p style={{ color: "#f97316", marginBottom: "12px" }}>{error}</p>
      )}

      {crises.length === 0 && !loading ? (
        <p style={{ color: "#9ca3af" }}>
          Nenhuma crise registrada ainda para este dispositivo.
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table
            style={{
              width: "100%",
              borderCollapse: "collapse",
              fontSize: "14px",
            }}
          >
            <thead>
              <tr style={{ backgroundColor: "#0f172a" }}>
                <th style={{ padding: "8px", textAlign: "left" }}>Início</th>
                <th style={{ padding: "8px", textAlign: "left" }}>Fim</th>
                <th style={{ padding: "8px", textAlign: "left" }}>Duração</th>
                <th style={{ padding: "8px", textAlign: "left" }}>BPM médio</th>
                <th style={{ padding: "8px", textAlign: "left" }}>BPM máx</th>
              </tr>
            </thead>
            <tbody>
              {crises.map((c) => (
                <tr key={c.id} style={{ borderTop: "1px solid #1f2937" }}>
                  <td style={{ padding: "8px" }}>
                    {formatDateTime(c.start_time)}
                  </td>
                  <td style={{ padding: "8px" }}>
                    {formatDateTime(c.end_time)}
                  </td>
                  <td style={{ padding: "8px" }}>
                    {formatDuration(c.start_time, c.end_time)}
                  </td>
                  <td style={{ padding: "8px" }}>{c.avg_bpm ?? "--"}</td>
                  <td style={{ padding: "8px" }}>{c.max_bpm ?? "--"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

