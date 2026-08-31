# -*- coding: utf-8 -*-
"""通过 GitHub Contents API 上传 top5-predictor 全部代码到仓库（绕过被限的 git 协议）
token 从环境变量 GH_TOKEN 或项目 .env 读取（勿硬编码，PAT 被吊销会 401）"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import urllib.error

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


def load_token():
    t = os.environ.get('GH_TOKEN', '')
    if t:
        return t
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('GH_TOKEN='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    return ''


TOKEN = load_token()
if not TOKEN:
    print("❌ 未配置 GH_TOKEN（环境变量或 .env）")
    sys.exit(1)
REPO = "maoyuxuan897-beep/football-predictor"
BASE = r"C:\Users\ASUS\WorkBuddy\2026-08-29-20-32-59\top5-predictor"
API = f"https://api.github.com/repos/{REPO}/contents"


def get_file_sha(url):
    """查询远端文件当前 sha（存在返回 sha，不存在返回 None）"""
    req = urllib.request.Request(url, headers={"Authorization": f"token {TOKEN}",
                                               "Accept": "application/vnd.github+json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp).get('sha')
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        return None  # 其他错误按不存在处理，让 PUT 尝试创建
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

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
    url = API + '/' + '/'.join(urllib.parse.quote(p) for p in rel.split('/'))
    body = {
        "message": f"upload {rel}",
        "content": content,
        "branch": "main"
    }
    # GitHub Contents API 更新已存在文件必须携带当前 sha（422 缺 sha 即此原因）
    sha = get_file_sha(url)
    if sha:
        body["sha"] = sha
    body_enc = json.dumps(body).encode()
    req = urllib.request.Request(url, data=body_enc,
                                 headers={"Authorization": f"token {TOKEN}",
                                          "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json"},
                                 method="PUT")
    ok = False
    for attempt in range(4):  # 国内访问 GitHub API 偶发 TLS 重置，重试
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            json.load(resp)
            ok = True
            break
        except urllib.error.HTTPError as e:
            if e.code == 422:
                # 更新已存在文件缺少/过期 sha：重新获取后重试一次
                new_sha = get_file_sha(url)
                if new_sha:
                    body['sha'] = new_sha
                    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                                 headers={"Authorization": f"token {TOKEN}",
                                                          "Accept": "application/vnd.github+json",
                                                          "Content-Type": "application/json"},
                                                 method="PUT")
                    continue
            msg = e.read().decode('utf-8', 'ignore')[:150]
            failed.append((rel, f"HTTP {e.code}: {msg}"))
            print(f"  ✗ {rel}: HTTP {e.code}")
            break  # HTTP 状态错误不重试
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  ~ {rel} 网络错误({type(e).__name__}), 重试 {attempt+1}/4...")
            time.sleep(4)
    if ok:
        uploaded += 1
        print(f"  ✓ {rel}")

print(f"\n完成: 成功 {uploaded} / 失败 {len(failed)}")
for rel, err in failed:
    print(f"  ✗ {rel}: {err}")
