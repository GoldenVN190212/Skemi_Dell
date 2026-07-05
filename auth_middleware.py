"""
FastAPI Authentication Middleware
Production-level auth with guest mode support
"""

from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Optional, Callable
import os
import time

from auth_manager import get_auth_manager, is_guest_allowed, check_feature_access

# Auth ENFORCEMENT is opt-in. Skemi's primary use is a single local user who runs
# `python Server.py` and uses the app without logging in — so by default the
# middleware is PERMISSIVE (never blocks). Set SKEMI_REQUIRE_AUTH=1 for a shared/
# hosted deployment to actually enforce login + guest restrictions.
_AUTH_REQUIRED = os.getenv("SKEMI_REQUIRE_AUTH", "").strip().lower() in ("1", "true", "yes", "on")


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to handle authentication and authorization"""
    
    def __init__(self, app, exclude_paths: list = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/", "/health", "/api/health", "/login", "/register",
            "/static/", "/assets/", "/css/", "/js/", "/images/"
        ]
        self.auth_manager = get_auth_manager()
    
    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path

        # PERMISSIVE mode (default, local single-user): never block. Attach the
        # token's identity if present (so per-user features still work) but allow
        # everything. Enforcement is opt-in via SKEMI_REQUIRE_AUTH.
        if not _AUTH_REQUIRED:
            tok = self._extract_token(request)
            request.state.token = tok
            if tok:
                ok, payload = self.auth_manager.verify_token(tok)
                request.state.authenticated = bool(ok)
                request.state.user_id = (payload or {}).get("user_id") if ok else None
                request.state.user_role = (payload or {}).get("role", "user") if ok else "user"
            else:
                request.state.authenticated = False
                request.state.user_id = None
                request.state.user_role = "user"
            return await call_next(request)

        # Skip auth for excluded paths. Match a path prefix ONLY when the excluded
        # entry ends in "/" (a directory like "/css/"); otherwise require an EXACT
        # match or a proper path-segment boundary. The old `path.startswith("/")`
        # matched EVERY path against the "/" entry → auth was a silent no-op.
        for excluded in self.exclude_paths:
            if path == excluded:
                return await call_next(request)
            # Prefix-match ONLY real directory entries ("/css/"), NOT the root "/"
            # (len>1) — "/".startswith on every path was the no-op bug.
            if len(excluded) > 1 and excluded.endswith("/") and path.startswith(excluded):
                return await call_next(request)

        # Check if guest is allowed for this path
        guest_allowed = is_guest_allowed(path)
        
        # Get token from header or cookie
        token = self._extract_token(request)
        
        if token:
            # Verify token
            valid, payload = self.auth_manager.verify_token(token)
            if valid:
                # Set user info in request state
                request.state.user_id = payload.get("user_id")
                request.state.user_role = payload.get("role", "user")
                request.state.authenticated = True
                request.state.token = token
            else:
                # Invalid token - treat as guest or reject
                if not guest_allowed:
                    return self._auth_required_response(path)
                request.state.user_id = None
                request.state.user_role = "guest"
                request.state.authenticated = False
                request.state.token = None
        else:
            # No token - guest mode
            if not guest_allowed:
                return self._auth_required_response(path)
            request.state.user_id = None
            request.state.user_role = "guest"
            request.state.authenticated = False
            request.state.token = None
        
        # Check feature access for API endpoints
        if path.startswith("/api/") and request.state.user_role == "guest":
            feature = self._extract_feature(path)
            if feature and not check_feature_access("guest", feature):
                return self._feature_blocked_response(feature)
        
        # Log activity for authenticated users
        if request.state.authenticated:
            self._log_request(request)
        
        return await call_next(request)
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract JWT token from Authorization header or cookie"""
        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        
        # Check cookie
        token = request.cookies.get("skemi_token")
        if token:
            return token
        
        # Check query param (for WebSocket fallback)
        token = request.query_params.get("token")
        if token:
            return token
        
        return None
    
    def _auth_required_response(self, path: str):
        """Return response requiring authentication"""
        # For HTML pages, redirect to login
        if path.endswith('.html') or path == '/':
            response = RedirectResponse(url="/Login.html?redirect=" + path, status_code=302)
            return response
        
        # For API, return JSON error
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "success": False,
                "error": "Authentication required",
                "code": "AUTH_REQUIRED",
                "message": "Vui lòng đăng nhập để sử dụng tính năng này"
            }
        )
    
    def _feature_blocked_response(self, feature: str):
        """Return response for blocked feature"""
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "success": False,
                "error": "Feature not available",
                "code": "GUEST_RESTRICTED",
                "message": "Tính năng này yêu cầu đăng nhập. Vui lòng đăng ký tài khoản để sử dụng.",
                "feature": feature
            }
        )
    
    def _extract_feature(self, path: str) -> Optional[str]:
        """Extract feature name from API path"""
        if "/chat" in path:
            return "chat"
        if "/computer" in path or "/phantom" in path:
            return "computer"
        if "/search" in path:
            return "search"
        if "/studio" in path:
            return "studio"
        return None
    
    def _log_request(self, request: Request):
        """Log request for audit (non-blocking)"""
        try:
            user_id = getattr(request.state, 'user_id', None)
            if user_id:
                # Async logging - don't block request
                import asyncio
                asyncio.create_task(self._async_log(user_id, request.url.path))
        except:
            pass
    
    async def _async_log(self, user_id: str, endpoint: str):
        """Async activity logging"""
        try:
            self.auth_manager._log_activity(user_id, "api_request", endpoint, None, True, None)
        except:
            pass


def get_current_user(request: Request) -> dict:
    """Get current user info from request state"""
    return {
        "user_id": getattr(request.state, 'user_id', None),
        "role": getattr(request.state, 'user_role', 'guest'),
        "authenticated": getattr(request.state, 'authenticated', False),
        "token": getattr(request.state, 'token', None)
    }


def require_user(request: Request):
    """Dependency to require authenticated user"""
    if not getattr(request.state, 'authenticated', False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return get_current_user(request)


def require_feature(feature: str):
    """Dependency factory to require specific feature access"""
    def checker(request: Request):
        user = get_current_user(request)
        if not check_feature_access(user["role"], feature):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access to {feature} not allowed for {user['role']}"
            )
        return user
    return checker
