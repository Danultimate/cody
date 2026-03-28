import { useEffect, useState, useRef, useCallback } from "react";
import axios from "axios";
import QueryPanel from "./components/QueryPanel.jsx";
import AnswerPanel from "./components/AnswerPanel.jsx";
import RepoTree from "./components/RepoTree.jsx";
import AddRepoModal from "./components/AddRepoModal.jsx";
import styles from "./App.module.css";

const API_BASE = import.meta.env.VITE_API_URL ?? "/";
const POLL_INTERVAL = 2000;

function timeAgo(dateStr) {
  if (!dateStr) return null;
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

export default function App() {
  const [repos, setRepos] = useState([]);
  const [selectedRepo, setSelectedRepo] = useState(null);
  const [answer, setAnswer] = useState(null);
  const [chunks, setChunks] = useState([]);
  const [latencyMs, setLatencyMs] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [highlightedFile, setHighlightedFile] = useState(null);
  const [showAddRepo, setShowAddRepo] = useState(false);
  const [syncingRepoId, setSyncingRepoId] = useState(null);
  const answerRef = useRef(null);
  const syncPollRef = useRef(null);

  const fetchRepos = useCallback((keepSelected) => {
    axios.get(`${API_BASE}repos`).then((res) => {
      setRepos(res.data);
      if (res.data.length > 0 && !keepSelected) setSelectedRepo(res.data[0]);
    }).catch(() => {
      setError("Could not connect to the API. Is the backend running?");
    });
  }, []);

  useEffect(() => { fetchRepos(false); }, []);

  // Keep selectedRepo in sync when repos list refreshes
  useEffect(() => {
    if (!selectedRepo || repos.length === 0) return;
    const updated = repos.find((r) => r.id === selectedRepo.id);
    if (updated) setSelectedRepo(updated);
  }, [repos]);

  const handleQuery = async (question) => {
    if (!selectedRepo) return;
    setIsLoading(true);
    setError(null);
    setAnswer(null);
    setChunks([]);
    setHighlightedFile(null);

    try {
      const res = await axios.post(`${API_BASE}query`, {
        question,
        repo_id: selectedRepo.id,
        top_k: 8,
      });
      setAnswer(res.data.answer);
      setChunks(res.data.chunks);
      setLatencyMs(res.data.latency_ms);
      setTimeout(() => answerRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    } catch (e) {
      setError(e.response?.data?.detail || "Query failed. Check the console.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleDelete = async (repo) => {
    if (!window.confirm(`Delete "${repo.name}" and all its indexed data?`)) return;
    try {
      await axios.delete(`${API_BASE}repos/${repo.id}`);
      const remaining = repos.filter((r) => r.id !== repo.id);
      setRepos(remaining);
      if (selectedRepo?.id === repo.id) {
        setSelectedRepo(remaining[0] ?? null);
        setAnswer(null);
        setChunks([]);
      }
    } catch (e) {
      setError(e.response?.data?.detail || "Delete failed.");
    }
  };

  const handleResync = async (repo) => {
    if (syncingRepoId) return;
    setSyncingRepoId(repo.id);
    try {
      const res = await axios.post(`${API_BASE}repos/${repo.id}/resync`);
      const jobId = res.data.job_id;

      syncPollRef.current = setInterval(async () => {
        try {
          const status = await axios.get(`${API_BASE}ingest/${jobId}`);
          if (status.data.status === "done" || status.data.status === "error") {
            clearInterval(syncPollRef.current);
            setSyncingRepoId(null);
            fetchRepos(true);
          }
        } catch {
          clearInterval(syncPollRef.current);
          setSyncingRepoId(null);
        }
      }, POLL_INTERVAL);
    } catch (e) {
      setError(e.response?.data?.detail || "Resync failed.");
      setSyncingRepoId(null);
    }
  };

  useEffect(() => () => clearInterval(syncPollRef.current), []);

  const handleRepoDone = () => {
    fetchRepos(false);
    setShowAddRepo(false);
  };

  return (
    <div className={styles.layout}>
      {/* Sidebar */}
      <aside className={styles.sidebar}>
        <div className={styles.logo}>
          <span className={styles.logoAccent}>&#x2665;</span> codebase intel
        </div>

        <div className={styles.sideSection}>
          <div className={styles.sideRow}>
            <label className={styles.sideLabel}>Repository</label>
            <button className={styles.addBtn} onClick={() => setShowAddRepo(true)} title="Add repository">
              +
            </button>
          </div>
          <select
            className={styles.repoSelect}
            value={selectedRepo?.id ?? ""}
            onChange={(e) => {
              const repo = repos.find((r) => r.id === Number(e.target.value));
              setSelectedRepo(repo ?? null);
            }}
          >
            {repos.length === 0 && <option value="">No repos indexed</option>}
            {repos.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>

          {selectedRepo && (
            <>
              <div className={styles.repoMeta}>
                <span>{selectedRepo.chunk_count ?? 0} chunks</span>
                <span>·</span>
                <span>{selectedRepo.file_count ?? 0} files</span>
                {selectedRepo.indexed_at && (
                  <>
                    <span>·</span>
                    <span title={new Date(selectedRepo.indexed_at).toLocaleString()}>
                      synced {timeAgo(selectedRepo.indexed_at)}
                    </span>
                  </>
                )}
              </div>
              <div className={styles.repoActions}>
                <button
                  className={styles.syncBtn}
                  onClick={() => handleResync(selectedRepo)}
                  disabled={syncingRepoId === selectedRepo.id}
                  title="Sync latest changes"
                >
                  {syncingRepoId === selectedRepo.id ? "Syncing…" : "↻ Sync"}
                </button>
                <button
                  className={styles.deleteBtn}
                  onClick={() => handleDelete(selectedRepo)}
                  disabled={!!syncingRepoId}
                  title="Delete repository"
                >
                  Delete
                </button>
              </div>
            </>
          )}
        </div>

        {chunks.length > 0 && (
          <div className={styles.sideSection}>
            <label className={styles.sideLabel}>Files in last query</label>
            <RepoTree
              chunks={chunks}
              highlightedFile={highlightedFile}
              onSelectFile={setHighlightedFile}
            />
          </div>
        )}
      </aside>

      {/* Main */}
      <main className={styles.main}>
        <header className={styles.header}>
          <h1 className={styles.title}>Ask anything about your codebase</h1>
          <p className={styles.subtitle}>
            Powered by Voyage AI embeddings + Gemini 2.0 Flash — no hallucinations, every answer cited.
          </p>
        </header>

        <QueryPanel onSubmit={handleQuery} isLoading={isLoading} disabled={!selectedRepo} />

        {error && <div className={styles.error}>{error}</div>}

        <div ref={answerRef}>
          {(answer !== null || isLoading) && (
            <AnswerPanel
              answer={answer}
              chunks={chunks}
              latencyMs={latencyMs}
              isLoading={isLoading}
              highlightedFile={highlightedFile}
            />
          )}
        </div>
      </main>

      {showAddRepo && (
        <AddRepoModal
          apiBase={API_BASE}
          onClose={() => setShowAddRepo(false)}
          onDone={handleRepoDone}
        />
      )}
    </div>
  );
}
