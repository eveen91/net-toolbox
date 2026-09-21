import { useCallback, useEffect, useRef, useState } from "react";
import {
  autodiscoverStreamUrl,
  getActiveAutodiscoverJob,
  getSubnet,
  listSubnetScans,
  startAutodiscoverJob,
} from "../api.js";

export function scanAddressLabel(address) {
  if (address.status === "pending") return "pending";
  if (address.status === "in_progress") return "scanning…";
  return address.alive ? "used" : "free";
}

export function useIpamScan(subnetId, onDetailUpdated) {
  const [confirmingScan, setConfirmingScan] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [lastScan, setLastScan] = useState(null);
  const [scanProgress, setScanProgress] = useState(null);
  const eventSourceRef = useRef(null);

  useEffect(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    setConfirmingScan(false);
    setScanning(false);
    setScanError(null);
    setScanResult(null);
    setLastScan(null);
    setScanProgress(null);
    listSubnetScans(subnetId)
      .then((scans) => setLastScan(scans.length > 0 ? scans[0] : null))
      .catch(() => {});
    return () => eventSourceRef.current?.close();
  }, [subnetId]);

  const runAutodiscover = useCallback(async () => {
    setScanError(null);
    setScanning(true);
    setScanProgress({ completed: 0, total: 0 });
    try {
      const { jobId } = await startAutodiscoverJob(subnetId);
      const eventSource = new EventSource(autodiscoverStreamUrl(subnetId, jobId));
      eventSourceRef.current = eventSource;
      let settled = false;
      eventSource.onmessage = async (event) => {
        const payload = JSON.parse(event.data);
        setScanProgress({ completed: payload.completed, total: payload.total });
        if (payload.status === "done") {
          settled = true;
          setScanResult(payload.result);
          eventSource.close();
          eventSourceRef.current = null;
          try {
            const scans = await listSubnetScans(subnetId);
            setLastScan(scans.length > 0 ? scans[0] : null);
          } catch {}
          onDetailUpdated(await getSubnet(subnetId));
          setScanning(false);
          setConfirmingScan(false);
          setScanProgress(null);
        } else if (payload.status === "error") {
          settled = true;
          setScanError(payload.error || "Scan failed");
          eventSource.close();
          eventSourceRef.current = null;
          setScanning(false);
          setConfirmingScan(false);
          setScanProgress(null);
        }
      };
      eventSource.onerror = () => {
        if (settled) return;
        setScanError("Lost connection to the scan progress stream.");
        eventSource.close();
        eventSourceRef.current = null;
        setScanning(false);
        setConfirmingScan(false);
        setScanProgress(null);
      };
    } catch (error) {
      setScanError(error.message);
      setScanning(false);
      setConfirmingScan(false);
      setScanProgress(null);
    }
  }, [onDetailUpdated, subnetId]);

  return {
    confirmingScan, scanning, scanError, scanResult, lastScan, scanProgress,
    setConfirmingScan, setScanResult, runAutodiscover,
  };
}

export function useActiveIpamScan(subnetId) {
  const [scanning, setScanning] = useState(false);
  const [addresses, setAddresses] = useState([]);
  const eventSourceRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const checkActive = async () => {
      try {
        const result = await getActiveAutodiscoverJob(subnetId);
        if (cancelled) return;
        if (result.jobId != null) {
          if (eventSourceRef.current == null) {
            setScanning(true);
            const eventSource = new EventSource(autodiscoverStreamUrl(subnetId, result.jobId));
            eventSourceRef.current = eventSource;
            eventSource.onmessage = (event) => {
              const payload = JSON.parse(event.data);
              setAddresses(payload.addresses || []);
              if (payload.status === "done" || payload.status === "error") {
                eventSource.close();
                eventSourceRef.current = null;
                setScanning(false);
              }
            };
          }
        } else {
          setScanning(false);
        }
      } catch {
        return;
      }
    };

    checkActive();
    const intervalId = setInterval(checkActive, 5000);
    return () => {
      cancelled = true;
      clearInterval(intervalId);
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
  }, [subnetId]);

  return { scanning, addresses };
}
