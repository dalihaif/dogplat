# -*- coding: utf-8 -*-
"""自检脚本：跑一遍所有页面与接口，确认没有 500。
用法：python selftest.py
默认跑在临时库 + 临时上传目录上，**不碰真实数据**（可用 DOGPLAT_DB 覆盖）
"""
import glob
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import date, timedelta

# 必须在 import app 之前设好：隔离库文件与上传目录
_TMP = tempfile.mkdtemp(prefix='dogplat_selftest_')
os.environ.setdefault('DOGPLAT_DB', os.path.join(_TMP, 'selftest.db'))
os.environ.setdefault('DOGPLAT_UPLOADS', os.path.join(_TMP, 'uploads'))

import app as A          # noqa: E402
import db as DB          # noqa: E402

A.ensure_init()
c = A.app.test_client()

ok = True


def check(name, resp, expect=200):
    global ok
    good = resp.status_code == expect
    if not good:
        ok = False
    print(('  OK  ' if good else ' FAIL ') + f'{name:32s} {resp.status_code}')
    if not good:
        body = resp.get_data(as_text=True)
        print(body[:2000])


print('--- 1. 登记狗狗 ---')
birth = (date.today() - timedelta(days=95)).isoformat()   # 约 3 个月
r = c.post('/dogs/new', data={
    'name': '旺财', 'breed_cn': '金毛寻回犬', 'breed_en': 'Golden Retriever',
    'sex': '公', 'birth_date': birth, 'arrive_date': date.today().isoformat(),
    'weight_current': '7.5', 'neutered': '未绝育', 'chip_no': 'CN123456789',
    'owner_name': '李海峰', 'owner_phone': '13900000000',
    'personality_tags': '亲人、兴奋度高',
}, follow_redirects=True)
check('POST /dogs/new', r)

# 取 dog id
conn = A.DB.connect()
dog = conn.execute('SELECT * FROM dogs ORDER BY id DESC LIMIT 1').fetchone()
dog = dict(dog)
conn.close()
did = dog['id']
print(f'  狗狗 id={did} 出生={dog["birth_date"]} 月龄={A.biz.age_text(dog["birth_date"])}')

print('--- 2. 页面 ---')
for path, name, exp in [
    ('/', '总览', 200),
    ('/dogs', '档案列表', 200),
    (f'/dogs/{did}/edit', '编辑档案', 200),
    (f'/dog/{did}', '工作台跳转', 302),
    (f'/dog/{did}/today', '今日待办', 200),
    (f'/dog/{did}/train', '训练', 200),
    (f'/dog/{did}/health', '饮食健康', 200),
    (f'/dog/{did}/weekly', '周报 7 天', 200),
    (f'/dog/{did}/weekly?days=30', '周报 30 天', 200),
    (f'/dog/{did}/profile', '档案与免疫', 200),
    (f'/dog/{did}/diary', '狗狗日记', 200),
    (f'/dog/{did}/expense', '狗狗记账', 200),
    ('/knowledge', '知识库', 200),
    ('/knowledge?q=疫苗', '知识库搜索', 200),
    ('/knowledge?cat=训练', '知识库分类', 200),
    ('/about', '关于', 200),
    ('/fetch', '联网检索页', 200),
    ('/manifest.webmanifest', 'PWA manifest', 200),
    ('/sw.js', 'PWA ServiceWorker', 200),
    ('/static/icon-192.png', 'PWA 图标', 200),
    ('/no-such-page', '404', 404),
]:
    check(name, c.get(path), exp)

print('--- 3. 打卡接口 ---')
today = date.today().isoformat()


def ck(kind, data, time_s='08:00'):
    return c.post('/api/checkin', json={
        'dog_id': did, 'type': kind, 'day': today, 'time': time_s, 'data': data})


check('打卡·喂食', ck('feed', {'amount': 60, 'eaten': 58, 'food': '皇家幼犬粮'}, '08:00'))
check('打卡·便便(理想)', ck('potty', {'kind': '便', 'success': True, 'score': 3,
                                 'location': '阳台尿垫', 'trigger': '餐后'}, '08:20'))
check('打卡·便便(糊状)', ck('potty', {'kind': '便', 'success': True, 'score': 6,
                                 'location': '阳台尿垫', 'trigger': '餐后'}, '13:20'))
check('打卡·便便(糊状2)', ck('potty', {'kind': '便', 'success': False, 'score': 6,
                                  'location': '客厅', 'trigger': '玩耍后'}, '18:20'))
check('打卡·训练', ck('train', {'command': '坐', 'minutes': 5, 'env': '室内',
                               'distraction': 2, 'success': 4, 'total': 5,
                               'reward': '鸡肉粒'}, '09:00'))
check('打卡·体重', ck('weight', {'kg': 7.6}, '07:00'))
check('打卡·饮水', ck('water', {'ml': 250}, '10:00'))

r = ck('potty', {'kind': '便', 'success': False, 'score': 6, 'blood': False})
j = r.get_json()
print(f'  预警条数：{len(j["alerts"])}')
for a in j['alerts']:
    print(f'    [{a["level"]}] {a["title"]} → {a["action"]}')

print('--- 4. 健康记录 ---')
r = c.post('/api/health_record', data={
    'dog_id': did, 'kind': '首针多联', 'happen_date': date.today().isoformat(),
    'next_due': (date.today() + timedelta(days=21)).isoformat(),
    'vet': 'XX 宠物医院', 'dose_no': '第 1 针'}, follow_redirects=True)
check('POST 疫苗登记', r)

print('--- 5. 各页面二次渲染（有数据后） ---')
for path, name in [
    ('/', '总览(有数据)'),
    (f'/dog/{did}/today', '今日待办(有记录)'),
    (f'/dog/{did}/train', '训练(有记录)'),
    (f'/dog/{did}/health', '健康(有记录)'),
    (f'/dog/{did}/weekly', '周报(有数据)'),
    (f'/dog/{did}/profile', '档案(有记录)'),
    (f'/dog/{did}/diary', '日记(有数据)'),
    (f'/dog/{did}/expense', '记账(有数据)'),
]:
    check(name, c.get(path))

print('--- 5b. 联网检索流程（联网操作，可能较慢） ---')
import search as S
rows, err = S.search_web('幼犬 疫苗', 'auto', 6)
print(f'  搜索「幼犬 疫苗」：{len(rows)} 条', ('| ' + err) if err else '')
urls = [r['url'] for r in rows if not r['blocked']][:2]
if urls:
    cands, rep = S.fetch_and_extract(urls, per_page=3)
    print(f'  抓取 {len(rep)} 篇，提取 {len(cands)} 条候选')
    check('POST /fetch/extract', c.post('/fetch/extract', data={'query': '幼犬 疫苗', 'url': urls}))
    if cands:
        check('POST /fetch/save',
              c.post('/fetch/save', data={'idx': [0]}, follow_redirects=True))
        n = A.DB.connect().execute(
            'SELECT COUNT(*) c FROM knowledge WHERE source=?',
            (cands[0]['source'],)).fetchone()['c']
        print(f'  入库验证：source={cands[0]["source"]} 的条目数 = {n}')
else:
    print('  联网不可用，跳过抓取测试')

print('--- 5c. 记录管理：列表 / 编辑 / 删除 ---')
for q in ['', '?type=feed', '?type=train', '?type=potty', '?page=2',
          f'?from={birth}&to={today}', '?q=鸡肉', '?type=feed&page=1']:
    check(f'GET /dog/{did}/records{q}', c.get(f'/dog/{did}/records{q}'))

conn = A.DB.connect()
row = conn.execute(
    "SELECT id FROM care_events WHERE dog_id=? AND type='feed' ORDER BY id LIMIT 1",
    (did,)).fetchone()
conn.close()
fid = row['id']
r = c.post('/api/event/update', json={
    'id': fid, 'type': 'feed', 'day': today, 'time': '08:05', 'note': '改成 08:05 了',
    'data': {'amount': 70, 'eaten': 70, 'food': '皇家幼犬粮（改）'}})
check('POST /api/event/update', r, 200)
conn = A.DB.connect()
row = dict(conn.execute('SELECT * FROM care_events WHERE id=?', (fid,)).fetchone())
conn.close()
ok2 = (row['time'] == '08:05' and row['note'] == '改成 08:05 了'
       and json.loads(row['payload'])['amount'] == 70)
print(('  OK  ' if ok2 else ' FAIL ') + f'编辑已生效：time={row["time"]} note={row["note"]} '
      f'amount={json.loads(row["payload"])["amount"]}')
if not ok2:
    ok = False

# 体重回写：加两条（用未来日期确保是最新的）→ 档案取最新 → 删最新 → 回落到前一条
fw1 = (date.today() + timedelta(days=100)).isoformat()
fw2 = (date.today() + timedelta(days=107)).isoformat()
c.post('/api/checkin', json={'dog_id': did, 'type': 'weight', 'day': fw1,
                            'time': '07:00', 'data': {'kg': 5.0}})
c.post('/api/checkin', json={'dog_id': did, 'type': 'weight', 'day': fw2,
                            'time': '07:00', 'data': {'kg': 6.2}})
conn = A.DB.connect()
w = dict(conn.execute('SELECT weight_current FROM dogs WHERE id=?', (did,)).fetchone())
wid = conn.execute("SELECT id FROM care_events WHERE dog_id=? AND type='weight'"
                   " ORDER BY day DESC, time DESC LIMIT 1", (did,)).fetchone()['id']
conn.close()
print(f'  两条体重后档案体重 = {w["weight_current"]}（应为 6.2）')
c.post('/api/event/delete', json={'id': wid})
conn = A.DB.connect()
w2 = dict(conn.execute('SELECT weight_current FROM dogs WHERE id=?', (did,)).fetchone())
conn.close()
print(f'  删掉最新体重后档案体重 = {w2["weight_current"]}（应回落到 5.0）')
if w['weight_current'] != 6.2 or w2['weight_current'] != 5.0:
    print('  FAIL 体重回写不同步')
    ok = False

# 删除一条训练记录
conn = A.DB.connect()
tid = conn.execute("SELECT id FROM care_events WHERE dog_id=? AND type='train' LIMIT 1",
                   (did,)).fetchone()
conn.close()
if tid:
    check('POST /api/event/delete', c.post('/api/event/delete', json={'id': tid['id']}), 200)
    conn = A.DB.connect()
    gone = conn.execute('SELECT 1 FROM care_events WHERE id=?', (tid['id'],)).fetchone()
    conn.close()
    print(('  OK  ' if not gone else ' FAIL ') + '删除后记录已不存在')
    if gone:
        ok = False

# 免疫记录编辑
conn = A.DB.connect()
hid = conn.execute("SELECT id FROM health_records WHERE dog_id=? LIMIT 1", (did,)).fetchone()
conn.close()
if hid:
    check('POST /api/health_record/update', c.post('/api/health_record/update', json={
        'id': hid['id'], 'kind': '首针多联', 'dose_no': '第 1 针（改）',
        'happen_date': today, 'next_due': today, 'vet': '改过的医院', 'note': '改过'}), 200)
    conn = A.DB.connect()
    hr = dict(conn.execute('SELECT * FROM health_records WHERE id=?', (hid['id'],)).fetchone())
    conn.close()
    hr_ok = hr['vet'] == '改过的医院'
    print(('  OK  ' if hr_ok else ' FAIL ') + f'免疫记录已改：vet={hr["vet"]}')
    if not hr_ok:
        ok = False

print('--- 5d. 狗狗状态 + 父母信息 ---')
r = c.post('/dogs/new', data={
    'name': '小黑', 'breed_cn': '中华田园犬', 'sex': '母',
    'birth_date': birth, 'arrive_date': today, 'weight_current': '4.2',
    'status': '在养', 'status_note': '建档',
    'sire_name': '大黄', 'sire_breed': '中华田园犬', 'sire_chip': 'CN7770001',
    'dam_name': '小白', 'dam_breed': '中华田园犬', 'dam_chip': 'CN7770002',
    'parents_note': '同窝 3 只',
}, follow_redirects=True)
check('POST /dogs/new（带父母信息）', r)

conn = A.DB.connect()
nd = dict(conn.execute("SELECT * FROM dogs WHERE name='小黑'").fetchone())
conn.close()
p_ok = (nd['sire_name'] == '大黄' and nd['dam_name'] == '小白'
        and nd['sire_chip'] == 'CN7770001' and nd['parents_note'] == '同窝 3 只'
        and nd['status'] == '在养')
print(('  OK  ' if p_ok else ' FAIL ')
      + f"父母信息已存：父={nd['sire_name']}/{nd['sire_chip']} 母={nd['dam_name']}/{nd['dam_chip']} "
        f"状态={nd['status']}")
if not p_ok:
    ok = False
did2 = nd['id']

for s in ['在养', '送人', '死亡', '走失', '其他']:
    check(f'GET /dogs?status={s}', c.get(f'/dogs?status={s}'))

# 改状态：应写入 status_changed_at 并留一条流水
r = c.post('/api/dog/status', json={'dog_id': did2, 'status': '送人',
                                   'note': '2026-10-20 送给表姐家'})
check('POST /api/dog/status', r)
conn = A.DB.connect()
nd2 = dict(conn.execute('SELECT * FROM dogs WHERE id=?', (did2,)).fetchone())
log1 = [dict(x) for x in conn.execute(
    'SELECT * FROM dog_status_log WHERE dog_id=? ORDER BY id', (did2,)).fetchall()]
conn.close()
s_ok = (nd2['status'] == '送人' and nd2['active'] == 0 and nd2['status_changed_at']
        and len(log1) == 1 and log1[0]['old_status'] == '在养'
        and log1[0]['new_status'] == '送人' and '表姐' in log1[0]['note'])
print(('  OK  ' if s_ok else ' FAIL ')
      + f"状态改为「{nd2['status']}」active={nd2['active']} 变更时间={nd2['status_changed_at']}")
print(f'       变更流水：{log1[0]["old_status"]} → {log1[0]["new_status"]}'
      f' 说明={log1[0]["note"]} 时间={log1[0]["changed_at"]}')
if not s_ok:
    ok = False

# 非在养 → 不再产生喂养/免疫预警
conn = A.DB.connect()
nd3 = dict(conn.execute('SELECT * FROM dogs WHERE id=?', (did2,)).fetchone())
al = A.biz.alerts_for(conn, nd3)
conn.close()
print(('  OK  ' if not al else ' FAIL ') + f'非在养预警条数 = {len(al)}（应为 0）')
if al:
    ok = False

# 总览页应把非在养狗狗放到下面
check('GET / （含非在养分组）', c.get('/'))
check(f'GET /dog/{did2}/profile（含变更历史）', c.get(f'/dog/{did2}/profile'))

# 重复设同一状态：不写流水
res2 = c.post('/api/dog/status', json={'dog_id': did2, 'status': '送人'}).get_json()
conn = A.DB.connect()
n_log = conn.execute('SELECT COUNT(*) c FROM dog_status_log WHERE dog_id=?',
                     (did2,)).fetchone()['c']
conn.close()
dup_ok = (res2.get('changed') is False and n_log == 1)
print(('  OK  ' if dup_ok else ' FAIL ')
      + f'重复设同状态：changed={res2.get("changed")} 流水条数={n_log}（应 False / 1）')
if not dup_ok:
    ok = False

# 改回在养 → 第 2 条流水
c.post('/api/dog/status', json={'dog_id': did2, 'status': '在养', 'note': '又抱回来了'})
conn = A.DB.connect()
n_log2 = conn.execute('SELECT COUNT(*) c FROM dog_status_log WHERE dog_id=?',
                      (did2,)).fetchone()['c']
back = dict(conn.execute('SELECT status, active FROM dogs WHERE id=?', (did2,)).fetchone())
conn.close()
back_ok = (n_log2 == 2 and back['status'] == '在养' and back['active'] == 1)
print(('  OK  ' if back_ok else ' FAIL ')
      + f'改回在养：流水={n_log2} 条 status={back["status"]} active={back["active"]}')
if not back_ok:
    ok = False

# 非法入参
r_bad = c.post('/api/dog/status', json={'dog_id': did2, 'status': '跑路了'})
r_miss = c.post('/api/dog/status', json={'status': '在养'})
r_404 = c.post('/api/dog/status', json={'dog_id': 999999, 'status': '在养'})
print(f'  非法状态 -> {r_bad.status_code} {r_bad.get_json().get("error")}')
print(f'  缺 dog_id -> {r_miss.status_code} {r_miss.get_json().get("error")}')
print(f'  狗狗不存在 -> {r_404.status_code} {r_404.get_json().get("error")}')
if (r_bad.status_code, r_miss.status_code, r_404.status_code) != (400, 400, 404):
    print('  FAIL 边界状态码不对')
    ok = False

print('--- 5e. 老库迁移（旧 active 标记 → 新 status） ---')
legacy = os.path.join(DB.DATA_DIR, '_legacy_test.db')
if os.path.exists(legacy):
    os.remove(legacy)
lc = sqlite3.connect(legacy)
lc.row_factory = sqlite3.Row
lc.executescript(
    "CREATE TABLE dogs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, breed_cn TEXT,"
    " sex TEXT, birth_date TEXT, note TEXT, active INTEGER DEFAULT 1, created_at TEXT);"
    "INSERT INTO dogs (name, breed_cn, active, created_at) VALUES ('老狗甲','土狗',1,'2025-01-01');"
    "INSERT INTO dogs (name, breed_cn, active, created_at) VALUES ('老狗乙','土狗',0,'2025-01-02');")
lc.commit()
# 复刻 init_db 的升级路径：先补建缺的表，再补列 + 回填
lc.executescript(DB.SCHEMA)
DB.migrate(lc)
rows = {r['name']: dict(r) for r in lc.execute('SELECT * FROM dogs')}
logs = [dict(r) for r in lc.execute('SELECT * FROM dog_status_log')]
m1 = (rows['老狗甲']['status'] == '在养' and rows['老狗乙']['status'] == '其他' and len(logs) == 2)
print(('  OK  ' if m1 else ' FAIL ')
      + f"active=1 → {rows['老狗甲']['status']}，active=0 → {rows['老狗乙']['status']}，"
        f"迁移流水 {len(logs)} 条")
if not m1:
    ok = False
# 幂等：再跑一遍不应重复写流水
lc.executescript(DB.SCHEMA)
DB.migrate(lc)
n2 = lc.execute('SELECT COUNT(*) c FROM dog_status_log').fetchone()['c']
cols = {r[1] for r in lc.execute('PRAGMA table_info(dogs)')}
need = {'status', 'status_changed_at', 'sire_name', 'sire_breed', 'sire_chip',
        'dam_name', 'dam_breed', 'dam_chip', 'parents_note'}
m2 = (n2 == 2 and need <= cols)
print(('  OK  ' if m2 else ' FAIL ')
      + f'重复迁移幂等：流水仍 {n2} 条，新列齐全 {"是" if need <= cols else "否"}')
if not m2:
    ok = False
lc.close()

# 迁移前应自动备份
baks = glob.glob(legacy + '.bak_before_migrate_*')
print(('  OK  ' if len(baks) == 1 else ' FAIL ')
      + f'升级前自动备份：{len(baks)} 份（应为 1）')
if len(baks) != 1:
    ok = False
for b in baks:
    os.remove(b)
os.remove(legacy)

print('--- 5f. 狗狗日记（含图片/视频上传） ---')
from io import BytesIO                    # noqa: E402


def _img_bytes(color, size=(800, 600), fmt='JPEG'):
    from PIL import Image
    b = BytesIO()
    Image.new('RGB', size, color).save(b, fmt)
    b.seek(0)
    return b


r = c.post(f'/dog/{did}/diary/new',
           data={'day': date.today().isoformat(), 'title': '自检日记',
                 'mood': '开心', 'place': '自检地点', 'content': '第一行\n第二行',
                 'files': [(_img_bytes((224, 123, 57)), 'photo1.jpg'),
                           (_img_bytes((44, 110, 155), fmt='PNG'), 'photo2.png'),
                           (BytesIO('不是图片'.encode('utf-8')), 'note.txt')]},
           content_type='multipart/form-data', follow_redirects=True)
check('POST 日记(2图+1非法)', r)

conn = A.DB.connect()
conn.row_factory = sqlite3.Row
e_row = conn.execute('SELECT * FROM dog_diary ORDER BY id DESC LIMIT 1').fetchone()
eid = e_row['id'] if e_row else None
media = [dict(x) for x in conn.execute(
    'SELECT * FROM diary_media WHERE diary_id=?', (eid,)).fetchall()]
d_ok = (e_row and e_row['title'] == '自检日记' and len(media) == 2
        and all(m['kind'] == 'image' for m in media))
print(('  OK  ' if d_ok else ' FAIL ')
      + f'日记入库：title={e_row["title"] if e_row else None}，媒体 {len(media)} 个'
        f'（非法格式已跳过，应为 2）')
if not d_ok:
    ok = False

# 缩略图确实落盘了
thumbs_ok = all(m['thumb'] and os.path.exists(os.path.join(DB.UPLOAD_DIR, m['thumb']))
                for m in media)
print(('  OK  ' if thumbs_ok else ' FAIL ') + '图片缩略图已生成并落盘')
if not thumbs_ok:
    ok = False

# 媒体能通过 /media 路由取到（用缩略图路径，小）
if media:
    r = c.get('/media/' + media[0]['thumb'])
    check('GET /media/<缩略图>', r)
    ct_ok = r.headers.get('Content-Type', '').startswith('image/')
    print(('  OK  ' if ct_ok else ' FAIL ') + f'媒体 Content-Type = {r.headers.get("Content-Type")}')
    if not ct_ok:
        ok = False

# 日记页渲染 + 内容出现
r = c.get(f'/dog/{did}/diary')
check('GET 日记页', r)
body = r.get_data(as_text=True)
for kw in ('自检日记', '自检地点', 'photo1.jpg'):
    found = kw in body
    print(('  OK  ' if found else ' FAIL ') + f'日记页包含「{kw}」')
    if not found:
        ok = False

# 月份筛选 + 关键词筛选
mon = date.today().strftime('%Y-%m')
check('GET 日记页?month=', c.get(f'/dog/{did}/diary?month={mon}'))
check('GET 日记页?q=', c.get(f'/dog/{did}/diary?q=自检'))
check('GET 日记页?q=不存在xyz', c.get(f'/dog/{did}/diary?q=不存在xyz'))

# 编辑日记文字
r = c.post('/api/diary/update', json={'id': eid, 'day': date.today().isoformat(),
                                      'title': '改过的标题', 'mood': '平静',
                                      'place': '', 'content': '改过的正文'})
j = r.get_json() or {}
t2 = conn.execute('SELECT title, mood FROM dog_diary WHERE id=?', (eid,)).fetchone()
u_ok = r.status_code == 200 and j.get('ok') and t2['title'] == '改过的标题'
print(('  OK  ' if u_ok else ' FAIL ') + f'编辑日记：{r.status_code} title={t2["title"]}')
if not u_ok:
    ok = False

# 删除单个媒体 → 文件也要从磁盘消失
if media:
    mid = media[0]['id']
    fp = os.path.join(DB.UPLOAD_DIR, media[0]['path'])
    tp = os.path.join(DB.UPLOAD_DIR, media[0]['thumb'])
    r = c.post('/api/diary/media/delete', json={'id': mid})
    left = conn.execute('SELECT COUNT(*) c FROM diary_media WHERE id=?', (mid,)).fetchone()['c']
    gone = (not os.path.exists(fp)) and (not os.path.exists(tp)) and left == 0
    print(('  OK  ' if (r.status_code == 200 and gone) else ' FAIL ')
          + f'删除媒体：库记录剩 {left}，磁盘文件已清 {not os.path.exists(fp)}')
    if not (r.status_code == 200 and gone):
        ok = False
    r = c.post('/api/diary/media/delete', json={'id': 999999})
    print(('  OK  ' if r.status_code == 404 else ' FAIL ')
          + f'删不存在的媒体 -> {r.status_code}（应为 404）')
    if r.status_code != 404:
        ok = False

# 边界：空日记（无标题无正文无文件）应被挡回
r = c.post(f'/dog/{did}/diary/new', data={'day': date.today().isoformat()},
           follow_redirects=True)
n_empty = conn.execute('SELECT COUNT(*) c FROM dog_diary').fetchone()['c']
print(('  OK  ' if n_empty == 1 else ' FAIL ')
      + f'空日记被拒绝：日记总数 {n_empty}（应为 1）')
if n_empty != 1:
    ok = False

# 删除日记（连带剩余媒体）
r = c.post(f'/dog/{did}/diary/{eid}/delete', follow_redirects=True)
check('POST 删除日记', r)
left_e = conn.execute('SELECT COUNT(*) c FROM dog_diary WHERE id=?', (eid,)).fetchone()['c']
left_m = conn.execute('SELECT COUNT(*) c FROM diary_media WHERE diary_id=?', (eid,)).fetchone()['c']
de_ok = left_e == 0 and left_m == 0
print(('  OK  ' if de_ok else ' FAIL ') + f'删日记连带媒体：日记剩 {left_e}，媒体剩 {left_m}')
if not de_ok:
    ok = False

print('--- 5g. 狗狗记账 ---')
r = c.get(f'/dog/{did}/expense')
check('GET 记账页', r)

today_s = date.today().isoformat()
made = []
for cat, item, amt in [('狗粮', '幼犬粮 2kg', 168.0), ('洗澡美容', '洗澡', 88.0),
                       ('疫苗', '狂犬疫苗', 120.0)]:
    r = c.post('/api/expense', json={'dog_id': did, 'day': today_s, 'category': cat,
                                     'item': item, 'amount': amt, 'shop': '自检店',
                                     'pay_method': '微信'})
    j = r.get_json() or {}
    made.append(j)
    print(('  OK  ' if (r.status_code == 200 and j.get('ok')) else ' FAIL ')
          + f'新增记账「{item}」¥{amt}')
    if not (r.status_code == 200 and j.get('ok')):
        ok = False

summ = made[-1].get('summary', {}) if made else {}
# 本月合计 = 168 + 88 + 120 = 376（都记在今天）
s_ok = abs(summ.get('month', 0) - 376.0) < 0.01 and summ.get('count') == 3
print(('  OK  ' if s_ok else ' FAIL ')
      + f'统计：本月 ¥{summ.get("month")}（应 376.0）· 笔数 {summ.get("count")}（应 3）')
if not s_ok:
    ok = False

# 分类汇总应含三类
cats = {c_['category'] for c_ in summ.get('by_cat', [])}
c_ok = {'狗粮', '洗澡美容', '疫苗'} <= cats
print(('  OK  ' if c_ok else ' FAIL ') + f'分类汇总：{sorted(cats)}')
if not c_ok:
    ok = False
# 近 12 月走势应恰好 12 个点，且最后一个是本月
ms = summ.get('months', [])
m_ok = len(ms) == 12 and ms[-1]['m'] == date.today().strftime('%Y-%m')
print(('  OK  ' if m_ok else ' FAIL ') + f'近 12 月走势 {len(ms)} 点，末位 {ms[-1]["m"] if ms else "—"}')
if not m_ok:
    ok = False

# 边界
bad_cases = [
    ('金额为 0', {'dog_id': did, 'day': today_s, 'category': '狗粮', 'amount': 0}, 400),
    ('金额非数字', {'dog_id': did, 'day': today_s, 'category': '狗粮', 'amount': 'abc'}, 400),
    ('分类非法', {'dog_id': did, 'day': today_s, 'category': '不存在的类', 'amount': 10}, 400),
    ('日期非法', {'dog_id': did, 'day': '2026-13-99', 'category': '狗粮', 'amount': 10}, 400),
    ('狗狗不存在', {'dog_id': 999999, 'day': today_s, 'category': '狗粮', 'amount': 10}, 404),
]
for name, payload, exp in bad_cases:
    r = c.post('/api/expense', json=payload)
    print(('  OK  ' if r.status_code == exp else ' FAIL ')
          + f'{name} -> {r.status_code}（应 {exp}）')
    if r.status_code != exp:
        ok = False

# 编辑
row = conn.execute('SELECT * FROM dog_expense ORDER BY id DESC LIMIT 1').fetchone()
r = c.post('/api/expense/update', json={'id': row['id'], 'day': today_s,
                                        'category': '就医', 'item': '改过的项目',
                                        'amount': 210.5, 'note': '改过'})
upd = conn.execute('SELECT * FROM dog_expense WHERE id=?', (row['id'],)).fetchone()
u2 = (r.status_code == 200 and upd['category'] == '就医'
      and upd['item'] == '改过的项目' and abs(upd['amount'] - 210.5) < 0.01)
print(('  OK  ' if u2 else ' FAIL ') + f'编辑记账：{r.status_code} {upd["item"]} ¥{upd["amount"]}')
if not u2:
    ok = False

# 筛选
check('GET 记账页?category=狗粮', c.get(f'/dog/{did}/expense?category=狗粮'))
check('GET 记账页?from=..&to=..', c.get(f'/dog/{did}/expense?from={today_s}&to={today_s}'))
check('GET 记账页?q=洗澡', c.get(f'/dog/{did}/expense?q=洗澡'))

# CSV 导出
r = c.get(f'/dog/{did}/expense.csv')
csv_ok = (r.status_code == 200 and 'text/csv' in r.headers.get('Content-Type', '')
          and '合计' in r.get_data(as_text=True))
print(('  OK  ' if csv_ok else ' FAIL ') + f'CSV 导出：{r.status_code} {r.headers.get("Content-Type")}')
if not csv_ok:
    ok = False

# 删除
r = c.post('/api/expense/delete', json={'id': row['id']})
gone = conn.execute('SELECT COUNT(*) c FROM dog_expense WHERE id=?', (row['id'],)).fetchone()['c']
print(('  OK  ' if (r.status_code == 200 and gone == 0) else ' FAIL ')
      + f'删除记账：{r.status_code}，剩余 {gone} 条')
if not (r.status_code == 200 and gone == 0):
    ok = False
r = c.post('/api/expense/delete', json={'id': 999999})
print(('  OK  ' if r.status_code == 404 else ' FAIL ') + f'删不存在记账 -> {r.status_code}（应 404）')
if r.status_code != 404:
    ok = False
conn.close()

print('--- 6. 业务逻辑抽样 ---')
print('  月龄:', A.biz.age_text(dog['birth_date']))
plan = A.biz.feed_plan(dog)
print('  喂养计划:', plan['meals'], '餐 /', plan['amount'], '/ 每餐', plan['per_meal_g'], 'g')
tl = A.biz.today_timeline(dog)
print('  时间轴条目:', len(tl))
for it in tl[:6]:
    print(f'    {it["time"]} {it["kind"]:6s} {it["title"]}')
stats = A.biz.range_stats(A.DB.connect(), dog, 7)
print('  7 天统计:', {k: stats[k] for k in ('train_rate', 'potty_rate', 'avg_stool', 'feed_rate')})
print('  综合分:', A.biz.health_score(stats), '判定:', A.biz.verdict(stats)[0])

print()
print('=' * 40)
print('全部通过 ✅' if ok else '存在失败 ❌')
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(0 if ok else 1)
