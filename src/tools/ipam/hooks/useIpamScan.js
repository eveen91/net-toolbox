import { useCallback, useEffect, useRef, useState } from "react";
import {
  autodiscoverStreamUrl,
  getActiveAutodiscoverJob,
  getAutodiscoverJob,
  getSubnet,
  listSubnetScans,
  startAutodiscoverJob,
} from "../api.js";

export function scanAddressLabel(address) {
  if (address.status === "pending") return "pending";
  if (address.status === "in_progress") return "scanning…";
  return address.alive ? "used" : "free";
}

export function openAutodiscoverStream(subnetId, jobId) {
  return new EventSource(autodiscoverStreamUrl(subnetId, jobId), { withCredentials: true });
}

export function useIpamScan(subnetId, onDetailUpdated, onScanCompleted) {
  const [confirmingScan, setConfirmingScan] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [scanError, setScanError] = useState(null);
  const [scanResult, setScanResult] = useState(null);
  const [lastScan, setLastScan] = useState(null);
  const [scanProgress, setScanProgress] = useState(null);
  const eventSourceRef = useRef(null);
  const recoveryTimerRef = useRef(null);

  useEffect(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    clearTimeout(recoveryTimerRef.current);
    setConfirmingScan(false);
    setScanning(false);
    setScanError(null);
    setScanResult(null);
    setLastScan(null);
    setScanProgress(null);
    listSubnetScans(subnetId)
      .then((scans) => setLastScan(scans.length > 0 ? scans[0] : null))
      .catch(() => {});
    return () => {
      eventSourceRef.current?.close();
      clearTimeout(recoveryTimerRef.current);
    };
  }, [subnetId]);

  const runAutodiscover = useCallback(async () => {
    setScanError(null);
    setScanning(true);
    setScanProgress({ completed: 0, total: 0 });
    let settled = false;

    const finish = async (payload) => {
      if (settled) return;
      settled = true;
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
      clearTimeout(recoveryTimerRef.current);
      setScanning(false);
      setConfirmingScan(false);
      setScanProgress(null);
      if (payload.status !== "done") {
        setScanError(payload.error || (payload.status === "cancelled" ? "Scan cancelled" : "Scan failed"));
        return;
      }
      setScanResult(payload.result);
      try {
        const [scans, updatedSubnet] = await Promise.all([
          listSubnetScans(subnetId),
          getSubnet(subnetId),
        ]);
        setLastScan(scans.length > 0 ? scans[0] : null);
        onDetailUpdated(updatedSubnet);
        onScanCompleted?.();
      } catch (error) {
        setScanError(`Scan completed, but refreshing IPAM data failed: ${error.message}`);
      }
    };

    const recover = async (jobId) => {
      if (settled) return;
      try {
        const payload = await getAutodiscoverJob(subnetId, jobId);
        setScanProgress({ completed: payload.completed, total: payload.total });
        if (payload.status !== "running") {
          await finish(payload);
          return;
        }
        recoveryTimerRef.current = setTimeout(() => recover(jobId), 1000);
      } catch (error) {
        if (settled) return;
        settled = true;
        setScanError(`Unable to read scan status: ${error.message}`);
        setScanning(false);
        setConfirmingScan(false);
        setScanProgress(null);
      }
    };

    try {
      const { jobId } = await startAutodiscoverJob(subnetId);
      const eventSource = openAutodiscoverStream(subnetId, jobId);
      eventSourceRef.current = eventSource;
      eventSource.onmessage = async (event) => {
        let payload;
        try {
          payload = JSON.parse(event.data);
        } catch {
          eventSource.close();
          eventSourceRef.current = null;
          await recover(jobId);
          return;
        }
        setScanProgress({ completed: payload.completed, total: payload.total });
        if (payload.status !== "running") await finish(payload);
      };
      eventSource.onerror = () => {
        if (settled) return;
        eventSource.close();
        eventSourceRef.current = null;
        recover(jobId);
      };
    } catch (error) {
      setScanError(error.message);
      setScanning(false);
      setConfirmingScan(false);
      setScanProgress(null);
    }
  }, [onDetailUpdated, onScanCompleted, subnetId]);

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
            const eventSource = openAutodiscoverStream(subnetId, result.jobId);
            eventSourceRef.current = eventSource;
            eventSource.onmessage = (event) => {
              const payload = JSON.parse(event.data);
              setAddresses(payload.addresses || []);
              if (payload.status === "done" || payload.status === "error" || payload.status === "cancelled") {
                eventSource.close();
                eventSourceRef.current = null;
                setScanning(false);
              }
            };
            eventSource.onerror = () => {
              eventSource.close();
              eventSourceRef.current = null;
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
