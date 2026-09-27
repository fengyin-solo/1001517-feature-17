"""人员培训业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "training"
REQUIRED_FIELDS = ["培训编号", "培训主题", "培训对象"]
STATUS_ORDER = ["待开班", "进行中", "已结班", "已取消"]
ACTION_RULES = {"开班登记": "进行中", "确认结班": "已结班", "取消培训": "已取消"}
NEGATIVE_ACTIONS = []

# 结班判定口径：考核成绩与培训课时同时达标才允许确认结班
PASS_SCORE = 60.0
FULL_SCORE = 100.0
REQUIRED_HOURS = 16.0
CLOSABLE_STATUS = "进行中"
CONDITION_TEXT = (
    f"考核成绩不低于 {PASS_SCORE:g} 分（满分 {FULL_SCORE:g} 分）"
    f"且培训课时不少于 {REQUIRED_HOURS:g} 课时"
)


def _to_number(value: Any) -> float | None:
    """把成绩/课时转成数值；空值与无法解析的一律返回 None。"""
    if value is None:
        return None
    if isinstance(value, bool):
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


def _is_blank(value: Any) -> bool:
    return value is None or not str(value).strip()


class TrainingService:
    def _apply_filters(
        self,
        rows: list[dict[str, Any]],
        *,
        keyword: str | None = None,
        topic: str | None = None,
        trainee: str | None = None,
    ) -> list[dict[str, Any]]:
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("培训编号", ""))]
        if topic:
            rows = [row for row in rows if topic in str(row.get("培训主题", ""))]
        if trainee:
            rows = [row for row in rows if trainee in str(row.get("培训对象", ""))]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        topic: str | None = None,
        trainee: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._apply_filters(
            store.rows(MODULE), keyword=keyword, topic=topic, trainee=trainee
        )
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

    def _duplicate_code_partners(self, entry: dict[str, Any]) -> list[int]:
        """找出与给定记录培训编号相同的其他记录，便于指出具体是哪几条重复。"""
        code = str(entry.get("培训编号") or "").strip()
        if not code:
            return []
        return [
            int(row.get("id", 0))
            for row in store.rows(MODULE)
            if row is not entry and str(row.get("培训编号") or "").strip() == code
        ]

    def _disqualify_reasons(self, entry: dict[str, Any]) -> list[str]:
        """按结班条件逐条核对，返回未达标原因；空列表表示达标。"""
        reasons: list[str] = []
        if _is_blank(entry.get("培训主题")):
            reasons.append("培训主题缺失")
        if self._duplicate_code_partners(entry):
            reasons.append("培训编号重复")
        score = _to_number(entry.get("考核成绩"))
        if _is_blank(entry.get("考核成绩")):
            reasons.append("考核成绩为空")
        elif score is None:
            reasons.append("考核成绩不是有效数值")
        elif score > FULL_SCORE:
            reasons.append(f"考核成绩超出满分 {FULL_SCORE:g} 分")
        elif score < PASS_SCORE:
            reasons.append(f"考核成绩未达及格线 {PASS_SCORE:g} 分")
        hours = _to_number(entry.get("培训课时"))
        if _is_blank(entry.get("培训课时")):
            reasons.append("培训课时为空")
        elif hours is None:
            reasons.append("培训课时不是有效数值")
        elif hours < REQUIRED_HOURS:
            reasons.append(f"培训课时不足 {REQUIRED_HOURS:g} 课时")
        return reasons

    def completion_summary(
        self,
        *,
        keyword: str | None = None,
        topic: str | None = None,
        trainee: str | None = None,
    ) -> dict[str, Any]:
        """结班判定汇总：只统计待结班（进行中）的培训，口径与列表筛选保持一致。"""
        rows = self._apply_filters(
            store.rows(MODULE), keyword=keyword, topic=topic, trainee=trainee
        )
        pending = [row for row in rows if row.get("status") == CLOSABLE_STATUS]
        unqualified: list[dict[str, Any]] = []
        for row in pending:
            reasons = self._disqualify_reasons(row)
            if reasons:
                unqualified.append({
                    "id": row.get("id"),
                    "培训编号": row.get("培训编号"),
                    "培训主题": row.get("培训主题"),
                    "培训对象": row.get("培训对象"),
                    "培训课时": row.get("培训课时"),
                    "考核成绩": row.get("考核成绩"),
                    "未达标原因": "；".join(reasons),
                })
        return {
            "condition": {
                "及格成绩": PASS_SCORE,
                "满分": FULL_SCORE,
                "标准课时": REQUIRED_HOURS,
                "说明": CONDITION_TEXT,
            },
            "待结班数": len(pending),
            "达标人数": len(pending) - len(unqualified),
            "未达标人数": len(unqualified),
            "未达标名单": unqualified,
        }

    def _completion_blockers(self, entry: dict[str, Any]) -> list[str]:
        """确认结班前的硬校验：任一原因成立都不许结班，并说明是哪一条、为什么。"""
        blockers: list[str] = []
        entry_id = entry.get("id")
        code = str(entry.get("培训编号") or "").strip() or "未填写"
        status = str(entry.get("status") or "")
        if status != CLOSABLE_STATUS:
            blockers.append(
                f"培训记录 {entry_id} 当前状态为「{status}」，只有进行中的培训才能确认结班"
            )
        if _is_blank(entry.get("培训主题")):
            blockers.append(
                f"培训记录 {entry_id}（培训编号「{code}」）缺少培训主题，不允许结班"
            )
        partners = self._duplicate_code_partners(entry)
        if partners:
            others = "、".join(str(item) for item in partners)
            blockers.append(
                f"培训编号「{code}」在记录 {entry_id} 与记录 {others} 中重复，不允许结班"
            )
        score = _to_number(entry.get("考核成绩"))
        if _is_blank(entry.get("考核成绩")):
            blockers.append(f"培训记录 {entry_id} 考核成绩为空，不允许结班")
        elif score is None:
            blockers.append(
                f"培训记录 {entry_id} 考核成绩「{entry.get('考核成绩')}」不是有效数值，不允许结班"
            )
        elif score > FULL_SCORE:
            blockers.append(
                f"培训记录 {entry_id} 考核成绩 {score:g} 超出满分 {FULL_SCORE:g} 分，不允许结班"
            )
        elif score < PASS_SCORE:
            blockers.append(
                f"培训记录 {entry_id} 考核成绩 {score:g} 未达及格线 {PASS_SCORE:g} 分，不允许结班"
            )
        hours = _to_number(entry.get("培训课时"))
        if _is_blank(entry.get("培训课时")):
            blockers.append(f"培训记录 {entry_id} 培训课时为空，不允许结班")
        elif hours is None:
            blockers.append(
                f"培训记录 {entry_id} 培训课时「{entry.get('培训课时')}」不是有效数值，不允许结班"
            )
        elif hours < REQUIRED_HOURS:
            blockers.append(
                f"培训记录 {entry_id} 培训课时 {hours:g} 未达标准课时 {REQUIRED_HOURS:g} 课时，不允许结班"
            )
        return blockers

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"培训记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于人员培训可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if action == "确认结班":
            blockers = self._completion_blockers(entry)
            if blockers:
                return None, "；".join(blockers)
        entry["status"] = target
        entry["pending"] = target not in (STATUS_ORDER[-2], STATUS_ORDER[-1])
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"培训记录已{action}"
