import { useRef, useEffect } from "react";
import styles from "./AnswerPanel.module.css";

export default function AnswerPanel({ answer, chunks, latencyMs, isLoading, highlightedFile }) {
  const sourceRefs = useRef({});

  useEffect(() => {
    if (highlightedFile && sourceRefs.current[highlightedFile]) {
      sourceRefs.current[highlightedFile].scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [highlightedFile]);

  if (isLoading) {
    return (
      <div className={styles.loadingCard}>
        <div className={styles.skeleton} style={{ width: "60%" }} />
        <div className={styles.skeleton} style={{ width: "90%" }} />
        <div className={styles.skeleton} style={{ width: "75%" }} />
        <div className={styles.skeleton} style={{ width: "50%" }} />
      </div>
    );
  }

  if (!answer) return null;

  return (
    <div className={styles.panel}>
      {/* Answer */}
      <div className={styles.answerCard}>
        <div className={styles.answerHeader}>
          <span className={styles.answerLabel}>Answer</span>
          {latencyMs !== null && (
            <span className={styles.latencyBadge}>
              Answered in {(latencyMs / 1000).toFixed(1)}s
            </span>
          )}
        </div>
        <p className={styles.answerText}>{answer}</p>
      </div>

      {/* Sources */}
      {chunks.length > 0 && (
        <div className={styles.sources}>
          <h3 className={styles.sourcesTitle}>
            Sources <span className={styles.sourceCount}>{chunks.length}</span>
          </h3>
          <div className={styles.chunkGrid}>
            {chunks.map((chunk, i) => (
              <div
                key={i}
                ref={(el) => {
                  if (el) sourceRefs.current[chunk.file_path] = el;
                }}
                className={`${styles.chunkCard} ${
                  highlightedFile === chunk.file_path ? styles.highlighted : ""
                }`}
              >
                <div className={styles.chunkHeader}>
                  <span className={styles.filePath}>{chunk.file_path}</span>
                  <div className={styles.chunkMeta}>
                    {chunk.chunk_type && (
                      <span className={styles.chunkType}>{chunk.chunk_type}</span>
                    )}
                    <span className={styles.lineRange}>
                      L{chunk.start_line}–{chunk.end_line}
                    </span>
                    <span className={styles.similarity}>
                      {(chunk.similarity * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>
                {chunk.name && <div className={styles.chunkName}>{chunk.name}</div>}
                <pre className={styles.codePreview}>
                  {chunk.content.split("\n").slice(0, 3).join("\n")}
                  {chunk.content.split("\n").length > 3 && "\n…"}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
