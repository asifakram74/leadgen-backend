import os
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from typing import Dict, Optional

class AISiteService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def analyze_website(self, url: str, business_info: Dict) -> Dict:
        """
        Analyzes a website to see if it's 'Healthy' or has 'Issues'.
        Returns a dict with 'status' and 'reason'.
        """
        if not self.client:
            return {"status": "Analysis Unavailable (Set API Key)", "reason": "No API Key"}

        try:
            # 1. Fetch basic page content
            response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if response.status_code != 200:
                return {"status": "Issues", "reason": f"Website unreachable (Status {response.status_code})"}

            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract basic data for AI
            title = soup.title.string if soup.title else "No Title"
            meta_desc = ""
            desc_tag = soup.find("meta", attrs={"name": "description"})
            if desc_tag:
                meta_desc = desc_tag.get("content", "")

            # Get a sample of the body text
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            clean_text = '\n'.join(chunk for chunk in chunks if chunk)[:2000]

            # 2. Ask AI to analyze
            prompt = f"""
            Analyze this business website for a {business_info.get('category', 'business')}.
            Business Name: {business_info.get('name', 'Unknown')}
            URL: {url}
            Page Title: {title}
            Meta Description: {meta_desc}
            
            Website Content Sample:
            {clean_text}
            
            TASK: Is this website professional, modern, and high-converting?
            CRITERIA for 'Issues':
            - Looks dated or broken.
            - Low text content or generic "Under Construction".
            - Mismatched name or category.
            - Hard to read on mobile (implied from structure).
            
            Reply in JSON format:
            {{
                "is_healthy": true/false,
                "reason": "short explanation",
                "score": 1-10
            }}
            """

            completion = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": "You are a professional web auditor."}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )

            import json
            analysis = json.loads(completion.choices[0].message.content)
            
            return {
                "status": "Healthy" if analysis.get("is_healthy") else "Issues",
                "reason": analysis.get("reason"),
                "score": analysis.get("score")
            }

        except Exception as e:
            return {"status": "Analysis Error", "reason": str(e)}

    def generate_landing_page(self, lead_data: Dict) -> str:
        """
        Generates a premium single-page HTML/Tailwind site based on lead data.
        """
        if not self.client:
            return "<h1>AI Generation Unavailable</h1><p>Please provide an OpenAI API Key.</p>"

        prompt = f"""
        Generate a premium, modern single-page website for this lead:
        Name: {lead_data.get('name')}
        Category: {lead_data.get('category')}
        Address: {lead_data.get('address')}
        Phone: {lead_data.get('phone')}
        Email: {lead_data.get('email', 'Contact us')}
        Rating: {lead_data.get('rating')} ({lead_data.get('reviews')} reviews)
        
        Style Requirements:
        - Use Tailwind CSS via CDN.
        - Dark/Premium theme or category-matching color palette (e.g., Gold/Black for Salon).
        - Modern typography (Inter/Roboto).
        - Sections: Hero, Services, About, Contact, Map Placeholder.
        - Fully responsive.
        - High-quality SVG icons from Lucide/FontAwesome.
        
        Output ONLY the raw HTML code starting with <!DOCTYPE html>.
        """

        completion = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": "You are a world-class web developer creating conversion-optimized landing pages."}, {"role": "user", "content": prompt}]
        )

        return completion.choices[0].message.content
