import asyncio
import base64
import contextlib
import os
import time
from typing import Dict, Any, Optional

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

class SkemiWebWorker:
    """
    Handles Playwright interactions over CDP for Chrome/Edge.
    Allows high-speed, 100% reliable clicks/types bypassing the OS-level UI tree bottlenecks.
    """
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_connected = False
        self._lock = asyncio.Lock()
        self.last_connected_port = 0

    async def _bind_best_page(self) -> bool:
        if not self.context:
            self.page = None
            return False
        try:
            pages = [page for page in self.context.pages if page and not page.is_closed()]
        except Exception:
            pages = []
        if not pages:
            try:
                self.page = await self.context.new_page()
            except Exception:
                self.page = None
                return False
            return self.page is not None

        def page_score(page: Page) -> tuple[int, int]:
            try:
                url = str(page.url or "")
            except Exception:
                url = ""
            score = 0
            if url and not url.startswith("devtools://"):
                score += 20
            if url.startswith("http://") or url.startswith("https://"):
                score += 50
            if "chrome-extension://" in url:
                score -= 50
            if "newtab" in url:
                score -= 10
            return score, len(url)

        pages.sort(key=page_score, reverse=True)
        self.page = pages[0]
        return self.page is not None

    async def connect(self, port: int = 9222, retries: int = 18, delay: float = 0.35) -> bool:
        """Connect to an existing Chromium instance via CDP."""
        if not HAS_PLAYWRIGHT:
            print("[WEB WORKER] Playwright is not installed.")
            return False

        async with self._lock:
            if self.is_connected and self.page and not self.page.is_closed():
                return True
                
            if not self.playwright:
                try:
                    self.playwright = await async_playwright().start()
                except Exception as e:
                    print(f"[WEB WORKER] Failed to boot Playwright: {e}")
                    return False

            endpoints = [
                f"http://127.0.0.1:{port}",
            ]
            last_error = None
            for _ in range(max(1, int(retries or 1))):
                for endpoint_url in endpoints:
                    try:
                        self.browser = await self.playwright.chromium.connect_over_cdp(endpoint_url, timeout=5000)
                        if self.browser.contexts:
                            self.context = self.browser.contexts[0]
                        else:
                            return False
                        if not await self._bind_best_page():
                            return False

                        self.last_connected_port = int(port or 0)
                        self.is_connected = True
                        print(f"[WEB WORKER] Successfully connected to Chromium via CDP on port {port}.")
                        return True
                    except Exception as e:
                        last_error = e
                        self.is_connected = False
                await asyncio.sleep(max(0.1, float(delay or 0.0)))
            
            current_time = time.time()
            if not hasattr(self, '_last_cdp_error_log') or current_time - getattr(self, '_last_cdp_error_log', 0) > 60:
                print(f"[WEB WORKER] CDP connection pending/failed on port {port}. Retrying silently in background...")
                self._last_cdp_error_log = current_time
            return False

    async def disconnect(self):
        """Disconnect CDP session (but keep browser running)."""
        async with self._lock:
            if self.browser:
                try:
                    await self.browser.close()
                except:
                    pass
            self.browser = None
            self.context = None
            self.page = None
            self.is_connected = False
            self.last_connected_port = 0

    async def ensure_page(self) -> bool:
        if not self.is_connected or not self.context:
            return False
        if self.page and not self.page.is_closed():
            return True
        return await self._bind_best_page()

    async def shutdown(self):
        """Completely teardown Playwright engine."""
        await self.disconnect()
        if self.playwright:
            try:
                await self.playwright.stop()
            except:
                pass
            self.playwright = None

    async def get_interactive_elements(self) -> list:
        """
        Extract interactive elements rapidly via JS DOM injection.
        Orders of magnitude faster than Windows UIA or AI Vision.
        """
        if not await self.ensure_page():
            return []
            
        script = """
            () => {
                const elements = document.querySelectorAll('button, a, input, select, textarea, [role="button"], [role="link"], [tabindex="0"]');
                const results = [];
                for (const el of elements) {
                    const rect = el.getBoundingClientRect();
                    // Ignore invisible / zero-size elements
                    if (rect.width > 0 && rect.height > 0) {
                        
                        // Heuristic class name/tag categorization
                        let class_name = el.tagName.toLowerCase();
                        if (el.getAttribute('role')) {
                            class_name += ` [${el.getAttribute('role')}]`;
                        }
                        
                        const text = el.innerText || el.value || el.placeholder || el.name || el.getAttribute('aria-label') || '';
                        
                        results.push({
                            text: text.substring(0, 100),
                            class_name: class_name,
                            x: Math.round(rect.x + rect.width / 2),
                            y: Math.round(rect.y + rect.height / 2),
                            left: Math.round(rect.x),
                            top: Math.round(rect.y),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            is_pwd: el.type === 'password'
                        });
                    }
                }
                return results;
            }
        """
        try:
            return await self.page.evaluate(script)
        except Exception as e:
            print(f"[WEB WORKER] DOM Extraction failed: {e}")
            return []

    async def navigate(self, url: str) -> bool:
        if not await self.ensure_page():
            return False
        try:
            await self.page.goto(url, wait_until="load", timeout=15000)
            return True
        except Exception as e:
            print(f"[WEB WORKER] Navigate error: {e}")
            return False

    async def ensure_youtube_playing(self, url: str = "") -> Dict[str, Any]:
        if not await self.ensure_page():
            return {"success": False, "error": "Playwright page is unavailable"}
        try:
            target_url = str(url or "").strip()
            if target_url:
                current_url = str(getattr(self.page, "url", "") or "")
                if current_url != target_url:
                    await self.page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
            with contextlib.suppress(Exception):
                await self.page.wait_for_load_state("networkidle", timeout=5000)
            await self.page.wait_for_timeout(900)
            playback = await self.page.evaluate(
                """async () => {
                    const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
                    const clickIfPresent = (selectors) => {
                        for (const selector of selectors) {
                            const node = document.querySelector(selector);
                            if (node) {
                                node.click();
                                return true;
                            }
                        }
                        return false;
                    };
                    clickIfPresent([
                        '.ytp-ad-skip-button',
                        '.ytp-skip-ad-button',
                        'button.ytp-ad-skip-button-modern'
                    ]);
                    const video = document.querySelector('video');
                    if (video) {
                        try {
                            video.muted = false;
                            video.volume = 1;
                        } catch (error) {}
                        try {
                            await video.play();
                        } catch (error) {}
                        await wait(250);
                        if (video.paused) {
                            clickIfPresent([
                                '.ytp-play-button',
                                'button[title^="Play"]',
                                'button[aria-label^="Play"]',
                                'button[aria-keyshortcuts="k"]'
                            ]);
                            await wait(250);
                        }
                        if (video.paused) {
                            return { playing: false, currentTime: Number(video.currentTime || 0) };
                        }
                        return { playing: true, currentTime: Number(video.currentTime || 0) };
                    }
                    return { playing: false, currentTime: 0 };
                }"""
            )
            if not bool((playback or {}).get("playing")):
                with contextlib.suppress(Exception):
                    await self.page.keyboard.press("k")
                await self.page.wait_for_timeout(250)
                playback = await self.page.evaluate(
                    """() => {
                        const video = document.querySelector('video');
                        return {
                            playing: !!(video && !video.paused),
                            currentTime: Number(video?.currentTime || 0)
                        };
                    }"""
                )
            return {
                "success": bool((playback or {}).get("playing")),
                "playing": bool((playback or {}).get("playing")),
                "current_time": float((playback or {}).get("currentTime") or 0.0),
                "url": str(getattr(self.page, "url", "") or ""),
            }
        except Exception as e:
            return {"success": False, "error": str(e), "url": str(getattr(self.page, "url", "") or "")}

    async def snapshot(self) -> Dict[str, Any]:
        if not await self.ensure_page():
            return {}
        try:
            viewport = await self.page.evaluate(
                """() => ({
                    width: Math.max(window.innerWidth || 0, document.documentElement?.clientWidth || 0, 1),
                    height: Math.max(window.innerHeight || 0, document.documentElement?.clientHeight || 0, 1),
                    dpr: window.devicePixelRatio || 1
                })"""
            )
            title = ""
            try:
                title = await self.page.title()
            except Exception:
                title = ""
            interactive_elements = []
            with contextlib.suppress(Exception):
                interactive_elements = await self.get_interactive_elements()
            return {
                "url": str(getattr(self.page, "url", "") or ""),
                "title": str(title or ""),
                "viewport_width": int((viewport or {}).get("width") or 1),
                "viewport_height": int((viewport or {}).get("height") or 1),
                "device_pixel_ratio": float((viewport or {}).get("dpr") or 1.0),
                "interactive_elements": list(interactive_elements or [])[:24],
            }
        except Exception as e:
            print(f"[WEB WORKER] Snapshot error: {e}")
            return {}

    async def capture_jpeg_base64(self, quality: int = 58) -> str:
        if not await self.ensure_page():
            return ""
        try:
            jpeg_bytes = await self.page.screenshot(
                type="jpeg",
                quality=max(20, min(int(quality or 58), 90)),
                animations="disabled",
                caret="hide",
                scale="css",
            )
            return base64.b64encode(jpeg_bytes).decode("utf-8")
        except Exception as e:
            print(f"[WEB WORKER] Screenshot error: {e}")
            return ""

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute automation action natively via Playwright Mouse/Keyboard APIs.
        Bypasses Windows entirely, guaranteeing delivery inside the Phantom context.
        """
        if not await self.ensure_page():
            return {"success": False, "error": "Playwright is not connected to any page."}
            
        try:
            if action == "click":
                x = params.get("x")
                y = params.get("y")
                if x is not None and y is not None:
                    await self.page.mouse.move(float(x), float(y))
                    await self.page.mouse.click(float(x), float(y), delay=50)
                    return {"success": True, "method": "playwright_cdp"}
                    
            elif action == "type":
                text = params.get("text", "")
                
                # If we have coordinates, click first to focus
                x = params.get("x")
                y = params.get("y")
                if x is not None and y is not None:
                    await self.page.mouse.click(float(x), float(y))
                    await self.page.wait_for_timeout(40)
                    
                # CDP Typing is robust and instant
                await self.page.keyboard.type(text, delay=10)
                
                # Optional auto-submit
                if params.get("submit", False):
                    await self.page.keyboard.press("Enter")
                    
                return {"success": True, "method": "playwright_cdp"}
                
            elif action in ("press", "key"):
                key = params.get("key", "Enter")
                # Normalize common keys
                key_map = {
                    "enter": "Enter", "backspace": "Backspace", "esc": "Escape", "tab": "Tab", 
                    "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight"
                }
                k = key_map.get(key.lower(), key)
                await self.page.keyboard.press(k)
                return {"success": True, "method": "playwright_cdp"}
                
            elif action == "scroll":
                direction = params.get("direction", "down")
                delta_y = 600 if direction == "down" else -600
                await self.page.mouse.wheel(0, delta_y)
                return {"success": True, "method": "playwright_cdp"}
                
        except Exception as e:
            print(f"[WEB WORKER] Action execution failed: {e}")
            return {"success": False, "error": str(e)}
            
        return {"success": False, "error": f"Action '{action}' not fully matched by parameters."}

# Global singleton instance
web_worker_instance = SkemiWebWorker()
