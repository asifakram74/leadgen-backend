import os
import re
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from typing import Dict, Optional
from dotenv import load_dotenv
from datetime import datetime

# Ensure environment variables are loaded for background threads
load_dotenv()


class AISiteService:
    def __init__(self):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if self.api_key:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://api.deepseek.com"
            )
        else:
            self.client = None

    def analyze_website(self, url: str, business_info: Dict) -> Dict:
        """
        Master Audit Engine: Performs a high-technical-depth analysis of a website.
        Strictly prohibits fabrication and repetition.
        """
        if not self.client:
            fallback_report = "## Executive Summary\n\n**System Error**: DeepSeek API key is missing or invalid.\n\n### Required Action\n\n- Add your DEEPSEEK_API_KEY to the environment variables."
            return {"status": "Analysis Error", "reason": "No API Key", "report": fallback_report}

        try:
            # 1. Fetch page content with realistic headers
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }
            response = requests.get(url, timeout=20, headers=headers)
            if response.status_code != 200:
                fallback_report = f"## Executive Summary\n\n**Critical Failure**: The AI was unable to reach the website.\n\n### Detailed Findings\n\n- **Connection Error**: Website returned HTTP {response.status_code}\n- **Action Required**: Verify that the domain is still active and not blocking automated access."
                return {
                    "status": "Unreachable",
                    "reason": f"Website unreachable (Status {response.status_code})",
                    "report": fallback_report
                }

            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract technical metadata for the auditor
            title = soup.title.string if soup.title else "No Title"
            meta_desc = ""
            desc_tag = soup.find("meta", attrs={"name": "description"})
            if desc_tag:
                meta_desc = desc_tag.get("content", "")

            # Technical data harvesting
            headings = [h.text.strip() for h in soup.find_all(['h1', 'h2', 'h3'])]
            links = soup.find_all('a')
            images = soup.find_all('img')
            scripts = soup.find_all('script')
            
            # ── Contact Harvesting ───────────────────────────
            social_patterns = ['facebook.com', 'instagram.com', 'linkedin.com', 'twitter.com', 'x.com', 'youtube.com', 'tiktok.com', 'upwork.com', 'snapchat.com', 'threads.net', 'pinterest.com', 'yelp.com']
            found_socials = []
            found_emails = set()
            found_whatsapp = ""

            for link in links:
                href = link.get('href', '')
                if any(p in href.lower() for p in social_patterns):
                    if href.startswith('/') or 'google.com' in href: continue
                    found_socials.append(href)
                
                if 'mailto:' in href.lower():
                    email = href.lower().replace('mailto:', '').split('?')[0].strip()
                    if email: found_emails.add(email)
                
                if 'wa.me' in href.lower() or 'api.whatsapp.com' in href.lower():
                    found_whatsapp = href

            # Regex backup for emails
            if not found_emails:
                email_regex = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
                emails_in_text = re.findall(email_regex, soup.get_text())
                for e in emails_in_text: found_emails.add(e.lower())

            # Extract a clean text sample for context
            for s in soup(["script", "style"]):
                s.decompose()
            clean_text = soup.get_text(separator=' ', strip=True)[:2500]

            system_prompt = (
                "You are a Senior Website Auditor and Master SEO Strategist. Your mission is to perform a "
                "brutally honest, highly technical, and professional audit of the provided website content.\n\n"
                "STRICT MASTER RULES:\n"
                "1. NO FABRICATION: Do not invent issues. Only report what can be logically proven from the provided HTML/Meta data.\n"
                "2. NO REPETITION: Every finding must be unique. Do not repeat the same issue across multiple categories.\n"
                "3. TECHNICAL PRECISION: Use executive, high-level technical terms (e.g., LCP, CLS, semantic hierarchy, DOM complexity).\n"
                "4. MOBILE-FIRST: Any responsiveness failure (missing viewport, horizontal scroll, desktop-only nav) is a CRITICAL severity issue.\n\n"
                "### FORMAT:\n"
                "Return a structured Markdown report with headings: Executive Summary, Ratings Table, Detailed Findings, Issue List (Severity based), and Overall Verdict.\n\n"
                "CRITICAL: Your 'Ratings Table' MUST include exactly these four rows to ensure system parsing:\n"
                "| Category | Score | Notes |\n"
                "|---|---|---|\n"
                "| UX/UI | X/10 | ... |\n"
                "| SEO | X/10 | ... |\n"
                "| Performance | X/10 | ... |\n"
                "| Responsiveness | X/10 | ... |\n"
            )

            user_prompt = f"""
AUDIT REQUEST:
Business Name: {business_info.get('name', 'Unknown')}
Category: {business_info.get('category', 'Unknown')}
URL: {url}

SCRAPED DATA FOR ANALYSIS:
Title Tag: {title}
Meta Description: {meta_desc}
Heading Structure (first 10): {str(headings[:10])}
Assets Count: {len(links)} links, {len(images)} images, {len(scripts)} scripts.

SAMPLE PAGE CONTENT:
{clean_text}

TASK: Perform the audit according to the Master Rules. Be professional and strictly non-repetitive.
"""

            completion = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            )

            report = completion.choices[0].message.content if completion.choices else ""
            if not report:
                fallback_report = "## Executive Summary\n\n**System Error**: The AI analysis engine failed to generate a detailed report for this asset. Please retry."
                return {"status": "Analysis Error", "reason": "AI returned empty report", "report": fallback_report}

            # Regex backup for socials in raw text/scripts if not found in anchors
            if not found_socials:
                social_regex = r'https?://(?:www\.)?(?:facebook\.com|instagram\.com|linkedin\.com|twitter\.com|x\.com|youtube\.com|tiktok\.com|upwork\.com|snapchat\.com|threads\.net|pinterest\.com|yelp\.com)/[a-zA-Z0-9._-]+'
                # Check scripts and full text
                raw_matches = re.findall(social_regex, response.text)
                for m in raw_matches:
                    if 'google.com' in m.lower(): continue
                    found_socials.append(m)

            # Post-processing: Determine status based on the AI's verdict
            actual_status = "Issues"
            if any(term in report for term in ["✅ Ready", "Healthy", "No Issue", "Excellent"]):
                actual_status = "Healthy"
            elif any(term in report for term in ["❌ Redesign Required", "Critical", "Poor"]):
                actual_status = "Issues"

            # Clean and label social links for the frontend
            labeled_socials = []
            for s in list(dict.fromkeys(found_socials)):
                url_l = s.lower()
                label = "Social"
                if 'facebook' in url_l: label = "Facebook"
                elif 'instagram' in url_l: label = "Instagram"
                elif 'linkedin' in url_l: label = "LinkedIn"
                elif 'twitter' in url_l or 'x.com' in url_l: label = "X"
                elif 'tiktok' in url_l: label = "TikTok"
                elif 'youtube' in url_l: label = "YouTube"
                elif 'upwork' in url_l: label = "Upwork"
                elif 'snapchat' in url_l: label = "Snapchat"
                elif 'threads' in url_l: label = "Threads"
                elif 'pinterest' in url_l: label = "Pinterest"
                elif 'yelp' in url_l: label = "Yelp"
                labeled_socials.append(f"{label}: {s}")

            return {
                "status": actual_status,
                "reason": "Technical analysis complete" if report else "Empty analysis result",
                "report": report,
                "social_links": ", ".join(labeled_socials),
                "emails": ", ".join(list(found_emails)),
                "whatsapp": found_whatsapp
            }

        except Exception as e:
            fallback_report = f"## Executive Summary\n\n**Critical Failure**: The AI was unable to establish a connection to the website.\n\n### Detailed Findings\n\n- **Connection Error**: {str(e)}\n- **Action Required**: Verify that the domain is correctly spelled, still active, and has a valid SSL certificate."
            return {"status": "Unreachable", "reason": "Connection Failed", "report": fallback_report}

    @staticmethod
    def get_safe_folder_name(name: str, identifier: str) -> str:
        """
        Generates a consistent, web-safe folder name for leads.
        Uses hyphens for clean URLs.
        """
        import hashlib, re, uuid
        raw_name = name.lower()
        clean_name = re.sub(r'[^a-z0-9]+', '-', raw_name).strip('-')
        # Ensure we have a stable hash
        safe_id = identifier or str(uuid.uuid4())
        url_hash = hashlib.md5(safe_id.encode()).hexdigest()[:8]
        return f"{clean_name}-{url_hash}"

    def _extract_scores(self, report_text: str) -> dict:
        """
        Parses ratings like 'UX/UI | 4 | Poor...' or 'Responsiveness: 5/10'
        from the DeepSeek report text. Returns a dict of label → score string.
        """
        scores = {}
        # Normalize report: remove bolding for easier matching
        clean_text = report_text.replace("**", "")

        # Try to parse from table format first
        table_matches = re.findall(r"\|\s*([^|]+)\s*\|\s*(\d+)(?:\s*/\s*10)?\s*\|\s*([^|]+)\s*\|", clean_text)
        for label, val, _ in table_matches:
            lbl = label.strip().lower()
            if lbl not in ["category", "---", "ratings table"]:
                # Normalize label
                if "ux" in lbl or "user" in lbl: clean_lbl = "UX/UI"
                elif "seo" in lbl: clean_lbl = "SEO"
                elif "respo" in lbl or "mobile" in lbl: clean_lbl = "Responsiveness"
                elif "dev" in lbl or "perf" in lbl or "speed" in lbl: clean_lbl = "Performance"
                else: clean_lbl = label.strip()
                scores[clean_lbl] = val.strip()

        # Fallback to standard key-value matches
        patterns = [
            ("UX/UI",  r"User[- ]?Friendliness[^\d]*(\d+)\s*/\s*10"),
            ("UX/UI",  r"UX[^\d]*(\d+)\s*/\s*10"),
            ("SEO",          r"SEO[^\d]*(\d+)\s*/\s*10"),
            ("Performance",        r"Performance[^\d]*(\d+)\s*/\s*10"),
            ("Performance",        r"Speed[^\d]*(\d+)\s*/\s*10"),
            ("Responsiveness",        r"Responsiveness[^\d]*(\d+)\s*/\s*10"),
            ("Responsiveness",        r"Mobile[^\d]*(\d+)\s*/\s*10"),
        ]
        for label, pattern in patterns:
            if label not in scores:
                m = re.search(pattern, clean_text, re.IGNORECASE)
                if m: scores[label] = m.group(1)
        
        return scores

    def create_audit_report_file(self, name: str, report_text: str, folder_path: str) -> str:
        """
        Generates a cinematic, hyper-visual PDF and HTML audit report.
        """
        os.makedirs(folder_path, exist_ok=True)
        scores = self._extract_scores(report_text)
        generated_date = datetime.now().strftime("%B %d, %Y %H:%M")

        # ── 1. Create Premium HTML Report ──
        try:
            html_path = os.path.join(folder_path, "audit_report.html")
            
            def get_score_color(val):
                try:
                    v = float(val)
                    if v >= 8: return "#10b981" # Emerald
                    if v >= 5: return "#f59e0b" # Amber
                    return "#ef4444" # Rose
                except: return "#6366f1"

            # Clean and format the Markdown for HTML
            safe_report = report_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            safe_report = re.sub(r"\|.*\|", "", safe_report)
            safe_report = re.sub(r"[-]{3,}", "", safe_report)

            # Process headings with scores
            lines = safe_report.split("\n")
            processed_lines = []
            for line in lines:
                if line.startswith("## ") or line.startswith("### "):
                    title = line.replace("#", "").strip()
                    score_tag = ""
                    for cat, score in scores.items():
                        if cat.lower() in title.lower():
                            s100 = int(float(score) * 10)
                            score_tag = f' <span style="background:{get_score_color(score)}; color:white; padding:2px 8px; border-radius:6px; font-size:12px; margin-left:10px;">SCORE: {s100}/100</span>'
                            break
                    tag = "h2" if line.startswith("## ") else "h3"
                    processed_lines.append(f"<{tag}>{title}{score_tag}</{tag}>")
                elif line.strip().startswith("- ") or line.strip().startswith("* "):
                    processed_lines.append(f"<li>{line.strip()[2:]}</li>")
                elif "**" in line:
                    processed_lines.append(re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line))
                else:
                    processed_lines.append(line)
            
            final_lines = []
            in_list = False
            for pl in processed_lines:
                if pl.startswith("<li>"):
                    if not in_list:
                        final_lines.append("<ul>")
                        in_list = True
                    final_lines.append(pl)
                else:
                    if in_list:
                        final_lines.append("</ul>")
                        in_list = False
                    final_lines.append(pl)
            safe_report = "\n".join(final_lines)

            # Score Dashboard HTML
            score_dashboard = ""
            if scores:
                score_dashboard = '<div class="score-dashboard">'
                for lbl, val in scores.items():
                    color = get_score_color(val)
                    s100 = int(float(val) * 10)
                    score_dashboard += f'''
                    <div class="score-item">
                        <div class="score-circle-container">
                            <div class="score-circle" style="background: conic-gradient({color} {s100}%, #f1f5f9 0)">
                                <div class="score-inner">{s100}</div>
                            </div>
                        </div>
                        <div class="score-label">{lbl}</div>
                    </div>
                    '''
                score_dashboard += '</div>'

            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Audit Report — {name}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;600;800&family=Inter:wght@400;500;700&display=swap');
  :root {{ --primary: #6366f1; --background: #f8fafc; --card: #ffffff; --text: #1e293b; --text-muted: #64748b; }}
  body {{ font-family: 'Inter', sans-serif; line-height: 1.7; margin: 0; padding: 0; background: var(--background); color: var(--text); }}
  .container {{ max-width: 900px; margin: 40px auto; background: var(--card); padding: 60px; border-radius: 40px; box-shadow: 0 25px 50px -12px rgba(0,0,0,0.08); border: 1px solid rgba(0,0,0,0.05); }}
  .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 40px; padding-bottom: 30px; border-bottom: 2px solid #f1f5f9; }}
  .header-left h1 {{ font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 32px; margin: 0; letter-spacing: -1px; color: #0f172a; }}
  .header-left .target {{ color: var(--primary); font-weight: 700; text-transform: uppercase; font-size: 14px; letter-spacing: 2px; }}
  .badge-verified {{ background: #f0fdf4; color: #166534; padding: 6px 14px; border-radius: 12px; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1px; border: 1px solid #bbf7d0; }}
  .score-dashboard {{ display: flex; justify-content: space-around; gap: 20px; margin-bottom: 50px; background: #f8fafc; padding: 30px; border-radius: 30px; }}
  .score-item {{ text-align: center; flex: 1; }}
  .score-circle-container {{ position: relative; width: 80px; height: 80px; margin: 0 auto 15px; }}
  .score-circle {{ width: 100%; height: 100%; border-radius: 50%; display: flex; align-items: center; justify-content: center; }}
  .score-inner {{ width: 80%; height: 80%; background: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: 800; color: #0f172a; box-shadow: inset 0 2px 4px rgba(0,0,0,0.05); }}
  .score-label {{ font-size: 11px; font-weight: 800; color: var(--text-muted); text-transform: uppercase; letter-spacing: 1px; }}
  h2, h3 {{ font-family: 'Outfit', sans-serif; color: #0f172a; margin-top: 40px; }}
  h2 {{ font-size: 24px; border-left: 5px solid var(--primary); padding-left: 15px; margin-bottom: 24px; background: #f8fafc; padding-top: 10px; padding-bottom: 10px; border-radius: 0 10px 10px 0; display: flex; align-items: center; justify-content: space-between; }}
  h3 {{ font-size: 18px; color: var(--primary); display: flex; align-items: center; gap: 10px; }}
  .report-body {{ font-size: 15px; color: #334155; }}
  ul {{ padding-left: 0; list-style: none; }}
  li {{ margin-bottom: 12px; padding: 15px; background: #fff; border-radius: 15px; border: 1px solid #f1f5f9; border-left: 4px solid #e2e8f0; }}
  li:hover {{ border-color: var(--primary); }}
  .footer {{ margin-top: 60px; padding-top: 30px; border-top: 1px solid #f1f5f9; text-align: center; font-size: 12px; color: var(--text-muted); }}
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="header-left"><div class="target">{name}</div><h1>Intelligence Audit</h1></div>
      <div class="badge-verified">Verified DeepSeek AI Analysis</div>
    </div>
    {score_dashboard}
    <div class="report-body">{safe_report}</div>
    <div class="footer">Generated by LeadStation AI  |  {generated_date}<br>&copy; 2024. Confidential Business Intelligence Report.</div>
  </div>
</body>
</html>"""

            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)

            # ── 2. Create Premium PDF Report ──
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                from reportlab.lib.units import mm
                from reportlab.lib.colors import HexColor, white
                from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
                from reportlab.lib.enums import TA_CENTER, TA_RIGHT

                pdf_path = os.path.join(folder_path, "audit_report.pdf")
                doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                    rightMargin=15*mm, leftMargin=15*mm, topMargin=15*mm, bottomMargin=15*mm)

                styles = getSampleStyleSheet()
                T = lambda name, **kw: ParagraphStyle(name, parent=styles["Normal"], **kw)

                # Custom Styles
                title_s = T("Ttl", fontSize=26, textColor=HexColor("#0f172a"), fontName="Helvetica-Bold", leading=32)
                sub_s = T("Sub", fontSize=10, textColor=HexColor("#6366f1"), fontName="Helvetica-Bold", spaceAfter=20, letterSpacing=1)
                sec_s = T("Sec", fontSize=14, textColor=white, fontName="Helvetica-Bold", spaceBefore=12, spaceAfter=8, backColor=HexColor("#0f172a"), leftIndent=0, borderPadding=8)
                body_s = T("Bod", fontSize=10, textColor=HexColor("#334155"), leading=14, spaceAfter=6)
                bullet_s = T("Bul", fontSize=10, textColor=HexColor("#334155"), leading=14, leftIndent=5*mm, spaceAfter=6)

                story = []
                story.append(Paragraph(f"{name.upper()}", sub_s))
                story.append(Paragraph(f"Website Intelligence Audit", title_s))
                story.append(Spacer(1, 10))
                story.append(HRFlowable(width="100%", thickness=1, color=HexColor("#f1f5f9"), spaceAfter=15))

                if scores:
                    lbl_row = [Paragraph(lbl.upper(), T("L", fontSize=8, alignment=TA_CENTER, fontName="Helvetica-Bold")) for lbl, _ in scores.items()]
                    val_row = [Paragraph(f"{val}<font size=8>/10</font>", T("V", fontSize=18, alignment=TA_CENTER, fontName="Helvetica-Bold")) for _, val in scores.items()]
                    sc_table = Table([lbl_row, val_row], colWidths=[180 // len(scores) * mm] * len(scores))
                    sc_table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), HexColor("#f8fafc")), ("ROUNDEDCORNERS", [10]), ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]))
                    story.append(sc_table)
                    story.append(Spacer(1, 20))

                clean_report = report_text.replace("&", "&amp;")
                clean_report = re.sub(r"\|.*\|", "", clean_report)
                clean_report = re.sub(r"[-]{3,}", "", clean_report)

                for line in clean_report.split("\n"):
                    line = line.strip()
                    if not line: continue
                    
                    if line.startswith("## "):
                        title = line.replace("#", "").strip().upper()
                        current_score = ""
                        for cat, score in scores.items():
                            if cat.lower() in title.lower():
                                current_score = f" [SCORE: {score}/10]"
                                break
                        story.append(Spacer(1, 10))
                        story.append(Paragraph(f"  {title}{current_score}", sec_s))
                        story.append(Spacer(1, 5))
                    elif line.startswith("### "):
                        story.append(Paragraph(line.replace("#", "").strip(), T("H3", fontSize=12, textColor=HexColor("#6366f1"), fontName="Helvetica-Bold", spaceAfter=5)))
                    elif line.startswith("- ") or line.startswith("* "):
                        clean_line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line[2:])
                        story.append(Paragraph(f"• {clean_line}", bullet_s))
                    else:
                        clean_line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
                        story.append(Paragraph(clean_line, body_s))

                story.append(Spacer(1, 20))
                story.append(HRFlowable(width="100%", thickness=0.5, color=HexColor("#f1f5f9")))
                story.append(Paragraph(f"Generated by LeadStation AI  |  {generated_date}", T("Foot", fontSize=8, textColor=HexColor("#94a3b8"), alignment=TA_CENTER, spaceBefore=10)))

                doc.build(story)
            except Exception as e: print(f"[PDF ERROR] {e}")

            rel = folder_path.replace("\\", "/").split("storage/")[-1]
            
            # Prefer PDF if it exists, fallback to HTML
            pdf_path = os.path.join(folder_path, "audit_report.pdf")
            if os.path.exists(pdf_path):
                return f"/storage/{rel}/audit_report.pdf"
            return f"/storage/{rel}/audit_report.html"

        except Exception as e:
            print(f"[REPORT ERROR] {e}")
            return ""

    def generate_landing_page(self, lead_data: Dict, user_prompt: str = "") -> str:
        """Generates a premium single-page HTML site."""
        if not self.client: return "<h1>AI Generation Unavailable</h1>"
        if user_prompt and user_prompt.strip():
            prompt = user_prompt.strip()
        else:
            prompt = f"""
            You are an expert front-end developer.
            Business: {lead_data.get('name')} | Category: {lead_data.get('category')}
            Analysis: {lead_data.get('ai_report')}
            Return ONLY valid HTML/CSS code inside a single code block.
            """
            
        completion = self.client.chat.completions.create(model="deepseek-chat", messages=[{"role": "user", "content": prompt}])
        content = completion.choices[0].message.content
        if content.startswith("```"):
            lines = content.split('\n')
            if lines[0].startswith("```"): lines = lines[1:]
            if lines and lines[-1].startswith("```"): lines = lines[:-1]
            content = '\n'.join(lines)
        return content
