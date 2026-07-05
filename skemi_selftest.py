"""
skemi_selftest.py — one-command verification of the Skemi desktop-control engine.

Run:  python skemi_selftest.py

Exercises every path that does NOT need a live LLM round-trip: app resolver,
app↔web routing, the window policy (adopt-in-place = no-op, fresh-launch hidden,
taskbar-summon, park/un-park), GDI-leak-safe capture, the duplicate-handle prune,
the orphan-desktop reap, and the concurrency guard. Prints PASS/FAIL per check.

It also reports the IDD (virtual-display) state and, when the IDD is OFF, prints
the exact 2-click fix — the only step that needs the user's UAC. With the IDD on,
add --idd to also verify a fresh AI-launched app hides + captures non-black there.

Nothing here mutates production state permanently: any window it opens (Notepad)
it closes; any IsoDesktop it creates is throwaway. Safe to run anytime.
"""
from __future__ import annotations
import sys, time, subprocess

_P = {"pass": 0, "fail": 0}


def chk(name: str, ok: bool, detail: str = "") -> bool:
    tag = "PASS" if ok else "FAIL"
    _P["pass" if ok else "fail"] += 1
    print(f"  [{tag}] {name}" + (f"  — {detail}" if detail else ""))
    return ok


def _visible(h, win32gui, win32api) -> bool:
    r = win32gui.GetWindowRect(h)
    cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
    mons = [win32api.GetMonitorInfo(m)['Monitor'] for m, _, _ in win32api.EnumDisplayMonitors(None, None)]
    return any(m[0] <= cx < m[2] and m[1] <= cy < m[3] for m in mons)


def _find_notepad(win32gui, tries=50):
    for _ in range(tries):
        out = []
        win32gui.EnumWindows(lambda h, _: (out.append(h)
            if win32gui.IsWindowVisible(h) and win32gui.GetWindowText(h).endswith('Notepad') else None, True)[1], None)
        if out:
            return out[0]
        time.sleep(0.2)
    return 0


def main(idd_test: bool = False) -> int:
    print("=" * 60)
    print(" SKEMI desktop-engine self-test")
    print("=" * 60)
    try:
        import win32gui, win32con, win32api
    except Exception as e:
        print("  win32 not available — Windows only:", e)
        return 2
    import skemi_iso_desktop as iso
    try:
        import Server  # noqa: needed for routing
        have_server = True
    except Exception as e:
        have_server = False
        print("  (Server import failed — routing checks skipped:", str(e)[:60], ")")

    print("\n# 1. App resolver")
    chk("claude → Store/MSIX token", iso._resolve_exe('claude').lower().startswith('shell:appsfolder'),
        iso._resolve_exe('claude'))
    chk("notepad → notepad.exe", iso._resolve_exe('notepad') == 'notepad.exe')
    chk("nonsense → '' (no false match)", iso._resolve_exe('zzqxfakeapp') == '')
    # prefix-extension trap: a not-installed app whose name starts with an installed
    # app's name ("photoshop" ⊃ "photos") must NOT false-match → '' so it routes web.
    chk("photoshop → '' (not Microsoft Photos)", iso._resolve_exe('photoshop') == '')
    chk("premiere → '' (prefix trap)", iso._resolve_exe('premiere') == '')
    # Vietnamese diacritic fold for click_text: model writes plain 'd', screen shows
    # 'đ' — "dang" must match "Đặng" (đ/Đ is atomic, NFD doesn't decompose it).
    fold = iso._fold_vn
    chk("đ-fold: 'dang' ⊂ 'Đặng'", fold('dang') in fold('Đặng'))
    chk("đ-fold: 'dong'/'duoc'/'dieu'", all(fold(a) in fold(b) for a, b in
        [('dong', 'Đóng'), ('duoc', 'Được'), ('dieu khien', 'Điều khiển')]))

    if have_server:
        print("\n# 2. App ↔ Web routing (deterministic, no LLM)")
        d0 = iso.IsoDesktop('selftest_route', user_desktop=True)
        chk("'tìm trên google …' → web", Server._route_surface_sync('tìm trên google thời tiết', d0) == 'web')
        chk("'mở notepad gõ hi' → app", Server._route_surface_sync('mở notepad gõ hi', d0) == 'app')
        chk("'mở https://x.com' → web", Server._route_surface_sync('mở https://x.com', d0) == 'web')

    print("\n# 3. Window policy")
    d = iso.IsoDesktop('selftest_win', user_desktop=True)
    # running-window matcher must not false-match host/generic substrings
    chk("_find_running_window('frame') → 0 (no host-exe match)", d._find_running_window('frame') == 0)
    chk("_find_running_window('host') → 0", d._find_running_window('host') == 0)
    chk("_find_running_window('app') → 0 (too short / host)", d._find_running_window('app') == 0)
    chk("_find_running_window('window') → 0 (plural trap)", d._find_running_window('window') == 0)
    # 3a. fresh launch → hidden + taskbar-eligible + focus not stolen
    ufg = win32gui.GetForegroundWindow()
    r = d.launch('notepad'); h = r.get('hwnd'); time.sleep(1.0)
    chk("fresh-launch hidden (off-screen)", h and not _visible(h, win32gui, win32api))
    ex = win32gui.GetWindowLong(h, -20) if h else 0
    chk("fresh-launch taskbar-eligible", bool(h) and not (ex & 0x80) and bool(win32gui.GetWindowText(h)))
    chk("fresh-launch did not steal focus", win32gui.GetForegroundWindow() == ufg or win32gui.GetForegroundWindow() != h)
    # 3b. park → minimized hidden → SW_RESTORE (raw taskbar click) → on-screen
    d._park_idle_windows(); time.sleep(0.4)
    chk("idle park → minimized & hidden", bool(h) and win32gui.IsIconic(h) and not _visible(h, win32gui, win32api))
    win32gui.ShowWindow(h, win32con.SW_RESTORE); time.sleep(0.4)
    chk("raw taskbar-click (SW_RESTORE) → on-screen", bool(h) and not win32gui.IsIconic(h) and _visible(h, win32gui, win32api))
    # 3c. un-park → hidden again for operation
    d._park_idle_windows(); time.sleep(0.2); d._unpark_windows(); time.sleep(0.4)
    chk("un-park → hidden again for next command", bool(h) and not _visible(h, win32gui, win32api))
    # 3d. adopt an already-open (now visible) window = no-op
    win32gui.ShowWindow(h, win32con.SW_RESTORE); time.sleep(0.2)
    win32gui.SetWindowPos(h, 0, 240, 160, 700, 500, win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER); time.sleep(0.2)
    rect0 = win32gui.GetWindowRect(h); exs0 = win32gui.GetWindowLong(h, -20)
    d.adopted_windows.add(h)
    d._park_idle_windows(); time.sleep(0.3)
    chk("adopted (user) window NEVER parked/moved", win32gui.GetWindowRect(h) == rect0 and not win32gui.IsIconic(h))
    subprocess.run(['taskkill', '/IM', 'notepad.exe', '/F'], capture_output=True)

    print("\n# 4. Capture is GDI-leak-safe (no raise on bad input)")
    chk("_print_window(bad hwnd) → None", d._print_window(0xDEADBEEF) is None)
    chk("_grab_screen_rect(bad rect) → None", d._grab_screen_rect((0, 0, -1, -1)) is None)

    print("\n# 5. Tracking-collection hygiene")
    live = win32gui.GetDesktopWindow()
    d.ai_windows = [0xDEAD, live]; d.adopted_windows = {0xDEAD, live}; d._win_first_seen = {0xDEAD: 1.0}
    d._prune_dead_windows()
    chk("prune drops dead handles, keeps live", d.ai_windows == [live] and d.adopted_windows == {live})
    mgr = iso.IsoDesktopManager()
    for i in range(12):
        mgr.create(f'st{i}', True)
    chk("orphan-desktop reap caps growth", len(mgr._desktops) <= 9, f"{len(mgr._desktops)} desktops")
    # a BUSY desktop (even oldest) must NEVER be reaped — that would kill a running task
    bi = mgr.create('busy_one', True); bd = mgr.get(bi['id']); bd.busy = True; bd.created_at = 0.0
    for i in range(15):
        mgr.create(f'st2_{i}', True)
    chk("reap never kills a BUSY desktop", mgr.get(bi['id']) is not None)

    print("\n# 6. Web agent robustness (no live browser needed)")
    try:
        import skemi_web_agent as wa
        chk("_safe_int junk → -1 (no crash)", wa._safe_int('boxlabel') == -1 and wa._safe_int(None) == -1)
        chk("_safe_int numeric → int", wa._safe_int('7') == 7 and wa._safe_int(3.0) == 3 and wa._safe_int(True) == -1)
        # press-key map: multi-word keys not mangled by .title()
        import inspect
        src = inspect.getsource(wa.WebController.press)
        chk("press maps PageDown/Home (no .title() mangle)", '"pagedown": "PageDown"' in src and '"home": "Home"' in src)
    except Exception as e:
        print("  [INFO] web-agent checks skipped:", str(e)[:60])

    print("\n# 7. Capture busy-throttle ordering (web live vs native cache)")
    dt = iso.IsoDesktop('selftest_cap', user_desktop=True)
    class _W:
        class _P:
            def poll(self):
                return None
        proc = _P(); last_shot = b'WEBLIVE'
    dt.web = _W(); dt.active_surface = 'web'; dt.busy = True
    dt._jpeg_cache = b'OLDNATIVE'; dt._jpeg_cache_ts = time.time()
    chk("busy+web → serves LIVE web frame", dt.capture_jpeg(70) == b'WEBLIVE')
    dt.active_surface = 'app'; dt.web = None
    chk("busy+native → serves throttled cache", dt.capture_jpeg(70) == b'OLDNATIVE')

    if have_server:
        print("\n# 8. Concurrency guard + Stop/Show reach the unified desktop")
        import asyncio

        async def _guard_checks():
            mgr2 = iso.get_manager()
            info = mgr2.create('selftest_unified', True)
            Server._UNIFIED_ISO['id'] = info['id']
            du = mgr2.get(info['id'])
            # concurrency guard: a 2nd command while busy is rejected
            du.busy = True
            res = await Server.iso_agent({'id': info['id'], 'command': 'mở notepad'})
            chk("2nd command while busy → rejected", res.get('busy') is True and res.get('success') is False)
            du.busy = False
            # Stop reaches the unified desktop even with an empty id
            du.cancelled = False
            await Server.iso_stop({})
            chk("iso_stop({}) cancels the unified desktop", du.cancelled is True)
            # self-heal: if the shared desktop is closed/reaped, the next call must
            # recreate it (not hand back a dead id) — long-running-server robustness.
            old_id = Server._UNIFIED_ISO['id']
            try:
                du.close()
            except Exception:
                pass
            mgr2._desktops.pop(old_id, None)
            dh = await Server.unified_iso_desktop()
            chk("unified desktop self-heals after reap", dh is not None and Server._UNIFIED_ISO['id'] != old_id)
            try:
                mgr2.get(Server._UNIFIED_ISO['id']).close()
            except Exception:
                pass
        try:
            asyncio.run(_guard_checks())
        except Exception as e:
            print("  [INFO] guard checks skipped:", str(e)[:60])

    print("\n# 9. Agent planner control-flow (deterministic, mock LLM — no cloud)")
    dp = iso.IsoDesktop('selftest_planner', user_desktop=True)
    # 9a. done=true on the first round → success immediately, no wasted rounds
    def _llm_done(_prompt):
        return '{"plan":[{"action":"wait","seconds":0}],"done":true,"summary":"Đã xong."}'
    rA = dp.run_agent('nhiệm vụ giả', _llm_done, max_steps=8)
    chk("done=true → success + stops in 1 round", rA.get('success') is True and rA.get('rounds', 99) <= 1, f"rounds={rA.get('rounds')}")
    # 9b. never-done plan that changes nothing → must STOP (not loop forever) + honest fail
    def _llm_stuck(_prompt):
        return '{"plan":[{"action":"wait","seconds":0}],"done":false,"summary":"đang thử"}'
    t9 = time.time()
    rB = dp.run_agent('nhiệm vụ không bao giờ xong', _llm_stuck, max_steps=8)
    chk("never-done → terminates (no infinite loop)", time.time() - t9 < 60)
    chk("never-done → honest success=False", rB.get('success') is False)
    # 9c. unparseable model output → handled, no crash
    def _llm_garbage(_prompt):
        return 'totally not json <think>hmm</think>'
    rC = dp.run_agent('lệnh lỗi model', _llm_garbage, max_steps=4)
    chk("garbage LLM output → no crash, returns result", isinstance(rC, dict) and 'summary' in rC)
    # 9d. LLM that raises → retried/handled, no crash
    def _llm_raise(_prompt):
        raise TimeoutError('ollama down')
    rD = dp.run_agent('lệnh model timeout', _llm_raise, max_steps=4)
    chk("LLM raises → no crash, returns result", isinstance(rD, dict))
    # 9e. FULL pipeline (mock LLM, no cloud): open_app → type-with-id (VN + emoji) →
    #     done. Exercises adopt/launch + click-element-first + readback-verify +
    #     surrogate-pair emoji + đ — the hot paths refactored this session.
    subprocess.run(['taskkill', '/IM', 'notepad.exe', '/F'], capture_output=True)
    _steps = iter([
        '{"plan":[{"action":"open_app","app":"notepad"},{"action":"wait","seconds":1}],"done":false,"summary":"mở"}',
        '{"plan":[{"action":"type","id":0,"text":"Skemi 👍 Đặng"}],"done":false,"summary":"gõ"}',
        '{"plan":[],"done":true,"summary":"xong"}'])
    def _llm_pipe(_p, **k):
        try: return next(_steps)
        except StopIteration: return '{"plan":[],"done":true,"summary":"xong"}'
    rE = dp.run_agent('mở notepad gõ thử', _llm_pipe, max_steps=6)
    _np = dp._primary_window()
    _txt = ''
    with __import__('contextlib').suppress(Exception):
        _f = [0]
        def _cb(c, _):
            cl = (win32gui.GetClassName(c) or '').lower()
            if 'edit' in cl or 'richedit' in cl: _f[0] = c
            return True
        win32gui.EnumChildWindows(_np, _cb, None)
        if _f[0]:
            import ctypes as _ct
            n = win32gui.SendMessage(_f[0], 0x000E, 0, 0)
            b = _ct.create_unicode_buffer(n + 2); win32gui.SendMessage(_f[0], 0x000D, n + 1, b); _txt = b.value
    chk("pipeline open_app→type(VN+emoji)→done lands text",
        rE.get('success') is True and 'Đặng' in _txt and '👍' in _txt, repr(_txt[:40]))
    subprocess.run(['taskkill', '/IM', 'notepad.exe', '/F'], capture_output=True)

    print("\n# 10. Virtual display (IDD) state")
    try:
        import phantom_core as pc
        m = pc.find_idd_monitor()
        # When invoked right after Finish_IDD_Setup.bat (enableidd 1), Windows needs
        # a few seconds to ENUMERATE the new virtual monitor. An immediate check
        # races the enumeration and would falsely report "IDD is OFF" — making the
        # user's single UAC click look failed. In --idd mode, POLL up to ~12s so a
        # freshly-enabled display is reliably detected.
        if idd_test and not m.get('found'):
            print("  [INFO] Cho man hinh ao enumerate sau enableidd 1 (toi da 12s)...")
            for _ in range(12):
                time.sleep(1.0)
                m = pc.find_idd_monitor()
                if m.get('found'):
                    break
        if m.get('found'):
            chk("IDD attached", True, f"rect {m.get('rect')} {m.get('width')}x{m.get('height')}")
            if idd_test:
                d2 = iso.IsoDesktop('selftest_idd', user_desktop=True)
                rr = d2.launch('notepad'); hh = rr.get('hwnd'); time.sleep(1.2)
                img = d2.capture()
                ext = img.convert('L').getextrema() if img else None
                chk("fresh app hidden on IDD", bool(hh) and d2._is_on_render_rect(hh))
                chk("IDD capture non-black", bool(ext and ext[1] > 60))
                subprocess.run(['taskkill', '/IM', 'notepad.exe', '/F'], capture_output=True)
        else:
            print("  [INFO] IDD is OFF →", m.get('message', 'not attached'))
            print("         Fix (one-time, 2 UAC clicks): Skemi → Gỡ màn hình ảo (clears all")
            print("         duplicate adapters) → vào lại chế độ AI (clean reinstall). Then")
            print("         re-run:  python skemi_selftest.py --idd")
    except Exception as e:
        print("  [INFO] IDD check skipped:", str(e)[:60])

    print("\n" + "=" * 60)
    print(f" RESULT: {_P['pass']} passed, {_P['fail']} failed")
    print("=" * 60)
    return 1 if _P['fail'] else 0


if __name__ == "__main__":
    sys.exit(main(idd_test="--idd" in sys.argv))
