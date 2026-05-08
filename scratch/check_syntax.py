import ast
import sys

file_path = r'c:\Users\zarmi\Downloads\leadgenbackend.onlinetoolpot.com.v2\app\services\builder\ai_service.py'

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        source = f.read()
    ast.parse(source)
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax Error: {e.msg}")
    print(f"Line: {e.lineno}, Offset: {e.offset}")
    if e.text:
        print(f"Text: {e.text.strip()}")
except Exception as e:
    print(f"Error: {e}")
