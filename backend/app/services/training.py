"""人员培训业务规则：状态流转、结班判定、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "training"
REQUIRED_FIELDS = ["培训编号", "培训主题", "培训对象"]
STATUS_ORDER = ["待开班", "进行中", "已结班", "已取消"]
ACTION_RULES = {"开班登记": "进行中", "确认结班": "已结班", "取消培训": "已取消"}
NEGATIVE_ACTIONS = []

# 结班判定口径：考核成绩达到及格线且培训课时达到要求学时才算达标。
FULL_SCORE = 100
PASS_SCORE = 60
REQUIRED_HOURS = 8
CRITERIA_TEXT = f"考核成绩≥{PASS_SCORE}分（满分{FULL_SCORE}分）且培训课时≥{REQUIRED_HOURS}学时"
PENDING_STATUS = "进行中"  # 待结班只统计进行中的培训班


def _parse_number(value: Any) -> float | None:
    """把成绩、课时这类可能混着文本的字段解析成数字；解析不了就返回 None。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _fmt_number(value: float) -> str:
    """成绩、课时展示时去掉多余的 .0。"""
    return str(int(value)) if value == int(value) else str(value)


def judge_entry(entry: dict[str, Any]) -> list[str]:
    """按结班条件逐条核对，返回未达标原因；空列表表示达标。"""
    reasons: list[str] = []
    raw_score = entry.get("考核成绩")
    score = _parse_number(raw_score)
    if raw_score is None or str(raw_score).strip() == "":
        reasons.append("考核成绩为空")
    elif score is None:
        reasons.append(f"考核成绩「{raw_score}」无法识别为分数")
    elif score > FULL_SCORE:
        reasons.append(f"考核成绩{_fmt_number(score)}分超出满分{FULL_SCORE}分")
    elif score < PASS_SCORE:
        reasons.append(f"考核成绩{_fmt_number(score)}分未达{PASS_SCORE}分及格线")

    raw_hours = entry.get("培训课时")
    hours = _parse_number(raw_hours)
    if raw_hours is None or str(raw_hours).strip() == "":
        reasons.append("培训课时为空")
    elif hours is None:
        reasons.append(f"培训课时「{raw_hours}」无法识别为学时数")
    elif hours < REQUIRED_HOURS:
        reasons.append(f"培训课时{_fmt_number(hours)}学时不足{REQUIRED_HOURS}学时")
    return reasons


def _brief(entry: dict[str, Any]) -> dict[str, Any]:
    """结班判定名单里用到的记录摘要字段。"""
    return {
        "id": entry.get("id"),
        "培训编号": entry.get("培训编号"),
        "培训主题": entry.get("培训主题"),
        "培训对象": entry.get("培训对象"),
        "培训课时": entry.get("培训课时"),
        "考核成绩": entry.get("考核成绩"),
    }


class TrainingService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        topic: str | None = None,
        target: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("培训编号", ""))]
        if topic:
            rows = [row for row in rows if topic in str(row.get("培训主题", ""))]
        if target:
            rows = [row for row in rows if target in str(row.get("培训对象", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def completion_summary(self) -> dict[str, Any]:
        """结班判定汇总：达标/未达标名单、结班条件与数据质量提示。

        达标判定只看待结班（进行中）的培训班；编号重复、主题缺失的排查
        覆盖除已取消外的全部记录，并给出具体是哪一条。
        """
        rows = store.rows(MODULE)
        pending = [row for row in rows if row.get("status") == PENDING_STATUS]
        passed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        for row in pending:
            reasons = judge_entry(row)
            if reasons:
                failed.append({**_brief(row), "未达标原因": "；".join(reasons)})
            else:
                passed.append(_brief(row))

        active = [row for row in rows if row.get("status") != "已取消"]
        serial_count: dict[str, int] = {}
        for row in active:
            serial = str(row.get("培训编号") or "").strip()
            if serial:
                serial_count[serial] = serial_count.get(serial, 0) + 1
        data_issues: list[dict[str, Any]] = []
        for row in active:
            serial = str(row.get("培训编号") or "").strip()
            if serial and serial_count[serial] > 1:
                data_issues.append({
                    "id": row.get("id"),
                    "培训编号": row.get("培训编号"),
                    "问题": f"培训编号「{serial}」重复",
                })
            if not str(row.get("培训主题") or "").strip():
                data_issues.append({
                    "id": row.get("id"),
                    "培训编号": row.get("培训编号") or "—",
                    "问题": "培训主题缺失",
                })

        return {
            "结班条件": {
                "满分": FULL_SCORE,
                "及格线": PASS_SCORE,
                "要求课时": REQUIRED_HOURS,
                "说明": CRITERIA_TEXT,
            },
            "待结班数": len(pending),
            "达标人数": len(passed),
            "未达标人数": len(failed),
            "达标名单": passed,
            "未达标名单": failed,
            "数据质量提示": data_issues,
        }

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"培训记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于人员培训可执行范围"
        if action == "确认结班":
            reasons = judge_entry(entry)
            if reasons:
                return None, f"不允许结班：{'；'.join(reasons)}（结班条件：{CRITERIA_TEXT}）"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"培训记录已{action}"
