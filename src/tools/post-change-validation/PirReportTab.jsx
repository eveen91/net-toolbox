import React, { useState } from "react";

export default function PirReportTab() {
  const [signoffUser, setSignoffUser] = useState("");
  const [notes, setNotes] = useState("");
  const [signed, setSigned] = useState(false);

  const handleSignoff = (e) => {
    e.preventDefault();
    setSigned(true);
  };

  return (
    <div>
      <div className="tool-section-title">PIR Evidence Package & Sign-off</div>
      <p className="tool-hint" style={{ marginBottom: "20px" }}>
        Review final test results summary and complete Post-Implementation Review sign-off.
      </p>

      {signed ? (
        <div className="tool-error" style={{ borderColor: "#166534", backgroundColor: "#123a2e", color: "#6ee7b7" }}>
          PIR Package signed off by <strong>{signoffUser}</strong>. Complete evidence Markdown exported.
        </div>
      ) : (
        <form onSubmit={handleSignoff}>
          <div className="tool-field">
            <label className="tool-label">Sign-off Engineer Name</label>
            <input
              type="text"
              className="tool-input"
              value={signoffUser}
              onChange={(e) => setSignoffUser(e.target.value)}
              placeholder="e.g. Lead Network Security Engineer"
              required
            />
          </div>

          <div className="tool-field">
            <label className="tool-label">PIR Notes / Observations</label>
            <textarea
              className="tool-textarea"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="All post-change validation tests passed cleanly without emergency rollbacks."
            />
          </div>

          <div className="tool-actions">
            <button type="submit" className="tool-btn tool-btn-primary">
              Sign off & Export PIR Package
            </button>
          </div>
        </form>
      )}
    </div>
  );
}
