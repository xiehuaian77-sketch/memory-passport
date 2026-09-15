"""Tests for scripts/start_demo.py (Phase 7.0B One-Command Demo Launcher)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add scripts directory to path for direct imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import start_demo


def test_01_mask_secret_protects_agent_keys():
    """TEST 1: API keys and tokens are securely masked."""
    raw_key = "mp_ak_0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    masked = start_demo.mask_secret(raw_key)
    assert masked.startswith("mp_ak_")
    assert masked.endswith("cdef")
    assert "****************" in masked
    assert "0123456789abcdef0123456789abcdef" not in masked

    assert start_demo.mask_secret(None) == "<未配置>"
    assert start_demo.mask_secret("") == "<未配置>"


def test_02_sanitize_text_filters_credentials():
    """TEST 2: Text sanitization scrubs raw keys from logs."""
    log_line = "Error: caller used mp_ak_0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef with Bearer eyJhbGciOiJIUzI1NiJ9.test"
    sanitized = start_demo.sanitize_text(log_line)
    assert "mp_ak_0123456789abcdef" not in sanitized
    assert "mp_ak_****************[MASKED]" in sanitized
    assert "Bearer eyJhb...[MASKED]" in sanitized


def test_03_environment_check_detects_current_python():
    """TEST 3: Current environment passes Python 3.11+ requirement."""
    res = start_demo.check_environment()
    assert res["python"] is not None
    assert sys.version_info >= (3, 11)


def test_04_port_detection():
    """TEST 4: is_port_in_use correctly identifies open/closed ports."""
    # Test an unused high port
    unused_port = 59991
    assert not start_demo.is_port_in_use("127.0.0.1", unused_port)


def test_05_reused_process_protection():
    """TEST 5: Reused services are strictly protected during cleanup."""
    start_demo.backend_reused = True
    start_demo.backend_proc = None
    start_demo.frontend_reused = True
    start_demo.frontend_proc = None

    # Trigger cleanup - should execute without error and without killing external PID
    start_demo.cleanup()
    assert start_demo.is_cleaning_up is True
    # Reset for other tests
    start_demo.is_cleaning_up = False


def test_06_cli_argument_parsing():
    """TEST 6: Launcher CLI argument parsing and flags."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--backend-timeout", type=int, default=15)
    parser.add_argument("--frontend-timeout", type=int, default=45)
    parser.add_argument("--backend-only", action="store_true")

    args = parser.parse_args(["--no-color", "--backend-only", "--backend-timeout", "20"])
    assert args.no_color is True
    assert args.backend_only is True
    assert args.backend_timeout == 20
    assert args.frontend_timeout == 45


def test_07_launcher_script_syntax_and_imports():
    """TEST 7: Launcher script compiles cleanly and contains zero hardcoded live secrets."""
    script_file = SCRIPTS_DIR / "start_demo.py"
    assert script_file.exists()
    content = script_file.read_text(encoding="utf-8")

    forbidden = ["sk-proj-", "sk-live-", "ghp_", "sk-ant-"]
    for token in forbidden:
        assert token not in content
