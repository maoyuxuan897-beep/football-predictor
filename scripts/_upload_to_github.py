# -*- coding: utf-8 -*-
"""通过 GitHub Contents API 上传 top5-predictor 全部代码到仓库（绕过被限的 git 协议）"""
import base64
import json
import os
import subprocess
import sys
import urllib.request

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

TOKEN = "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"
REPO = "maoyuxuan897-beep/football-predictor"
BASE = r"C:\Users\ASUS\WorkBuddy\2026-08-29-20-32-59\top5-predictor"
API = f"https://api.github.com/repos/{REPO}/contents"

# 用 git ls-files 获取应上传的文件（已被 .gitignore 过滤）
r = subprocess.run(['git', 'ls-files'], cwd=BASE, capture_output=True, text=True, encoding='utf-8')
files = [f for f in r.stdout.splitlines() if f.strip()]
print(f"待上传 {len(files)} 个文件")

uploaded = 0
failed = []
for rel in files:
    abs_path = os.path.join(BASE, rel.replace('/', os.sep))
    if not os.path.exists(abs_path):
        failed.append((rel, '本地文件不存在'))
        continue
    try:
        with open(abs_path, 'rb') as f:
            content = base64.b64encode(f.read()).decode()
    except OSError as e:
        failed.append((rel, str(e)))
        continue
    body = json.dumps({
        "message": f"upload {rel}",
        "content": content,
        "branch": "main"
    }).encode()
    url = API + '/' + '/'.join(urllib.parse.quote(p) for p in rel.split('/'))
    req = urllib.request.Request(url, data=body,
                                 headers={"Authorization": f"token {TOKEN}",
                                          "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json"},
                                 method="PUT")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        json.load(resp)
        uploaded += 1
        print(f"  ✓ {rel}")
    except urllib.error.HTTPError as e:
        msg = e.read().decode('utf-8', 'ignore')[:150]
        failed.append((rel, f"HTTP {e.code}: {msg}"))
        print(f"  ✗ {rel}: HTTP {e.code}")

print(f"\n完成: 成功 {uploaded} / 失败 {len(failed)}")
for rel, err in failed:
    print(f"  ✗ {rel}: {err}")
