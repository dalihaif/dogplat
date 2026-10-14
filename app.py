# -*- coding: utf-8 -*-
"""狗狗管理平台 · Flask 应用"""
import csv
import io
import json
import mimetypes
import os
import shutil
import sys
import uuid
from datetime import date, datetime, timedelta
from urllib.parse import quote

from flask import (Flask, g, jsonify, redirect, render_template, request,
                   send_from_directory, url_for, flash, Response)

import biz
import db as DB
import knowledge as K

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dogplat-local-key'
app.config['JSON_AS_ASCII'] = False
# 上传上限：单个请求 300MB（够放一段手机短视频），超过返回友好提示
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024
app.teardown_appcontext(DB.close_db)

# ---------------------------------------------------------------- 作者 / 版本
APP_NAME = '狗狗管理平台'
APP_VERSION = 'v2.1'
APP_SINCE = '2026-10-14'
AUTHOR = {
    'name': '李海峰',
    'phone': '13988531240',
    'email': 'dalihaif@qq.com',
    'org': '大理大学第一附属医院',
    'github': 'dalihaif',
    'github_url': 'https://github.com/dalihaif',
    'city': '云南 · 大理',
    'slogan': '技术改变工作，设计美化生活',
    'intro': '档案管理从业者，业余写点能真正用起来的小系统。'
             '这个平台最初是为了管好自家的狗，后来把喂养、训练、健康、'
             '日记和花销都做了进来。',
}

# 狗狗管理状态：不再用「在养 / 已归档」这种二值开关
DOG_STATUS = biz.DOG_STATUS
STATUS_CHIP = {'在养': 'ok', '送人': 'brand', '死亡': 'danger', '走失': 'warn', '其他': ''}
STATUS_TIP = {
    '在养': '当前正在饲养，正常排计划、打卡、提醒',
    '送人': '已送养 / 转让给他人，不再提醒喂养免疫',
    '死亡': '已离世，档案保留不再提醒',
    '走失': '走失未找回，档案保留不再提醒',
    '其他': '其他情况（如寄养在外、长期不在身边），不参与提醒',
}

# ---------------------------------------------------------------- 日记 & 记账配置
# 日记心情（存文字，展示带表情）
DIARY_MOODS = [('开心', '😀'), ('平静', '😌'), ('慵懒', '😴'), ('兴奋', '🥳'),
               ('调皮', '😤'), ('不适', '🤒'), ('温馨', '🥰')]
DIARY_MOOD_EMOJI = dict(DIARY_MOODS)

# 记账分类（覆盖用户点名的：用品、洗澡、打针）
EXPENSE_CATS = [
    ('狗粮', '主食狗粮、罐头、冻干、鲜食'),
    ('零食', '磨牙棒、训练零食、肉干'),
    ('用品', '窝垫、牵引绳、项圈、玩具、餐具、尿垫、清洁用品'),
    ('洗澡美容', '洗澡、剪毛、修甲、spa'),
    ('疫苗', '联苗、狂犬疫苗（打针）'),
    ('驱虫', '体内 / 体外驱虫药'),
    ('就医', '门诊、化验、手术、药品'),
    ('训练', '训练课、上门训练'),
    ('证件', '办证、芯片、年检'),
    ('寄养', '宠物店 / 医院寄养'),
    ('运输', '打车、接送、托运'),
    ('其他', '以上之外'),
]
EXPENSE_CAT_TIP = dict(EXPENSE_CATS)
PAY_METHODS = ['微信', '支付宝', '现金', '银行卡', '其他']

# 允许上传的媒体类型（离线白名单，不看 MIME 免得被伪造）
IMAGE_EXT = {'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'}
VIDEO_EXT = {'mp4', 'webm', 'mov', 'm4v', 'ogg', 'avi'}
MAX_MEDIA_PER_UPLOAD = 20
THUMB_SIZE = (640, 640)   # 缩略图最长边

MIME_MAP = {
    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'gif': 'image/gif',
    'webp': 'image/webp', 'bmp': 'image/bmp',
    'mp4': 'video/mp4', 'webm': 'video/webm', 'mov': 'video/quicktime',
    'm4v': 'video/x-m4v', 'ogg': 'video/ogg', 'avi': 'video/x-msvideo',
}


def media_kind(ext):
    ext = (ext or '').lower()
    if ext in IMAGE_EXT:
        return 'image'
    if ext in VIDEO_EXT:
        return 'video'
    return None


def human_size(n):
    n = n or 0
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024.0


def save_media(fs, dog_id):
    """把上传的单个文件落盘，返回可直接入库的字典；不合法返回 None。

    文件名用 uuid，原始名单独存 —— secure_filename 会把中文吃光。
    """
    ext = (fs.filename or '').rsplit('.', 1)[-1].lower() if '.' in (fs.filename or '') else ''
    kind = media_kind(ext)
    if not kind:
        return None
    month = date.today().strftime('%Y%m')
    sub = os.path.join('diary', str(dog_id), month)
    folder = os.path.join(DB.UPLOAD_DIR, sub)
    os.makedirs(folder, exist_ok=True)

    name = uuid.uuid4().hex
    fname = f'{name}.{ext}'
    fpath = os.path.join(folder, fname)
    fs.save(fpath)
    size = os.path.getsize(fpath)

    rel = os.path.join(sub, fname).replace('\\', '/')
    thumb_rel = ''
    if kind == 'image':
        thumb_rel = _make_thumb(fpath, folder, name)
    return {
        'kind': kind,
        'path': rel,
        'thumb': thumb_rel,
        'orig_name': fs.filename,
        'mime': MIME_MAP.get(ext) or mimetypes.guess_type(fname)[0] or 'application/octet-stream',
        'size': size,
    }


def _make_thumb(src, folder, name):
    """给图片生成缩略图，失败就返回空（列表改用原图，不阻塞上传）"""
    try:
        from PIL import Image
    except ImportError:
        return ''
    try:
        im = Image.open(src)
        im = im.convert('RGB') if im.mode in ('P', 'RGBA', 'LA') else im
        im.thumbnail(THUMB_SIZE)
        tp = os.path.join(folder, f'{name}_thumb.jpg')
        im.save(tp, 'JPEG', quality=82, optimize=True)
        rel = os.path.relpath(tp, DB.UPLOAD_DIR).replace('\\', '/')
        return rel
    except Exception:
        return ''


def delete_media_file(conn, mid):
    """删一条媒体：先删磁盘文件，再删库记录"""
    row = conn.execute('SELECT * FROM diary_media WHERE id=?', (mid,)).fetchone()
    if not row:
        return False
    for p in (row['path'], row['thumb']):
        if not p:
            continue
        fp = os.path.join(DB.UPLOAD_DIR, p)
        try:
            if os.path.exists(fp):
                os.remove(fp)
        except OSError:
            pass
    conn.execute('DELETE FROM diary_media WHERE id=?', (mid,))
    return dict(row)


def delete_diary_dir(dog_id, day):
    """日记删掉后，顺手清掉那天该狗狗的月目录（若已空）"""
    month = (day or '').replace('-', '')[:6]
    folder = os.path.join(DB.UPLOAD_DIR, 'diary', str(dog_id), month)
    try:
        if os.path.isdir(folder) and not os.listdir(folder):
            os.rmdir(folder)
    except OSError:
        pass


def month_str(d=None):
    return (d or date.today()).strftime('%Y-%m')


def load_diary_meta(conn, dog_id=None):
    """取某只狗狗（或全部）的日记月份分布，用于筛选下拉"""
    where, args = '', []
    if dog_id:
        where, args = ' WHERE dog_id=?', [dog_id]
    return [dict(r) for r in conn.execute(
        "SELECT substr(day,1,7) m, COUNT(*) c FROM dog_diary" + where +
        " GROUP BY m ORDER BY m DESC", args).fetchall()]


def diary_media_map(conn, ids):
    """批量取媒体，避免 N+1"""
    if not ids:
        return {}
    q = ','.join('?' for _ in ids)
    out = {}
    for r in conn.execute(
            f'SELECT * FROM diary_media WHERE diary_id IN ({q}) ORDER BY id', ids).fetchall():
        out.setdefault(r['diary_id'], []).append(dict(r))
    return out


def expense_summary(conn, dog_id, day=None):
    """消费统计：本月 / 今年 / 总计 / 分类分布 / 近 12 月走势"""
    day = day or date.today()
    today_s = day.isoformat()
    month_s = day.strftime('%Y-%m')
    year_s = day.strftime('%Y')
    total = conn.execute(
        'SELECT IFNULL(SUM(amount),0) s, COUNT(*) c FROM dog_expense WHERE dog_id=?',
        (dog_id,)).fetchone()
    cur_month = conn.execute(
        "SELECT IFNULL(SUM(amount),0) s FROM dog_expense WHERE dog_id=? AND substr(day,1,7)=?",
        (dog_id, month_s)).fetchone()['s']
    cur_year = conn.execute(
        "SELECT IFNULL(SUM(amount),0) s FROM dog_expense WHERE dog_id=? AND substr(day,1,4)=?",
        (dog_id, year_s)).fetchone()['s']
    by_cat = [dict(r) for r in conn.execute(
        'SELECT category, SUM(amount) s, COUNT(*) c FROM dog_expense WHERE dog_id=?'
        ' GROUP BY category ORDER BY s DESC', (dog_id,)).fetchall()]
    months = []
    for i in range(11, -1, -1):
        y, m = day.year, day.month - i
        while m <= 0:
            m += 12
            y -= 1
        key = f'{y:04d}-{m:02d}'
        months.append({'m': key, 's': 0})
    mrow = {x['m']: x for x in months}
    for r in conn.execute(
            "SELECT substr(day,1,7) m, SUM(amount) s FROM dog_expense WHERE dog_id=?"
            " GROUP BY m", (dog_id,)).fetchall():
        if r['m'] in mrow:
            mrow[r['m']]['s'] = round(r['s'] or 0, 2)
    return {
        'total': round(total['s'] or 0, 2), 'count': total['c'],
        'month': round(cur_month or 0, 2), 'year': round(cur_year or 0, 2),
        'by_cat': by_cat, 'months': months, 'month_key': month_s,
    }


def apply_status(conn, dog_id, new_status, note='', at=None):
    """改状态：状态真的变了才写日志，返回 True/False。

    同时维护旧的 active 字段（=1 仅当在养），保证老逻辑不乱。
    """
    row = conn.execute('SELECT status FROM dogs WHERE id=?', (dog_id,)).fetchone()
    if not row:
        return False
    old = row['status'] or biz.STATUS_MANAGED
    if new_status == old:
        return False
    at = at or datetime.now().strftime('%Y-%m-%d %H:%M')
    conn.execute(
        'UPDATE dogs SET status=?, status_changed_at=?, active=? WHERE id=?',
        (new_status, at, 1 if new_status == biz.STATUS_MANAGED else 0, dog_id))
    conn.execute(
        'INSERT INTO dog_status_log (dog_id, old_status, new_status, note, changed_at)'
        ' VALUES (?,?,?,?,?)',
        (dog_id, old, new_status, (note or '').strip(), at))
    return True


def load_status_log(conn, did, limit=30):
    return [dict(r) for r in conn.execute(
        'SELECT * FROM dog_status_log WHERE dog_id=? ORDER BY changed_at DESC, id DESC LIMIT ?',
        (did, limit)).fetchall()]


# ---------------------------------------------------------------- 初始化
def ensure_init():
    conn = DB.connect()
    DB.init_db(conn)
    seed_health_columns(conn)
    conn.close()


def seed_health_columns(conn):
    """首次运行时把内置知识底表灌入 knowledge 表，方便检索"""
    n = conn.execute('SELECT COUNT(*) c FROM knowledge').fetchone()['c']
    if n:
        return
    now = datetime.now().strftime('%Y-%m-%d')
    rows = []
    for r in K.FEED_TABLE:
        rows.append(('喂养', f'{r[0]} 月龄喂养方案',
                     f'{r[2]} 餐/日，间隔 {r[3]}，参考体重 {r[5]} kg，每日粮量 {r[6]} g',
                     'A-Pets / WTOPETS 喂养指南', '', f'{r[0]} 月龄', now))
    for a, b in K.POTTY_FREQ_TABLE:
        rows.append(('排泄', f'{a} 排泄频率', b, 'UC Davis 兽医学院', '', a, now))
    for s, form, judge, lv in K.STOOL_SCORES:
        rows.append(('排泄', f'便便评分 {s} 分', f'{form} —— {judge}', '通用 1-7 分法', '', '通用', now))
    for r in K.VACCINE_RULES:
        rows.append(('免疫', r['kind'], f'{r["window"]}。{r["tip"]}', '邢台仟宠宠物医院 / 蘑菇宠医', '',
                     r['window'], now))
    for kind, off, win in K.DEWORM_RULES:
        rows.append(('免疫', kind, win, '执业兽医问答', '', win, now))
    for c in K.COMMANDS:
        rows.append(('训练', f'口令：{c["name"]}',
                     f'教法：{c["how"]}。成功标准：{c["standard"]}。常见坑：{c["pitfall"]}',
                     '日新犬舍 / 宠智灵训练指南', '', '8 周龄起', now))
    for name, desc, freq in K.SOCIAL_ITEMS:
        rows.append(('训练', f'社会化：{name}', f'{desc}；频率 {freq}',
                     'Petselect 幼犬社会化指南', '', '3-16 周', now))
    for f, why, lv in K.FORBIDDEN_FOODS:
        rows.append(('饮食', f'禁忌食物：{f}', why,
                     '公安部昆明警犬基地 / 科普中国 / 俄亥俄州立大学兽医学院', '', '全阶段', now))
    conn.executemany(
        'INSERT INTO knowledge (category, topic, conclusion, source, url, age_range, fetched_at)'
        ' VALUES (?,?,?,?,?,?,?)', rows)
    conn.commit()


# ---------------------------------------------------------------- 模板全局
@app.context_processor
def inject_globals():
    conn = DB.get_db()
    dogs = conn.execute(
        "SELECT * FROM dogs WHERE IFNULL(status,'在养')=? ORDER BY id",
        (biz.STATUS_MANAGED,)).fetchall()
    return {
        'all_dogs': [dict(d) for d in dogs],
        'today': date.today().isoformat(),
        'DISCLAIMER': K.DISCLAIMER,
        'AUTHOR': AUTHOR,
        'APP_NAME': APP_NAME,
        'APP_VERSION': APP_VERSION,
        'APP_SINCE': APP_SINCE,
        'dog_age': biz.age_text,
        'dog_stage': lambda b: biz.stage_of(biz.month_age(b)[0]),
        'DOG_STATUS': DOG_STATUS,
        'STATUS_CHIP': STATUS_CHIP,
        'STATUS_TIP': STATUS_TIP,
        'DIARY_MOODS': DIARY_MOODS,
        'DIARY_MOOD_EMOJI': DIARY_MOOD_EMOJI,
        'EXPENSE_CATS': EXPENSE_CATS,
        'EXPENSE_CAT_TIP': EXPENSE_CAT_TIP,
        'PAY_METHODS': PAY_METHODS,
        'human_size': human_size,
        'dstatus': lambda d: (d.get('status') if hasattr(d, 'get') else d['status']) or biz.STATUS_MANAGED,
    }


@app.template_filter('age_text')
def f_age_text(v):
    return biz.age_text(v)


# ---------------------------------------------------------------- 首页
@app.route('/')
def index():
    conn = DB.get_db()
    dogs = [dict(d) for d in conn.execute(
        "SELECT * FROM dogs WHERE IFNULL(status,'在养')=? ORDER BY id",
        (biz.STATUS_MANAGED,)).fetchall()]
    # 已送人 / 死亡 / 走失 / 其他的，不在总览打扰，但列在下面留个入口
    others = [dict(d) for d in conn.execute(
        "SELECT * FROM dogs WHERE IFNULL(status,'在养')<>? ORDER BY status_changed_at DESC, id",
        (biz.STATUS_MANAGED,)).fetchall()]

    cards = []
    for d in dogs:
        timeline, hit, total = biz.today_progress(conn, d)
        alerts = biz.alerts_for(conn, d)
        m, _ = biz.month_age(d['birth_date'])
        plan = biz.feed_plan(d)
        cards.append({
            'dog': d,
            'age': biz.age_text(d['birth_date']),
            'months': m,
            'stage': biz.stage_of(m),
            'plan': plan,
            'hit': hit, 'total': total,
            'pct': round(hit / total * 100) if total else 0,
            'alerts': alerts,
            'danger': sum(1 for a in alerts if a['level'] == 'danger'),
            'warn': sum(1 for a in alerts if a['level'] == 'warn'),
        })

    global_alerts = []
    for c in cards:
        for a in c['alerts']:
            global_alerts.append({'dog': c['dog']['name'], 'dog_id': c['dog']['id'], **a})
    global_alerts.sort(key=lambda x: 0 if x['level'] == 'danger' else 1)

    return render_template('index.html', cards=cards, alerts=global_alerts, others=others)


# ---------------------------------------------------------------- 档案
@app.route('/dogs')
def dogs():
    conn = DB.get_db()
    sel = (request.args.get('status') or '').strip()
    sql = 'SELECT * FROM dogs'
    args = []
    if sel in DOG_STATUS:
        sql += " WHERE IFNULL(status,'在养')=?"
        args.append(sel)
    # 在养的排前面，其余按状态变更时间倒序
    sql += " ORDER BY (IFNULL(status,'在养')=?) DESC, status_changed_at DESC, id"
    args.append(biz.STATUS_MANAGED)

    counts = {s: 0 for s in DOG_STATUS}
    for r in conn.execute(
            "SELECT IFNULL(status,'在养') s, COUNT(*) c FROM dogs GROUP BY s").fetchall():
        counts[r['s']] = counts.get(r['s'], 0) + r['c']

    # 每只狗狗最近一次状态变更
    log_map = {}
    for r in conn.execute(
            'SELECT dog_id, old_status, new_status, note, changed_at FROM dog_status_log'
            ' WHERE id IN (SELECT MAX(id) FROM dog_status_log GROUP BY dog_id)').fetchall():
        log_map[r['dog_id']] = dict(r)

    out = []
    for r in conn.execute(sql, args).fetchall():
        d = dict(r)
        m, _ = biz.month_age(d['birth_date'])
        d['age'] = biz.age_text(d['birth_date'])
        d['stage'] = biz.stage_of(m)
        d['status'] = d.get('status') or biz.STATUS_MANAGED
        d['last_log'] = log_map.get(d['id'])
        out.append(d)
    return render_template('dogs.html', dogs=out, sel=sel, counts=counts,
                           total=sum(counts.values()))


@app.route('/dogs/new', methods=['GET', 'POST'])
def dog_new():
    if request.method == 'POST':
        return save_dog(None)
    return render_template('dog_form.html', dog=None)


@app.route('/dogs/<int:did>/edit', methods=['GET', 'POST'])
def dog_edit(did):
    conn = DB.get_db()
    dog = conn.execute('SELECT * FROM dogs WHERE id=?', (did,)).fetchone()
    if not dog:
        flash('狗狗不存在', 'danger')
        return redirect(url_for('dogs'))
    if request.method == 'POST':
        return save_dog(did)
    return render_template('dog_form.html', dog=dict(dog))


FIELDS = ['name', 'breed_cn', 'breed_en', 'sex', 'birth_date', 'arrive_date',
          'weight_current', 'neutered', 'chip_no', 'license_no', 'owner_name',
          'owner_phone', 'coat_color', 'shoulder_height', 'personality_tags',
          'purchase_source', 'note',
          'sire_name', 'sire_breed', 'sire_chip',
          'dam_name', 'dam_breed', 'dam_chip', 'parents_note']


def save_dog(did):
    conn = DB.get_db()
    f = request.form
    vals = {}
    for k in FIELDS:
        v = (f.get(k) or '').strip()
        if k in ('weight_current', 'shoulder_height'):
            vals[k] = float(v) if v else None
        else:
            vals[k] = v or None
    if not vals.get('name'):
        flash('名字必填', 'danger')
        return redirect(request.url)

    if vals.get('weight_current'):
        vals['weight_updated_at'] = date.today().isoformat()

    new_status = (f.get('status') or '').strip()
    if new_status not in DOG_STATUS:
        new_status = biz.STATUS_MANAGED
    status_note = (f.get('status_note') or '').strip()

    if did:
        sets = ', '.join(f'{k}=?' for k in vals)
        conn.execute(f'UPDATE dogs SET {sets} WHERE id=?', list(vals.values()) + [did])
        # 状态走 apply_status，状态真的变了才记流水
        if apply_status(conn, did, new_status, status_note):
            flash(f'档案已保存，状态已改为「{new_status}」', 'success')
        else:
            flash('档案已保存', 'success')
    else:
        vals['created_at'] = datetime.now().isoformat(timespec='seconds')
        vals['status'] = new_status
        vals['status_changed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
        vals['active'] = 1 if new_status == biz.STATUS_MANAGED else 0
        cols = ', '.join(vals)
        ph = ', '.join('?' for _ in vals)
        cur = conn.execute(f'INSERT INTO dogs ({cols}) VALUES ({ph})', list(vals.values()))
        did = cur.lastrowid
        # 建档时就不是「在养」的，也留一条记录
        if new_status != biz.STATUS_MANAGED:
            conn.execute(
                'INSERT INTO dog_status_log (dog_id, old_status, new_status, note, changed_at)'
                ' VALUES (?,?,?,?,?)',
                (did, '（建档）', new_status, status_note,
                 datetime.now().strftime('%Y-%m-%d %H:%M')))
        # 初始体重也记一条事件，便于画曲线
        if vals.get('weight_current'):
            conn.execute(
                'INSERT INTO care_events (dog_id, day, time, type, payload, created_at)'
                ' VALUES (?,?,?,?,?,?)',
                (did, date.today().isoformat(), datetime.now().strftime('%H:%M'),
                 'weight', json.dumps({'kg': vals['weight_current']}, ensure_ascii=False),
                 datetime.now().isoformat(timespec='seconds')))
        flash('档案已保存', 'success')
    conn.commit()
    return redirect(url_for('dog_home', did=did))


@app.route('/api/dog/status', methods=['POST'])
def api_dog_status():
    """快速改管理状态，并留一条变更记录（改了什么 + 时间）"""
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        did = int(j.get('dog_id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少 dog_id'}), 400
    row = conn.execute('SELECT id FROM dogs WHERE id=?', (did,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '狗狗不存在'}), 404

    st = (j.get('status') or '').strip()
    if st not in DOG_STATUS:
        return jsonify({'ok': False, 'error': '状态不合法'}), 400
    note = (j.get('note') or '').strip()

    changed = apply_status(conn, did, st, note)
    conn.commit()
    d = conn.execute('SELECT status, status_changed_at FROM dogs WHERE id=?', (did,)).fetchone()
    return jsonify({'ok': True, 'changed': changed, 'status': d['status'],
                    'changed_at': d['status_changed_at']})


# ---------------------------------------------------------------- 狗狗工作台
def load_dog(did):
    conn = DB.get_db()
    dog = conn.execute('SELECT * FROM dogs WHERE id=?', (did,)).fetchone()
    return conn, (dict(dog) if dog else None)


@app.route('/dog/<int:did>')
def dog_home(did):
    conn, dog = load_dog(did)
    if not dog:
        return redirect(url_for('dogs'))
    return redirect(url_for('dog_today', did=did))


@app.route('/dog/<int:did>/today')
def dog_today(did):
    conn, dog = load_dog(did)
    if not dog:
        return redirect(url_for('dogs'))
    day = request.args.get('day') or date.today().isoformat()
    d = biz.parse_date(day) or date.today()
    timeline, hit, total = biz.today_progress(conn, dog, d)
    evs = biz.events_of(conn, dog['id'], day, 1)
    m, _ = biz.month_age(dog['birth_date'])
    sched = biz.vaccine_schedule(dog)
    alerts = biz.alerts_for(conn, dog)
    return render_template(
        'dog_today.html', dog=dog, day=day, timeline=timeline, hit=hit, total=total,
        events=evs, plan=biz.feed_plan(dog), age=biz.age_text(dog['birth_date'], d),
        stage=biz.stage_of(m), alerts=alerts, schedule=sched,
        stool_scores=K.STOOL_SCORES, commands=K.COMMANDS,
        social=K.SOCIAL_ITEMS, triggers=K.POTTY_TRIGGERS)


@app.route('/dog/<int:did>/train')
def dog_train(did):
    conn, dog = load_dog(did)
    if not dog:
        return redirect(url_for('dogs'))
    stats = biz.range_stats(conn, dog, 14)
    evs = [e for e in biz.events_of(conn, dog['id']) if e['type'] == 'train']
    by_cmd = {}
    for e in evs:
        c = e['data'].get('command') or '未命名'
        g = by_cmd.setdefault(c, [0, 0, 0])
        g[0] += e['data'].get('success', 0)
        g[1] += e['data'].get('total', 0)
        g[2] += 1
    cmd_rows = [{'name': k, 'rate': round(v[0] / v[1] * 100) if v[1] else 0,
                 'sessions': v[2], 'success': v[0], 'total': v[1]}
                for k, v in by_cmd.items()]
    cmd_rows.sort(key=lambda x: x['name'])
    return render_template('dog_train.html', dog=dog, stats=stats,
                           alerts=biz.alerts_for(conn, dog),
                           logs=sorted(evs, key=lambda x: (x['day'], x['time'] or ''), reverse=True)[:60],
                           cmd_rows=cmd_rows, commands=K.COMMANDS,
                           plan=biz.feed_plan(dog), stool_scores=K.STOOL_SCORES,
                           triggers=K.POTTY_TRIGGERS)


@app.route('/dog/<int:did>/health')
def dog_health(did):
    conn, dog = load_dog(did)
    if not dog:
        return redirect(url_for('dogs'))
    evs = biz.events_of(conn, dog['id'])
    feeds = sorted([e for e in evs if e['type'] == 'feed'],
                   key=lambda x: (x['day'], x['time'] or ''), reverse=True)[:80]
    potties = sorted([e for e in evs if e['type'] == 'potty'],
                     key=lambda x: (x['day'], x['time'] or ''), reverse=True)[:80]
    weights = sorted([e for e in evs if e['type'] == 'weight' and e['data'].get('kg')],
                     key=lambda x: (x['day'], x['time'] or ''))
    records = conn.execute(
        'SELECT * FROM health_records WHERE dog_id=? ORDER BY happen_date DESC',
        (did,)).fetchall()
    return render_template('dog_health.html', dog=dog, feeds=feeds, potties=potties,
                           weights=weights, records=[dict(r) for r in records],
                           stool_scores=K.STOOL_SCORES, forbidden=K.FORBIDDEN_FOODS,
                           commands=K.COMMANDS, triggers=K.POTTY_TRIGGERS,
                           plan=biz.feed_plan(dog),
                           schedule=biz.vaccine_schedule(dog),
                           alerts=biz.alerts_for(conn, dog),
                           weight_json=json.dumps([[w['day'], w['data']['kg']] for w in weights],
                                                  ensure_ascii=False))


@app.route('/dog/<int:did>/weekly')
def dog_weekly(did):
    conn, dog = load_dog(did)
    if not dog:
        return redirect(url_for('dogs'))
    days = int(request.args.get('days', 7))
    days = days if days in (7, 14, 30) else 7
    stats = biz.range_stats(conn, dog, days)
    v, vd = biz.verdict(stats)
    return render_template('dog_weekly.html', dog=dog, stats=stats, verdict=v,
                           verdict_desc=vd, tips=biz.next_week_plan(stats),
                           score=biz.health_score(stats),
                           stats_json=json.dumps(stats, ensure_ascii=False),
                           alerts=biz.alerts_for(conn, dog))


@app.route('/dog/<int:did>/profile')
def dog_profile(did):
    conn, dog = load_dog(did)
    if not dog:
        return redirect(url_for('dogs'))
    m, _ = biz.month_age(dog['birth_date'])
    recent_diary = [dict(r) for r in conn.execute(
        'SELECT * FROM dog_diary WHERE dog_id=? ORDER BY day DESC, id DESC LIMIT 3',
        (did,)).fetchall()]
    dm = diary_media_map(conn, [e['id'] for e in recent_diary])
    for e in recent_diary:
        e['media'] = dm.get(e['id'], [])
    return render_template('dog_profile.html', dog=dog, age=biz.age_text(dog['birth_date']),
                           months=m, stage=biz.stage_of(m), schedule=biz.vaccine_schedule(dog),
                           social=K.SOCIAL_ITEMS,
                           status_log=load_status_log(conn, did, 30),
                           recent_diary=recent_diary,
                           diary_n=conn.execute(
                               'SELECT COUNT(*) c FROM dog_diary WHERE dog_id=?',
                               (did,)).fetchone()['c'],
                           expense=expense_summary(conn, did),
                           records=[dict(r) for r in conn.execute(
                               'SELECT * FROM health_records WHERE dog_id=? ORDER BY happen_date DESC',
                               (did,)).fetchall()],
                           alerts=biz.alerts_for(conn, dog))


# ---------------------------------------------------------------- 记录管理
EVENT_TYPES = [('feed', '喂食'), ('potty', '排泄'), ('train', '训练'),
               ('weight', '体重'), ('water', '饮水'), ('note', '备注')]
EVENT_LABEL = dict(EVENT_TYPES)


@app.route('/dog/<int:did>/records')
def dog_records(did):
    """全部记录：按类型 / 日期范围 / 关键词筛选，分页，可编辑、可删除"""
    conn, dog = load_dog(did)
    if not dog:
        return redirect(url_for('dogs'))
    typ = (request.args.get('type') or '').strip()
    d1 = (request.args.get('from') or '').strip()
    d2 = (request.args.get('to') or '').strip()
    kw = (request.args.get('q') or '').strip()
    try:
        page = max(1, int(request.args.get('page') or 1))
    except ValueError:
        page = 1
    per = 50

    # 类型分布（全部，不受当前筛选影响，让用户知道数据构成）
    counts = {t: 0 for t, _ in EVENT_TYPES}
    for r in conn.execute('SELECT type, COUNT(*) c FROM care_events WHERE dog_id=? GROUP BY type',
                          (did,)).fetchall():
        counts[r['type']] = r['c']

    where = ' WHERE dog_id=?'
    args = [did]
    if typ:
        where += ' AND type=?'
        args.append(typ)
    if d1:
        where += ' AND day>=?'
        args.append(d1)
    if d2:
        where += ' AND day<=?'
        args.append(d2)
    if kw:
        where += ' AND (IFNULL(note,"") LIKE ? OR IFNULL(payload,"") LIKE ?)'
        args += [f'%{kw}%'] * 2

    matched = conn.execute('SELECT COUNT(*) c FROM care_events' + where, args).fetchone()['c']
    pages = max(1, (matched + per - 1) // per)
    page = min(page, pages)

    rows = conn.execute(
        'SELECT * FROM care_events' + where + ' ORDER BY day DESC, time DESC, id DESC LIMIT ? OFFSET ?',
        args + [per, (page - 1) * per]).fetchall()

    events = []
    for r in rows:
        d = dict(r)
        try:
            d['data'] = json.loads(d['payload']) if d['payload'] else {}
        except (ValueError, TypeError):
            d['data'] = {}
        events.append(d)

    return render_template(
        'dog_records.html', dog=dog, events=events, counts=counts,
        total=sum(counts.values()), matched=matched,
        typ=typ, d1=d1, d2=d2, kw=kw, page=page, pages=pages,
        types=EVENT_TYPES, labels=EVENT_LABEL,
        plan=biz.feed_plan(dog), stool_scores=K.STOOL_SCORES,
        commands=K.COMMANDS, triggers=K.POTTY_TRIGGERS,
        alerts=biz.alerts_for(conn, dog))




# ---------------------------------------------------------------- API：打卡
def _resync_weight(conn, dog_id):
    """以最新一条体重记录为准回写 dogs 表。
    打卡 / 编辑 / 删除体重记录后都调它，保证档案里的体重和记录不脱节。"""
    row = conn.execute(
        "SELECT day, payload FROM care_events WHERE dog_id=? AND type='weight'"
        " AND payload IS NOT NULL ORDER BY day DESC, time DESC LIMIT 1",
        (dog_id,)).fetchone()
    kg, day = None, None
    if row:
        try:
            kg = (json.loads(row['payload']) or {}).get('kg')
        except (ValueError, TypeError):
            kg = None
        if kg:
            day = row['day']
    conn.execute('UPDATE dogs SET weight_current=?, weight_updated_at=? WHERE id=?',
                 (kg, day, dog_id))


@app.route('/api/checkin', methods=['POST'])
def api_checkin():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    dog_id = int(j.get('dog_id'))
    typ = j.get('type')
    time_s = j.get('time') or datetime.now().strftime('%H:%M')
    day = j.get('day') or date.today().isoformat()
    data = j.get('data') or {}
    if isinstance(data, str):
        data = json.loads(data)
    note = j.get('note') or ''

    conn.execute(
        'INSERT INTO care_events (dog_id, day, time, type, payload, note, created_at)'
        ' VALUES (?,?,?,?,?,?,?)',
        (dog_id, day, time_s, typ, json.dumps(data, ensure_ascii=False), note,
         datetime.now().isoformat(timespec='seconds')))

    # 体重类记录：档案体重以最新记录为准
    if typ == 'weight':
        _resync_weight(conn, dog_id)
    conn.commit()

    dog = dict(conn.execute('SELECT * FROM dogs WHERE id=?', (dog_id,)).fetchone())
    alerts = biz.alerts_for(conn, dog)
    return jsonify({'ok': True, 'alerts': alerts})


@app.route('/api/event/update', methods=['POST'])
def api_event_update():
    """修改一条已有记录（日期/时间/类型/内容/备注都能改）"""
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        eid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少记录 id'}), 400

    row = conn.execute('SELECT * FROM care_events WHERE id=?', (eid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '记录不存在'}), 404

    typ = j.get('type') or row['type']
    day = j.get('day') or row['day']
    time_s = j.get('time') or row['time']
    note = row['note'] if j.get('note') is None else j.get('note')

    data = j.get('data')
    if data is None:
        payload = row['payload']
    else:
        if isinstance(data, str):
            data = json.loads(data)
        payload = json.dumps(data, ensure_ascii=False)

    conn.execute(
        'UPDATE care_events SET day=?, time=?, type=?, payload=?, note=? WHERE id=?',
        (day, time_s, typ, payload, note, eid))

    # 体重记录被改 → 重新同步档案；从别的类型改成体重也算
    if typ == 'weight' or row['type'] == 'weight':
        _resync_weight(conn, row['dog_id'])
    conn.commit()

    dog = dict(conn.execute('SELECT * FROM dogs WHERE id=?', (row['dog_id'],)).fetchone())
    return jsonify({'ok': True, 'alerts': biz.alerts_for(conn, dog)})


@app.route('/api/event/delete', methods=['POST'])
def api_event_delete():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        eid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少记录 id'}), 400
    row = conn.execute('SELECT dog_id, type FROM care_events WHERE id=?', (eid,)).fetchone()
    conn.execute('DELETE FROM care_events WHERE id=?', (eid,))
    if row and row['type'] == 'weight':
        _resync_weight(conn, row['dog_id'])
    conn.commit()
    return jsonify({'ok': True})


@app.route('/api/health_record/update', methods=['POST'])
def api_health_record_update():
    """修改一条免疫/就诊登记"""
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        rid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少记录 id'}), 400
    conn.execute(
        'UPDATE health_records SET kind=?, dose_no=?, happen_date=?, next_due=?, vet=?, note=?'
        ' WHERE id=?',
        (j.get('kind'), j.get('dose_no'), j.get('happen_date'), j.get('next_due'),
         j.get('vet'), j.get('note'), rid))
    conn.commit()
    return jsonify({'ok': True})



@app.route('/api/health_record', methods=['POST'])
def api_health_record():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    conn.execute(
        'INSERT INTO health_records (dog_id, kind, dose_no, happen_date, next_due, vet, note, created_at)'
        ' VALUES (?,?,?,?,?,?,?,?)',
        (int(j['dog_id']), j.get('kind'), j.get('dose_no'), j.get('happen_date'),
         j.get('next_due'), j.get('vet'), j.get('note'),
         datetime.now().isoformat(timespec='seconds')))
    conn.commit()
    flash('健康记录已登记', 'success')
    return redirect(request.referrer or url_for('index'))


@app.route('/health_record/<int:rid>/delete', methods=['POST'])
def health_record_delete(rid):
    conn = DB.get_db()
    conn.execute('DELETE FROM health_records WHERE id=?', (rid,))
    conn.commit()
    return redirect(request.referrer or url_for('index'))


# ---------------------------------------------------------------- 狗狗日记
DIARY_PER = 20


@app.route('/dog/<int:did>/diary')
def dog_diary(did):
    """狗狗日记：图文/视频时间线，可按月 / 关键词筛选，分页"""
    conn, dog = load_dog(did)
    if not dog:
        return redirect(url_for('dogs'))
    mon = (request.args.get('month') or '').strip()
    kw = (request.args.get('q') or '').strip()
    try:
        page = max(1, int(request.args.get('page') or 1))
    except ValueError:
        page = 1

    where, args = ' WHERE dog_id=?', [did]
    if mon:
        where += " AND substr(day,1,7)=?"
        args.append(mon)
    if kw:
        where += ' AND (IFNULL(title,"") LIKE ? OR IFNULL(content,"") LIKE ?' \
                 ' OR IFNULL(place,"") LIKE ?)'
        args += [f'%{kw}%'] * 3

    matched = conn.execute('SELECT COUNT(*) c FROM dog_diary' + where, args).fetchone()['c']
    pages = max(1, (matched + DIARY_PER - 1) // DIARY_PER)
    page = min(page, max(1, pages))
    rows = conn.execute(
        'SELECT * FROM dog_diary' + where +
        ' ORDER BY day DESC, id DESC LIMIT ? OFFSET ?',
        args + [DIARY_PER, (page - 1) * DIARY_PER]).fetchall()
    entries = [dict(r) for r in rows]
    mm = diary_media_map(conn, [e['id'] for e in entries])
    for e in entries:
        e['media'] = mm.get(e['id'], [])

    stats = conn.execute(
        'SELECT COUNT(*) c FROM dog_diary WHERE dog_id=?', (did,)).fetchone()['c']
    media_n = conn.execute(
        'SELECT COUNT(*) c, SUM(kind="image") i, SUM(kind="video") v'
        ' FROM diary_media WHERE dog_id=?', (did,)).fetchone()

    return render_template(
        'dog_diary.html', dog=dog, entries=entries, matched=matched,
        page=page, pages=pages, mon=mon, kw=kw,
        months=load_diary_meta(conn, did), stats=stats,
        img_n=media_n['i'] or 0, vid_n=media_n['v'] or 0,
        alerts=biz.alerts_for(conn, dog))


@app.route('/dog/<int:did>/diary/new', methods=['POST'])
def diary_new(did):
    """新建日记（multipart，可带多张图片/视频）"""
    conn, dog = load_dog(did)
    if not dog:
        return redirect(url_for('dogs'))
    f = request.form
    day = (f.get('day') or date.today().isoformat()).strip()
    title = (f.get('title') or '').strip()
    content = (f.get('content') or '').strip()
    files = [x for x in request.files.getlist('files') if x and x.filename]
    if not title and not content and not files:
        flash('至少写点什么，或者传张照片', 'danger')
        return redirect(url_for('dog_diary', did=did))

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    cur = conn.execute(
        'INSERT INTO dog_diary (dog_id, day, title, mood, place, content, created_at, updated_at)'
        ' VALUES (?,?,?,?,?,?,?,?)',
        (did, day, title or None, (f.get('mood') or '').strip() or None,
         (f.get('place') or '').strip() or None, content or None, now, now))
    eid = cur.lastrowid

    saved = skipped = 0
    for fs in files[:MAX_MEDIA_PER_UPLOAD]:
        info = save_media(fs, did)
        if not info:
            skipped += 1
            continue
        conn.execute(
            'INSERT INTO diary_media (diary_id, dog_id, kind, path, thumb, orig_name,'
            ' mime, size, created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (eid, did, info['kind'], info['path'], info['thumb'], info['orig_name'],
             info['mime'], info['size'], now))
        saved += 1
    conn.commit()

    msg = '日记已保存'
    if saved:
        msg += f'，附 {saved} 个文件'
    if skipped:
        msg += f'（{skipped} 个格式不支持已跳过）'
    flash(msg, 'success')
    return redirect(url_for('dog_diary', did=did, month=day[:7]))


@app.route('/api/diary/update', methods=['POST'])
def api_diary_update():
    """改日记文字（媒体另走删除/新增）"""
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        eid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少日记 id'}), 400
    row = conn.execute('SELECT id FROM dog_diary WHERE id=?', (eid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '日记不存在'}), 404
    conn.execute(
        'UPDATE dog_diary SET day=?, title=?, mood=?, place=?, content=?, updated_at=?'
        ' WHERE id=?',
        ((j.get('day') or date.today().isoformat()).strip(),
         (j.get('title') or '').strip() or None,
         (j.get('mood') or '').strip() or None,
         (j.get('place') or '').strip() or None,
         (j.get('content') or '').strip() or None,
         datetime.now().strftime('%Y-%m-%d %H:%M'), eid))
    conn.commit()
    return jsonify({'ok': True})


@app.route('/dog/<int:did>/diary/<int:eid>/delete', methods=['POST'])
def diary_delete(did, eid):
    conn = DB.get_db()
    row = conn.execute('SELECT * FROM dog_diary WHERE id=? AND dog_id=?',
                       (eid, did)).fetchone()
    if row:
        for m in conn.execute('SELECT id FROM diary_media WHERE diary_id=?', (eid,)).fetchall():
            delete_media_file(conn, m['id'])
        conn.execute('DELETE FROM dog_diary WHERE id=?', (eid,))
        delete_diary_dir(did, row['day'])
        conn.commit()
        flash('日记已删除', 'success')
    else:
        flash('日记不存在', 'danger')
    return redirect(url_for('dog_diary', did=did))


@app.route('/api/diary/media/delete', methods=['POST'])
def api_diary_media_delete():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        mid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少媒体 id'}), 400
    got = delete_media_file(conn, mid)
    if not got:
        return jsonify({'ok': False, 'error': '媒体不存在'}), 404
    conn.commit()
    return jsonify({'ok': True})


@app.route('/media/<path:relpath>')
def media_file(relpath):
    """按需读取上传的图片/视频（放在 data 下，不塞进 static）"""
    return send_from_directory(DB.UPLOAD_DIR, relpath)


@app.errorhandler(413)
def too_large(e):
    flash('上传太大（单次请求上限 300MB），请压缩视频或分批上传', 'danger')
    return redirect(request.referrer or url_for('index')), 303


# ---------------------------------------------------------------- 狗狗记账
EXPENSE_PER = 30


@app.route('/dog/<int:did>/expense')
def dog_expense(did):
    """记账：买用品、洗澡、打针等消费，带统计图与筛选列表"""
    conn, dog = load_dog(did)
    if not dog:
        return redirect(url_for('dogs'))
    cat = (request.args.get('category') or '').strip()
    d1 = (request.args.get('from') or '').strip()
    d2 = (request.args.get('to') or '').strip()
    kw = (request.args.get('q') or '').strip()
    try:
        page = max(1, int(request.args.get('page') or 1))
    except ValueError:
        page = 1

    where, args = ' WHERE dog_id=?', [did]
    if cat:
        where += ' AND category=?'
        args.append(cat)
    if d1:
        where += ' AND day>=?'
        args.append(d1)
    if d2:
        where += ' AND day<=?'
        args.append(d2)
    if kw:
        where += ' AND (IFNULL(item,"") LIKE ? OR IFNULL(shop,"") LIKE ?' \
                 ' OR IFNULL(note,"") LIKE ?)'
        args += [f'%{kw}%'] * 3

    matched = conn.execute('SELECT COUNT(*) c FROM dog_expense' + where, args).fetchone()['c']
    pages = max(1, (matched + EXPENSE_PER - 1) // EXPENSE_PER)
    page = min(page, max(1, pages))
    rows = conn.execute(
        'SELECT * FROM dog_expense' + where +
        ' ORDER BY day DESC, id DESC LIMIT ? OFFSET ?',
        args + [EXPENSE_PER, (page - 1) * EXPENSE_PER]).fetchall()

    fsum = conn.execute(
        'SELECT IFNULL(SUM(amount),0) s FROM dog_expense' + where, args).fetchone()['s']

    return render_template(
        'dog_expense.html', dog=dog, rows=[dict(r) for r in rows],
        matched=matched, page=page, pages=pages,
        cat=cat, d1=d1, d2=d2, kw=kw, fsum=round(fsum or 0, 2),
        summary=expense_summary(conn, did),
        alerts=biz.alerts_for(conn, dog))


@app.route('/api/expense', methods=['POST'])
def api_expense_add():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    did = _expense_dog_id(conn, j)
    if did is None:
        return jsonify({'ok': False, 'error': '狗狗不存在'}), 404
    v, err = _expense_vals(j)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    conn.execute(
        'INSERT INTO dog_expense (dog_id, day, category, item, amount, qty, unit,'
        ' shop, pay_method, note, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (did, v['day'], v['category'], v['item'], v['amount'], v['qty'], v['unit'],
         v['shop'], v['pay_method'], v['note'],
         datetime.now().isoformat(timespec='seconds')))
    conn.commit()
    return jsonify({'ok': True, 'summary': expense_summary(conn, did)})


@app.route('/api/expense/update', methods=['POST'])
def api_expense_update():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        rid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少记录 id'}), 400
    row = conn.execute('SELECT dog_id FROM dog_expense WHERE id=?', (rid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '记录不存在'}), 404
    v, err = _expense_vals(j)
    if err:
        return jsonify({'ok': False, 'error': err}), 400
    conn.execute(
        'UPDATE dog_expense SET day=?, category=?, item=?, amount=?, qty=?, unit=?,'
        ' shop=?, pay_method=?, note=? WHERE id=?',
        (v['day'], v['category'], v['item'], v['amount'], v['qty'], v['unit'],
         v['shop'], v['pay_method'], v['note'], rid))
    conn.commit()
    return jsonify({'ok': True, 'summary': expense_summary(conn, row['dog_id'])})


@app.route('/api/expense/delete', methods=['POST'])
def api_expense_delete():
    conn = DB.get_db()
    j = request.get_json(silent=True) or request.form
    try:
        rid = int(j.get('id'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': '缺少记录 id'}), 400
    row = conn.execute('SELECT dog_id FROM dog_expense WHERE id=?', (rid,)).fetchone()
    if not row:
        return jsonify({'ok': False, 'error': '记录不存在'}), 404
    conn.execute('DELETE FROM dog_expense WHERE id=?', (rid,))
    conn.commit()
    return jsonify({'ok': True, 'summary': expense_summary(conn, row['dog_id'])})


def _expense_dog_id(conn, j):
    try:
        did = int(j.get('dog_id'))
    except (TypeError, ValueError):
        return None
    if not conn.execute('SELECT 1 FROM dogs WHERE id=?', (did,)).fetchone():
        return None
    return did


def _expense_vals(j):
    """校验并规整记账字段，返回 (值字典, 错误信息)"""
    day = (j.get('day') or date.today().isoformat()).strip()
    if not biz.parse_date(day):
        return None, '日期格式不对（用 2026-10-14 这种）'
    cat = (j.get('category') or '').strip()
    if cat not in EXPENSE_CAT_TIP:
        return None, '请选择消费分类'
    try:
        amount = round(float(j.get('amount')), 2)
    except (TypeError, ValueError):
        return None, '金额要填数字'
    if amount <= 0:
        return None, '金额要大于 0'

    def fnum(k):
        v = j.get(k)
        if v in (None, ''):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    return {
        'day': day, 'category': cat,
        'item': (j.get('item') or '').strip() or None,
        'amount': amount, 'qty': fnum('qty'),
        'unit': (j.get('unit') or '').strip() or None,
        'shop': (j.get('shop') or '').strip() or None,
        'pay_method': (j.get('pay_method') or '').strip() or None,
        'note': (j.get('note') or '').strip() or None,
    }, None


@app.route('/dog/<int:did>/expense.csv')
def dog_expense_csv(did):
    """导出 CSV（带 BOM，Excel 打开不乱码）"""
    conn, dog = load_dog(did)
    if not dog:
        return redirect(url_for('dogs'))
    rows = conn.execute(
        'SELECT * FROM dog_expense WHERE dog_id=? ORDER BY day, id', (did,)).fetchall()
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['日期', '分类', '项目', '金额', '数量', '单位', '商家', '支付方式', '备注'])
    total = 0.0
    for r in rows:
        total += r['amount'] or 0
        w.writerow([r['day'], r['category'], r['item'] or '', f'{r["amount"]:.2f}',
                    r['qty'] if r['qty'] is not None else '', r['unit'] or '',
                    r['shop'] or '', r['pay_method'] or '', r['note'] or ''])
    w.writerow([])
    w.writerow(['合计', '', '', f'{total:.2f}', '', '', '', '', f'{len(rows)} 笔'])
    data = '\ufeff' + buf.getvalue()
    fn = f'{dog["name"]}_记账_{date.today().isoformat()}.csv'
    # 头里不能直接放中文（WSGI 头是 latin-1），按 RFC 5987 百分号编码
    disp = ("attachment; filename=expense.csv; filename*=UTF-8''"
            + quote(fn, safe=''))
    return Response(data, mimetype='text/csv', headers={'Content-Disposition': disp})


# ---------------------------------------------------------------- 知识库
@app.route('/knowledge')
def knowledge_page():
    conn = DB.get_db()
    q = (request.args.get('q') or '').strip()
    cat = request.args.get('cat') or ''
    sql = 'SELECT * FROM knowledge WHERE 1=1'
    args = []
    if q:
        sql += ' AND (topic LIKE ? OR conclusion LIKE ? OR source LIKE ?)'
        args += [f'%{q}%'] * 3
    if cat:
        sql += ' AND category=?'
        args.append(cat)
    rows = conn.execute(sql + ' ORDER BY category, id', args).fetchall()
    cats = [r['category'] for r in conn.execute(
        'SELECT DISTINCT category FROM knowledge ORDER BY category').fetchall()]
    return render_template('knowledge.html', rows=[dict(r) for r in rows],
                           q=q, cat=cat, cats=cats,
                           forbidden=K.FORBIDDEN_FOODS, feed=K.FEED_TABLE,
                           potty=K.POTTY_FREQ_TABLE, stools=K.STOOL_SCORES,
                           vaccines=K.VACCINE_RULES, commands=K.COMMANDS,
                           social=K.SOCIAL_ITEMS, deworm=K.DEWORM_RULES,
                           vaccine_sched=K.VACCINE_RULES)


@app.route('/knowledge/add', methods=['POST'])
def knowledge_add():
    conn = DB.get_db()
    f = request.form
    conn.execute(
        'INSERT INTO knowledge (category, topic, conclusion, source, url, age_range, fetched_at)'
        ' VALUES (?,?,?,?,?,?,?)',
        (f.get('category') or '其他', f.get('topic'), f.get('conclusion'),
         f.get('source'), f.get('url'), f.get('age_range'),
         date.today().isoformat()))
    conn.commit()
    flash('已入库', 'success')
    return redirect(url_for('knowledge_page'))


@app.route('/knowledge/<int:kid>/delete', methods=['POST'])
def knowledge_delete(kid):
    conn = DB.get_db()
    conn.execute('DELETE FROM knowledge WHERE id=?', (kid,))
    conn.commit()
    return redirect(url_for('knowledge_page'))


# ---------------------------------------------------------------- 联网检索入库
import search as S

PENDING = os.path.join(DB.DATA_DIR, 'pending_candidates.json')


def save_pending(cands):
    with open(PENDING, 'w', encoding='utf-8') as f:
        json.dump(cands, f, ensure_ascii=False)


def load_pending():
    if not os.path.exists(PENDING):
        return []
    try:
        with open(PENDING, encoding='utf-8') as f:
            return json.load(f)
    except (ValueError, OSError):
        return []


def render_fetch(**kw):
    base = {'rows': None, 'query': '', 'engine': 'auto', 'candidates': None,
            'report': None, 'msg': '', 'error': '', 'trust_label': S.TRUST_LABEL}
    base.update(kw)
    return render_template('fetch.html', **base)


@app.route('/fetch')
def fetch_page():
    return render_fetch()


@app.route('/fetch/search', methods=['POST'])
def fetch_search():
    q = (request.form.get('q') or '').strip()
    engine = request.form.get('engine') or 'auto'
    rows, err = S.search_web(q, engine, 10)
    return render_fetch(rows=rows, query=q, engine=engine, error=err,
                        msg=f'共 {len(rows)} 条相关结果' if rows else '')


@app.route('/fetch/url', methods=['POST'])
def fetch_by_url():
    """直接抓一个指定网址"""
    u = (request.form.get('url') or '').strip()
    if not u.startswith('http'):
        return render_fetch(error='请输入完整网址（以 http 开头）')
    cands, report = S.fetch_and_extract([u], per_page=8)
    save_pending(cands)
    return render_fetch(query=u, report=report, candidates=list(enumerate(cands)),
                        msg=f'提取 {len(cands)} 条候选',
                        error='' if cands else '没提取到内容，可能该页正文太短或是动态加载')


@app.route('/fetch/extract', methods=['POST'])
def fetch_extract():
    urls = request.form.getlist('url')
    q = request.form.get('query') or ''
    if not urls:
        return render_fetch(query=q, error='没有勾选任何结果')
    cands, report = S.fetch_and_extract(urls)
    save_pending(cands)
    ok_n = sum(1 for r in report if r['ok'])
    return render_fetch(query=q, report=report, candidates=list(enumerate(cands)),
                        msg=f'抓取 {len(report)} 篇（成功 {ok_n}），提取 {len(cands)} 条候选',
                        error='' if cands else '抓到的页面没提取出可用内容，换个关键词或直接粘网址')


@app.route('/fetch/save', methods=['POST'])
def fetch_save():
    idxs = []
    for v in request.form.getlist('idx'):
        try:
            idxs.append(int(v))
        except ValueError:
            pass
    cands = load_pending()
    conn = DB.get_db()
    new = skip = 0
    for i in idxs:
        if i < 0 or i >= len(cands):
            continue
        c = cands[i]
        dup = conn.execute('SELECT 1 FROM knowledge WHERE conclusion=? LIMIT 1',
                           (c['conclusion'],)).fetchone()
        if dup:
            skip += 1
            continue
        conn.execute(
            'INSERT INTO knowledge (category, topic, conclusion, source, url, age_range, fetched_at)'
            ' VALUES (?,?,?,?,?,?,?)',
            (c['category'], c['topic'], c['conclusion'], c['source'], c['url'],
             '通用', date.today().isoformat()))
        new += 1
    conn.commit()
    flash(f'入库 {new} 条' + (f'，跳过重复 {skip} 条' if skip else ''), 'success')
    return redirect(url_for('knowledge_page'))


# ---------------------------------------------------------------- 关于
@app.route('/about')
def about_page():
    """关于本平台 + 作者基本信息"""
    conn = DB.get_db()

    def one(sql, args=()):
        return conn.execute(sql, args).fetchone()[0]

    stat = {
        'dogs': one('SELECT COUNT(*) FROM dogs'),
        'managed': one("SELECT COUNT(*) FROM dogs WHERE IFNULL(status,'在养')=?",
                       (biz.STATUS_MANAGED,)),
        'events': one('SELECT COUNT(*) FROM care_events'),
        'diary': one('SELECT COUNT(*) FROM dog_diary'),
        'media': one('SELECT COUNT(*) FROM diary_media'),
        'expense': one('SELECT COUNT(*) FROM dog_expense'),
        'spent': one('SELECT IFNULL(SUM(amount),0) FROM dog_expense'),
        'knowledge': one('SELECT COUNT(*) FROM knowledge'),
    }
    return render_template('about.html', stat=stat, since=APP_SINCE)


# ---------------------------------------------------------------- PWA
@app.route('/manifest.webmanifest')
def pwa_manifest():
    data = {
        'name': APP_NAME,
        'short_name': '狗狗',
        'description': '狗狗档案、喂养排便计划、训练与饮食健康记录、日记与记账',
        'lang': 'zh-CN',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'orientation': 'portrait',
        'background_color': '#FAF7F3',
        'theme_color': '#E07B39',
        'icons': [
            {'src': '/static/icon-192.png', 'sizes': '192x192',
             'type': 'image/png', 'purpose': 'any'},
            {'src': '/static/icon-512.png', 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'any'},
            {'src': '/static/icon-512.png', 'sizes': '512x512',
             'type': 'image/png', 'purpose': 'maskable'},
        ],
        'shortcuts': [
            {'name': '今日打卡', 'url': '/dog/1/today'},
            {'name': '记录管理', 'url': '/dog/1/records'},
            {'name': '狗狗日记', 'url': '/dog/1/diary'},
            {'name': '狗狗记账', 'url': '/dog/1/expense'},
            {'name': '狗狗档案', 'url': '/dogs'},
        ],
    }
    return jsonify(data), 200, {'Content-Type': 'application/manifest+json; charset=utf-8'}


@app.route('/sw.js')
def pwa_sw():
    resp = send_from_directory(app.static_folder, 'sw.js',
                               mimetype='application/javascript')
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache'
    return resp


# ---------------------------------------------------------------- 启动
@app.errorhandler(404)
def nf(e):
    return render_template('404.html'), 404


import socket


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except OSError:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


class _Tee:
    """把输出同时写到控制台和日志文件（后台运行时控制台可能不存在）"""

    def __init__(self, *streams):
        self.streams = [s for s in streams if s is not None]

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
                st.flush()
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


def _setup_logging():
    try:
        os.makedirs(DB.DATA_DIR, exist_ok=True)
        f = open(os.path.join(DB.DATA_DIR, 'server.log'), 'a', encoding='utf-8')
        sys.stdout = _Tee(sys.stdout, f)
        sys.stderr = _Tee(sys.stderr, f)
    except Exception:
        pass


if __name__ == '__main__':
    _setup_logging()
    ensure_init()
    port = int(os.environ.get('DOGPLAT_PORT', 5800))
    ip = lan_ip()
    banner = (
        '\n' + '=' * 60 + '\n'
        f'  {APP_NAME} {APP_VERSION} 已启动\n'
        f'  作者：      {AUTHOR["name"]}（{AUTHOR["email"]}）\n'
        f'  本机访问：  http://127.0.0.1:{port}\n'
        f'  局域网访问：http://{ip}:{port}   （手机连同一 WiFi 打开这个）\n'
        f'  启动时间：  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n'
        + '=' * 60
    )
    print(banner)

    # 把地址写到文件，方便不开窗口时查看
    try:
        with open(os.path.join(DB.DATA_DIR, '访问地址.txt'), 'w', encoding='utf-8') as f:
            f.write(banner.strip() + '\n\n手机装到桌面：用局域网地址打开 → 浏览器菜单选「安装应用 / 添加到主屏幕」\n')
    except OSError:
        pass

    try:
        from waitress import serve
        print('  服务器：waitress（生产级，8 线程）')
        serve(app, host='0.0.0.0', port=port, threads=8, _quiet=True)
    except ImportError:
        print('  服务器：Flask 内置（建议 pip install waitress）')
        app.run(host='0.0.0.0', port=port, debug=False)
