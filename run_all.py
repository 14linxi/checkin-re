#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GitHub Actions 批量签到入口

当前只调度 WPS、Agent Router、Trae CN、WorkBuddy 四个脚本：
- 支持从平台独立 Secret（WPS_JSON 等）或 config/token.json 读取配置
- 未配置账号的平台自动跳过
- 子任务的推送会写入缓冲区，全部执行完后合并成一条消息统一发送
- 任一平台进程失败时退出码为 1，便于 GitHub Actions 标记失败

Usage:
    python run_all.py                       # 运行所有已配置平台
    python run_all.py --platforms wps,trae  # 只运行指定平台
    python run_all.py --list                # 查看平台列表
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "config" / "token.json"

PLATFORMS = [
    {
        "name": "wps",
        "title": "WPS",
        "script": "script/wps/main.py",
        "config_path": ("wps",),
    },
    {
        "name": "agentrouter",
        "title": "Agent Router",
        "script": "script/agentrouter/main.py",
        "config_path": ("agentrouter",),
    },
    {
        "name": "trae",
        "title": "Trae CN",
        "script": "script/trae/main.py",
        "config_path": ("trae",),
    },
    {
        "name": "workbuddy",
        "title": "WorkBuddy",
        "script": "script/workbuddy/main.py",
        "config_path": ("workbuddy",),
    },
]

# 平台独立 Secret 环境变量名
PLATFORM_ENV_KEYS = {
    "wps": "WPS_JSON",
    "agentrouter": "AGENTROUTER_JSON",
    "trae": "TRAE_JSON",
    "workbuddy": "WORKBUDDY_JSON",
}

def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f"⚠️ 环境变量 {name}={raw!r} 不是整数，使用默认值 {default}")
        return default


DEFAULT_TIMEOUT = _env_int("CHECKIN_TASK_TIMEOUT", 1800)
SUMMARY_MAX_CHARS = _env_int("CHECKIN_SUMMARY_MAX_CHARS", 4000)
NOTIFY_COMPACT = (os.environ.get("CHECKIN_NOTIFY_COMPACT") or "true").strip().lower() not in (
    "false",
    "0",
    "no",
)

# 统一汇总时去掉各平台重复的统计头和低价值行
SUMMARY_HEADER_PREFIXES = (
    "📊 总账号数",
    "✅ 签到成功",
    "✅ 执行成功",
    "📅 今日已签",
    "❌ 签到失败",
    "❌ 执行失败",
    "⚠️ 重复账号",
    "⚠️ 需更新凭证",
    "📋 详细结果",
)
NOISE_LINE_PATTERNS = (
    re.compile(r"^剩余(?:试用申请次数|抽奖次数)[:：]\s*0$"),
    re.compile(r"^第\d+次.*(?:次数已用完|已抽奖|已参与|请先完成)"),
)


def _compact_content(content: str) -> str:
    """压缩单个平台的推送内容，保留账号结果和关键奖励/错误"""
    kept = []
    for raw_line in (content or "").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(SUMMARY_HEADER_PREFIXES):
            continue
        if any(pattern.search(stripped) for pattern in NOISE_LINE_PATTERNS):
            continue

        # 账户信息只保留积分，去掉抽奖次数和即将过期等细节
        account_info = re.match(r"^账户信息[:：].*?积分[:：]?\s*(\d+)", stripped)
        if account_info:
            kept.append(f"    积分 {account_info.group(1)}")
            continue

        # 账号级状态前补空行，去掉其它空行
        if stripped.startswith(("✅ ", "❌ ", "⚠️ ")) and kept:
            kept.append("")
        kept.append(line)

    # 丢弃下面已经没有任何结果的“抽奖结果/试用申请结果”标题
    result = []
    for index, line in enumerate(kept):
        if line.strip() in ("抽奖结果:", "试用申请结果:"):
            next_line = kept[index + 1].strip() if index + 1 < len(kept) else ""
            if not next_line or next_line.startswith(("✅", "❌", "⚠️", "[")):
                continue
        result.append(line)

    return "\n".join(result).strip()
NOTIFY_BUFFER_PATH = Path(tempfile.gettempdir()) / f"checkin-notify-{os.getpid()}.jsonl"


def parse_args():
    parser = argparse.ArgumentParser(description="批量执行签到脚本")
    parser.add_argument(
        "--platforms",
        default="all",
        help="要运行的平台，逗号分隔；all 表示全部已配置平台",
    )
    parser.add_argument("--list", action="store_true", help="列出支持的平台")
    return parser.parse_args()


def _parse_json(raw: str, label: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} 不是合法 JSON: {exc}") from exc


def _unwrap_platform(name: str, payload):
    """兼容两种 Secret 写法：{"accounts": [...]} 或 {"wps": {"accounts": [...]}}"""
    if isinstance(payload, dict) and "accounts" not in payload:
        nested = payload.get(name)
        if isinstance(nested, dict):
            payload = nested
    if not isinstance(payload, dict):
        raise ValueError(f"{PLATFORM_ENV_KEYS[name]} 必须是 JSON 对象")
    return payload


def ensure_config() -> dict:
    """合并配置：本地文件 < TOKEN_JSON < 平台独立 Secret"""
    config = {}
    if CONFIG_PATH.exists():
        try:
            config.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise ValueError(f"配置文件 JSON 格式错误: {exc}") from exc

    env_payload_used = False

    raw_full = (os.environ.get("TOKEN_JSON") or os.environ.get("CHECKIN_TOKEN_JSON") or "").strip()
    if raw_full:
        payload = _parse_json(raw_full, "TOKEN_JSON")
        if not isinstance(payload, dict):
            raise ValueError("TOKEN_JSON 必须是 JSON 对象")
        config.update(payload)
        env_payload_used = True

    for name, env_name in PLATFORM_ENV_KEYS.items():
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            continue
        config[name] = _unwrap_platform(name, _parse_json(raw, env_name))
        env_payload_used = True

    if env_payload_used:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"已从环境变量生成配置文件: {CONFIG_PATH}")

    if not config:
        raise FileNotFoundError(
            f"未找到配置: {CONFIG_PATH} 不存在，且未设置平台 Secret"
        )

    return config


def get_config_node(config: dict, path: tuple):
    node = config
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def has_accounts(config: dict, platform: dict) -> bool:
    node = get_config_node(config, platform["config_path"])
    return isinstance(node, dict) and bool(node.get("accounts"))


def select_platforms(config: dict, requested: str):
    requested = (requested or "all").strip()
    if requested == "all":
        candidates = PLATFORMS
    else:
        wanted = {item.strip().lower() for item in requested.split(",") if item.strip()}
        known = {item["name"] for item in PLATFORMS}
        unknown = wanted - known
        if unknown:
            raise ValueError(f"未知平台: {', '.join(sorted(unknown))}")
        candidates = [item for item in PLATFORMS if item["name"] in wanted]

    selected, skipped = [], []
    for platform in candidates:
        if has_accounts(config, platform):
            selected.append(platform)
        else:
            skipped.append(platform)
    return selected, skipped


def reset_notify_buffer() -> None:
    try:
        NOTIFY_BUFFER_PATH.unlink()
    except FileNotFoundError:
        pass


def load_notification_records() -> list:
    if not NOTIFY_BUFFER_PATH.exists():
        return []

    records = []
    for line in NOTIFY_BUFFER_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def run_platform(platform: dict) -> dict:
    script_path = PROJECT_ROOT / platform["script"]
    started = time.time()
    print(f"\n{'=' * 60}")
    print(f"▶ 开始执行 {platform['title']} ({platform['name']})")
    print(f"  脚本: {platform['script']}")
    print(f"{'=' * 60}")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("TZ", "Asia/Shanghai")
    # 子任务不直接推送，改为写入缓冲区，由本脚本统一汇总
    env["CHECKIN_NOTIFY_DISABLED"] = "true"
    env["CHECKIN_NOTIFY_BUFFER_FILE"] = str(NOTIFY_BUFFER_PATH)
    env["CHECKIN_NOTIFY_PLATFORM"] = platform["name"]
    # GitHub Actions 中关闭启动随机延迟，避免无意义的等待
    env.setdefault("TRAE_JITTER_MAX", "0")
    env.setdefault("WORKBUDDY_JITTER_MAX", "0")

    if not script_path.exists():
        return {
            "platform": platform,
            "success": False,
            "returncode": None,
            "duration": 0.0,
            "output": f"脚本不存在: {script_path}",
        }

    try:
        result = subprocess.run(
            [sys.executable, "-u", str(script_path)],
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=DEFAULT_TIMEOUT,
        )
        output = (result.stdout or "") + (result.stderr or "")
        print(output, end="" if output.endswith("\n") else "\n")
        return {
            "platform": platform,
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "duration": time.time() - started,
            "output": output,
        }
    except subprocess.TimeoutExpired as exc:
        output = ""
        if exc.stdout:
            output += exc.stdout if isinstance(exc.stdout, str) else exc.stdout.decode("utf-8", "replace")
        if exc.stderr:
            output += exc.stderr if isinstance(exc.stderr, str) else exc.stderr.decode("utf-8", "replace")
        output += f"\n任务超时（>{DEFAULT_TIMEOUT} 秒）"
        print(output)
        return {
            "platform": platform,
            "success": False,
            "returncode": None,
            "duration": time.time() - started,
            "output": output,
        }
    except Exception as exc:  # noqa: BLE001 - 单平台异常不影响其他平台
        message = f"执行异常: {type(exc).__name__}: {exc}"
        print(message)
        return {
            "platform": platform,
            "success": False,
            "returncode": None,
            "duration": time.time() - started,
            "output": message,
        }


def build_summary(results: list, skipped: list, records: list) -> tuple:
    total = len(results)
    success_count = sum(1 for item in results if item["success"])

    if total and success_count == total:
        title = f"✅ 每日签到完成 ({success_count}/{total})"
    elif success_count:
        title = f"⚠️ 每日签到部分进程失败 ({success_count}/{total})"
    else:
        title = f"❌ 每日签到进程失败 (0/{total})"

    records_by_platform = {}
    for record in records:
        name = str(record.get("platform") or "").strip()
        records_by_platform.setdefault(name, []).append(record)

    lines = [f"🕐 完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"]
    if skipped:
        lines.append("⏭ 未配置跳过: " + "、".join(item["title"] for item in skipped))
    lines.append("")

    for item in results:
        platform = item["platform"]
        lines.append(f"━━━ {platform['title']}（{int(item['duration'])} 秒）━━━")

        if not item["success"]:
            code = item["returncode"] if item["returncode"] is not None else "超时/异常"
            lines.append(f"❌ 脚本进程异常退出（{code}），详情见 Actions 日志")

        seen = set()
        for record in records_by_platform.get(platform["name"], []):
            record_title = str(record.get("title") or "").strip()
            record_content = str(record.get("content") or "").strip()
            if NOTIFY_COMPACT:
                record_content = _compact_content(record_content)
            key = (record_title, record_content)
            if not record_title and not record_content:
                continue
            if key in seen:
                continue
            seen.add(key)
            if record_title and not NOTIFY_COMPACT:
                lines.append(f"【{record_title}】")
            if record_content:
                lines.append(record_content)

        if not seen and item["success"]:
            lines.append("（脚本未产生可汇总的签到内容）")
        lines.append("")

    content = "\n".join(lines).strip()
    if SUMMARY_MAX_CHARS > 0 and len(content) > SUMMARY_MAX_CHARS:
        content = (
            content[:SUMMARY_MAX_CHARS]
            + "\n…（内容过长已截断，完整日志见 GitHub Actions）"
        )

    return title, content


def main() -> int:
    args = parse_args()

    if args.list:
        for platform in PLATFORMS:
            print(f"{platform['name']:<12} {platform['title']:<14} {platform['script']}")
        return 0

    try:
        config = ensure_config()
        selected, skipped = select_platforms(config, args.platforms)
    except (FileNotFoundError, ValueError) as exc:
        print(f"❌ {exc}")
        return 1

    if not selected:
        print("❌ 没有找到已配置账号的平台，请检查平台 Secret 或 config/token.json")
        for platform in skipped:
            print(f"   - {platform['title']}: 未配置")
        return 1

    print(f"📋 本次执行: {', '.join(item['title'] for item in selected)}")
    if skipped:
        print(f"⏭ 未配置跳过: {', '.join(item['title'] for item in skipped)}")

    reset_notify_buffer()
    results = [run_platform(platform) for platform in selected]
    records = load_notification_records()
    failed = [item for item in results if not item["success"]]

    title, content = build_summary(results, skipped, records)
    print(f"\n{title}\n{content}")

    # 所有子任务推送已缓冲，这里统一发送一次
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from notification import NotificationSound, send_notification

        sound = (
            NotificationSound.BIRDSONG
            if not failed
            else NotificationSound.ALARM
        )
        send_notification(title=title, content=content, sound=sound)
    except Exception as exc:  # noqa: BLE001 - 推送失败不改变任务结果
        print(f"⚠️ 统一推送发送失败: {type(exc).__name__}: {exc}")
    finally:
        try:
            NOTIFY_BUFFER_PATH.unlink()
        except FileNotFoundError:
            pass

    print(f"\n📊 执行结果: {len(results) - len(failed)}/{len(results)} 个平台进程成功")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
