export function parseLines(text) {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));
}

// Each line looks like: "hostname,linux" or "hostname,windows"
export function parseSources(text) {
  return parseLines(text).map((line) => {
    const parts = line.split(",").map((p) => p.trim());
    const host = parts[0];
    const os = (parts[1] || "").toLowerCase();
    if (!host) throw new Error(`Invalid source line: "${line}"`);
    if (os !== "linux" && os !== "windows") {
      throw new Error(`Source "${host}" needs an OS of "linux" or "windows" (got "${parts[1] || ""}")`);
    }
    return { host, os };
  });
}

export function parsePorts(text) {
  return parseLines(text).map((line) => {
    const n = parseInt(line, 10);
    if (Number.isNaN(n) || n <= 0 || n > 65535) throw new Error(`Invalid port: "${line}"`);
    return n;
  });
}

export function rowsToCsv(rows) {
  const header = "SourceHost,DestinationHost,Port,Status,Timestamp";
  const lines = rows.map(
    (r) => `${r.source_host},${r.destination},${r.port},${r.status},${r.timestamp}`
  );
  return [header, ...lines].join("\n");
}

export function downloadCsv(csv, filename) {
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
