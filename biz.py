# -*- coding: utf-8 -*-
"""核心业务逻辑：月龄计算、计划生成、预警、统计"""
import json
import calendar
from datetime import date, datetime, timedelta

import knowledge as K

# ---------------------------------------------------------------- 日期工具


def parse_date(s):
    if not s:
        return None
    if isinstance(s, date):
        return s
    s = str(s).strip()
    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%Y.%m.%d'):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def add_months(d, months):
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def month_age(birth, today=None):
    """返回 (月数, 余天数)，月数最小 0"""
    birth = parse_date(birth)
    if not birth:
        return None, None
    today = today or date.today()
    if today < birth:
        return 0, 0
    months = (today.year - birth.year) * 12 + (today.month - birth.month)
    if today.day < min(birth.day, calendar.monthrange(today.year, today.month)[1]):
        months -= 1
    months = max(months, 0)
    days = (today - add_months(birth, months)).days
    return months, days


def age_text(birth, today=None):
    m, d = month_age(birth, today)
    if m is None:
        return '未知'
    return f'{m} 个月 {d} 天'


def stage_of(months):
    if months is None:
        return '未知'
    if months < 2:
        return '乳犬/断奶期'
    if months < 4:
        return '社会化黄金期'
    if months < 6:
        return '快速生长期'
    if months < 12:
        return '青少年期'
    return '成年期'


def weeks_of(birth, today=None):
    birth = parse_date(birth)
    if not birth:
        return None
    return ((today or date.today()) - birth).days // 7


# ---------------------------------------------------------------- 喂养计划


def feed_row_for(months):
    if months is None:
        return K.FEED_TABLE[2]
    row = K.FEED_TABLE[0]
    for r in K.FEED_TABLE:
        if months >= r[0]:
            row = r
    return row


def feed_plan(dog):
    """根据月龄 + 体重算出每日餐数、餐时间、粮量区间"""
    months, _ = month_age(dog['birth_date'])
    row = feed_row_for(months)
    _, stage, meals, gap, coef, ref_w, ref_g = row
    times = K.MEAL_TIMES.get(meals, K.MEAL_TIMES[2])

    weight = dog['weight_current']
    if weight:
        base = weight * 1000 * coef / 100.0
        low, high = round(base * 0.88), round(base * 1.12)
        per_meal_g = round((low + high) / 2 / meals)
        per_meal = f'{round(low / meals)}–{round(high / meals)} g'
        amount = f'{low}–{high} g/日'
        amount_src = f'按当前体重 {weight} kg × {coef}% 估算，每 2 周按体重微调 ±10%'
    else:
        rl, rh = (ref_g.split('-') + ['0'])[:2]
        amount = f'{ref_g} g/日'
        per_meal_g = round((float(rl) + float(rh)) / 2 / meals)
        per_meal = f'约 {per_meal_g} g/餐（参考值）'
        amount_src = f'体重未录入，取{stage}参考值（{ref_w} kg 体型）；录入体重后自动改为按体重计算'

    return {
        'months': months,
        'stage': stage,
        'meals': meals,
        'gap': gap,
        'times': times,
        'amount': amount,
        'per_meal': per_meal,
        'per_meal_g': per_meal_g,
        'amount_src': amount_src,
        'coef': coef,
        'water_tip': '睡前 2 小时开始减少饮水，白天必须给足清水',
    }


# ---------------------------------------------------------------- 今日时间轴

POTTY_LABEL = '定点排便'


def today_timeline(dog, day=None):
    """把喂养和排便绑在一起，生成一天的待办时间轴"""
    day = day or date.today()
    plan = feed_plan(dog)
    items = []

    wake = '06:30'
    if plan['meals'] <= 2:
        wake = '07:30'

    items.append({
        'time': wake, 'kind': 'potty', 'title': '起床出笼 → 立刻去定点',
        'detail': '出笼 5 分钟内必带，成功率最高',
        'trigger': '睡醒后/出笼后', 'key': f'potty@{wake}',
    })

    for i, t in enumerate(plan['times'], start=1):
        hh, mm = map(int, t.split(':'))
        after = (datetime(2000, 1, 1, hh, mm) + timedelta(minutes=20)).strftime('%H:%M')
        items.append({
            'time': t, 'kind': 'feed', 'title': f'第 {i} 餐',
            'detail': f'计划量 {plan["per_meal"]}　今日合计 {plan["amount"]}',
            'trigger': '', 'key': f'feed@{t}',
        })
        items.append({
            'time': after, 'kind': 'potty', 'title': f'第 {i} 餐后定点排便',
            'detail': '餐后 15-30 分钟肠道蠕动，最容易成功',
            'trigger': '餐后', 'key': f'potty@{after}',
        })

    bed = '22:30' if plan['meals'] >= 3 else '22:00'
    items.append({
        'time': bed, 'kind': 'potty', 'title': '睡前最后一次排便',
        'detail': '排空后再睡，夜里更安稳',
        'trigger': '睡前', 'key': f'potty@{bed}',
    })

    items.sort(key=lambda x: x['time'])
    return items


# ---------------------------------------------------------------- 打卡记录


def events_of(conn, dog_id, day=None, days=1):
    if day:
        start = parse_date(day)
        end = start + timedelta(days=days - 1)
        rows = conn.execute(
            'SELECT * FROM care_events WHERE dog_id=? AND day>=? AND day<=? ORDER BY day, time',
            (dog_id, start.isoformat(), end.isoformat())).fetchall()
    else:
        rows = conn.execute(
            'SELECT * FROM care_events WHERE dog_id=? ORDER BY day DESC, time DESC',
            (dog_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d['data'] = json.loads(d['payload']) if d['payload'] else {}
        except (ValueError, TypeError):
            d['data'] = {}
        out.append(d)
    return out


def done_keys(conn, dog_id, day):
    """当天已完成的打卡 key 集合"""
    keys = set()
    for e in events_of(conn, dog_id, day, 1):
        keys.add(f"{e['type']}@{e['time']}")
    return keys


def today_progress(conn, dog, day=None):
    day = day or date.today()
    timeline = today_timeline(dog, day)
    done = done_keys(conn, dog['id'], day.isoformat())
    total = len(timeline)
    hit = sum(1 for it in timeline if it['key'] in done)
    for it in timeline:
        it['done'] = it['key'] in done
    return timeline, hit, total


# ---------------------------------------------------------------- 健康预警

DOG_STATUS = ['在养', '送人', '死亡', '走失', '其他']
# 只有「在养」的狗狗才谈得上喂养、免疫、训练这些事
STATUS_MANAGED = '在养'


def status_of(dog):
    return (dog.get('status') if hasattr(dog, 'get') else dog['status']) or STATUS_MANAGED


def is_managed(dog):
    return status_of(dog) == STATUS_MANAGED


def alerts_for(conn, dog):
    """返回预警列表 [{level, title, detail, action}]"""
    # 已送人 / 已死亡 / 走失的狗狗不再提醒喂养免疫训练
    if not is_managed(dog):
        return []
    out = []
    today = date.today()
    evs = events_of(conn, dog['id'])

    # 1) 便便评分
    stools = [e for e in evs if e['type'] == 'potty'
              and e['data'].get('kind') == '便']
    if stools:
        recent = sorted(stools, key=lambda x: (x['day'], x['time'] or ''))[-3:]
        scores = [e['data'].get('score') for e in recent if e['data'].get('score')]
        if scores and scores[-1] == 7:
            out.append({'level': 'danger', 'title': '便便水样（7 分）',
                        'detail': '最近一次记录为水样便',
                        'action': '立即就医，携带近 3 天进食与排便记录、疫苗驱虫时间'})
        elif len(scores) >= 2 and all(s >= 6 for s in scores[-K.WARN_RULES['stool_soft_streak']:]):
            out.append({'level': 'warn', 'title': f'连续 {len(scores[-2:])} 次糊状便',
                        'detail': '评分 ' + '、'.join(str(s) for s in scores[-2:]),
                        'action': '暂停所有零食与换粮，记录下一次排便；持续 24 小时未改善请就医'})
        if any(e['data'].get('blood') for e in recent):
            out.append({'level': 'danger', 'title': '便中带血或粘液',
                        'detail': '记录中存在血便标记',
                        'action': '立即就医'})

    # 2) 体重下降
    weights = sorted([e for e in evs if e['type'] == 'weight' and e['data'].get('kg')],
                     key=lambda x: x['day'])
    if len(weights) >= 2:
        latest = weights[-1]
        ld = parse_date(latest['day'])
        base = None
        for w in weights:
            if (ld - parse_date(w['day'])).days >= 7:
                base = w
        if base:
            b, n = base['data']['kg'], latest['data']['kg']
            if b > 0 and (b - n) / b * 100 >= K.WARN_RULES['weight_drop_pct']:
                out.append({'level': 'warn', 'title': '7 天内体重下降超过 5%',
                            'detail': f"{base['day']} {b} kg → {latest['day']} {n} kg",
                            'action': '建议就医排查'})

    # 3) 拒食
    feeds = sorted([e for e in evs if e['type'] == 'feed'], key=lambda x: (x['day'], x['time'] or ''))
    if feeds:
        last = feeds[-1]
        if last['data'].get('eaten') == 0:
            try:
                t = datetime.strptime(last['day'] + ' ' + (last['time'] or '08:00'), '%Y-%m-%d %H:%M')
            except ValueError:
                t = datetime.combine(parse_date(last['day']), datetime.min.time())
            hrs = (datetime.now() - t).total_seconds() / 3600
            if hrs >= K.WARN_RULES['reject_food_hours']:
                out.append({'level': 'danger', 'title': '疑似拒食超过 24 小时',
                            'detail': f"最后一次进食记录 {last['day']} {last['time']}，实际进食 0 g",
                            'action': '立即就医'})
            else:
                out.append({'level': 'warn', 'title': '最近一餐未进食',
                            'detail': f"{last['day']} {last['time']} 进食 0 g",
                            'action': '观察下一餐，若仍不吃请就医'})

    # 4) 体重长时间未更新
    if dog['weight_current']:
        wd = parse_date(dog['weight_updated_at'])
        if wd and (today - wd).days > 30:
            out.append({'level': 'warn', 'title': '体重超过 30 天未更新',
                        'detail': f'上次更新 {dog["weight_updated_at"]}',
                        'action': '重新称重并录入'})

    # 5) 疫苗 / 驱虫到期
    for a in vaccine_alerts(conn, dog):
        out.append(a)

    # 6) 月龄提醒
    m, _ = month_age(dog['birth_date'])
    if m is not None and m >= 3 and not dog.get('_has_rabies'):
        pass
    return out


def vaccine_schedule(dog):
    """按出生日期排出免疫日历"""
    birth = parse_date(dog['birth_date'])
    if not birth:
        return []
    rows = []
    for r in K.VACCINE_RULES:
        d = birth + timedelta(days=r['offset_days'])
        rows.append({'kind': r['kind'], 'date': d.isoformat(),
                     'window': r['window'], 'tip': r['tip']})
    for kind, off, win in K.DEWORM_RULES:
        rows.append({'kind': kind, 'date': (birth + timedelta(days=off)).isoformat(),
                     'window': win, 'tip': ''})
    # 6 月龄后每季度一次内驱
    for i in range(1, 5):
        d = add_months(birth, 6) + timedelta(days=90 * (i - 1))
        rows.append({'kind': f'体内驱虫（6 月龄后第 {i} 次，每季度）',
                     'date': d.isoformat(), 'window': '每季度 1 次', 'tip': ''})
    rows.sort(key=lambda x: x['date'])
    return rows


def vaccine_alerts(conn, dog):
    out = []
    today = date.today()
    done_kinds = {r['kind']: r for r in conn.execute(
        'SELECT * FROM health_records WHERE dog_id=?', (dog['id'],)).fetchall()}
    for row in vaccine_schedule(dog):
        kind, d = row['kind'], parse_date(row['date'])
        if kind in done_kinds:
            continue
        left = (d - today).days
        if left < -30:
            continue
        if left < 0:
            out.append({'level': 'danger', 'title': f'{kind} 已逾期 {abs(left)} 天',
                        'detail': f'计划日期 {row["date"]}（{row["window"]}）',
                        'action': '尽快补种，并登记到健康记录'})
        elif left <= 14:
            out.append({'level': 'warn', 'title': f'{kind} 还有 {left} 天到期',
                        'detail': f'计划日期 {row["date"]}（{row["window"]}）',
                        'action': row['tip'] or '提前预约宠物医院'})
    return out


# ---------------------------------------------------------------- 统计


def range_stats(conn, dog, days=7, end=None):
    end = end or date.today()
    start = end - timedelta(days=days - 1)
    evs = events_of(conn, dog['id'], start.isoformat(), days)

    train = [e for e in evs if e['type'] == 'train']
    s = sum(e['data'].get('success', 0) for e in train)
    t = sum(e['data'].get('total', 0) for e in train)
    train_rate = round(s / t * 100) if t else None

    potty = [e for e in evs if e['type'] == 'potty']
    potty_total = len(potty)
    potty_ok = sum(1 for e in potty if e['data'].get('success'))
    potty_rate = round(potty_ok / potty_total * 100) if potty_total else None

    stools = [e['data'].get('score') for e in potty if e['data'].get('score')]
    avg_stool = round(sum(stools) / len(stools), 1) if stools else None

    feeds = [e for e in evs if e['type'] == 'feed']
    feeds_ok = sum(1 for e in feeds
                   if e['data'].get('amount') and e['data'].get('eaten') is not None
                   and e['data']['amount'] > 0
                   and e['data']['eaten'] / e['data']['amount'] >= 0.9)
    feed_rate = round(feeds_ok / len(feeds) * 100) if feeds else None

    weights = [(e['day'], e['data']['kg']) for e in evs
               if e['type'] == 'weight' and e['data'].get('kg')]
    weights.sort()

    # 每日训练成功率（画图用）
    by_day = {}
    for e in train:
        d = by_day.setdefault(e['day'], [0, 0])
        d[0] += e['data'].get('success', 0)
        d[1] += e['data'].get('total', 0)
    trend = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        v = by_day.get(d)
        trend.append({'day': d[5:], 'rate': round(v[0] / v[1] * 100) if v and v[1] else None})

    return {
        'start': start.isoformat(), 'end': end.isoformat(), 'days': days,
        'train_rate': train_rate, 'train_count': len(train),
        'potty_rate': potty_rate, 'potty_total': potty_total, 'potty_ok': potty_ok,
        'avg_stool': avg_stool, 'feed_rate': feed_rate, 'feed_count': len(feeds),
        'weights': weights, 'trend': trend,
        'train_total': t, 'train_success': s,
    }


def health_score(stats):
    """0-100 综合分，用于周报结论"""
    parts = []
    if stats['train_rate'] is not None:
        parts.append(stats['train_rate'] * 0.35)
    if stats['potty_rate'] is not None:
        parts.append(stats['potty_rate'] * 0.35)
    if stats['avg_stool'] is not None:
        parts.append(max(0, (8 - stats['avg_stool']) / 5 * 100) * 0.3)
    if not parts:
        return None
    w = 0.35 * (stats['train_rate'] is not None) + \
        0.35 * (stats['potty_rate'] is not None) + \
        0.3 * (stats['avg_stool'] is not None)
    return round(sum(parts) / w)


def verdict(stats):
    sc = health_score(stats)
    if sc is None:
        return '数据不足', '先连续记录 3 天再来看看'
    if sc >= 80:
        return '进步明显', '保持当前节奏，可以按 10-20% 幅度加点难度了'
    if sc >= 60:
        return '稳步向前', '维持现有安排，重点盯住成功率最低的那一项'
    if sc >= 40:
        return '需要调整', '把训练拆得更小、时间更短，先把成功率拉过 60%'
    return '存在明显问题', '下降的指标优先排查健康因素，再谈训练'


def next_week_plan(stats):
    tips = []
    tr = stats['train_rate']
    if tr is None:
        tips.append('本周每天至少记 1 次训练日志，先有数据才能判断')
    elif tr >= 80:
        tips.append(f'训练成功率 {tr}%，下周把干扰等级提高一级（换到院子里练）')
    elif tr >= 50:
        tips.append(f'训练成功率 {tr}%，下周保持同一难度，把每次时长压到 5 分钟')
    else:
        tips.append(f'训练成功率仅 {tr}%，下周退回到上一个难度，拆分动作重教')

    pr = stats['potty_rate']
    if pr is None:
        tips.append('开始用打卡记录每次定点排便的成/败，才能看出规律')
    elif pr < 80:
        tips.append(f'定点成功率 {pr}%，重点检查：间隔是否太久、饭后是否漏带、定点是否太远')
    else:
        tips.append(f'定点成功率 {pr}%，可以开始把尿垫往门口移动，为户外如厕过渡')

    if stats['avg_stool'] and stats['avg_stool'] >= 5:
        tips.append(f'平均便便评分 {stats["avg_stool"]}，偏软，先别换粮、先减零食')
    else:
        tips.append('继续保持定时定量投喂，每 2 周称一次体重并录入')

    return tips[:3]
