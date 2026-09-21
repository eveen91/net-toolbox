import ast
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import main
from ipam.repository import IpamRepository
from ipam.service import IpamService, IpamServiceError

SERVER_ROOT = Path(__file__).parents[1]
PROJECT_ROOT = SERVER_ROOT.parent
IPAM_ROOT = SERVER_ROOT / "ipam"
FRONTEND_IPAM_ROOT = PROJECT_ROOT / "src" / "tools" / "ipam"


def test_ipam_routes_are_registered_once():
    routes = Counter(
        (method, route.path)
        for route in main.app.routes
        if route.path.startswith("/api/ipam")
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    )
    assert routes
    assert [route for route, count in routes.items() if count != 1] == []


def test_main_has_no_ipam_route_decorators():
    tree = ast.parse((SERVER_ROOT / "main.py").read_text())
    decorated_paths = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not decorator.args:
                continue
            path = decorator.args[0]
            if isinstance(path, ast.Constant) and isinstance(path.value, str):
                decorated_paths.append(path.value)
    assert not [path for path in decorated_paths if path.startswith("/api/ipam")]


def test_router_uses_service_instead_of_database_module():
    tree = ast.parse((IPAM_ROOT / "router.py").read_text())
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "db" not in imported_modules
    assert not any(
        isinstance(node, ast.ImportFrom) and node.module == "db"
        for node in ast.walk(tree)
    )
    assert not any(
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "scans"
        and node.attr in {"repository", "SCAN_EXECUTOR", "SCANS_IN_PROGRESS", "SCAN_JOBS"}
        for node in ast.walk(tree)
    )


def test_service_translates_repository_value_error():
    repository = Mock()
    repository.create_subnet.side_effect = ValueError("overlapping subnet")
    service = IpamService(repository)

    with pytest.raises(IpamServiceError, match="overlapping subnet") as error:
        service.create_subnet("10.0.0.0/24", None, None)

    assert isinstance(error.value.__cause__, ValueError)


def test_repository_delegates_representative_operations():
    database = SimpleNamespace(
        SCAN_CONCURRENCY_MIN=1,
        SCAN_CONCURRENCY_MAX=256,
        SCAN_JOB_TIMEOUT_SECONDS=3600,
        create_subnet=Mock(return_value={"id": 7}),
        list_subnets=Mock(return_value=[{"id": 7}]),
        update_scan_job=Mock(return_value=True),
    )
    repository = IpamRepository(database)

    assert repository.create_subnet("10.0.0.0/24", 10, "office") == {"id": 7}
    assert repository.list_subnets() == [{"id": 7}]
    assert repository.update_scan_job("job-1", status="done") is True
    database.create_subnet.assert_called_once_with("10.0.0.0/24", 10, "office")
    database.list_subnets.assert_called_once_with()
    database.update_scan_job.assert_called_once_with("job-1", status="done")


def test_schemas_import_without_application_modules():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import importlib, sys; importlib.import_module('ipam.schemas'); "
            "assert 'main' not in sys.modules; assert 'ipam.router' not in sys.modules; "
            "assert 'ipam.scan_service' not in sys.modules",
        ],
        cwd=SERVER_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _frontend_dependencies(path):
    source = path.read_text()
    dependencies = set()
    for relative in re.findall(r"from\s+[\"'](\.[^\"']+)[\"']", source):
        candidate = (path.parent / relative).resolve()
        candidates = [candidate]
        if candidate.suffix == "":
            candidates.extend(candidate.with_suffix(suffix) for suffix in (".js", ".jsx"))
            candidates.extend(candidate / f"index{suffix}" for suffix in (".js", ".jsx"))
        target = next((item for item in candidates if item.is_file()), None)
        if target is not None and FRONTEND_IPAM_ROOT in target.parents:
            dependencies.add(target)
    return dependencies


def test_ipam_frontend_imports_are_acyclic():
    files = set(FRONTEND_IPAM_ROOT.rglob("*.js")) | set(FRONTEND_IPAM_ROOT.rglob("*.jsx"))
    graph = {path.resolve(): _frontend_dependencies(path) for path in files}
    visiting = set()
    visited = set()

    def visit(path, chain):
        if path in visiting:
            cycle_start = chain.index(path)
            cycle = chain[cycle_start:] + [path]
            pytest.fail(" -> ".join(item.relative_to(PROJECT_ROOT).as_posix() for item in cycle))
        if path in visited:
            return
        visiting.add(path)
        for dependency in graph.get(path, ()):
            visit(dependency, chain + [dependency])
        visiting.remove(path)
        visited.add(path)

    for path in graph:
        visit(path, [path])


def test_ipam_python_imports_are_acyclic():
    modules = {path.stem: path for path in IPAM_ROOT.glob("*.py") if path.name != "__init__.py"}
    graph = {name: set() for name in modules}
    for name, path in modules.items():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
                dependency = node.module.split(".")[0]
                if dependency in modules:
                    graph[name].add(dependency)
    visiting = set()
    visited = set()

    def visit(module, chain):
        if module in visiting:
            cycle_start = chain.index(module)
            pytest.fail(" -> ".join(chain[cycle_start:] + [module]))
        if module in visited:
            return
        visiting.add(module)
        for dependency in graph[module]:
            visit(dependency, chain + [dependency])
        visiting.remove(module)
        visited.add(module)

    for module in graph:
        visit(module, [module])
