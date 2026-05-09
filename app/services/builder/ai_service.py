import os
import re
import requests
import urllib3
from bs4 import BeautifulSoup
from openai import OpenAI
import google.generativeai as genai
from typing import Dict, Optional
from dotenv import load_dotenv
from datetime import datetime

# Suppress SSL verification warnings for fallback mode
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
            
        # Gemini Configuration
        self.gemini_key = os.getenv("GEMINI_API_KEY")
        if self.gemini_key:
            genai.configure(api_key=self.gemini_key)

    def analyze_website(self, url: str, business_info: Dict, model_id: str = "deepseek-chat") -> Dict:
        """
        Master Audit Engine: Performs a high-technical-depth analysis of a website.
        Strictly prohibits fabrication and repetition.
        """
        if not self.client:
            fallback_report = "## Executive Summary\n\n**System Error**: DeepSeek API key is missing or invalid.\n\n### Required Action\n\n- Add your DEEPSEEK_API_KEY to the environment variables."
            return {"status": "Analysis Error", "reason": "No API Key", "report": fallback_report}

        try:
            # 1. Fetch page content with robust headers
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
            
            # Ensure URL has protocol
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            response = None
            last_error = ""
            
            # Try HTTPS then HTTP if needed, with SSL fallback
            for attempt_url in [url, url.replace('https://', 'http://') if 'https://' in url else url.replace('http://', 'https://')]:
                try:
                    response = requests.get(attempt_url, timeout=7, headers=headers, allow_redirects=True)
                    if response.status_code == 200: break
                except requests.exceptions.SSLError:
                    try:
                        # Fallback for sites with expired/invalid SSL
                        response = requests.get(attempt_url, timeout=7, headers=headers, allow_redirects=True, verify=False)
                        if response.status_code == 200: break
                    except Exception as e:
                        last_error = str(e)
                except Exception as e:
                    last_error = str(e)
            
            if not response or response.status_code != 200:
                sc = response.status_code if response else "Unknown"
                fallback_report = f"## Executive Summary\n\n**Critical Failure**: The AI was unable to reach the website.\n\n### Detailed Findings\n\n- **Connection Error**: {last_error if last_error else f'HTTP {sc}'}\n- **Action Required**: Verify that the domain is still active and not blocking automated access."
                return {
                    "status": "Unreachable",
                    "reason": f"Website unreachable ({sc})",
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

            # ── Dynamic Model Routing ──
            # Gemini API handles: gemini-* and gemma-* models
            if "gemini" in model_id.lower() or "gemma" in model_id.lower():
                if not self.gemini_key:
                    raise Exception("Gemini API Key not configured. Please add GEMINI_API_KEY to your .env file.")
                
                # Pass model_id directly — supports all models in the dropdown.
                # Only fall back to a known-good ID if a bare/generic or legacy string is passed.
                if model_id.lower() in ["gemini", "gemini-flash", "gemini-pro", "gemini-1.5-flash", "gemini-1.5-pro"]:
                    actual_model = "gemini-2.5-flash-preview-05-20"
                elif "gemini-1.5" in model_id.lower():
                    actual_model = "gemini-2.5-flash-preview-05-20"
                else:
                    actual_model = model_id
                
                # Debug: Log the incoming and resolved model
                print(f"[AI ROUTER] Incoming: '{model_id}' | Resolved: '{actual_model}'")
                
                # Re-configure to be sure
                genai.configure(api_key=self.gemini_key)
                model = genai.GenerativeModel(actual_model)
                
                # Use same generation config as builder for stability
                generation_config = {
                    "temperature": 0.3, # Lower temperature for analytical precision
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 4096,
                }
                
                response = model.generate_content(f"{system_prompt}\n\n{user_prompt}", generation_config=generation_config)
                report = response.text
            else:
                if not self.client:
                    raise Exception("DeepSeek API Key not configured.")
                    
                actual_model = "deepseek-reasoner" if "reasoner" in model_id.lower() else "deepseek-chat"
                completion = self.client.chat.completions.create(
                    model=actual_model,
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

    def _convert_html_to_pdf(self, html_path: str, pdf_path: str):
        """
        Uses Playwright to render the HTML report and save it as a high-fidelity PDF.
        Synchronous wrapper for background thread usage.
        """
        from playwright.sync_api import sync_playwright
        from app.services.scraper.browser_manager import get_browser_context
        
        with sync_playwright() as p:
            # Use a dedicated worker ID for PDF generation to avoid locking with scrapers
            context = get_browser_context(p, worker_id=888, headless=True)
            page = context.new_page()
            
            # Convert file path to absolute file:// URL for Playwright
            abs_html_path = os.path.abspath(html_path).replace('\\', '/')
            file_url = f"file:///{abs_html_path}"
            
            # Navigate to the local HTML file
            # Wait for network idle to ensure Google Fonts etc are loaded
            page.goto(file_url, wait_until="networkidle")
            
            # Print to PDF with premium settings
            page.pdf(
                path=pdf_path,
                format="A4",
                print_background=True,
                margin={"top": "0px", "right": "0px", "bottom": "0px", "left": "0px"},
                display_header_footer=False,
                prefer_css_page_size=True
            )
            
            context.close()

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

    def create_audit_report_file(self, name: str, report_text: str, folder_path: str, model_id: str = "deepseek-chat") -> str:
        """
        Generates a cinematic, hyper-visual PDF and HTML audit report.
        """
        os.makedirs(folder_path, exist_ok=True)
        scores = self._extract_scores(report_text)
        generated_date = datetime.now().strftime("%B %d, %Y %H:%M")

        # Determine Model Name for Badge
        model_display = "DeepSeek"
        if "gemini" in model_id.lower(): model_display = "Gemini"
        elif "reasoner" in model_id.lower(): model_display = "DeepSeek R1"
        
        badge_text = f"Verified {model_display} AI Analysis"

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
            
            # Highlight CRITICAL, HIGH, FAIL with badges
            safe_report = re.sub(r'\*\*(CRITICAL|FAIL|HIGH)\*\*', r'<span class="badge-critical">\1</span>', safe_report)
            safe_report = re.sub(r'\*\*(MEDIUM|LOW|HEALTHY)\*\*', r'<span class="badge-medium">\1</span>', safe_report)

            # Process headings with scores
            lines = safe_report.split("\n")
            processed_lines = []
            for line in lines:
                if line.startswith("## ") or line.startswith("### "):
                    title = line.replace("#", "").strip()
                    # Remove any existing badges for matching
                    match_title = re.sub(r'<[^>]+>', '', title).lower()
                    
                    score_tag = ""
                    for cat, score in scores.items():
                        if cat.lower() in match_title:
                            s100 = int(float(score) * 10)
                            score_tag = f' <span class="header-score" style="background:{get_score_color(score)}">SCORE: {s100}/100</span>'
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
                        <div class="score-value">{s100}%</div>
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
  :root {{ --primary: #000000; --accent: #666666; --background: #ffffff; --card: #ffffff; --text: #000000; --text-muted: #666666; }}
  body {{ font-family: 'Inter', sans-serif; line-height: 1.5; margin: 0; padding: 0; background: var(--background); color: var(--text); }}
  .container {{ max-width: 750px; margin: 0 auto; background: var(--card); padding: 40px; }}
  .header {{ border-bottom: 1px solid #000; margin-bottom: 30px; padding-bottom: 20px; }}
  .header h1 {{ font-family: 'Outfit', sans-serif; font-weight: 700; font-size: 24px; margin: 0; }}
  .header .target {{ font-size: 14px; color: var(--text-muted); margin-bottom: 5px; }}
  .score-dashboard {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 30px; padding: 20px 0; border-bottom: 1px solid #eee; }}
  .score-item {{ text-align: left; }}
  .score-value {{ font-size: 20px; font-weight: 700; }}
  .score-label {{ font-size: 10px; text-transform: uppercase; color: var(--text-muted); }}
  h2, h3 {{ font-family: 'Outfit', sans-serif; margin-top: 30px; }}
  h2 {{ font-size: 18px; border-bottom: 1px solid #eee; padding-bottom: 5px; }}
  h3 {{ font-size: 14px; margin-bottom: 10px; }}
  .report-body {{ font-size: 13px; }}
  ul {{ padding-left: 15px; }}
  li {{ margin-bottom: 5px; }}
  .footer {{ margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px; font-size: 10px; color: #999; text-align: center; }}
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="target">{name}</div>
      <h1>Website Audit Report</h1>
    </div>
    {score_dashboard}
    <div class="report-body">{safe_report}</div>
    <div class="footer">Generated by LeadStation AI  |  {generated_date}<br>&copy; 2024. Confidential Business Intelligence Report.</div>
  </div>
</body>
</html>"""

            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)

            # ── 2. Create Premium PDF Report via Playwright ──
            # This ensures the PDF looks EXACTLY like the HTML design
            try:
                pdf_path = os.path.join(folder_path, "audit_report.pdf")
                self._convert_html_to_pdf(html_path, pdf_path)
                print(f"[*] Pixel-Perfect PDF generated via Playwright: {pdf_path}")
            except Exception as e:
                print(f"[PLAYWRIGHT PDF ERROR] {e}. Falling back to basic PDF engine.")
                # FALLBACK: Basic ReportLab PDF if Playwright fails
                try:
                    from reportlab.lib.pagesizes import A4
                    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                    from reportlab.lib.units import mm
                    from reportlab.lib.colors import HexColor, white, slateblue, slategray
                    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table, TableStyle
                    from reportlab.lib.enums import TA_CENTER, TA_LEFT

                    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                        rightMargin=20*mm, leftMargin=20*mm, topMargin=20*mm, bottomMargin=20*mm)

                    styles = getSampleStyleSheet()
                    def T(name, **kw): return ParagraphStyle(name, parent=styles["Normal"], **kw)

                    # Professional Color Palette
                    PRIMARY = HexColor("#1e293b")
                    ACCENT = HexColor("#3b82f6")
                    TEXT = HexColor("#334155")
                    LIGHT = HexColor("#f1f5f9")

                    # Custom Styles
                    title_s = T("Ttl", fontSize=24, textColor=PRIMARY, fontName="Helvetica-Bold", leading=30)
                    sub_s = T("Sub", fontSize=10, textColor=ACCENT, fontName="Helvetica-Bold", spaceAfter=5, letterSpacing=1)
                    sec_s = T("Sec", fontSize=14, textColor=PRIMARY, fontName="Helvetica-Bold", spaceBefore=15, spaceAfter=10)
                    body_s = T("Bod", fontSize=10, textColor=TEXT, leading=15, spaceAfter=8)
                    bullet_s = T("Bul", fontSize=10, textColor=TEXT, leading=15, leftIndent=5*mm, spaceAfter=6)

                    story = []
                    
                    # Header
                    story.append(Paragraph(f"{name.upper()}", sub_s))
                    story.append(Paragraph("Website Intelligence Audit", title_s))
                    story.append(Spacer(1, 10))
                    story.append(HRFlowable(width="100%", thickness=1.5, color=LIGHT, spaceAfter=20))

                    # Score Grid
                    if scores:
                        data = []
                        row_lbl = []
                        row_val = []
                        for lbl, val in scores.items():
                            s100 = int(float(val) * 10)
                            row_lbl.append(Paragraph(lbl.upper(), T("L", fontSize=8, fontName="Helvetica-Bold", textColor=slategray)))
                            row_val.append(Paragraph(f"<b>{s100}%</b>", T("V", fontSize=16, fontName="Helvetica-Bold", textColor=PRIMARY)))
                        
                        data.append(row_lbl)
                        data.append(row_val)
                        
                        sc_table = Table(data, colWidths=[170 // len(scores) * mm] * len(scores))
                        sc_table.setStyle(TableStyle([
                            ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                            ("TOPPADDING", (0, 0), (-1, -1), 10),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                            ("LEFTPADDING", (0, 0), (-1, -1), 15),
                            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ]))
                        story.append(sc_table)
                        story.append(Spacer(1, 25))

                    clean_report = report_text.replace("&", "&amp;")
                    clean_report = re.sub(r"\|.*\|", "", clean_report) # Remove raw tables
                    clean_report = re.sub(r"[-]{3,}", "", clean_report)

                    for line in clean_report.split("\n"):
                        line = line.strip()
                        if not line: continue
                        
                        if line.startswith("## "):
                            title = line.replace("#", "").strip()
                            story.append(Spacer(1, 15))
                            # Add a bottom border to section titles
                            story.append(Paragraph(title, sec_s))
                            story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT, spaceAfter=10))
                        elif line.startswith("### "):
                            story.append(Paragraph(line.replace("#", "").strip(), T("H3", fontSize=12, textColor=ACCENT, fontName="Helvetica-Bold", spaceAfter=8)))
                        elif line.startswith("- ") or line.startswith("* "):
                            clean_line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line[2:])
                            story.append(Paragraph(f"• {clean_line}", bullet_s))
                        else:
                            clean_line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
                            story.append(Paragraph(clean_line, body_s))

                    story.append(Spacer(1, 30))
                    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT))
                    story.append(Paragraph(f"Generated by LeadStation AI  |  {generated_date}", T("Foot", fontSize=8, textColor=slategray, alignment=TA_CENTER, spaceBefore=10)))

                    doc.build(story)
                except Exception as ex:
                    print(f"[CRITICAL PDF FALLBACK ERROR] {ex}")

            rel = folder_path.replace("\\", "/").split("storage/")[-1]
            
            # Prefer PDF for the main return value as it's the professional standard
            pdf_path = os.path.join(folder_path, "audit_report.pdf")
            if os.path.exists(pdf_path):
                return f"/storage/{rel}/audit_report.pdf"
            
            html_path = os.path.join(folder_path, "audit_report.html")
            if os.path.exists(html_path):
                return f"/storage/{rel}/audit_report.html"
            
            return ""

        except Exception as e:
            print(f"[REPORT ERROR] {e}")
            return ""

    def _clean_ai_output(self, content: str) -> str:
        # Robust cleanup for AI conversational preamble and Markdown blocks
        if "```" in content:
            # Extract content between first ```html and last ``` (or just first ``` and last ```)
            matches = re.findall(r"```(?:html)?\s*([\s\S]*?)```", content, re.IGNORECASE)
            if matches:
                # Take the longest block as it's likely the full HTML
                content = max(matches, key=len).strip()
        
        # Secondary fallback: If still no <html> tag but starts with DOCTYPE
        if "<html" not in content.lower() and "<!doctype" in content.lower():
            content = content[content.lower().find("<!doctype"):]

        return content

    def generate_website(self, lead_data: Dict, user_prompt: str = "", model_id: str = "gemini-2.5-flash-preview-05-20") -> str:
        """Alias for generate_landing_page to support maps_scraper.py"""
        return self.generate_landing_page(lead_data, user_prompt, model_id)

    def generate_landing_page(self, lead_data: Dict, user_prompt: str = "", model_id: str = "gemini-2.5-flash-preview-05-20") -> str:
        """Generates a premium single-page HTML site using the specified model."""
        
        # ─── MASTER SYSTEM RULES (Hidden from User) ───────────────────
        system_rules = f"""
You are an ELITE Web Architect and UI/UX Designer. Build a WORLD-CLASS landing page for: {lead_data.get('name')}
Category: {lead_data.get('category')}
Analysis: {lead_data.get('ai_report', 'N/A')}

### MANDATORY DESIGN RULES (DO NOT IGNORE):
1. **DATA HARVESTING**: Use REAL data from the Analysis.
2. **INDUSTRY INTENT**: 
   - **Service/Medical**: Prioritize Trust, Service Grids, and 'Book Appointment'.
   - **Food/Cafe/Shop**: Prioritize 'Mouth-watering' visuals, Menus, and Location.
3. **ICONS**: Use FontAwesome 6 (fa-solid) ONLY.
4. **IMAGES**: Use LoremFlickr: https://loremflickr.com/800/600/[keyword] (Use hyphenated-words).
5. **UNIQUE DESIGN**: Pick a unique style: Minimalist, Dark Mode, Vibrant, or Corporate.
6. **NO CONVERSATION**: Return ONLY the code inside a single code block starting with ```html. Do not include any intro text.
7. **MAPS**: Embed a Google Maps iframe for: {lead_data.get('address') or lead_data.get('name')}.

Return ONLY the code inside a single code block. No explanations.
"""
        
        # Combine user instruction with system rules
        final_prompt = f"{system_rules}\n\nUSER SPECIFIC INSTRUCTIONS:\n{user_prompt.strip() if user_prompt else 'Create a high-conversion site based on the analysis report.'}"

        # Route to Gemini API (handles gemini-* and gemma-* models)
        if "gemini" in model_id.lower() or "gemma" in model_id.lower():
            if not self.gemini_key:
                raise Exception("Gemini API Key not configured. Please add GEMINI_API_KEY to your .env file.")
            
            try:
                # Only fall back to a known-good ID if a bare/generic or legacy string is passed.
                if model_id.lower() in ["gemini", "gemini-flash", "gemini-pro", "gemini-1.5-flash", "gemini-1.5-pro"]:
                    actual_model = "gemini-2.5-flash-preview-05-20"
                elif "gemini-1.5" in model_id.lower():
                    actual_model = "gemini-2.5-flash-preview-05-20"
                else:
                    actual_model = model_id
                
                # Debug: Log the incoming and resolved model
                print(f"[AI ROUTER] Incoming: '{model_id}' | Resolved: '{actual_model}'")

                # Re-configure to be absolutely sure
                genai.configure(api_key=self.gemini_key)
                model = genai.GenerativeModel(actual_model)
                
                # Add a safety setting to avoid being blocked by strict filters
                generation_config = {
                    "temperature": 0.7,
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 8192,
                }
                
                response = model.generate_content(final_prompt, generation_config=generation_config)
                
                if not response or not response.text:
                    raise Exception("Gemini returned an empty response. This usually means the prompt was blocked by safety filters.")
                
                return self._clean_ai_output(response.text)
            except Exception as e:
                # Log the full error to the console for the user to see
                print(f"[GEMINI ERROR] Model: {model_id} | Details: {str(e)}")
                raise Exception(f"Intelligence Glitch (Gemini): {str(e)}")

        # Route to DeepSeek
        else:
            if not self.client:
                raise Exception("DeepSeek API Key not configured. Please add DEEPSEEK_API_KEY to your .env file.")
            
            try:
                actual_model = "deepseek-reasoner" if "reasoner" in model_id.lower() else "deepseek-chat"
                completion = self.client.chat.completions.create(
                    model=actual_model,
                    messages=[{"role": "user", "content": final_prompt}]
                )
                content = completion.choices[0].message.content
                return self._clean_ai_output(content)
            except Exception as e:
                raise Exception(f"DeepSeek Error ({model_id}): {str(e)}")
