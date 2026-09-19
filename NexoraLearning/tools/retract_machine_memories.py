"""清理误入记忆的机器指令值（如 continue_learning）。

用法（在 NexoraLearning 目录）：
    python -X utf8 tools/retract_machine_memories.py --username ots20oug [--dry-run] [--data-dir data]

规则：evidence.sqlite3 里 status='active' 且 quote 匹配 ^[a-z][a-z0-9_-]*$（长度 ≤ 64）的记忆
标为 retracted，并写一条 source_type='system_cleanup' 的 feedback 留痕；不删除任何行。
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from pathlib import Path

_TOKEN = re.compile(r"^[a-z][a-z0-9_\-]{0,63}$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", required=True)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    path = Path(args.data_dir) / "users" / args.username / "memories" / "evidence.sqlite3"
    if not path.is_file():
        print(json.dumps({"ok": False, "reason": "no_memory_db", "path": str(path)}, ensure_ascii=False))
        return 0
    connection = sqlite3.connect(str(path), timeout=15)
    connection.row_factory = sqlite3.Row
    rows = connection.execute("SELECT id, kind, key, quote FROM memories WHERE status='active'").fetchall()
    targets = [row for row in rows if _TOKEN.match(str(row["quote"] or "").strip())]
    result = {"ok": True, "username": args.username, "active_before": len(rows),
              "retracted": [{"id": r["id"], "kind": r["kind"], "quote": r["quote"]} for r in targets],
              "dry_run": bool(args.dry_run)}
    if not args.dry_run and targets:
        now = int(time.time())
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            for row in targets:
                source_id = f"cleanup_{row['id']}"
                exists = connection.execute("SELECT 1 FROM sources WHERE source_id=?", (source_id,)).fetchone()
                if not exists:
                    connection.execute("INSERT INTO sources VALUES (?,?,?,?,?,?)",
                                       (source_id, "system", "system_cleanup", "机器指令值不是学生原话", now, now))
                    connection.execute("INSERT OR IGNORE INTO feedback VALUES (?,?,?,?)",
                                       (source_id, row["id"], "disagree", ""))
                connection.execute("UPDATE memories SET status='retracted' WHERE id=?", (row["id"],))
    connection.close()
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
