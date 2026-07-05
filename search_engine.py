# search_engine.py
"""
Search Engine v1 - Optimized for high accuracy and speed.
"""

import sys
import codecs
if sys.stdout.encoding != 'utf-8':
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

import httpx
import logging
import asyncio
import urllib.parse
import os
import sqlite3
from bs4 import BeautifulSoup
import re
from typing import List, Dict, Set, Optional, Tuple, Any
import random
import time
import hashlib
from datetime import datetime, timedelta
import trafilatura
import feedparser
from collections import Counter
import unicodedata
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SmartSearch")

class RequestManager:
    def __init__(self):
        self.limits = httpx.Limits(max_keepalive_connections=80, max_connections=150)
        self.timeout = httpx.Timeout(18.0, connect=6.0, read=12.0)
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            limits=self.limits,
            follow_redirects=True,
            http2=True,
        )
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0',
            'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 OPR/108.0.0.0'
        ]
        self.host_cooldown_until: Dict[str, float] = {}
        self.url_status_cache: Dict[str, Dict] = {}

    def _get_headers(self, referer=None):
        ua = random.choice(self.user_agents)
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1",
            "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="122", "Chromium";v="122"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Cache-Control": "max-age=0",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    async def get(self, url: str, headers: Dict = None, retries: int = 3, backoff_factor: float = 1.2, timeout: float = None):
        """Perform a GET request with optimized retry logic."""
        actual_timeout = timeout if timeout is not None else self.timeout
        host = ""
        try:
            host = urllib.parse.urlsplit(url).netloc.lower()
        except Exception:
            host = ""
        if host:
            until = float(self.host_cooldown_until.get(host, 0.0) or 0.0)
            if until > time.time():
                return None
        for attempt in range(retries):
            current_headers = headers or self._get_headers()
            try:
                if attempt > 0:
                    await asyncio.sleep(backoff_factor * attempt + random.random())
                
                resp = await self.client.get(url, headers=current_headers, timeout=actual_timeout)
                
                if resp.status_code == 429:
                    logger.warning(f"Rate limited (429) for {url}. Attempt {attempt+1}/{retries}")
                    self.url_status_cache[url] = {"status": 429, "ts": time.time()}
                    if host:
                        self.host_cooldown_until[host] = time.time() + 180.0
                    continue
                
                if resp.status_code == 403:
                    logger.warning(f"Forbidden (403) for {url}. Trying different headers...")
                    self.url_status_cache[url] = {"status": 403, "ts": time.time()}
                    if host:
                        self.host_cooldown_until[host] = max(self.host_cooldown_until.get(host, 0.0), time.time() + 60.0)
                    if not headers:
                        current_headers = self._get_headers()
                    continue

                if resp.status_code == 404:
                    self.url_status_cache[url] = {"status": 404, "ts": time.time()}
                    if host:
                        self.host_cooldown_until[host] = max(self.host_cooldown_until.get(host, 0.0), time.time() + 300.0)
                    continue

                resp.raise_for_status()
                self.url_status_cache[url] = {"status": resp.status_code, "ts": time.time()}
                return resp
            
            except httpx.HTTPStatusError as e:
                try:
                    code = int(e.response.status_code)
                    self.url_status_cache[url] = {"status": code, "ts": time.time()}
                    if host and code in [403, 404]:
                        self.host_cooldown_until[host] = max(self.host_cooldown_until.get(host, 0.0), time.time() + (300.0 if code == 404 else 120.0))
                except Exception:
                    pass
                if e.response.status_code in [429, 403, 503]: continue
                if attempt == retries - 1: return None
            except Exception:
                if attempt == retries - 1: return None
        return None

    async def close(self):
        await self.client.aclose()


class SmartSearchEngine:
    def __init__(self):
        self.request_manager = RequestManager()
        # Domain authority scoring - automatic based on TLD and patterns
        self.authority_tlds = {'.edu', '.gov', '.org', '.io'}
        self.low_quality_patterns = ['pinterest', 'quora', 'reddit', 'facebook', 'twitter', 'instagram', 'tiktok', 'medium.com/@']
        self.blocked_domains = {
            "facebook.com", "m.facebook.com", "instagram.com", "tiktok.com",
            "x.com", "twitter.com", "reddit.com", "pinterest.com",
            "threads.com", "linkedin.com", "apps.apple.com",
            "play.google.com", "itunes.apple.com",
            "claude5.com", "www.claude5.com", "claude5.ai", "www.claude5.ai",
            "scriptbyai.com", "www.scriptbyai.com", "datastudios.org", "www.datastudios.org",
            "eonmsk.com", "www.eonmsk.com", "justainews.com", "www.justainews.com",
            "gradually.ai", "www.gradually.ai", "claudefa.st", "www.claudefa.st",
            "felloai.com", "www.felloai.com", "theneuron.ai", "www.theneuron.ai",
            "aichatbot.com.vn", "www.aichatbot.com.vn", "dienthoaivui.com.vn", "www.dienthoaivui.com.vn",
            "quantraai.com", "www.quantraai.com", "tino.vn", "www.tino.vn",
            "happyphone.vn", "www.happyphone.vn", "divineshop.vn", "www.divineshop.vn",
            "licensesoft.net.vn", "www.licensesoft.net.vn", "proweb.com.vn", "www.proweb.com.vn",
            "trithuc24h.com.vn", "www.trithuc24h.com.vn", "congnghevadoisong.vn", "www.congnghevadoisong.vn",
        }
        self.latest_model_press_allowlist = {
            "reuters.com", "apnews.com", "techcrunch.com", "theverge.com", "wired.com", "arstechnica.com",
            "venturebeat.com", "zdnet.com", "engadget.com", "cnet.com", "mashable.com",
            "9to5google.com", "9to5mac.com", "tomsguide.com", "androidauthority.com",
            "windowscentral.com", "theinformation.com", "axios.com", "forbes.com",
        }
        self.latest_model_official_domains = {
            "anthropic.com", "platform.claude.com", "x.ai", "openai.com", "platform.openai.com",
            "help.openai.com", "developers.openai.com", "community.openai.com", "chatgpt.com",
            "blog.google", "deepmind.google", "ai.google.dev", "developers.googleblog.com",
            "gemini.google.com", "cloud.google.com", "google.dev",
            "docs.anthropic.com", "console.anthropic.com",
            "qwen.ai", "alibabacloud.com", "minimax.io",
        }
        self._drop_query_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "fbclid", "gclid", "srsltid", "ref", "source", "ved", "ei", "sei",
            "sa", "aqs", "oq", "sourceid", "atb", "mc_cid", "mc_eid",
        }
        self._search_cache: Dict[str, Dict] = {}
        self._rerank_cache: Dict[str, float] = {}
        self._page_cache: Dict[str, Dict] = {}
        self._enable_semantic_rerank = str(os.getenv("SKEMI_ENABLE_SEMANTIC_RERANK", "1")).strip().lower() in {"1", "true", "yes"}
        self._enable_searxng_engine = str(os.getenv("SKEMI_ENABLE_SEARXNG_ENGINE", "1")).strip().lower() in {"1", "true", "yes"}
        self._searxng_base_url = str(os.getenv("SKEMI_SEARXNG_URL", "http://127.0.0.1:8888")).strip().rstrip("/")
        # Tavily — a reliable AI-research search API (free tier). When a key is set
        # it becomes the PRIMARY engine: clean fresh results WITH content, which is
        # what makes "deep research" actually deep. The HTML-scrape engines
        # (Brave/DDG/SearXNG) are routinely bot-blocked and return nothing.
        self._tavily_key = str(os.getenv("SKEMI_TAVILY_KEY") or os.getenv("TAVILY_API_KEY") or "").strip()
        # ddgs (DuckDuckGo) Python library — uses DDG's real API endpoints (NOT the
        # bot-blocked HTML scrape), so it returns fresh results with no key and no
        # Docker. This is the reliable free default. `pip install ddgs`.
        self._enable_ddgs_lib = str(os.getenv("SKEMI_ENABLE_DDGS_LIB", "1")).strip().lower() in {"1", "true", "yes"}
        self._enable_brave_engine = str(os.getenv("SKEMI_ENABLE_BRAVE_ENGINE", "1")).strip().lower() in {"1", "true", "yes"}
        self._enable_startpage_engine = str(os.getenv("SKEMI_ENABLE_STARTPAGE_ENGINE", "0")).strip().lower() in {"1", "true", "yes"}
        self._enable_qwant_engine = str(os.getenv("SKEMI_ENABLE_QWANT_ENGINE", "1")).strip().lower() in {"1", "true", "yes"}
        self._enable_mojeek_engine = str(os.getenv("SKEMI_ENABLE_MOJEEK_ENGINE", "0")).strip().lower() in {"1", "true", "yes"}
        self._embedder = None
        self._cross_encoder = None
        self._models_init_done = False
        self._models_init_lock = threading.Lock()
        self._std_max_seconds = int(os.getenv("SKEMI_STD_SEARCH_MAX_SECONDS", "12"))
        # DEEP research targets 100+ sources → a longer budget so the parallel engine
        # waves + follow-up queries have time to gather and rank them (user goal:
        # "deep research, luôn trên 100 nguồn").
        # Deep research goal: "trên 100 nguồn đến 300 nguồn". Ceiling raised to
        # 300 with a longer time budget + more follow-up waves so the parallel
        # engine can actually reach that depth (all still env-overridable).
        self._deep_max_seconds = int(os.getenv("SKEMI_DEEP_SEARCH_MAX_SECONDS", "140"))
        self._std_min_sources = int(os.getenv("SKEMI_STD_MIN_SOURCES", "12"))
        self._std_max_sources = int(os.getenv("SKEMI_STD_MAX_SOURCES", "30"))
        self._deep_min_sources = int(os.getenv("SKEMI_DEEP_MIN_SOURCES", "120"))
        self._deep_max_sources = int(os.getenv("SKEMI_DEEP_MAX_SOURCES", "300"))
        self._latest_min_sources = int(os.getenv("SKEMI_LATEST_MIN_SOURCES", "10"))
        self._std_min_context_chars = int(os.getenv("SKEMI_STD_MIN_CONTEXT_CHARS", "5000"))
        self._deep_min_context_chars = int(os.getenv("SKEMI_DEEP_MIN_CONTEXT_CHARS", "16000"))
        self._latest_min_context_chars = int(os.getenv("SKEMI_LATEST_MIN_CONTEXT_CHARS", "2200"))
        self._std_followup_queries = int(os.getenv("SKEMI_STD_FOLLOWUP_QUERIES", "3"))
        self._deep_followup_queries = int(os.getenv("SKEMI_DEEP_FOLLOWUP_QUERIES", "12"))
        self._latest_followup_queries = int(os.getenv("SKEMI_LATEST_FOLLOWUP_QUERIES", "2"))
        self._source_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "source_reputation.db")
        os.makedirs(os.path.dirname(self._source_db_path), exist_ok=True)
        self._init_source_reputation_db()

    def _repair_mojibake(self, text: str) -> str:
        raw = str(text or "")
        if not raw:
            return ""
        suspicious = ("Ã", "Ä", "â€", "â€™", "â€œ", "â€\x9d", "á»", "áº")
        if any(marker in raw for marker in suspicious):
            try:
                repaired = raw.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
                if repaired:
                    raw = repaired
            except Exception:
                pass
        return raw

    def _normalize_for_match(self, text: str) -> str:
        raw = unicodedata.normalize("NFKD", self._repair_mojibake(text))
        raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
        raw = raw.replace("đ", "d").replace("Đ", "d")
        return re.sub(r"\s+", " ", raw.lower()).strip()

    def _extract_site_filters(self, text: str) -> List[str]:
        sites: List[str] = []
        seen: Set[str] = set()
        for match in re.findall(r"\bsite:([a-z0-9][a-z0-9.-]*\.[a-z]{2,})", self._normalize_for_match(text)):
            domain = str(match or "").lower().strip(".")
            if domain and domain not in seen:
                seen.add(domain)
                sites.append(domain)
        return sites

    def _search_low_signal_penalty(self, title: str, snippet: str, url: str = "") -> float:
        blob = self._normalize_for_match(" ".join([title or "", snippet or "", url or ""]))
        if not blob:
            return 0.0

        penalty = 0.0
        strong_markers = (
            "table of contents", "introduction", "muc luc", "gioi thieu", "noi dung chinh",
            "how to use", "huong dan", "mau prompt", "cau lenh", "bang gia", "pricing",
            "download", "apk", "app store", "play store",
        )
        medium_markers = (
            "prompt", "template", "guide", "tutorial", "tips", "best model", "which model is best",
            "so sanh", "compare", "comparison", "versus", "vs",
        )

        if any(marker in blob for marker in strong_markers):
            penalty += 4.0
        if any(marker in blob for marker in medium_markers):
            penalty += 2.0
        if blob.count(" - ") >= 4 or blob.count(":") >= 4:
            penalty += 1.5
        if re.search(r"\b(?:chapter|section|contents|overview|summary)\b", blob):
            penalty += 1.0
        return penalty

    def _clean_latest_subject_candidate(self, candidate: str) -> str:
        text = self._normalize_for_match(candidate)
        text = re.sub(r"\bsite:[a-z0-9][a-z0-9.-]*\.[a-z]{2,}\b", " ", text)
        text = re.sub(
            r"\b(?:latest|newest|current|official|trusted|major|press|source|sources|news|today|recent|new|now|"
            r"moi|nhat|moi nhat|hien|tai|cap|nhat|phien|ban|ra|mat|model|models|version|release|overview|"
            r"compare|comparison|between|what|which|la|gi|ve|cua|cho|toi|muon|biet|tim|kiem|thong|tin)\b",
            " ",
            text,
        )
        tokens = [
            token
            for token in re.findall(r"[a-z0-9][a-z0-9.+-]*", text)
            if not token.isdigit() and len(token) > 1
        ]
        return " ".join(tokens[:4]).strip()

    def _infer_subject_domains(self, subject: str, explicit_sites: Optional[List[str]] = None) -> List[str]:
        domains: List[str] = []
        seen: Set[str] = set()

        for domain in explicit_sites or []:
            normalized = str(domain or "").lower().strip(".")
            if normalized and normalized not in seen:
                seen.add(normalized)
                domains.append(normalized)

        tokens = [token for token in re.findall(r"[a-z0-9]+", self._normalize_for_match(subject)) if len(token) > 1]
        stems: List[str] = []
        for stem in ("".join(tokens), "-".join(tokens), *(tokens[:1]), *(tokens[-1:] if len(tokens) > 1 else [])):
            if stem and stem not in stems:
                stems.append(stem)

        suffixes = ("ai", "com", "io", "dev", "app", "cloud", "co", "org")
        for stem in stems:
            for suffix in suffixes:
                candidate = f"{stem}.{suffix}"
                if candidate not in seen:
                    seen.add(candidate)
                    domains.append(candidate)
            for prefix in ("platform", "blog", "docs"):
                candidate = f"{prefix}.{stem}.com"
                if candidate not in seen:
                    seen.add(candidate)
                    domains.append(candidate)
        return domains

    def _text_mentions_subject(self, subject: str, text: str) -> bool:
        haystack = self._normalize_for_match(text)
        if not haystack:
            return False
        normalized_subject = self._normalize_for_match(subject)
        if normalized_subject and normalized_subject in haystack:
            return True
        tokens = [token for token in re.findall(r"[a-z0-9]+", normalized_subject) if len(token) > 2]
        if not tokens:
            return False
        strong_tokens = [token for token in tokens if len(token) >= 4]
        tokens_to_check = strong_tokens or tokens
        hits = sum(1 for token in tokens_to_check if token in haystack)
        threshold = 1 if len(tokens_to_check) == 1 else min(2, len(tokens_to_check))
        return hits >= threshold

    def _sanitize_query_for_web(self, query: str) -> str:
        original = self._repair_mojibake(query).strip()
        if not original:
            return ""
        normalized = self._normalize_for_match(original)
        if not normalized:
            return ""
        if self._is_internal_payload_query(normalized):
            return ""

        cleaned = original
        cleaned = re.sub(r"^[\"'`]+|[\"'`]+$", "", cleaned).strip()
        cleaned = re.sub(r"[\r\n\t]+", " ", cleaned)
        cleaned = re.sub(r"[<>|]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if not cleaned:
            return ""
        return cleaned[:220]

    def _is_internal_payload_query(self, text: str) -> bool:
        q = self._normalize_for_match(text)
        if not q:
            return False
        markers = (
            "tep:",
            "loai:",
            "che do phan tich:",
            "noi dung trich xuat:",
            "van ban ocr:",
            "phan tich anh",
            "image analysis",
            "file:",
            "analysis mode:",
        )
        hits = sum(1 for m in markers if m in q)
        return hits >= 2

    def _build_search_expansion_queries(
        self,
        queries: List[str],
        query_class: str = "general",
        recency_priority: str = "medium",
        deep_research: bool = False,
    ) -> List[str]:
        cleaned_base: List[str] = []
        for raw in queries or []:
            normalized = self._sanitize_query_for_web(raw) or self._normalize_for_match(raw)
            if normalized and normalized not in cleaned_base:
                cleaned_base.append(normalized)

        if not cleaned_base:
            return []

        followup_cap = self._deep_followup_queries if deep_research else self._std_followup_queries
        expansions: List[str] = []
        seen: Set[str] = set(cleaned_base)
        current_year = str(datetime.utcnow().year)
        current_month = datetime.utcnow().strftime("%Y-%m")

        for base_query in cleaned_base[:3]:
            time_variants: List[str] = []
            if current_year not in base_query:
                time_variants.append(f"{base_query} {current_year}")
            if deep_research and current_month not in base_query:
                time_variants.append(f"{base_query} {current_month}")
            for candidate in time_variants:
                normalized = self._normalize_for_match(candidate)[:220].strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                expansions.append(normalized)
                if len(expansions) >= followup_cap:
                    return expansions

        return expansions[:followup_cap]

    def _init_source_reputation_db(self) -> None:
        conn = sqlite3.connect(self._source_db_path)
        try:
            c = conn.cursor()
            c.execute(
                """
                CREATE TABLE IF NOT EXISTS source_reputation (
                    topic TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    trust_score REAL NOT NULL DEFAULT 0,
                    freshness_score REAL NOT NULL DEFAULT 0,
                    authority_score REAL NOT NULL DEFAULT 0,
                    hit_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    fail_count INTEGER NOT NULL DEFAULT 0,
                    last_seen TEXT,
                    PRIMARY KEY(topic, domain)
                )
                """
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_source_rep_topic ON source_reputation(topic)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_source_rep_trust ON source_reputation(trust_score DESC)")
            conn.commit()
        finally:
            conn.close()

    def _topic_key(self, queries: List[str]) -> str:
        raw = " ".join([q.strip().lower() for q in (queries or []) if str(q).strip()])[:220]
        raw = re.sub(r"\s+", " ", raw).strip()
        return raw or "general"

    def _upsert_source_reputation(self, topic: str, domain: str, authority: float, recency: float, trust: float, success: bool = True) -> None:
        if not topic or not domain:
            return
        conn = sqlite3.connect(self._source_db_path)
        try:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO source_reputation(topic, domain, trust_score, freshness_score, authority_score, hit_count, success_count, fail_count, last_seen)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(topic, domain) DO UPDATE SET
                    trust_score = (source_reputation.trust_score * source_reputation.hit_count + excluded.trust_score) / (source_reputation.hit_count + 1),
                    freshness_score = (source_reputation.freshness_score * source_reputation.hit_count + excluded.freshness_score) / (source_reputation.hit_count + 1),
                    authority_score = (source_reputation.authority_score * source_reputation.hit_count + excluded.authority_score) / (source_reputation.hit_count + 1),
                    hit_count = source_reputation.hit_count + 1,
                    success_count = source_reputation.success_count + excluded.success_count,
                    fail_count = source_reputation.fail_count + excluded.fail_count,
                    last_seen = excluded.last_seen
                """,
                (
                    topic,
                    domain,
                    float(trust),
                    float(recency),
                    float(authority),
                    1 if success else 0,
                    0 if success else 1,
                    datetime.now().isoformat(),
                ),
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    def _token_set(self, text: str) -> Set[str]:
        norm = re.sub(r"[^\w\s/\-]", " ", self._normalize_for_match(text))
        return {t for t in norm.split() if len(t) > 1}

    def _critical_tokens(self, text: str) -> Set[str]:
        norm_text = self._normalize_for_match(text)
        tokens = self._token_set(norm_text)
        stop = {
            "hello", "xin", "chao", "ban", "biet", "la", "gi", "nao", "khong",
            "moi", "nhat", "latest", "new", "newest", "current", "today",
            "cua", "ve", "cho", "toi", "nua", "them", "ra", "mat", "thong",
            "tin", "nam", "nay", "what", "which", "site", "www", "http", "https",
            "official", "announcement", "announcements", "documentation", "docs",
            "overview", "update", "updated", "news", "recent",
            "model", "models", "version", "versions", "release", "releases",
            "note", "notes", "specification", "specifications", "spec", "specs",
            "phien", "ban", "mo", "hinh", "cap", "ai",
        }
        critical = set()
        for t in tokens:
            if t in stop:
                continue
            if any(ch.isdigit() for ch in t) or len(t) >= 3:
                critical.add(t)
        # Cross-lingual anchors for better matching against English-heavy sources.
        if "trung dong" in norm_text:
            critical.update({"middle", "east", "mena"})
        if "trung quoc" in norm_text:
            critical.update({"china", "chinese"})
        return set(sorted(critical, key=lambda x: (-len(x), x))[:8])

    def _matches_critical_tokens(self, text: str, critical_tokens: Set[str]) -> bool:
        if not critical_tokens:
            return True
        bag = self._token_set(text)
        non_numeric = {t for t in critical_tokens if not any(ch.isdigit() for ch in t)}
        if non_numeric:
            required_hits = 1 if len(non_numeric) <= 6 else 2
            return len(bag & non_numeric) >= required_hits
        return len(bag & critical_tokens) > 0

    def _query_focus_tokens(self, query: str) -> Set[str]:
        generic = {
            "official", "announcement", "announcements", "documentation", "docs",
            "overview", "update", "updated", "news", "recent", "site",
            "www", "http", "https", "com", "org", "net",
            "model", "models", "version", "versions", "release", "releases",
            "note", "notes", "specification", "specifications", "spec", "specs",
            "phien", "ban", "mo", "hinh", "cap", "ai",
        }
        focus = {
            token
            for token in self._critical_tokens(query)
            if token and token not in generic and not token.isdigit()
        }
        return set(sorted(focus, key=lambda x: (-len(x), x))[:6])

    def _candidate_query_support_metrics(self, text: str, queries: List[str]) -> Tuple[int, int]:
        bag = self._token_set(text)
        if not bag:
            return 0, 0

        support_count = 0
        max_hits = 0
        for query in queries or []:
            focus = self._query_focus_tokens(query)
            if not focus:
                continue
            hits = len(bag & focus)
            max_hits = max(max_hits, hits)
            required_hits = 1 if len(focus) <= 3 else 2 if len(focus) <= 6 else 3
            if hits >= required_hits:
                support_count += 1
        return support_count, max_hits

    def _matched_queries_for_text(self, text: str, queries: List[str]) -> List[str]:
        normalized = self._normalize_for_match(text)
        if not normalized:
            return []
        matched: List[str] = []
        seen: Set[str] = set()
        for query in queries or []:
            query_text = str(query or "").strip()
            if not query_text or query_text in seen:
                continue
            focus = self._query_focus_tokens(query_text)
            if focus and self._matches_critical_tokens(normalized, focus):
                matched.append(query_text)
                seen.add(query_text)
                continue
            query_norm = self._normalize_for_match(query_text)
            if query_norm and query_norm in normalized:
                matched.append(query_text)
                seen.add(query_text)
        return matched

    def _query_coverage_counts(self, items: List[Dict], queries: List[str]) -> Dict[str, int]:
        coverage = {str(query or "").strip(): 0 for query in queries or [] if str(query or "").strip()}
        if not coverage:
            return {}
        for item in items or []:
            matched_queries = [
                str(query or "").strip()
                for query in (item.get("matched_queries") or [])
                if str(query or "").strip()
            ]
            if not matched_queries:
                text = " ".join(
                    [
                        str(item.get("title", "")),
                        str(item.get("snippet", "")),
                        str(item.get("content", ""))[:1200],
                        str(item.get("url", "")),
                    ]
                )
                matched_queries = self._matched_queries_for_text(text, list(coverage.keys()))
            for query in set(matched_queries):
                if query in coverage:
                    coverage[query] += 1
        return coverage

    def _evidence_confidence_level(self, item: Dict) -> str:
        trust_tier = str(item.get("source_trust_tier") or "").strip().lower()
        authority = float(item.get("authority_score", 0.0) or 0.0)
        has_full_content = bool(str(item.get("content") or "").strip())
        if bool(item.get("is_official_source")) or trust_tier in {"official", "official_family", "docs"}:
            return "high"
        if trust_tier == "major_press":
            return "medium" if has_full_content else "low"
        if authority >= 75.0 and has_full_content:
            return "medium"
        return "low"

    def _extract_version_claims(self, text: str, anchors: Optional[Set[str]] = None) -> List[str]:
        raw_text = re.sub(r"\s+", " ", str(text or "")).strip()
        if not raw_text:
            return []
        normalized_text = self._normalize_for_match(raw_text)
        anchor_tokens = {
            self._normalize_for_match(anchor)
            for anchor in (anchors or set())
            if self._normalize_for_match(anchor)
        }
        claims: List[str] = []
        seen: Set[str] = set()
        patterns = (
            r"\b(?:[A-Z][A-Za-z0-9\-]{1,24}\s){1,3}\d+(?:\.\d+){0,2}\b",
            r"\b[A-Z][A-Za-z0-9\-]{1,24}-\d+(?:\.\d+){0,2}(?:-[A-Za-z0-9]+){0,2}\b",
            r"\b(?:[A-Z][A-Za-z0-9\-]{1,24}\s){0,2}[A-Z][A-Za-z0-9\-]*\d+(?:\.\d+){0,2}\b",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, raw_text):
                claim_raw = re.sub(r"\s+", " ", match.group(0)).strip(" -.")
                claim = self._normalize_for_match(claim_raw)
                if not claim:
                    continue
                if not re.search(r"[a-z]", claim) or not re.search(r"\d", claim):
                    continue
                if re.fullmatch(r"(?:19|20)\d{2}", claim):
                    continue
                if len(claim.split()) > 4:
                    continue
                claim_tokens = claim.split()
                contains_anchor_token = bool(anchor_tokens) and any(token in anchor_tokens for token in claim_tokens)
                digitish_tokens = [
                    token
                    for token in claim_tokens
                    if token and any(ch.isdigit() for ch in token)
                ]
                has_embedded_alnum = any(
                    any(ch.isdigit() for ch in token) and any(ch.isalpha() for ch in token)
                    for token in digitish_tokens
                )
                if digitish_tokens and all(re.fullmatch(r"(?:19|20)\d{2}", token) for token in digitish_tokens):
                    continue
                if anchor_tokens:
                    if not contains_anchor_token and not has_embedded_alnum:
                        continue
                    if not contains_anchor_token:
                        window_start = max(0, match.start() - 48)
                        window_end = min(len(raw_text), match.end() + 48)
                        window_text = self._normalize_for_match(raw_text[window_start:window_end])
                        if not any(anchor in window_text for anchor in anchor_tokens):
                            continue
                if claim in seen:
                    continue
                seen.add(claim)
                claims.append(claim)
        return claims[:8]

    def _apply_freshness_window(
        self,
        results: List[Dict],
        recency_priority: str,
        *,
        min_keep: int,
    ) -> List[Dict]:
        if recency_priority != "high" or not results:
            return results

        now_dt = datetime.now()
        dated: List[Dict] = []
        undated: List[Dict] = []
        for raw in results:
            item = dict(raw)
            published_at = item.get("published_at") or self._extract_published_at(
                item.get("title", ""),
                item.get("snippet", ""),
                item.get("content", ""),
                item.get("url", ""),
            )
            if published_at:
                item["published_at"] = published_at
                try:
                    item["_published_dt"] = datetime.fromisoformat(str(published_at))
                except Exception:
                    item["_published_dt"] = None
            if isinstance(item.get("_published_dt"), datetime):
                dated.append(item)
            else:
                undated.append(item)

        if len(dated) < 2:
            return results

        dated.sort(key=lambda item: item.get("_published_dt", datetime.min), reverse=True)
        newest_dt = dated[0]["_published_dt"]
        cutoff_dt = max(now_dt - timedelta(days=365), newest_dt - timedelta(days=180))
        kept = [item for item in dated if item.get("_published_dt") and item["_published_dt"] >= cutoff_dt]
        if len(kept) < min_keep:
            kept = dated[: min(len(dated), max(min_keep, len(kept)))]

        if len(kept) < min_keep and undated:
            undated.sort(
                key=lambda item: (
                    float(item.get("query_support_count", 0.0) or 0.0),
                    float(item.get("query_match_hits_max", 0.0) or 0.0),
                    float(item.get("combined_score", 0.0) or 0.0),
                ),
                reverse=True,
            )
            kept.extend(undated[: max(0, min_keep - len(kept))])

        trimmed: List[Dict] = []
        for item in kept:
            clean = dict(item)
            clean.pop("_published_dt", None)
            trimmed.append(clean)
        return trimmed

    def _domain_relevant_for_topic(self, domain: str, url: str, topic: str) -> bool:
        d = (domain or "").lower()
        u = (url or "").lower()
        t = (topic or "").lower()
        if not d:
            return False
        topic_tokens = self._token_set(t)
        entity_tokens = [token for token in self._query_focus_tokens(t) if len(token) >= 4]
        if any(token in t for token in ("latest", "newest", "current", "moi nhat", "version", "model", "phien ban", "release")):
            if {"grok", "xai"} & topic_tokens or "x.ai" in t:
                trusted = ("x.ai", "reuters.com", "apnews.com", "techcrunch.com", "theverge.com", "wired.com", "arstechnica.com")
                if any(td in d for td in trusted):
                    return True
            if {"claude", "anthropic"} & topic_tokens:
                trusted = ("anthropic.com", "platform.claude.com", "reuters.com", "apnews.com", "techcrunch.com", "theverge.com", "wired.com", "arstechnica.com")
                if any(td in d for td in trusted):
                    return True
            if {"openai", "chatgpt"} & topic_tokens or any(token.startswith("gpt") for token in topic_tokens):
                trusted = ("openai.com", "platform.openai.com", "developers.openai.com", "help.openai.com", "chatgpt.com", "reuters.com", "apnews.com", "techcrunch.com", "theverge.com", "wired.com", "arstechnica.com")
                if any(td in d for td in trusted):
                    return True
            if entity_tokens and any(token in d or token in u for token in entity_tokens):
                return True
        # AI/LLM topic safety gate to avoid semantic drift (e.g., car pages for GLM query)
        ai_signals = ("glm", "llm", "model", "zhipu", "chatglm", "ai", "artificial intelligence")
        if any(sig in t for sig in ai_signals):
            bad_path = ("o-to", "oto", "xe-may", "car", "automotive", "gia-xe", "2banh")
            if any(bp in u for bp in bad_path):
                return False
            good_domain = (
                "zhipu", "bigmodel", "reuters", "apnews", "bbc", "openai", "anthropic",
                "huggingface", "arxiv", "github", "vietnamplus", "vnexpress", "tuoitre",
                "thanhnien", "vov", "laodong", "vietnamnet",
            )
            if any(g in d for g in good_domain):
                return True
            # keep unknown domain only when url/title itself has strong AI signal
            return any(sig in u for sig in ai_signals)
        return True

    def _canonicalize_url(self, url: str) -> str:
        try:
            p = urllib.parse.urlsplit(url.strip())
            scheme = p.scheme or "https"
            netloc = p.netloc.lower()
            path = p.path.rstrip("/")
            q_pairs = urllib.parse.parse_qsl(p.query, keep_blank_values=False)
            clean_q = [(k, v) for (k, v) in q_pairs if k.lower() not in self._drop_query_params]
            query = urllib.parse.urlencode(clean_q, doseq=True)
            return urllib.parse.urlunsplit((scheme, netloc, path, query, ""))
        except Exception:
            return (url or "").strip()

    def _is_blocked_url(self, url: str) -> bool:
        try:
            raw = (url or "").strip().lower()
            if not raw:
                return True
            parsed = urllib.parse.urlsplit(raw)
            domain = (parsed.netloc or "").lower()
            path = (parsed.path or "").lower()
            query = (parsed.query or "").lower()
            if domain.startswith("www."):
                domain = domain[4:]
            if domain.startswith("m."):
                domain = domain[2:]
            if not domain:
                return True
            blocked_suffix = (
                ".pdf", ".zip", ".rar", ".7z", ".tar", ".gz", ".dmg", ".exe", ".apk", ".ipa",
                ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg",
                ".mp4", ".mp3", ".wav",
            )
            if any(path.endswith(sfx) for sfx in blocked_suffix):
                return True

            hard_block_domains = {
                "google.com", "search.brave.com", "duckduckgo.com", "startpage.com",
                "www.startpage.com", "qwant.com", "www.qwant.com", "webcache.googleusercontent.com",
                "translate.google.com", "googleadservices.com", "doubleclick.net", "consent.google.com",
            }
            if domain in hard_block_domains:
                return True

            blocked_path_markers = (
                "/search", "/url", "/imgres", "/aclk", "/amp/", "/amphtml/",
                "/login", "/signin", "/signup", "/account", "/share", "/ads/",
            )
            if any(marker in path for marker in blocked_path_markers):
                return True

            blocked_query_markers = ("adurl=", "redirect=", "target=", "url=")
            if any(marker in query for marker in blocked_query_markers) and domain not in {"github.com", "docs.github.com"}:
                return True

            for blocked in self.blocked_domains:
                b = blocked.lower()
                if b.startswith("www."):
                    b = b[4:]
                if domain == b or domain.endswith("." + b):
                    return True

            for p in self.low_quality_patterns:
                if p and p.lower() in raw:
                    return True
            return False
        except Exception:
            return True

    def _relevance_score(self, text: str, query_tokens: Set[str]) -> float:
        if not query_tokens:
            return 0.0
        tokens = self._token_set(text)
        if not tokens:
            return 0.0
        overlap = len(tokens & query_tokens) / max(1, len(query_tokens))
        return max(0.0, min(1.0, overlap))

    def _is_gibberish_text(self, text: str) -> bool:
        sample = (text or "").strip()
        if len(sample) < 80:
            return True
        allowed = 0
        total = 0
        for ch in sample[:5000]:
            total += 1
            cat = unicodedata.category(ch)
            if ch.isspace() or cat.startswith(("L", "N", "P", "S")):
                allowed += 1
        ratio = allowed / max(1, total)
        return ratio < 0.60

    def _lazy_init_rerank_models(self) -> None:
        """Initialize semantic/cross-encoder models once, with graceful fallback."""
        if self._models_init_done:
            return
        with self._models_init_lock:
            if self._models_init_done:
                return
            embed_ok = False
            cross_ok = False
            try:
                from sentence_transformers import SentenceTransformer
                self._embedder = SentenceTransformer("all-MiniLM-L6-v2")
                embed_ok = self._embedder is not None
            except Exception as e:
                self._embedder = None
                logger.info(f"[RERANK] embedder load skipped, using lexical fallback: {e}")
            try:
                from sentence_transformers import CrossEncoder
                self._cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
                cross_ok = self._cross_encoder is not None
            except Exception as e:
                self._cross_encoder = None
                logger.info(f"[RERANK] cross-encoder load skipped: {e}")
            finally:
                self._models_init_done = True
                logger.info("[RERANK] model status: embedder=%s cross_encoder=%s", embed_ok, cross_ok)

    def _semantic_score(self, query: str, text: str) -> float:
        if not query or not text or self._embedder is None:
            return 0.0
        key = hashlib.md5(f"sem|{query}|{text[:800]}".encode("utf-8")).hexdigest()
        if key in self._rerank_cache:
            return self._rerank_cache[key]
        try:
            qv = self._embedder.encode([query])[0]
            tv = self._embedder.encode([text])[0]
            denom = (float((qv * qv).sum()) ** 0.5) * (float((tv * tv).sum()) ** 0.5)
            score = float((qv * tv).sum() / denom) if denom > 0 else 0.0
            score = max(0.0, min(1.0, (score + 1.0) / 2.0))
        except Exception:
            score = 0.0
        self._rerank_cache[key] = score
        return score

    def _cross_score(self, query: str, text: str) -> float:
        if not query or not text or self._cross_encoder is None:
            return 0.0
        key = hashlib.md5(f"cross|{query}|{text[:800]}".encode("utf-8")).hexdigest()
        if key in self._rerank_cache:
            return self._rerank_cache[key]
        try:
            raw = float(self._cross_encoder.predict([(query, text)])[0])
            # map approximately into [0,1]
            score = 1.0 / (1.0 + pow(2.718281828, -raw))
        except Exception:
            score = 0.0
        self._rerank_cache[key] = score
        return score

    def _rerank_candidates(self, query: str, results: List[Dict], deep_research: bool = False) -> List[Dict]:
        """Hybrid rerank: lexical + semantic + cross-encoder (optional)."""
        if not results:
            return results
        q_tokens = self._token_set(query)

        # Fast path: keep reranking lightweight for normal mode.
        if not deep_research or not self._enable_semantic_rerank:
            for r in results:
                txt = f"{r.get('title', '')} {r.get('snippet', '')}"
                lex = self._relevance_score(txt, q_tokens)
                base = float(r.get("combined_score", 50.0)) / 100.0
                r["rerank_score"] = lex * 0.7 + base * 0.3
            results.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
            return results

        self._lazy_init_rerank_models()
        query_vec = None
        if query and self._embedder is not None:
            try:
                query_vec = self._embedder.encode([query])[0]
            except Exception:
                query_vec = None

        for r in results:
            txt = f"{r.get('title', '')} {r.get('snippet', '')}"
            lex = self._relevance_score(txt, q_tokens)
            sem = 0.0
            if query_vec is not None and txt:
                sem_key = hashlib.md5(f"semv|{query}|{txt[:800]}".encode("utf-8")).hexdigest()
                sem = self._rerank_cache.get(sem_key, 0.0)
                if sem <= 0.0:
                    try:
                        tv = self._embedder.encode([txt])[0]
                        denom = (float((query_vec * query_vec).sum()) ** 0.5) * (float((tv * tv).sum()) ** 0.5)
                        raw = float((query_vec * tv).sum() / denom) if denom > 0 else 0.0
                        sem = max(0.0, min(1.0, (raw + 1.0) / 2.0))
                        self._rerank_cache[sem_key] = sem
                    except Exception:
                        sem = 0.0
            r["rerank_score"] = lex * 0.65 + sem * 0.35
        results.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)

        # cross-encoder on top-k only to avoid heavy latency
        top_k = 10 if deep_research else 6
        for r in results[:top_k]:
            txt = f"{r.get('title', '')} {r.get('snippet', '')}"
            cross = self._cross_score(query, txt)
            if cross > 0:
                r["rerank_score"] = r.get("rerank_score", 0.0) * 0.6 + cross * 0.4
        results.sort(key=lambda x: x.get("rerank_score", 0.0), reverse=True)
        return results

    def _build_cache_key(self, queries: List[str], recency_priority: str, deep_research: bool) -> str:
        payload = "||".join((queries or [])) + f"|{recency_priority}|{int(bool(deep_research))}"
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    def _get_cached_search(self, key: str, ttl_seconds: int) -> Any:
        item = self._search_cache.get(key)
        if not item:
            return None
        if time.time() - float(item.get("ts", 0)) > ttl_seconds:
            self._search_cache.pop(key, None)
            return None
        return item.get("data")

    def _put_cached_search(self, key: str, data: Any) -> None:
        self._search_cache[key] = {"ts": time.time(), "data": data}
        # keep cache bounded
        if len(self._search_cache) > 256:
            oldest_key = min(self._search_cache.items(), key=lambda kv: kv[1].get("ts", 0))[0]
            self._search_cache.pop(oldest_key, None)

    def _get_cached_page(self, canonical_url: str, ttl_seconds: int = 900) -> Dict:
        item = self._page_cache.get(canonical_url)
        if not item:
            return {}
        if time.time() - float(item.get("ts", 0)) > ttl_seconds:
            self._page_cache.pop(canonical_url, None)
            return {}
        return dict(item.get("data", {}))

    def _put_cached_page(self, canonical_url: str, data: Dict) -> None:
        self._page_cache[canonical_url] = {"ts": time.time(), "data": dict(data)}
        if len(self._page_cache) > 512:
            oldest_key = min(self._page_cache.items(), key=lambda kv: kv[1].get("ts", 0))[0]
            self._page_cache.pop(oldest_key, None)
        
    def _calculate_domain_authority(self, url: str) -> float:
        """Calculate automatic domain authority score (0-100)"""
        try:
            domain = urllib.parse.urlparse(url).netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]
            if domain in self.blocked_domains:
                return 0.0
            score = 50.0  # Base score
            
            # TLD bonuses
            for tld in self.authority_tlds:
                if domain.endswith(tld):
                    score += 20
                    break
            
            # High authority domains
            high_authority = [
                'wikipedia.org', 'arxiv.org', 'github.com', 'stackoverflow.com',
                'nature.com', 'science.org', 'ieee.org', 'acm.org', 'scholar.google',
                'researchgate.net', 'medium.com', 'techcrunch', 'theverge',
                'arstechnica', 'wired.com', 'forbes.com', 'reuters.com', 'apnews.com',
                'bbc.com', 'nytimes.com', 'wsj.com',
                'openai.com', 'anthropic.com', 'ai.google.dev', 'deepmind.google',
                'developers.googleblog.com', 'huggingface.co', 'modelscope.cn',
                'zhipuai.com', 'zhipuai.cn', 'bigmodel.cn'
            ]
            for ha in high_authority:
                if ha in domain:
                    score += 25
                    break
            
            # Low quality penalties
            for lq in self.low_quality_patterns:
                if lq in domain:
                    score -= 30
                    break
            
            # News sites get recency bonus
            news_patterns = ['news', 'tin', 'bao', 'vietnamnet', 'vnexpress', 'thanhnien', 'tuoitre', 'laodong', 'dantri', '24h', 'kenh14', 'znews']
            for np in news_patterns:
                if np in domain:
                    score += 15
                    break
            
            return max(0, min(100, score))
        except:
            return 50.0
    
    def _extract_recency_from_snippet(self, snippet: str) -> float:
        """Enhanced recency detection (0-100 score). Handles min, hours, days, years."""
        if not snippet:
            return 50.0
        s = self._normalize_for_match(snippet).lower()
        now = datetime.now()
        
        # 1. Extremely recent relative patterns (Minutes/Hours) -> Ultimate priority
        if re.search(r'\b(\d+)\s*(phut|min|minute|hour|gio|hr)s?\s*(truoc|ago)\b', s):
            return 100.0
        if "vua xong" in s or "just now" in s or "live" in s:
            return 100.0
            
        # 2. Daily relative (Days)
        day_match = re.search(r'\b(\d+)\s*(ngay|day)s?\s*(truoc|ago)\b', s)
        if day_match:
            days = int(day_match.group(1))
            if days <= 1: return 99.0
            if days <= 3: return 96.0
            if days <= 7: return 92.0
            return max(70, 92 - days * 2)

        # 3. Weekly/Monthly relative
        if re.search(r'\b(\d+)\s*(tuan|week|month|thang)s?\s*(truoc|ago)\b', s):
            return 80.0

        # 4. Explicit Date Parsing (e.g., Dec 2025, 20/03/2026)
        # Year check (prioritize current and future mentioned/planned)
        year_matches = re.findall(r'\b(202[4-9]|2030)\b', s)
        if year_matches:
            latest = max(int(y) for y in year_matches)
            if latest >= now.year:
                current_month_names = [
                    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
                    "thang 1", "thang 2", "thang 3", "thang 4", "thang 5", "thang 6",
                    "thang 7", "thang 8", "thang 9", "thang 10", "thang 11", "thang 12",
                ]
                has_month_anchor = any(month in s for month in current_month_names)
                has_release_anchor = any(
                    marker in s
                    for marker in ("release", "released", "announcement", "announced", "updated", "update", "cap nhat", "ra mat")
                )
                if has_month_anchor and has_release_anchor:
                    return 92.0
                if has_month_anchor:
                    return 82.0
                if has_release_anchor:
                    return 70.0
                return 58.0
            if latest == now.year - 1:
                return 42.0
            return 20.0  # Aggressive drop for older results
        
        # 5. Semantic keywords
        boost_words = ['moi nhat', 'latest', 'new', 'breaking', 'cap nhat', 'updated', 'current']
        if any(w in s for w in boost_words):
            return 65.0
            
        return 50.0

    def _is_historical_request(self, text: str) -> bool:
        s = self._normalize_for_match(text)
        if not s:
            return False
        historical_markers = (
            "history", "historical", "timeline", "lich su", "truoc day", "ngay xua",
            "phien ban cu", "old version", "qua trinh", "tu nam", "from 20",
        )
        return any(marker in s for marker in historical_markers)

    def _is_latest_model_query(self, text: str) -> bool:
        s = self._normalize_for_match(text)
        if not s or self._is_historical_request(s):
            return False
        latest_markers = (
            "latest", "newest", "current", "moi nhat", "hien tai", "phien ban moi nhat",
            "model moi nhat", "version", "release", "phien ban", "ra mat", "cap nhat",
        )
        has_subject = bool(self._extract_latest_subjects(text))
        has_latest = any(marker in s for marker in latest_markers)
        return has_subject and (has_latest or "model" in s)

    def _latest_model_domain_policy(self, topic: str) -> Dict[str, Set[str]]:
        official: Set[str] = set()
        official_families: Set[str] = set(self.latest_model_official_domains)
        explicit_sites = self._extract_site_filters(topic)
        subjects = self._extract_latest_subjects(topic)
        for domain in explicit_sites:
            official.add(domain)
        for subject in subjects:
            official.update(self._infer_subject_domains(subject, explicit_sites=explicit_sites))
        allowed = set(official) | set(official_families) | set(self.latest_model_press_allowlist)
        return {
            "official": official,
            "official_families": official_families,
            "press": set(self.latest_model_press_allowlist),
            "allowed": allowed,
        }

    def _extract_latest_subjects(self, text: str) -> List[str]:
        t = self._normalize_for_match(text)
        if not t or self._is_historical_request(t):
            return []
        work = re.sub(r"\bsite:[a-z0-9][a-z0-9.-]*\.[a-z]{2,}\b", " ", t)
        work = re.sub(r"[|/;:+()\[\]{}]", " ", work)
        work = re.sub(r"\b(?:and|or|vs|versus|va|voi|cung|hay|hoac|with|between)\b", ",", work)
        subjects: List[str] = []
        seen: Set[str] = set()
        for raw_part in re.split(r",", work):
            subject = self._clean_latest_subject_candidate(raw_part)
            if subject and subject not in seen:
                seen.add(subject)
                subjects.append(subject)
        if subjects:
            return subjects
        fallback = self._clean_latest_subject_candidate(work)
        return [fallback] if fallback else []

    def _domain_matches_any(self, domain: str, policy_domains: Set[str]) -> bool:
        d = str(domain or "").lower().replace("www.", "")
        if not d:
            return False
        for candidate in policy_domains:
            c = str(candidate or "").lower().replace("www.", "")
            if d == c or d.endswith("." + c):
                return True
        return False

    def _source_trust_tier(self, domain: str, policy: Dict[str, Set[str]]) -> Optional[str]:
        if self._domain_matches_any(domain, policy.get("official", set())):
            return "official"
        if self._domain_matches_any(domain, policy.get("official_families", set())):
            return "official_family"
        if self._domain_matches_any(domain, policy.get("press", set())):
            return "major_press"
        return None

    def _trust_tier_sort_value(self, trust_tier: Optional[str]) -> float:
        tier = str(trust_tier or "").strip().lower()
        if tier == "official":
            return 1.0
        if tier == "official_family":
            return 0.86
        if tier == "major_press":
            return 0.68
        return 0.0

    def _extract_published_at(self, *parts: str) -> Optional[str]:
        raw_text = " ".join(str(part or "") for part in parts if part)
        text = self._normalize_for_match(raw_text)
        if not text:
            return None
        now = datetime.now()

        relative_match = re.search(r"\b(\d+)\s*(minute|min|hour|hr|gio|day|ngay|week|tuan|month|thang)s?\s*(ago|truoc)\b", text)
        if relative_match:
            value = int(relative_match.group(1))
            unit = relative_match.group(2)
            if unit in {"minute", "min"}:
                dt = now - timedelta(minutes=value)
            elif unit in {"hour", "hr", "gio"}:
                dt = now - timedelta(hours=value)
            elif unit in {"day", "ngay"}:
                dt = now - timedelta(days=value)
            elif unit in {"week", "tuan"}:
                dt = now - timedelta(weeks=value)
            else:
                dt = now - timedelta(days=value * 30)
            return dt.date().isoformat()

        iso_match = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", text)
        if iso_match:
            try:
                return datetime(int(iso_match.group(1)), int(iso_match.group(2)), int(iso_match.group(3))).date().isoformat()
            except ValueError:
                pass

        dmy_match = re.search(r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", text)
        if dmy_match:
            try:
                return datetime(int(dmy_match.group(3)), int(dmy_match.group(2)), int(dmy_match.group(1))).date().isoformat()
            except ValueError:
                pass

        month_map = {
            "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
            "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
            "august": 8, "aug": 8, "september": 9, "sept": 9, "sep": 9, "october": 10, "oct": 10,
            "november": 11, "nov": 11, "december": 12, "dec": 12,
        }
        for token, month_value in month_map.items():
            full_date = re.search(rf"\b{token}\s+(\d{{1,2}}),?\s+(20\d{{2}})\b", text)
            if full_date:
                try:
                    return datetime(int(full_date.group(2)), month_value, int(full_date.group(1))).date().isoformat()
                except ValueError:
                    pass
            month_year = re.search(rf"\b{token}\s+(20\d{{2}})\b", text)
            if month_year:
                try:
                    return datetime(int(month_year.group(1)), month_value, 1).date().isoformat()
                except ValueError:
                    pass

        vn_month = re.search(r"\bthang\s+(\d{1,2})\s+(20\d{2})\b", text)
        if vn_month:
            try:
                return datetime(int(vn_month.group(2)), int(vn_month.group(1)), 1).date().isoformat()
            except ValueError:
                pass
        return None

    def _filter_latest_model_evidence(self, items: List[Dict], topic: str) -> Tuple[List[Dict], List[Tuple[str, str, str]], Optional[str], Optional[str]]:
        policy = self._latest_model_domain_policy(topic)
        freshness_floor = datetime.now() - timedelta(days=540)
        requested_subjects = self._extract_latest_subjects(topic)
        accepted: List[Dict] = []
        rejected: List[Tuple[str, str, str]] = []

        for raw_item in items:
            item = dict(raw_item)
            url = self._canonicalize_url(str(item.get("url", "")))
            domain = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
            if not url or not domain:
                rejected.append((url, domain, "missing_url"))
                continue
            trust_tier = self._source_trust_tier(domain, policy)
            if not trust_tier:
                rejected.append((url, domain, "untrusted_domain"))
                continue
            published_at = self._extract_published_at(
                item.get("published_at", ""),
                item.get("title", ""),
                item.get("snippet", ""),
                item.get("content", ""),
                url,
            )
            evidence_text = " ".join(
                [
                    str(item.get("title", "")),
                    str(item.get("snippet", "")),
                    str(item.get("content", "")),
                    url,
                ]
            )
            if not published_at:
                if trust_tier in {"official", "official_family"} and self._is_latest_candidate_text(evidence_text):
                    published_dt = datetime.now()
                    item["derived_publish_date"] = True
                else:
                    rejected.append((url, domain, "missing_publish_date"))
                    continue
            else:
                try:
                    published_dt = datetime.fromisoformat(published_at)
                except ValueError:
                    rejected.append((url, domain, "invalid_publish_date"))
                    continue
            if published_at and published_dt < freshness_floor:
                rejected.append((url, domain, f"older_than_cutoff:{freshness_floor.date().isoformat()}"))
                continue
            matched_subjects = [subject for subject in requested_subjects if self._text_mentions_subject(subject, evidence_text)]
            if not matched_subjects:
                extracted_subjects = self._extract_latest_subjects(evidence_text)
                if requested_subjects:
                    matched_subjects = [subject for subject in extracted_subjects if subject in requested_subjects]
                else:
                    matched_subjects = extracted_subjects
            if not matched_subjects:
                if len(requested_subjects) == 1:
                    matched_subjects = list(requested_subjects)
                else:
                    rejected.append((url, domain, "subject_mismatch"))
                    continue
            item["url"] = url
            item["published_at"] = published_at
            item["published_dt"] = published_dt
            item["is_official_source"] = trust_tier in {"official", "official_family"}
            item["source_trust_tier"] = trust_tier
            item["source_rejection_reason"] = ""
            item["matched_subjects"] = matched_subjects
            accepted.append(item)

        if not accepted:
            return [], rejected, None, freshness_floor.date().isoformat()

        final_items: List[Dict] = []
        newest_by_subject: Dict[str, str] = {}
        cutoff_by_subject: Dict[str, str] = {}
        dedup_urls: Set[str] = set()
        subject_list = requested_subjects or sorted({subject for item in accepted for subject in item.get("matched_subjects", [])})

        for subject in subject_list:
            subject_items = [item for item in accepted if subject in item.get("matched_subjects", [])]
            if not subject_items:
                continue
            newest_dt = max(item["published_dt"] for item in subject_items)
            effective_cutoff_dt = max(freshness_floor, newest_dt - timedelta(days=180))
            newest_by_subject[subject] = newest_dt.date().isoformat()
            cutoff_by_subject[subject] = effective_cutoff_dt.date().isoformat()
            for item in subject_items:
                if item["published_dt"] < effective_cutoff_dt:
                    rejected.append((item.get("url", ""), urllib.parse.urlparse(item.get("url", "")).netloc.lower(), f"older_than_latest_window:{subject}:{effective_cutoff_dt.date().isoformat()}"))
                    continue
                if item["url"] in dedup_urls:
                    continue
                item["matched_subject"] = subject
                dedup_urls.add(item["url"])
                final_items.append(item)

        final_items.sort(
            key=lambda item: (
                self._trust_tier_sort_value(item.get("source_trust_tier")),
                item.get("published_dt", datetime.min),
                float(item.get("authority_score", 0.0) or 0.0),
                float(item.get("combined_score", 0.0) or 0.0),
            ),
            reverse=True,
        )
        for item in final_items:
            item.pop("published_dt", None)
        newest_summary = ", ".join(f"{subject}:{date}" for subject, date in newest_by_subject.items()) if newest_by_subject else None
        cutoff_summary = ", ".join(f"{subject}:{date}" for subject, date in cutoff_by_subject.items()) if cutoff_by_subject else freshness_floor.date().isoformat()
        missing_subjects = [subject for subject in subject_list if subject not in newest_by_subject]
        if requested_subjects and missing_subjects:
            for subject in missing_subjects:
                rejected.append(("", "", f"missing_subject:{subject}"))
        return final_items, rejected, newest_summary, cutoff_summary

    def _is_latest_candidate_text(self, text: str) -> bool:
        s = self._normalize_for_match(text)
        if not s:
            return False
        latest_markers = (
            "latest", "newest", "current", "moi nhat", "cap nhat", "release notes",
            "model release", "announcement", "rollout", "update", "gpt-5", "gpt 5",
            "gpt-5.1", "gpt 5.1", "chatgpt release notes",
        )
        return any(marker in s for marker in latest_markers)

    def _filter_latest_rss_candidates(self, items: List[Dict], topic: str) -> List[Dict]:
        if not items:
            return []
        policy = self._latest_model_domain_policy(topic)
        requested_subjects = self._extract_latest_subjects(topic)
        filtered: List[Dict] = []
        seen: Set[str] = set()
        for item in items:
            url = self._canonicalize_url(str(item.get("url") or ""))
            if not url or url in seen:
                continue
            domain = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
            trust_tier = self._source_trust_tier(domain, policy)
            if trust_tier != "major_press":
                continue
            text = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("snippet") or ""),
                    str(item.get("content") or ""),
                    url,
                ]
            )
            subject_match = any(self._text_mentions_subject(subject, text) for subject in requested_subjects) if requested_subjects else True
            if not subject_match or not self._is_latest_candidate_text(text):
                continue
            candidate = dict(item)
            candidate["url"] = url
            candidate["source_trust_tier"] = trust_tier
            candidate["is_official_source"] = False
            filtered.append(candidate)
            seen.add(url)
        return filtered

    async def close(self):
        await self.request_manager.close()

    def get_top_sources_by_topic(self, topic: str, limit: int = 20) -> List[Dict]:
        topic_key = (topic or "").strip().lower()
        if not topic_key:
            return []
        conn = sqlite3.connect(self._source_db_path)
        try:
            c = conn.cursor()
            c.execute(
                """
                SELECT topic, domain, trust_score, freshness_score, authority_score, hit_count, success_count, fail_count, last_seen
                FROM source_reputation
                WHERE topic = ?
                ORDER BY trust_score DESC, freshness_score DESC, hit_count DESC
                LIMIT ?
                """,
                (topic_key, max(1, min(200, int(limit)))),
            )
            rows = c.fetchall()
            return [
                {
                    "topic": r[0],
                    "domain": r[1],
                    "trust_score": float(r[2] or 0.0),
                    "freshness_score": float(r[3] or 0.0),
                    "authority_score": float(r[4] or 0.0),
                    "hit_count": int(r[5] or 0),
                    "success_count": int(r[6] or 0),
                    "fail_count": int(r[7] or 0),
                    "last_seen": r[8],
                }
                for r in rows
            ]
        except Exception:
            return []
        finally:
            conn.close()

    async def _search_wikipedia(self, query: str, max_results: int = 5):
        """Direct search on Wikipedia."""
        try:
            search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json"
            async with httpx.AsyncClient() as client:
                resp = await client.get(search_url, timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    results = []
                    for item in data.get('query', {}).get('search', [])[:max_results]:
                        results.append({
                            'title': item['title'],
                            'url': f"https://en.wikipedia.org/wiki/{item['title'].replace(' ', '_')}",
                            'source': 'wikipedia',
                            'snippet': item.get('snippet', '')
                        })
                    return results
            return []
        except:
            return []

    async def search_guaranteed_massive(
        self,
        query: str,
        recency_priority: str = "medium",
        min_sources: int = 20,
        deep_research: bool = False,
    ) -> List[Dict]:
        """Search with engines with early stop when enough sources found.
        
        Args:
            query: Search query
            recency_priority: "high", "medium", or "low"
            min_sources: Stop when this many unique sources found (default 7)
        """
        try:
            query = self._sanitize_query_for_web(query) or self._normalize_for_match(query)
            if not query:
                return []
            logger.info(f"[GUARANTEED-SEARCH] Query: {query} | Recency: {recency_priority} | Min sources: {min_sources}")
            is_latest_query = self._is_latest_model_query(query)
            
            # Ưu tiên engines theo độ tin cậy và tốc độ
            # Tier 1: Nhanh, ít rate limit
            # Tier 2: Chậm hơn, có thể bị rate limit
            engines_tier1 = []
            # Tavily FIRST when configured — it actually returns fresh results.
            if self._tavily_key:
                engines_tier1.append((self._search_tavily_extensive, 0.0))
            # ddgs library — reliable free default (real DDG API, no key/Docker).
            if self._enable_ddgs_lib:
                engines_tier1.append((self._search_ddgs_lib_extensive, 0.02))
            if self._enable_searxng_engine:
                engines_tier1.append((self._search_searxng_extensive, 0.05))
            engines_tier1.append((self._search_ddg_extensive, 0.15))
            if self._enable_brave_engine:
                engines_tier1.append((self._search_brave_extensive, 0.3))
            if self._enable_startpage_engine:
                engines_tier1.append((self._search_startpage_extensive, 0.42))
            engines_tier2 = []
            if self._enable_qwant_engine:
                engines_tier2.append((self._search_qwant_extensive, 0.35))
            if deep_research and self._enable_mojeek_engine:
                engines_tier2.insert(0, (self._search_mojeek_extensive, 0.45))
            
            all_results = []
            
            # Tier 1: Chạy song song, đợi kết quả
            tasks1 = []
            for func, delay in engines_tier1:
                tasks1.append(self._run_engine_with_early_stop(func, query, (45 if deep_research else 25), delay, all_results, min_sources))
            
            results1 = await asyncio.gather(*tasks1, return_exceptions=True)
            for res in results1:
                if isinstance(res, list):
                    all_results.extend(res)
            
            # Early stop check
            unique_check = self._deduplicate_comprehensive(
                all_results,
                recency_priority=recency_priority,
                topic=(query or "").strip().lower()[:220] or "general",
                critical_tokens=self._critical_tokens(query or ""),
            )
            if len(unique_check) >= min_sources:
                logger.info(f"[EARLY-STOP] Found {len(unique_check)} topical sources after Tier 1")
                return unique_check[:50]
            
            # Tier 2: Chạy nếu chưa đủ
            tasks2 = []
            for func, delay in engines_tier2:
                tasks2.append(self._run_engine_with_early_stop(func, query, 45, delay, all_results, min_sources))
            
            results2 = await asyncio.gather(*tasks2, return_exceptions=True)
            for res in results2:
                if isinstance(res, list):
                    all_results.extend(res)
            
            unique_results = self._deduplicate_comprehensive(
                all_results,
                recency_priority=recency_priority,
                topic=(query or "").strip().lower()[:220] or "general",
                critical_tokens=self._critical_tokens(query or ""),
            )
            if 0 < len(unique_results) < max(3, min_sources // 3):
                rss_results = await self._search_trusted_rss_blend(
                    query,
                    max_results=(40 if deep_research else 25),
                )
                if is_latest_query:
                    rss_results = self._filter_latest_rss_candidates(rss_results, query)
                if rss_results:
                    logger.info("[GUARANTEED-RSS-FALLBACK] Adding %d trusted RSS candidates", len(rss_results))
                    all_results.extend(rss_results)
                    unique_results = self._deduplicate_comprehensive(
                        all_results,
                        recency_priority=recency_priority,
                        topic=(query or "").strip().lower()[:220] or "general",
                        critical_tokens=self._critical_tokens(query or ""),
                    )
            logger.info(f"[SEARCH-v1] Pool: {len(all_results)} -> Unique: {len(unique_results)}")
            # Per-query contribution cap. Deep research aggregates several queries, so
            # allow each to bring more candidates toward the 100+ source target.
            return unique_results[:90 if deep_research else 50]
            
        except Exception as e:
            logger.error(f"[GUARANTEED-SEARCH-ERROR] {str(e)}")
            return []
    
    async def _run_engine_with_early_stop(self, func, query: str, limit: int, delay: float, current_results: List, min_sources: int) -> List[Dict]:
        """Run a single search engine with delay."""
        await asyncio.sleep(delay)
        try:
            return await func(query, limit)
        except Exception:
            return []

    async def _search_ddgs_lib_extensive(self, query: str, max_results: int = 20):
        """DuckDuckGo via the `ddgs` library (real API, not the bot-blocked HTML
        scrape). Free, no key, no Docker — the reliable default web provider.
        ddgs is synchronous, so run it in a thread to keep the event loop free."""
        if not self._enable_ddgs_lib:
            return []

        def _run():
            try:
                try:
                    from ddgs import DDGS  # newer package name
                except Exception:
                    from duckduckgo_search import DDGS  # legacy name
            except Exception:
                return []
            out = []
            try:
                with DDGS() as d:
                    for item in d.text(query, max_results=min(max_results, 20)):
                        url = self._canonicalize_url(str(item.get("href") or item.get("url") or "").strip())
                        if not url or self._is_blocked_url(url):
                            continue
                        out.append({
                            "title": str(item.get("title") or url).strip()[:150],
                            "url": url,
                            "snippet": str(item.get("body") or item.get("snippet") or "").strip()[:300],
                            "source": "ddgs",
                            "published_at": item.get("date") or item.get("published_at"),
                        })
            except Exception as e:
                logger.warning("ddgs query failed: %s", e)
            return out

        try:
            import asyncio
            return await asyncio.to_thread(_run)
        except Exception as e:
            logger.error("ddgs runner failed: %s", e)
            return []

    async def _search_tavily_extensive(self, query: str, max_results: int = 20):
        """Tavily Search API — reliable, AI-research-grade results (with content).
        Primary engine when SKEMI_TAVILY_KEY is set. Returns the same row shape as
        the other engines so the rest of the pipeline is unchanged."""
        if not self._tavily_key:
            return []
        try:
            resp = await self.request_manager.client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self._tavily_key,
                    "query": query,
                    "search_depth": "advanced",
                    "max_results": min(max_results, 20),
                    "include_answer": False,
                    "include_raw_content": False,
                },
                headers={"Content-Type": "application/json"},
                timeout=20.0,
            )
            if resp.status_code != 200:
                logger.warning("Tavily HTTP %s", resp.status_code)
                return []
            data = resp.json()
            rows = []
            for item in list(data.get("results") or [])[:max_results]:
                target_url = self._canonicalize_url(str(item.get("url") or "").strip())
                if not target_url or self._is_blocked_url(target_url):
                    continue
                rows.append({
                    "title": str(item.get("title") or target_url).strip()[:150],
                    "url": target_url,
                    "snippet": str(item.get("content") or "").strip()[:300],
                    "source": "tavily",
                    "published_at": item.get("published_date") or item.get("published_at"),
                })
            return rows
        except Exception as e:
            logger.error(f"Tavily search failed: {e}")
            return []

    async def _search_searxng_extensive(self, query: str, max_results: int = 20):
        """Search the self-hosted SearXNG JSON API first for free, broad retrieval."""
        if not self._enable_searxng_engine or not self._searxng_base_url:
            return []
        try:
            resp = await self.request_manager.client.get(
                f"{self._searxng_base_url}/search",
                params={
                    "q": query,
                    "format": "json",
                    "language": "all",
                    "safesearch": "0",
                    "categories": "general",
                },
                headers={
                    "Accept": "application/json",
                    **self.request_manager._get_headers(referer=self._searxng_base_url),
                },
                timeout=10.0,
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            rows = []
            for item in list(data.get("results") or [])[:max_results]:
                target_url = self._canonicalize_url(str(item.get("url") or "").strip())
                if not target_url or self._is_blocked_url(target_url):
                    continue
                rows.append(
                    {
                        "title": str(item.get("title") or target_url).strip()[:150],
                        "url": target_url,
                        "snippet": str(item.get("content") or item.get("snippet") or "").strip()[:300],
                        "source": "searxng",
                        "published_at": item.get("publishedDate") or item.get("published_date"),
                    }
                )
            return rows
        except Exception as e:
            logger.error(f"SearXNG search failed: {e}")
            return []

    async def _filter_candidates_http_200(self, results: List[Dict], max_keep: int = 25) -> List[Dict]:
        """Keep only candidates that currently resolve to HTTP 200."""
        if not results:
            return []
        sem = asyncio.Semaphore(18)
        checked: List[Dict] = []
        seen_urls: Set[str] = set()

        async def check_one(item: Dict, timeout_seconds: float) -> Optional[Dict]:
            url = self._canonicalize_url(str(item.get("url", "")))
            if not url:
                return None
            cache_item = self.request_manager.url_status_cache.get(url)
            if cache_item and (time.time() - float(cache_item.get("ts", 0))) < 600:
                if int(cache_item.get("status", 0)) == 200:
                    out = dict(item)
                    out["url"] = url
                    out["http_status"] = 200
                    return out
                return None
            async with sem:
                resp = await self.request_manager.get(url, timeout=timeout_seconds, retries=1)
                if not resp:
                    return None
                if int(resp.status_code) != 200:
                    return None
                out = dict(item)
                out["url"] = url
                out["http_status"] = 200
                return out

        async def run_wave(candidates: List[Dict], timeout_seconds: float) -> None:
            if not candidates:
                return
            tasks = [check_one(r, timeout_seconds) for r in candidates]
            res = await asyncio.gather(*tasks, return_exceptions=True)
            for it in res:
                if not isinstance(it, dict):
                    continue
                cu = self._canonicalize_url(str(it.get("url", "")))
                if not cu or cu in seen_urls:
                    continue
                seen_urls.add(cu)
                checked.append(it)

        probe_cap = min(len(results), max(50, max_keep * 3))
        first_cap = min(probe_cap, max(30, max_keep * 2))
        await run_wave(results[:first_cap], timeout_seconds=2.8)
        if len(checked) < min(max_keep, 12) and first_cap < probe_cap:
            second_cap = min(probe_cap, first_cap + 24)
            await run_wave(results[first_cap:second_cap], timeout_seconds=2.2)
            first_cap = second_cap
        if len(checked) < min(max_keep, 15) and first_cap < probe_cap:
            await run_wave(results[first_cap:probe_cap], timeout_seconds=1.8)

        return checked[:max_keep]
    
    def _quick_dedupe(self, results: List[Dict]) -> List[Dict]:
        """Quick deduplication for early stop check."""
        seen = set()
        unique = []
        for r in results:
            url = self._canonicalize_url(r.get('url', ''))
            if not url or self._is_blocked_url(url):
                continue
            if url not in seen:
                seen.add(url)
                unique.append(r)
        return unique

    async def _search_brave_extensive(self, query: str, max_results: int = 15):
        """Search Brave with improved link extraction."""
        try:
            url = f"https://search.brave.com/search?q={urllib.parse.quote_plus(query)}"
            resp = await self.request_manager.get(url, retries=1)
            if not resp or not resp.text: return []
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            items = soup.select('[data-type="web"]') or soup.select('.snippet')
            
            for item in items[:max_results]:
                try:
                    link_elem = item.select_one('a[href^="http"]:not([href*="brave.com"])')
                    if not link_elem:
                        for a in item.find_all('a'):
                            href = a.get('href', '')
                            if href.startswith('http') and 'brave.com' not in href:
                                link_elem = a; break
                    
                    if link_elem and (url := link_elem.get('href')):
                        title = link_elem.get_text(strip=True) or url
                        snippet = ""
                        snippet_elem = item.select_one('.snippet-content') or item.select_one('.snippet-description')
                        if snippet_elem: snippet = snippet_elem.get_text(strip=True)
                        results.append({'title': title[:150], 'url': url, 'snippet': snippet[:300], 'source': 'brave'})
                except: continue
            return results
        except Exception as e:
            logger.error(f"Brave search failed: {e}")
            return []

    async def _search_startpage_extensive(self, query: str, max_results: int = 15):
        """Search Startpage."""
        try:
            url = f"https://www.startpage.com/sp/search?query={urllib.parse.quote_plus(query)}"
            resp = await self.request_manager.get(url)
            if not resp or not resp.text: return []
            if "/sp/captcha" in str(resp.url).lower() or "/sp/captcha" in resp.text.lower():
                logger.info("Startpage captcha detected; skipping this engine for now.")
                self.request_manager.host_cooldown_until["www.startpage.com"] = time.time() + 300.0
                return []
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            items = soup.select('div.result') or soup.select('div.w-gl__result')
            for section in items[:max_results]:
                try:
                    title_elem = section.select_one('a.result-link') or section.select_one('a.w-gl__result-url') or section.find('a')
                    if not title_elem: continue
                    title = title_elem.get_text(strip=True)
                    url = title_elem.get('href', '')
                    snippet = ""
                    snippet_elem = section.select_one('.result-snippet') or section.select_one('.w-gl__description')
                    if snippet_elem: snippet = snippet_elem.get_text(strip=True)
                    if url and url.startswith('http') and 'startpage.com' not in url:
                        results.append({'title': title[:150], 'url': url, 'snippet': snippet[:300], 'source': 'startpage'})
                except: continue
            return results
        except Exception as e:
            logger.error(f"Startpage failed: {e}")
            return []

    async def _search_trusted_rss_blend(self, query: str, max_results: int = 25):
        """Resilient fallback: aggregate trusted global RSS feeds when web engines are blocked."""
        feeds = [
            ("bbc", "https://feeds.bbci.co.uk/news/world/rss.xml"),
            ("bbc", "https://feeds.bbci.co.uk/news/business/rss.xml"),
            ("guardian", "https://www.theguardian.com/world/rss"),
            ("nytimes", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
            ("reuters", "https://www.reutersagency.com/feed/?best-topics=world&post_type=best"),
            ("reuters", "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best"),
            ("aljazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
            ("techcrunch", "https://techcrunch.com/feed/"),
        ]
        q_norm = self._normalize_for_match(query or "")
        query_tokens = {t for t in self._token_set(q_norm) if t not in {"ban", "biet", "dang", "co", "su", "kien", "o", "khong"}}
        if "trung dong" in q_norm:
            query_tokens.update({"middle", "east"})
        if "trung quoc" in q_norm:
            query_tokens.update({"china"})

        out: List[Dict] = []
        seen = set()
        async def fetch_feed(source: str, feed_url: str) -> List[Dict]:
            try:
                resp = await self.request_manager.get(feed_url, retries=1, timeout=4.0)
                if not resp or int(resp.status_code) != 200:
                    return []
                parsed = feedparser.parse(resp.content)
                entries = list(getattr(parsed, "entries", []) or [])[:12]
                local_items: List[Dict] = []
                for e in entries:
                    link = str(getattr(e, "link", "") or "").strip()
                    title = str(getattr(e, "title", "") or "").strip()
                    if not link or not title or not link.startswith("http"):
                        continue
                    summary_raw = str(getattr(e, "summary", "") or getattr(e, "description", "") or "")
                    summary = BeautifulSoup(summary_raw, "html.parser").get_text(" ", strip=True)[:300]
                    local_items.append(
                        {
                            "title": title[:150],
                            "url": link,
                            "snippet": summary,
                            "source": f"rss:{source}",
                        }
                    )
                return local_items
            except Exception:
                return []

        batches = await asyncio.gather(
            *[fetch_feed(source, feed_url) for source, feed_url in feeds],
            return_exceptions=True,
        )
        for batch in batches:
            if not isinstance(batch, list):
                continue
            for item in batch:
                link = str(item.get("url", "")).strip()
                title = str(item.get("title", "")).strip()
                key = self._canonicalize_url(link)
                if not key or key in seen or not title:
                    continue
                bag = self._token_set(self._normalize_for_match(f"{title} {item.get('snippet', '')} {link}"))
                if query_tokens:
                    overlap = len(query_tokens & bag) / max(1, len(query_tokens))
                    if overlap < 0.15 and len(out) >= 10:
                        continue
                seen.add(key)
                out.append(item)
                if len(out) >= max_results:
                    return out
        return out

    async def _search_ddg_extensive(self, query: str, max_results: int = 15):
        try:
            url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
            headers = self.request_manager._get_headers(referer="https://duckduckgo.com/")
            resp = await self.request_manager.get(url, headers=headers)
            if not resp or not resp.text: return []
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for item in soup.select('.result')[:max_results]:
                try:
                    title_elem = item.select_one('.result__a')
                    if not title_elem: continue
                    url = title_elem.get('href', '')
                    if 'duckduckgo.com/l/?' in url:
                        parsed_url = urllib.parse.urlparse(url)
                        url = urllib.parse.parse_qs(parsed_url.query).get('uddg', [url])[0]
                    snippet = ""
                    snippet_elem = item.select_one('.result__snippet')
                    if snippet_elem: snippet = snippet_elem.get_text(strip=True)
                    if url.startswith('http'):
                        results.append({'title': title_elem.get_text(strip=True)[:150], 'url': url, 'snippet': snippet[:300], 'source': 'ddg'})
                except: continue
            return results
        except Exception as e:
            logger.error(f"DDG failed: {e}")
            return []

    async def _search_bing_extensive(self, query: str, max_results: int = 20):
        try:
            url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}"
            resp = await self.request_manager.get(url)
            if not resp or not resp.text: return []
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            items = soup.select('.b_algo') or soup.find_all('li', class_='b_algo')
            for item in items[:max_results]:
                try:
                    link = item.find('a')
                    if link and (url := link.get('href')) and url.startswith('http') and 'bing.com' not in url:
                        snippet = ""
                        snippet_elem = item.select_one('.b_caption p') or item.select_one('.b_snippet') or item.select_one('.st')
                        if snippet_elem: snippet = snippet_elem.get_text(strip=True)
                        results.append({'title': link.get_text(strip=True)[:150], 'url': url, 'snippet': snippet[:300], 'source': 'bing'})
                except: continue
            return results
        except Exception as e:
            logger.error(f"Bing failed: {e}")
            return []

    async def _search_swisscows_extensive(self, query: str, max_results: int = 15):
        try:
            url = f"https://swisscows.com/web?query={urllib.parse.quote_plus(query)}"
            resp = await self.request_manager.get(url)
            if not resp or not resp.text: return []
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for item in soup.select('article')[:max_results]:
                try:
                    link = item.find('a')
                    if link and (url := link.get('href')) and url.startswith('http'):
                        snippet = ""
                        snippet_elem = item.select_one('.description')
                        if snippet_elem: snippet = snippet_elem.get_text(strip=True)
                        results.append({'title': link.get_text(strip=True)[:150], 'url': url, 'snippet': snippet[:300], 'source': 'swisscows'})
                except: continue
            return results
        except Exception as e:
            logger.error(f"Swisscows failed: {e}")
            return []

    async def _search_mojeek_extensive(self, query: str, max_results: int = 15):
        try:
            url = f"https://www.mojeek.com/search?q={urllib.parse.quote_plus(query)}"
            resp = await self.request_manager.get(url)
            if not resp or not resp.text: return []
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            for item in soup.select('.ob')[:max_results]:
                try:
                    link = item.select_one('a.t')
                    if link and (url := link.get('href')) and url.startswith('http'):
                        snippet = ""
                        snippet_elem = item.select_one('.s') or item.select_one('p')
                        if snippet_elem: snippet = snippet_elem.get_text(strip=True)
                        results.append({'title': link.get_text(strip=True)[:150], 'url': url, 'snippet': snippet[:300], 'source': 'mojeek'})
                except: continue
            return results
        except Exception as e:
            logger.error(f"Mojeek failed: {e}")
            return []

    async def _search_qwant_extensive(self, query: str, max_results: int = 15):
        try:
            url = f"https://www.qwant.com/?q={urllib.parse.quote_plus(query)}&t=web"
            resp = await self.request_manager.get(url)
            if not resp or not resp.text: return []
            soup = BeautifulSoup(resp.text, 'html.parser')
            results = []
            items = soup.select('div.result-link') or soup.select('div[class*="result__link"]') or soup.find_all('a', class_=re.compile(r'external-link|result__link|url', re.I))
            for item in items[:max_results]:
                try:
                    href = item.get('href', '')
                    if href.startswith('http') and 'qwant.com' not in href:
                        title = item.get_text(strip=True) or href
                        results.append({'title': title[:150], 'url': href, 'source': 'qwant'})
                except: continue
            return results
        except Exception as e:
            logger.error(f"Qwant failed: {e}")
            return []

    def _deduplicate_comprehensive(
        self,
        results: List[Dict],
        recency_priority: str = "medium",
        topic: str = "general",
        critical_tokens: Optional[Set[str]] = None,
    ) -> List[Dict]:
        """Deduplicate and rank results by domain authority and recency"""
        seen_urls = set()
        unique_results = []
        domain_counts = {}
        rep_rows = self.get_top_sources_by_topic(topic, limit=200)
        rep_map = {
            str(r.get("domain", "")).replace("www.", "").strip().lower(): r
            for r in (rep_rows or [])
            if str(r.get("domain", "")).strip()
        }
        
        for r in results:
            url = self._canonicalize_url(r.get('url', ''))
            if not url or url in seen_urls: continue
            if self._is_blocked_url(url):
                continue
            title = str(r.get("title", ""))
            snippet = str(r.get("snippet", ""))
            text_for_match = f"{title} {snippet} {url}"
            if not self._matches_critical_tokens(text_for_match, critical_tokens or set()):
                continue
            domain = urllib.parse.urlparse(url).netloc
            if not domain or any(bad in domain for bad in ['google.', 'youtube.', 'search.', 'bing.com', 'duckduckgo.com']): continue
            if not self._domain_relevant_for_topic(domain, url, topic):
                continue
            if domain_counts.get(domain, 0) >= 2: continue
            seen_urls.add(url)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            r['url'] = url
            
            # Calculate authority score
            authority_score = self._calculate_domain_authority(url)
            r['authority_score'] = authority_score
            low_signal_penalty = self._search_low_signal_penalty(title, snippet, url)
            r['low_signal_penalty'] = low_signal_penalty
            
            # Calculate recency score from snippet + title + url
            recency_score = self._extract_recency_from_snippet(
                f"{r.get('title', '')} {r.get('snippet', '')} {url}"
            )
            r['recency_score'] = recency_score
            published_at = self._extract_published_at(
                r.get("published_at", ""),
                r.get("title", ""),
                r.get("snippet", ""),
                url,
            )
            if published_at:
                r["published_at"] = published_at
            
            # Combined score based on recency priority
            if recency_priority == "high":
                # Prioritize freshness, but keep trust floor from authority
                r['combined_score'] = authority_score * 0.25 + recency_score * 0.75
            elif recency_priority == "medium":
                r['combined_score'] = authority_score * 0.4 + recency_score * 0.6
            else:
                r['combined_score'] = authority_score * 0.6 + recency_score * 0.4

            # Penalize very low-authority source even if very fresh.
            if authority_score < 35:
                r['combined_score'] *= 0.75
            if low_signal_penalty > 0:
                r['combined_score'] -= low_signal_penalty * 4.5

            rep = rep_map.get(domain.replace("www.", "").lower())
            if rep:
                trust_hist = float(rep.get("trust_score", 0.0) or 0.0)
                fresh_hist = float(rep.get("freshness_score", 0.0) or 0.0)
                auth_hist = float(rep.get("authority_score", 0.0) or 0.0)
                hist_score = trust_hist * 0.6 + fresh_hist * 0.2 + auth_hist * 0.2
                r['combined_score'] = r['combined_score'] * 0.8 + hist_score * 0.2
                r['historical_score'] = hist_score
            else:
                r['historical_score'] = 0.0

            # In high-recency mode, reject weak/unknown domains aggressively.
            if recency_priority == "high":
                hist_ok = float(r.get("historical_score", 0.0) or 0.0) >= 60.0
                if authority_score < 38 and not hist_ok:
                    continue
                if low_signal_penalty >= 4.0 and authority_score < 65.0 and not hist_ok:
                    continue
            
            unique_results.append(r)
            self._upsert_source_reputation(
                topic=topic,
                domain=domain,
                authority=authority_score,
                recency=recency_score,
                trust=r['combined_score'],
                success=True,
            )
        
        
        # Sort by combined score (higher is better)
        unique_results.sort(key=lambda x: x.get('combined_score', 50), reverse=True)
        
        logger.info(
            "[RANKING] Top 5 domains (authority, freshness, trust): %s",
            [
                (
                    urllib.parse.urlparse(r['url']).netloc,
                    round(float(r.get('authority_score', 0.0)), 1),
                    round(float(r.get('recency_score', 0.0)), 1),
                    round(float(r.get('combined_score', 0.0)), 1),
                )
                for r in unique_results[:5]
            ],
        )
        
        return unique_results

    def _deduplicate_relaxed(self, results: List[Dict], recency_priority: str = "medium") -> List[Dict]:
        """Relaxed fallback when strict topical filters return too few sources."""
        seen_urls = set()
        unique_results: List[Dict] = []
        domain_counts: Dict[str, int] = {}

        for r in results:
            url = self._canonicalize_url(r.get('url', ''))
            if not url or url in seen_urls:
                continue
            if self._is_blocked_url(url):
                continue
            domain = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
            if not domain:
                continue
            if domain_counts.get(domain, 0) >= 2:
                continue
            seen_urls.add(url)
            domain_counts[domain] = domain_counts.get(domain, 0) + 1

            authority_score = self._calculate_domain_authority(url)
            recency_score = self._extract_recency_from_snippet(
                f"{r.get('title', '')} {r.get('snippet', '')} {url}"
            )
            if recency_priority == "high":
                combined_score = authority_score * 0.30 + recency_score * 0.70
            elif recency_priority == "medium":
                combined_score = authority_score * 0.45 + recency_score * 0.55
            else:
                combined_score = authority_score * 0.60 + recency_score * 0.40

            out = dict(r)
            out["url"] = url
            out["authority_score"] = authority_score
            out["recency_score"] = recency_score
            out["combined_score"] = combined_score
            unique_results.append(out)

        unique_results.sort(key=lambda x: x.get("combined_score", 0.0), reverse=True)
        return unique_results

    async def _prepare_candidate_pool(
        self,
        all_search_results: List[Dict],
        queries: List[str],
        recency_priority: str,
        deep_research: bool,
        is_latest_query: bool,
        min_sources: int,
        max_sources: int,
    ) -> List[Dict]:
        topic = self._topic_key(queries)
        combined_critical_tokens = self._critical_tokens(" ".join(queries or []))
        unique_search_results = self._deduplicate_comprehensive(
            all_search_results,
            recency_priority=recency_priority,
            topic=topic,
            critical_tokens=combined_critical_tokens,
        )
        if is_latest_query:
            latest_policy = self._latest_model_domain_policy(topic)
            prefiltered_results = []
            rejected_domains = []
            for result in unique_search_results:
                domain = urllib.parse.urlparse(result.get("url", "")).netloc.lower().replace("www.", "")
                if self._domain_matches_any(domain, latest_policy.get("allowed", set())):
                    trust_tier = self._source_trust_tier(domain, latest_policy)
                    result["is_official_source"] = trust_tier in {"official", "official_family"}
                    result["source_trust_tier"] = trust_tier
                    result["source_rejection_reason"] = ""
                    prefiltered_results.append(result)
                else:
                    rejected_domains.append((domain, "untrusted_domain"))
            if rejected_domains:
                logger.info("[LATEST-MODEL] Rejected pre-rank domains: %s", rejected_domains[:12])
            unique_search_results = prefiltered_results

        query_focus_sets = []
        for query in queries or []:
            focus_tokens = self._query_focus_tokens(query)
            if focus_tokens:
                query_focus_sets.append(focus_tokens)

        if combined_critical_tokens:
            topic_focused = []
            for result in unique_search_results:
                focus_text = " ".join(
                    [
                        str(result.get("title", "")),
                        str(result.get("snippet", "")),
                        str(result.get("url", "")),
                    ]
                )
                if len(query_focus_sets) > 1:
                    if any(self._matches_critical_tokens(focus_text, focus_tokens) for focus_tokens in query_focus_sets):
                        topic_focused.append(result)
                elif self._matches_critical_tokens(focus_text, combined_critical_tokens):
                    topic_focused.append(result)
            if topic_focused:
                unique_search_results = topic_focused

        support_filtered = []
        for result in unique_search_results:
            focus_text = " ".join(
                [
                    str(result.get("title", "")),
                    str(result.get("snippet", "")),
                    str(result.get("url", "")),
                ]
            )
            matched_queries = self._matched_queries_for_text(focus_text, queries)
            result["matched_queries"] = matched_queries
            result["primary_query"] = matched_queries[0] if matched_queries else ""
            support_count, max_hits = self._candidate_query_support_metrics(focus_text, queries)
            result["query_support_count"] = support_count
            result["query_match_hits_max"] = max_hits
            authority_score = float(result.get("authority_score", 0.0) or 0.0)
            low_signal_penalty = float(result.get("low_signal_penalty", 0.0) or 0.0)
            trust_tier = str(result.get("source_trust_tier") or "").strip().lower()
            trusted_source = bool(result.get("is_official_source")) or trust_tier in {
                "official",
                "official_family",
                "major_press",
                "docs",
            }
            if is_latest_query and low_signal_penalty >= 4.0 and not trusted_source and authority_score < 68.0:
                continue
            if len(query_focus_sets) <= 1:
                single_focus = query_focus_sets[0] if query_focus_sets else set()
                required_hits = 1 if len(single_focus) <= 3 or trusted_source or authority_score >= 65.0 else 2
                if max_hits >= required_hits:
                    support_filtered.append(result)
            else:
                if support_count >= 1 or (max_hits >= 1 and (trusted_source or authority_score >= 65.0)):
                    support_filtered.append(result)
        if support_filtered:
            unique_search_results = support_filtered

        query_tokens: Set[str] = set()
        for focus_tokens in query_focus_sets:
            query_tokens.update(focus_tokens)
        if not query_tokens:
            query_tokens = self._token_set(" ".join(queries or []))
        filtered_results = []
        for result in unique_search_results:
            txt = f"{result.get('title','')} {result.get('snippet','')}"
            rel = self._relevance_score(txt, query_tokens)
            result['relevance_score'] = rel
            low_signal_penalty = float(result.get("low_signal_penalty", 0.0) or 0.0)
            rel_threshold = (0.12 if deep_research else 0.18) + min(0.08, low_signal_penalty * 0.015)
            if rel >= rel_threshold:
                filtered_results.append(result)
        if filtered_results:
            unique_search_results = filtered_results

        query_for_rank = " | ".join((queries or [])[:2]).strip()
        unique_search_results.sort(
            key=lambda item: (
                item.get('query_support_count', 0.0) * 0.30
                + item.get('query_match_hits_max', 0.0) * 0.10
                + item.get('relevance_score', 0.0) * 0.35
                + (item.get('combined_score', 50.0) / 100.0) * 0.25
            ),
            reverse=True,
        )
        unique_search_results = self._rerank_candidates(query_for_rank, unique_search_results, deep_research=deep_research)
        unique_search_results.sort(
            key=lambda item: (
                item.get('query_support_count', 0.0) * 0.30
                + item.get('query_match_hits_max', 0.0) * 0.10
                + item.get('rerank_score', 0.0) * 0.35
                + (item.get('combined_score', 50.0) / 100.0) * 0.25
            ),
            reverse=True,
        )
        pre_http_results = list(unique_search_results)
        unique_search_results = await self._filter_candidates_http_200(
            pre_http_results,
            max_keep=max_sources,
        )
        unique_search_results = self._apply_freshness_window(
            unique_search_results,
            recency_priority,
            min_keep=max(4, min_sources // 3),
        )
        if recency_priority == "high" and len(unique_search_results) < max(4, min_sources // 3):
            seen_urls = {self._canonicalize_url(item.get("url", "")) for item in unique_search_results}
            snippet_fallback_count = 0
            for item in pre_http_results:
                canonical_url = self._canonicalize_url(item.get("url", ""))
                if not canonical_url or canonical_url in seen_urls:
                    continue
                if not str(item.get("snippet") or item.get("title") or "").strip():
                    continue
                if float(item.get("low_signal_penalty", 0.0) or 0.0) >= 4.0:
                    continue
                if float(item.get("authority_score", 0.0) or 0.0) < 55.0 and float(item.get("query_match_hits_max", 0.0) or 0.0) < 2.0:
                    continue
                out = dict(item)
                out["url"] = canonical_url
                out["http_status"] = out.get("http_status") or 0
                out["snippet_only"] = True
                unique_search_results.append(out)
                seen_urls.add(canonical_url)
                snippet_fallback_count += 1
                if len(unique_search_results) >= max_sources:
                    break
            if snippet_fallback_count:
                unique_search_results = self._apply_freshness_window(
                    unique_search_results,
                    recency_priority,
                    min_keep=max(4, min_sources // 3),
                )
                logger.info(
                    "[SNIPPET-FALLBACK] Added %d trusted snippet-only candidates after HTTP200 filtering",
                    snippet_fallback_count,
                )
        if is_latest_query and len(unique_search_results) < min(max_sources, max(5, min_sources // 2)):
            seen_urls = {self._canonicalize_url(item.get("url", "")) for item in unique_search_results}
            snippet_fallback_count = 0
            for item in pre_http_results:
                canonical_url = self._canonicalize_url(item.get("url", ""))
                if not canonical_url or canonical_url in seen_urls:
                    continue
                if not str(item.get("snippet") or item.get("title") or "").strip():
                    continue
                if float(item.get("low_signal_penalty", 0.0) or 0.0) >= 4.0:
                    continue
                out = dict(item)
                out["url"] = canonical_url
                out["http_status"] = out.get("http_status") or 0
                out["snippet_only"] = True
                unique_search_results.append(out)
                seen_urls.add(canonical_url)
                snippet_fallback_count += 1
                if len(unique_search_results) >= max_sources:
                    break
            if snippet_fallback_count:
                logger.info(
                    "[LATEST-SNIPPET-FALLBACK] Added %d trusted snippet-only candidates after HTTP200 filtering",
                    snippet_fallback_count,
                )
        logger.info(
            "[HTTP200-FILTER] retained=%d target=%d-%d deep=%s",
            len(unique_search_results),
            min_sources,
            max_sources,
            deep_research,
        )
        return unique_search_results

    async def crawl_optimized_target_15(self, urls: List[str], min_pages: int = 5, max_pages: int = 10, deadline_ts: float = None) -> List[Dict]:
        """Crawl with early stop when enough pages found.
        
        Args:
            urls: List of URLs to crawl
            min_pages: Minimum pages to find before stopping (default 5)
            max_pages: Maximum pages to crawl (default 10)
        """
        try:
            def get_authority(url):
                return self._calculate_domain_authority(url)
            
            filtered_urls = []
            for u in urls:
                cu = self._canonicalize_url(u)
                if self._is_blocked_url(cu):
                    continue
                filtered_urls.append(cu)

            sorted_urls = sorted(filtered_urls, key=get_authority, reverse=True)
            urls_pool = sorted_urls[:30]  # Giảm pool size
            
            logger.info(f"[CRAWL-ELITE] Pool: {len(urls_pool)} URLs | Target: {min_pages}-{max_pages} pages")
            start_time = time.time()
            successful_crawls = []
            batch_size = 6  # Giảm batch size
            
            for i in range(0, len(urls_pool), batch_size):
                if deadline_ts and time.time() >= deadline_ts:
                    logger.info("[CRAWL-BUDGET] Deadline reached, stop crawling")
                    break
                batch = urls_pool[i:i + batch_size]
                logger.info(f"[CRAWL-STEP] Batch {i//batch_size + 1}. Success: {len(successful_crawls)}/{min_pages}")
                
                tasks = [self._crawl_single_with_deep_retry(url) for url in batch]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for res in results:
                    if isinstance(res, dict) and res.get('success'):
                        if len(res.get('content','')) > 80:
                            successful_crawls.append(res)
                
                # Early stop khi đủ
                if len(successful_crawls) >= min_pages:
                    logger.info(f"[CRAWL-EARLY-STOP] Found {len(successful_crawls)} pages, stopping")
                    break
            
            final_crawls = successful_crawls[:max_pages]
            logger.info(f"[CRAWL-FINAL] {len(final_crawls)} pages in {time.time()-start_time:.2f}s")
            return final_crawls
        except Exception as e:
            logger.error(f"[CRAWL-CRITICAL-ERROR] {str(e)}")
            return []

    async def _crawl_single_with_deep_retry(self, url: str):
        """Internal multi-tiered retry for a single URL until success or exhausted."""
        methods = ['normal', 'basic', 'mobile']
        for method in methods:
            try:
                res = await self._crawl_single_with_retry(url, method=method)
                if res.get('success') and len(res.get('content','')) > 80:  # GIẢM từ 150 xuống 80
                    return res
                if method != methods[-1]:
                    await asyncio.sleep(0.1)  # GIẢM delay
            except:
                continue
        return {'success': False, 'url': url}

    async def _crawl_single_with_retry(self, url: str, method: str = 'normal'):
        try:
            canonical_url = self._canonicalize_url(url)
            if self._is_blocked_url(canonical_url):
                return {'success': False, 'url': canonical_url, 'reason': 'blocked_domain'}

            cached = self._get_cached_page(canonical_url, ttl_seconds=900)
            if cached:
                return cached

            headers = self.request_manager._get_headers(referer="https://www.google.com/")
            if method == 'bot':
                headers['User-Agent'] = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
            elif method == 'mobile':
                headers['User-Agent'] = "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1"
            
            resp = await self.request_manager.get(canonical_url, headers=headers, timeout=8, retries=1)
            if not resp or not resp.text:
                return {'success': False, 'url': canonical_url, 'reason': 'no_response'}

            content_type = resp.headers.get('content-type', '').lower()
            if 'html' not in content_type:
                return {'success': False, 'url': canonical_url, 'reason': f'non_html_content:{content_type}'}

            low = resp.text.lower()
            blocking_signals = [t for t in ["access denied", "security check", "captcha", "cloudflare", "blocked"] if t in low]

            content = ""
            title = "No title"
            try:
                # Use trafilatura for robust main content extraction
                content = trafilatura.extract(resp.text, include_comments=False, include_tables=True, favor_recall=True) or ""
                
                # Fallback to BeautifulSoup for title, as it's generally reliable for this
                soup = BeautifulSoup(resp.text, 'html.parser')
                if soup.title and soup.title.string:
                    title = soup.title.string.strip()[:150]
                # Strong fallback: if trafilatura fails/empty, extract visible text from HTML.
                if len(content or "") < 80:
                    content = self._extract_high_quality_content(soup) or content
            except Exception as e:
                logger.warning(f"Crawling content/title extraction error for {canonical_url}: {e}")
                try:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    if soup.title and soup.title.string:
                        title = soup.title.string.strip()[:150]
                    content = self._extract_high_quality_content(soup) or ""
                except Exception:
                    return {'success': False, 'url': canonical_url, 'reason': f'extraction_error:{e}'}

            if len(content) > 80:
                if self._is_gibberish_text(content):
                    if blocking_signals:
                        return {
                            'success': False,
                            'url': canonical_url,
                            'reason': f"blocked_page:{','.join(blocking_signals[:2])}",
                        }
                    return {'success': False, 'url': canonical_url, 'reason': 'gibberish'}
                result = {
                    'success': True,
                    'title': title,
                    'content': content[:8000], # Increased content limit
                    'url': canonical_url,
                    'content_length': len(content),
                    'method': method,
                }
                if blocking_signals:
                    result['page_protection_signals'] = blocking_signals[:3]
                self._put_cached_page(canonical_url, result)
                return result

            if blocking_signals:
                return {
                    'success': False,
                    'url': canonical_url,
                    'reason': f"blocked_page:{','.join(blocking_signals[:2])}",
                }
            return {'success': False, 'url': canonical_url, 'reason': f'short_content ({len(content)})'}
        
        except Exception as e:
            logger.error(f"Critical crawl error for {url}: {e}", exc_info=True)
            return {'success': False, 'url': self._canonicalize_url(url), 'error': str(e)}



    def _extract_high_quality_content(self, soup) -> str:
        """Enhanced content extractor that handles tables and lists better."""
        content_parts = []
        
        # Try to find main content areas
        main_content = soup.find('article') or soup.find('main') or \
                       soup.find('div', id=re.compile(r'content|main|article|post', re.I)) or \
                       soup.find('div', class_=re.compile(r'content|main|article|post|entry', re.I))
        
        search_area = main_content if main_content else soup.body
        if not search_area: return ""

        # Recursive extraction for better structure
        for elem in search_area.find_all(['h1', 'h2', 'h3', 'p', 'li', 'tr', 'table']):
            if elem.name in ['h1', 'h2', 'h3']:
                text = elem.get_text(strip=True)
                if text: content_parts.append(f"\n### {text} ###\n")
            elif elem.name == 'p':
                text = elem.get_text(" ", strip=True)
                if len(text.split()) > 4: content_parts.append(text)
            elif elem.name == 'li':
                text = elem.get_text(" ", strip=True)
                if len(text.split()) > 2: content_parts.append(f"- {text}")
            elif elem.name == 'table':
                # Handle tables by extracting rows efficiently
                rows = []
                for tr in elem.find_all('tr'):
                    cells = [td.get_text(" ", strip=True) for td in tr.find_all(['td', 'th'])]
                    if cells: rows.append(" | ".join(cells))
                if rows:
                    content_parts.append("\n[TABLE START]\n" + "\n".join(rows) + "\n[TABLE END]\n")
            elif elem.name == 'tr':
                # Only process tr if it's NOT inside a table we already handled
                if not elem.find_parent('table'):
                    cells = [td.get_text(" ", strip=True) for td in elem.find_all(['td', 'th'])]
                    if cells: content_parts.append(" | ".join(cells))

        text = '\n'.join(content_parts)
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    async def smart_search(self, user_query: str, recency_priority: str = "medium", deep_research: bool = False, query_class: str = "general", on_progress: Optional[Any] = None) -> dict:
        return await self.smart_search_multi([user_query], recency_priority=recency_priority, deep_research=deep_research, query_class=query_class, on_progress=on_progress)

    async def smart_search_multi(self, queries: List[str], recency_priority: str = "medium", deep_research: bool = False, query_class: str = "general", on_progress: Optional[Any] = None) -> dict:
        """Execute multiple queries, consolidate results, and crawl best targets."""
        try:
            if queries and all(self._is_internal_payload_query(q) for q in queries):
                return {"context": "LOCAL_FILE_CONTEXT_ONLY", "urls": []}
            cleaned_queries: List[str] = []
            for q in (queries or []):
                cq = self._sanitize_query_for_web(q)
                if cq and cq not in cleaned_queries:
                    cleaned_queries.append(cq)
            if cleaned_queries:
                queries = cleaned_queries
            effective_deep_research = bool(deep_research)
            query_budget = 5 if not effective_deep_research else 7
            if len(queries) > query_budget:
                queries = queries[:query_budget]
            latest_topic = " ".join(queries or [])
            normalized_query_class = str(query_class or "general").strip().lower()
            is_latest_query = normalized_query_class == "latest_model" or any(
                self._is_latest_model_query(q) for q in (queries or [])
            )
            if on_progress:
                await on_progress("Đang tổng hợp và đối soát dữ liệu..." if "vi" in str(os.getenv("SKEMI_LANG", "vi")) else "Synthesizing and cross-referencing neural data...")
            cache_key = self._build_cache_key(queries, recency_priority, effective_deep_research) + (f"|{normalized_query_class}" if normalized_query_class else "")
            cached = self._get_cached_search(cache_key, ttl_seconds=(300 if effective_deep_research else 120))
            if cached:
                logger.info("[MULTI-SEARCH-CACHE] Hit latest_model=%s", is_latest_query)
                if isinstance(cached, dict):
                    return cached
                return {"context": str(cached), "urls": []}

            logger.info(f"[MULTI-SEARCH] Queries: {len(queries)} | Recency: {recency_priority} | Deep: {effective_deep_research}")
            search_start = time.time()
            base_budget = self._deep_max_seconds if effective_deep_research else self._std_max_seconds
            per_query_budget = 5.0 if effective_deep_research else 4.0
            if recency_priority == "high":
                per_query_budget += 1.0
            max_total_seconds = base_budget + max(0, min(len(queries), 8) - 1) * per_query_budget
            if len(queries) > 1:
                max_total_seconds += min(len(queries), 8) * (4.0 if effective_deep_research else 3.0)
                max_total_seconds = max(max_total_seconds, 180.0 if effective_deep_research else 120.0)
            deadline_ts = search_start + max_total_seconds
            query_tokens: Set[str] = set()
            for query in queries or []:
                query_tokens.update(self._query_focus_tokens(query))
            if not query_tokens:
                query_tokens = self._token_set(" ".join(queries or []))

            min_sources = self._deep_min_sources if effective_deep_research else self._std_min_sources
            max_sources = self._deep_max_sources if effective_deep_research else self._std_max_sources
            required_sources = min_sources
            min_context_chars = self._deep_min_context_chars if effective_deep_research else self._std_min_context_chars
            all_search_results = []
            per_query_target = 2 if len(queries) > 1 else 1

            async def _collect_query_results(query_text: str, *, pass_deep: bool, pass_min_sources: int) -> int:
                if on_progress:
                    # Diversify messages based on query index or content
                    msg_vi = f"Đang dò tìm: {query_text}..."
                    msg_en = f"Probing depth for: {query_text}..."
                    
                    if i == 0:
                        msg_vi = f"Khởi tạo hạt giống nơ-ron: {query_text}..."
                        msg_en = f"Initializing neural seed: {query_text}..."
                    elif i % 3 == 1:
                        msg_vi = f"Mở rộng không gian truy vấn: {query_text}..."
                        msg_en = f"Expanding latent query space: {query_text}..."
                    elif i % 3 == 2:
                        msg_vi = f"Đang quét tín hiệu từ: {query_text}..."
                        msg_en = f"Scanning secondary signals for: {query_text}..."

                    await on_progress(msg_vi if "vi" in str(os.getenv("SKEMI_LANG", "vi")) else msg_en)
                
                res = await self.search_guaranteed_massive(
                    query_text,
                    recency_priority=recency_priority,
                    min_sources=pass_min_sources,
                    deep_research=pass_deep,
                )
                added = 0
                if isinstance(res, list):
                    for item in res:
                        if isinstance(item, dict):
                            tagged = dict(item)
                            tagged["_planned_query"] = query_text
                            all_search_results.append(tagged)
                            added += 1
                return added

            for i, q in enumerate(queries):
                if time.time() >= deadline_ts:
                    logger.info("[MULTI-SEARCH-BUDGET] Deadline reached before finishing query planning")
                    break
                if i > 0:
                    await asyncio.sleep(0.4)
                await _collect_query_results(
                    q,
                    pass_deep=effective_deep_research,
                    pass_min_sources=min_sources,
                )
                if len(self._quick_dedupe(all_search_results)) >= max_sources and len(queries) <= 1:
                    logger.info(f"[MULTI-SEARCH-EARLY-STOP] Found {len(self._quick_dedupe(all_search_results))} sources")
                    break

            if on_progress:
                await on_progress("Đang tối ưu hóa danh sách nguồn tin..." if "vi" in str(os.getenv("SKEMI_LANG", "vi")) else "Refining candidate source pool...")
            unique_search_results = await self._prepare_candidate_pool(
                all_search_results=all_search_results,
                queries=queries,
                recency_priority=recency_priority,
                deep_research=effective_deep_research,
                is_latest_query=is_latest_query,
                min_sources=min_sources,
                max_sources=max_sources,
            )

            query_coverage = self._query_coverage_counts(unique_search_results, queries)
            underfilled_queries = [
                query
                for query in queries
                if query_coverage.get(query, 0) < per_query_target
            ]

            if underfilled_queries:
                logger.info(
                    "[MULTI-SEARCH-COVERAGE] underfilled=%s coverage=%s target=%d",
                    underfilled_queries,
                    query_coverage,
                    per_query_target,
                )
                for coverage_query in underfilled_queries:
                    if time.time() >= deadline_ts:
                        logger.info("[MULTI-SEARCH-COVERAGE] Deadline reached during targeted recovery")
                        break
                    await _collect_query_results(
                        coverage_query,
                        pass_deep=True,
                        pass_min_sources=max(min_sources, per_query_target * 3),
                    )
                    await asyncio.sleep(0.25)
                unique_search_results = await self._prepare_candidate_pool(
                    all_search_results=all_search_results,
                    queries=queries,
                    recency_priority=recency_priority,
                    deep_research=True if underfilled_queries else effective_deep_research,
                    is_latest_query=is_latest_query,
                    min_sources=min_sources,
                    max_sources=max_sources,
                )
                query_coverage = self._query_coverage_counts(unique_search_results, queries)
                underfilled_queries = [
                    query
                    for query in queries
                    if query_coverage.get(query, 0) < per_query_target
                ]

            if len(unique_search_results) < required_sources:
                recovery_queries = self._build_search_expansion_queries(
                    queries,
                    query_class=normalized_query_class,
                    recency_priority=recency_priority,
                    deep_research=effective_deep_research,
                )
                if recovery_queries:
                    logger.info(
                        "[MULTI-SEARCH-RECOVERY] sources=%d/%d, running %d follow-up queries: %s",
                        len(unique_search_results),
                        required_sources,
                        len(recovery_queries),
                        recovery_queries,
                    )
                for followup_query in recovery_queries:
                    if time.time() >= deadline_ts:
                        logger.info("[MULTI-SEARCH-RECOVERY] Deadline reached during follow-up queries")
                        break
                    extra_results = await self.search_guaranteed_massive(
                        followup_query,
                        recency_priority=recency_priority,
                        min_sources=required_sources,
                        deep_research=effective_deep_research,
                    )
                    if isinstance(extra_results, list) and extra_results:
                        for item in extra_results:
                            if isinstance(item, dict):
                                tagged = dict(item)
                                tagged["_planned_query"] = followup_query
                                all_search_results.append(tagged)
                if recovery_queries:
                    unique_search_results = await self._prepare_candidate_pool(
                        all_search_results=all_search_results,
                        queries=queries + recovery_queries,
                        recency_priority=recency_priority,
                        deep_research=effective_deep_research,
                        is_latest_query=is_latest_query,
                        min_sources=min_sources,
                        max_sources=max_sources,
                    )
                    query_coverage = self._query_coverage_counts(unique_search_results, queries)
                    underfilled_queries = [
                        query
                        for query in queries
                        if query_coverage.get(query, 0) < per_query_target
                    ]

            if underfilled_queries:
                targeted_expansions: List[str] = []
                for coverage_query in underfilled_queries:
                    for candidate in self._build_search_expansion_queries(
                        [coverage_query],
                        query_class=normalized_query_class,
                        recency_priority=recency_priority,
                        deep_research=True,
                    ):
                        if candidate not in targeted_expansions:
                            targeted_expansions.append(candidate)
                if targeted_expansions:
                    logger.info(
                        "[MULTI-SEARCH-COVERAGE-EXPANSION] underfilled=%s expansions=%s",
                        underfilled_queries,
                        targeted_expansions,
                    )
                for followup_query in targeted_expansions:
                    if time.time() >= deadline_ts:
                        logger.info("[MULTI-SEARCH-COVERAGE-EXPANSION] Deadline reached during targeted expansions")
                        break
                    await _collect_query_results(
                        followup_query,
                        pass_deep=True,
                        pass_min_sources=max(min_sources, per_query_target * 3),
                    )
                if targeted_expansions:
                    unique_search_results = await self._prepare_candidate_pool(
                        all_search_results=all_search_results,
                        queries=queries + targeted_expansions,
                        recency_priority=recency_priority,
                        deep_research=True,
                        is_latest_query=is_latest_query,
                        min_sources=min_sources,
                        max_sources=max_sources,
                    )
                    query_coverage = self._query_coverage_counts(unique_search_results, queries)

            if not unique_search_results:
                result_text = "**UNVERIFIED_LATEST_MODEL** No trusted fresh sources were found." if is_latest_query else "**NO RELEVANT SOURCES FOUND**"
                res_dict = {
                    "context": result_text,
                    "urls": [],
                    "query_class": "latest_model" if is_latest_query else "general",
                    "latest_verified": False if is_latest_query else True,
                    "freshness_cutoff": None,
                    "latest_published_at": None,
                    "source_fingerprint": "",
                    "metrics": {
                        "source_count": 0,
                        "required_sources": required_sources,
                        "context_chars": len(result_text),
                        "target_context_chars": min_context_chars,
                    },
                }
                self._put_cached_search(cache_key, res_dict)
                return res_dict

            min_pages = 28 if effective_deep_research else 16
            max_pages = 48 if effective_deep_research else 24
            candidate_cap = min(len(unique_search_results), (42 if effective_deep_research else 36))
            urls = [r['url'] for r in unique_search_results[:candidate_cap]]
            if on_progress:
                await on_progress(f"Đang trích xuất dữ liệu sâu từ {len(urls)} trang..." if "vi" in str(os.getenv("SKEMI_LANG", "vi")) else f"Crawling deep intelligence from {len(urls)} pages...")
            crawled_data = await self.crawl_optimized_target_15(
                urls,
                min_pages=min_pages,
                max_pages=max_pages,
                deadline_ts=deadline_ts,
            )
            if not crawled_data and unique_search_results:
                fallback_candidate_cap = min(len(unique_search_results), 10 if len(queries) > 1 else 6)
                fallback_urls = [r['url'] for r in unique_search_results[:fallback_candidate_cap]]
                logger.info(
                    "[CRAWL-FALLBACK] No pages crawled before deadline, retrying top %d URLs without hard deadline",
                    len(fallback_urls),
                )
                crawled_data = await self.crawl_optimized_target_15(
                    fallback_urls,
                    min_pages=max(4, min_pages // 3),
                    max_pages=max(8, max_pages // 2),
                    deadline_ts=None,
                )

            for data in crawled_data:
                data['authority_score'] = self._calculate_domain_authority(data['url'])
                data['relevance_score'] = self._relevance_score(
                    f"{data.get('title','')} {data.get('content','')[:1200]}",
                    query_tokens,
                )

            relevance_floor = 0.12 if effective_deep_research else 0.2
            focused_crawled = [d for d in crawled_data if d.get('relevance_score', 0.0) >= relevance_floor]
            if focused_crawled:
                crawled_data = focused_crawled

            latest_cutoff = None
            latest_newest = None
            if is_latest_query:
                evidence_pool: List[Dict] = []
                for item in crawled_data:
                    evidence_pool.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", "")[:420],
                        "content": item.get("content", ""),
                        "authority_score": item.get("authority_score", 0.0),
                        "combined_score": item.get("relevance_score", 0.0) * 100.0,
                        "kind": "crawl",
                    })
                for item in unique_search_results[:max_sources]:
                    evidence_pool.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("snippet", ""),
                        "content": "",
                        "authority_score": item.get("authority_score", 0.0),
                        "combined_score": item.get("combined_score", 0.0),
                        "kind": "search",
                    })
                trusted_items, rejected_items, latest_newest, latest_cutoff = self._filter_latest_model_evidence(evidence_pool, latest_topic)
                missing_subjects = sorted({
                    reason.split("missing_subject:", 1)[1]
                    for _, _, reason in rejected_items
                    if isinstance(reason, str) and reason.startswith("missing_subject:")
                })
                verified_subjects = sorted({
                    str(item.get("matched_subject", "")).strip().lower()
                    for item in trusted_items
                    if str(item.get("matched_subject", "")).strip()
                })
                if rejected_items:
                    logger.info("[LATEST-MODEL] Rejected sources: %s", rejected_items[:20])
                if not trusted_items and unique_search_results:
                    policy = self._latest_model_domain_policy(latest_topic)
                    requested_subjects = self._extract_latest_subjects(latest_topic)
                    snippet_verified: List[Dict] = []
                    seen_fallback_urls: Set[str] = set()
                    for item in unique_search_results[:max_sources]:
                        url = self._canonicalize_url(str(item.get("url", "")))
                        if not url or url in seen_fallback_urls:
                            continue
                        domain = urllib.parse.urlparse(url).netloc.lower().replace("www.", "")
                        trust_tier = self._source_trust_tier(domain, policy)
                        if not trust_tier:
                            continue
                        evidence_text = " ".join(
                            [
                                str(item.get("title", "")),
                                str(item.get("snippet", "")),
                                url,
                            ]
                        )
                        published_at = self._extract_published_at(
                            item.get("published_at", ""),
                            item.get("title", ""),
                            item.get("snippet", ""),
                            url,
                        )
                        if trust_tier == "major_press" and not self._is_latest_candidate_text(evidence_text):
                            continue
                        snippet_verified.append(
                            {
                                "title": item.get("title", ""),
                                "url": url,
                                "snippet": item.get("snippet", ""),
                                "content": "",
                                "published_at": published_at,
                                "is_official_source": trust_tier in {"official", "official_family"},
                                "source_trust_tier": trust_tier,
                                "matched_subject": requested_subjects[0] if requested_subjects else "",
                                "relevance_score": float(item.get("relevance_score", 0.0) or 0.0),
                                "authority_score": float(item.get("authority_score", 0.0) or 0.0),
                                "source_rejection_reason": "",
                            }
                        )
                        seen_fallback_urls.add(url)
                    if snippet_verified:
                        logger.info(
                            "[LATEST-MODEL] Using %d trusted search-result candidates as final fallback",
                            len(snippet_verified),
                        )
                        trusted_items = snippet_verified
                if not trusted_items:
                    result_text = "**UNVERIFIED_LATEST_MODEL** The latest model could not be verified from trusted fresh sources."
                    res_dict = {
                        "context": result_text,
                        "urls": [],
                        "query_class": "latest_model",
                        "latest_verified": False,
                        "freshness_cutoff": latest_cutoff,
                        "source_fingerprint": "",
                        "verified_subjects": verified_subjects,
                        "unverified_subjects": missing_subjects,
                        "metrics": {
                            "source_count": 0,
                            "required_sources": required_sources,
                            "context_chars": len(result_text),
                            "target_context_chars": min_context_chars,
                        },
                    }
                    self._put_cached_search(cache_key, res_dict)
                    return res_dict
                crawled_data = trusted_items

            matched_queries_by_url: Dict[str, List[str]] = {}
            primary_query_by_url: Dict[str, str] = {}
            for item in unique_search_results:
                canonical_url = self._canonicalize_url(str(item.get("url", "")))
                if not canonical_url:
                    continue
                matched_queries = [
                    str(query or "").strip()
                    for query in (item.get("matched_queries") or [])
                    if str(query or "").strip()
                ]
                if not matched_queries:
                    planned_query = str(item.get("_planned_query") or "").strip()
                    if planned_query:
                        matched_queries = [planned_query]
                if matched_queries:
                    matched_queries_by_url[canonical_url] = matched_queries
                    primary_query_by_url[canonical_url] = matched_queries[0]

            for data in crawled_data:
                canonical_url = self._canonicalize_url(str(data.get("url", "")))
                matched_queries = list(matched_queries_by_url.get(canonical_url, []))
                if not matched_queries and not is_latest_query:
                    evidence_text = " ".join(
                        [
                            str(data.get("title", "")),
                            str(data.get("snippet", "")),
                            str(data.get("content", ""))[:1200],
                            str(data.get("url", "")),
                        ]
                    )
                    matched_queries = self._matched_queries_for_text(evidence_text, queries)
                data["matched_queries"] = matched_queries
                if matched_queries:
                    data["primary_query"] = matched_queries[0]
                elif canonical_url in primary_query_by_url:
                    data["primary_query"] = primary_query_by_url[canonical_url]

            crawled_data.sort(
                key=lambda x: (
                    (1.0 if x.get('is_official_source') else 0.0) * 0.35
                    + (float(x.get('published_at', '1970-01-01')[:4]) if x.get('published_at') else 0.0) * 0.0001
                    + x.get('relevance_score', 0.0) * 0.4
                    + (x.get('authority_score', 50) / 100.0) * 0.25
                ),
                reverse=True,
            )
            agreement_summary = self._check_source_agreement(crawled_data)
            domain_diversity = len({urllib.parse.urlparse(d.get('url', '')).netloc.lower() for d in crawled_data if d.get('url')})
            if not domain_diversity:
                domain_diversity = len({urllib.parse.urlparse(r.get('url', '')).netloc.lower() for r in unique_search_results if r.get('url')})

            def _format_context_item(data: Dict, *, snippet_only: bool = False) -> str:
                domain = urllib.parse.urlparse(data['url']).netloc.replace('www.', '')
                auth_badge = "*" if data.get('authority_score', 0) >= 70 else ""
                if is_latest_query:
                    raw_detail = data.get('snippet', '') or data.get('content', '')
                    raw_detail = re.sub(r"\s+", " ", raw_detail or "").strip()
                    detail_text = raw_detail[:620]
                    published_meta = f"\nPublished: {data.get('published_at', 'unknown')}" if data.get('published_at') else ""
                    trust_meta = f"\nTrust: {data.get('source_trust_tier', '')}" if data.get('source_trust_tier') else ""
                    return (
                        f"### VERIFIED ITEM {auth_badge}\n"
                        f"Subject: {data.get('matched_subject', 'unknown')}\n"
                        f"Domain: {domain}\n"
                        f"Title: {data['title']}\n"
                        f"URL: {data['url']}{published_meta}{trust_meta}\n"
                        f"Evidence: {detail_text}"
                    )

                detail_text = data.get('content', '')[:2000] or data.get('snippet', '')
                published_meta = f"\nPublished: {data.get('published_at', 'unknown')}" if data.get('published_at') else ""
                trust_meta = f"\nTrust: {data.get('source_trust_tier', '')}" if data.get('source_trust_tier') else ""
                matched_meta = ", ".join(data.get("matched_queries") or [])
                query_meta = f"\nMatched queries: {matched_meta}" if matched_meta else ""
                snippet_meta = ""
                if snippet_only:
                    verification_level = self._evidence_confidence_level(data)
                    snippet_meta = f"\nSnippet-only evidence: yes\nVerification level: {verification_level}"
                    if verification_level == "low":
                        snippet_meta += "\nDo not treat specific version/date/spec claims from this item as verified unless corroborated elsewhere."
                return (
                    f"### {domain} {auth_badge}\n"
                    f"{data['title']}\n"
                    f"{data['url']}{published_meta}{trust_meta}{query_meta}{snippet_meta}\n"
                    f"{detail_text}"
                )

            multi_topic_mode = (not is_latest_query) and len(queries) > 1
            data_sections = []
            used_urls: Set[str] = set()

            if multi_topic_mode:
                verified_coverage = self._query_coverage_counts(crawled_data, queries)
                search_coverage = self._query_coverage_counts(unique_search_results, queries)
                coverage_lines = []
                for query in queries:
                    query_items = [
                        data for data in crawled_data[:max_pages]
                        if query in (data.get("matched_queries") or [])
                    ]
                    newest_date = next((item.get("published_at") for item in query_items if item.get("published_at")), "")
                    coverage_lines.append(
                        f"- {query}: verified={verified_coverage.get(query, 0)}, candidate_hits={search_coverage.get(query, 0)}, newest={newest_date or 'undated'}"
                    )
                if coverage_lines:
                    data_sections.append("### query_coverage\n" + "\n".join(coverage_lines))

                for query in queries:
                    query_blocks: List[str] = []
                    section_used_urls: Set[str] = set()
                    query_items = [
                        data for data in crawled_data[:max_pages]
                        if query in (data.get("matched_queries") or [])
                    ]
                    for data in query_items:
                        canonical_url = self._canonicalize_url(str(data.get("url", "")))
                        if canonical_url and canonical_url in section_used_urls:
                            continue
                        query_blocks.append(_format_context_item(data))
                        if canonical_url:
                            section_used_urls.add(canonical_url)
                            used_urls.add(canonical_url)

                    query_snippets = [
                        res for res in unique_search_results
                        if query in (res.get("matched_queries") or [])
                    ]
                    query_norm = self._normalize_for_match(query)
                    claim_buckets: Dict[str, List[Tuple[str, bool]]] = {}
                    for evidence_item in list(query_items) + list(query_snippets):
                        evidence_text = " ".join(
                            [
                                str(evidence_item.get("title", "")),
                                str(evidence_item.get("snippet", "")),
                                str(evidence_item.get("content", ""))[:2400],
                                str(evidence_item.get("url", "")),
                            ]
                        )
                        title_and_url = self._normalize_for_match(
                            " ".join(
                                [
                                    str(evidence_item.get("title", "")),
                                    str(evidence_item.get("url", "")),
                                ]
                            )
                        )
                        matched_for_item = {
                            str(mq or "").strip()
                            for mq in (evidence_item.get("matched_queries") or [])
                            if str(mq or "").strip()
                        }
                        is_query_specific = (
                            len(matched_for_item) <= 1
                            or bool(query_norm and query_norm in title_and_url)
                        )
                        confidence = self._evidence_confidence_level(evidence_item)
                        for claim in self._extract_version_claims(
                            evidence_text,
                            anchors=self._query_focus_tokens(query),
                        ):
                            claim_buckets.setdefault(claim, []).append((confidence, is_query_specific))
                    supported_claims: List[str] = []
                    unverified_claims: List[str] = []
                    for claim, evidence_points in claim_buckets.items():
                        specific_points = [point for point in evidence_points if point[1]]
                        if not specific_points:
                            continue
                        levels = [level for level, _ in specific_points]
                        high_count = levels.count("high")
                        if high_count >= 1:
                            supported_claims.append(claim)
                        else:
                            unverified_claims.append(claim)

                    query_anchor_tokens = self._query_focus_tokens(query)

                    def _claim_rank(value: str) -> Tuple[int, int, int, str]:
                        value_tokens = value.split()
                        anchor_hit = 0 if any(token in query_anchor_tokens for token in value_tokens) else 1
                        return (anchor_hit, len(value_tokens), len(value), value)

                    supported_claims = sorted(dict.fromkeys(supported_claims), key=_claim_rank)
                    unverified_claims = sorted(dict.fromkeys(unverified_claims), key=_claim_rank)

                    if supported_claims:
                        verification_status = "corroborated_version_claims"
                    elif unverified_claims:
                        verification_status = "reported_but_unverified_version_claims"
                    elif query_items or query_snippets:
                        verification_status = "supporting_evidence_without_a_corroborated_version_name"
                    else:
                        verification_status = "no_query_specific_evidence_retrieved"

                    verification_lines = [
                        f"- verification_status={verification_status}",
                        f"- verified_pages={len(query_items)}",
                        f"- snippet_candidates={len(query_snippets)}",
                        f"- supported_version_claims={', '.join(supported_claims[:4]) if supported_claims else 'none'}",
                        f"- unverified_version_claims={', '.join(unverified_claims[:4]) if unverified_claims else 'none'}",
                    ]
                    if not query_items and not supported_claims and query_snippets:
                        verification_lines.append("- guidance=do_not_state_a_specific_latest_version_as_fact_without_corroboration")
                        verification_lines.append("- guidance=report_only_what_the_current_sources_explicitly_say_for_this_query")
                    if not query_items and not query_snippets:
                        verification_lines.append("- guidance=no_fresh_query_specific_results_were_retrieved_in_this_pass")
                    query_blocks.insert(0, "### verification_summary\n" + "\n".join(verification_lines))

                    snippet_count = 0
                    for res in query_snippets:
                        canonical_url = self._canonicalize_url(str(res.get("url", "")))
                        if not canonical_url or canonical_url in section_used_urls:
                            continue
                        query_blocks.append(_format_context_item(res, snippet_only=True))
                        section_used_urls.add(canonical_url)
                        used_urls.add(canonical_url)
                        snippet_count += 1
                        if len(query_items) >= per_query_target and snippet_count >= 1:
                            break
                        if len(query_items) < per_query_target and snippet_count >= 2:
                            break

                    if query_blocks:
                        data_sections.append(f"## query: {query}\n" + "\n\n".join(query_blocks))

                for data in crawled_data[:max_pages]:
                    canonical_url = self._canonicalize_url(str(data.get("url", "")))
                    if canonical_url and canonical_url in used_urls:
                        continue
                    data_sections.append("## query: ungrouped\n" + _format_context_item(data))
                    if canonical_url:
                        used_urls.add(canonical_url)
            else:
                for data in crawled_data[:max_pages]:
                    data_sections.append(_format_context_item(data))
                    canonical_url = self._canonicalize_url(str(data.get("url", "")))
                    if canonical_url:
                        used_urls.add(canonical_url)

            final_data = "\n\n".join(data_sections)

            if not final_data and unique_search_results:
                snippet_sections = []
                for res in unique_search_results[:max_sources]:
                    canonical_url = self._canonicalize_url(str(res.get('url', '')))
                    if canonical_url and canonical_url in used_urls:
                        continue
                    snippet_sections.append(_format_context_item(res, snippet_only=True))
                    if canonical_url:
                        used_urls.add(canonical_url)
                final_data = "\n\n".join(snippet_sections)
            elif unique_search_results:
                snippet_sections = []
                shown_urls = {self._canonicalize_url(str(url)) for url in used_urls if url}
                remaining = [
                    res for res in unique_search_results
                    if self._canonicalize_url(str(res.get('url', ''))) not in shown_urls
                ]
                snippet_budget = max(0, max_sources - len(crawled_data))
                if len(final_data) < min_context_chars:
                    snippet_budget = max(snippet_budget, min(12 if effective_deep_research else 8, len(remaining)))
                for res in remaining[:snippet_budget]:
                    canonical_url = self._canonicalize_url(str(res.get('url', '')))
                    if canonical_url and canonical_url in used_urls:
                        continue
                    snippet_sections.append(_format_context_item(res, snippet_only=True))
                    if canonical_url:
                        used_urls.add(canonical_url)
                if snippet_sections:
                    final_data += "\n\n" + "\n\n".join(snippet_sections)

            if agreement_summary and not is_latest_query:
                final_data += f"\n\n### source_agreement\n{agreement_summary}"

            if len(final_data) < min_context_chars and unique_search_results:
                supplemental_sections = []
                already_present = {self._canonicalize_url(str(url)) for url in used_urls if url}
                for res in unique_search_results:
                    res_url = self._canonicalize_url(str(res.get('url', '')))
                    if not res_url or res_url in already_present:
                        continue
                    supplemental_sections.append(_format_context_item({**res, "url": res_url}, snippet_only=True))
                    already_present.add(res_url)
                    if len("\n\n".join(supplemental_sections)) + len(final_data) >= min_context_chars:
                        break
                if supplemental_sections:
                    final_data += "\n\n" + "\n\n".join(supplemental_sections)

            elapsed = time.time() - search_start
            total_sources = min(len(unique_search_results), max_sources)
            evidence_complete = total_sources >= required_sources or len(final_data) >= min_context_chars
            if not evidence_complete:
                if is_latest_query:
                    result_text = (
                        f"**UNVERIFIED_LATEST_MODEL** Only {total_sources} trusted sources and {len(final_data)} context chars "
                        f"were gathered (targets: >= {required_sources} sources or >= {min_context_chars} chars).\n\n{final_data}"
                    )
                else:
                    result_text = (
                        f"**INSUFFICIENT_EVIDENCE: {total_sources} verified sources, {len(final_data)} context chars "
                        f"(targets: >= {required_sources} sources or >= {min_context_chars} chars)**\n{final_data}"
                    )
            elif is_latest_query:
                result_text = (
                    "**LATEST_MODEL_VERIFIED_CONTEXT**\n"
                    f"Freshness cutoff: {latest_cutoff or 'unknown'}\n"
                    f"Newest verified by subject: {latest_newest or 'unknown'}\n"
                    f"Verified HTTP 200 sources kept: {total_sources} (target >= {required_sources})\n"
                    "Use the verified items below as primary evidence. If an exact release date is missing, say so, but you may still name the latest model explicitly shown in official docs or release notes.\n\n"
                    f"{final_data}"
                )
            else:
                result_text = (
                    f"**FOUND {total_sources} VERIFIED_HTTP_200 SOURCES (target={min_sources}-{max_sources}, "
                    f"crawled={len(crawled_data)}, in {elapsed:.2f}s, diversity={domain_diversity}):**\n"
                    f"{final_data}"
                )
            
            # Build unified URLs list
            final_urls = []
            seen_urls = set()
            # 1. Add crawled pages first (highest quality)
            for d in crawled_data:
                u = d.get('url')
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    final_urls.append({
                        "url": u,
                        "title": d.get("title", ""),
                        "snippet": (d.get("content", "")[:300] + "...") if d.get("content") else d.get("snippet", ""),
                        "published_at": d.get("published_at"),
                        "is_official_source": bool(d.get("is_official_source", False)),
                        "source_trust_tier": d.get("source_trust_tier"),
                        "source_rejection_reason": d.get("source_rejection_reason", ""),
                    })
            # 2. Add remaining search hits so source drawer stays rich enough.
            for r in unique_search_results:
                u = r.get('url')
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    final_urls.append({
                        "url": u,
                        "title": r.get("title", ""),
                        "snippet": r.get("snippet", ""),
                        "published_at": r.get("published_at"),
                        "is_official_source": bool(r.get("is_official_source", False)),
                        "source_trust_tier": r.get("source_trust_tier"),
                        "source_rejection_reason": r.get("source_rejection_reason", ""),
                    })

            source_fingerprint = hashlib.md5("||".join(sorted(u.get("url", "") for u in final_urls[:max_sources])).encode("utf-8")).hexdigest() if final_urls else ""
            res_dict = {
                "context": result_text,
                "urls": final_urls[:max_sources],
                "query_class": "latest_model" if is_latest_query else "general",
                "latest_verified": bool(final_urls) if is_latest_query else True,
                "freshness_cutoff": latest_cutoff,
                "latest_published_at": latest_newest,
                "source_fingerprint": source_fingerprint,
                "metrics": {
                    "source_count": min(len(final_urls), max_sources),
                    "required_sources": required_sources,
                    "context_chars": len(result_text),
                    "target_context_chars": min_context_chars,
                },
            }
            if len(queries) > 1 and query_coverage:
                res_dict["query_coverage"] = query_coverage
                res_dict["metrics"]["query_coverage"] = query_coverage
            if is_latest_query:
                res_dict["verified_subjects"] = verified_subjects
                res_dict["unverified_subjects"] = missing_subjects
            if is_latest_query:
                logger.info(
                    "[LATEST-MODEL] Final trusted source set: newest=%s cutoff=%s urls=%s",
                    latest_newest,
                    latest_cutoff,
                    [u.get("url", "") for u in final_urls[:10]],
                )
            self._put_cached_search(cache_key, res_dict)
            return res_dict
        except Exception as e:
            return {"context": f"**SEARCH SYSTEM ERROR: {str(e)}**", "urls": []}

    def _check_source_agreement(self, crawled_data: List[Dict]) -> str:
        """Generate a short cross-source consistency note for downstream LLM."""
        if not crawled_data:
            return ""
        if len(crawled_data) < 3:
            return "Cross-check level: low (fewer than 3 independent sources)."

        try:
            number_sets: List[Set[str]] = []
            year_sets: List[Set[str]] = []
            for data in crawled_data:
                content = str(data.get("content", ""))
                numbers = set(re.findall(r"\b\d+[,.]?\d*\b", content)[:30])
                years = set(re.findall(r"\b(20\d{2})\b", content))
                if numbers:
                    number_sets.append(numbers)
                if years:
                    year_sets.append(years)

            common_numbers = set()
            common_years = set()
            if len(number_sets) >= 2:
                common_numbers = set.intersection(*number_sets)
            if len(year_sets) >= 2:
                common_years = set.intersection(*year_sets)

            if common_years:
                years_preview = ", ".join(sorted(common_years)[:3])
                return f"Cross-check: sources align on key year(s): {years_preview}."
            if common_numbers:
                nums_preview = ", ".join(sorted(common_numbers)[:5])
                return f"Cross-check: overlapping numeric facts found: {nums_preview}."
            return "Cross-check: sources vary; answer should mention uncertainty where needed."
        except Exception:
            return ""

    def get_engine_info(self) -> Dict[str, Any]:
        return {
            "engine": "SmartSearchEngine",
            "provider_order": [
                provider
                for provider, enabled in (
                    ("searxng", self._enable_searxng_engine),
                    ("duckduckgo_html", True),
                    ("brave_html", self._enable_brave_engine),
                    ("startpage_html", self._enable_startpage_engine),
                    ("qwant_html", self._enable_qwant_engine),
                    ("mojeek_html", self._enable_mojeek_engine),
                )
                if enabled
            ],
            "providers": {
                "searxng": {
                    "enabled": self._enable_searxng_engine,
                    "base_url": self._searxng_base_url,
                },
                "duckduckgo_html": {"enabled": True},
                "brave_html": {"enabled": self._enable_brave_engine},
                "startpage_html": {"enabled": self._enable_startpage_engine},
                "qwant_html": {"enabled": self._enable_qwant_engine},
                "mojeek_html": {"enabled": self._enable_mojeek_engine},
            },
            "limits": {
                "std_max_seconds": self._std_max_seconds,
                "deep_max_seconds": self._deep_max_seconds,
                "std_min_sources": self._std_min_sources,
                "std_max_sources": self._std_max_sources,
                "deep_min_sources": self._deep_min_sources,
                "deep_max_sources": self._deep_max_sources,
                "latest_min_sources": self._latest_min_sources,
                "std_min_context_chars": self._std_min_context_chars,
                "deep_min_context_chars": self._deep_min_context_chars,
                "latest_min_context_chars": self._latest_min_context_chars,
            },
            "features": {
                "semantic_rerank": self._enable_semantic_rerank,
                "http200_filter": True,
                "source_reputation_db": self._source_db_path,
                "latest_model_policy": True,
            },
        }

async def test():
    engine = SmartSearchEngine()
    try:
        print("Testing SMART SEARCH V8...")
        result = await engine.smart_search("Manchester United latest match result")
        print(f"Result Preview: {result[:500]}...")
        if "CRAWLED DATA" in result:
            match = re.search(r'\((\d+)\s+PAGES\)', result)
            if match: print(f"✓ Crawled pages: {match.group(1)}")
    finally:
        await engine.close()

if __name__ == "__main__":
    asyncio.run(test())


