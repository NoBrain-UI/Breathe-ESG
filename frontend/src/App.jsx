import { useState, useEffect, useCallback } from "react";
import axios from "axios";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Axios instance with auth token
const api = axios.create({ baseURL: API });
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token) config.headers.Authorization = `Token ${token}`;
  return config;
});

// ── Status badge ──────────────────────────────────────────
const StatusBadge = ({ status }) => {
  const colors = {
    PENDING: "bg-yellow-100 text-yellow-800 border border-yellow-300",
    FLAGGED: "bg-red-100 text-red-800 border border-red-300",
    APPROVED: "bg-green-100 text-green-800 border border-green-300",
    REJECTED: "bg-gray-100 text-gray-600 border border-gray-300",
  };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[status] || "bg-gray-100 text-gray-600"}`}>
      {status}
    </span>
  );
};

const ScopeBadge = ({ scope }) => {
  const colors = { S1: "bg-orange-100 text-orange-800", S2: "bg-blue-100 text-blue-800", S3: "bg-purple-100 text-purple-800" };
  const labels = { S1: "Scope 1", S2: "Scope 2", S3: "Scope 3" };
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-semibold ${colors[scope] || "bg-gray-100"}`}>
      {labels[scope] || scope}
    </span>
  );
};

// ── Login ─────────────────────────────────────────────────
function Login({ onLogin }) {
  const [creds, setCreds] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await axios.post(`${API}/api/auth/token/`, creds);
      localStorage.setItem("token", res.data.token);
      onLogin();
    } catch {
      setError("Invalid credentials");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-8 w-96">
        <div className="mb-6">
          <div className="text-2xl font-bold text-gray-900">Breathe ESG</div>
          <div className="text-sm text-gray-500 mt-1">Analyst Review Dashboard</div>
        </div>
        <form onSubmit={submit} className="space-y-4">
          <input
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            placeholder="Username"
            value={creds.username}
            onChange={(e) => setCreds({ ...creds, username: e.target.value })}
          />
          <input
            type="password"
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
            placeholder="Password"
            value={creds.password}
            onChange={(e) => setCreds({ ...creds, password: e.target.value })}
          />
          {error && <div className="text-red-600 text-sm">{error}</div>}
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-emerald-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Upload Panel ───────────────────────────────────────────
function UploadPanel({ tenantId, onUploaded }) {
  const [uploading, setUploading] = useState(null);
  const [results, setResults] = useState([]);

  const upload = async (sourceType, file) => {
    setUploading(sourceType);
    const form = new FormData();
    form.append("file", file);
    form.append("tenant_id", tenantId);
    try {
      const res = await api.post(`/api/ingest/${sourceType.toLowerCase()}/`, form);
      setResults((r) => [
        { sourceType, ...res.data, ok: true, ts: new Date().toLocaleTimeString() },
        ...r,
      ]);
      onUploaded();
    } catch (e) {
      setResults((r) => [
        { sourceType, error: e.response?.data?.error || "Upload failed", ok: false, ts: new Date().toLocaleTimeString() },
        ...r,
      ]);
    } finally {
      setUploading(null);
    }
  };

  const sources = [
    { id: "SAP", label: "SAP Fuel & Procurement", hint: "ME2N / MB51 CSV export", color: "blue" },
    { id: "UTILITY", label: "Utility Electricity", hint: "Green Button CSV", color: "amber" },
    { id: "TRAVEL", label: "Corporate Travel", hint: "Navan / Concur CSV export", color: "purple" },
  ];

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <h2 className="font-semibold text-gray-900 mb-1">Upload Data</h2>
      <p className="text-xs text-gray-500 mb-4">Upload one file per source type. Each upload creates a new ingestion job.</p>
      <div className="grid grid-cols-3 gap-4">
        {sources.map(({ id, label, hint, color }) => (
          <label
            key={id}
            className={`cursor-pointer border-2 border-dashed rounded-lg p-4 text-center hover:border-${color}-400 hover:bg-${color}-50 transition-colors ${uploading === id ? "opacity-60 pointer-events-none" : ""}`}
          >
            <div className={`text-xs font-semibold text-${color}-700 mb-1`}>{label}</div>
            <div className="text-xs text-gray-400 mb-3">{hint}</div>
            <div className="text-xs text-gray-500 underline">
              {uploading === id ? "Uploading…" : "Click to upload CSV"}
            </div>
            <input
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => e.target.files[0] && upload(id, e.target.files[0])}
            />
          </label>
        ))}
      </div>
      {results.length > 0 && (
        <div className="mt-4 space-y-1">
          {results.slice(0, 5).map((r, i) => (
            <div key={i} className={`text-xs px-3 py-1.5 rounded ${r.ok ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"}`}>
              {r.ts} — {r.sourceType}: {r.ok ? `✓ ${r.rows_ingested} rows ingested, ${r.rows_failed} failed` : `✗ ${r.error}`}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Summary Cards ──────────────────────────────────────────
function SummaryCards({ summary }) {
  if (!summary) return null;
  const cards = [
    { label: "Total Records", value: summary.total_records, color: "gray" },
    { label: "Pending Review", value: summary.pending_review, color: "yellow" },
    { label: "Flagged", value: summary.flagged, color: "red" },
    { label: "Approved", value: summary.approved, color: "green" },
    { label: "Suspicious", value: summary.suspicious, color: "orange" },
    { label: "Total CO₂e (kg)", value: parseFloat(summary.total_co2e_kg || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 }), color: "emerald" },
  ];

  return (
    <div className="grid grid-cols-6 gap-3">
      {cards.map(({ label, value, color }) => (
        <div key={label} className="bg-white rounded-xl border border-gray-200 p-4">
          <div className={`text-2xl font-bold text-${color}-600`}>{value}</div>
          <div className="text-xs text-gray-500 mt-1">{label}</div>
        </div>
      ))}
    </div>
  );
}

// ── Record Detail Drawer ───────────────────────────────────
function RecordDrawer({ record, onClose, onUpdate }) {
  const [note, setNote] = useState(record?.review_note || "");
  const [saving, setSaving] = useState(false);

  useEffect(() => { setNote(record?.review_note || ""); }, [record]);

  if (!record) return null;

  const setStatus = async (newStatus) => {
    setSaving(true);
    try {
      const res = await api.patch(`/api/records/${record.id}/review/`, {
        review_status: newStatus,
        review_note: note,
      });
      onUpdate(res.data);
      onClose();
    } catch (e) {
      alert("Failed to update: " + (e.response?.data?.error || e.message));
    } finally {
      setSaving(false);
    }
  };

  const Field = ({ label, value }) =>
    value ? (
      <div className="flex gap-2 text-sm">
        <span className="text-gray-500 w-36 shrink-0">{label}</span>
        <span className="text-gray-900 break-all">{String(value)}</span>
      </div>
    ) : null;

  return (
    <div className="fixed inset-0 z-50 flex">
      <div className="flex-1 bg-black/30" onClick={onClose} />
      <div className="w-[480px] bg-white shadow-xl overflow-y-auto">
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
          <div>
            <div className="font-semibold text-gray-900">{record.activity_description}</div>
            <div className="flex gap-2 mt-1">
              <StatusBadge status={record.review_status} />
              <ScopeBadge scope={record.scope} />
              {record.is_suspicious && (
                <span className="px-2 py-0.5 rounded text-xs font-medium bg-orange-100 text-orange-800 border border-orange-300">
                  ⚠ Suspicious
                </span>
              )}
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-xl">×</button>
        </div>

        <div className="p-6 space-y-5">
          {record.is_suspicious && record.suspicion_reasons?.length > 0 && (
            <div className="bg-orange-50 border border-orange-200 rounded-lg p-3">
              <div className="text-xs font-semibold text-orange-800 mb-1">⚠ Flagged by system:</div>
              {record.suspicion_reasons.map((r, i) => (
                <div key={i} className="text-xs text-orange-700">• {r}</div>
              ))}
            </div>
          )}

          <div className="space-y-2">
            <Field label="Source" value={record.source_type} />
            <Field label="Date" value={record.activity_date} />
            <Field label="Quantity" value={`${record.quantity_original} ${record.unit_original}`} />
            <Field label="Normalized" value={record.quantity_normalized ? `${record.quantity_normalized} ${record.unit_normalized}` : null} />
            <Field label="CO₂e" value={record.co2e_kg ? `${parseFloat(record.co2e_kg).toLocaleString()} kg` : null} />
            <Field label="Emission Factor" value={record.emission_factor_used} />
          </div>

          {record.source_type === "SAP" && (
            <div className="border-t pt-4 space-y-2">
              <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide">SAP Data</div>
              <Field label="Plant (WERKS)" value={record.sap_plant_code} />
              <Field label="Material Group" value={record.sap_material_group} />
              <Field label="Vendor (LIFNR)" value={record.sap_vendor} />
              <Field label="PO Number" value={record.sap_po_number} />
            </div>
          )}

          {record.source_type === "UTILITY" && (
            <div className="border-t pt-4 space-y-2">
              <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Utility Data</div>
              <Field label="Meter ID" value={record.utility_meter_id} />
              <Field label="Tariff" value={record.utility_tariff} />
              <Field label="Billing Period" value={`${record.utility_billing_start} → ${record.utility_billing_end}`} />
            </div>
          )}

          {record.source_type === "TRAVEL" && (
            <div className="border-t pt-4 space-y-2">
              <div className="text-xs font-semibold text-gray-600 uppercase tracking-wide">Travel Data</div>
              <Field label="Segment" value={record.travel_segment_type} />
              <Field label="Route" value={record.travel_origin && `${record.travel_origin} → ${record.travel_destination}`} />
              <Field label="Distance" value={record.travel_distance_km ? `${record.travel_distance_km} km` : null} />
              <Field label="Traveler" value={record.travel_traveler_email} />
            </div>
          )}

          <div className="border-t pt-4">
            <label className="text-xs font-semibold text-gray-600 uppercase tracking-wide block mb-2">
              Analyst Note
            </label>
            <textarea
              className="w-full border border-gray-300 rounded-lg p-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-emerald-500"
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Optional note for audit trail…"
              disabled={record.locked}
            />
          </div>

          {!record.locked && (
            <div className="flex gap-2">
              <button
                onClick={() => setStatus("APPROVED")}
                disabled={saving}
                className="flex-1 bg-green-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-green-700 disabled:opacity-50"
              >
                Approve
              </button>
              <button
                onClick={() => setStatus("FLAGGED")}
                disabled={saving}
                className="flex-1 bg-orange-500 text-white rounded-lg py-2 text-sm font-medium hover:bg-orange-600 disabled:opacity-50"
              >
                Flag
              </button>
              <button
                onClick={() => setStatus("REJECTED")}
                disabled={saving}
                className="flex-1 bg-gray-200 text-gray-700 rounded-lg py-2 text-sm font-medium hover:bg-gray-300 disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          )}

          {record.locked && (
            <div className="bg-gray-50 border border-gray-200 rounded-lg p-3 text-xs text-gray-600">
              🔒 Locked for audit on {new Date(record.locked_at).toLocaleDateString()}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Records Table ──────────────────────────────────────────
function RecordsTable({ records, onSelect, loading }) {
  if (loading) return <div className="text-center py-16 text-gray-400">Loading records…</div>;
  if (!records.length) return <div className="text-center py-16 text-gray-400">No records match the current filters.</div>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs text-gray-500 uppercase tracking-wide">
            <th className="py-3 px-4">Date</th>
            <th className="py-3 px-4">Source</th>
            <th className="py-3 px-4">Description</th>
            <th className="py-3 px-4">Scope</th>
            <th className="py-3 px-4 text-right">Quantity</th>
            <th className="py-3 px-4 text-right">CO₂e (kg)</th>
            <th className="py-3 px-4">Status</th>
            <th className="py-3 px-4"></th>
          </tr>
        </thead>
        <tbody>
          {records.map((r) => (
            <tr
              key={r.id}
              className={`border-b border-gray-100 hover:bg-gray-50 cursor-pointer ${r.is_suspicious ? "bg-orange-50/40" : ""}`}
              onClick={() => onSelect(r)}
            >
              <td className="py-3 px-4 text-gray-600">{r.activity_date}</td>
              <td className="py-3 px-4">
                <span className="text-xs font-mono text-gray-700">{r.source_type}</span>
              </td>
              <td className="py-3 px-4 max-w-xs truncate text-gray-800">
                {r.is_suspicious && <span className="text-orange-500 mr-1">⚠</span>}
                {r.activity_description}
              </td>
              <td className="py-3 px-4"><ScopeBadge scope={r.scope} /></td>
              <td className="py-3 px-4 text-right text-gray-700">
                {parseFloat(r.quantity_original).toLocaleString("en-IN")} {r.unit_original}
              </td>
              <td className="py-3 px-4 text-right text-gray-700">
                {r.co2e_kg ? parseFloat(r.co2e_kg).toLocaleString("en-IN", { maximumFractionDigits: 1 }) : "—"}
              </td>
              <td className="py-3 px-4"><StatusBadge status={r.review_status} /></td>
              <td className="py-3 px-4 text-right">
                <button className="text-xs text-blue-600 hover:underline">Review →</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main Dashboard ─────────────────────────────────────────
function Dashboard({ tenantId }) {
  const [records, setRecords] = useState([]);
  const [summary, setSummary] = useState(null);
  const [selectedRecord, setSelectedRecord] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    source_type: "", scope: "", review_status: "", suspicious: "",
  });
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  const fetchRecords = useCallback(async () => {
    setLoading(true);
    try {
      const params = { tenant_id: tenantId, page, ...Object.fromEntries(
        Object.entries(filters).filter(([, v]) => v)
      )};
      const res = await api.get("/api/records/", { params });
      setRecords(res.data.results || res.data);
      if (res.data.count) setTotalPages(Math.ceil(res.data.count / 50));
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [tenantId, filters, page]);

  const fetchSummary = useCallback(async () => {
    try {
      const res = await api.get("/api/records/summary/", { params: { tenant_id: tenantId } });
      setSummary(res.data);
    } catch (e) { console.error(e); }
  }, [tenantId]);

  useEffect(() => { fetchRecords(); fetchSummary(); }, [fetchRecords, fetchSummary]);

  const handleRecordUpdate = (updated) => {
    setRecords((rs) => rs.map((r) => (r.id === updated.id ? updated : r)));
    fetchSummary();
  };

  const FilterSelect = ({ name, label, options }) => (
    <select
      className="border border-gray-300 rounded-lg px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500"
      value={filters[name]}
      onChange={(e) => { setFilters({ ...filters, [name]: e.target.value }); setPage(1); }}
    >
      <option value="">{label}</option>
      {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
    </select>
  );

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          <span className="text-lg font-bold text-gray-900">Breathe ESG</span>
          <span className="text-gray-400 mx-2">·</span>
          <span className="text-sm text-gray-500">Analyst Review Dashboard</span>
        </div>
        <button
          onClick={() => { localStorage.removeItem("token"); window.location.reload(); }}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Sign out
        </button>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Summary cards */}
        <SummaryCards summary={summary} />

        {/* Upload */}
        <UploadPanel tenantId={tenantId} onUploaded={() => { fetchRecords(); fetchSummary(); }} />

        {/* Filters + Table */}
        <div className="bg-white rounded-xl border border-gray-200">
          <div className="px-6 py-4 border-b border-gray-200 flex gap-3 flex-wrap items-center">
            <span className="text-sm font-semibold text-gray-700">Records</span>
            <div className="flex-1" />
            <FilterSelect name="source_type" label="All sources" options={[
              ["SAP", "SAP"], ["UTILITY", "Utility"], ["TRAVEL", "Travel"]
            ]} />
            <FilterSelect name="scope" label="All scopes" options={[
              ["S1", "Scope 1"], ["S2", "Scope 2"], ["S3", "Scope 3"]
            ]} />
            <FilterSelect name="review_status" label="All statuses" options={[
              ["PENDING", "Pending"], ["FLAGGED", "Flagged"], ["APPROVED", "Approved"], ["REJECTED", "Rejected"]
            ]} />
            <FilterSelect name="suspicious" label="All" options={[
              ["true", "Suspicious only"]
            ]} />
          </div>

          <RecordsTable records={records} onSelect={setSelectedRecord} loading={loading} />

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="px-6 py-4 border-t border-gray-200 flex gap-2 justify-end">
              <button disabled={page === 1} onClick={() => setPage(page - 1)}
                className="px-3 py-1 text-sm border border-gray-300 rounded disabled:opacity-40">← Prev</button>
              <span className="px-3 py-1 text-sm text-gray-600">{page} / {totalPages}</span>
              <button disabled={page === totalPages} onClick={() => setPage(page + 1)}
                className="px-3 py-1 text-sm border border-gray-300 rounded disabled:opacity-40">Next →</button>
            </div>
          )}
        </div>
      </div>

      {selectedRecord && (
        <RecordDrawer
          record={selectedRecord}
          onClose={() => setSelectedRecord(null)}
          onUpdate={handleRecordUpdate}
        />
      )}
    </div>
  );
}

// ── Root ───────────────────────────────────────────────────
export default function App() {
  const [authed, setAuthed] = useState(!!localStorage.getItem("token"));
  // In a real app, tenant would be selected after login or come from user profile
  const TENANT_ID = import.meta.env.VITE_TENANT_ID || "";

  if (!authed) return <Login onLogin={() => setAuthed(true)} />;
  return <Dashboard tenantId={TENANT_ID} />;
}