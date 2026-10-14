# -*- coding: utf-8 -*-
"""联网检索与正文提取

流程：关键词 → 搜索引擎 → 结果列表（带可信度打分）
     → 抓取选中页面 → 提取正文 → 切分候选知识条目 → 人工确认入库

设计原则（对应联网检索模块）：
- 每条结论必须带来源，来源必须可追溯
- 搜索引擎只用来找线索，事实以抓取到的正文为准
- 信源按可信度分级，低可信来源明确标注"来源可靠性一般"
- 抓取失败不阻塞，如实返回失败原因
"""
import re
import time
import ssl
from urllib.parse import urlparse, quote

import requests
from bs4 import BeautifulSoup

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
HEADERS = {
    'User-Agent': UA,
    'Accept': ('text/html,application/xhtml+xml,application/xml;q=0.9,'
               'image/avif,image/webp,image/apng,*/*;q=0.8'),
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Cache-Control': 'max-age=0',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'cross-site',
    'Sec-Fetch-User': '?1',
    'sec-ch-ua': '"Chromium";v="120", "Not(A:Brand";v="24", "Google Chrome";v="120"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
}
TIMEOUT = 12
MAX_FETCH = 6

# 实测抓取不到的站点（反爬严格），不浪费重试，直接提示人工打开
BLOCKED_HOSTS = ['zhihu.com', 'zhuanlan.zhihu.com', 'mp.weixin.qq.com',
                 'xiaohongshu.com', 'douyin.com', 'bilibili.com',
                 'weibo.com', 'toutiao.com', 'baijiahao.baidu.com']
# 非文章类页面，直接排除
JUNK_HOSTS = ['image.baidu.com', 'v.baidu.com', 'tieba.baidu.com',
              'map.baidu.com', 'zhidao.baidu.com', 'wenku.baidu.com',
              'tv.sohu.com', 'v.qq.com', 'youtube.com',
              'douban.com', 'apps.apple.com', 'play.google.com',
              'y.qq.com', 'music.163.com', 'taobao.com', 'jd.com']


def make_session():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def is_blocked(url):
    host = (urlparse(url).netloc or '').lower()
    return any(b in host for b in BLOCKED_HOSTS)


def is_junk(url):
    host = (urlparse(url).netloc or '').lower()
    path = (urlparse(url).path or '').lower()
    if any(b in host for b in JUNK_HOSTS):
        return True
    if re.search(r'\.(jpg|jpeg|png|gif|webp|pdf|zip|rar|mp4|mp3)$', path):
        return True
    if '/search' in path or 'list.php' in path:
        return True
    return False


# ---------------------------------------------------------------- 信源分级
TRUST_HIGH = [
    'edu.cn', '.edu/', 'ac.cn', 'gov.cn', 'org.cn',
    'kepuchina.cn', 'kepuchina.org', 'msdmanuals', 'kmjqjd.com',
    'ucdavis.edu', 'osu.edu', 'cornell.edu', 'avma.org', 'wsava.org',
    'vcahospitals.com', 'petmd.com', 'akc.org', 'aspca.org',
    'isdpp.com', 'moguvet.com', 'pubmed', 'cnki.net', 'sciencedirect',
    'springer', 'nature.com', 'vetmed', 'vetstreet.com', 'pets.webmd.com',
]
TRUST_MID = [
    'zhihu.com', 'boqii.com', 'chongwu', 'petkit', 'royalcanin', 'hillspet',
    'preventivevet.com', 'thesprucepets.com', 'greencross', 'petplace',
    'dogtime.com', 'puipi.com', 'maohai.org', 'ptpet.com', 'a-pets.com',
    'wtopets.com', 'petselect', 'ack-pet.com', 'cqpet.net', 'hlcwfw.cn',
]
TRUST_LOW = [
    'baijiahao', 'sohu.com', 'toutiao', '163.com', 'sina.com',
    'tieba.baidu', 'zhidao.baidu', 'douyin', 'xiaohongshu', 'bilibili',
    'iask', 'wenda', 'jingyan.baidu',
]

TRUST_LABEL = {
    'high': ('可信', 'ok', '兽医学院 / 官方机构 / 科研科普 / 执业兽医平台'),
    'mid': ('中等', 'warn', '垂直宠物媒体 / 专业训犬机构 / 品牌官方'),
    'low': ('偏低', 'danger', '自媒体 / 问答 / 聚合站 —— 来源可靠性一般，需交叉验证'),
    'unknown': ('未知', '', '域名未在信源白名单中，自行判断'),
}


def trust_of(url):
    d = (urlparse(url).netloc or '').lower()
    full = url.lower()
    for k in TRUST_HIGH:
        if k in full:
            return 'high'
    for k in TRUST_LOW:
        if k in full:
            return 'low'
    for k in TRUST_MID:
        if k in full:
            return 'mid'
    if d.endswith('.tw') or d.endswith('.hk'):
        return 'mid'
    return 'unknown'


def trust_score(url, title='', snippet=''):
    level = trust_of(url)
    base = {'high': 40, 'mid': 22, 'low': 8, 'unknown': 12}[level]
    txt = (title or '') + ' ' + (snippet or '')
    for kw, add in [('官方', 8), ('指南', 6), ('科普', 8), ('兽医', 6),
                    ('执业', 6), ('大学', 6), ('研究', 5), ('规范', 5),
                    ('广告', -10), ('优惠', -8), ('购买', -8)]:
        if kw in txt:
            base += add
    return base


# ---------------------------------------------------------------- 搜索
def _clean(s):
    return re.sub(r'\s+', ' ', (s or '')).strip()


def search_bing(query, limit=10):
    r = make_session().get('https://cn.bing.com/search',
                           params={'q': query, 'count': '30',
                                   'mkt': 'zh-CN', 'setlang': 'zh-CN',
                                   'ensearch': '0'},
                           timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'lxml')
    out = []
    for it in soup.select('li.b_algo'):
        a = it.select_one('h2 a')
        if not a or not a.get('href'):
            continue
        cap = it.select_one('.b_caption p') or it.select_one('p')
        out.append({
            'title': _clean(a.get_text()),
            'url': a['href'],
            'snippet': _clean(cap.get_text()) if cap else '',
        })
        if len(out) >= limit:
            break
    return out


def search_baidu(query, limit=10):
    r = make_session().get('https://www.baidu.com/s',
                           params={'wd': query, 'rn': '30'},
                           timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, 'lxml')
    out = []
    for it in soup.select('.c-container'):
        a = it.select_one('h3 a') or it.select_one('a')
        if not a:
            continue
        url = it.get('mu') or a.get('href') or ''
        if not url.startswith('http'):
            continue
        abs_ = it.select_one('.c-abstract') or it.select_one('[class*=content-right]')
        out.append({
            'title': _clean(a.get_text()),
            'url': url,
            'snippet': _clean(abs_.get_text())[:300] if abs_ else '',
        })
        if len(out) >= limit:
            break
    return out


# ---------------------------------------------------------------- 相关性过滤
def keywords(q):
    """把查询拆成用于相关性判断的词"""
    q = (q or '').strip()
    parts = [p for p in re.split(r'[\s,，、。；;+/|]+', q) if len(p) >= 2]
    grams = []
    for p in parts:
        if len(p) > 3 and re.match(r'^[\u4e00-\u9fa5]+$', p):
            grams += [p[i:i + 2] for i in range(len(p) - 1)]
    return parts, list(dict.fromkeys(grams))


def is_relevant(query, title, snippet):
    parts, grams = keywords(query)
    txt = (title or '') + ' ' + (snippet or '')
    if not parts:
        return True
    if any(p in txt for p in parts):
        return True
    return sum(1 for g in grams if g in txt) >= 2


def search_web(query, engine='auto', limit=10):
    """返回 (结果列表, 错误信息)。auto = 双引擎合并去重"""
    query = (query or '').strip()
    if not query:
        return [], '关键词不能为空'

    rows, errors = [], []
    engines = [(search_bing, 'Bing'), (search_baidu, '百度')]
    if engine == 'bing':
        engines = engines[:1]
    elif engine == 'baidu':
        engines = engines[1:]

    seen = set()
    for fn, name in engines:
        try:
            got = fn(query, limit * 2)
        except Exception as e:
            errors.append(f'{name} 失败：{type(e).__name__}')
            continue
        if not got:
            errors.append(f'{name} 无结果')
            continue
        for x in got:
            if x['url'] in seen:
                continue
            if is_junk(x['url']):
                continue
            if not is_relevant(query, x['title'], x['snippet']):
                continue
            seen.add(x['url'])
            x['engine'] = name
            x['trust'] = trust_of(x['url'])
            x['score'] = trust_score(x['url'], x['title'], x['snippet'])
            x['blocked'] = is_blocked(x['url'])
            rows.append(x)

    rows.sort(key=lambda x: (-x['score'], x['blocked']))
    if not rows:
        return [], '；'.join(errors) or '没有找到相关结果，换个说法再试'
    return rows[:limit], ''



# ---------------------------------------------------------------- 正文提取
DROP_TAGS = ['script', 'style', 'noscript', 'nav', 'header', 'footer',
             'aside', 'form', 'iframe', 'svg', 'button']
MAIN_SELECTORS = [
    'article', '.rich_media_content', '.article-content', '.article_content',
    '.post-content', '.entry-content', '.content-body', '#js_content',
    '.artical-content', '.detail-content', '.news_content', '.TRS_Editor',
    '#content', '.content', 'main',
]


def fetch_article(url):
    """抓取网页并提取标题与正文段落。返回 dict"""
    res = {'url': url, 'ok': False, 'title': '', 'paragraphs': [],
           'text': '', 'error': '', 'trust': trust_of(url)}
    if is_blocked(url):
        res['error'] = ('该站点反爬严格（需登录或有风控），本系统不抓取。'
                        '请手动打开链接阅读，再手工入库')
        return res

    sess = make_session()
    try:
        p = urlparse(url)
        home = f'{p.scheme}://{p.netloc}/'
        try:
            sess.get(home, timeout=8)          # 预热拿 cookie
            sess.headers['Referer'] = home
        except Exception:
            pass
        r = sess.get(url, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        if r.encoding in (None, 'ISO-8859-1'):
            r.encoding = r.apparent_encoding or 'utf-8'
        html = r.text
    except Exception as e:
        res['error'] = f'{type(e).__name__}: {str(e)[:110]}'
        return res

    try:
        soup = BeautifulSoup(html, 'lxml')
    except Exception:
        soup = BeautifulSoup(html, 'html.parser')

    t = soup.find('title')
    res['title'] = _clean(t.get_text()) if t else ''

    for tag in soup(DROP_TAGS):
        tag.decompose()

    node = None
    for sel in MAIN_SELECTORS:
        cand = soup.select_one(sel)
        if cand and len(cand.get_text(strip=True)) > 300:
            node = cand
            break
    if node is None:
        # 兜底：取文字最多的 div
        best, best_len = None, 0
        for div in soup.find_all('div'):
            n = len(div.get_text(strip=True))
            if n > best_len:
                best, best_len = div, n
        node = best or soup.body or soup

    paras = []
    for p in node.find_all(['p', 'li']):
        txt = _clean(p.get_text())
        if 12 <= len(txt) <= 500:
            paras.append(txt)
    if not paras:
        raw = _clean(node.get_text())
        paras = [s for s in re.split(r'[。！？\n]', raw) if 12 <= len(s) <= 500]

    # 去重保序
    seen, out = set(), []
    for p in paras:
        k = p[:40]
        if k in seen:
            continue
        seen.add(k)
        out.append(p)

    res['paragraphs'] = out[:200]
    res['text'] = '\n'.join(out)
    res['ok'] = len(out) >= 3
    if not res['ok']:
        res['error'] = '正文提取失败或内容过短（可能是动态加载页面）'
    return res


# ---------------------------------------------------------------- 候选条目生成
TOPIC_RULES = [
    ('免疫', ['疫苗', '免疫', '狂犬', '多联', '六联', '八联', '接种', '抗体', '驱虫', '寄生虫']),
    ('喂养', ['喂食', '喂养', '狗粮', '幼犬粮', '喂量', '粮量', '热量', '营养', '断奶', '奶粉',
              '泡软', '每日', '餐', '蛋白', '钙']),
    ('排泄', ['排便', '大小便', '如厕', '尿垫', '定点', '便便', '腹泻', '软便', '憋尿', '排泄']),
    ('训练', ['训练', '口令', '坐下', '召回', '随行', '社会化', '奖励', '正向', '等待', '笼']),
    ('饮食', ['禁忌', '不能吃', '中毒', '巧克力', '葡萄', '洋葱', '木糖醇', '有毒', '禁食',
              '人食', '盐']),
    ('行为', ['吠叫', '咬', '分离焦虑', '扑人', '护食', '拆家', '啃咬', '攻击', '恐惧']),
    ('健康', ['体温', '呕吐', '就医', '症状', '检查', '皮肤病', '关节', '肥胖', '体重']),
]

KEY_HINT = ['应', '需', '必须', '不要', '禁止', '建议', '每周', '每天', '每次',
            '小时', '分钟', '月龄', '周龄', '克', '毫升', '天']


def classify(text):
    best, best_hits = '其他', 0
    for cat, kws in TOPIC_RULES:
        hits = sum(1 for k in kws if k in text)
        if hits > best_hits:
            best, best_hits = cat, hits
    return best, best_hits


def extract_candidates(article, max_items=12):
    """把正文段落转成候选知识条目"""
    out = []
    src_title = article.get('title') or ''
    host = urlparse(article['url']).netloc
    for p in article.get('paragraphs', []):
        if len(p) < 18 or len(p) > 260:
            continue
        cat, hits = classify(p)
        if hits == 0:
            continue
        score = hits * 10
        if any(k in p for k in KEY_HINT):
            score += 12
        if re.search(r'\d', p):
            score += 8
        for bad in ['点击', '关注', '广告', '微信', '公众号', '版权', '转载', '优惠']:
            if bad in p:
                score -= 15
        if score < 20:
            continue
        # 主题 = 这条命中的关键词
        kws = []
        for c, ks in TOPIC_RULES:
            if c == cat:
                kws = [k for k in ks if k in p]
                break
        topic = '、'.join(kws[:3]) or (src_title[:40] and src_title[:40]) or host
        out.append({
            'category': cat,
            'topic': topic,
            'conclusion': p,
            'source': host,
            'url': article['url'],
            'trust': article.get('trust', 'unknown'),
            'score': score,
            'article': src_title[:60],
        })
    out.sort(key=lambda x: -x['score'])
    return out[:max_items]


def fetch_and_extract(urls, per_page=6):
    """批量抓取 + 提取。返回 (候选列表, 抓取报告)"""
    cands, report = [], []
    for u in urls[:MAX_FETCH]:
        art = fetch_article(u)
        report.append({
            'url': u, 'ok': art['ok'], 'title': art['title'][:80],
            'paras': len(art['paragraphs']), 'error': art['error'],
            'trust': art['trust'],
        })
        if art['ok']:
            cands.extend(extract_candidates(art, per_page))
        time.sleep(0.4)          # 别把人家站点打疼
    cands.sort(key=lambda x: -x['score'])
    return cands, report
