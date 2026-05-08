from __future__ import annotations

import argparse
import http.server
import socketserver
from pathlib import Path

from .config import ConfigError, load_config
from .assessment.evaluator import AssessmentEvaluator
from .assessment.report import generate_assessment_html_report
from .evaluation import Evaluator
from .reporting import generate_html_report
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

    assessment_report_parser = subparsers.add_parser("assessment-report", help="从模型能力评估结果生成 HTML 报告")
    assessment_report_parser.add_argument("--input", default="runs/latest", help="运行结果目录")
    assessment_report_parser.add_argument("--output", help="HTML 输出路径，默认写入输入目录 report.html")

    report_parser = subparsers.add_parser("report", help="从运行结果生成 HTML 报告")
    report_parser.add_argument("--input", default="runs/latest", help="运行结果目录")
    report_parser.add_argument("--output", help="HTML 输出路径，默认写入输入目录 report.html")

    serve_parser = subparsers.add_parser("serve", help="启动本地静态报告服务")
    serve_parser.add_argument("--input", default="runs/latest", help="报告目录")
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
    config = load_config(use_dotenv=not args.no_dotenv, dry_run=args.dry_run)
    if args.provider == "fake":
        config = _force_fake(config)
    if args.dry_run:
        print(f"配置有效，模型数量：{len(config.models)}")
        for model in config.models:
            print(f"- {model.alias}: {model.provider}/{model.model_name}")
        return 0
    summary = Evaluator(config).run()
    report_path = generate_html_report(summary.to_dict(), summary.output_dir / "report.html")
    generate_html_report(load_summary(config.output_root / "latest"), config.output_root / "latest" / "report.html")
    print(f"评测完成：{summary.output_dir}")
    print(f"报告文件：{report_path}")
    return 0


def _assessment_run(args: argparse.Namespace) -> int:
    config = load_config(use_dotenv=not args.no_dotenv, dry_run=args.dry_run)
    if args.provider == "fake":
        config = _force_fake(config)
    if args.dry_run:
        print(f"配置有效，模型数量：{len(config.models)}")
        for model in config.models:
            print(f"- {model.alias}: {model.provider}/{model.model_name}")
        return 0
    summary = AssessmentEvaluator(config).run()
    report_path = generate_assessment_html_report(summary.to_dict(), summary.output_dir / "report.html")
    generate_assessment_html_report(load_summary(config.output_root / "latest"), config.output_root / "latest" / "report.html")
    print(f"模型能力评估完成：{summary.output_dir}")
    print(f"报告文件：{report_path}")
    return 0


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
    output_path = Path(args.output) if args.output else input_dir / "report.html"
    generate_html_report(summary, output_path)
    print(f"报告文件：{output_path}")
    return 0


def _assessment_report(args: argparse.Namespace) -> int:
    input_dir = Path(args.input)
    summary = load_summary(input_dir)
    output_path = Path(args.output) if args.output else input_dir / "report.html"
    generate_assessment_html_report(summary, output_path)
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
        print(f"报告服务：http://127.0.0.1:{args.port}/report.html")
        httpd.serve_forever()
    return 0
