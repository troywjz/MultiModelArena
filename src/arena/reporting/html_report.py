from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from arena.models import DIMENSIONS
from arena.security import redact_text


def generate_html_report(summary: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    body = _render(summary)
    output_path.write_text(redact_text(body), encoding="utf-8")
    return output_path


def _render(summary: dict[str, Any]) -> str:
    results = sorted(summary["results"], key=lambda item: item["average_score"], reverse=True)
    rows = "\n".join(_score_row(result) for result in results)
    cards = "\n".join(_model_card(result) for result in results)
    tasks = "\n".join(_task_section(task, results) for task in summary["tasks"])
    chart_data = json.dumps(
        {
            "labels": [result["model_name"] for result in results],
            "scores": [result["average_score"] for result in results],
        },
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MultiModelMultiAgentArena 报告</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f7f4;
      --ink: #17211b;
      --muted: #5d665f;
      --line: #d9ded7;
      --panel: #ffffff;
      --accent: #236b5b;
      --accent-2: #9a5b21;
      --bad: #9d2f2f;
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
      padding: 32px clamp(20px, 4vw, 56px) 24px;
      border-bottom: 1px solid var(--line);
      background: #eef2ec;
    }}
    main {{ padding: 24px clamp(20px, 4vw, 56px) 48px; }}
    h1 {{ margin: 0 0 10px; font-size: clamp(28px, 4vw, 44px); letter-spacing: 0; }}
    h2 {{ margin: 32px 0 14px; font-size: 22px; letter-spacing: 0; }}
    h3 {{ margin: 0 0 10px; font-size: 18px; letter-spacing: 0; }}
    p {{ margin: 0 0 10px; }}
    .meta, .muted {{ color: var(--muted); }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-top: 20px;
    }}
    .metric, .card, .task {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .metric strong {{ display: block; font-size: 24px; }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 16px;
    }}
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
    th {{ background: #eef2ec; }}
    .scorebar {{
      min-width: 96px;
      height: 10px;
      background: #e4e7e1;
      border-radius: 999px;
      overflow: hidden;
    }}
    .scorebar span {{
      display: block;
      height: 100%;
      background: var(--accent);
    }}
    .pill {{
      display: inline-block;
      margin: 0 6px 6px 0;
      padding: 4px 8px;
      border-radius: 999px;
      background: #e7eee9;
      color: var(--accent);
      font-size: 13px;
    }}
    .error {{ color: var(--bad); }}
    .task {{ margin-bottom: 14px; }}
    .evidence {{
      padding-left: 18px;
      color: var(--muted);
    }}
    canvas {{
      width: min(680px, 100%);
      height: 220px;
      display: block;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin-bottom: 20px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>多模型评测报告</h1>
    <p class="meta">运行 ID：{_e(summary["run_id"])} · 生成时间：{_e(summary["created_at"])}</p>
    <div class="summary">
      <div class="metric"><strong>{len(results)}</strong><span>模型数量</span></div>
      <div class="metric"><strong>{len(summary["tasks"])}</strong><span>任务数量</span></div>
      <div class="metric"><strong>{sum(len(r["errors"]) for r in results)}</strong><span>错误数量</span></div>
    </div>
  </header>
  <main>
    <section>
      <h2>总体结论</h2>
      <p>{_e(summary["consensus"]).replace(chr(10), "<br>")}</p>
    </section>

    <section>
      <h2>平均分对比</h2>
      <canvas id="scoreChart" width="680" height="220" aria-label="平均分柱状图"></canvas>
      <table>
        <thead><tr><th>模型</th><th>平均分</th><th>推荐角色</th><th>维度分</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </section>

    <section>
      <h2>模型画像</h2>
      <div class="cards">{cards}</div>
    </section>

    <section>
      <h2>任务证据</h2>
      {tasks}
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
    ctx.fillStyle = '#17211b';
    ctx.font = '14px Segoe UI, Microsoft YaHei, Arial';
    const max = 10;
    const barGap = 12;
    const barWidth = Math.max(24, (width - barGap * (chartData.scores.length - 1)) / Math.max(1, chartData.scores.length));
    chartData.scores.forEach((score, index) => {{
      const x = padding + index * (barWidth + barGap);
      const barHeight = height * score / max;
      const y = padding + height - barHeight;
      ctx.fillStyle = '#236b5b';
      ctx.fillRect(x, y, barWidth, barHeight);
      ctx.fillStyle = '#17211b';
      ctx.fillText(String(score), x, y - 8);
      const label = chartData.labels[index].slice(0, 12);
      ctx.fillText(label, x, padding + height + 22);
    }});
  </script>
</body>
</html>"""


def _score_row(result: dict[str, Any]) -> str:
    scores = " ".join(
        f"{_e(name)}: {_e(str(result['scores'].get(name, 0)))}"
        for name in DIMENSIONS
    )
    return (
        "<tr>"
        f"<td>{_e(result['model_name'])}<br><span class=\"muted\">{_e(result['provider'])}</span></td>"
        f"<td><strong>{_e(str(result['average_score']))}</strong><div class=\"scorebar\"><span style=\"width:{float(result['average_score']) * 10}%\"></span></div></td>"
        f"<td>{_pills(result['recommended_roles'])}</td>"
        f"<td>{scores}</td>"
        "</tr>"
    )


def _model_card(result: dict[str, Any]) -> str:
    strengths = "".join(f"<li>{_e(item)}</li>" for item in result["strengths"])
    weaknesses = "".join(f"<li>{_e(item)}</li>" for item in result["weaknesses"])
    evidence = "".join(f"<li>{_e(item)}</li>" for item in result["evidence"])
    errors = "".join(f"<li class=\"error\">{_e(item)}</li>" for item in result["errors"])
    return f"""
    <article class="card">
      <h3>{_e(result["model_name"])}</h3>
      <p class="muted">{_e(result["alias"])} · {_e(result["provider"])} · 平均分 {_e(str(result["average_score"]))}/10</p>
      <p>{_pills(result["recommended_roles"])}</p>
      <h3>优点</h3><ul>{strengths}</ul>
      <h3>缺点</h3><ul>{weaknesses}</ul>
      <h3>证据摘录</h3><ul class="evidence">{evidence}</ul>
      {f"<h3>错误</h3><ul>{errors}</ul>" if errors else ""}
    </article>
    """


def _task_section(task: dict[str, Any], results: list[dict[str, Any]]) -> str:
    items: list[str] = []
    for result in results:
        answer = result["revisions"].get(task["id"]) or result["answers"].get(task["id"])
        if answer:
            items.append(f"<li><strong>{_e(result['model_name'])}</strong>：{_e(answer[:260])}</li>")
    return f"""
    <article class="task">
      <h3>{_e(task["title"])}</h3>
      <p class="muted">{_e(task["prompt"])}</p>
      <ul>{''.join(items)}</ul>
    </article>
    """


def _pills(items: list[str]) -> str:
    return "".join(f"<span class=\"pill\">{_e(item)}</span>" for item in items)


def _e(value: str) -> str:
    return html.escape(value, quote=True)
