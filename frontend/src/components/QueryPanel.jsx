import { useState } from "react";
import styles from "./QueryPanel.module.css";

export default function QueryPanel({ onSubmit, isLoading, disabled }) {
  const [question, setQuestion] = useState("");

  const handleSubmit = (e) => {
    e.preventDefault();
    const q = question.trim();
    if (q) onSubmit(q);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSubmit(e);
    }
  };

  return (
    <form className={styles.form} onSubmit={handleSubmit}>
      <textarea
        className={styles.textarea}
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="How does authentication work? Where is the database connection initialized? What does the rate limiter do?"
        rows={3}
        disabled={isLoading || disabled}
      />
      <div className={styles.actions}>
        <span className={styles.hint}>⌘ + Enter to submit</span>
        <button
          type="submit"
          className={styles.button}
          disabled={isLoading || disabled || !question.trim()}
        >
          {isLoading ? (
            <span className={styles.thinking}>
              <span className={styles.dot} />
              <span className={styles.dot} />
              <span className={styles.dot} />
              Thinking…
            </span>
          ) : (
            "Ask"
          )}
        </button>
      </div>
    </form>
  );
}
