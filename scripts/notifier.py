"""
Sends an HTML email digest of matched postdoc positions and draft emails.
"""
import os
import smtplib
import logging
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SCORE_COLORS = {
    10: "#1a7f37", 9: "#1a7f37", 8: "#2da44e",
    7: "#d29922", 6: "#d29922",
}


def _score_badge(score: int) -> str:
    color = SCORE_COLORS.get(score, "#d29922")
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:12px;font-size:12px;font-weight:bold;">{score}/10</span>'


def _job_card(item: dict) -> str:
    job = item["job"]
    score_result = item["score_result"]
    email = item["email"]
    score = score_result.get("score", 0)
    matched = ", ".join(score_result.get("matched_areas", []))
    reason = score_result.get("reason", "")
    deadline_line = f'<p style="margin:4px 0;color:#57606a;">截止日期: {job.deadline}</p>' if job.deadline else ""
    email_body_html = email.get("body", "").replace("\n", "<br>")

    return f"""
<div style="border:1px solid #d0d7de;border-radius:8px;padding:20px;margin-bottom:20px;background:#ffffff;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
    {_score_badge(score)}
    <h2 style="margin:0;font-size:16px;color:#1f2328;">
      <a href="{job.url}" style="color:#0969da;text-decoration:none;">{job.title}</a>
    </h2>
  </div>
  <p style="margin:4px 0;color:#57606a;">🏛️ {job.institution or 'Unknown'} &nbsp;|&nbsp; 📍 {job.location or 'N/A'} &nbsp;|&nbsp; 来源: {job.source}</p>
  {deadline_line}
  <p style="margin:8px 0;color:#57606a;font-size:13px;">匹配方向: <strong>{matched}</strong> — {reason}</p>

  <details style="margin-top:12px;">
    <summary style="cursor:pointer;color:#0969da;font-weight:bold;">📝 查看AI草稿邮件</summary>
    <div style="margin-top:12px;background:#f6f8fa;border-radius:6px;padding:16px;border:1px solid #d0d7de;">
      <p style="margin:0 0 8px 0;font-size:13px;color:#57606a;"><strong>主题:</strong> {email.get('subject', '')}</p>
      <hr style="border:none;border-top:1px solid #d0d7de;margin:8px 0;">
      <p style="margin:0;font-size:13px;line-height:1.6;white-space:pre-wrap;">{email_body_html}</p>
    </div>
  </details>

  <p style="margin-top:12px;margin-bottom:0;">
    <a href="{job.url}" style="background:#0969da;color:white;padding:6px 14px;border-radius:6px;text-decoration:none;font-size:13px;">查看原始职位</a>
  </p>
</div>
"""


def build_html(items: list[dict], scan_stats: dict) -> str:
    today = date.today().strftime("%Y年%m月%d日")
    count = len(items)
    cards = "\n".join(_job_card(item) for item in items)
    total_scanned = scan_stats.get("total_scanned", 0)
    new_jobs = scan_stats.get("new_jobs", 0)

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:700px;margin:0 auto;padding:20px;background:#f6f8fa;">

<div style="background:#1f2328;color:white;padding:20px 24px;border-radius:8px;margin-bottom:24px;">
  <h1 style="margin:0 0 4px 0;font-size:20px;">🎓 博后每日推送</h1>
  <p style="margin:0;opacity:0.8;">{today} &nbsp;·&nbsp; 发现 <strong>{count}</strong> 个匹配岗位（共扫描 {total_scanned} 条，新增 {new_jobs} 条）</p>
</div>

{'<p style="color:#57606a;text-align:center;padding:40px;">今日无新增匹配岗位，明日继续。</p>' if count == 0 else cards}

<div style="margin-top:32px;padding-top:16px;border-top:1px solid #d0d7de;color:#57606a;font-size:12px;text-align:center;">
  由 PostdocScanner 自动生成 · 数据来源: AcademicJobsOnline, jobs.ac.uk, EURAXESS, AcademicPositions, NatureCareers
</div>

</body>
</html>
"""


def send_email(items: list[dict], scan_stats: dict, profile: dict) -> None:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    notify_email = os.environ.get("NOTIFY_EMAIL", "") or profile.get("notification", {}).get("notify_email", "")

    if not all([smtp_user, smtp_password, notify_email]):
        logger.warning("SMTP credentials not configured — skipping email notification")
        return

    count = len(items)
    today = date.today().strftime("%Y-%m-%d")
    subject = f"【博后推送】{today} · {count} 个匹配岗位" if count > 0 else f"【博后推送】{today} · 今日无新增"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = notify_email

    html_content = build_html(items, scan_stats)
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, notify_email, msg.as_string())
        logger.info(f"Email sent to {notify_email}: {subject}")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        raise
