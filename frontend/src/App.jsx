import React, { useState } from "react";
import { RealtimeDashboard } from "./components/RealtimeDashboard";
import { HistoryPage } from "./pages/HistoryPage";

export const App = () => {
  const [view, setView] = useState("realtime");
  const [deviceId, setDeviceId] = useState("bracelet-01");

  return (
    <div
      style={{
        minHeight: "100vh",
        margin: 0,
        padding: "32px",
        backgroundColor: "#111827",
        color: "#f9fafb",
        fontFamily: "system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "24px",
          gap: "16px",
          flexWrap: "wrap",
        }}
      >
        <h1 style={{ margin: 0 }}>Monitor de Crises Epilépticas</h1>

        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <label>
            <span style={{ fontSize: "14px", marginRight: "4px" }}>
              Dispositivo:
            </span>
            <input
              type="text"
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
              style={{
                padding: "6px 10px",
                borderRadius: "999px",
                border: "1px solid #4b5563",
                backgroundColor: "#020617",
                color: "#f9fafb",
              }}
            />
          </label>

          <div
            style={{
              display: "inline-flex",
              backgroundColor: "#020617",
              borderRadius: "999px",
              padding: "4px",
            }}
          >
            <button
              type="button"
              onClick={() => setView("realtime")}
              style={{
                padding: "6px 14px",
                borderRadius: "999px",
                border: "none",
                cursor: "pointer",
                backgroundColor:
                  view === "realtime" ? "#22c55e" : "transparent",
                color: view === "realtime" ? "#020617" : "#e5e7eb",
                fontSize: "14px",
                fontWeight: 600,
              }}
            >
              Tempo real
            </button>
            <button
              type="button"
              onClick={() => setView("history")}
              style={{
                padding: "6px 14px",
                borderRadius: "999px",
                border: "none",
                cursor: "pointer",
                backgroundColor:
                  view === "history" ? "#22c55e" : "transparent",
                color: view === "history" ? "#020617" : "#e5e7eb",
                fontSize: "14px",
                fontWeight: 600,
              }}
            >
              Histórico
            </button>
          </div>
        </div>
      </header>

      {view === "realtime" ? (
        <RealtimeDashboard />
      ) : (
        <HistoryPage deviceId={deviceId} />
      )}
    </div>
  );
};
