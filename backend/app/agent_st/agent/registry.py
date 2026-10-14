from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable


@dataclass
class ApprovalSpec:
    """写操作的审批规格（P2c）：有它 = 这个工具**必须先经用户确认**才能执行。

    - `summarize(args)`：给确认卡片用的「在做什么」摘要（人话，带章节/知识点/题号之类）
    - `precheck(ctx, args)`：**拦截时**先跑的前置校验 —— 此刻同轮内存状态
      （`ctx.turn` 里的构思/查重结果）还拿得到，而审批发生在新请求里、那时已经为空；
      返回非空 = 不排入待批准，直接把 blockers 交给模型去修正
    - `impact`：影响面文案，卡片上展示（写去哪个表、能不能回退）
    """

    summarize: Callable[[dict], str] | None = None
    precheck: Callable[[Any, dict], list[str]] | None = None
    impact: str = ""


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
    # 非空 = 写操作：execute() 不直接执行，改为排成「待批准动作」，由用户确认后再跑（P2c）
    approval: ApprovalSpec | None = None


TOOLS: dict[str, ToolSpec] = {}


def tool(name: str, description: str, parameters: dict,
         flows: tuple[str, ...] = ("explain", "generate_items"),
         roles: tuple[str, ...] = ("student", "teacher", "admin"),
         approval: ApprovalSpec | None = None):
    def deco(fn: Callable):
        TOOLS[name] = ToolSpec(name, description, parameters, fn, flows, roles, approval)
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


def tool_ok(result) -> bool:
    """这次工具调用算不算「成功执行」。

    返回错误、待批准（写操作只排了队、还没真跑）、显式 `ok=False`，都不算成功 ——
    前端「思考与工具调用」面板按这个显示 完成 / 失败 / 待批准。
    """
    if isinstance(result, dict):
        if result.get("error"):
            return False
        if result.get("pending"):
            return False
        if result.get("ok") is False:
            return False
    return True


def is_approval_replay(ctx) -> bool:
    """审批回放标记：approve 接口在服务端重新执行写工具时会置上它。"""
    return bool((getattr(ctx, "turn", None) or {}).get("approval_replay"))


def _run_precheck(spec: ToolSpec, ctx, args: dict) -> list[str]:
    pre = spec.approval.precheck if spec.approval else None
    if pre is None:
        return []
    try:
        return [str(x) for x in (pre(ctx, args) or [])]
    except Exception as exc:  # noqa: BLE001 - 前置校验自身出错时不放行
        return [f"前置校验执行失败：{exc}"]


def _build_action(spec: ToolSpec, args: dict, ctx) -> dict:
    summarize = spec.approval.summarize if spec.approval else None
    summary = ""
    if summarize is not None:
        try:
            summary = str(summarize(args) or "").strip()
        except Exception:  # noqa: BLE001 - 摘要失败不能挡住动作本身
            summary = ""
    extra = getattr(ctx, "extra", None) or {}
    return {
        "kind": "action",
        "action_id": "AC" + uuid.uuid4().hex[:10].upper(),
        "tool": spec.name,
        "args": args,                       # 服务端落库的参数：approve 时以它为准，不信前端
        "summary": summary or f"执行工具 {spec.name}",
        "impact": (spec.approval.impact if spec.approval else ""),
        "status": "pending",                # pending / executed / rejected
        "created_by": str(getattr(ctx, "user_id", "") or ""),
        "course_id": str(extra.get("courseId") or ""),
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _enqueue_pending(spec: ToolSpec, args: dict, ctx) -> dict:
    """写操作闸门：不执行，改成排一条待批准动作。"""
    blockers = _run_precheck(spec, ctx, args)
    if blockers:
        return {
            "ok": False,
            "errors": blockers,
            "hint": "未通过前置校验，动作**没有**进入待批准；请按 errors 修正后重试。",
        }
    action = _build_action(spec, args, ctx)
    ctx.turn.setdefault("pending_actions", []).append(action)
    return {
        "ok": False,
        "pending": True,
        "actionId": action["action_id"],
        "tool": spec.name,
        "summary": action["summary"],
        "impact": action["impact"],
        "hint": ("已排入「待批准」：需要用户在界面上点「确认执行」后才会真正写入。"
                 "本轮不要声称已经保存/已经完成，请提示用户去点确认。"),
    }


def execute(name: str, args: dict, ctx) -> Any:
    spec = TOOLS.get(name)
    if spec is None:
        return {"error": f"未知工具 {name}"}
    if ctx.flow_id not in spec.flows:
        return {"error": f"当前任务流 {ctx.flow_id} 不能调用 {name}"}
    role = role_of(ctx)
    if role and role not in spec.roles:
        return {"error": f"当前角色（{role}）无权调用工具 {name}"}

    # 写操作闸门：带 approval 的工具默认不执行，只排一条待批准动作；
    # 只有 approve 接口（服务端回放，带 approval_replay 标记）才真正执行。
    # 出题页单独放行 save_question_draft：教师点「生成习题」即视为准许写入草稿，
    # 结果直接出现在题目预览里。答疑里的同名工具仍要确认。
    extra = getattr(ctx, "extra", None) or {}
    draft_already_allowed = (
        spec.name == "save_question_draft" and bool(extra.get("autoApproveDraft"))
    )
    if spec.approval is not None and not is_approval_replay(ctx) and not draft_already_allowed:
        return _enqueue_pending(spec, args or {}, ctx)

    try:
        return spec.fn(ctx, **(args or {}))
    except TypeError as exc:
        return {"error": f"参数错误：{exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
