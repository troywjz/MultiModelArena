from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from arena.security import redact_text


def generate_assessment_html_report(summary: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(redact_text(_render(summary)), encoding="utf-8")
    return output_path


def _render(summary: dict[str, Any]) -> str:
    results = sorted(summary["results"], key=lambda item: item["total_score"], reverse=True)
    domains = sorted({task["domain"] for task in summary["tasks"]})
    rows = "\n".join(_ranking_row(result, domains) for result in results)
    cards = "\n".join(_model_card(result, domains) for result in results)
    evidence = "\n".join(_evidence_section(result) for result in results)
    chart_data = json.dumps(
        {"labels": [result["model_name"] for result in results], "scores": [result["total_score"] for result in results]},
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>模型能力评估报告</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f4;
      --ink: #16201d;
      --muted: #5c6660;
      --line: #d7ddd7;
      --panel: #ffffff;
      --green: #236b5b;
      --blue: #315f8a;
      --amber: #9a6a22;
      --red: #9d3030;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
      background: var(--bg);
      color: var(--ink);
      line-height: 1.55;
    }}
    header {{
      padding: 30px clamp(18px, 4vw, 56px) 22px;
      background: #edf1ed;
      border-bottom: 1px solid var(--line);
    }}
    main {{ padding: 22px clamp(18px, 4vw, 56px) 48px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(28px, 4vw, 42px); letter-spacing: 0; }}
    h2 {{ margin: 30px 0 12px; font-size: 22px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 8px; font-size: 17px; letter-spacing: 0; }}
    p {{ margin: 0 0 10px; }}
    .muted {{ color: var(--muted); }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .metric, .panel, .model {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 15px;
    }}
    .metric strong {{ display: block; font-size: 24px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: #edf1ed; }}
    .models {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 16px;
    }}
    .bar {{
      min-width: 92px;
      height: 10px;
      background: #e4e8e3;
      border-radius: 999px;
      overflow: hidden;
      margin-top: 6px;
    }}
    .bar span {{ display: block; height: 100%; background: var(--green); }}
    .pill {{
      display: inline-block;
      margin: 0 6px 6px 0;
      padding: 4px 8px;
      border-radius: 999px;
      background: #e8eee9;
      color: var(--green);
      font-size: 13px;
    }}
    .warn {{ color: var(--red); }}
    canvas {{
      width: min(720px, 100%);
      height: 220px;
      display: block;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 18px;
    }}
    details {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 12px;
    }}
    summary {{ cursor: pointer; font-weight: 600; }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: #f3f5f2;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      max-height: 360px;
      overflow: auto;
    }}
  </style>
</head>
<body>
  <header>
    <h1>模型能力评估报告</h1>
    <p class="muted">运行 ID：{_e(summary["run_id"])} · 生成时间：{_e(summary["created_at"])}</p>
    <div class="metrics">
      <div class="metric"><strong>{len(results)}</strong><span>模型组合</span></div>
      <div class="metric"><strong>{len(summary["tasks"])}</strong><span>基准任务</span></div>
      <div class="metric"><strong>{sum(len(task["mutations"]) for task in summary["tasks"])}</strong><span>扰动脚本</span></div>
    </div>
  </header>
  <main>
    <section>
      <h2>总体结论</h2>
      <p>{_e(summary.get("summary", "")).replace(chr(10), "<br>")}</p>
    </section>
    <section>
      <h2>主分排名</h2>
      <canvas id="scoreChart" width="720" height="220" aria-label="主分柱状图"></canvas>
      <table>
        <thead><tr><th>模型</th><th>主分</th><th>领域分</th><th>建议角色</th><th>失败项</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>
    <section>
      <h2>模型画像</h2>
      <div class="models">{cards}</div>
    </section>
    <section>
      <h2>完整证据</h2>
      {evidence}
    </section>
  </main>
  <script>
    const chartData = {chart_data};
    const canvas = document.getElementById('scoreChart');
    const ctx = canvas.getContext('2d');
    const padding = 36;
    const width = canvas.width - padding * 2;
    const height = canvas.height - padding * 2;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.font = '14px Segoe UI, Microsoft YaHei, Arial';
    const gap = 12;
    const barWidth = Math.max(24, (width - gap * (chartData.scores.length - 1)) / Math.max(1, chartData.scores.length));
    chartData.scores.forEach((score, index) => {{
      const x = padding + index * (barWidth + gap);
      const h = height * score / 10;
      const y = padding + height - h;
      ctx.fillStyle = '#236b5b';
      ctx.fillRect(x, y, barWidth, h);
      ctx.fillStyle = '#16201d';
      ctx.fillText(String(score), x, y - 8);
      ctx.fillText(chartData.labels[index].slice(0, 14), x, padding + height + 22);
    }});
  </script>
</body>
</html>"""


def _ranking_row(result: dict[str, Any], domains: list[str]) -> str:
    domain_text = " ".join(f"{_e(domain)}: {_e(str(result['domain_scores'].get(domain, 0)))}" for domain in domains)
    roles = _top_items(result["role_fit"], 2)
    failures = result["failures"][:3] + result["errors"][:3]
    failure_text = "<br>".join(_e(item) for item in failures) or "无"
    return (
        "<tr>"
        f"<td>{_e(result['model_name'])}<br><span class=\"muted\">{_e(result['provider'])}</span></td>"
        f"<td><strong>{_e(str(result['total_score']))}</strong><div class=\"bar\"><span style=\"width:{float(result['total_score']) * 10}%\"></span></div></td>"
        f"<td>{domain_text}</td>"
        f"<td>{_pills([name for name, _score in roles])}</td>"
        f"<td class=\"{'warn' if failures else ''}\">{failure_text}</td>"
        "</tr>"
    )


def _model_card(result: dict[str, Any], domains: list[str]) -> str:
    dq = _score_list(result["quality_scores"])
    behavior = _score_list(result["behavior_fingerprint"])
    rules = _score_list(result["rule_scores"])
    roles = _pills([name for name, _score in _top_items(result["role_fit"], 3)])
    evidence = "".join(f"<li>{_e(item)}</li>" for item in result["evidence"][:4])
    return f"""
    <article class="model">
      <h3>{_e(result["model_name"])}</h3>
      <p class="muted">{_e(result["alias"])} · 主分 {_e(str(result["total_score"]))}/10</p>
      <p>{roles}</p>
      <h3>Assessment Quality</h3>
      <p>{dq}</p>
      <h3>规则评分</h3>
      <p>{rules}</p>
      <h3>行为计数</h3>
      <p>{behavior}</p>
      <h3>证据摘录</h3>
      <ul>{evidence}</ul>
    </article>
    """


def _evidence_section(result: dict[str, Any]) -> str:
    details = []
    for response in result["responses"]:
        label = f"{response['task_id']} / {response['phase_id']}"
        payload = json.dumps(response["parsed"] if response["parsed"] is not None else response["raw_text"], ensure_ascii=False, indent=2)
        details.append(f"<details><summary>{_e(label)}</summary><pre>{_e(payload)}</pre></details>")
    return f"<section class=\"panel\"><h3>{_e(result['model_name'])}</h3>{''.join(details)}</section>"


def _score_list(scores: dict[str, Any]) -> str:
    return " ".join(f"<span class=\"pill\">{_e(str(name))}: {_e(str(score))}</span>" for name, score in scores.items())


def _top_items(scores: dict[str, float], count: int) -> list[tuple[str, float]]:
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:count]


def _pills(items: list[str]) -> str:
    return "".join(f"<span class=\"pill\">{_e(item)}</span>" for item in items)


def _e(value: str) -> str:
    return html.escape(value, quote=True)
