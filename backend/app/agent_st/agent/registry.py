from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable
    flows: tuple[str, ...] = ("explain", "generate_items")


TOOLS: dict[str, ToolSpec] = {}


def tool(name: str, description: str, parameters: dict, flows: tuple[str, ...] = ("explain", "generate_items")):
    def deco(fn: Callable):
        TOOLS[name] = ToolSpec(name, description, parameters, fn, flows)
        return fn

    return deco


def openai_tools(flow_id: str, names: list[str] | None = None) -> list[dict]:
    wanted = names or [spec.name for spec in TOOLS.values() if flow_id in spec.flows]
    specs = []
    for name in wanted:
        spec = TOOLS.get(name)
        if spec is None or flow_id not in spec.flows:
            continue
        specs.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            }
        )
    return specs


def execute(name: str, args: dict, ctx) -> Any:
    spec = TOOLS.get(name)
    if spec is None:
        return {"error": f"未知工具 {name}"}
    if ctx.flow_id not in spec.flows:
        return {"error": f"当前任务流 {ctx.flow_id} 不能调用 {name}"}
    try:
        return spec.fn(ctx, **(args or {}))
    except TypeError as exc:
        return {"error": f"参数错误：{exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
