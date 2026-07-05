"""
Legion AI Agent Control — orchestrate up to 16 parallel AI agents from a single
Master ROM (prompt). One Manager (strong model) breaks the objective into a Task
Queue and distributes it to Workers (lighter models). A Performance Ledger tracks
each agent's speed, success/error and token usage in real time, powering a
promote/demote system.

Fully INDEPENDENT of Computer-Use / phantom desktop control — these agents are
pure LLM workers running in the background (nothing renders on the user's screen).

LLM calls go through ChatBackend when a model is reachable; otherwise the module
gracefully SIMULATES work so the command center is fully demoable offline.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Request

router = APIRouter(prefix="/api/legion", tags=["legion"])

MAX_AGENTS = 16
BASE_DIR = Path(__file__).resolve().parent
LEGION_DB = str(BASE_DIR / "legion.db")

# Model tiers — Manager uses the strong main model, Workers a lighter/cheaper one.
MANAGER_MODEL = os.getenv("SKEMI_LEGION_MANAGER_MODEL", "") or "devstral-2:123b-cloud"
WORKER_MODEL = os.getenv("SKEMI_LEGION_WORKER_MODEL", "") or "qwen2.5:3b"

MANAGER_SYS = (
    "Bạn là MANAGER trong một đội quân AI. Nhiệm vụ: nhận mục tiêu tổng (Master ROM), "
    "bẻ nhỏ thành các tác vụ con độc lập, rõ ràng, và điều phối. Tư duy chiến lược, ngắn gọn."
)
WORKER_SYS = (
    "Bạn là WORKER trong một đội quân AI. Nhiệm vụ: thực thi MỘT tác vụ con được giao "
    "một cách chính xác, súc tích, trả về kết quả dùng được ngay."
)

# ── Runtime state (single active deployment per process) ─────────────────────
_state: Dict[str, Any] = {
    "deployed": False,
    "rom": "",
    "deploy_id": None,
    "agents": {},          # id -> agent dict
    "tasks": [],           # task queue items
    "phase": "idle",       # idle | planning | working | done
    "started_at": 0,
}
_lock = asyncio.Lock()
_run_task: Optional[asyncio.Task] = None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _est_tokens(text: str) -> int:
    return max(1, int(len(str(text or "")) / 3.5))


def _make_agent(aid: str, role: str) -> Dict[str, Any]:
    return {
        "id": aid,
        "role": role,                          # manager | worker
        "status": "idle",                      # idle | working | error | killed | done
        "current_task": "",
        "log": "",
        "model": MANAGER_MODEL if role == "manager" else WORKER_MODEL,
        "system_prompt": MANAGER_SYS if role == "manager" else WORKER_SYS,
        "metrics": {
            "tasks_done": 0, "success": 0, "error": 0,
            "tokens": 0, "avg_ms": 0, "_total_ms": 0,
        },
    }


def _init_agents(total: int) -> Dict[str, Any]:
    total = max(2, min(MAX_AGENTS, total))
    agents: Dict[str, Any] = {}
    agents["AG-00"] = _make_agent("AG-00", "manager")
    for i in range(1, total):
        wid = f"AG-{i:02d}"
        agents[wid] = _make_agent(wid, "worker")
    return agents


# ── Persistence: performance ledger ──────────────────────────────────────────
def _db() -> sqlite3.Connection:
    con = sqlite3.connect(LEGION_DB)
    con.execute(
        """CREATE TABLE IF NOT EXISTS performance_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT 'guest',
            deploy_id TEXT, agent_id TEXT, role TEXT, section TEXT,
            task TEXT, ok INTEGER, ms INTEGER, tokens INTEGER, ts INTEGER
        )"""
    )
    # Additive migration for databases created before user_id existed.
    cols = {row[1] for row in con.execute("PRAGMA table_info(performance_ledger)").fetchall()}
    if "user_id" not in cols:
        con.execute("ALTER TABLE performance_ledger ADD COLUMN user_id TEXT NOT NULL DEFAULT 'guest'")
    if "section" not in cols:
        con.execute("ALTER TABLE performance_ledger ADD COLUMN section TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS idx_ledger_user ON performance_ledger(user_id, ts DESC)")
    return con


def _resolve_ledger_user_id(request: Optional[Request]) -> str:
    """Attribute a ledger row to the signed-in account. Lazy-imports Server.py's
    (signature-verified) account resolver to avoid a module import cycle —
    Server.py is the one that imports this module, not the other way round,
    so by the time an endpoint actually runs Server is already loaded."""
    if request is None:
        return "guest"
    try:
        import Server as _server_mod  # lazy — see docstring
        acct = _server_mod._resolve_account_id(request)
        return acct or "guest"
    except Exception:
        return "guest"


def _ledger_record(deploy_id: str, agent: Dict[str, Any], task: str, ok: bool, ms: int, tokens: int,
                    user_id: str = "guest", section: str = "") -> None:
    try:
        con = _db()
        con.execute(
            "INSERT INTO performance_ledger (user_id, deploy_id, agent_id, role, section, task, ok, ms, tokens, ts) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user_id, deploy_id, agent["id"], agent["role"], section, task[:300], 1 if ok else 0, ms, tokens, _now_ms()),
        )
        con.commit()
        con.close()
    except Exception:
        pass


# ── LLM bridge (graceful) ─────────────────────────────────────────────────────
async def _llm(model: str, prompt: str, timeout: float = 40.0) -> tuple[Optional[str], int]:
    """Return (text, tokens) from the backend model, or (None, 0) if unreachable."""
    try:
        import ChatBackend as backend  # imported lazily to avoid cycles
        if hasattr(backend, "_generate_text_once"):
            out = await backend._generate_text_once(model, prompt, timeout=timeout, num_predict=512)
            if out and str(out).strip():
                txt = str(out).strip()
                return txt, _est_tokens(prompt) + _est_tokens(txt)
    except Exception:
        pass
    return None, 0


def _parse_task_list(raw: str) -> List[str]:
    if not raw:
        return []
    # try JSON array first
    m = re.search(r"\[[\s\S]*\]", raw)
    if m:
        try:
            arr = json.loads(m.group(0))
            if isinstance(arr, list):
                out = [str(x).strip() for x in arr if str(x).strip()]
                if out:
                    return out[:14]
        except Exception:
            pass
    # fallback: split lines / bullets
    lines = [re.sub(r"^[\s\-\*\d\.\)]+", "", ln).strip() for ln in raw.splitlines()]
    return [ln for ln in lines if len(ln) > 6][:14]


# ── Orchestration ────────────────────────────────────────────────────────────
async def _manager_plan(rom: str, n_workers: int) -> tuple[List[str], int]:
    n = max(3, min(n_workers, 10))
    prompt = (
        f"{MANAGER_SYS}\n\nMục tiêu tổng (Master ROM):\n{rom}\n\n"
        f"Hãy bẻ nhỏ thành đúng {n} tác vụ con độc lập, ngắn gọn. "
        f'Trả về DUY NHẤT một JSON array các chuỗi, ví dụ ["tác vụ 1","tác vụ 2"].'
    )
    out, toks = await _llm(MANAGER_MODEL, prompt, timeout=45.0)
    tasks = _parse_task_list(out) if out else []
    if not tasks:
        # Simulated decomposition so the command center works offline.
        verbs = ["Nghiên cứu", "Phân tích", "Tổng hợp", "Đối chiếu nguồn cho", "Soạn thảo phần", "Kiểm thử ý tưởng",
                 "Lập dàn ý", "Đánh giá rủi ro", "Đề xuất giải pháp cho", "Mô phỏng kịch bản"]
        topic = (rom[:70] + "…") if len(rom) > 70 else rom
        tasks = [f"{verbs[i % len(verbs)]}: {topic}" for i in range(n)]
    return tasks, toks


async def _worker_run(deploy_id: str, agent: Dict[str, Any], task: str, user_id: str = "guest", section: str = "") -> None:
    if agent["status"] == "killed":
        return
    agent["status"] = "working"
    agent["current_task"] = task
    agent["log"] = "Đang xử lý…"
    t0 = _now_ms()
    out, toks = await _llm(agent["model"], f"{agent['system_prompt']}\n\nTác vụ: {task}\n\nKết quả súc tích:")
    ok = True
    if out is None:
        # simulate latency + result
        await asyncio.sleep(random.uniform(0.7, 2.6))
        out = f"[mô phỏng • {agent['model'].split(':')[0]}] Đã hoàn thành: {task}"
        toks = random.randint(140, 620)
        ok = random.random() > 0.06  # ~6% simulated failure
        if not ok:
            out = f"[mô phỏng] Lỗi tạm thời khi xử lý: {task} — sẽ thử lại."
    if agent["status"] == "killed":
        return
    ms = _now_ms() - t0
    m = agent["metrics"]
    m["tasks_done"] += 1
    m["success" if ok else "error"] += 1
    m["tokens"] += toks
    m["_total_ms"] += ms
    m["avg_ms"] = m["_total_ms"] // max(1, m["tasks_done"])
    agent["log"] = str(out)[:500]
    agent["status"] = "error" if not ok else "idle"
    agent["current_task"] = "" if ok else task
    _ledger_record(deploy_id, agent, task, ok, ms, toks, user_id=user_id, section=section)


async def _orchestrate(deploy_id: str, rom: str, user_id: str = "guest", section: str = "") -> None:
    try:
        mgr = next((a for a in _state["agents"].values() if a["role"] == "manager"), None)
        workers = [a for a in _state["agents"].values() if a["role"] == "worker" and a["status"] != "killed"]
        if not mgr or not workers:
            _state["phase"] = "done"
            return

        _state["phase"] = "planning"
        mgr["status"] = "working"
        mgr["current_task"] = "Đang bẻ nhỏ Master ROM thành tác vụ…"
        mgr["log"] = "Phân rã mục tiêu tổng."
        plan, toks = await _manager_plan(rom, len(workers))
        mgr["metrics"]["tokens"] += toks
        mgr["status"] = "idle"
        mgr["current_task"] = ""
        mgr["log"] = f"Đã tạo {len(plan)} tác vụ, đang điều phối."

        _state["tasks"] = [
            {"id": f"T{idx:02d}", "task": t, "status": "queued", "agent": None}
            for idx, t in enumerate(plan)
        ]

        _state["phase"] = "working"

        async def run_item(item: Dict[str, Any], worker: Dict[str, Any]) -> None:
            if worker["status"] == "killed":
                item["status"] = "skipped"
                return
            item["status"] = "running"
            item["agent"] = worker["id"]
            await _worker_run(deploy_id, worker, item["task"], user_id=user_id, section=section)
            item["status"] = "done"

        # round-robin distribute across live workers, run concurrently
        coros = []
        live = [w for w in workers if w["status"] != "killed"]
        for i, item in enumerate(_state["tasks"]):
            w = live[i % len(live)]
            coros.append(run_item(item, w))
        await asyncio.gather(*coros, return_exceptions=True)

        _state["phase"] = "done"
        if mgr["status"] != "killed":
            mgr["log"] = "Hoàn tất chiến dịch. Sẵn sàng ROM mới."
    except Exception as exc:  # noqa: BLE001
        _state["phase"] = "done"
        try:
            mgr = next((a for a in _state["agents"].values() if a["role"] == "manager"), None)
            if mgr:
                mgr["log"] = f"Lỗi điều phối: {exc}"
        except Exception:
            pass


# ── API ───────────────────────────────────────────────────────────────────────
@router.post("/deploy")
async def deploy(request: Request, payload: Dict[str, Any] = Body(...)):
    global _run_task
    rom = str(payload.get("rom", "")).strip()
    total = int(payload.get("agents", payload.get("total", 16)) or 16)
    if not rom:
        return {"success": False, "error": "Master ROM trống."}
    user_id = _resolve_ledger_user_id(request)
    async with _lock:
        if _run_task and not _run_task.done():
            _run_task.cancel()
        deploy_id = uuid.uuid4().hex[:12]
        _state.update({
            "deployed": True, "rom": rom, "deploy_id": deploy_id,
            "agents": _init_agents(total), "tasks": [], "phase": "planning",
            "started_at": _now_ms(),
        })
    _run_task = asyncio.create_task(_orchestrate(deploy_id, rom, user_id=user_id, section="deploy"))
    return {"success": True, "deploy_id": deploy_id, "agents": list(_state["agents"].keys())}


@router.get("/state")
async def state():
    return {
        "deployed": _state["deployed"],
        "phase": _state["phase"],
        "rom": _state["rom"],
        "deploy_id": _state["deploy_id"],
        "agents": list(_state["agents"].values()),
        "tasks": _state["tasks"],
    }


def _agent(aid: str) -> Optional[Dict[str, Any]]:
    return _state["agents"].get(aid)


@router.post("/promote/{aid}")
async def promote(aid: str):
    a = _agent(aid)
    if not a:
        return {"success": False, "error": "Agent không tồn tại."}
    a["role"] = "manager"
    a["model"] = MANAGER_MODEL
    a["system_prompt"] = MANAGER_SYS
    a["log"] = "Đã THĂNG CHỨC → Manager (bẻ task & điều phối)."
    return {"success": True, "agent": a}


@router.post("/demote/{aid}")
async def demote(aid: str):
    a = _agent(aid)
    if not a:
        return {"success": False, "error": "Agent không tồn tại."}
    a["role"] = "worker"
    a["model"] = WORKER_MODEL
    a["system_prompt"] = WORKER_SYS
    a["log"] = "Đã HẠ BỆ → Worker (thực thi tác vụ)."
    return {"success": True, "agent": a}


@router.post("/kill/{aid}")
async def kill(aid: str):
    a = _agent(aid)
    if not a:
        return {"success": False, "error": "Agent không tồn tại."}
    a["status"] = "killed"
    a["current_task"] = ""
    a["log"] = "Tiến trình đã bị DỪNG."
    return {"success": True, "agent": a}


@router.post("/stop")
async def stop_all():
    global _run_task
    if _run_task and not _run_task.done():
        _run_task.cancel()
    for a in _state["agents"].values():
        if a["status"] in ("working",):
            a["status"] = "idle"
            a["current_task"] = ""
    _state["phase"] = "done"
    return {"success": True}


# ── Cross-section squad runner ────────────────────────────────────────────────
# Other sections (Search, Studio, Lab, …) call this when the user's "multi_agent"
# skill is on: instead of a single AI call, a Legion squad runs the task — a
# Manager decomposes it, Workers execute the sub-tasks in parallel (real LLM
# calls), then the Manager SYNTHESISES one final result. Stateless / ephemeral so
# it never disturbs the live dashboard deployment.

# Workers use the reliable main model here (correctness over cost) so results are
# real, not a stub.
SQUAD_WORKER_MODEL = os.getenv("SKEMI_LEGION_SQUAD_WORKER_MODEL", "") or MANAGER_MODEL


_BOSS_POSITIONS = {"sếp", "sep", "quản lý", "quan ly", "manager", "boss", "giám đốc", "giam doc"}

# ── Live activity board ─────────────────────────────────────────────────────
# Every squad run (from ANY section) registers here so Legion can show, in real
# time, WHICH section is working, WHAT each named agent is doing (its sub-goal),
# its status and token spend. Capped, newest first.
_activity_runs: List[Dict[str, Any]] = []
_ACTIVITY_CAP = 24

SECTION_LABELS = {
    "search": "Tra cứu", "studio": "Studio", "home": "Studio", "chat": "Chat",
    "lab": "Phòng thí nghiệm", "cli": "Skemi CLI", "workspace": "Skemi CLI",
    "quiz": "Quiz", "legion": "Legion", "widget": "Trợ lý nổi", "": "Khác",
}


def _register_activity(section: str, goal: str, agents: List[Dict[str, Any]]) -> Dict[str, Any]:
    run = {
        "run_id": uuid.uuid4().hex[:10],
        "section": section or "",
        "section_label": SECTION_LABELS.get((section or "").lower(), section or "Khác"),
        "goal": goal,
        "started_at": _now_ms(),
        "status": "working",
        "agents": agents,          # list of mutable per-agent records
    }
    _activity_runs.insert(0, run)
    del _activity_runs[_ACTIVITY_CAP:]
    return run


async def _squad_worker(aid: str, name: str, function: str, system_prompt: str, subtask: str,
                        arec: Optional[Dict[str, Any]] = None,
                        deploy_id: str = "", user_id: str = "guest", section: str = "") -> Dict[str, Any]:
    t0 = _now_ms()
    if arec is not None:
        arec["status"] = "working"
    sysp = (system_prompt or "").strip() or WORKER_SYS
    if function:
        sysp += f"\nChức vụ/vai của bạn: {function}."
    out, toks = await _llm(SQUAD_WORKER_MODEL, f"{sysp}\n\nTÁC VỤ: {subtask}\n\nKết quả dùng được ngay:", timeout=75.0)
    ms = _now_ms() - t0
    ok = bool(out and str(out).strip())
    if arec is not None:
        arec["status"] = "done" if ok else "error"
        arec["tokens"] = toks
        arec["ms"] = ms
    # Logged HERE (as soon as this one agent finishes), not after the whole
    # squad's asyncio.gather() completes — so if the request gets cancelled
    # mid-run (user closed the tab), whichever agents DID finish before that
    # are still on the record instead of the entire run vanishing untracked.
    _ledger_record(deploy_id, {"id": aid, "role": "worker"}, subtask, ok, ms, toks, user_id=user_id, section=section)
    return {
        "id": aid, "name": name or aid, "role": "worker", "function": function or "Thực thi",
        "task": subtask, "output": str(out).strip() if ok else "",
        "ok": ok, "ms": ms, "tokens": toks,
    }


async def _manager_synthesize(task: str, results: List[Dict[str, Any]], mgr_name: str = "", mgr_sys: str = "") -> tuple[Optional[str], int]:
    joined = "\n\n".join(f"[{r.get('name') or r['id']} • {r['function']}] (tác vụ: {r['task']})\n{r['output']}"
                         for r in results if r.get("output"))
    if not joined:
        return None, 0
    head = (mgr_sys.strip() or MANAGER_SYS)
    prompt = (
        head +
        (f"\nBạn là {mgr_name} — người chỉ huy đội này." if mgr_name else "") +
        f"\n\nMỤC TIÊU TỔNG: {task}\n\nKết quả thô từ các thành viên trong đội:\n{joined}\n\n"
        "Hãy TỔNG HỢP thành MỘT kết quả cuối cùng mạch lạc, đầy đủ, loại trùng lặp, "
        "giải quyết mâu thuẫn nếu có. Chỉ trả nội dung tổng hợp dùng được ngay."
    )
    return await _llm(MANAGER_MODEL, prompt, timeout=80.0)


def _parse_agents_spec(payload: Dict[str, Any]) -> tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split a user roster of named agents into (manager, workers) by position."""
    spec = payload.get("agents_spec")
    if not isinstance(spec, list) or not spec:
        return None, []
    managers, workers = [], []
    for a in spec:
        if not isinstance(a, dict):
            continue
        pos = str(a.get("position") or "").strip()
        entry = {"name": str(a.get("name") or "Agent").strip(), "position": pos,
                 "system_prompt": str(a.get("system_prompt") or "").strip(),
                 "id": str(a.get("id") or "")}
        (managers if pos.lower() in _BOSS_POSITIONS else workers).append(entry)
    manager = managers[0] if managers else None
    # extra managers fall back to acting as workers so nobody is idle
    workers = managers[1:] + workers
    return manager, workers


@router.post("/run-task")
async def run_task(request: Request, payload: Dict[str, Any] = Body(...)):
    task = str(payload.get("task", "")).strip()
    if not task:
        return {"success": False, "error": "Thiếu task."}
    user_id = _resolve_ledger_user_id(request)

    # Preferred: a full named-agent roster (name + position + system prompt) from the
    # Legion org chart. Falls back to a plain roster of strings, then to a count.
    manager_spec, worker_specs = _parse_agents_spec(payload)
    if worker_specs:
        n_workers = max(1, min(len(worker_specs), MAX_AGENTS - 1))
        worker_specs = worker_specs[:n_workers]
        roster_fns = [w["position"] or w["name"] for w in worker_specs]
    else:
        n = max(2, min(int(payload.get("agents", 4) or 4), MAX_AGENTS))
        n_workers = n - 1
        raw_roster = payload.get("roster") if isinstance(payload.get("roster"), list) else []
        roster_fns = []
        for item in raw_roster:
            if isinstance(item, str):
                roster_fns.append(item.strip())
            elif isinstance(item, dict):
                roster_fns.append(str(item.get("function") or item.get("role") or "").strip())
        worker_specs = None

    deploy_id = uuid.uuid4().hex[:12]
    section = str(payload.get("section", "")).strip()
    mgr_name = manager_spec["name"] if manager_spec else "Chỉ huy"
    mgr_sys = manager_spec["system_prompt"] if manager_spec else ""
    mgr_id = manager_spec["id"] if manager_spec else "AG-00"

    # 1) Manager decomposes the goal into sub-tasks.
    plan, mtoks = await _manager_plan(task, n_workers)
    if not plan:
        plan = [task]
    plan = plan[:n_workers] if n_workers > 0 else plan

    # Register this run on the live activity board (one record per agent, mutated
    # in place as each finishes → Legion polls /activity and shows it real-time).
    act_agents = [{"id": mgr_id, "name": mgr_name, "role": "manager", "function": "Chỉ huy & tổng hợp",
                   "subtask": "Phân rã mục tiêu & điều phối đội", "status": "working", "tokens": mtoks}]
    worker_recs = []
    for i, sub in enumerate(plan):
        if worker_specs and i < len(worker_specs):
            w = worker_specs[i]
            rec = {"id": w["id"] or f"AG-{i+1:02d}", "name": w["name"], "role": "worker",
                   "function": w["position"] or "Nhân viên", "subtask": sub, "status": "queued", "tokens": 0}
        else:
            fn = roster_fns[i] if i < len(roster_fns) and roster_fns[i] else ""
            rec = {"id": f"AG-{i+1:02d}", "name": f"AG-{i+1:02d}", "role": "worker",
                   "function": fn or "Nhân viên", "subtask": sub, "status": "queued", "tokens": 0}
        worker_recs.append(rec)
        act_agents.append(rec)
    run = _register_activity(section, task, act_agents)

    # 2) Workers execute in parallel — each with its name / role / own system prompt.
    coros = []
    for i, sub in enumerate(plan):
        if worker_specs and i < len(worker_specs):
            w = worker_specs[i]
            coros.append(_squad_worker(w["id"] or f"AG-{i+1:02d}", w["name"], w["position"], w["system_prompt"], sub, worker_recs[i],
                                        deploy_id=deploy_id, user_id=user_id, section=section))
        else:
            fn = roster_fns[i] if i < len(roster_fns) and roster_fns[i] else ""
            coros.append(_squad_worker(f"AG-{i+1:02d}", "", fn, "", sub, worker_recs[i],
                                        deploy_id=deploy_id, user_id=user_id, section=section))
    results = list(await asyncio.gather(*coros, return_exceptions=False))

    # 3) Manager (the boss the user named) synthesises one final answer.
    act_agents[0]["subtask"] = "Đang tổng hợp kết quả của cả đội"
    final, stoks = await _manager_synthesize(task, results, mgr_name, mgr_sys)
    if not final:
        final = "\n\n".join(f"• {r['function']}: {r['output']}" for r in results if r.get("output")) \
            or "Đội quân chưa tạo được kết quả (model có thể đang bận). Hãy thử lại."

    act_agents[0]["status"] = "done"
    act_agents[0]["tokens"] = mtoks + stoks
    run["status"] = "done"
    run["finished_at"] = _now_ms()
    ok_count = sum(1 for r in results if r["ok"])

    # Each worker's ledger row was already written the moment IT finished
    # (inside _squad_worker — so a mid-run cancellation still keeps whatever
    # agents did complete). Only the manager's synthesis step is logged here.
    _ledger_record(deploy_id, {"id": mgr_id, "role": "manager"}, task, True, 0, mtoks + stoks,
                    user_id=user_id, section=section)

    return {
        "success": True,
        "deploy_id": deploy_id,
        "result": final,
        "manager": {"id": mgr_id, "name": mgr_name or "Chỉ huy", "role": "manager",
                    "model": MANAGER_MODEL, "tokens": mtoks + stoks},
        "agents": results,
        "workers_ok": ok_count,
        "worker_count": len(results),
    }


@router.get("/activity")
async def activity():
    """Live board: what every section's squad is doing right now, by agent name."""
    now = _now_ms()
    runs = []
    active_agents = 0
    live_tokens = 0
    for r in _activity_runs:
        ags = r.get("agents", [])
        working = sum(1 for a in ags if a.get("status") == "working")
        active_agents += working
        run_tokens = sum(int(a.get("tokens") or 0) for a in ags)
        if r.get("status") == "working":
            live_tokens += run_tokens
        runs.append({
            "run_id": r["run_id"], "section": r["section"], "section_label": r["section_label"],
            "goal": r["goal"], "status": r["status"],
            "age_ms": now - r["started_at"],
            "tokens": run_tokens,
            "agents": [{"id": a["id"], "name": a["name"], "role": a["role"],
                        "function": a["function"], "subtask": a.get("subtask", ""),
                        "status": a.get("status", "queued"), "tokens": a.get("tokens", 0)} for a in ags],
        })
    active_runs = [r for r in _activity_runs if r.get("status") == "working"]
    sections_active = sorted({r["section_label"] for r in active_runs})
    return {
        "success": True,
        "summary": {
            "active_runs": len(active_runs),
            "active_agents": active_agents,
            "live_tokens": live_tokens,
            "sections_active": sections_active,
        },
        "runs": runs,
    }


@router.get("/leaderboard")
async def leaderboard():
    rows = sorted(
        _state["agents"].values(),
        key=lambda a: (a["metrics"]["success"], -a["metrics"]["avg_ms"] if a["metrics"]["avg_ms"] else 0),
        reverse=True,
    )
    return {"leaderboard": [
        {"id": a["id"], "role": a["role"], **a["metrics"]} for a in rows
    ]}
