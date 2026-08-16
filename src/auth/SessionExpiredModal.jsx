import React from "react";
import "./auth.css";

export default function SessionExpiredModal() {
  const handleOk = () => {
    window.location.reload();
  };

  return (
    <div className="nt-session-expired-overlay">
      <div className="nt-session-expired-dialog">
        <h2>Session expired</h2>
        <p className="tool-hint">Your session expired — please log in again.</p>
        <button className="tool-btn tool-btn-primary" onClick={handleOk}>
          OK
        </button>
      </div>
    </div>
  );
}