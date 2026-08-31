# -*- coding: utf-8 -*-
"""配置 GitHub Actions Secret + 开启 Pages + 触发 workflow"""
import base64
import json
import sys
import time
import urllib.request
import urllib.error

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from nacl import encoding, public

TOKEN = "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"
REPO = "maoyuxuan897-beep/football-predictor"
FOOTBALL_DATA_KEY = "f1310a00ba7b4e8fb5d240cdcd10b38a"
API = f"https://api.github.com/repos/{REPO}"


def api(method, path, body=None):
    url = API + path if path.startswith('/') else API + '/' + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Authorization": f"token {TOKEN}",
                                          "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json"},
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r) if r.status != 204 else {}
    except urllib.error.HTTPError as e:
        print(f"  ❌ {method} {path} → HTTP {e.code}: {e.read().decode('utf-8','ignore')[:200]}")
        raise


# 1) 配置 Secret FOOTBALL_DATA_KEY（用仓库公钥加密）
print("=== 1/3 配置 Actions Secret ===")
pub = api('GET', '/actions/secrets/public-key')
sealed = public.SealedBox(public.PublicKey(pub['key'], encoding.Base64Encoder()))
encrypted = sealed.encrypt(FOOTBALL_DATA_KEY.encode())
api('PUT', '/actions/secrets/FOOTBALL_DATA_KEY',
    {"encrypted_value": base64.b64encode(encrypted).decode(), "key_id": pub['key_id']})
print("  ✅ Secret FOOTBALL_DATA_KEY 已配置")

# 2) 开启 GitHub Pages（gh-pages 分支）
print("=== 2/3 开启 GitHub Pages ===")
try:
    api('POST', '/pages', {"source": {"branch": "gh-pages", "path": "/"}})
    print("  ✅ Pages 已开启（gh-pages 分支）")
except Exception:
    # 可能已存在，用 PUT 更新
    try:
        api('PUT', '/pages', {"source": {"branch": "gh-pages", "path": "/"}})
        print("  ✅ Pages 配置已更新")
    except Exception as e:
        print(f"  ⚠ Pages 配置需手动检查: {e}")

# 3) 触发 workflow
print("=== 3/3 触发每日更新 workflow ===")
try:
    api('POST', '/actions/workflows/daily.yml/dispatches', {"ref": "main"})
    print("  ✅ 已触发，等待运行...")
except Exception as e:
    print(f"  ⚠ 触发失败: {e}")

print("\n完成。可访问 https://github.com/maoyuxuan897-beep/football-predictor/actions 查看运行状态")
