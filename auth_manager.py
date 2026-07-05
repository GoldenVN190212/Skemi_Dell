"""
Skemi Authentication & Authorization Manager
Production-level auth system with user isolation
"""

import os
import sqlite3
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from functools import wraps
import jwt

# Config
def _load_jwt_secret() -> str:
    """Stable JWT signing secret. Env var wins (production). Otherwise PERSIST a
    generated secret to a local file — without this, the default `secrets.token_hex`
    produced a NEW secret every process start, so every server restart invalidated
    all tokens and force-logged-out every user."""
    env = os.getenv("SKEMI_JWT_SECRET")
    if env:
        return env
    path = os.path.join(os.path.dirname(__file__), ".skemi_jwt_secret")
    try:
        if os.path.exists(path):
            s = open(path, "r", encoding="utf-8").read().strip()
            if s:
                return s
        s = secrets.token_hex(32)
        with open(path, "w", encoding="utf-8") as f:
            f.write(s)
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        return s
    except Exception:
        return secrets.token_hex(32)   # last resort: ephemeral (sessions won't persist)


JWT_SECRET = _load_jwt_secret()
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("SKEMI_JWT_EXPIRY_HOURS", "168"))  # 7 days
AUTH_DB_PATH = os.getenv("SKEMI_AUTH_DB", os.path.join(os.path.dirname(__file__), "skemi_auth.db"))
BCRYPT_ROUNDS = 12

# Guest restrictions
GUEST_ALLOWED_ENDPOINTS = {
    "/", "/index.html", "/Home.html", "/Search.html", "/Settings.html",
    "/health", "/api/health", "/api/models",
    "/api/auth/login", "/api/auth/register", "/api/auth/logout",
    "/api/phantom/check-driver", "/api/phantom/desktops"
}
GUEST_BLOCKED_ENDPOINTS = {
    "/Chat.html", "/chat", "/api/chat", "/api/agent", "/api/ask",
    "/Computer.html", "/api/local-computer", "/api/phantom"
}


@dataclass
class User:
    user_id: str
    username: str
    email: str
    role: str  # "admin", "user", "guest"
    created_at: float
    last_login: float
    is_active: bool
    metadata: Dict[str, Any]


class AuthManager:
    """Production-level authentication manager"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_db()
        return cls._instance
    
    def _init_db(self):
        """Initialize auth database with proper schema"""
        conn = sqlite3.connect(AUTH_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                created_at REAL DEFAULT (strftime('%s', 'now')),
                last_login REAL,
                is_active INTEGER DEFAULT 1,
                metadata TEXT DEFAULT '{}'
            )
        """)
        
        # Sessions table with user linkage
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token TEXT UNIQUE NOT NULL,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                expires_at REAL NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                is_valid INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # Activity log for security audit
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                action TEXT NOT NULL,
                endpoint TEXT,
                timestamp REAL DEFAULT (strftime('%s', 'now')),
                ip_address TEXT,
                success INTEGER,
                details TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_id, key),
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sessions_token ON user_sessions(token)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_user ON activity_log(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_activity_time ON activity_log(timestamp)")
        
        conn.commit()
        conn.close()
    
    def _hash_password(self, password: str) -> str:
        """Secure password hashing using PBKDF2"""
        salt = secrets.token_hex(16)
        pwdhash = hashlib.pbkdf2_hmac(
            'sha256', 
            password.encode('utf-8'), 
            salt.encode('utf-8'), 
            BCRYPT_ROUNDS * 10000
        ).hex()
        return f"{salt}${pwdhash}"
    
    def _verify_password(self, password: str, stored_hash: str) -> bool:
        """Verify password against stored hash"""
        try:
            salt, hash_value = stored_hash.split('$')
            pwdhash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                BCRYPT_ROUNDS * 10000
            ).hex()
            return secrets.compare_digest(pwdhash, hash_value)  # constant-time
        except Exception:
            return False
    
    def register_user(self, username: str, password: str, email: str = None, role: str = "user") -> Tuple[bool, str, Optional[str]]:
        """Register new user - returns (success, message, user_id)"""
        if not username or not password:
            return False, "Username and password required", None
        
        if len(password) < 8:
            return False, "Password must be at least 8 characters", None
        
        user_id = secrets.token_hex(16)
        password_hash = self._hash_password(password)
        
        conn = sqlite3.connect(AUTH_DB_PATH)
        cursor = conn.cursor()
        
        try:
            cursor.execute(
                "INSERT INTO users (user_id, username, email, password_hash, role) VALUES (?, ?, ?, ?, ?)",
                (user_id, username, email, password_hash, role)
            )
            conn.commit()
            self._log_activity(user_id, "register", None, None, True, f"Username: {username}")
            return True, "Registration successful", user_id
        except sqlite3.IntegrityError as e:
            if "username" in str(e).lower():
                return False, "Username already exists", None
            if "email" in str(e).lower():
                return False, "Email already registered", None
            return False, "Registration failed", None
        finally:
            conn.close()
    
    def authenticate_user(self, username: str, password: str, ip_address: str = None, user_agent: str = None) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """Authenticate and create session - returns (success, message, user_id, token)"""
        if not username or not password:
            return False, "Username and password required", None, None
        
        conn = sqlite3.connect(AUTH_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT user_id, password_hash, role, is_active FROM users WHERE username = ? OR email = ?",
            (username, username)
        )
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            self._log_activity(None, "login_failed", None, ip_address, False, f"Username: {username}, Reason: not found")
            return False, "Invalid credentials", None, None
        
        if not row["is_active"]:
            conn.close()
            self._log_activity(row["user_id"], "login_failed", None, ip_address, False, "Account disabled")
            return False, "Account is disabled", None, None
        
        if not self._verify_password(password, row["password_hash"]):
            conn.close()
            self._log_activity(row["user_id"], "login_failed", None, ip_address, False, "Wrong password")
            return False, "Invalid credentials", None, None
        
        # Update last login
        user_id = row["user_id"]
        cursor.execute(
            "UPDATE users SET last_login = strftime('%s', 'now') WHERE user_id = ?",
            (user_id,)
        )
        
        # Create JWT token
        token = self._create_jwt_token(user_id, row["role"])
        
        # Create session record
        session_id = secrets.token_hex(16)
        expires_at = time.time() + (JWT_EXPIRY_HOURS * 3600)
        
        cursor.execute(
            "INSERT INTO user_sessions (session_id, user_id, token, expires_at, ip_address, user_agent) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, user_id, token, expires_at, ip_address, user_agent)
        )
        
        conn.commit()
        conn.close()
        
        self._log_activity(user_id, "login", None, ip_address, True, f"Session: {session_id}")
        return True, "Login successful", user_id, token
    
    def _create_jwt_token(self, user_id: str, role: str) -> str:
        """Create JWT token"""
        payload = {
            "user_id": user_id,
            "role": role,
            "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
            "iat": datetime.utcnow(),
            "jti": secrets.token_hex(8)
        }
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    def verify_token(self, token: str) -> Tuple[bool, Optional[Dict]]:
        """Verify JWT token and return payload. Called on EVERY authenticated
        request, so it must never leak a DB connection or 500 on a transient SQLite
        error — those are caught and FAIL CLOSED (deny)."""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            return False, None
        except jwt.InvalidTokenError:
            return False, None
        except Exception:
            return False, None
        # Session-revocation check in DB — robust to a locked/busy SQLite (don't 500,
        # don't leak the connection): on any DB error, deny (fail closed).
        conn = None
        try:
            conn = sqlite3.connect(AUTH_DB_PATH, timeout=5)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT is_valid, expires_at FROM user_sessions WHERE token = ?",
                (token,)
            )
            row = cursor.fetchone()
            if not row:
                return False, None
            if not row[0] or row[1] < time.time():
                return False, None
            return True, payload
        except Exception:
            return False, None
        finally:
            if conn is not None:
                with __import__("contextlib").suppress(Exception):
                    conn.close()
    
    def logout(self, token: str) -> bool:
        """Invalidate session"""
        conn = sqlite3.connect(AUTH_DB_PATH)
        cursor = conn.cursor()
        
        # Get user_id before deleting
        cursor.execute("SELECT user_id FROM user_sessions WHERE token = ?", (token,))
        row = cursor.fetchone()
        
        if row:
            cursor.execute("DELETE FROM user_sessions WHERE token = ?", (token,))
            conn.commit()
            self._log_activity(row[0], "logout", None, None, True, "Session invalidated")
        
        conn.close()
        return True
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        conn = sqlite3.connect(AUTH_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT user_id, username, email, role, created_at, last_login, is_active, metadata FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return User(
            user_id=row["user_id"],
            username=row["username"],
            email=row["email"],
            role=row["role"],
            created_at=row["created_at"],
            last_login=row["last_login"],
            is_active=bool(row["is_active"]),
            metadata=eval(row["metadata"]) if row["metadata"] else {}
        )
    
    def _log_activity(self, user_id: Optional[str], action: str, endpoint: str = None, 
                     ip_address: str = None, success: bool = None, details: str = None):
        """Log activity for security audit"""
        try:
            conn = sqlite3.connect(AUTH_DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO activity_log (user_id, action, endpoint, ip_address, success, details) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, action, endpoint, ip_address, 1 if success else 0, details)
            )
            conn.commit()
            conn.close()
        except:
            pass  # Don't fail on logging errors
    
    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions"""
        conn = sqlite3.connect(AUTH_DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM user_sessions WHERE expires_at < ?", (time.time(),))
        deleted = cursor.rowcount
        conn.commit()
        conn.close()
        
        return deleted


# Global instance
_auth_manager = None

def get_auth_manager() -> AuthManager:
    """Get auth manager singleton"""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = AuthManager()
    return _auth_manager


def require_auth(allow_guest: bool = False):
    """Decorator to require authentication for endpoints"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # This will be called from FastAPI - need request object
            # For now, return a marker that middleware will handle
            return await func(*args, **kwargs)
        
        # Mark the function with auth requirements
        wrapper._require_auth = True
        wrapper._allow_guest = allow_guest
        return wrapper
    return decorator


def is_guest_allowed(path: str) -> bool:
    """Check if endpoint allows guest access.

    Path is NORMALIZED (drop query, trailing slash, lowercase) before matching —
    otherwise a guest could bypass the block list via casing the server still
    routes ("/chat.html" or "/API/phantom/..." on case-insensitive Windows would
    skip the exact/startswith checks and fall through to 'allowed')."""
    p = (path or "").split("?", 1)[0].split("#", 1)[0].rstrip("/").lower() or "/"
    allowed = {e.rstrip("/").lower() or "/" for e in GUEST_ALLOWED_ENDPOINTS}
    blocked = {e.rstrip("/").lower() for e in GUEST_BLOCKED_ENDPOINTS}

    # Exact allow wins (covers /api/phantom/check-driver even though /api/phantom is blocked)
    if p in allowed:
        return True
    # Blocked prefixes
    for b in blocked:
        if p == b or p.startswith(b + "/") or p.startswith(b):
            return False
    # Static files are allowed
    if p.endswith(('.html', '.css', '.js', '.png', '.jpg', '.ico', '.svg', '.woff', '.woff2')):
        return True
    # API endpoints generally require auth
    if p.startswith('/api/'):
        return False
    # Default: allow
    return True


def check_feature_access(user_role: str, feature: str) -> bool:
    """Check if user role has access to feature"""
    role_permissions = {
        "guest": ["view", "search_readonly"],
        "user": ["view", "search", "chat", "computer", "phantom", "studio"],
        "admin": ["view", "search", "chat", "computer", "phantom", "studio", "admin_panel", "user_management"]
    }
    
    allowed = role_permissions.get(user_role, [])
    return feature in allowed


# For testing
if __name__ == "__main__":
    auth = get_auth_manager()
    
    # Register test user
    success, msg, uid = auth.register_user("test", "password123", "test@test.com")
    print(f"Register: {success} - {msg}")
    
    if success:
        # Login
        success, msg, uid, token = auth.authenticate_user("test", "password123")
        print(f"Login: {success} - {msg}")
        print(f"Token: {token[:20]}...")
        
        # Verify token
        valid, payload = auth.verify_token(token)
        print(f"Token valid: {valid}")
        
        # Get user
        user = auth.get_user(uid)
        print(f"User: {user.username}, Role: {user.role}")
