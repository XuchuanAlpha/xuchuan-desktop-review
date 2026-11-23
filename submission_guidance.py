"""Local, read-only hash registry and approved submission guidance snapshots."""
import hashlib
import json
import os
import re
import stat

import audit_trail
from dataclasses import dataclass
from datetime import datetime, timezone

PRIMARY = "xuchuan-submission-format.md"
WITNESS_FILE = "release-witnesses.tsv"
CAP = 8
MAX_SELECTED = 8
MAX_GUIDANCE_BYTES = 32768
MAX_TURN_GUIDANCE_BYTES = 65536
VERIFY = "verify_release_file"
TARGETS = {
    "source": "xuchuan_desktop.pyw",
    "release_notes": "xuchuan-release-notes.md",
    "manifest": "xuchuan_release_manifest.json",
    "guidance_runtime": "submission_guidance.py",
    "development_rules": "DEVELOPMENT_RULES.md",
    "format_card": "requirements-format-card.md",
    "requirements_example": "EXAMPLE_requirements_list.md",
    "appendix_example": "EXAMPLE_appendix.md",
    "bundled_guidance": PRIMARY,
}
ACTIVE = "active_skill_snapshot"
SHA256 = re.compile(r"[0-9a-fA-F]{64}")
GUIDANCE_NAME = re.compile(r"xuchuan-submission-[a-z0-9-]{1,48}\.md")
RULE_NAMES = {"requirements.max_utf8_bytes", "appendix.max_utf8_bytes"}
TOOL = {
    "type": "function",
    "function": {
        "name": VERIFY,
        "description": "Compute a SHA-256 for a registered local release object. No paths.",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "enum": [*TARGETS, ACTIVE]},
                "expected_sha256": {"type": "string", "pattern": "^[0-9A-Fa-f]{64}$"},
            },
            "required": ["target"],
            "additionalProperties": False,
        },
    },
}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(content):
    return hashlib.sha256(content).hexdigest()


def initialize(connection):
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS submission_guidance_decision (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, sha256 TEXT NOT NULL,
            content BLOB NOT NULL, decision TEXT NOT NULL, proposer TEXT NOT NULL,
            approver TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS submission_guidance_event (
            id INTEGER PRIMARY KEY, round_id TEXT NOT NULL, time TEXT NOT NULL,
            kind TEXT NOT NULL, detail TEXT NOT NULL
        );
    """)


def event(connection, round_id, kind, detail):
    with connection:
        connection.execute(
            "INSERT INTO submission_guidance_event(round_id,time,kind,detail) VALUES (?,?,?,?)",
            (round_id, now(), kind, detail),
        )


def read_regular(root, name, limit):
    path = root / name
    before = path.lstat()
    if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
            or getattr(before, "st_file_attributes", 0) & 0x400 or before.st_size > limit):
        raise ValueError("文件不是限额内的普通文件")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        def identity(info):
            return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink, info.st_size,
                    info.st_mtime_ns)
        if identity(before) != identity(opened):
            raise ValueError("打开时文件已变化")
        content = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
        if (len(content) != opened.st_size or identity(opened) != identity(after)
                or opened.st_ctime_ns != after.st_ctime_ns or identity(after) != identity(path.lstat())):
            raise ValueError("读取期间文件已变化")
    return content


def parse_guidance(raw):
    if len(raw) > MAX_GUIDANCE_BYTES:
        raise ValueError("指引超过大小上限")
    text = raw.decode("utf-8")
    lines = text.splitlines()
    try:
        declaration = json.loads(lines[0].removeprefix("<!-- guidance: ").removesuffix(" -->"))
    except (IndexError, ValueError) as error:
        raise ValueError("指引缺少有效声明") from error
    if (not lines[0].startswith("<!-- guidance: ") or not lines[0].endswith(" -->")
            or not isinstance(declaration, dict) or set(declaration) != {"tools", "rules"}
            or not isinstance(declaration["tools"], list) or not isinstance(declaration["rules"], dict)):
        raise ValueError("指引声明格式错误")
    if any(not isinstance(tool, str) or tool != VERIFY for tool in declaration["tools"]):
        raise ValueError("指引声明了登记表之外的工具")
    for name, value in declaration["rules"].items():
        if name not in RULE_NAMES or type(value) is not int or not 1 <= value <= 65536:
            raise ValueError("指引规则声明无效")
    text = text.partition("\n")[2]
    if not text.strip():
        raise ValueError("指引正文为空")
    return text, declaration["rules"]


def candidates(root, connection):
    files = sorted(path.name for path in root.iterdir() if GUIDANCE_NAME.fullmatch(path.name))
    return sorted(set(files) | set(active(connection)))


def active(connection):
    rows = connection.execute("""
        SELECT d.name,d.id,d.sha256,d.content FROM submission_guidance_decision d
        JOIN (SELECT name,max(id) id FROM submission_guidance_decision
              WHERE decision='approved' GROUP BY name) a ON d.id=a.id
        ORDER BY d.name
    """)
    return {name: (number, checksum, content) for name, number, checksum, content in rows}


def approved_snapshots(registry, names=None):
    selected = [name for name in sorted(registry) if names is None or name in names]
    return tuple(Snapshot(name, *registry[name]) for name in selected[:MAX_SELECTED])


def candidate(root, name):
    if not GUIDANCE_NAME.fullmatch(name):
        raise ValueError("指引文件名不在允许范围")
    return read_regular(root, name, MAX_GUIDANCE_BYTES)


def decide(connection, name, raw, approved, proposer, approver, summary):
    if not GUIDANCE_NAME.fullmatch(name) or len(raw) > MAX_GUIDANCE_BYTES:
        raise ValueError("指引不在允许范围")
    if not (1 <= len(proposer) <= 100 and 1 <= len(approver) <= 100 and 1 <= len(summary) <= 500):
        raise ValueError("提议者或变更摘要的长度无效")
    if approved:
        parse_guidance(raw)
    with connection:
        number = connection.execute("""
            INSERT INTO submission_guidance_decision
                (name,sha256,content,decision,proposer,approver,summary,created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (name, digest(raw), raw, "approved" if approved else "rejected",
              proposer, approver, summary, now())).lastrowid
    return number


@dataclass(frozen=True)
class Snapshot:
    name: str
    version: int
    sha256: str
    raw: bytes


def freeze(registry, enabled, names=None):
    if not enabled:
        return (), "未加载：开关关闭"
    snapshots, skipped, declarations = [], [], {}
    selected = sorted(set(names if names is not None else registry))
    if not selected:
        return (), "未加载：无已选择的已批准指引"
    if len(selected) > MAX_SELECTED:
        raise ValueError(f"每轮最多选择 {MAX_SELECTED} 份指引。")
    for name in selected:
        if name not in registry:
            skipped.append(f"{name}：无已批准版本")
            continue
        version, expected, raw = registry[name]
        if not isinstance(raw, bytes) or digest(raw) != expected:
            skipped.append(f"{name}：批准快照哈希不一致")
            continue
        try:
            _, rules = parse_guidance(raw)
        except ValueError as error:
            skipped.append(f"{name}：{error}")
            continue
        for rule, value in rules.items():
            if rule in declarations and declarations[rule][0] != value:
                raise ValueError(f"指引冲突：{declarations[rule][1]} / {name} · {rule}。请取消其中一份。")
            declarations[rule] = (value, name)
        snapshots.append(Snapshot(name, version, expected, raw))
    if sum(len(item.raw) for item in snapshots) > MAX_TURN_GUIDANCE_BYTES:
        raise ValueError("已选指引总量超限，请减少本轮选择。")
    status = "已加载" if snapshots else "未加载"
    if skipped:
        status += " · 已跳过 " + "；".join(skipped)
    return tuple(snapshots), status


def witness_values(root, version):
    try:
        text = read_regular(root, WITNESS_FILE, 131072).decode("utf-8-sig")
    except FileNotFoundError:
        return {}, "未提供"
    except (OSError, ValueError):
        return {}, "无法读取"
    values = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) != 7:
            return {}, "格式无效"
        release, name, checksum, witness, date, method, note = fields
        if release not in {version, "v" + version} or name not in TARGETS.values():
            continue
        if not SHA256.fullmatch(checksum) or not (witness and date and method):
            if note == "无法计算" and not checksum:
                continue
            return {}, "格式无效"
        if any(len(field) > 160 for field in (witness, date, method)):
            return {}, "字段超长"
        values.setdefault(name, {}).setdefault(witness, {})[checksum.lower()] = date
    return values, "已读取"


def integrity(root, version, snapshots, targets=None):
    content_hashes = {}
    manifest = {}
    for target, name in TARGETS.items():
        if targets is not None and target not in targets and target != "manifest":
            continue
        try:
            raw = read_regular(root, name, 2_000_000)
            content_hashes[target] = digest(raw)
            if target == "manifest":
                manifest = json.loads(raw)
                if not isinstance(manifest, dict):
                    manifest = {}
        except (OSError, ValueError):
            continue
    hashes = manifest.get("integrity_files")
    hashes = hashes if isinstance(hashes, dict) else {}
    witnesses, witness_status = witness_values(root, version) if targets is None else ({}, "未查询")
    rows = []
    for target, name in TARGETS.items():
        if targets is not None and target not in targets:
            continue
        result = content_hashes.get(target)
        expected = hashes.get(name) if manifest.get("version") == version else None
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            expected = None
        else:
            expected = expected.lower()
        sources = [
            {"source": name_record, "date": date, "sha256": check}
            for name_record, checks in sorted(witnesses.get(name, {}).items())
            for check, date in sorted(checks.items())
        ]
        checks = ([expected] if expected else []) + [row["sha256"] for row in sources]
        status = ("不一致" if result and any(result != check for check in checks)
                  else "一致" if result and checks else "无法比对")
        rows.append({"target": target, "file": name, "sha256": result, "expected": expected,
                     "witnesses": sources, "status": status})
    for item in snapshots:
        computed = digest(item.raw) if isinstance(item.raw, bytes) else None
        rows.append({"target": ACTIVE, "file": item.name, "sha256": computed,
                     "expected": item.sha256, "witnesses": [],
                     "status": "一致" if computed == item.sha256 else "不一致"})
    return rows, witness_status


def summary(report):
    rows, witness_status = report
    return {"时间": now(), "方法": "SHA-256 · hashlib · 完整性核对，不证明来源真实性",
            "见证文件": witness_status,
            "文件": [{"文件": row["file"], "状态": row["status"],
                    "哈希前八位": (row["sha256"] or "")[:8],
                    "见证": [{"署名": item["source"], "日期": item["date"],
                               "哈希前八位": item["sha256"][:8]} for item in row["witnesses"][:8]]}
                   for row in rows]}


def verify(connection, root, turn, arguments):
    used, admitted = audit_trail.reserve_check(connection, turn.round_id, CAP)
    result = {"used": used, "limit": CAP}
    try:
        if not admitted:
            raise ValueError("本轮完整性校验次数已达上限")
        if not isinstance(arguments, str) or len(arguments) > 512:
            raise ValueError("校验参数超长或格式错误")
        request = json.loads(arguments)
        if not isinstance(request, dict) or set(request) - {"target", "expected_sha256"}:
            raise ValueError("只允许登记目标和预期哈希")
        target = request.get("target")
        if not isinstance(target, str) or target not in (*TARGETS, ACTIVE):
            raise ValueError("目标未登记，未打开文件")
        result["target"] = target
        supplied = request.get("expected_sha256")
        if "expected_sha256" in request and (not isinstance(supplied, str) or not SHA256.fullmatch(supplied)):
            raise ValueError("预期哈希须为完整的 64 位十六进制，未打开文件")
        rows, _ = integrity(root, turn.version, turn.check_snapshots, {target})
        rows = [row for row in rows if row["target"] == target]
        result["files"] = []
        for row in rows:
            expected, computed = row["expected"], row["sha256"]
            source = ("获批快照" if target == ACTIVE else "发布清单") if expected else None
            expected_by_agent = supplied.lower() if supplied else None
            result["files"].append({
                "name": row["file"], "sha256": computed, "expected_sha256": expected,
                "expected_source": source, "match": computed == expected if computed and expected else None,
                "agent_expected_sha256": expected_by_agent,
                "agent_match": computed == expected_by_agent if computed and expected_by_agent else None,
            })
        if not rows:
            raise ValueError("无本轮获批指引快照")
    except json.JSONDecodeError:
        result["错误"] = "校验参数 JSON 无效，未打开文件"
    except ValueError as error:
        result["错误"] = str(error)
    if "files" in result and "错误" not in result:
        checks = ["一致" if row["match"] is True else "不一致" if row["match"] is False else "无法比对"
                  for row in result["files"]]
        result["result"] = "、".join(checks)
    log = f"{result.get('target', '未登记目标')} · {result.get('错误', result.get('result', '已计算'))} · {result['used']}/{CAP}"
    if result.get("files"):
        hashes = [f"{row['name']} {(row['sha256'] or '')[:8]} · "
                  f"{row['expected_source'] or '无预期值'} {(row['expected_sha256'] or '')[:8]}"
                  for row in result["files"]]
        log += " · " + "；".join(hashes)
    event(connection, turn.round_id, "校验工具", log)
    turn.records.append(f"程序记录 · 校验工具：{log}")
    return json.dumps(result, ensure_ascii=False)


@dataclass
class Turn:
    version: str
    round_id: str
    snapshots: tuple
    state: str
    records: list
    check_snapshots: tuple = ()
    last_report: object = None
