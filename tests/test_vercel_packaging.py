"""Regression tests for Vercel deployment packaging."""

from pathlib import Path


RUNTIME_DIRS = {
    "agents",
    "config",
    "constants",
    "database",
    "prompts",
    "schemas",
    "services",
    "storage",
    "ui",
    "utils",
    "workflows",
}


def test_vercelignore_does_not_exclude_runtime_packages():
    ignore_file = Path(".vercelignore")
    ignored_paths = {
        line.strip().lstrip("/")
        for line in ignore_file.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    ignored_runtime_dirs = {
        runtime_dir
        for runtime_dir in RUNTIME_DIRS
        if runtime_dir in ignored_paths or f"{runtime_dir}/" in ignored_paths
    }

    assert ignored_runtime_dirs == set()


def test_whatsapp_workflow_entrypoint_imports():
    from workflows.api import process_whatsapp_message

    assert process_whatsapp_message.__name__ == "process_whatsapp_message"
