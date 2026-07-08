"""Python parser for BlastRadius.

Walks a repository, parses every .py file with the stdlib `ast` module,
and emits an IRDocument. Two-pass design:

  Pass 1 — declarations: modules, classes, functions/methods, imports,
            API endpoints (via framework decorators), tests (via naming).
  Pass 2 — references: resolve call sites to known qualified names
            (exact import match first, then same-module, then unique
            global name match).
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..ir import IRDocument, IRNode, IREdge, NodeKind, EdgeKind

# Decorator attribute names that indicate an HTTP endpoint (FastAPI / Flask style)
_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "route", "websocket"}

_SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", "build", "dist"}


class PythonParser:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.doc = IRDocument(language="python", root=str(self.root))
        # qualified name -> IRNode, for resolution
        self._defs: dict[str, IRNode] = {}
        # short name -> [qualified names], for fallback resolution
        self._by_name: dict[str, list[str]] = {}
        # per-module import alias map: module_qname -> {alias: qualified_target}
        self._imports: dict[str, dict[str, str]] = {}
        # deferred call references: (caller_qname, module_qname, call_text)
        self._calls: list[tuple[str, str, str]] = []

    # ------------------------------------------------------------------

    def parse(self) -> IRDocument:
        py_files = [
            p for p in sorted(self.root.rglob("*.py"))
            if not any(part in _SKIP_DIRS for part in p.parts)
        ]
        trees: list[tuple[str, Path, ast.Module]] = []

        # Pass 1: declarations
        for path in py_files:
            module_qname = self._module_name(path)
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            trees.append((module_qname, path, tree))
            self._collect_declarations(module_qname, path, tree)

        # Pass 2: references (calls)
        for module_qname, path, tree in trees:
            self._collect_calls(module_qname, tree)
        self._resolve_calls()

        return self.doc

    # ------------------------------------------------------------------
    # Pass 1
    # ------------------------------------------------------------------

    def _module_name(self, path: Path) -> str:
        rel = path.relative_to(self.root).with_suffix("")
        parts = [p for p in rel.parts if p != "__init__"]
        return ".".join(parts) if parts else rel.stem

    def _rel(self, path: Path) -> str:
        return str(path.relative_to(self.root))

    def _register(self, node: IRNode) -> None:
        self.doc.add_node(node)
        self._defs[node.id] = node
        self._by_name.setdefault(node.name, []).append(node.id)

    def _collect_declarations(self, module_qname: str, path: Path, tree: ast.Module) -> None:
        rel = self._rel(path)
        is_test_file = path.name.startswith("test_") or path.name.endswith("_test.py")

        self._register(IRNode(id=module_qname, kind=NodeKind.MODULE,
                              name=module_qname.split(".")[-1], file=rel, line=1))
        self._imports[module_qname] = {}

        for stmt in tree.body:
            self._declare(stmt, module_qname, module_qname, rel, is_test_file, in_class=None)

    def _declare(self, stmt: ast.stmt, module_qname: str, parent: str,
                 rel: str, is_test_file: bool, in_class: str | None) -> None:
        if isinstance(stmt, (ast.Import, ast.ImportFrom)):
            self._record_import(stmt, module_qname)

        elif isinstance(stmt, ast.ClassDef):
            qname = f"{parent}.{stmt.name}"
            self._register(IRNode(id=qname, kind=NodeKind.CLASS, name=stmt.name,
                                  file=rel, line=stmt.lineno,
                                  end_line=getattr(stmt, "end_lineno", stmt.lineno) or stmt.lineno))
            self.doc.add_edge(parent, qname, EdgeKind.CONTAINS)
            for base in stmt.bases:
                base_name = _dotted(base)
                if base_name:
                    resolved = self._imports.get(module_qname, {}).get(base_name, base_name)
                    self.doc.add_edge(qname, resolved, EdgeKind.INHERITS)
            for inner in stmt.body:
                self._declare(inner, module_qname, qname, rel, is_test_file, in_class=qname)

        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qname = f"{parent}.{stmt.name}"
            is_test = is_test_file or stmt.name.startswith("test_")
            endpoint = _endpoint_info(stmt)

            if is_test:
                kind = NodeKind.TEST
            elif in_class:
                kind = NodeKind.METHOD
            else:
                kind = NodeKind.FUNCTION

            node = IRNode(id=qname, kind=kind, name=stmt.name, file=rel, line=stmt.lineno,
                          end_line=getattr(stmt, "end_lineno", stmt.lineno) or stmt.lineno)
            if endpoint:
                node.meta.update(endpoint)
            self._register(node)
            self.doc.add_edge(parent, qname, EdgeKind.CONTAINS)

            if endpoint:
                ep_id = f"endpoint:{endpoint['http_method']} {endpoint['route']}"
                if ep_id not in self._defs:
                    self._register(IRNode(id=ep_id, kind=NodeKind.API_ENDPOINT,
                                          name=ep_id.split(":", 1)[1], file=rel,
                                          line=stmt.lineno, meta=endpoint))
                self.doc.add_edge(qname, ep_id, EdgeKind.EXPOSES)

    def _record_import(self, stmt: ast.Import | ast.ImportFrom, module_qname: str) -> None:
        table = self._imports[module_qname]
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                table[alias.asname or alias.name.split(".")[0]] = alias.name
                self.doc.add_edge(module_qname, alias.name, EdgeKind.IMPORTS)
        else:  # from X import y
            base = stmt.module or ""
            for alias in stmt.names:
                target = f"{base}.{alias.name}" if base else alias.name
                table[alias.asname or alias.name] = target
                if base:
                    self.doc.add_edge(module_qname, base, EdgeKind.IMPORTS)

    # ------------------------------------------------------------------
    # Pass 2
    # ------------------------------------------------------------------

    def _collect_calls(self, module_qname: str, tree: ast.Module) -> None:
        for func_node, caller_qname in _walk_functions(tree, module_qname):
            for call in ast.walk(func_node):
                if isinstance(call, ast.Call):
                    name = _dotted(call.func)
                    if name:
                        self._calls.append((caller_qname, module_qname, name))

    def _resolve_calls(self) -> None:
        seen: set[tuple[str, str]] = set()
        for caller, module_qname, call_text in self._calls:
            target = self._resolve(call_text, module_qname, caller)
            if target and target != caller and (caller, target) not in seen:
                seen.add((caller, target))
                self.doc.add_edge(caller, target, EdgeKind.CALLS)
                # a test that CALLS something also TESTS it
                node = self._defs.get(caller)
                if node and node.kind == NodeKind.TEST:
                    self.doc.add_edge(caller, target, EdgeKind.TESTS)

    def _resolve(self, call_text: str, module_qname: str, caller: str) -> str | None:
        imports = self._imports.get(module_qname, {})
        head, *rest = call_text.split(".")

        # 1. exact import alias:  from app.payments import charge; charge()
        if head in imports:
            candidate = ".".join([imports[head], *rest])
            if candidate in self._defs:
                return candidate
            if imports[head] in self._defs and not rest:
                return imports[head]

        # 2. same module:  helper()
        candidate = f"{module_qname}.{call_text}"
        if candidate in self._defs:
            return candidate

        # 3. same class (methods calling siblings via self.x())
        if head == "self" and rest:
            cls = caller.rsplit(".", 1)[0]
            candidate = f"{cls}.{rest[0]}"
            if candidate in self._defs:
                return candidate

        # 4. unique global short-name match:  Model.method or bare name
        tail = call_text.split(".")[-1]
        matches = self._by_name.get(tail, [])
        if len(matches) == 1:
            return matches[0]

        return None


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------

def _dotted(node: ast.expr) -> str | None:
    """Render Name / Attribute chains as dotted text: pay.charge -> 'pay.charge'."""
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _endpoint_info(func: ast.FunctionDef | ast.AsyncFunctionDef) -> dict | None:
    """Detect FastAPI/Flask style decorators: @app.get('/x'), @router.post('/y'), @app.route('/z')."""
    for dec in func.decorator_list:
        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
            method = dec.func.attr.lower()
            if method in _HTTP_METHODS and dec.args:
                arg = dec.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    http = "ANY" if method == "route" else method.upper()
                    return {"http_method": http, "route": arg.value}
    return None


def _walk_functions(tree: ast.Module, module_qname: str):
    """Yield (ast_function_node, qualified_name) for all functions/methods."""
    def visit(body, parent):
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qname = f"{parent}.{stmt.name}"
                yield stmt, qname
                yield from visit(stmt.body, qname)
            elif isinstance(stmt, ast.ClassDef):
                yield from visit(stmt.body, f"{parent}.{stmt.name}")
    yield from visit(tree.body, module_qname)
