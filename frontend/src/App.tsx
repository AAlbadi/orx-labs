import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  Users, Mail, Calendar, MessageSquare, Upload, Sparkles,
  RefreshCw, Play, Check, ExternalLink,
  BookOpen, ChevronRight, TrendingUp, AlertCircle, FileText, Send,
  Search, X, CheckCircle2, Loader2, ArrowRight, Zap, Activity
} from 'lucide-react';

const GithubIcon = (props: React.SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
  </svg>
);

const LinkedinIcon = (props: React.SVGProps<SVGSVGElement>) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" {...props}>
    <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z" />
    <rect x="2" y="9" width="4" height="12" />
    <circle cx="4" cy="4" r="2" />
  </svg>
);

const API_BASE = 'http://localhost:8000/api/v1';

interface Lead {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  company: string;
  role: string;
  linkedin_url: string;
  github_username: string;
  academic_profile: string;
  status: string;
  harvested_context: any;
  personalized_subject: string;
  personalized_copy: string;
  selected_variant: string;
  created_at: string;
}

interface Analytics {
  summary: {
    total_leads: number;
    enriched_leads: number;
    contacted_leads: number;
    replied_leads: number;
    meetings_booked: number;
    reply_rate: number;
    booking_rate: number;
  };
  funnel: {
    Ingested: number;
    Enriched: number;
    Contacted: number;
    Replied: number;
    Booked: number;
  };
  recent_logs: any[];
  meetings: any[];
}

type ToastType = 'success' | 'error' | 'info' | 'loading';

interface Toast {
  id: string;
  type: ToastType;
  message: string;
  sub?: string;
}

// ─── Toast Component ───────────────────────────────────────────────────────────
function ToastContainer({ toasts, dismiss }: { toasts: Toast[]; dismiss: (id: string) => void }) {
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2.5 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-start gap-3 px-4 py-3.5 rounded-2xl border shadow-2xl max-w-sm w-full animate-slide-up
            ${t.type === 'success' ? 'bg-emerald-950/95 border-emerald-800 text-emerald-100' : ''}
            ${t.type === 'error' ? 'bg-red-950/95 border-red-800 text-red-100' : ''}
            ${t.type === 'info' ? 'bg-zinc-900/95 border-zinc-700 text-zinc-100' : ''}
            ${t.type === 'loading' ? 'bg-violet-950/95 border-violet-800 text-violet-100' : ''}
          `}
        >
          <div className="mt-0.5 shrink-0">
            {t.type === 'success' && <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
            {t.type === 'error' && <AlertCircle className="h-4 w-4 text-red-400" />}
            {t.type === 'info' && <Activity className="h-4 w-4 text-zinc-400" />}
            {t.type === 'loading' && <Loader2 className="h-4 w-4 text-violet-400 animate-spin" />}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold">{t.message}</p>
            {t.sub && <p className="text-xs opacity-70 mt-0.5">{t.sub}</p>}
          </div>
          <button onClick={() => dismiss(t.id)} className="shrink-0 text-current opacity-40 hover:opacity-80 transition-opacity ml-1">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [chatHistory, setChatHistory] = useState<any[]>([]);
  const [replyMessage, setReplyMessage] = useState('');
  const [activeTab, setActiveTab] = useState<'dashboard' | 'leads' | 'negotiator'>('dashboard');
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [ingestMode, setIngestMode] = useState<'csv' | 'search'>('csv');
  const [searchQuery, setSearchQuery] = useState('');
  const [toasts, setToasts] = useState<Toast[]>([]);
  const toastCounter = useRef(0);

  // ── Toast helpers ──
  const addToast = useCallback((type: ToastType, message: string, sub?: string, duration = 5000): string => {
    const id = `toast-${++toastCounter.current}`;
    setToasts(prev => [...prev, { id, type, message, sub }]);
    if (type !== 'loading') {
      setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), duration);
    }
    return id;
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const updateToast = useCallback((id: string, type: ToastType, message: string, sub?: string) => {
    setToasts(prev => prev.map(t => t.id === id ? { ...t, type, message, sub } : t));
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 5000);
  }, []);

  // ── Data Fetching ──
  const fetchData = useCallback(async () => {
    try {
      const [leadsRes, analyticsRes] = await Promise.all([
        fetch(`${API_BASE}/leads/`),
        fetch(`${API_BASE}/analytics/dashboard`)
      ]);
      const leadsData = await leadsRes.json();
      const analyticsData = await analyticsRes.json();
      setLeads(leadsData);
      setAnalytics(analyticsData);
    } catch (err) {
      console.error('Failed to fetch data from API', err);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 8000);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => {
    if (selectedLead) fetchChatHistory(selectedLead.id);
  }, [selectedLead]);

  const fetchChatHistory = async (leadId: number) => {
    try {
      const res = await fetch(`${API_BASE}/leads/${leadId}/negotiation`);
      const data = await res.json();
      setChatHistory(data.history || []);
    } catch (err) {
      console.error('Failed to fetch chat history', err);
    }
  };

  // ── Actions ──
  const handleEnrich = async (leadId: number) => {
    setActionLoading(`enrich-${leadId}`);
    const toastId = addToast('loading', 'Running Context Harvester…', 'Scraping LinkedIn, GitHub & arXiv');
    try {
      await fetch(`${API_BASE}/leads/${leadId}/enrich`, { method: 'POST' });
      updateToast(toastId, 'success', 'Harvest queued!', 'Pipeline running in background');
      fetchData();
    } catch (err) {
      updateToast(toastId, 'error', 'Enrichment failed', 'Check API connectivity');
    } finally {
      setActionLoading(null);
    }
  };

  const handleDispatch = async (leadId: number) => {
    setActionLoading(`dispatch-${leadId}`);
    const toastId = addToast('loading', 'Dispatching email…');
    try {
      await fetch(`${API_BASE}/leads/${leadId}/dispatch`, { method: 'POST' });
      updateToast(toastId, 'success', 'Email dispatched!', 'Lead status updated to CONTACTED');
      fetchData();
    } catch (err) {
      updateToast(toastId, 'error', 'Dispatch failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handleSimulateReply = async () => {
    if (!selectedLead || !replyMessage.trim()) return;
    setActionLoading('chat');
    try {
      await fetch(`${API_BASE}/leads/${selectedLead.id}/simulate-reply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: replyMessage })
      });
      setReplyMessage('');
      fetchChatHistory(selectedLead.id);
      fetchData();
    } catch (err) {
      addToast('error', 'Simulation failed');
    } finally {
      setActionLoading(null);
    }
  };

  const handleCsvUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!csvFile) return;
    setLoading(true);
    const toastId = addToast('loading', 'Uploading CSV…', 'Ingesting leads into the pipeline');
    const formData = new FormData();
    formData.append('file', csvFile);

    try {
      const res = await fetch(`${API_BASE}/leads/upload/csv`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      updateToast(toastId, 'success', `${data.leads_count} leads ingested!`, 'Harvester pipeline queued for all leads');
      setCsvFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      await fetchData();
      setTimeout(() => setActiveTab('leads'), 800);
    } catch (err) {
      updateToast(toastId, 'error', 'Upload failed', 'Check API connectivity');
    } finally {
      setLoading(false);
    }
  };

  const handleWebSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    setLoading(true);
    const query = searchQuery;
    setSearchQuery('');

    const toastId = addToast('loading', `Searching for "${query}"…`, 'ScrapeGraphAI is scanning the web');

    try {
      const res = await fetch(`${API_BASE}/leads/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query })
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      const count = data.leads_count ?? 0;

      if (count === 0) {
        updateToast(toastId, 'info', 'No new leads found', 'They may already be in your CRM or try a different query');
      } else {
        updateToast(toastId, 'success', `${count} leads discovered!`, `"${query}" — Enrichment pipeline started`);
      }

      await fetchData();
      // Navigate to leads tab so user can see the results
      setActiveTab('leads');

    } catch (err: any) {
      updateToast(toastId, 'error', 'Search failed', err.message || 'Check API connectivity');
    } finally {
      setLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const mapping: Record<string, string> = {
      INGESTED: 'bg-zinc-800 text-zinc-400 border-zinc-700',
      HARVESTING: 'bg-blue-950 text-blue-400 border-blue-900 animate-pulse',
      ENRICHED: 'bg-emerald-950 text-emerald-400 border-emerald-900',
      COPYWRITING: 'bg-violet-950 text-violet-400 border-violet-900 animate-pulse',
      DRAFTED: 'bg-indigo-950 text-indigo-300 border-indigo-900',
      CONTACTED: 'bg-amber-950 text-amber-400 border-amber-900',
      REPLIED: 'bg-rose-950 text-rose-400 border-rose-900',
      NEGOTIATING: 'bg-purple-950 text-purple-300 border-purple-900',
      BOOKED: 'bg-teal-950 text-teal-400 border-teal-900 border-2',
      STOPPED: 'bg-red-950 text-red-400 border-red-900',
      HARVEST_FAILED: 'bg-red-950 text-red-400 border-red-800',
      COPY_FAILED: 'bg-orange-950 text-orange-400 border-orange-800',
    };
    return (
      <span className={`px-2.5 py-1 text-xs font-semibold rounded-full border ${mapping[status] || 'bg-zinc-800 text-zinc-400'}`}>
        {status}
      </span>
    );
  };

  const activeLeads = leads.filter(l => ['REPLIED', 'NEGOTIATING', 'BOOKED'].includes(l.status));

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col font-sans">

      {/* Toast Container */}
      <ToastContainer toasts={toasts} dismiss={dismissToast} />

      {/* Premium Header */}
      <header className="border-b border-zinc-900 bg-zinc-950/80 backdrop-blur-md sticky top-0 z-40 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-violet-600 to-indigo-500 flex items-center justify-center shadow-lg shadow-violet-500/20">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-white m-0">ORX Cold-Outreach</h1>
            <p className="text-xs text-zinc-500 m-0">Autonomous Context-Aware Outreach Engine</p>
          </div>
        </div>

        <nav className="flex gap-1">
          {([
            { key: 'dashboard', label: 'Dashboard' },
            { key: 'leads', label: `Leads CRM${leads.length > 0 ? ` (${leads.length})` : ''}` },
            { key: 'negotiator', label: `Negotiator${activeLeads.length > 0 ? ` (${activeLeads.length})` : ''}` },
          ] as const).map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${activeTab === tab.key ? 'bg-zinc-900 text-white border border-zinc-800' : 'text-zinc-400 hover:text-white hover:bg-zinc-900/50'}`}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <button
            onClick={fetchData}
            className="p-2 text-zinc-400 hover:text-white rounded-lg border border-zinc-900 hover:bg-zinc-900 transition-all"
            title="Refresh data"
          >
            <RefreshCw className="h-4 w-4" />
          </button>
          <div className="text-xs text-zinc-500 px-3 py-1.5 rounded-md bg-zinc-900 border border-zinc-800">
            Founder Mode: Active
          </div>
        </div>
      </header>

      {/* Tab Panels */}
      <main className="flex-1 p-6 max-w-7xl w-full mx-auto">

        {/* ─── DASHBOARD ──────────────────────────────────────────── */}
        {activeTab === 'dashboard' && (
          <div className="space-y-6">
            {/* Metric Panel */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {[
                { label: 'Total Leads', value: analytics?.summary.total_leads ?? 0, sub: 'From CSV and AI search', icon: <Users className="h-4 w-4 text-violet-400" />, color: 'violet' },
                { label: 'Enriched Profiles', value: analytics?.summary.enriched_leads ?? 0, sub: 'Context graph harvested', icon: <Sparkles className="h-4 w-4 text-emerald-400" />, color: 'emerald' },
                { label: 'Reply Rate', value: `${analytics?.summary.reply_rate ?? 0}%`, sub: `${analytics?.summary.replied_leads ?? 0} replies / ${analytics?.summary.contacted_leads ?? 0} sent`, icon: <TrendingUp className="h-4 w-4 text-amber-400" />, color: 'amber' },
                { label: 'Meetings Booked', value: analytics?.summary.meetings_booked ?? 0, sub: 'Autonomously scheduled', icon: <Calendar className="h-4 w-4 text-teal-400" />, color: 'teal' },
              ].map(m => (
                <div key={m.label} className="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-900 flex flex-col justify-between hover:border-zinc-800 transition-all">
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-medium text-zinc-400">{m.label}</span>
                    <div className="p-2 rounded-lg bg-zinc-800/80">{m.icon}</div>
                  </div>
                  <div className="mt-4">
                    <h3 className="text-3xl font-extrabold text-white">{m.value}</h3>
                    <p className="text-xs text-zinc-500 mt-1">{m.sub}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Ingestion & Feed Panel */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

              {/* Lead Ingestion Box */}
              <div className="lg:col-span-1 p-6 rounded-2xl bg-zinc-900/40 border border-zinc-900">
                <h2 className="text-lg font-bold text-white mb-4 flex items-center gap-2">
                  <Zap className="h-4 w-4 text-violet-400" />
                  Lead Ingestion
                </h2>

                {/* Mode Tabs */}
                <div className="flex gap-2 mb-4 p-1 bg-zinc-950 rounded-lg border border-zinc-900">
                  <button
                    type="button"
                    id="mode-csv"
                    onClick={() => setIngestMode('csv')}
                    className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all flex items-center justify-center gap-1.5 ${ingestMode === 'csv' ? 'bg-zinc-900 text-white border border-zinc-800' : 'text-zinc-500 hover:text-zinc-300'}`}
                  >
                    <Upload className="h-3 w-3" /> CSV Ingestion
                  </button>
                  <button
                    type="button"
                    id="mode-search"
                    onClick={() => setIngestMode('search')}
                    className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-all flex items-center justify-center gap-1.5 ${ingestMode === 'search' ? 'bg-zinc-900 text-white border border-zinc-800' : 'text-zinc-500 hover:text-zinc-300'}`}
                  >
                    <Search className="h-3 w-3" /> AI Search Graph
                  </button>
                </div>

                {ingestMode === 'csv' ? (
                  <form onSubmit={handleCsvUpload} className="space-y-4">
                    <label
                      htmlFor="csv-file-input"
                      className={`block border border-dashed rounded-xl p-6 text-center cursor-pointer transition-all bg-zinc-950 flex flex-col items-center justify-center gap-2
                        ${csvFile ? 'border-violet-500/70 bg-violet-950/10' : 'border-zinc-800 hover:border-violet-500/50'}`}
                    >
                      <Upload className={`h-7 w-7 ${csvFile ? 'text-violet-400' : 'text-zinc-600'}`} />
                      <span className={`text-sm font-semibold ${csvFile ? 'text-violet-300' : 'text-zinc-400'}`}>
                        {csvFile ? csvFile.name : 'Select Outreach CSV'}
                      </span>
                      <p className="text-[10px] text-zinc-600 leading-normal">Required columns: email, first_name, last_name, company</p>
                      <input
                        type="file"
                        accept=".csv"
                        ref={fileInputRef}
                        onChange={(e) => setCsvFile(e.target.files?.[0] || null)}
                        className="hidden"
                        id="csv-file-input"
                      />
                    </label>
                    <button
                      type="submit"
                      id="btn-csv-upload"
                      disabled={loading || !csvFile}
                      className="w-full bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white font-semibold py-2.5 px-4 rounded-xl transition-all shadow-md shadow-violet-900/20 flex items-center justify-center gap-2"
                    >
                      {loading ? (
                        <><Loader2 className="h-4 w-4 animate-spin" /> Processing...</>
                      ) : (
                        <><Upload className="h-4 w-4" /> Upload & Start Harvester</>
                      )}
                    </button>
                  </form>
                ) : (
                  <form onSubmit={handleWebSearch} className="space-y-4">
                    <div className="bg-zinc-950 p-4 rounded-xl border border-zinc-900 space-y-3">
                      <label className="text-xs text-zinc-400 font-semibold block">Search Query / Intent</label>
                      <input
                        type="text"
                        id="search-query-input"
                        placeholder="e.g. AI compiler researchers at Stripe"
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            e.preventDefault();
                            if (!loading && searchQuery.trim()) handleWebSearch(e as any);
                          }
                        }}
                        disabled={loading}
                        className="w-full bg-zinc-900 border border-zinc-800 rounded-lg text-sm text-white p-2.5 outline-none focus:border-violet-500/60 transition-all placeholder:text-zinc-600 disabled:opacity-50"
                      />
                      <p className="text-[10px] text-zinc-600 leading-relaxed">
                        ScrapeGraphAI SearchGraph scans the web, extracts contact profiles, and enqueues them for enrichment automatically.
                      </p>
                    </div>
                    <button
                      type="submit"
                      id="btn-search-harvest"
                      disabled={loading || !searchQuery.trim()}
                      className="w-full bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-800 disabled:text-zinc-600 text-white font-semibold py-2.5 px-4 rounded-xl transition-all shadow-md shadow-violet-900/20 flex items-center justify-center gap-2"
                    >
                      {loading ? (
                        <><Loader2 className="h-4 w-4 animate-spin" /> Searching the web...</>
                      ) : (
                        <><Search className="h-4 w-4" /> Search & Harvest Leads</>
                      )}
                    </button>

                    {/* Quick example queries */}
                    <div className="space-y-1.5">
                      <p className="text-[10px] text-zinc-600 font-semibold uppercase tracking-wider">Quick examples</p>
                      {[
                        'ML engineers at OpenAI',
                        'GPU researchers at NVIDIA',
                        'Compiler engineers at Apple',
                      ].map(q => (
                        <button
                          key={q}
                          type="button"
                          onClick={() => setSearchQuery(q)}
                          disabled={loading}
                          className="w-full text-left px-3 py-1.5 rounded-lg text-xs text-zinc-500 hover:text-zinc-300 hover:bg-zinc-900/50 border border-transparent hover:border-zinc-800 transition-all disabled:opacity-40 flex items-center gap-2"
                        >
                          <ChevronRight className="h-3 w-3 shrink-0" />
                          {q}
                        </button>
                      ))}
                    </div>
                  </form>
                )}
              </div>

              {/* Conversion Funnel */}
              <div className="lg:col-span-1 p-6 rounded-2xl bg-zinc-900/40 border border-zinc-900">
                <h2 className="text-lg font-bold text-white mb-4">Outreach Funnel</h2>
                <div className="space-y-4 mt-2">
                  {analytics && Object.entries(analytics.funnel).map(([stage, count]) => {
                    const pct = Math.round((count / Math.max(analytics.summary.total_leads, 1)) * 100);
                    return (
                      <div key={stage} className="space-y-1.5">
                        <div className="flex justify-between items-center text-xs font-semibold">
                          <span className="text-zinc-300">{stage}</span>
                          <span className="text-zinc-500">{count} <span className="text-zinc-700 font-normal">({pct}%)</span></span>
                        </div>
                        <div className="w-full h-2 rounded-full bg-zinc-800 overflow-hidden">
                          <div
                            className="h-full bg-gradient-to-r from-violet-600 to-indigo-500 rounded-full transition-all duration-700"
                            style={{ width: `${pct}%` }}
                          />
                        </div>
                      </div>
                    );
                  })}
                  {!analytics && (
                    <p className="text-xs text-zinc-600 text-center py-10">Loading funnel data...</p>
                  )}
                </div>
              </div>

              {/* Real-time Dispatch Logs */}
              <div className="lg:col-span-1 p-6 rounded-2xl bg-zinc-900/40 border border-zinc-900 flex flex-col max-h-[350px]">
                <h2 className="text-lg font-bold text-white mb-3">Live Dispatch Log</h2>
                <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
                  {!analytics?.recent_logs || analytics.recent_logs.length === 0 ? (
                    <div className="text-center py-10 space-y-2">
                      <Mail className="h-8 w-8 text-zinc-800 mx-auto" />
                      <p className="text-xs text-zinc-600">No email logs yet. Dispatch a lead to see activity here.</p>
                    </div>
                  ) : (
                    analytics.recent_logs.map((log) => (
                      <div key={log.id} className="p-3 bg-zinc-950 rounded-xl border border-zinc-900 flex justify-between items-center text-xs">
                        <div className="space-y-0.5">
                          <p className="font-semibold text-zinc-200">{log.lead_name}</p>
                          <p className="text-[10px] text-zinc-500 truncate max-w-[160px]">{log.subject}</p>
                        </div>
                        <div className="text-right space-y-0.5">
                          <span className={`px-1.5 py-0.5 text-[9px] font-bold rounded ${log.status === 'SENT' ? 'bg-indigo-950 text-indigo-400' : 'bg-rose-950 text-rose-400'}`}>
                            {log.status}
                          </span>
                          <p className="text-[9px] text-zinc-600">
                            {new Date(log.sent_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </p>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>

            {/* Confirmed Meetings Feed */}
            <div className="p-6 rounded-2xl bg-zinc-900/40 border border-zinc-900">
              <h2 className="text-lg font-bold text-white mb-4">Confirmed Calendar Meetings</h2>
              {!analytics?.meetings || analytics.meetings.length === 0 ? (
                <div className="text-center py-8 text-zinc-500 text-sm flex flex-col items-center gap-2">
                  <Calendar className="h-8 w-8 text-zinc-800" />
                  <p>Waiting for meeting coordinates to confirm...</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {analytics.meetings.map((meeting, idx) => (
                    <div key={idx} className="p-4 rounded-xl bg-teal-950/20 border border-teal-900/50 flex items-center justify-between">
                      <div className="space-y-1">
                        <h4 className="font-semibold text-teal-300 text-sm">{meeting.lead_name}</h4>
                        <p className="text-xs text-zinc-400">{meeting.company}</p>
                      </div>
                      <span className="text-xs text-teal-400 font-medium">
                        {new Date(meeting.booked_at).toLocaleDateString()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ─── LEADS CRM ──────────────────────────────────────────── */}
        {activeTab === 'leads' && (
          <div className="space-y-6">
            <div className="flex justify-between items-center">
              <div>
                <h2 className="text-xl font-bold text-white">Leads CRM Manager</h2>
                <p className="text-xs text-zinc-500 mt-1">Context Harvester enriched profiles and A/B copywriting drafts.</p>
              </div>
              <div className="flex items-center gap-2">
                {loading && (
                  <div className="flex items-center gap-2 text-xs text-violet-400 bg-violet-950/30 border border-violet-900/50 px-3 py-2 rounded-xl">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    Harvesting new leads…
                  </div>
                )}
                <button
                  onClick={fetchData}
                  className="p-2 text-zinc-400 hover:text-white rounded-lg border border-zinc-900 hover:bg-zinc-900 transition-all"
                >
                  <RefreshCw className="h-4 w-4" />
                </button>
                {/* Quick-add from dashboard */}
                <button
                  onClick={() => { setActiveTab('dashboard'); setIngestMode('search'); }}
                  className="flex items-center gap-1.5 text-xs px-3 py-2 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-semibold transition-all"
                >
                  <Search className="h-3.5 w-3.5" /> Find More Leads
                </button>
              </div>
            </div>

            {leads.length === 0 ? (
              /* Empty State */
              <div className="flex flex-col items-center justify-center py-24 space-y-5 border border-dashed border-zinc-800 rounded-2xl bg-zinc-900/20">
                <div className="h-16 w-16 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center">
                  <Users className="h-7 w-7 text-zinc-600" />
                </div>
                <div className="text-center space-y-1">
                  <h3 className="text-lg font-bold text-zinc-300">No leads ingested yet</h3>
                  <p className="text-sm text-zinc-500 max-w-md">Use the AI Search Graph or upload a CSV to start building your outreach pipeline.</p>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => { setActiveTab('dashboard'); setIngestMode('csv'); }}
                    className="flex items-center gap-2 text-sm px-4 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-white font-semibold transition-all"
                  >
                    <Upload className="h-4 w-4" /> Upload CSV
                  </button>
                  <button
                    onClick={() => { setActiveTab('dashboard'); setIngestMode('search'); }}
                    className="flex items-center gap-2 text-sm px-4 py-2.5 rounded-xl bg-violet-600 hover:bg-violet-500 text-white font-semibold transition-all"
                  >
                    <Search className="h-4 w-4" /> AI Search for Leads
                  </button>
                </div>
              </div>
            ) : (
              /* Main CRM Workspace */
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                {/* Leads Table */}
                <div className="lg:col-span-2 rounded-2xl bg-zinc-900/40 border border-zinc-900 overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse text-sm">
                      <thead className="border-b border-zinc-900">
                        <tr className="text-zinc-500 text-xs uppercase tracking-wider">
                          <th className="px-5 py-3.5 font-semibold">Lead</th>
                          <th className="px-5 py-3.5 font-semibold">Company / Role</th>
                          <th className="px-5 py-3.5 font-semibold">Signals</th>
                          <th className="px-5 py-3.5 font-semibold">Status</th>
                          <th className="px-5 py-3.5 font-semibold text-right">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-900/40">
                        {leads.map((lead) => (
                          <tr
                            key={lead.id}
                            className={`hover:bg-zinc-900/30 transition-all cursor-pointer ${selectedLead?.id === lead.id ? 'bg-violet-950/10 border-l-2 border-l-violet-600' : ''}`}
                            onClick={() => setSelectedLead(lead)}
                          >
                            <td className="px-5 py-4">
                              <div className="font-semibold text-white">{lead.first_name} {lead.last_name}</div>
                              <div className="text-xs text-zinc-500 mt-0.5 truncate max-w-[160px]">{lead.email}</div>
                            </td>
                            <td className="px-5 py-4">
                              <div className="text-zinc-300 font-medium">{lead.company}</div>
                              <div className="text-xs text-zinc-500 mt-0.5">{lead.role}</div>
                            </td>
                            <td className="px-5 py-4">
                              <div className="flex items-center gap-2">
                                {lead.linkedin_url && (
                                  <a href={lead.linkedin_url} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} className="text-zinc-600 hover:text-blue-400 transition-all" title="LinkedIn">
                                    <LinkedinIcon className="h-4 w-4" />
                                  </a>
                                )}
                                {lead.github_username && (
                                  <a href={`https://github.com/${lead.github_username}`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()} className="text-zinc-600 hover:text-white transition-all" title="GitHub">
                                    <GithubIcon className="h-4 w-4" />
                                  </a>
                                )}
                                {lead.academic_profile && (
                                  <span className="text-zinc-600 hover:text-amber-400 transition-all cursor-pointer" title="Academic">
                                    <BookOpen className="h-4 w-4" />
                                  </span>
                                )}
                                {!lead.linkedin_url && !lead.github_username && !lead.academic_profile && (
                                  <span className="text-zinc-700 text-xs">—</span>
                                )}
                              </div>
                            </td>
                            <td className="px-5 py-4">
                              {getStatusBadge(lead.status)}
                            </td>
                            <td className="px-5 py-4 text-right" onClick={(e) => e.stopPropagation()}>
                              <div className="flex items-center justify-end gap-1.5">
                                {['INGESTED', 'HARVEST_FAILED', 'COPY_FAILED'].includes(lead.status) && (
                                  <button
                                    onClick={() => handleEnrich(lead.id)}
                                    disabled={actionLoading === `enrich-${lead.id}`}
                                    className={`px-2.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1 border transition-all
                                      ${lead.status.includes('FAILED')
                                        ? 'bg-red-950/50 text-red-400 border-red-900 hover:bg-red-900/50'
                                        : 'bg-zinc-800 hover:bg-emerald-900/50 hover:text-emerald-400 text-zinc-400 border-transparent hover:border-emerald-900'}`}
                                    title={lead.status.includes('FAILED') ? 'Retry enrichment' : 'Run Harvester'}
                                  >
                                    {actionLoading === `enrich-${lead.id}`
                                      ? <Loader2 className="h-3 w-3 animate-spin" />
                                      : <RefreshCw className="h-3 w-3" />}
                                    {lead.status.includes('FAILED') ? 'Retry' : 'Enrich'}
                                  </button>
                                )}
                                {lead.status === 'DRAFTED' && (
                                  <button
                                    onClick={() => handleDispatch(lead.id)}
                                    disabled={actionLoading === `dispatch-${lead.id}`}
                                    className="px-2.5 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white font-semibold text-xs transition-all flex items-center gap-1"
                                  >
                                    {actionLoading === `dispatch-${lead.id}`
                                      ? <Loader2 className="h-3 w-3 animate-spin" />
                                      : <Send className="h-3 w-3" />}
                                    Send
                                  </button>
                                )}
                                {['ENRICHED', 'COPYWRITING', 'CONTACTED', 'REPLIED', 'NEGOTIATING', 'BOOKED'].includes(lead.status) && (
                                  <button
                                    onClick={() => { setSelectedLead(lead); setActiveTab('negotiator'); }}
                                    className="p-1.5 rounded-lg border border-zinc-800 text-zinc-500 hover:text-violet-400 hover:bg-violet-950/20 hover:border-violet-900 transition-all"
                                    title="Chat History"
                                  >
                                    <MessageSquare className="h-3.5 w-3.5" />
                                  </button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Lead Details & Context Inspector */}
                <div className="lg:col-span-1 p-6 rounded-2xl bg-zinc-900/40 border border-zinc-900 space-y-5">
                  {selectedLead ? (
                    <>
                      <div className="flex justify-between items-start">
                        <div>
                          <h3 className="text-base font-bold text-white">{selectedLead.first_name} {selectedLead.last_name}</h3>
                          <p className="text-xs text-zinc-500 mt-0.5">{selectedLead.role} at {selectedLead.company}</p>
                          <p className="text-xs text-zinc-600 mt-0.5">{selectedLead.email}</p>
                        </div>
                        {getStatusBadge(selectedLead.status)}
                      </div>

                      {/* Context Harvester Output */}
                      <div className="space-y-2">
                        <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-500 flex items-center gap-1.5">
                          <Sparkles className="h-3.5 w-3.5 text-violet-400" />
                          Harvester Knowledge Base
                        </h4>
                        <div className="p-3 bg-zinc-950 rounded-xl border border-zinc-900 space-y-3 max-h-[220px] overflow-y-auto">
                          {selectedLead.harvested_context ? (
                            <>
                              {selectedLead.harvested_context?.linkedin?.summary && (
                                <div>
                                  <span className="text-[10px] font-bold text-violet-400">LinkedIn Summary:</span>
                                  <p className="text-xs text-zinc-400 mt-1 leading-relaxed">
                                    {selectedLead.harvested_context.linkedin.summary}
                                  </p>
                                </div>
                              )}
                              {selectedLead.harvested_context?.linkedin?.recent_posts?.length > 0 && (
                                <div>
                                  <span className="text-[10px] font-bold text-blue-400">Recent Activity:</span>
                                  <ul className="mt-1 space-y-1">
                                    {selectedLead.harvested_context.linkedin.recent_posts.slice(0, 2).map((p: string, i: number) => (
                                      <li key={i} className="text-xs text-zinc-500 leading-relaxed truncate" title={p}>💬 {p}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {selectedLead.harvested_context?.github?.length > 0 && (
                                <div>
                                  <span className="text-[10px] font-bold text-teal-400">GitHub Repos:</span>
                                  <ul className="text-xs text-zinc-400 mt-1 space-y-1">
                                    {selectedLead.harvested_context.github.map((repo: any, i: number) => (
                                      <li key={i} className="flex justify-between">
                                        <span className="font-semibold text-zinc-300 truncate max-w-[130px]">{repo.name}</span>
                                        <span className="text-zinc-600 text-[10px]">{repo.language}</span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {selectedLead.harvested_context?.publications?.length > 0 && (
                                <div>
                                  <span className="text-[10px] font-bold text-amber-400">Academic Papers:</span>
                                  <ul className="text-xs text-zinc-400 mt-1 space-y-1">
                                    {selectedLead.harvested_context.publications.map((pub: any, i: number) => (
                                      <li key={i} className="truncate text-zinc-300" title={pub.title}>📚 {pub.title}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </>
                          ) : (
                            <div className="text-xs text-zinc-600 text-center py-6">
                              <RefreshCw className="h-5 w-5 mx-auto mb-2 text-zinc-700" />
                              No context harvested yet. Run enrichment to pull LinkedIn, GitHub & arXiv data.
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Personalized Email Copy */}
                      <div className="space-y-2">
                        <h4 className="text-xs font-bold uppercase tracking-wider text-zinc-500 flex items-center gap-1.5">
                          <FileText className="h-3.5 w-3.5 text-indigo-400" />
                          Synapse Draft (Variant {selectedLead.selected_variant || '—'})
                        </h4>
                        <div className="p-4 bg-zinc-950 rounded-xl border border-zinc-900 space-y-3 max-h-[250px] overflow-y-auto">
                          {selectedLead.personalized_copy ? (
                            <>
                              <div>
                                <span className="text-[10px] font-semibold text-zinc-500">Subject:</span>
                                <div className="text-xs text-white font-semibold mt-0.5">{selectedLead.personalized_subject}</div>
                              </div>
                              <div>
                                <span className="text-[10px] font-semibold text-zinc-500">Body:</span>
                                <div className="text-xs text-zinc-300 mt-1 whitespace-pre-wrap leading-relaxed">
                                  {selectedLead.personalized_copy}
                                </div>
                              </div>
                              {selectedLead.status === 'DRAFTED' && (
                                <button
                                  onClick={() => handleDispatch(selectedLead.id)}
                                  disabled={actionLoading === `dispatch-${selectedLead.id}`}
                                  className="w-full mt-2 py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold flex items-center justify-center gap-1.5 transition-all"
                                >
                                  <Send className="h-3 w-3" /> Dispatch This Email
                                </button>
                              )}
                            </>
                          ) : (
                            <div className="text-xs text-zinc-600 text-center py-6">
                              <FileText className="h-5 w-5 mx-auto mb-2 text-zinc-700" />
                              Run context harvest to compile personalized copy.
                            </div>
                          )}
                        </div>
                      </div>
                    </>
                  ) : (
                    <div className="text-zinc-600 text-center py-20 text-sm flex flex-col items-center gap-3">
                      <Activity className="h-8 w-8 text-zinc-800" />
                      <p>Select a lead to inspect context graphs and personalized drafts.</p>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ─── NEGOTIATOR INBOX ───────────────────────────────────── */}
        {activeTab === 'negotiator' && (
          <div className="space-y-6">
            <div>
              <h2 className="text-xl font-bold text-white">AI Negotiator Agent Inbox</h2>
              <p className="text-xs text-zinc-500 mt-1">Autonomous stateful booking agent managing availability coordinates.</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Inbox Lead Selection */}
              <div className="lg:col-span-1 p-5 rounded-2xl bg-zinc-900/40 border border-zinc-900 max-h-[600px] overflow-y-auto space-y-2.5">
                <h3 className="text-xs font-bold uppercase text-zinc-500 mb-3 tracking-wider flex items-center gap-2">
                  <Activity className="h-3.5 w-3.5" /> Active Conversations
                </h3>
                {activeLeads.length === 0 ? (
                  <div className="text-center py-12 space-y-3">
                    <MessageSquare className="h-8 w-8 text-zinc-800 mx-auto" />
                    <div>
                      <p className="text-xs text-zinc-500 font-semibold">No active negotiations</p>
                      <p className="text-[11px] text-zinc-700 mt-1 leading-relaxed">Leads appear here once they reply to outreach emails.</p>
                    </div>
                  </div>
                ) : (
                  activeLeads.map((l) => (
                    <div
                      key={l.id}
                      onClick={() => setSelectedLead(l)}
                      className={`p-4 rounded-xl border transition-all cursor-pointer flex justify-between items-center ${selectedLead?.id === l.id ? 'bg-violet-950/20 border-violet-800' : 'bg-zinc-950 border-zinc-900 hover:border-zinc-800'}`}
                    >
                      <div className="space-y-1">
                        <div className="font-semibold text-sm text-white">{l.first_name} {l.last_name}</div>
                        <div className="text-xs text-zinc-500">{l.company}</div>
                      </div>
                      {getStatusBadge(l.status)}
                    </div>
                  ))
                )}

                {/* Show ALL leads that could be simulated */}
                {activeLeads.length === 0 && leads.filter(l => l.status === 'CONTACTED').length > 0 && (
                  <div className="border-t border-zinc-900 pt-3 mt-3">
                    <p className="text-[10px] font-bold uppercase tracking-wider text-zinc-600 mb-2">Contacted (simulate reply)</p>
                    {leads.filter(l => l.status === 'CONTACTED').map(l => (
                      <div
                        key={l.id}
                        onClick={() => setSelectedLead(l)}
                        className="p-3 rounded-xl border border-zinc-900 hover:border-zinc-800 bg-zinc-950 cursor-pointer mb-2 flex justify-between items-center transition-all"
                      >
                        <div>
                          <div className="font-semibold text-sm text-zinc-300">{l.first_name} {l.last_name}</div>
                          <div className="text-xs text-zinc-600">{l.company}</div>
                        </div>
                        {getStatusBadge(l.status)}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Chat Thread Console */}
              <div className="lg:col-span-2 p-5 rounded-2xl bg-zinc-900/40 border border-zinc-900 flex flex-col h-[600px]">
                {selectedLead ? (
                  <>
                    <div className="border-b border-zinc-900 pb-3 flex justify-between items-center">
                      <div>
                        <h4 className="font-bold text-white text-base">{selectedLead.first_name} {selectedLead.last_name}</h4>
                        <p className="text-xs text-zinc-500">{selectedLead.email} • {selectedLead.role} at {selectedLead.company}</p>
                      </div>
                      {getStatusBadge(selectedLead.status)}
                    </div>

                    {/* Chat Bubble List */}
                    <div className="flex-1 overflow-y-auto py-4 space-y-3 pr-2">
                      {chatHistory.length === 0 ? (
                        <div className="text-center py-16 space-y-3">
                          <MessageSquare className="h-8 w-8 text-zinc-700 mx-auto" />
                          <p className="text-sm text-zinc-500">Dialogue loop initialized.</p>
                          <div className="mt-2 p-3 bg-zinc-950 rounded-xl text-xs text-left max-w-sm mx-auto border border-zinc-900 text-zinc-500">
                            Simulate receiving a scheduling question from this lead to start the negotiation thread.
                          </div>
                        </div>
                      ) : (
                        chatHistory.map((chat, idx) => (
                          <div
                            key={idx}
                            className={`flex ${chat.role === 'user' ? 'justify-start' : 'justify-end'}`}
                          >
                            <div className={`max-w-md p-3.5 rounded-2xl text-xs leading-relaxed ${chat.role === 'user' ? 'bg-zinc-900 text-zinc-300 border border-zinc-800' : 'bg-violet-950/30 text-violet-200 border border-violet-900/50'}`}>
                              <span className="font-bold text-[9px] uppercase tracking-wider block mb-1 text-zinc-500">
                                {chat.role === 'user' ? 'Lead Prospect' : 'ORX AI Negotiator'}
                              </span>
                              <p className="whitespace-pre-wrap">{chat.content}</p>
                              <span className="text-[8px] text-zinc-600 block mt-1 text-right">
                                {new Date(chat.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                              </span>
                            </div>
                          </div>
                        ))
                      )}
                    </div>

                    {/* Simulation Console Input */}
                    <div className="border-t border-zinc-900 pt-3">
                      <p className="text-[10px] text-zinc-600 mb-2 font-semibold">SIMULATE INCOMING REPLY</p>
                      <div className="bg-zinc-950 rounded-xl border border-zinc-900 p-2 flex items-center gap-2 focus-within:border-violet-500/50 transition-all">
                        <input
                          type="text"
                          placeholder="e.g. 'What slots do you have on Wednesday?'"
                          value={replyMessage}
                          onChange={(e) => setReplyMessage(e.target.value)}
                          onKeyDown={(e) => e.key === 'Enter' && handleSimulateReply()}
                          className="flex-1 bg-transparent border-0 outline-none text-xs text-zinc-200 px-2 py-1.5"
                        />
                        <button
                          onClick={handleSimulateReply}
                          disabled={actionLoading === 'chat' || !replyMessage.trim()}
                          className="px-3.5 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-900 disabled:text-zinc-600 text-white font-semibold text-xs transition-all flex items-center gap-1"
                        >
                          {actionLoading === 'chat' ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
                          Simulate
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="text-zinc-500 flex-1 flex flex-col items-center justify-center gap-3">
                    <MessageSquare className="h-10 w-10 text-zinc-800" />
                    <p className="text-sm">Select a lead to inspect the scheduling negotiation loop.</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-900 py-4 px-6 text-center text-xs text-zinc-700 bg-zinc-950">
        © 2026 ORX Outreach Engine — Authored for Abdu Aziz Rashid Hamed Al Badi — Built with ScrapeGraphAI & OpenRouter
      </footer>
    </div>
  );
}
