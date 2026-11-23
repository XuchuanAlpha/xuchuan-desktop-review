"""SQLite audit journal for outbound attempts and per-turn verification limits."""
import hashlib
import json
import re
from datetime import datetime, timezone

GENESIS = "0" * 64
TABLE = "desktop_audit_event"
OUTCOMES = {"cancelled", "replied", "timed_out", "failed"}
UNKNOWN = "已发起，结果未知，内容可能已发出"


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def needs_migration(connection):
    return not connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)
    ).fetchone()


def initialize(connection):
    connection.executescript("""
        BEGIN;
        CREATE TABLE IF NOT EXISTS desktop_audit_event (
            id INTEGER PRIMARY KEY, time TEXT NOT NULL, kind TEXT NOT NULL,
            turn_id TEXT NOT NULL, reference TEXT NOT NULL, metadata TEXT NOT NULL,
            previous TEXT NOT NULL, digest TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS desktop_audit_turn_kind ON desktop_audit_event(turn_id, kind);
        CREATE INDEX IF NOT EXISTS desktop_audit_reference ON desktop_audit_event(reference, kind);
        CREATE TABLE IF NOT EXISTS desktop_audit_head (
            singleton INTEGER PRIMARY KEY CHECK(singleton=1),
            record_count INTEGER NOT NULL, digest TEXT NOT NULL
        );
        INSERT OR IGNORE INTO desktop_audit_head VALUES (1, 0, '0000000000000000000000000000000000000000000000000000000000000000');
        COMMIT;
    """)


def digest(row):
    encoded = json.dumps(row, ensure_ascii=True, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def head(connection):
    return connection.execute(
        "SELECT record_count,digest FROM desktop_audit_head WHERE singleton=1"
    ).fetchone()


def append_locked(connection, kind, turn_id, reference, metadata):
    number, previous = head(connection)
    payload = json.dumps(metadata, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    row = (number + 1, timestamp(), kind, turn_id, reference, payload, previous)
    checksum = digest(row)
    connection.execute("INSERT INTO desktop_audit_event VALUES (?,?,?,?,?,?,?,?)", (*row, checksum))
    connection.execute("UPDATE desktop_audit_head SET record_count=?,digest=? WHERE singleton=1",
                       (number + 1, checksum))
    return row[0]


def start(connection, turn_id, request_id, endpoint, body, approvals=(), *, approved=False, cancelled=False):
    # This commit must finish before the transport can accept the request.
    connection.execute("PRAGMA synchronous=FULL")
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        approval = (append_locked(connection, "outbound_approval", turn_id, request_id, {})
                    if approved else None)
        append_locked(connection, "outbound_pending", turn_id, request_id, {
            "endpoint": endpoint, "sha256": hashlib.sha256(body).hexdigest(),
            "outbound_approval": approval, "file_approvals": list(approvals),
        })
        if cancelled:
            append_locked(connection, "outbound_result", turn_id, request_id, {"status": "cancelled"})


def finish(connection, turn_id, request_id, status):
    if status not in OUTCOMES:
        raise ValueError("Invalid transport result")
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        append_locked(connection, "outbound_result", turn_id, request_id, {"status": status})


def check_count(connection, turn_id):
    return connection.execute("""
        SELECT count(*) FROM desktop_audit_event WHERE turn_id=? AND kind='verification_admitted'
    """, (turn_id,)).fetchone()[0]


def reserve_check(connection, turn_id, cap):
    with connection:
        connection.execute("BEGIN IMMEDIATE")
        used = check_count(connection, turn_id)
        admitted = used < cap
        used += int(admitted)
        append_locked(connection, "verification_admitted" if admitted else "verification_refused",
                      turn_id, "", {"used": used, "limit": cap})
    return used, admitted


def verify_chain(connection, prefix_count=None):
    # One SQLite read snapshot for both the head and the ordered rows.
    with connection:
        connection.execute("BEGIN")
        count, stored_head = head(connection)
        previous, prefix, seen = GENESIS, GENESIS if prefix_count == 0 else None, 0
        for row in connection.execute("""
            SELECT id,time,kind,turn_id,reference,metadata,previous,digest
            FROM desktop_audit_event ORDER BY id
        """):
            seen += 1
            if row[0] != seen or row[-2] != previous or row[-1] != digest(row[:-1]):
                raise ValueError(f"Audit chain mismatch at record {seen}")
            previous = row[-1]
            if seen == prefix_count:
                prefix = previous
        if (seen, previous) != (count, stored_head):
            raise ValueError("Audit head does not match journal")
    return seen, previous, prefix


def export_checkpoint(connection, version):
    count, checksum, _ = verify_chain(connection)
    return f"{version}\t{count}\t{checksum}\t{timestamp()}\n"


def compare_checkpoint(connection, line):
    match = re.fullmatch(r"(\S{1,32})\t(0|[1-9][0-9]{0,17})\t([0-9a-f]{64})\t([^\t\r\n]{1,40})\r?\n?", line)
    if not match:
        raise ValueError("Invalid checkpoint format")
    _, count, expected, time = match.groups()
    if datetime.fromisoformat(time).tzinfo is None:
        raise ValueError("Checkpoint has no timezone")
    count = int(count)
    current, _, prefix = verify_chain(connection, count)
    if current < count:
        raise ValueError(f"Audit rollback: checkpoint has {count} records, local journal has {current}")
    if prefix != expected:
        raise ValueError(f"Audit checkpoint mismatch at record {count}")
    return count, current
