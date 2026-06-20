"""
SessionStart hook - injects knowledge base context into every conversation.

This is the "context injection" layer. When Claude Code starts a session,
this hook reads the knowledge base index and recent daily log, then injects
them as additional context so Claude always "remembers" what it has learned.

Configure in .claude/settings.json:
{
    "hooks": {
        "SessionStart": [{
            "matcher": "",
            "command": "uv run python hooks/session-start.py"
        }]
    }
}
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Paths relative to project root
ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = ROOT / "knowledge"
DAILY_DIR = ROOT / "daily"
INDEX_FILE = KNOWLEDGE_DIR / "index.md"

VAULT_CONCEPTS_DIR = Path("C:/Users/PC/OneDrive/Joost/Obsidian/wiki/concepts")

MAX_CONTEXT_CHARS = 20_000
MAX_LOG_LINES = 30
MAX_CONCEPTS_CHARS = 2_500


def get_recent_log() -> str:
    """Read the most recent daily log (today or yesterday)."""
    today = datetime.now(timezone.utc).astimezone()

    for offset in range(2):
        date = today - timedelta(days=offset)
        log_path = DAILY_DIR / f"{date.strftime('%Y-%m-%d')}.md"
        if log_path.exists():
            lines = log_path.read_text(encoding="utf-8").splitlines()
            # Return last N lines to keep context small
            recent = lines[-MAX_LOG_LINES:] if len(lines) > MAX_LOG_LINES else lines
            return "\n".join(recent)

    return "(no recent daily log)"


def get_vault_concepts() -> str:
    """Read concept files from vault and return a compact domain/category list."""
    if not VAULT_CONCEPTS_DIR.exists():
        return ""

    concepts = []
    for f in VAULT_CONCEPTS_DIR.glob("*.md"):
        if f.name == "index.md":
            continue
        try:
            content = f.read_text(encoding="utf-8")
            fm: dict[str, str] = {}
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        k, _, v = line.partition(":")
                        fm[k.strip()] = v.strip().strip('"')
            concepts.append({
                "domain":   fm.get("domain", "?"),
                "category": fm.get("category", "?"),
                "title":    fm.get("title", f.stem),
            })
        except Exception:
            pass

    if not concepts:
        return ""

    concepts.sort(key=lambda c: (c["domain"], c["category"]))

    lines = [f"{c['domain']:<10}  {c['category']:<18}  {c['title']}" for c in concepts]
    result = "## Bewezen Patronen (wiki/concepts/)\n\n" + "\n".join(lines)
    if len(result) > MAX_CONCEPTS_CHARS:
        result = result[:MAX_CONCEPTS_CHARS] + "\n...(meer via /wiki-query)"
    return result


def build_context() -> str:
    """Assemble the context to inject into the conversation."""
    parts = []

    # Today's date
    today = datetime.now(timezone.utc).astimezone()
    parts.append(f"## Today\n{today.strftime('%A, %B %d, %Y')}")

    # Knowledge base index (the core retrieval mechanism)
    if INDEX_FILE.exists():
        index_content = INDEX_FILE.read_text(encoding="utf-8")
        parts.append(f"## Knowledge Base Index\n\n{index_content}")
    else:
        parts.append("## Knowledge Base Index\n\n(empty - no articles compiled yet)")

    # Vault concepts (bewezen patronen per domein)
    concepts = get_vault_concepts()
    if concepts:
        parts.append(concepts)

    # Recent daily log
    recent_log = get_recent_log()
    parts.append(f"## Recent Daily Log\n\n{recent_log}")

    context = "\n\n---\n\n".join(parts)

    # Truncate if too long
    if len(context) > MAX_CONTEXT_CHARS:
        context = context[:MAX_CONTEXT_CHARS] + "\n\n...(truncated)"

    return context


def main():
    context = build_context()

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": context,
        }
    }

    print(json.dumps(output))


if __name__ == "__main__":
    main()
