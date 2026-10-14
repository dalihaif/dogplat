# -*- coding: utf-8 -*-
"""数据库连接与建表"""
import os
import shutil
import sqlite3
from datetime import datetime

from flask import g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.dirname(os.environ['DOGPLAT_DB']) if os.environ.get('DOGPLAT_DB') else os.path.join(BASE_DIR, 'data')
# 上传的图片/视频落这里（不是 static，走 /media 路由按需读取）
UPLOAD_DIR = os.environ.get('DOGPLAT_UPLOADS') or os.path.join(DATA_DIR, 'uploads')
# 可用环境变量 DOGPLAT_DB 指向别的库文件（自检/测试用，避免污染真实数据）
DB_PATH = os.environ.get('DOGPLAT_DB') or os.path.join(DATA_DIR, 'dogplat.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS dogs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    breed_cn          TEXT,
    breed_en          TEXT,
    sex               TEXT,
    birth_date        TEXT,
    arrive_date       TEXT,
    weight_current    REAL,
    weight_updated_at TEXT,
    neutered          TEXT,
    chip_no           TEXT,
    license_no        TEXT,
    owner_name        TEXT,
    owner_phone       TEXT,
    coat_color        TEXT,
    shoulder_height   REAL,
    personality_tags  TEXT,
    purchase_source   TEXT,
    -- 父母信息（血统追溯用）
    sire_name         TEXT,
    sire_breed        TEXT,
    sire_chip         TEXT,
    dam_name          TEXT,
    dam_breed         TEXT,
    dam_chip          TEXT,
    parents_note      TEXT,
    -- 管理状态：在养 / 送人 / 死亡 / 走失 / 其他
    status            TEXT DEFAULT '在养',
    status_changed_at TEXT,
    note              TEXT,
    active            INTEGER DEFAULT 1,   -- 兼容旧字段，等于 status=='在养'
    created_at        TEXT
);

-- 狗狗状态变更流水（改了什么、为什么、什么时候）
CREATE TABLE IF NOT EXISTS dog_status_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    dog_id     INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT,
    note       TEXT,
    changed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dsl_dog ON dog_status_log(dog_id, changed_at);

CREATE TABLE IF NOT EXISTS care_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    dog_id     INTEGER NOT NULL,
    day        TEXT NOT NULL,
    time       TEXT,
    type       TEXT NOT NULL,
    payload    TEXT,
    note       TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ce_dog_day ON care_events(dog_id, day);

CREATE TABLE IF NOT EXISTS health_records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    dog_id      INTEGER NOT NULL,
    kind        TEXT,
    dose_no     TEXT,
    happen_date TEXT,
    next_due    TEXT,
    vet         TEXT,
    note        TEXT,
    created_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_hr_dog ON health_records(dog_id);

-- 狗狗日记：一条日记可带多张图片/视频（媒体另存 diary_media）
CREATE TABLE IF NOT EXISTS dog_diary (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    dog_id     INTEGER NOT NULL,
    day        TEXT NOT NULL,
    title      TEXT,
    mood       TEXT,
    place      TEXT,
    content    TEXT,
    created_at TEXT,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_diary_dog_day ON dog_diary(dog_id, day);

-- 日记媒体：图片 / 视频，文件落在 data/uploads 下，这里只存相对路径与元信息
CREATE TABLE IF NOT EXISTS diary_media (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    diary_id   INTEGER NOT NULL,
    dog_id     INTEGER NOT NULL,
    kind       TEXT,          -- image / video
    path       TEXT,          -- 相对 data/uploads 的路径
    thumb      TEXT,          -- 图片缩略图相对路径（视频为空）
    orig_name  TEXT,          -- 上传时的原始文件名（含中文）
    mime       TEXT,
    size       INTEGER,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_dm_diary ON diary_media(diary_id);

-- 狗狗记账：买用品、洗澡、打针等各类消费
CREATE TABLE IF NOT EXISTS dog_expense (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    dog_id     INTEGER NOT NULL,
    day        TEXT NOT NULL,
    category   TEXT,
    item       TEXT,
    amount     REAL DEFAULT 0,
    qty        REAL,
    unit       TEXT,
    shop       TEXT,
    pay_method TEXT,
    note       TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_ex_dog_day ON dog_expense(dog_id, day);

CREATE TABLE IF NOT EXISTS knowledge (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    category   TEXT,
    topic      TEXT,
    conclusion TEXT,
    source     TEXT,
    url        TEXT,
    age_range  TEXT,
    fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    k TEXT PRIMARY KEY,
    v TEXT
);
"""

# 老库补列（ALTER TABLE 不写默认值，才能识别出"还没迁移过"的行）
NEW_DOG_COLUMNS = [
    ('sire_name', 'TEXT'), ('sire_breed', 'TEXT'), ('sire_chip', 'TEXT'),
    ('dam_name', 'TEXT'), ('dam_breed', 'TEXT'), ('dam_chip', 'TEXT'),
    ('parents_note', 'TEXT'),
    ('status', 'TEXT'), ('status_changed_at', 'TEXT'),
]


def _db_file_of(conn):
    """取连接当前指向的库文件路径（迁移前备份要用）"""
    try:
        for row in conn.execute('PRAGMA database_list').fetchall():
            if row[1] == 'main':
                return row[2]
    except sqlite3.Error:
        pass
    return None


def migrate(conn):
    """给已存在的库补新字段，并把旧的 active 标记翻译成 status。

    幂等：重复跑不会重复写日志，也不会重复备份。
    """
    cols = {r[1] for r in conn.execute('PRAGMA table_info(dogs)').fetchall()}
    if not cols:
        return

    missing = [n for n, _ in NEW_DOG_COLUMNS if n not in cols]
    if missing:
        # 动结构之前先留一份完整备份，出事能回滚
        src = _db_file_of(conn)
        if src and os.path.exists(src):
            dst = f'{src}.bak_before_migrate_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
            try:
                shutil.copy2(src, dst)
                print(f'[migrate] 升级前已备份数据库 → {os.path.basename(dst)}')
            except OSError as e:
                print(f'[migrate] 备份失败，继续升级：{e}')

    for name, ddl in NEW_DOG_COLUMNS:
        if name not in cols:
            conn.execute(f'ALTER TABLE dogs ADD COLUMN {name} {ddl}')

    # 还没定过状态的行：按旧的 active 翻译过来
    legacy = conn.execute(
        'SELECT id, name, active FROM dogs WHERE status IS NULL').fetchall()
    for r in legacy:
        new_status = '在养' if r['active'] else '其他'
        conn.execute(
            'UPDATE dogs SET status=?, status_changed_at=? WHERE id=?',
            (new_status, datetime.now().strftime('%Y-%m-%d %H:%M'), r['id']))
        conn.execute(
            'INSERT INTO dog_status_log (dog_id, old_status, new_status, note, changed_at)'
            ' VALUES (?,?,?,?,?)',
            (r['id'], '旧「已归档」标记', new_status,
             '由旧版的「在养 / 已归档」开关自动换算，请按实际情况改成送人 / 死亡 / 走失等',
             datetime.now().strftime('%Y-%m-%d %H:%M')))
    conn.commit()



def connect():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def get_db():
    if 'db' not in g:
        g.db = connect()
    return g.db


def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db(conn=None):
    own = conn is None
    if own:
        conn = connect()
    conn.executescript(SCHEMA)
    migrate(conn)
    conn.commit()
    if own:
        conn.close()
