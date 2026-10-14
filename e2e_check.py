# -*- coding: utf-8 -*-
"""对真实运行中的服务做端到端验证，测完删掉，保证净零改动"""
import io
import json
import sqlite3
import sys
import urllib.request

import requests

BASE = 'http://127.0.0.1:5800'
S = requests.Session()
S.trust_env = False          # 绕过系统代理
S.proxies = {'http': None, 'https': None}

ok = True


def ck(name, cond, extra=''):
    global ok
    if not cond:
        ok = False
    print(('  OK  ' if cond else ' FAIL ') + name + ((' ' + extra) if extra else ''))


DBF = sys.argv[1] if len(sys.argv) > 1 else 'data/dogplat.db'
conn = sqlite3.connect(DBF)
conn.row_factory = sqlite3.Row


def counts():
    d = conn.execute('SELECT COUNT(*) c FROM dog_diary').fetchone()['c']
    m = conn.execute('SELECT COUNT(*) c FROM diary_media').fetchone()['c']
    e = conn.execute('SELECT COUNT(*) c FROM dog_expense').fetchone()['c']
    return d, m, e


before = counts()
print(f'起始：日记 {before[0]} / 媒体 {before[1]} / 记账 {before[2]}')

print('--- 页面可访问 ---')
for p in ['/', '/dogs', '/dog/1/today', '/dog/1/diary', '/dog/1/expense',
          '/dog/1/profile', '/dog/2/profile']:
    try:
        r = S.get(BASE + p, timeout=15)
        ck(f'GET {p}', r.status_code == 200, str(r.status_code))
    except Exception as ex:
        ck(f'GET {p}', False, repr(ex))

print('--- 记账：新增 → 统计 → 删除 ---')
r = S.post(BASE + '/api/expense', json={
    'dog_id': 1, 'day': '2026-10-14', 'category': '用品', 'item': 'E2E 测试用品',
    'amount': 12.34, 'shop': 'E2E店', 'pay_method': '微信'}, timeout=15)
j = r.json()
ck('新增记账', r.status_code == 200 and j.get('ok'), json.dumps(j.get('summary', {}), ensure_ascii=False)[:120])
new_id = None
row = conn.execute('SELECT id FROM dog_expense WHERE item="E2E 测试用品"').fetchone()
new_id = row['id'] if row else None
ck('落库可查', new_id is not None, f'id={new_id}')

r = S.get(BASE + '/dog/1/expense?q=E2E', timeout=15)
ck('筛选页含新记录', r.status_code == 200 and 'E2E 测试用品' in r.text)

r = S.get(BASE + '/dog/1/expense.csv', timeout=15)
ck('CSV 导出', r.status_code == 200 and 'text/csv' in r.headers.get('Content-Type', '')
   and '合计' in r.text, r.headers.get('Content-Type', ''))

if new_id:
    r = S.post(BASE + '/api/expense/delete', json={'id': new_id}, timeout=15)
    ck('删除记账', r.status_code == 200 and r.json().get('ok'))

print('--- 日记：上传图片 → 读取缩略图 → 删除 ---')
from PIL import Image
buf = io.BytesIO()
Image.new('RGB', (1000, 700), (224, 123, 57)).save(buf, 'JPEG')
buf.seek(0)
r = S.post(BASE + '/dog/1/diary/new',
           data={'day': '2026-10-14', 'title': 'E2E 日记', 'content': '端到端验证\n第二行',
                 'mood': '开心', 'place': 'E2E'},
           files=[('files', ('e2e.jpg', buf, 'image/jpeg'))],
           timeout=30, allow_redirects=True)
ck('上传日记+图片', r.status_code == 200 and 'E2E 日记' in r.text, str(r.status_code))

er = conn.execute('SELECT * FROM dog_diary WHERE title="E2E 日记" ORDER BY id DESC LIMIT 1').fetchone()
eid = er['id'] if er else None
mr = conn.execute('SELECT * FROM diary_media WHERE diary_id=?', (eid,)).fetchone() if eid else None
ck('日记入库', eid is not None, f'id={eid}')
ck('媒体入库', mr is not None, f'kind={mr["kind"] if mr else None} thumb={bool(mr and mr["thumb"])}')

if mr:
    rr = S.get(BASE + '/media/' + mr['thumb'], timeout=15)
    ck('缩略图可访问', rr.status_code == 200 and rr.headers.get('Content-Type', '').startswith('image/'),
       f'{rr.status_code} {rr.headers.get("Content-Type")} {len(rr.content)}B')
    rr = S.get(BASE + '/media/' + mr['path'], timeout=15)
    ck('原图可访问', rr.status_code == 200, f'{rr.status_code} {len(rr.content)}B')

# 直接访问一个不存在的媒体
rr = S.get(BASE + '/media/diary/1/197001/deadbeef.jpg', timeout=15)
ck('不存在的媒体 -> 404', rr.status_code == 404, str(rr.status_code))

if eid:
    r = S.post(BASE + f'/dog/1/diary/{eid}/delete', timeout=15, allow_redirects=True)
    ck('删除日记', r.status_code == 200)

after = counts()
print(f'结束：日记 {after[0]} / 媒体 {after[1]} / 记账 {after[2]}')
ck('净零改动', before == after, f'{before} -> {after}')

conn.close()
print()
print('E2E 通过 ✅' if ok else 'E2E 存在失败 ❌')
sys.exit(0 if ok else 1)
