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
    # 允许调用该工具的角色。默认三种角色都能用；教师专用工具写 ("teacher",)。
    # 过滤发生在两处：① 组装给模型的工具清单（看不见就调不到）；② execute() 执行前再校验。
    roles: tuple[str, ...] = ("student", "teacher", "admin")


TOOLS: dict[str, ToolSpec] = {}


def tool(name: str, description: str, parameters: dict,
         flows: tuple[str, ...] = ("explain", "generate_items"),
         roles: tuple[str, ...] = ("student", "teacher", "admin")):
    def deco(fn: Callable):
        TOOLS[name] = ToolSpec(name, description, parameters, fn, flows, roles)
        return fn

    return deco


def openai_tools(flow_id: str, names: list[str] | None = None,
                 role: str = "") -> list[dict]:
    """组装给模型的工具清单。role 非空时按角色过滤（空 = 不过滤，兼容旧调用方）。"""
    wanted = names or [spec.name for spec in TOOLS.values() if flow_id in spec.flows]
    specs = []
    for name in wanted:
        spec = TOOLS.get(name)
        if spec is None or flow_id not in spec.flows:
            continue
        if role and role not in spec.roles:
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


def role_of(ctx) -> str:
    """从工具上下文里取调用者角色（由服务端注入，模型无法指定）。"""
    return str(((getattr(ctx, "extra", None) or {}).get("role") or "")).strip()


def execute(name: str, args: dict, ctx) -> Any:
    spec = TOOLS.get(name)
    if spec is None:
        return {"error": f"未知工具 {name}"}
    if ctx.flow_id not in spec.flows:
        return {"error": f"当前任务流 {ctx.flow_id} 不能调用 {name}"}
    role = role_of(ctx)
    if role and role not in spec.roles:
        return {"error": f"当前角色（{role}）无权调用工具 {name}"}
    try:
        return spec.fn(ctx, **(args or {}))
    except TypeError as exc:
        return {"error": f"参数错误：{exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
