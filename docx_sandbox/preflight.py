import ast
from dataclasses import dataclass

ALLOWED_IMPORT_ROOTS = {"docx", "json", "math", "statistics", "decimal", "fractions", "datetime", "textwrap", "re", "collections", "itertools", "typing"}
FORBIDDEN_ROOTS = {"subprocess", "socket", "requests", "urllib", "httpx", "ftplib", "paramiko", "ctypes", "cffi", "pickle", "marshal", "dill"}
FORBIDDEN_NAMES = {"eval", "exec", "compile", "__import__", "breakpoint"}
FORBIDDEN_ATTRS = {"system", "popen", "spawn", "fork", "execv", "execve", "execl", "execle", "execvp", "putenv", "getenv", "environ", "urandom", "symlink", "link", "mknod", "mkfifo"}


@dataclass(frozen=True)
class PolicyIssue:
    code: str
    line: int
    column: int
    detail: str


@dataclass(frozen=True)
class PolicyReport:
    allowed: bool
    issues: tuple[PolicyIssue, ...]
    node_count: int


class ProgramPolicyVisitor(ast.NodeVisitor):
    def __init__(self, max_nodes: int = 25_000):
        self.issues: list[PolicyIssue] = []
        self.node_count = 0
        self.max_nodes = max_nodes

    def visit(self, node):
        self.node_count += 1
        if self.node_count > self.max_nodes:
            self._issue("node_limit", node, "program has too many syntax nodes")
            return
        return super().visit(node)

    def _issue(self, code, node, detail):
        if len(self.issues) < 50:
            self.issues.append(PolicyIssue(code, getattr(node, "lineno", 1), getattr(node, "col_offset", 0), detail))

    def visit_Import(self, node):
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            if root in FORBIDDEN_ROOTS or root not in ALLOWED_IMPORT_ROOTS:
                self._issue("forbidden_import", node, f"import of {root!r} is not allowed")
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        root = (node.module or "").split(".", 1)[0]
        if node.level or root in FORBIDDEN_ROOTS or root not in ALLOWED_IMPORT_ROOTS:
            self._issue("forbidden_import", node, "relative or unapproved import")
        self.generic_visit(node)

    def visit_Call(self, node):
        name = self._qualified_name(node.func)
        root = name.split(".", 1)[0]
        if name in FORBIDDEN_NAMES or root in FORBIDDEN_ROOTS or any(part in FORBIDDEN_ATTRS for part in name.split(".")):
            self._issue("forbidden_call", node, "call is not allowed")
        if name == "open":
            if not node.args or not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
                self._issue("dynamic_path", node, "open requires a literal approved path")
            elif not (node.args[0].value.startswith("/output/") or node.args[0].value.startswith("/assets/")):
                self._issue("path_outside_sandbox", node, "path is outside /assets or /output")
        self.generic_visit(node)

    def _qualified_name(self, node):
        if isinstance(node, ast.Name): return node.id
        if isinstance(node, ast.Attribute):
            parent = self._qualified_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr
        return "<dynamic>"


def inspect_program(source: str, *, max_nodes: int = 25_000, max_depth: int = 100) -> PolicyReport:
    try:
        tree = ast.parse(source.replace("\r\n", "\n").replace("\r", "\n"), mode="exec")
    except (SyntaxError, ValueError, RecursionError) as exc:
        return PolicyReport(False, (PolicyIssue("syntax_error", getattr(exc, "lineno", 1) or 1, getattr(exc, "offset", 0) or 0, "invalid program syntax"),), 0)
    visitor = ProgramPolicyVisitor(max_nodes)
    visitor.visit(tree)
    def depth(node, current=0):
        return max([current] + [depth(child, current + 1) for child in ast.iter_child_nodes(node)])
    if depth(tree) > max_depth:
        visitor.issues.append(PolicyIssue("syntax_depth", 1, 0, "program nesting is too deep"))
    return PolicyReport(not visitor.issues, tuple(visitor.issues), visitor.node_count)
