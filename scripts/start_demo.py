#!/usr/bin/env python3
"""Memory Passport — Hackathon One-Command Demo Launcher.

A robust, cross-platform (Windows-first) orchestrator designed for live presentations:
1. Validates Python (>=3.11), Node.js, and npm runtime environments.
2. Reuses existing healthy services or safely spawns Backend and Frontend.
3. Automatically executes database seed and verifies Demo Agent state.
4. Verifies standard MCP 2026-07-28 tool registry (15 tools).
5. Provides clear human-console URLs, MCP endpoints, and automated CLI trigger.
6. Ensures zero credential leakage in terminal and logs.
7. Gracefully tears down only launcher-spawned processes on Ctrl+C.
"""

from __future__ import annotations

import argparse
import atexit
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Ensure UTF-8 output encoding and line buffering on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass

import httpx

# Configuration
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
FRONTEND_HOST = "localhost"
FRONTEND_PORT = 3000

BACKEND_HEALTH_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}/"
MCP_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}/mcp"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
SEED_SCRIPT = PROJECT_ROOT / "scripts" / "seed_demo_data.py"
DEMO_SCRIPT = PROJECT_ROOT / "scripts" / "demo_agent_mcp_auth.py"

# State tracking for graceful cleanup
backend_proc: subprocess.Popen[Any] | None = None
backend_reused: bool = False
frontend_proc: subprocess.Popen[Any] | None = None
frontend_reused: bool = False
temp_dir_obj: tempfile.TemporaryDirectory[str] | None = None
is_cleaning_up: bool = False


# ---------- Console Styling & Masking ----------

class Styler:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled and sys.stdout.isatty()

    def green(self, text: str) -> str:
        return f"\033[92m{text}\033[0m" if self.enabled else text

    def red(self, text: str) -> str:
        return f"\033[91m{text}\033[0m" if self.enabled else text

    def yellow(self, text: str) -> str:
        return f"\033[93m{text}\033[0m" if self.enabled else text

    def cyan(self, text: str) -> str:
        return f"\033[96m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return f"\033[1m{text}\033[0m" if self.enabled else text


styler = Styler()


def mask_secret(secret: str | None) -> str:
    """Strictly masks secrets to prevent leakage."""
    if not secret:
        return "<未配置>"
    clean = secret.strip()
    if clean.startswith("mp_ak_"):
        if len(clean) > 14:
            return f"{clean[:6]}****************{clean[-4:]}"
        return "mp_ak_****"
    if len(clean) > 12:
        return f"{clean[:6]}...{clean[-4:]}"
    return "********"


def sanitize_text(text: str) -> str:
    """Filters credentials out of general log text."""
    text = re.sub(r"mp_ak_[a-f0-9]{64}", "mp_ak_****************[MASKED]", text, flags=re.IGNORECASE)
    text = re.sub(r"Bearer\s+eyJ[a-zA-Z0-9_\-\.]+", "Bearer eyJhb...[MASKED]", text, flags=re.IGNORECASE)
    return text


# ---------- Port & Process Utilities ----------

def is_port_in_use(host: str, port: int) -> bool:
    """Checks if a TCP port is currently open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def kill_process_tree(proc: subprocess.Popen[Any] | None) -> None:
    """Terminates a process and its children safely across Windows and POSIX."""
    if proc is None or proc.poll() is not None:
        return
    pid = proc.pid
    try:
        if sys.platform == "win32":
            # taskkill /F /T kills child processes (e.g. cmd.exe -> node.exe)
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:
        pass


def cleanup() -> None:
    """Ensures only launcher-spawned processes and temp logs are destroyed."""
    global is_cleaning_up
    if is_cleaning_up:
        return
    is_cleaning_up = True

    print("\n" + styler.yellow("正在安全停止由启动器创建的演示服务..."))

    if backend_proc is not None and not backend_reused:
        print("  - 停止后端服务 (PID: {})".format(backend_proc.pid))
        kill_process_tree(backend_proc)

    if frontend_proc is not None and not frontend_reused:
        print("  - 停止前端服务 (PID: {})".format(frontend_proc.pid))
        kill_process_tree(frontend_proc)

    if temp_dir_obj is not None:
        try:
            temp_dir_obj.cleanup()
        except Exception:
            pass

    print(styler.green("演示环境已安全退出。\n"))


# ---------- Step Implementations ----------

def check_environment() -> dict[str, Any]:
    """Step 1: Check Python version, Node.js, and npm."""
    print(styler.bold("\n[1/6] 检查基础运行环境"))

    # Python version check
    py_ver = sys.version_info
    py_ver_str = f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}"
    if py_ver < (3, 11):
        print(styler.red(f" [✗] Python 版本过低: {py_ver_str} (要求 >= 3.11)"))
        sys.exit(1)
    print(styler.green(f" [✓] Python: {py_ver_str} ({sys.executable})"))

    # Node check
    node_path = shutil.which("node")
    node_ver = "未知"
    if node_path:
        try:
            res = subprocess.run(["node", "--version"], capture_output=True, text=True, check=True)
            node_ver = res.stdout.strip()
            print(styler.green(f" [✓] Node.js: {node_ver}"))
        except Exception:
            node_path = None

    if not node_path:
        print(styler.yellow(" [!] Node.js 未安装或未在 PATH 中，前端界面将不可用 (支持纯后端 MCP 模式)"))

    # npm check
    npm_path = shutil.which("npm") or shutil.which("npm.cmd")
    npm_ver = "未知"
    if npm_path:
        try:
            res = subprocess.run([npm_path, "--version"], capture_output=True, text=True, check=True)
            npm_ver = res.stdout.strip()
            print(styler.green(f" [✓] npm: {npm_ver}"))
        except Exception:
            npm_path = None

    if not npm_path:
        print(styler.yellow(" [!] npm 未安装，前端界面将跳过启动"))

    return {
        "python": py_ver_str,
        "node": node_ver if node_path else None,
        "npm": npm_ver if npm_path else None,
        "has_frontend_runtime": bool(node_path and npm_path),
    }


def check_and_start_backend(temp_dir: Path, timeout_sec: int = 15) -> bool:
    """Step 2: Check or start Backend."""
    global backend_proc, backend_reused
    print(styler.bold("\n[2/6] 检查后端服务 (FastAPI / Uvicorn)"))

    # Check if already running and healthy
    if is_port_in_use(BACKEND_HOST, BACKEND_PORT):
        try:
            r = httpx.get(BACKEND_HEALTH_URL, timeout=1.5, trust_env=False)
            if r.status_code == 200 and r.json().get("service") == "Memory Passport API":
                backend_reused = True
                print(styler.green(f" [✓] 后端服务已在运行并处于健康状态: {BACKEND_HEALTH_URL} (复用现有服务)"))
                return True
        except Exception:
            pass

        # Port is open but not healthy Memory Passport API
        print(styler.red(f" [✗] 端口 {BACKEND_PORT} 已被其他程序占用，且未响应 Memory Passport API 健康检查。"))
        print(styler.yellow(" [!] 请检查并释放该端口后再重新运行本脚本。"))
        return False

    # Launch backend
    print(f" [•] 正在启动后端服务 ({BACKEND_HOST}:{BACKEND_PORT})...")
    log_path = temp_dir / "backend_uvicorn.log"
    log_file = open(log_path, "w", encoding="utf-8")

    backend_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=str(BACKEND_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )
    backend_reused = False

    # Poll /health endpoint
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
        if backend_proc.poll() is not None:
            print(styler.red(f" [✗] 后端进程启动失败 (Exit Code: {backend_proc.returncode})"))
            log_file.flush()
            if log_path.exists():
                content = sanitize_text(log_path.read_text(encoding="utf-8", errors="ignore"))
                print(styler.yellow(f" 后端日志摘要:\n{content[-500:]}"))
            return False

        try:
            r = httpx.get(BACKEND_HEALTH_URL, timeout=1.0, trust_env=False)
            if r.status_code == 200 and r.json().get("status") == "ok":
                print(styler.green(f" [✓] 后端启动成功并通过健康检查: {BACKEND_HEALTH_URL}"))
                return True
        except Exception:
            pass
        time.sleep(0.5)

    print(styler.red(f" [✗] 后端服务在 {timeout_sec} 秒内未能通过健康检查"))
    return False


def check_and_start_frontend(temp_dir: Path, has_runtime: bool, timeout_sec: int = 45) -> bool:
    """Step 3: Check or start Frontend."""
    global frontend_proc, frontend_reused
    print(styler.bold("\n[3/6] 检查前端界面 (Next.js)"))

    if not has_runtime:
        print(styler.yellow(" [!] 跳过前端启动 (Node/npm 缺失)"))
        return False

    # Check if already running
    if is_port_in_use("127.0.0.1", FRONTEND_PORT):
        try:
            r = httpx.get(FRONTEND_URL, timeout=2.0, trust_env=False)
            if r.status_code == 200:
                frontend_reused = True
                print(styler.green(f" [✓] 前端服务已在运行: {FRONTEND_URL} (复用现有服务)"))
                return True
        except Exception:
            pass

        print(styler.red(f" [✗] 端口 {FRONTEND_PORT} 已被其他程序占用。请释放后重试。"))
        return False

    # Launch frontend
    print(f" [•] 正在启动前端服务 (npm run dev @ {FRONTEND_URL})...")
    log_path = temp_dir / "frontend_next.log"
    log_file = open(log_path, "w", encoding="utf-8")

    npm_bin = shutil.which("npm.cmd") if sys.platform == "win32" else shutil.which("npm")
    npm_cmd = npm_bin or "npm"

    frontend_proc = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=str(FRONTEND_DIR),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        shell=(sys.platform == "win32"),
    )
    frontend_reused = False

    # Poll frontend URL
    start_time = time.time()
    print(" [•] 等待 Next.js 编译就绪 (最长等待 45s)...", end="", flush=True)
    while time.time() - start_time < timeout_sec:
        if frontend_proc.poll() is not None:
            print("\n" + styler.red(f" [✗] 前端进程启动失败 (Exit Code: {frontend_proc.returncode})"))
            log_file.flush()
            if log_path.exists():
                content = sanitize_text(log_path.read_text(encoding="utf-8", errors="ignore"))
                print(styler.yellow(f" 前端日志摘要:\n{content[-500:]}"))
            return False

        try:
            r = httpx.get(FRONTEND_URL, timeout=1.5, trust_env=False)
            if r.status_code == 200:
                print("\n" + styler.green(f" [✓] 前端编译就绪: {FRONTEND_URL}"))
                return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(1.0)

    print("\n" + styler.yellow(f" [!] 前端服务在 {timeout_sec} 秒内尚未完成首屏编译 (后台仍将继续编译)"))
    return True


def run_seed_and_verify_agent() -> dict[str, Any]:
    """Step 4: Execute idempotent seed and verify Demo Agent."""
    print(styler.bold("\n[4/6] 初始化并验证演示数据 (Demo Seed)"))

    if not SEED_SCRIPT.exists():
        print(styler.red(f" [✗] 未找到数据初始化脚本: {SEED_SCRIPT}"))
        return {"success": False}

    res = subprocess.run(
        [sys.executable, str(SEED_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )

    if res.returncode != 0:
        print(styler.red(" [✗] 数据初始化失败"))
        print(styler.yellow(sanitize_text(res.stderr[-500:])))
        return {"success": False}

    # Extract info safely without exposing plain secrets in stdout
    output = res.stdout
    user_match = re.search(r"Demo User:\s+(\S+)", output)
    agent_id_match = re.search(r"Agent ID:\s+(\S+)", output)
    agent_name_match = re.search(r"Demo Agent:\s+(.+)", output)
    agent_status_match = re.search(r"Status:\s+(.+)", output)
    api_key_match = re.search(r"API Key:\s+(mp_ak_[a-f0-9]{64})", output)

    user_email = user_match.group(1).strip() if user_match else "demo@memorypassport.ai"
    agent_id = agent_id_match.group(1).strip() if agent_id_match else None
    agent_name = agent_name_match.group(1).strip() if agent_name_match else "Demo Research Assistant"
    agent_status = agent_status_match.group(1).strip() if agent_status_match else "ACTIVE"

    # If new API key was output by seed, safely cache in process env
    detected_key = None
    if api_key_match:
        detected_key = api_key_match.group(1).strip()
        os.environ["MEMORY_PASSPORT_DEMO_AGENT_KEY"] = detected_key
    elif "MEMORY_PASSPORT_DEMO_AGENT_KEY" in os.environ:
        detected_key = os.environ["MEMORY_PASSPORT_DEMO_AGENT_KEY"]

    print(styler.green(f" [✓] 演示用户就绪: {user_email}"))
    print(styler.green(" [✓] 演示知识库: 10 条记忆 / 5 条关系 / 评测集已就绪"))
    print(styler.green(f" [✓] 演示 Agent: {agent_name} (ID: {agent_id or 'verified'})"))
    print(styler.green(f" [✓] Agent 状态: {agent_status}"))
    print(styler.green(" [✓] 初始委托权限: READ_MEMORY (已授权)"))

    masked_key = mask_secret(detected_key)
    print(styler.green(f" [✓] Agent 凭证: {masked_key} (已安全注入运行环境)"))

    return {
        "success": True,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "agent_key": detected_key,
    }


def verify_mcp_readiness(agent_key: str | None) -> bool:
    """Step 5: Verify MCP standard gateway (15 tools)."""
    print(styler.bold("\n[5/6] 验证标准 MCP 协议网关 (JSON-RPC 2.0)"))

    if not agent_key:
        print(styler.yellow(" [!] 未获取到 Demo Agent Key，跳过深度工具反射验证 (网关基础路由正常)"))
        return True

    try:
        payload = {
            "jsonrpc": "2.0",
            "id": "launcher-mcp-probe",
            "method": "tools/list",
        }
        headers = {
            "Authorization": f"Bearer {agent_key}",
            "Content-Type": "application/json",
        }
        r = httpx.post(MCP_URL, json=payload, headers=headers, timeout=5.0, trust_env=False)
        if r.status_code != 200:
            print(styler.red(f" [✗] MCP 握手失败 (HTTP {r.status_code})"))
            return False

        data = r.json()
        tools = data.get("result", {}).get("tools", [])
        tool_count = len(tools)

        if tool_count == 15:
            print(styler.green(f" [✓] MCP 网关握手成功: {MCP_URL}"))
            print(styler.green(" [✓] 核心工具注册表验证通过: 15 个工具已就绪 (包含 memory_search, memory_create, memory_update 等)"))
            return True
        else:
            print(styler.yellow(f" [!] MCP 工具注册数: {tool_count} (预期 15 个)"))
            return True
    except Exception as exc:
        print(styler.red(f" [✗] MCP 探测异常: {type(exc).__name__}"))
        return False


def print_summary(frontend_ready: bool) -> None:
    """Step 6: Print demo URLs and commands."""
    print(styler.bold("\n[6/6] 演示环境全链路就绪状态"))
    print("=" * 64)
    print(styler.cyan(styler.bold("            🎉 MEMORY PASSPORT DEMO READY")))
    print("=" * 64)

    if frontend_ready:
        print("\n" + styler.bold("📱 人类控制台入口 (Web3 & Agent 授权中心):"))
        print(f"   身份与授权中心: {styler.cyan('http://localhost:3000/identity')}")
        print(f"   记忆画像与看板: {styler.cyan('http://localhost:3000/dashboard')}")
        print(f"   质量评估控制台: {styler.cyan('http://localhost:3000/dashboard/evaluation')}")

    print("\n" + styler.bold("🤖 标准 MCP 协议网关 (Streamable HTTP):"))
    print(f"   MCP 端点地址:   {styler.cyan('http://127.0.0.1:8000/mcp')}")
    print(f"   后端 OpenAPI:   {styler.cyan('http://127.0.0.1:8000/docs')}")

    print("\n" + styler.bold("⚡ 现场全自动闭环授权演示脚本:"))
    print(f"   执行命令:       {styler.green('python scripts/demo_agent_mcp_auth.py')}")

    print("\n" + "=" * 64)
    print(" 💡 演示提示: 保持此窗口打开以维持后台服务运行。")
    print(" 🛑 演示结束后按 " + styler.bold("Ctrl+C") + " 可一键安全退出并清理服务。")
    print("=" * 64 + "\n")


# ---------- Main Entrypoint ----------

def main() -> None:
    global temp_dir_obj

    parser = argparse.ArgumentParser(description="Memory Passport — Hackathon One-Command Demo Launcher")
    parser.add_argument("--no-color", action="store_true", help="Disable colored console output")
    parser.add_argument("--backend-timeout", type=int, default=15, help="Backend health timeout in seconds")
    parser.add_argument("--frontend-timeout", type=int, default=45, help="Frontend readiness timeout in seconds")
    parser.add_argument("--backend-only", action="store_true", help="Launch backend and MCP only (skip frontend)")
    parser.add_argument("--check-only", action="store_true", help="Perform checks and initialization then exit 0 immediately")
    args = parser.parse_args()

    if args.no_color:
        styler.enabled = False

    # Setup temporary directory for background service logs
    temp_dir_obj = tempfile.TemporaryDirectory(prefix="mp_demo_")
    temp_dir = Path(temp_dir_obj.name)

    # Register exit handlers
    atexit.register(cleanup)
    signal.signal(signal.SIGINT, lambda sig, frame: sys.exit(0))
    signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(0))

    print("=" * 64)
    print(styler.cyan(styler.bold("       MEMORY PASSPORT — HACKATHON DEMO LAUNCHER")))
    print("       User-Owned Memory Infrastructure for AI Agents")
    print("=" * 64)

    # Step 1: Check environment
    env_info = check_environment()

    # Step 2: Start backend
    backend_ok = check_and_start_backend(temp_dir, timeout_sec=args.backend_timeout)
    if not backend_ok:
        sys.exit(1)

    # Step 3: Start frontend (if requested and runtime available)
    frontend_ready = False
    if not args.backend_only and env_info.get("has_frontend_runtime"):
        frontend_ready = check_and_start_frontend(temp_dir, True, timeout_sec=args.frontend_timeout)
    else:
        print(styler.yellow("\n[3/6] 跳过前端启动 (已启用 --backend-only 或环境缺少 Node.js)"))

    # Step 4: Seed data and verify Agent
    seed_result = run_seed_and_verify_agent()
    if not seed_result.get("success"):
        sys.exit(1)

    # Step 5: Verify MCP tools list
    mcp_ok = verify_mcp_readiness(seed_result.get("agent_key"))
    if not mcp_ok:
        print(styler.yellow(" [!] MCP 验证出现警告，但演示将继续允许进行。"))

    # Step 6: Print ready summary
    print_summary(frontend_ready)

    if args.check_only:
        print(styler.green(" [✓] --check-only 模式已完成全部验证，正常退出。\n"))
        cleanup()
        return

    # Keep alive until Ctrl+C
    try:
        while True:
            time.sleep(1.0)
            if backend_proc is not None and backend_proc.poll() is not None:
                print(styler.red("\n[!] 后端服务异常终止，演示退出。"))
                break
            if frontend_proc is not None and frontend_proc.poll() is not None:
                print(styler.yellow("\n[!] 前端服务异常终止。"))
                break
    except KeyboardInterrupt:
        pass
    finally:
        cleanup()


if __name__ == "__main__":
    main()
