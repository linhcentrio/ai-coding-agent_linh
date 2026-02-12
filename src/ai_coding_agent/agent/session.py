"""
Session Manager
================
Manage conversation sessions with persistence and token-aware compaction.
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..providers.base import Message


@dataclass
class SessionMetadata:
    """Session metadata."""
    id: str
    created_at: str
    updated_at: str
    provider: str
    model: str
    title: str = "Untitled Session"
    message_count: int = 0
    total_tokens: int = 0


@dataclass
class Session:
    """Conversation session."""
    metadata: SessionMetadata
    messages: List[Message] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return {
            "metadata": asdict(self.metadata),
            "messages": [
                {
                    "role": m.role,
                    "content": m.content,
                    "name": m.name,
                    "tool_calls": m.tool_calls,
                    "tool_call_id": m.tool_call_id,
                }
                for m in self.messages
            ],
            "context": self.context,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Session":
        """Create session from dictionary."""
        metadata = SessionMetadata(**data["metadata"])
        messages = [
            Message(
                role=m["role"],
                content=m["content"],
                name=m.get("name"),
                tool_calls=m.get("tool_calls"),
                tool_call_id=m.get("tool_call_id"),
            )
            for m in data.get("messages", [])
        ]
        return cls(
            metadata=metadata,
            messages=messages,
            context=data.get("context", {}),
        )


class SessionManager:
    """
    Manage conversation sessions.
    
    Features:
    - Session persistence to JSON files
    - Token-aware conversation compaction
    - Session listing and search
    """
    
    def __init__(
        self,
        storage_dir: Optional[Path] = None,
        max_tokens: int = 100000,
        compact_threshold: float = 0.8,  # Compact when 80% full
    ):
        self.storage_dir = storage_dir or Path.home() / ".ai_coding_agent" / "sessions"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_tokens = max_tokens
        self.compact_threshold = compact_threshold
        
        self._sessions: Dict[str, Session] = {}
    
    def _generate_id(self) -> str:
        """Generate unique session ID."""
        now = datetime.now().isoformat()
        hash_input = f"{now}-{id(self)}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:12]
    
    def _get_session_path(self, session_id: str) -> Path:
        """Get path for session file."""
        return self.storage_dir / f"{session_id}.json"
    
    def create(self, provider: str, model: str, title: str = "") -> Session:
        """Create a new session."""
        now = datetime.now().isoformat()
        session_id = self._generate_id()
        
        metadata = SessionMetadata(
            id=session_id,
            created_at=now,
            updated_at=now,
            provider=provider,
            model=model,
            title=title or f"Session {session_id[:6]}",
        )
        
        session = Session(metadata=metadata)
        self._sessions[session_id] = session
        
        return session
    
    def get(self, session_id: str) -> Optional[Session]:
        """Get session by ID, loading from disk if needed."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        
        session_path = self._get_session_path(session_id)
        if session_path.exists():
            return self.load(session_id)
        
        return None
    
    def save(self, session: Session) -> Path:
        """Save session to disk."""
        session.metadata.updated_at = datetime.now().isoformat()
        session.metadata.message_count = len(session.messages)
        
        session_path = self._get_session_path(session.metadata.id)
        
        with open(session_path, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)
        
        self._sessions[session.metadata.id] = session
        return session_path
    
    def load(self, session_id: str) -> Optional[Session]:
        """Load session from disk."""
        session_path = self._get_session_path(session_id)
        
        if not session_path.exists():
            return None
        
        with open(session_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        session = Session.from_dict(data)
        self._sessions[session_id] = session
        return session
    
    def delete(self, session_id: str) -> bool:
        """Delete a session."""
        session_path = self._get_session_path(session_id)
        
        if session_path.exists():
            session_path.unlink()
        
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        
        return False
    
    def list_sessions(self, limit: int = 50) -> List[SessionMetadata]:
        """List all sessions, most recent first."""
        sessions = []
        
        for path in self.storage_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    sessions.append(SessionMetadata(**data["metadata"]))
            except Exception:
                continue
        
        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        
        return sessions[:limit]
    
    def estimate_tokens(self, messages: List[Message]) -> int:
        """Estimate token count for messages (rough approximation)."""
        total = 0
        for msg in messages:
            # Rough estimate: 1 token per 4 characters
            total += len(msg.content) // 4
            if msg.tool_calls:
                total += len(str(msg.tool_calls)) // 4
        return total
    
    def compact_session(
        self,
        session: Session,
        keep_system: bool = True,
        keep_last_n: int = 10,
        summarize: bool = True,
    ) -> Session:
        """
        Compact session to reduce token usage.
        
        Strategies:
        1. Always keep system message
        2. Keep last N messages
        3. Optionally summarize removed messages
        
        Args:
            session: Session to compact
            keep_system: Keep system messages
            keep_last_n: Number of recent messages to keep
            summarize: Add summary of removed messages
        
        Returns:
            Compacted session
        """
        messages = session.messages
        
        if len(messages) <= keep_last_n:
            return session
        
        new_messages = []
        removed_messages = []
        
        for msg in messages:
            if msg.role == "system" and keep_system:
                new_messages.append(msg)
            elif len(messages) - len(removed_messages) - 1 < keep_last_n:
                new_messages.append(msg)
            else:
                removed_messages.append(msg)
        
        # Add summary if requested
        if summarize and removed_messages:
            summary_parts = []
            for msg in removed_messages:
                if msg.role == "user":
                    summary_parts.append(f"User asked: {msg.content[:100]}...")
                elif msg.role == "assistant":
                    summary_parts.append(f"Assistant: {msg.content[:100]}...")
            
            summary_msg = Message(
                role="system",
                content=f"[Previous conversation summary ({len(removed_messages)} messages)]\n" + 
                        "\n".join(summary_parts[:5])  # Limit summary length
            )
            
            # Insert summary after system message
            insert_idx = 1 if new_messages and new_messages[0].role == "system" else 0
            new_messages.insert(insert_idx, summary_msg)
        
        session.messages = new_messages
        session.context["compacted_at"] = datetime.now().isoformat()
        session.context["removed_messages"] = len(removed_messages)
        
        return session
    
    def should_compact(self, session: Session) -> bool:
        """Check if session should be compacted."""
        tokens = self.estimate_tokens(session.messages)
        return tokens >= self.max_tokens * self.compact_threshold
    
    def add_message(self, session: Session, message: Message, auto_compact: bool = True) -> Session:
        """Add message to session, auto-compacting if needed."""
        session.messages.append(message)
        
        if auto_compact and self.should_compact(session):
            session = self.compact_session(session)
        
        return session
