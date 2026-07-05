# Phantom Mode Fixes - Summary

## Bug 1: Creating/Switching Desktop Switches User's Screen
**File:** `desktop_agent.py:1668-1692`
- Reduced delay after Win+Ctrl+D from 1.2s → 0.3s
- Added verification loop (up to 5 attempts) to ensure we return to original desktop
- Total worst-case flash: ~0.5s instead of ~2s

## Bug 2: Workflow Missing lock_token
**File:** `Js/Computer.js:724,769`
- Added `lock_token: window.desktopAgent.getPhantomLockToken()` to both "create" and "select" workflow calls
- Without this, `hasPhantomSessionLock()` returns false, causing phantom to be blocked

## Bug 3: postLocalComputerAction Not Syncing AgentController
**File:** `Js/Computer.js:635-663`
- After backend confirms phantom, now syncs:
  - `mode` to localStorage
  - `phantomLockToken` to sessionStorage (generates one if backend returns empty)
  - `selectedDesktopIndex` to both session and localStorage
  - UI labels and buttons via `syncConversationModeLabel()`
  - Status via `ingestLocalComputerStatus()` and `updateRuntimeMeta()`

## Bug 4: ensurePhantomPreview Reverts to Live When workspace_ready false
**File:** `Computer.html:2639-2674`
- Removed `clearPhantomLockLocal()` and `this.mode = 'live'` calls
- Now keeps `mode = 'phantom'` so user sees setup wizard instead of being dumped to live viewer

## Bug 5: refreshPhantomSetupOrPrompt Reverts to Live
**File:** `Computer.html:2600-2603`
- Removed `clearPhantomLockLocal()` and `this.mode = 'live'` calls
- Now keeps `mode = 'phantom'` when workspace isn't ready

## Bug 6: ingestLocalComputerStatus Blocks Phantom Without Lock
**File:** `Computer.html:4171-4187`
- Changed logic to not block phantom when user has active phantom lock (`hasPhantomSessionLock() || payload.phantom_lock_active`)
- Even when blocked from `setMode`, still updates `this.mode = 'phantom'` if backend says phantom and user has lock

## Bug 7: setMode Double-Starting Phantom Preview
**File:** `Computer.html:3699-3702, 3786-3789`
- Added `_phantomAlreadyStarted` flag set when workflow resolves with 'check'
- Prevents `ensurePhantomPreview()` from starting duplicate session

## Bug 8: persistPhantomLock Hardcoded Index to 0
**File:** `Computer.html:3745-3748`
- Now uses `data.target_desktop_index` from backend, falling back to `this.selectedDesktopIndex`

## Root Cause Summary
The phantom mode kept reverting to live viewer because:
1. Multiple code paths (`ensurePhantomPreview`, `refreshPhantomSetupOrPrompt`, `ingestLocalComputerStatus`) would clear the phantom lock and set mode to 'live' whenever `workspace_ready` was false
2. The workflow didn't pass `lock_token`, so `hasPhantomSessionLock()` was always false, causing `ingestLocalComputerStatus` to block phantom mode
3. `postLocalComputerAction` didn't sync the AgentController's state, so the UI labels stayed at "Live Viewer"
4. `setMode` was calling `ensurePhantomPreview()` even when the workflow already started the session, causing duplicate/confused state

## Testing Steps
1. Open Computer tab
2. Click "Phantom" button
3. Choose "Create Desktop" or "Select Desktop"
4. After selection, the UI should show "Phantom" mode (not "Live Viewer")
5. The phantom HUD should be visible with ghost icon
6. The mode note should say "Phantom: AI stream cửa sổ app..."
7. If Phantom isn't set up, you should see the setup wizard (not be kicked back to live)
8. Clicking "Phantom" again should not re-show the confirmation if already in phantom mode
