"""PyMOL command-line execution with structured console/results feedback.

Uses the same upstream parser as PyMOL's command line. The assistant operates
molecular commands; system shells, script loaders and arbitrary Python remain
outside this interface. Atom-property expressions have a separate AST check.
"""
import ast
import contextlib
import io
import json
import re
import sys
import threading
from pathlib import PurePosixPath
from urllib.parse import urlparse

from pymol import parser as upstream_parser, parsing

BLOCKED = {
    "alias", "api", "assert", "class", "def", "del", "exec", "for", "fork",
    "global", "if", "import", "pass", "python", "quit", "raise", "resume", "run",
    "spawn", "system", "try", "while", "abort", "embed", "skip", "load_embedded",
    "loadall", "set_key", "mdo", "mappend", "log", "log_open", "log_close",
    "wizard", "replace_wizard", "refresh_wizard", "movie.produce",
}
EXPRESSIONS = {"alter": 1, "alter_state": 2, "iterate": 1, "iterate_state": 2, "label": 1}
ATOM_FIELDS = set("name resn resi resv chain segi elem b q color ss vdw formal_charge partial_charge ID index rank model x y z numeric_type text_type stereo flags p s".split())
FUNCTIONS = {"str", "int", "float", "round", "abs", "min", "max", "len", "print"}
MATH = {"sin", "cos", "tan", "sqrt", "log", "exp", "fabs", "ceil", "floor", "pi", "e"}
READ_ONLY = set("count_atoms count_states count_frames count_discrete get get_angle get_bond get_chains get_clip get_dihedral get_distance get_extent get_position get_renderer get_symmetry get_title get_type get_version get_view get_viewport help help_setting id_atom identify index pwd ls dir diagnostics mem phi_psi rms rms_cur intra_rms intra_rms_cur centerofmass".split())
SCRIPT_FORMATS = {"py", "pyc", "pyo", "pml", "p1m", "python"}


class CommandCancelled(RuntimeError):
    pass


class CommandFailure(RuntimeError):
    def __init__(self, result):
        self.result = result
        super().__init__("PyMOL command failed: " + result["command"] + "\n" + result["output"])


class ThreadCapture:
    def __init__(self, original, buffer):
        self.original, self.buffer, self.thread = original, buffer, threading.get_ident()

    def write(self, text):
        if threading.get_ident() == self.thread:
            self.buffer.write(text)
        if self.original:
            return self.original.write(text)
        return len(text)

    def flush(self):
        if self.original:
            self.original.flush()

    def __getattr__(self, name):
        return getattr(self.original, name)


def validate_expression(expression, operation):
    if len(expression) > 2000:
        raise ValueError("The atom expression is too long.")
    try:
        tree = ast.parse(expression, mode="exec")
    except SyntaxError as error:
        raise ValueError("Invalid atom expression: " + str(error)) from None
    allowed_nodes = (ast.Module, ast.Expr, ast.Assign, ast.AugAssign, ast.Name, ast.Load, ast.Store,
                     ast.Constant, ast.BinOp, ast.UnaryOp, ast.BoolOp, ast.Compare, ast.IfExp,
                     ast.Call, ast.keyword, ast.Attribute, ast.Tuple, ast.List, ast.Subscript,
                     ast.Slice, ast.JoinedStr, ast.FormattedValue, ast.operator, ast.unaryop,
                     ast.boolop, ast.cmpop)
    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ValueError("Use an atom-property expression, not a Python script.")
        if isinstance(node, ast.Name) and node.id not in ATOM_FIELDS | FUNCTIONS | {"math", "True", "False", "None"}:
            raise ValueError("Unsupported name in atom expression: " + node.id)
        if isinstance(node, ast.Attribute) and not (isinstance(node.value, ast.Name) and node.value.id == "math" and node.attr in MATH):
            raise ValueError("Arbitrary Python attributes are not atom expressions.")
        if isinstance(node, ast.Call):
            if not ((isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS) or
                    (isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "math" and node.func.attr in MATH)):
                raise ValueError("Unsupported function in atom expression.")
            if any(key.arg not in {"sep", "end"} for key in node.keywords):
                raise ValueError("Unsupported atom-expression function argument.")
        if isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if operation not in {"alter", "alter_state"} or any(not isinstance(t, ast.Name) or t.id not in ATOM_FIELDS for t in targets):
                raise ValueError("Assignments are supported only for atom properties in alter/alter_state.")


def simple_result(value, depth=0):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value[:6000] if isinstance(value, str) else value
    if depth > 3:
        return str(type(value).__name__)
    if isinstance(value, (list, tuple)):
        return [simple_result(v, depth + 1) for v in value[:100]]
    if isinstance(value, dict):
        return {str(k): simple_result(v, depth + 1) for k, v in list(value.items())[:100]}
    return str(value)[:1000]


class NativeCommands:
    def __init__(self, cmd):
        self.cmd = cmd
        self.parser = upstream_parser.Parser(cmd)
        self.names = sorted(name for name in cmd.keyword if not name.startswith("_") and name not in BLOCKED
                            and (cmd.keyword[name][4] < parsing.LITERAL or name in EXPRESSIONS)
                            and cmd.keyword[name][4] != parsing.PYTHON)

    def prepare(self, text):
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise ValueError("A PyMOL command must contain 1–8,000 characters.")
        if any(ord(c) < 32 and c not in "\n\t\r" for c in text):
            raise ValueError("Control characters are not supported in commands.")
        prepared = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            first = line.split(None, 1)[0]
            # Literal atom expressions own their semicolons; normal commands use
            # upstream's quote-aware splitter to support ordinary PML batches.
            parts = [line] if first in EXPRESSIONS else parsing.split(line, ";")
            for part in parts:
                part = part.strip()
                if not part or part.startswith("#"):
                    continue
                name, _, rest = part.partition(" ")
                if name not in self.names:
                    raise ValueError("Not an available assistant PyMOL command: " + name + ". Use exact molecular command names; Python and shell/script execution are not assistant tools.")
                if rest.lstrip().split(" ", 1)[0] in upstream_parser.py_delims or part.endswith("\\"):
                    raise ValueError("Python statements and line continuations are not molecular commands.")
                arguments = parsing.parse_arg(part, mode=self.cmd.keyword[name][4], _self=self.cmd)
                if any(key and (key.startswith("_") or key in {"space", "callback"}) for key, value in arguments):
                    raise ValueError("Internal Python arguments are not available to assistant commands.")
                secure = 1
                if name in EXPRESSIONS:
                    position = EXPRESSIONS[name]
                    positional = [value for key, value in arguments if key is None]
                    expression = dict((key, value) for key, value in arguments if key).get("expression")
                    if expression is None:
                        expression = positional[position] if len(positional) > position else None
                    if expression is None:
                        raise ValueError("The atom expression is missing.")
                    validate_expression(expression, name)
                    secure = 0
                if name in {"save", "png", "mpng"}:
                    secure = 0
                if name in {"set", "unset"} and rest.split(",", 1)[0].strip().lower() == "security":
                    raise ValueError("Changing PyMOL's security setting is outside molecular control.")
                if name in {"load", "load_traj", "load_png", "load_mtz"}:
                    values = dict((key, value) for key, value in arguments if key)
                    filename = values.get("filename", next((value for key, value in arguments if key is None), ""))
                    suffixes = PurePosixPath(urlparse(filename.strip("\"'")).path.lower()).suffixes
                    if any(s.lstrip(".") in SCRIPT_FORMATS for s in suffixes) or values.get("format", "").strip("\"'").lower() in SCRIPT_FORMATS:
                        raise ValueError("The assistant loads molecular data, not Python/PML scripts.")
                if name == "fetch":
                    if any(key in {"host", "url"} for key, value in arguments):
                        raise ValueError("Use PyMOL's standard structure download host.")
                    async_values = [value for key, value in arguments if key in {"async", "async_"}]
                    if async_values and any(v.strip() not in {"0", "False", "false"} for v in async_values):
                        raise ValueError("Assistant fetch commands must wait for completion (async_=0).")
                    if not async_values:
                        part += ", async_=0"
                prepared.append({"text": part, "name": name, "secure": secure})
        if not prepared or len(prepared) > 32:
            raise ValueError("Use 1–32 PyMOL commands in one command action.")
        return prepared

    def changes_scene(self, prepared):
        return any(item["name"] not in READ_ONLY for item in prepared)

    def execute(self, prepared, cancelled=None):
        outputs = []
        self.last_results = outputs
        for item in prepared:
            if cancelled and cancelled.is_set():
                raise CommandCancelled("Stopped before the next command. Completed changes remain in the scene.")
            # Discard pending feedback from earlier manual operations so it is
            # not misattributed to this command or sent as its tool result.
            self.cmd._get_feedback()
            buffer = io.StringIO()
            print("PyMOL AI> " + item["text"])
            with contextlib.redirect_stdout(ThreadCapture(sys.stdout, buffer)), contextlib.redirect_stderr(ThreadCapture(sys.stderr, buffer)):
                parsed = self.parser.parse(item["text"], secure=item["secure"])
                result = simple_result(self.parser.result)
            feedback = self.cmd._get_feedback() or []
            lines, seen = [], set()
            for line in (buffer.getvalue() + "\n".join(feedback)).splitlines():
                key = line.strip()
                if key and not key.startswith("PyMOL AI>") and key not in seen:
                    lines.append(line)
                    seen.add(key)
            output = "\n".join(lines).strip()[:10_000]
            ok = parsed == 1 and not re.search(r"(?im)^\s*(?:[\w-]+-)?Error\s*:", output)
            record = {"command": item["text"], "ok": ok, "output": output, "result": result}
            outputs.append(record)
            if not ok:
                raise CommandFailure(record)
        return outputs
