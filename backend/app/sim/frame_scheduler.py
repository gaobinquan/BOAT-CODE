"""帧调度器：模拟逐帧电力分配（纯函数，确定性）。

已核实机制（设计规格 4.0）：
- AI 按帧执行；每帧所有房间按建造顺序依次跑各自 AI
- 满电力(set max power) 优先于逐格加电(increase by one)：
  满电房间帧 1 即满；逐格房间帧 1 只有 1 格电
- 电力不足时按建造顺序分配
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RoomPowerIntent:
    """单个房间的电力意图，由指令链解析而来。"""

    room_id: str
    build_order: int
    mode: str                # always_max / incremental / conditional_off / passive
    target_power: int = 0    # 希望达到的电力
    condition_desc: str = "" # 条件开的描述（供警告输出）


@dataclass
class FrameResult:
    frame: int
    power_by_room: Dict[str, int] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


class FrameScheduler:
    """按帧分配电力并输出时序冲突警告。"""

    def __init__(self, max_frames: int = 6):
        self.max_frames = max_frames

    def simulate(
        self,
        intents: List[RoomPowerIntent],
        total_power: int,
    ) -> List[FrameResult]:
        """帧 1 起逐帧分配电力。

        - 帧 1：always_max 房间（按建造顺序）先满电；
          剩余电力给 incremental 房间每房 1 格（按建造顺序）
        - 后续帧：需求未满足的房间按建造顺序各 +1 格
        - 总需求超限 → 警告（按建造顺序的优先级后果）
        """
        intents = sorted(intents, key=lambda i: i.build_order)
        power: Dict[str, int] = {i.room_id: 0 for i in intents}
        frames: List[FrameResult] = []
        warnings: List[str] = []

        always = [i for i in intents if i.mode == "always_max"]
        incr = [i for i in intents if i.mode == "incremental"]
        cond = [i for i in intents if i.mode == "conditional_off"]

        frame1 = FrameResult(frame=1)
        available = total_power
        # 1) 满电房间优先
        for i in always:
            need = i.target_power
            if available >= need:
                power[i.room_id] = need
                available -= need
            else:
                power[i.room_id] = available
                available = 0
                warnings.append(
                    f"帧1 电力不足：{i.room_id} 满电需 {need}，仅得 {power[i.room_id]}"
                )
        # 2) 逐格房间每房 1 格
        for i in incr:
            if available > 0 and power[i.room_id] < i.target_power:
                power[i.room_id] += 1
                available -= 1
            elif power[i.room_id] < i.target_power:
                warnings.append(
                    f"帧1 电力不足：{i.room_id}（逐格加电）未分到电力"
                )
        # 3) 条件开房间初始为 0（passive 无电力指令不警告）
        for i in cond:
            if i.mode == "passive":
                continue
            warnings.append(
                f"{i.room_id} 条件开（{i.condition_desc}），帧1 为 0 格电，触发后逐格+1"
            )
        frame1.power_by_room = dict(power)
        frames.append(frame1)

        # 后续帧：按建造顺序 +1 格直至需求满足或达到 max_frames
        for frame_no in range(2, self.max_frames + 1):
            fr = FrameResult(frame=frame_no)
            for i in incr:
                if power[i.room_id] < i.target_power:
                    power[i.room_id] += 1
            fr.power_by_room = dict(power)
            frames.append(fr)
            if all(power[i.room_id] >= i.target_power for i in incr):
                break

        # 常开总量是否超总电力（静态超支检查，独立于帧模拟）
        always_sum = sum(i.target_power for i in always)
        if always_sum > total_power:
            warnings.append(
                f"常开电力合计 {always_sum} > 反应堆 {total_power}，"
                f"按建造顺序晚者先被限电"
            )

        for fr in frames:
            fr.warnings = list(warnings)
        return frames

    def parse_intents(
        self,
        room_id: str,
        build_order: int,
        commands: List[dict],
    ) -> RoomPowerIntent:
        """从指令链解析电力意图。

        commands: [{"condition": {"id": ...}, "action": {"id": ..., "params": {...}}}, ...]
        """
        for cmd in commands:
            cond_id = cmd["condition"]["id"]
            act = cmd["action"]
            if act["id"] == "act_set_max_power":
                if cond_id == "cond_none":
                    return RoomPowerIntent(
                        room_id, build_order, "always_max",
                        target_power=act["params"].get("max_power", 3),
                    )
                return RoomPowerIntent(
                    room_id, build_order, "conditional_off",
                    target_power=act["params"].get("max_power", 3),
                    condition_desc=cond_id,
                )
            if act["id"] == "act_power_up":
                if cond_id == "cond_none":
                    return RoomPowerIntent(
                        room_id, build_order, "incremental",
                        target_power=act["params"].get("target_power", 1),
                    )
                return RoomPowerIntent(
                    room_id, build_order, "conditional_off",
                    target_power=act["params"].get("target_power", 1),
                    condition_desc=cond_id,
                )
            if act["id"] == "act_set_power":
                if cond_id == "cond_none":
                    return RoomPowerIntent(
                        room_id, build_order, "always_max",
                        target_power=act["params"].get("电力值", act["params"].get("power", 1)),
                    )
                return RoomPowerIntent(
                    room_id, build_order, "conditional_off",
                    target_power=act["params"].get("电力值", act["params"].get("power", 1)),
                    condition_desc=cond_id,
                )
        return RoomPowerIntent(room_id, build_order, "passive", 0, "无电力指令")
