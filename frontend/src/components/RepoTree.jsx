import { useState, useEffect } from "react";
import styles from "./RepoTree.module.css";

function buildTree(chunks) {
  const tree = {};
  for (const chunk of chunks) {
    const parts = chunk.file_path.split("/");
    let node = tree;
    for (let i = 0; i < parts.length - 1; i++) {
      const dir = parts[i];
      if (!node[dir]) node[dir] = { _type: "dir", _children: {} };
      node = node[dir]._children;
    }
    const file = parts[parts.length - 1];
    if (!node[file]) node[file] = { _type: "file", _path: chunk.file_path };
  }
  return tree;
}

function TreeNode({ name, node, depth, onSelect, highlightedFile }) {
  const [open, setOpen] = useState(depth < 2);
  const isDir = node._type === "dir";
  const isFile = node._type === "file";
  const isHighlighted = isFile && node._path === highlightedFile;

  if (isDir) {
    return (
      <div>
        <div
          className={styles.dirRow}
          style={{ paddingLeft: depth * 12 }}
          onClick={() => setOpen((o) => !o)}
        >
          <span className={styles.arrow}>{open ? "▾" : "▸"}</span>
          <span className={styles.dirName}>{name}</span>
        </div>
        {open &&
          Object.entries(node._children)
            .sort(([, a], [, b]) => {
              if (a._type !== b._type) return a._type === "dir" ? -1 : 1;
              return 0;
            })
            .map(([childName, childNode]) => (
              <TreeNode
                key={childName}
                name={childName}
                node={childNode}
                depth={depth + 1}
                onSelect={onSelect}
                highlightedFile={highlightedFile}
              />
            ))}
      </div>
    );
  }

  return (
    <div
      className={`${styles.fileRow} ${isHighlighted ? styles.highlighted : ""}`}
      style={{ paddingLeft: depth * 12 + 16 }}
      onClick={() => onSelect(node._path)}
      title={node._path}
    >
      <span className={styles.fileIcon}>◆</span>
      <span className={styles.fileName}>{name}</span>
    </div>
  );
}

export default function RepoTree({ chunks, highlightedFile, onSelectFile }) {
  const [tree, setTree] = useState({});

  useEffect(() => {
    setTree(buildTree(chunks));
  }, [chunks]);

  return (
    <div className={styles.tree}>
      {Object.entries(tree)
        .sort(([, a], [, b]) => {
          if (a._type !== b._type) return a._type === "dir" ? -1 : 1;
          return 0;
        })
        .map(([name, node]) => (
          <TreeNode
            key={name}
            name={name}
            node={node}
            depth={0}
            onSelect={onSelectFile}
            highlightedFile={highlightedFile}
          />
        ))}
    </div>
  );
}
