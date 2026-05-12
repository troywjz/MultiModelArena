from __future__ import annotations

import argparse
import http.server
import socketserver
from pathlib import Path

from .config import ConfigError, load_config
from .assessment.evaluator import AssessmentEvaluator
from .assessment.protocol import REQUIRED_OUTPUT_FIELDS, build_assessment_messages, parse_json_response
from .assessment.report import generate_assessment_markdown_report
from .assessment.tasks import DEFAULT_ASSESSMENT_TASKS
from .evaluation import Evaluator
from .providers import build_provider
from .report_output import default_report_output_path
from .reporting import generate_markdown_report
from .storage import load_summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arena", description="多模型多轮评测与报告生成工具")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="运行评测")
    run_parser.add_argument("--provider", choices=["fake"], help="临时覆盖所有模型为 fake provider")
    run_parser.add_argument("--dry-run", action="store_true", help="只解析配置，不发起模型调用")
    run_parser.add_argument("--no-dotenv", action="store_true", help="不读取当前目录 .env")

    assessment_run_parser = subparsers.add_parser("assessment-run", help="运行模型能力程序化评估")
    assessment_run_parser.add_argument("--provider", choices=["fake"], help="临时覆盖所有模型为 fake provider")
    assessment_run_parser.add_argument("--dry-run", action="store_true", help="只解析配置，不发起模型调用")
    assessment_run_parser.add_argument("--no-dotenv", action="store_true", help="不读取当前目录 .env")

    probe_parser = subparsers.add_parser("probe-model", help="调用模型一次并检查响应是否符合正式评测 JSON 协议")
    probe_parser.add_argument("--alias", help="要测试的模型别名；不填则测试当前配置中的全部模型")
    probe_parser.add_argument("--provider", choices=["fake"], help="临时覆盖所有模型为 fake provider")
    probe_parser.add_argument("--no-dotenv", action="store_true", help="不读取当前目录 .env")
    probe_parser.add_argument("--prompt", help="自定义连通性提示词；设置后不使用正式评测 JSON 探针")
    probe_parser.add_argument("--show-response", action="store_true", help="在控制台打印模型原始响应，默认隐藏")

    assessment_report_parser = subparsers.add_parser("assessment-report", help="从模型能力评估结果生成 Markdown 报告")
    assessment_report_parser.add_argument("--input", default="runs/latest", help="运行结果目录")
    assessment_report_parser.add_argument("--output", help="Markdown 输出路径，默认写入根目录 report-output")

    report_parser = subparsers.add_parser("report", help="从运行结果生成 Markdown 报告")
    report_parser.add_argument("--input", default="runs/latest", help="运行结果目录")
    report_parser.add_argument("--output", help="Markdown 输出路径，默认写入根目录 report-output")

    serve_parser = subparsers.add_parser("serve", help="启动本地静态文件服务")
    serve_parser.add_argument("--input", default="report-output", help="静态文件目录")
    serve_parser.add_argument("--port", type=int, default=8000, help="监听端口")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "run":
            return _run(args)
        if args.command == "assessment-run":
            return _assessment_run(args)
        if args.command == "probe-model":
            return _probe_model(args)
        if args.command == "assessment-report":
            return _assessment_report(args)
        if args.command == "report":
            return _report(args)
        if args.command == "serve":
            return _serve(args)
    except ConfigError as exc:
        print(f"配置错误：{exc}")
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"执行失败：{exc}")
        return 1
    return 0


def _run(args: argparse.Namespace) -> int:
    config = load_config(use_dotenv=not args.no_dotenv, dry_run=args.dry_run, provider_override=args.provider)
    if args.dry_run:
        print(f"配置有效，模型数量：{len(config.models)}")
        for model in config.models:
            print(f"- {model.alias}: {model.provider}/{model.model_name}")
        return 0
    summary = Evaluator(config).run()
    report_path = default_report_output_path(summary.to_dict())
    generate_markdown_report(summary.to_dict(), report_path)
    print(f"评测完成：{summary.output_dir}")
    print(f"报告文件：{report_path}")
    return 0


def _assessment_run(args: argparse.Namespace) -> int:
    config = load_config(use_dotenv=not args.no_dotenv, dry_run=args.dry_run, provider_override=args.provider)
    if args.dry_run:
        print(f"配置有效，模型数量：{len(config.models)}")
        for model in config.models:
            print(f"- {model.alias}: {model.provider}/{model.model_name}")
        return 0
    summary = AssessmentEvaluator(config).run()
    report_path = default_report_output_path(summary.to_dict())
    generate_assessment_markdown_report(summary.to_dict(), report_path)
    print(f"模型能力评估完成：{summary.output_dir}")
    print(f"报告文件：{report_path}")
    return 0


def _probe_model(args: argparse.Namespace) -> int:
    config = load_config(use_dotenv=not args.no_dotenv, provider_override=args.provider)
    models = _select_models(config.models, args.alias)
    print(f"模型探针测试，目标模型数：{len(models)}")
    print("")
    had_call_error = False
    for index, model in enumerate(models, start=1):
        if index > 1:
            print("=" * 72)
            print("")
        try:
            _probe_one_model(model, args.prompt, show_response=args.show_response)
        except Exception as exc:  # noqa: BLE001
            had_call_error = True
            print("模型探针测试")
            print(f"- Alias：{model.alias}")
            print(f"- Provider：{model.provider}")
            print(f"- Model：{model.model_name}")
            print(f"- 调用结果：失败")
            print(f"- 错误：{exc}")
            hint = _call_error_hint(model, exc)
            if hint:
                print(f"- 修正建议：{hint}")
            print("")
    return 1 if had_call_error else 0


def _probe_one_model(model, prompt: str | None, *, show_response: bool) -> None:
    provider = build_provider(model)
    if prompt:
        probe_mode = "自定义连通性提示词"
        messages = [
            {
                "role": "system",
                "content": "你是一个模型连通性测试助手。请直接回答用户的问题。",
            },
            {"role": "user", "content": prompt},
        ]
    else:
        probe_mode = "正式评测 JSON 协议"
        messages = build_assessment_messages(DEFAULT_ASSESSMENT_TASKS[0])

    print("模型探针测试")
    print(f"- Alias：{model.alias}")
    print(f"- Provider：{model.provider}")
    print(f"- Model：{model.model_name}")
    print(f"- Temperature：{model.temperature}")
    print(f"- Max tokens：{model.max_tokens}")
    print(f"- Token limit field：{model.token_limit_field}")
    print(f"- Disable proxy：{model.disable_proxy}")
    print(f"- 模式：{probe_mode}")
    if prompt:
        print(f"- Prompt：{prompt}")
    else:
        print(f"- 任务：{DEFAULT_ASSESSMENT_TASKS[0].id} / {DEFAULT_ASSESSMENT_TASKS[0].title}")
    print("")

    response = provider.complete(messages)

    print("调用元数据")
    if response.usage:
        for key, value in response.usage.items():
            print(f"- {key}: {value}")
    else:
        print("- 无")
    print("- 响应原文：已隐藏（需要查看时添加 --show-response）")
    for item in _truncation_diagnostics(model, response.usage):
        print(f"- {item}")
    if show_response:
        print("")
        print("原始响应")
        print(response.text)
    print("")

    parsed, parse_error = parse_json_response(response.text)
    print("正式评测 JSON 识别")
    if parsed is None:
        print("- 结果：失败")
        print(f"- 原因：{parse_error}")
        if prompt:
            print("- 说明：自定义自然语言提示词通常不会返回正式 JSON；如需测试评测协议，请不要传 --prompt。")
        else:
            print("- 说明：正式 assessment-run 需要模型输出可解析的 JSON 对象；该模型当前响应不能进入程序化评分。")
        print("")
        return

    missing_fields = [field for field in REQUIRED_OUTPUT_FIELDS if not parsed.get(field)]
    print("- 结果：成功")
    if missing_fields:
        print(f"- 字段完整性：缺少 {', '.join(missing_fields)}")
        print("- 说明：可以被解析，但正式评测会因字段不完整而扣分。")
    else:
        print("- 字段完整性：完整")
    print("")


def _truncation_diagnostics(model, usage: dict) -> list[str]:
    finish_reason = str(usage.get("finish_reason", ""))
    completion_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    truncated = finish_reason in {"length", "max_tokens"} or (
        isinstance(completion_tokens, int) and model.max_tokens is not None and completion_tokens >= model.max_tokens
    )
    if not truncated:
        return ["截断诊断：未发现截断信号"]

    env_name = f"ARENA_MODEL_{model.alias.upper().replace('-', '_')}_MAX_TOKENS"
    current = model.max_tokens if model.max_tokens is not None else "未设置"
    details = []
    if finish_reason:
        details.append(f"finish_reason={finish_reason}")
    if completion_tokens is not None:
        details.append(f"completion_tokens={completion_tokens}")
    details.append(f"max_tokens={current}")
    fairness_note = (
        f"当前未传 {env_name}，使用模型默认输出上限"
        if model.max_tokens is None
        else f"当前使用输出预算 {env_name}={current}"
    )
    return [
        "截断诊断：输出被截断，JSON 很可能不完整",
        f"输出上限说明：{fairness_note}",
        "修正方向：缩短评测提示、压缩输出 schema、启用 JSON mode，或约束模型不要输出思考过程",
        "截断证据：" + "，".join(details),
    ]


def _call_error_hint(model, exc: Exception) -> str:
    message = str(exc).lower()
    if "timed out" not in message and "timeout" not in message:
        return ""
    env_name = f"ARENA_MODEL_{model.alias.upper().replace('-', '_')}_TIMEOUT_SECONDS"
    return f"请求超时；将 .env 中 {env_name} 调高，例如 180，并确认 PyCharm Working directory 是项目根目录 D:\\code\\MultiModelArena"


def _select_models(models, alias: str | None):
    if not models:
        raise ConfigError("没有可用模型配置")
    if alias is None:
        return models
    for model in models:
        if model.alias == alias:
            return [model]
    available = ", ".join(model.alias for model in models)
    raise ConfigError(f"找不到模型别名 {alias}，可用别名：{available}")


def _force_fake(config):
    from dataclasses import replace

    return replace(
        config,
        models=[
            replace(model, provider="fake", api_key="", base_url="")
            for model in config.models
        ],
    )


def _report(args: argparse.Namespace) -> int:
    input_dir = Path(args.input)
    summary = load_summary(input_dir)
    output_path = Path(args.output) if args.output else default_report_output_path(summary)
    generate_markdown_report(summary, output_path)
    print(f"报告文件：{output_path}")
    return 0


def _assessment_report(args: argparse.Namespace) -> int:
    input_dir = Path(args.input)
    summary = load_summary(input_dir)
    output_path = Path(args.output) if args.output else default_report_output_path(summary)
    generate_assessment_markdown_report(summary, output_path)
    print(f"报告文件：{output_path}")
    return 0


def _serve(args: argparse.Namespace) -> int:
    directory = Path(args.input).resolve()
    if not directory.exists():
        raise FileNotFoundError(f"报告目录不存在: {directory}")

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *handler_args, **handler_kwargs):
            super().__init__(*handler_args, directory=str(directory), **handler_kwargs)

    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as httpd:
        print(f"文件服务：http://127.0.0.1:{args.port}/")
        httpd.serve_forever()
    return 0
