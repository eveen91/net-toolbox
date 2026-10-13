import React, { useEffect, useRef, useState } from "react";
import DeviceFaceplate from "./DeviceFaceplate.jsx";

export function fitScale(availableWidth, availableHeight, contentWidth, contentHeight) {
  if (contentWidth <= 0 || contentHeight <= 0) return 1;
  return Math.max(0.01, Math.min(1, availableWidth / contentWidth, availableHeight / contentHeight));
}

export default function DeviceCanvas(props) {
  const container = useRef(null);
  const content = useRef(null);
  const fullscreen = useRef(null);
  const [dimensions, setDimensions] = useState({ width: 1, height: 1, availableWidth: 1, availableHeight: 1, minTarget: 58 });
  const [zoom, setZoom] = useState(null);
  const [fullscreenError, setFullscreenError] = useState("");
  useEffect(() => {
    const measure = () => {
      if (!container.current || !content.current) return;
      const sockets = [...content.current.querySelectorAll(".sv-socket")];
      setDimensions({ width: content.current.scrollWidth, height: content.current.scrollHeight,
        minTarget: sockets.length ? Math.min(...sockets.map((socket) => Math.min(socket.offsetWidth, socket.offsetHeight))) : 58,
        availableWidth: Math.max(1, container.current.clientWidth - 24), availableHeight: Math.max(1, container.current.clientHeight - 24) });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(container.current);
    observer.observe(content.current);
    return () => observer.disconnect();
  }, [props.device.id, props.device.version]);
  const fit = fitScale(dimensions.availableWidth, dimensions.availableHeight, dimensions.width, dimensions.height);
  const scale = zoom ?? fit;
  const targetsTooSmall = scale * dimensions.minTarget < 24;
  const enterFullscreen = async () => {
    setFullscreenError("");
    try {
      if (document.fullscreenElement === fullscreen.current) await document.exitFullscreen();
      else if (fullscreen.current.requestFullscreen) await fullscreen.current.requestFullscreen();
      else setFullscreenError("Fullscreen is unavailable in this browser. Use Fit or Port table.");
    } catch { setFullscreenError("Fullscreen could not open. Use Fit or Port table."); }
  };
  return <section className="sv-canvas-shell" ref={fullscreen} aria-label="Physical port panel">
    <div className="sv-canvas-toolbar">
      <button className="tool-btn tool-btn-ghost" aria-pressed={zoom === null} onClick={() => setZoom(null)}>Fit</button>
      <button className="tool-btn tool-btn-ghost" aria-label="Zoom out" onClick={() => setZoom(Math.max(0.1, scale - 0.1))}>−</button>
      <span className="sv-zoom-value" aria-live="polite">{Math.round(scale * 100)}%</span>
      <button className="tool-btn tool-btn-ghost" aria-label="Zoom in" onClick={() => setZoom(Math.min(2, scale + 0.1))}>+</button>
      <button className="tool-btn tool-btn-ghost" onClick={enterFullscreen}>Fullscreen / exit</button>
    </div>
    <p className="sv-documentation-note">Saved documentation · No live link status</p>
    <div className="sv-canvas-viewport" ref={container} tabIndex={0} aria-label="Zoomable device canvas">
      <div className="sv-canvas-size" style={{ width: dimensions.width * scale, height: dimensions.height * scale }}>
        <div className="sv-canvas-content" ref={content} style={{ transform: `scale(${scale})` }}>
          <DeviceFaceplate {...props} disabled={props.disabled || targetsTooSmall} />
        </div>
      </div>
    </div>
    {targetsTooSmall && <p className="tool-hint">This is an overview. Zoom in or use Port table to select a port.</p>}
    {fullscreenError && <p className="tool-error" role="alert">{fullscreenError}</p>}
  </section>;
}
