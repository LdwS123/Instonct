"""Whole-package checks: every module imports, the entry point is wired, no module name is hidden by a local variable."""
import ast
import importlib
import pkgutil

import instonct


def module_names():
    return [m.name for m in pkgutil.iter_modules(instonct.__path__)]


def test_every_module_imports():
    for name in module_names():
        importlib.import_module(f"instonct.{name}")


def test_entry_point_exists():
    from instonct import runner
    assert callable(runner.main)


def test_no_local_variable_hides_a_module():
    """Cross-module calls are written `module.function(...)`; a local variable with the module's name would silently break them."""
    ours = {n for n in module_names() if n not in ("optional", "extras", "gcal", "habits", "mailtriage", "plus", "screen", "tvremote", "webagent", "whatsapp")}
    for name in ours:
        tree = ast.parse(open(importlib.import_module(f"instonct.{name}").__file__).read())
        for node in ast.walk(tree):
            bound = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                a = node.args
                bound += [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound.append(node.id)
            assert not (set(bound) & ours), f"{name}.py line {getattr(node, 'lineno', '?')} hides a module: {set(bound) & ours}"
