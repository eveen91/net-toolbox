import React, { useState } from "react";
import { importIpamRecords } from "./api.js";

function parseImport(text, type) {
  if (type === "json") return JSON.parse(text);
  const [header, ...rows] = text.trim().split(/\r?\n/).map((row) => row.split(",").map((cell) => cell.trim()));
  return rows.filter((row) => row.some(Boolean)).map((row) => Object.fromEntries(header.map((key, index) => [key, row[index] || null])));
}

export default function IpamImport({ onImported }) {
  const [text, setText] = useState(""); const [type, setType] = useState("json"); const [report, setReport] = useState(null); const [error, setError] = useState(null); const [pending, setPending] = useState(false);
  const downloadReport = () => {
    const rows = ["category,row,message", ...["create", "update", "skip", "error"].flatMap((category) => report[category].map((item) => [category, item.row || "", item.message || item.cidr || item.address || item.startIp || ""].map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")))];
    const url = URL.createObjectURL(new Blob([rows.join("\n")], { type: "text/csv" }));
    const link = document.createElement("a"); link.href = url; link.download = "ipam-import-report.csv"; link.click(); URL.revokeObjectURL(url);
  };
  const run = async (confirm) => {
    setError(null); setPending(true);
    try {
      const result = await importIpamRecords(parseImport(text, type), confirm);
      setReport(result);
      if (confirm) onImported?.();
    } catch (err) { setError(err.message); } finally { setPending(false); }
  };
  return <section className="ip-import" aria-labelledby="ip-import-title"><h3 id="ip-import-title" className="ip-section-sub-title">Import CSV / JSON</h3><div className="ip-import-controls"><select className="tool-input" value={type} onChange={(event) => setType(event.target.value)}><option value="json">JSON</option><option value="csv">CSV</option></select><textarea className="tool-input" value={text} onChange={(event) => setText(event.target.value)} placeholder='[{"resourceType":"subnet","cidr":"10.0.0.0/24"}]' /><button className="tool-btn" disabled={!text.trim() || pending} onClick={() => run(false)}>Dry run</button>{report?.ready && <button className="tool-btn tool-btn-primary" disabled={pending} onClick={() => run(true)}>Confirm import</button>}</div>{error && <div className="tool-error" role="alert">{error}</div>}{report && <div className="tool-hint" role="status">Create: {report.summary.create} · Skip: {report.summary.skip} · Errors: {report.summary.error}<button className="tool-btn tool-btn-ghost ip-row-btn" onClick={downloadReport}>Export report</button>{report.error.map((item) => <div key={item.row} className="tool-error">Row {item.row}: {item.message}</div>)}</div>}</section>;
}
