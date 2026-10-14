# -*- coding: utf-8 -*-
"""清空所有业务数据（保留知识库）
用法：python reset.py        —— 清空狗狗、记录、免疫记录
     python reset.py all    —— 连知识库一起清空并重新灌入内置底表
"""
import sys

import app as A
import db as DB

conn = DB.connect()
DB.init_db(conn)
conn.executescript(
    'DELETE FROM care_events;'
    'DELETE FROM health_records;'
    'DELETE FROM dogs;'
    "DELETE FROM sqlite_sequence WHERE name IN ('dogs','care_events','health_records');"
)
if len(sys.argv) > 1 and sys.argv[1] == 'all':
    conn.execute('DELETE FROM knowledge')
    conn.commit()
    A.seed_health_columns(conn)
    print('已清空全部数据，并重建知识库')
else:
    conn.commit()
    print('已清空狗狗与记录（知识库保留）')
conn.close()
