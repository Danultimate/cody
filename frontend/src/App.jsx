import { useEffect, useState, useRef } from "react";
import axios from "axios";
import QueryPanel from "./components/QueryPanel.jsx";
import AnswerPanel from "./components/AnswerPanel.jsx";
import RepoTree from "./components/RepoTree.jsx";
import styles from "./App.module.css";

const API_BASE = import.meta.env.VITE_API_URL ?? "/";

export default function App() {
  const [repos, setRepos] = useState([]);
  const [selectedRepo, setSelectedRepo] = useState(null);
  const [answer, setAnswer] = useState(null);
  const [chunks, setChunks] = useState([]);
  const [latencyMs, setLatencyMs] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [highlightedFile, setHighlightedFile] = useState(null);
  const answerRef = useRef(null);

  useEffect(() => {
    axios.get(`${API_BASE}repos`).then((res) => {
      setRepos(res.data);
      if (res.data.length > 0) setSelectedRepo(res.data[0]);
    }).catch(() => {
      setError("Could not connect to the API. Is the backend running?");
    });
  }, []);

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

  return (
    <div className={styles.layout}>
      {/* Sidebar */}
      <aside className={styles.sidebar}>
        <div className={styles.logo}>
          <span className={styles.logoAccent}>&#x2665;</span> codebase intel
        </div>

        <div className={styles.sideSection}>
          <label className={styles.sideLabel}>Repository</label>
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
            <div className={styles.repoMeta}>
              <span>{selectedRepo.chunk_count ?? 0} chunks</span>
              <span>·</span>
              <span>{selectedRepo.file_count ?? 0} files</span>
            </div>
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
    </div>
  );
}
