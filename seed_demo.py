# -*- coding: utf-8 -*-
"""灌入演示数据（会把库清空重建，谨慎使用）
用法：python seed_demo.py
"""
import json
import random
from datetime import date, datetime, timedelta

import app as A
import db as DB

random.seed(20261014)

conn = DB.connect()
DB.init_db(conn)
conn.executescript(
    'DELETE FROM care_events;'
    'DELETE FROM health_records;'
    'DELETE FROM dog_status_log;'
    'DELETE FROM diary_media;'
    'DELETE FROM dog_diary;'
    'DELETE FROM dog_expense;'
    'DELETE FROM dogs;'
    "DELETE FROM sqlite_sequence WHERE name IN ('dogs','care_events','health_records',"
    "'dog_status_log','dog_diary','diary_media','dog_expense');"
)
conn.commit()

birth = date.today() - timedelta(days=128)      # 约 4 个月
arrive = date.today() - timedelta(days=60)

cur = conn.execute(
    'INSERT INTO dogs (name, breed_cn, breed_en, sex, birth_date, arrive_date,'
    ' weight_current, weight_updated_at, neutered, chip_no, owner_name, owner_phone,'
    ' personality_tags, coat_color, purchase_source, note,'
    ' sire_name, sire_breed, sire_chip, dam_name, dam_breed, dam_chip, parents_note,'
    ' status, status_changed_at, active, created_at)'
    ' VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)',
    ('豆豆', '威尔士柯基犬', 'Welsh Corgi', '公', birth.isoformat(), arrive.isoformat(),
     8.5, date.today().isoformat(), '未绝育', 'CN900123456', '李海峰', '13988531240',
     '亲人、兴奋度高、好奇', '三色', '朋友赠予', '换牙期啃咬比较明显',
     '大福', '威尔士柯基犬', 'CN900100001',
     '妞妞', '威尔士柯基犬', 'CN900100002',
     '同窝 4 只，父母均无髋关节病史',
     '在养', datetime.now().strftime('%Y-%m-%d %H:%M'), datetime.now().isoformat()))
did = cur.lastrowid

COMMANDS = ['看我 / 名字', '坐', '卧', '来（召回）', '等待']
ENVS = ['室内', '院子', '室内', '室内', '安静街道']

evs = []
# ---- 14 天记录
for d in range(13, -1, -1):
    day = (date.today() - timedelta(days=d)).isoformat()
    progress = (13 - d) / 13.0        # 0 → 1，越近越好

    # 三顿饭
    for i, t in enumerate(['07:30', '13:00', '18:30'], start=1):
        amount = 85
        eaten = amount if random.random() < (0.75 + progress * 0.25) else int(amount * random.uniform(.4, .9))
        evs.append((did, day, t, 'feed',
                    json.dumps({'amount': amount, 'eaten': eaten,
                                'food': '皇家幼犬粮', 'snack': '鸡肉粒 3 颗' if i == 2 else '',
                                'supplement': '益生菌 1 包' if i == 1 else ''},
                               ensure_ascii=False), ''))

    # 排便：定点成功率随进度提升
    for i, t in enumerate(['06:40', '07:50', '13:20', '18:50', '22:20'], start=1):
        if random.random() < 0.2:
            continue
        ok = random.random() < (0.45 + progress * 0.45)
        score = random.choice([3, 3, 4, 4, 5]) if ok else random.choice([4, 5, 5, 6])
        evs.append((did, day, t, 'potty',
                    json.dumps({'kind': '便' if i in (1, 3, 5) else '尿',
                                'success': ok, 'score': score if i in (1, 3, 5) else None,
                                'blood': False,
                                'location': '阳台尿垫' if ok else '客厅',
                                'trigger': ['睡醒后', '餐后', '餐后', '餐后', '睡前'][i - 1]},
                               ensure_ascii=False), ''))

    # 训练：每天 1-2 次
    for _ in range(random.choice([1, 1, 2])):
        cmd = COMMANDS[min(int(progress * len(COMMANDS)), len(COMMANDS) - 1)]
        total = 5
        base = 0.35 + progress * 0.55
        success = sum(1 for _ in range(total) if random.random() < base)
        evs.append((did, day, random.choice(['08:00', '12:40', '17:30']), 'train',
                    json.dumps({'command': cmd, 'minutes': 5,
                                'env': random.choice(ENVS),
                                'distraction': 1 + int(progress * 3),
                                'success': success, 'total': total,
                                'reward': '鸡肉粒',
                                'adjust': f'明天把等待加到 {5 + int(progress * 10)} 秒'},
                               ensure_ascii=False), ''))

# ---- 体重：每周 +0.3kg
for w in range(3, -1, -1):
    day = (date.today() - timedelta(days=w * 5)).isoformat()
    evs.append((did, day, '07:00', 'weight',
                json.dumps({'kg': round(7.6 + (3 - w) * 0.3, 1)}, ensure_ascii=False), ''))

conn.executemany(
    'INSERT INTO care_events (dog_id, day, time, type, payload, note, created_at)'
    ' VALUES (?,?,?,?,?,?,?)',
    [e + (datetime.now().isoformat(timespec='seconds'),) for e in evs])

# ---- 已完成的疫苗
conn.execute(
    'INSERT INTO health_records (dog_id, kind, dose_no, happen_date, next_due, vet, note, created_at)'
    ' VALUES (?,?,?,?,?,?,?,?)',
    (did, '首针多联', '第 1 针', (birth + timedelta(days=45)).isoformat(),
     (birth + timedelta(days=66)).isoformat(), '大理宠物医院', '无不良反应',
     datetime.now().isoformat(timespec='seconds')))
conn.execute(
    'INSERT INTO health_records (dog_id, kind, dose_no, happen_date, next_due, vet, note, created_at)'
    ' VALUES (?,?,?,?,?,?,?,?)',
    (did, '第二针多联', '第 2 针', (birth + timedelta(days=80)).isoformat(),
     (birth + timedelta(days=101)).isoformat(), '大理宠物医院', '',
     datetime.now().isoformat(timespec='seconds')))

conn.commit()

# ---- 日记（含 2 张自动生成的示例照片）
import os                # noqa: E402
import uuid              # noqa: E402


def _demo_photo(label, color):
    """用 Pillow 画一张示例图，省得演示时相册是空的"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    d = date.today().strftime('%Y%m')
    rel_dir = f'diary/{did}/{d}'
    folder = os.path.join(DB.UPLOAD_DIR, 'diary', str(did), d)
    os.makedirs(folder, exist_ok=True)
    name = uuid.uuid4().hex
    fp = os.path.join(folder, name + '.jpg')
    im = Image.new('RGB', (900, 600), color)
    dr = ImageDraw.Draw(im)
    dr.ellipse((360, 210, 540, 390), fill=(255, 255, 255))
    dr.text((40, 40), label, fill=(255, 255, 255))
    im.save(fp, 'JPEG', quality=85)
    tp = os.path.join(folder, name + '_thumb.jpg')
    im.thumbnail((640, 640))
    im.save(tp, 'JPEG', quality=82)
    return (f'{rel_dir}/{name}.jpg', f'{rel_dir}/{name}_thumb.jpg',
            os.path.getsize(fp))


diaries = [
    ((date.today() - timedelta(days=2)).isoformat(), '第一次学会「坐下」', '开心', '家里客厅',
     '练了三天，今天终于能听口令坐下并且保持 5 秒。奖励用鸡肉粒，一口气练了 10 分钟都不腻。'),
    ((date.today() - timedelta(days=9)).isoformat(), '洱海边第一次下水', '兴奋', '洱海生态廊道',
     '本来怕水，牵着走到浅滩犹豫了很久，最后自己踩进去了，尾巴摇得飞起。回来洗了个澡。'),
    ((date.today() - timedelta(days=20)).isoformat(), '换牙期咬坏拖鞋', '调皮', '家里',
     '第 3 双拖鞋阵亡。牙胶买了两个它都不爱，还是拖鞋香。明天去宠物店换硬一点的磨牙骨。'),
]
photos = {k: v for k, v in
          {0: _demo_photo('DODO @ home', (224, 123, 57)),
           1: _demo_photo('DODO @ Erhai', (44, 110, 155))}.items() if v}
for idx, (day, title, mood, place, content) in enumerate(diaries):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    cur = conn.execute(
        'INSERT INTO dog_diary (dog_id, day, title, mood, place, content, created_at, updated_at)'
        ' VALUES (?,?,?,?,?,?,?,?)', (did, day, title, mood, place, content, now, now))
    eid = cur.lastrowid
    for k, (path, thumb, size) in photos.items():
        if idx != k:
            continue
        conn.execute(
            'INSERT INTO diary_media (diary_id, dog_id, kind, path, thumb, orig_name,'
            ' mime, size, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (eid, did, 'image', path, thumb, f'{title}.jpg', 'image/jpeg', size, now))

# ---- 记账：近 3 个月的常见消费
CATS = [
    ('狗粮', '皇家幼犬粮 2kg', 168.0, 2, '袋', '宠物之家', '微信'),
    ('用品', '睡垫 + 牵引绳', 129.0, None, None, '宠物之家', '支付宝'),
    ('洗澡美容', '洗澡 + 修甲', 88.0, None, None, '萌宠生活馆', '微信'),
    ('疫苗', '第二针多联', 120.0, 1, '针', '大理宠物医院', '现金'),
    ('驱虫', '体外驱虫滴剂', 65.0, 1, '支', '宠物之家', '微信'),
    ('零食', '鸡肉粒训练零食', 39.9, 1, '袋', '网上买的', '支付宝'),
    ('用品', '尿垫 100 片', 49.0, 1, '包', '网上买的', '支付宝'),
    ('洗澡美容', '洗澡', 60.0, None, None, '萌宠生活馆', '微信'),
    ('狗粮', '皇家幼犬粮 2kg', 168.0, 2, '袋', '宠物之家', '微信'),
    ('就医', '拉稀看诊 + 益生菌', 210.0, None, None, '大理宠物医院', '微信'),
    ('训练', '幼犬基础课 4 次', 480.0, 4, '次', '狗狗训练工作室', '银行卡'),
    ('证件', '养犬登记证 + 芯片', 150.0, None, None, '畜牧局', '现金'),
    ('零食', '磨牙骨', 25.0, 1, '个', '宠物之家', '微信'),
    ('用品', '食盆 + 水碗', 45.0, 1, '套', '网上买的', '支付宝'),
    ('洗澡美容', '洗澡 + 剪毛', 128.0, None, None, '萌宠生活馆', '微信'),
]
ex_rows = []
for i, (cat, item, amt, qty, unit, shop, pay) in enumerate(CATS):
    day = (date.today() - timedelta(days=random.randint(1, 85))).isoformat()
    ex_rows.append((did, day, cat, item, amt, qty, unit, shop, pay,
                    '', datetime.now().isoformat(timespec='seconds')))
conn.executemany(
    'INSERT INTO dog_expense (dog_id, day, category, item, amount, qty, unit, shop,'
    ' pay_method, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)', ex_rows)

conn.commit()
n = conn.execute('SELECT COUNT(*) c FROM care_events').fetchone()['c']
nd = conn.execute('SELECT COUNT(*) c FROM dog_diary').fetchone()['c']
ne = conn.execute('SELECT COUNT(*) c FROM dog_expense').fetchone()['c']
conn.close()

print(f'演示数据已灌入：1 只狗狗（豆豆），{n} 条记录，{nd} 篇日记，{ne} 笔记账')
print('启动服务后访问 http://127.0.0.1:5800 查看')
