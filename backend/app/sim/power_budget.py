"""电力预算器：常开总量校验 + 超支自动降档（纯函数）。

三档位（规格 4.2）：
- 常开：护盾、维修
- 用后关闭/条件开：防空（敌方有战机→开；无→关）
- 半效率电：伤害够用时不满电

超支时按威胁度从低到高自动降档（威胁低者先降）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RoomDemand:
    room_id: str
    power: int          # 期望电力
    threat: int         # 该房间作为敌方目标时的威胁度（降档依据）
    tier: str           # always / conditional / half
    reason: str = ""


@dataclass
class BudgetResult:
    total: int
    used: int
    status: str                    # ok / over
    warnings: List[str] = field(default_factory=list)
    downgrades: List[str] = field(default_factory=list)   # 自动降档记录


class PowerBudget:
    """校验常开电力之和 ≤ 总电力；超支按威胁度自动降档。"""

    def check(
        self,
        demands: List[RoomDemand],
        total_power: int,
    ) -> BudgetResult:
        warnings: List[str] = []
        downgrades: List[str] = []

        always = [d for d in demands if d.tier == "always"]
        conditional = [d for d in demands if d.tier != "always"]
        used_always = sum(d.power for d in always)

        # 超支 → 按威胁度从低到高降档（改条件开，不再计入常开）
        overflow = used_always - total_power
        for d in sorted(always, key=lambda d: (d.threat, d.room_id)):
            if overflow <= 0:
                break
            overflow -= d.power
            downgrades.append(
                f"{d.room_id}（威胁{d.threat}）常开→条件开，释放 {d.power} 电力"
            )
            always.remove(d)
            conditional.append(d)

        used = sum(d.power for d in always)
        if used > total_power:
            warnings.append(f"常开电力 {used} 仍超反应堆输出 {total_power}")
            status = "over"
        else:
            status = "ok"

        warnings.extend(downgrades)
        return BudgetResult(
            total=total_power,
            used=used,
            status=status,
            warnings=warnings,
            downgrades=downgrades,
        )
