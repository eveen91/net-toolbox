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
    const n = Number(line);
    if (!/^[0-9]+$/.test(line) || !Number.isSafeInteger(n) || n <= 0 || n > 65535) throw new Error(`Invalid port: "${line}"`);
    return n;
  });
}

export const RUN_LIMITS = { sources: 16, destinations: 64, ports: 32, combinations: 1024 };

export function validateWorkload(sources, destinations, ports) {
  const sizes = { sources: sources.length, destinations: destinations.length, ports: ports.length };
  for (const [name, count] of Object.entries(sizes)) {
    if (count < 1) throw new Error(`Enter at least one ${name === "sources" ? "source" : name === "destinations" ? "destination" : "port"}.`);
    if (count > RUN_LIMITS[name]) throw new Error(`Use at most ${RUN_LIMITS[name]} ${name} per run.`);
  }
  const combinations = sizes.sources * sizes.destinations * sizes.ports;
  if (combinations > RUN_LIMITS.combinations) throw new Error(`This run has ${combinations} combinations. Reduce sources, destinations or ports to at most ${RUN_LIMITS.combinations} combinations.`);
  return combinations;
}

export function validateSettings({ connectTimeout, sshPort, winrmPort, winrmScheme, winrmTransport }) {
  for (const [name, value, max] of [["Connect timeout", connectTimeout, 60], ["SSH port", sshPort, 65535], ["WinRM port", winrmPort, 65535]]) {
    if (!Number.isInteger(value) || value < 1 || value > max) throw new Error(`${name} must be a whole number from 1 to ${max}.`);
  }
  if (winrmTransport === "basic" && winrmScheme !== "https") throw new Error("Basic WinRM authentication requires HTTPS. Select HTTPS in Advanced settings.");
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
