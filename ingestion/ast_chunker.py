from pathlib import Path
import tiktoken

try:
    from tree_sitter_languages import get_language, get_parser
    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False

_encoder = tiktoken.get_encoding("cl100k_base")

# AST node types to extract per language
_NODE_TYPES: dict[str, list[str]] = {
    "python": ["function_definition", "class_definition", "decorated_definition"],
    "javascript": [
        "function_declaration", "arrow_function", "class_declaration",
        "method_definition", "export_statement",
    ],
    "typescript": [
        "function_declaration", "arrow_function", "class_declaration",
        "method_definition", "export_statement",
    ],
    "php": ["function_definition", "method_declaration", "class_declaration"],
    "go": ["function_declaration", "method_declaration", "type_declaration"],
    "rust": ["function_item", "impl_item", "struct_item", "enum_item"],
    "java": ["method_declaration", "class_declaration", "constructor_declaration"],
    "ruby": ["method", "class", "module"],
    "c": ["function_definition", "struct_specifier"],
    "cpp": ["function_definition", "class_specifier", "struct_specifier"],
    "c_sharp": ["method_declaration", "class_declaration", "constructor_declaration"],
}

# chunk_type label mapping
_TYPE_MAP = {
    "function_definition": "function",
    "function_declaration": "function",
    "function_item": "function",
    "arrow_function": "function",
    "method_definition": "method",
    "method_declaration": "method",
    "method": "method",
    "class_definition": "class",
    "class_declaration": "class",
    "class_specifier": "class",
    "decorated_definition": "function",
    "export_statement": "function",
    "type_declaration": "type",
    "impl_item": "impl",
    "struct_item": "struct",
    "struct_specifier": "struct",
    "enum_item": "enum",
    "module": "module",
    "constructor_declaration": "function",
}

MIN_LINES = 5
MAX_LINES = 150
SPLIT_SIZE = 100
SPLIT_OVERLAP = 15
WINDOW_SIZE = 60
WINDOW_OVERLAP = 10


def _count_tokens(text: str) -> int:
    return len(_encoder.encode(text))


def _extract_name(node, language: str) -> str:
    """Best-effort extraction of the symbol name from an AST node."""
    # Look for direct identifier/name children
    name_types = {"identifier", "name", "property_identifier", "field_identifier"}
    for child in node.children:
        if child.type in name_types:
            return child.text.decode("utf-8", errors="replace")
    return ""


def _sliding_window(lines: list[str], file_path: str) -> list[dict]:
    chunks = []
    total = len(lines)
    start = 0
    while start < total:
        end = min(start + WINDOW_SIZE, total)
        window = lines[start:end]
        if len(window) >= MIN_LINES:
            content = "\n".join(window)
            chunks.append({
                "content": content,
                "chunk_type": "window",
                "name": "",
                "start_line": start + 1,
                "end_line": end,
                "token_count": _count_tokens(content),
            })
        if end == total:
            break
        start += WINDOW_SIZE - WINDOW_OVERLAP
    return chunks


def _split_large_chunk(content: str, start_line: int, name: str, chunk_type: str) -> list[dict]:
    lines = content.splitlines()
    parts = []
    i = 0
    part_num = 1
    while i < len(lines):
        end = min(i + SPLIT_SIZE, len(lines))
        sub_lines = lines[i:end]
        sub_content = "\n".join(sub_lines)
        parts.append({
            "content": sub_content,
            "chunk_type": chunk_type,
            "name": f"{name}_part_{part_num}" if name else f"part_{part_num}",
            "start_line": start_line + i,
            "end_line": start_line + end - 1,
            "token_count": _count_tokens(sub_content),
        })
        part_num += 1
        if end == len(lines):
            break
        i += SPLIT_SIZE - SPLIT_OVERLAP
    return parts


def chunk_file(file_path: Path, language: str, content: str) -> list[dict]:
    lines = content.splitlines()

    if not _TS_AVAILABLE or language not in _NODE_TYPES:
        return _sliding_window(lines, str(file_path))

    try:
        parser = get_parser(language)
    except Exception:
        return _sliding_window(lines, str(file_path))

    try:
        tree = parser.parse(content.encode("utf-8"))
    except Exception:
        return _sliding_window(lines, str(file_path))

    target_types = set(_NODE_TYPES[language])
    extracted: list[dict] = []

    def walk(node):
        if node.type in target_types:
            start_line = node.start_point[0]  # 0-indexed
            end_line = node.end_point[0]
            num_lines = end_line - start_line + 1

            if num_lines < MIN_LINES:
                # Still recurse into children for nested defs
                for child in node.children:
                    walk(child)
                return

            node_content = node.text.decode("utf-8", errors="replace")
            name = _extract_name(node, language)
            chunk_type = _TYPE_MAP.get(node.type, "function")

            if num_lines > MAX_LINES:
                parts = _split_large_chunk(node_content, start_line + 1, name, chunk_type)
                extracted.extend(parts)
            else:
                extracted.append({
                    "content": node_content,
                    "chunk_type": chunk_type,
                    "name": name,
                    "start_line": start_line + 1,
                    "end_line": end_line + 1,
                    "token_count": _count_tokens(node_content),
                })
            # Don't recurse into already-extracted nodes to avoid nesting
            return

        for child in node.children:
            walk(child)

    walk(tree.root_node)

    if not extracted:
        return _sliding_window(lines, str(file_path))

    return extracted
