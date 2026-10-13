// Remove only the moved host's blocks, preserving other unsaved input verbatim.
export function removeMovedHost(text, host) {
  let skip = false;
  return text.split(/(?<=\n)/).filter(line => {
    if (line.trim().startsWith("@")) skip = line.trim().slice(1).trim() === host;
    return !skip;
  }).join("");
}
