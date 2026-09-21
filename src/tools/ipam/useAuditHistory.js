import { useCallback, useEffect, useMemo, useState } from "react";
import { exportAuditLog, queryAuditLog } from "./api.js";

export default function useAuditHistory({
  subnetId,
  addressId,
  pageSize = 25,
  adminExport = false,
} = {}) {
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [eventType, setEventType] = useState("");
  const [page, setPage] = useState(1);
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const query = useMemo(() => ({
    subnetId,
    addressId,
    startDate,
    endDate,
    changeTypes: eventType ? [eventType] : [],
    limit: pageSize,
    offset: (page - 1) * pageSize,
  }), [addressId, endDate, eventType, page, pageSize, startDate, subnetId]);

  useEffect(() => {
    setPage(1);
  }, [addressId, endDate, eventType, startDate, subnetId]);

  const refresh = useCallback(() => setRefreshKey((key) => key + 1), []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    queryAuditLog(query)
      .then((result) => {
        if (!active) return;
        setEntries(result.entries || []);
        setTotal(result.total || 0);
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [query, refreshKey]);

  const exportCsv = useCallback(async (filename = "ipam-audit.csv") => {
    setExporting(true);
    setError(null);
    try {
      const blob = await exportAuditLog({ ...query, limit: undefined, offset: undefined }, adminExport);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setExporting(false);
    }
  }, [adminExport, query]);

  return {
    entries,
    total,
    loading,
    error,
    exporting,
    page,
    pageSize,
    startDate,
    endDate,
    eventType,
    setPage,
    setStartDate,
    setEndDate,
    setEventType,
    refresh,
    exportCsv,
  };
}
