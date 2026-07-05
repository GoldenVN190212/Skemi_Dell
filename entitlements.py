"""
Skemi — Entitlements & Token Metering
=====================================

SINGLE SOURCE OF TRUTH for what each subscription tier may do, how many
model tokens it may spend, and how much it has spent. Both the backend
(authoritative enforcement) and the frontend (display + soft gating, via
/api/entitlements) read from here.

Tiers (monthly prices set in Subscription.html):
    free      0đ
    pro       399.000đ
    advanced  999.000đ
    skemi     4.990.000đ

Design notes
------------
* Storage lives in the same SQLite file as auth (skemi_auth.db) so a user's
  plan + usage travel with their account. No external services, stdlib only.
* Token usage is metered at the model call. _raw_generate_once() in
  ChatBackend reads the ollama `prompt_eval_count` + `eval_count` and calls
  note_model_usage(); the active account is carried in a ContextVar that the
  request layer sets, so usage is attributed without threading an account_id
  through every function.
* "Unlimited" is represented by the sentinel UNLIMITED (-1). Fair-use applies.
* Real payment is NOT wired here. set_tier() is the hook a future payment
  webhook (or an admin) calls to grant a tier.
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

# --------------------------------------------------------------------------
# Plan definition  ── EDIT NUMBERS HERE to retune the whole product.
# --------------------------------------------------------------------------

UNLIMITED = -1  # sentinel for "no cap (fair use)"

# Feature keys (gated capabilities), ordered roughly by token cost:
#   search_basic        cheap   web lookup + short brief
#   deep_research       heavy   the vivid multi-module research report
#   studio_basic        cheap   flashcards, mind maps
#   studio_premium      medium  podcast, slides, infographic
#   studio_comic_book   heavy   comic / book generation
#   prompt_agent_full   medium  full-power professional prompt builder
#   skemi_computer      heavy   Phantom virtual-desktop automation
#   beta                –       early access to new features
#   api                 –       programmatic API access

TIERS: Dict[str, Dict[str, Any]] = {
    "free": {
        "label": "Free",
        "price_vnd": 0,
        # DAILY model-token budget (prompt + completion). Resets each day.
        # Bumped to a dev/usage-friendly ceiling: a single deep-research run can
        # burn 10k+ tokens, so 30k blocked real use after ~2 searches (402). 2M/day
        # lets Search actually be used; retune here for production economics.
        "daily_tokens": 2_000_000,
        # GATING PHILOSOPHY: features are NOT the paywall. Every useful/beautiful
        # thing is open to Free so people fall in love with it (we compete with
        # NotebookLM's free unlimited conversions). The real cost ceiling is the
        # DAILY token budget above + the small daily sub-quotas below. We hard-lock
        # only pure-infrastructure / abuse-risk surfaces: Skemi Control (a whole
        # virtual machine), the developer API, and beta access.
        # FEATURE GATING (per the approved 4-tier plan). Heavy/token-hungry
        # features unlock from Pro upward; cheap sticky ones stay open on Free.
        "features": {
            "search_basic": True,        # basic search + 2D map — open
            "deep_research": False,      # → Pro (heavy multi-module research)
            "map_3d": False,             # → Pro (3D knowledge map + gesture)
            "studio_basic": True,        # flashcards + mind maps — open
            "studio_premium": False,     # → Pro (podcast / slides / infographic)
            "studio_comic_book": False,  # → Pro (comic & book)
            "prompt_agent_full": False,  # → Pro (basic prompts stay open)
            "quiz_create": False,        # → Pro (AI quiz generation; play stays open)
            "lab_feasibility": False,    # → Pro
            "legion_squad": False,       # → Pro (3 agents)
            "lab_sandbox": False,        # → Advanced (real code execution)
            "remote_full": False,        # → Advanced
            "legion_full": False,        # → Advanced (full 8 agents)
            "skemi_computer": False,     # → Advanced (Phantom virtual desktop)
            "beta": False,               # → Advanced
            "api": False,                # → Skemi
        },
        # periodic quotas. -1 = unlimited. These keep the heavy operations sane on
        # Free without ever showing a "this feature is for paid users" wall.
        "quotas": {
            "prompts_per_6h": 60,
            "deep_research_per_day": 50,
            "uploads_active": 5,
            "quiz_rooms_active": 3,
            "studio_per_day": 20,
        },
        "priority": 0,   # AI queue weight (higher = served first)
        # Message history (user↔user AND user↔Skemi bot) is kept FOREVER for
        # every tier — text is cheap; we compete with Messenger, not gate it.
        # UNLIMITED here = permanent retention. It is NOT a paywall lever.
        "chat_history_hours": UNLIMITED,
    },
    "pro": {
        "label": "Pro",
        "price_vnd": 399_000,
        # DAILY model-token budget (prompt + completion). Resets each day.
        "daily_tokens": 400_000,
        "features": {
            "search_basic": True, "deep_research": True, "map_3d": True,
            "studio_basic": True, "studio_premium": True, "studio_comic_book": True,
            "prompt_agent_full": True, "quiz_create": True, "lab_feasibility": True,
            "legion_squad": True,        # up to 3 agents (cap enforced client-side)
            "lab_sandbox": False,        # → Advanced
            "remote_full": False,        # → Advanced
            "legion_full": False,        # → Advanced (8 agents)
            "skemi_computer": False,     # → Advanced
            "beta": False, "api": False,
        },
        "quotas": {
            "prompts_per_6h": 100,
            "deep_research_per_day": 50,
            "uploads_active": 25,
            "quiz_rooms_active": 20,
            "studio_per_day": 40,
        },
        "priority": 1,
        "chat_history_hours": UNLIMITED,  # permanent for all tiers
    },
    "advanced": {
        "label": "Advanced",
        "price_vnd": 999_000,
        # DAILY model-token budget (prompt + completion). Resets each day.
        "daily_tokens": 2_000_000,
        "features": {
            "search_basic": True, "deep_research": True, "map_3d": True,
            "studio_basic": True, "studio_premium": True, "studio_comic_book": True,
            "prompt_agent_full": True, "quiz_create": True, "lab_feasibility": True,
            "legion_squad": True, "lab_sandbox": True, "remote_full": True,
            "legion_full": True,         # full 8 agents
            "skemi_computer": True, "beta": True,
            "api": False,                # → Skemi
        },
        "quotas": {
            "prompts_per_6h": UNLIMITED,
            "deep_research_per_day": UNLIMITED,
            "uploads_active": UNLIMITED,
            "quiz_rooms_active": UNLIMITED,
            "studio_per_day": UNLIMITED,
        },
        "priority": 2,
        "chat_history_hours": UNLIMITED,  # permanent for all tiers
    },
    "skemi": {
        "label": "Skemi",
        "price_vnd": 4_990_000,
        # DAILY model-token budget (prompt + completion). Resets each day.
        "daily_tokens": 10_000_000,
        "features": {
            "search_basic": True, "deep_research": True, "map_3d": True,
            "studio_basic": True, "studio_premium": True, "studio_comic_book": True,
            "prompt_agent_full": True, "quiz_create": True, "lab_feasibility": True,
            "legion_squad": True, "lab_sandbox": True, "remote_full": True,
            "legion_full": True, "skemi_computer": True, "beta": True, "api": True,
        },
        "quotas": {
            "prompts_per_6h": UNLIMITED,
            "deep_research_per_day": UNLIMITED,
            "uploads_active": UNLIMITED,
            "quiz_rooms_active": UNLIMITED,
            "studio_per_day": UNLIMITED,
        },
        "priority": 3,
        "chat_history_hours": UNLIMITED,  # permanent for all tiers
    },
}

DEFAULT_TIER = "free"
TIER_ORDER = ["free", "pro", "advanced", "skemi"]

# Which tier a blocked feature should suggest upgrading to (cheapest that has it).
def _min_tier_for_feature(feature: str) -> str:
    for t in TIER_ORDER:
        if TIERS[t]["features"].get(feature):
            return t
    return "skemi"

# Map a quota kind -> the tier to suggest when it's exhausted.
def _suggest_tier_for_quota(kind: str, current_tier: str) -> str:
    """Suggest the next tier up that materially raises this quota."""
    cur_idx = TIER_ORDER.index(current_tier) if current_tier in TIER_ORDER else 0
    for t in TIER_ORDER[cur_idx + 1:]:
        lim = TIERS[t]["quotas"].get(kind, 0)
        cur = TIERS[current_tier]["quotas"].get(kind, 0)
        if lim == UNLIMITED or (isinstance(lim, int) and lim > (cur if cur != UNLIMITED else lim)):
            return t
    return "skemi"


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------

_DB_PATH = os.getenv(
    "SKEMI_AUTH_DB",
    os.path.join(os.path.dirname(__file__), "skemi_auth.db"),
)
_LOCK = threading.Lock()
_INIT_DONE = False


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(_DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _init_db() -> None:
    global _INIT_DONE
    if _INIT_DONE:
        return
    with _LOCK:
        if _INIT_DONE:
            return
        with _conn() as c:
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS account_plan (
                    account_id TEXT PRIMARY KEY,
                    tier       TEXT NOT NULL DEFAULT 'free',
                    updated_at REAL NOT NULL,
                    source     TEXT DEFAULT 'system'
                )
                """
            )
            # Generic periodic usage counter.
            #   kind   = 'tokens' | 'deep_research' | 'prompts' | 'studio' ...
            #   bucket = 'YYYY-MM' (monthly) | 'YYYY-MM-DD' (daily) | '<n>' (6h window)
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_counter (
                    account_id TEXT NOT NULL,
                    kind       TEXT NOT NULL,
                    bucket     TEXT NOT NULL,
                    used       INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (account_id, kind, bucket)
                )
                """
            )
            c.commit()
        _INIT_DONE = True


# --------------------------------------------------------------------------
# Time bucket helpers
# --------------------------------------------------------------------------

def _now() -> float:
    return time.time()


def month_bucket(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(ts if ts is not None else _now(), tz=timezone.utc)
    return dt.strftime("%Y-%m")


def day_bucket(ts: Optional[float] = None) -> str:
    dt = datetime.fromtimestamp(ts if ts is not None else _now(), tz=timezone.utc)
    return dt.strftime("%Y-%m-%d")


def window6h_bucket(ts: Optional[float] = None) -> str:
    t = ts if ts is not None else _now()
    return str(int(t // (6 * 3600)))


# kind -> bucket function for periodic metering
# NOTE: token budget resets DAILY (cheaper to reason about for users and caps
# the worst-case cloud spend per user per day, not per month).
_BUCKET_FN = {
    "tokens": day_bucket,
    "deep_research": day_bucket,
    "studio": day_bucket,
    "prompts": window6h_bucket,
}


# --------------------------------------------------------------------------
# Account id normalisation
# --------------------------------------------------------------------------

def normalize_account(account_id: Optional[str]) -> str:
    a = (account_id or "").strip()
    return a if a else "guest"


# --------------------------------------------------------------------------
# Tier read / write
# --------------------------------------------------------------------------

def valid_tier(tier: Optional[str]) -> str:
    t = (tier or "").strip().lower()
    return t if t in TIERS else DEFAULT_TIER


# Founder (CEO) accounts — full access while testing. Matched against the
# account_id the request layer sets (email or uid). Override/extend with the
# SKEMI_FOUNDER_ACCOUNTS env var (comma-separated).
FOUNDER_ACCOUNTS = set(
    a.strip().lower() for a in os.getenv("SKEMI_FOUNDER_ACCOUNTS", "tvo24027@gmail.com").split(",")
    if a.strip()
)


def is_founder(account_id: str) -> bool:
    return normalize_account(account_id).lower() in FOUNDER_ACCOUNTS


# BETA SWITCH — while OFF (default), EVERYONE gets the top tier so every feature
# is free during testing. Flip on (env SKEMI_GATING_ENABLED=1) to activate the
# real per-tier paywall once testing is done. Built now, dormant until then.
GATING_ENABLED = os.getenv("SKEMI_GATING_ENABLED", "0").strip() in ("1", "true", "yes", "on")


def get_tier(account_id: str) -> str:
    account_id = normalize_account(account_id)
    if not GATING_ENABLED:
        return "skemi"          # beta: all features free for everyone
    if account_id == "guest":
        return DEFAULT_TIER
    if is_founder(account_id):
        return "skemi"          # CEO test account → top tier, all features
    _init_db()
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT tier FROM account_plan WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if row:
            return valid_tier(row["tier"])
    except Exception:
        pass
    return DEFAULT_TIER


def set_tier(account_id: str, tier: str, source: str = "system") -> str:
    account_id = normalize_account(account_id)
    tier = valid_tier(tier)
    if account_id == "guest":
        return tier
    _init_db()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO account_plan (account_id, tier, updated_at, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(account_id) DO UPDATE SET
                tier = excluded.tier,
                updated_at = excluded.updated_at,
                source = excluded.source
            """,
            (account_id, tier, _now(), source),
        )
        c.commit()
    return tier


# --------------------------------------------------------------------------
# Config accessors
# --------------------------------------------------------------------------

def tier_config(tier: str) -> Dict[str, Any]:
    return TIERS.get(valid_tier(tier), TIERS[DEFAULT_TIER])


def can_use_feature(tier: str, feature: str) -> bool:
    return bool(tier_config(tier)["features"].get(feature, False))


def quota_limit(tier: str, kind: str) -> int:
    return int(tier_config(tier)["quotas"].get(kind, 0))


def daily_token_limit(tier: str) -> int:
    return int(tier_config(tier)["daily_tokens"])


# Backwards-compat alias (token budget is now DAILY, not monthly).
def monthly_token_limit(tier: str) -> int:
    return daily_token_limit(tier)


# --------------------------------------------------------------------------
# Usage read / write
# --------------------------------------------------------------------------

def _bucket_for(kind: str, ts: Optional[float] = None) -> str:
    fn = _BUCKET_FN.get(kind, month_bucket)
    return fn(ts)


def usage_get(account_id: str, kind: str, bucket: Optional[str] = None) -> int:
    account_id = normalize_account(account_id)
    if account_id == "guest":
        return 0
    _init_db()
    bucket = bucket or _bucket_for(kind)
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT used FROM usage_counter WHERE account_id=? AND kind=? AND bucket=?",
                (account_id, kind, bucket),
            ).fetchone()
        return int(row["used"]) if row else 0
    except Exception:
        return 0


def usage_add(account_id: str, kind: str, amount: int = 1, bucket: Optional[str] = None) -> int:
    account_id = normalize_account(account_id)
    if account_id == "guest" or amount == 0:
        return 0
    _init_db()
    bucket = bucket or _bucket_for(kind)
    with _LOCK:
        with _conn() as c:
            c.execute(
                """
                INSERT INTO usage_counter (account_id, kind, bucket, used, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_id, kind, bucket) DO UPDATE SET
                    used = used + excluded.used,
                    updated_at = excluded.updated_at
                """,
                (account_id, kind, bucket, int(amount), _now()),
            )
            c.commit()
            row = c.execute(
                "SELECT used FROM usage_counter WHERE account_id=? AND kind=? AND bucket=?",
                (account_id, kind, bucket),
            ).fetchone()
    return int(row["used"]) if row else int(amount)


# --------------------------------------------------------------------------
# ContextVar token meter  (set by the request layer; read at the model call)
# --------------------------------------------------------------------------

current_account: ContextVar[str] = ContextVar("skemi_current_account", default="guest")


def set_current_account(account_id: str) -> None:
    current_account.set(normalize_account(account_id))


def note_model_usage(prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
    """Attribute model token usage to the active account (monthly bucket)."""
    try:
        total = int(prompt_tokens or 0) + int(completion_tokens or 0)
        if total <= 0:
            return
        acc = normalize_account(current_account.get())
        if acc == "guest":
            return
        usage_add(acc, "tokens", total)
    except Exception:
        # Metering must never break a generation.
        pass


# --------------------------------------------------------------------------
# Checks (enforcement primitives)
# --------------------------------------------------------------------------

class Decision:
    """Result of an entitlement check."""

    def __init__(self, allowed: bool, reason: str = "", *, kind: str = "",
                 suggest_tier: str = "", used: int = 0, limit: int = 0,
                 message_vi: str = "", message_en: str = ""):
        self.allowed = allowed
        self.reason = reason          # 'ok' | 'feature' | 'quota' | 'tokens'
        self.kind = kind              # feature name or quota kind
        self.suggest_tier = suggest_tier
        self.used = used
        self.limit = limit
        self.message_vi = message_vi
        self.message_en = message_en

    def to_dict(self) -> Dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "kind": self.kind,
            "suggest_tier": self.suggest_tier,
            "used": self.used,
            "limit": self.limit,
            "message": {"vi": self.message_vi, "en": self.message_en},
        }


def check_feature(account_id: str, feature: str) -> Decision:
    tier = get_tier(account_id)
    if can_use_feature(tier, feature):
        return Decision(True, "ok", kind=feature)
    sug = _min_tier_for_feature(feature)
    label = TIERS[sug]["label"]
    return Decision(
        False, "feature", kind=feature, suggest_tier=sug,
        message_vi=f"Tính năng này có ở gói {label}.",
        message_en=f"This feature is available on {label}.",
    )


def check_token_budget(account_id: str) -> Decision:
    tier = get_tier(account_id)
    limit = daily_token_limit(tier)
    used = usage_get(account_id, "tokens")
    if limit == UNLIMITED or used < limit:
        return Decision(True, "ok", kind="tokens", used=used, limit=limit)
    sug = TIER_ORDER[min(TIER_ORDER.index(tier) + 1, len(TIER_ORDER) - 1)]
    label = TIERS[sug]["label"]
    return Decision(
        False, "tokens", kind="tokens", suggest_tier=sug, used=used, limit=limit,
        message_vi=f"Bạn đã dùng hết hạn mức token hôm nay. Mai sẽ làm mới, hoặc nâng cấp {label} để có thêm ngay.",
        message_en=f"You've used today's token budget. It resets tomorrow, or upgrade to {label} for more now.",
    )


def check_quota(account_id: str, kind: str) -> Decision:
    """Check a periodic quota (prompts / deep_research / studio). Does NOT consume."""
    tier = get_tier(account_id)
    limit = quota_limit(tier, _quota_key(kind))
    if limit == UNLIMITED:
        return Decision(True, "ok", kind=kind, limit=UNLIMITED)
    used = usage_get(account_id, kind)
    if used < limit:
        return Decision(True, "ok", kind=kind, used=used, limit=limit)
    sug = _suggest_tier_for_quota(_quota_key(kind), tier)
    label = TIERS[sug]["label"]
    return Decision(
        False, "quota", kind=kind, suggest_tier=sug, used=used, limit=limit,
        message_vi=f"Bạn đã đạt giới hạn ({limit}) của gói hiện tại. Nâng cấp {label} để dùng thêm.",
        message_en=f"You've reached your plan limit ({limit}). Upgrade to {label} for more.",
    )


# usage 'kind' (counter) -> quota config key
_QUOTA_KEY = {
    "prompts": "prompts_per_6h",
    "deep_research": "deep_research_per_day",
    "studio": "studio_per_day",
    "uploads": "uploads_active",
    "quiz_rooms": "quiz_rooms_active",
}


def _quota_key(kind: str) -> str:
    return _QUOTA_KEY.get(kind, kind)


def consume_quota(account_id: str, kind: str, amount: int = 1) -> int:
    """Record one use of a periodic quota (call after a successful action)."""
    return usage_add(account_id, kind, amount)


# --------------------------------------------------------------------------
# Snapshot (for GET /api/entitlements and the frontend)
# --------------------------------------------------------------------------

def snapshot(account_id: str) -> Dict[str, Any]:
    account_id = normalize_account(account_id)
    tier = get_tier(account_id)
    cfg = tier_config(tier)
    tokens_used = usage_get(account_id, "tokens")
    tokens_limit = daily_token_limit(tier)
    dr_limit = quota_limit(tier, "deep_research_per_day")
    pr_limit = quota_limit(tier, "prompts_per_6h")
    return {
        "account_id": account_id if account_id != "guest" else None,
        "tier": tier,
        "label": cfg["label"],
        "price_vnd": cfg["price_vnd"],
        "features": dict(cfg["features"]),
        "quotas": dict(cfg["quotas"]),
        "priority": cfg["priority"],
        "chat_history_hours": cfg["chat_history_hours"],
        # Baseline benefit for EVERY tier (incl. Free): all conversations —
        # user↔user and user↔Skemi bot — are stored forever, Messenger-style.
        "message_history": "permanent",
        "usage": {
            "tokens": {
                "used": tokens_used,
                "limit": tokens_limit,
                "remaining": (UNLIMITED if tokens_limit == UNLIMITED
                              else max(0, tokens_limit - tokens_used)),
                "period": "day",
                "bucket": day_bucket(),
            },
            "deep_research": {
                "used": usage_get(account_id, "deep_research"),
                "limit": dr_limit,
                "bucket": day_bucket(),
            },
            "prompts": {
                "used": usage_get(account_id, "prompts"),
                "limit": pr_limit,
                "bucket": window6h_bucket(),
            },
        },
        "all_tiers": {
            t: {
                "label": TIERS[t]["label"],
                "price_vnd": TIERS[t]["price_vnd"],
                "daily_tokens": TIERS[t]["daily_tokens"],
                "features": TIERS[t]["features"],
                "quotas": TIERS[t]["quotas"],
            }
            for t in TIER_ORDER
        },
    }


def describe_plan() -> str:
    """Human-readable plan summary (for logs / docs / quick review)."""
    lines = ["SKEMI SUBSCRIPTION PLAN", "=" * 60]
    for t in TIER_ORDER:
        c = TIERS[t]
        feats = [k for k, v in c["features"].items() if v]
        lines.append(f"\n[{c['label']}]  {c['price_vnd']:,}đ/month".replace(",", "."))
        tok = "unlimited" if c["daily_tokens"] == UNLIMITED else f"{c['daily_tokens']:,}".replace(",", ".")
        lines.append(f"  tokens/day   : {tok}")
        lines.append(f"  features     : {', '.join(feats)}")
        q = c["quotas"]
        def _fmt(v): return "∞" if v == UNLIMITED else str(v)
        lines.append(
            "  quotas       : "
            f"prompts/6h={_fmt(q['prompts_per_6h'])}, "
            f"deep_research/day={_fmt(q['deep_research_per_day'])}, "
            f"uploads={_fmt(q['uploads_active'])}, "
            f"quiz_rooms={_fmt(q['quiz_rooms_active'])}, "
            f"studio/day={_fmt(q['studio_per_day'])}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(describe_plan())
    # Tiny self-test
    acc = "selftest_account"
    set_tier(acc, "free")
    assert get_tier(acc) == "free"
    # Free can now ACCESS all useful features (gated by daily tokens/quota),
    # but heavy-infra surfaces stay locked.
    assert check_feature(acc, "deep_research").allowed is True
    assert check_feature(acc, "search_basic").allowed is True
    assert check_feature(acc, "skemi_computer").allowed is False
    assert check_feature(acc, "api").allowed is False
    set_tier(acc, "advanced")
    assert check_feature(acc, "skemi_computer").allowed is True
    set_tier(acc, "skemi")
    assert check_feature(acc, "api").allowed is True
    set_tier(acc, "pro")
    assert check_feature(acc, "deep_research").allowed is True
    set_current_account(acc)
    before = usage_get(acc, "tokens")
    note_model_usage(100, 50)
    after = usage_get(acc, "tokens")
    assert after - before == 150, (before, after)
    d = check_token_budget(acc)
    assert d.allowed is True
    # cleanup self-test rows
    with _conn() as _c:
        _c.execute("DELETE FROM account_plan WHERE account_id=?", (acc,))
        _c.execute("DELETE FROM usage_counter WHERE account_id=?", (acc,))
        _c.commit()
    print("\nself-test: OK")
