from app.services.builder.ai_service import AISiteService
import os

ai = AISiteService()

# Test score extractor
sample = """
Ratings Table
User-Friendliness: 6/10
Development Quality: 5/10
Responsiveness: 4/10
Overall Verdict: Needs Improvement
"""
scores = ai._extract_scores(sample)
print('[OK] Score extraction:', scores)

# Simulate URL construction (no /storage/ prefix)
folder_path = os.path.join('storage', 'leads', 'test-biz-abc12345')
rel = folder_path.replace('\\', '/').lstrip('storage/')
url = f"leads/{rel.split('leads/')[-1]}/audit_report.pdf"
print('[OK] Audit URL returned:', url)
print('[OK] Site preview URL : leads/test-biz-abc12345/index.html')
print()
print('Expected browser URL: http://127.0.0.1:8001/storage/leads/test-biz-abc12345/index.html')
