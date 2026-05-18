import { useState, useEffect, useRef } from "react";
import axios from "axios";
import styles from "./AddRepoModal.module.css";

const POLL_INTERVAL = 2000;

export default function AddRepoModal({ apiBase, onClose, onDone, suggestedRepos = [], onSelectRepo }) {
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [jobId, setJobId] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");
  const [rateLimited, setRateLimited] = useState(null); // null | 'ip' | 'global'
  const pollRef = useRef(null);
  const logRef = useRef(null);

  useEffect(() => {
    if (!jobId) return;
    pollRef.current = setInterval(async () => {
      try {
        const res = await axios.get(`${apiBase}ingest/${jobId}`);
        setJob(res.data);
        if (res.data.status === "done" || res.data.status === "error") {
          clearInterval(pollRef.current);
          if (res.data.status === "done") onDone();
        }
      } catch {}
    }, POLL_INTERVAL);
    return () => clearInterval(pollRef.current);
  }, [jobId]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [job?.log]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const res = await axios.post(`${apiBase}ingest`, { repo_url: repoUrl, branch });
      setJobId(res.data.job_id);
    } catch (err) {
      const status = err.response?.status;
      if (status === 429) {
        setRateLimited("ip");
      } else if (status === 503) {
        setRateLimited("global");
      } else {
        setError(err.response?.data?.detail || "Failed to start ingestion.");
      }
    }
  };

  const isDone = job?.status === "done";
  const isError = job?.status === "error";

  if (rateLimited === "global") {
    return (
      <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div className={styles.modal}>
          <div className={styles.header}>
            <h2 className={styles.title}>Add Repository</h2>
            <button className={styles.closeBtn} onClick={onClose}>✕</button>
          </div>
          <div className={styles.busyState}>
            <div className={styles.busyIcon}>&#x23F3;</div>
            <p className={styles.busyTitle}>Cody is busy right now</p>
            <p className={styles.busyText}>We're getting a lot of love at the moment. Try again in a little while, or explore one of the repos already indexed below.</p>
            {suggestedRepos.length > 0 && (
              <div className={styles.suggestedList}>
                {suggestedRepos.map((r) => (
                  <button key={r.id} className={styles.suggestedItem} onClick={() => onSelectRepo(r)}>
                    <span className={styles.suggestedName}>{r.name}</span>
                    <span className={styles.suggestedMeta}>{r.chunk_count ?? 0} chunks</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  if (rateLimited === "ip") {
    return (
      <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
        <div className={styles.modal}>
          <div className={styles.header}>
            <h2 className={styles.title}>Add Repository</h2>
            <button className={styles.closeBtn} onClick={onClose}>✕</button>
          </div>
          <div className={styles.rateLimitedState}>
            <p className={styles.rateLimitedTitle}>Daily limit reached</p>
            <p className={styles.rateLimitedText}>You've already indexed a repo today. Come back tomorrow, or explore one of these already-indexed repos:</p>
            {suggestedRepos.length > 0 ? (
              <div className={styles.suggestedList}>
                {suggestedRepos.map((r) => (
                  <button key={r.id} className={styles.suggestedItem} onClick={() => onSelectRepo(r)}>
                    <span className={styles.suggestedName}>{r.name}</span>
                    <span className={styles.suggestedMeta}>{r.chunk_count ?? 0} chunks</span>
                  </button>
                ))}
              </div>
            ) : (
              <p className={styles.rateLimitedText}>No repos indexed yet.</p>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.overlay} onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className={styles.modal}>
        <div className={styles.header}>
          <h2 className={styles.title}>Add Repository</h2>
          <button className={styles.closeBtn} onClick={onClose}>✕</button>
        </div>

        {!jobId ? (
          <form className={styles.form} onSubmit={handleSubmit}>
            <label className={styles.label}>GitHub URL</label>
            <input
              className={styles.input}
              type="text"
              placeholder="https://github.com/org/repo"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              required
              autoFocus
            />
            <label className={styles.label}>Branch</label>
            <input
              className={styles.input}
              type="text"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
            />
            {error && <div className={styles.error}>{error}</div>}
            <button className={styles.submitBtn} type="submit">
              Start Indexing
            </button>
          </form>
        ) : (
          <div className={styles.jobView}>
            <div className={styles.statusRow}>
              <span className={`${styles.badge} ${styles[job?.status ?? "pending"]}`}>
                {job?.status ?? "pending"}
              </span>
              <span className={styles.repoName}>{repoUrl}</span>
            </div>
            <pre className={styles.log} ref={logRef}>
              {job?.log || "Starting…"}
            </pre>
            {isDone && (
              <button className={styles.submitBtn} onClick={onClose}>
                Done — close
              </button>
            )}
            {isError && (
              <button className={styles.retryBtn} onClick={() => { setJobId(null); setJob(null); }}>
                Try again
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
