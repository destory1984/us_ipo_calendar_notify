"""미국 IPO 목록 모으기 (나스닥 IPO 캘린더, 키 필요 없음)

python ipo_fetch.py                  # 상장 예정 (앞으로 잡힌 것만)
python ipo_fetch.py -s filed         # 이번 달 신청 접수 건 (날짜 없는 상장 후보)
python ipo_fetch.py --csv ipo.csv    # CSV로 저장
python ipo_fetch.py --telegram       # 텔레그램으로도 보내기
python ipo_fetch.py --telegram --new-only   # 지난번에 보내지 않은 새 종목만 보내기

구역(-s): priced(상장 완료) upcoming(상장 예정) filed(신청 접수) withdrawn(철회)
나스닥 캘린더지만 NYSE 상장 건도 들어 있다.
"""
import argparse, csv, datetime, html, json, os, sys, urllib.parse, urllib.request

from sic_ko import sic_ko

URL = 'https://api.nasdaq.com/api/ipo/calendar?date={}'
DEAL_URL = 'https://api.nasdaq.com/api/ipo/overview/?dealId={}'
SEC_URL = 'https://data.sec.gov/submissions/CIK{}.json'
COLS = ['section', 'symbol', 'company', 'industry', 'exchange', 'price', 'shares', 'amount', 'date']


def get_json(url, ua='Mozilla/5.0'):
    req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept': 'application/json'})
    return json.load(urllib.request.urlopen(req, timeout=20))


def fetch_month(ym):
    return get_json(URL.format(ym))['data']


def industry_of(deal_id):
    # 나스닥 상세에서 CIK를 얻고, SEC에 등록된 업종(SIC) 이름을 읽는다
    try:
        cik = get_json(DEAL_URL.format(deal_id))['data']['poOverview']['SECCIK']['value']
        sec = get_json(SEC_URL.format(cik.zfill(10)), ua='ipo-fetch/1.0 (personal research script)')
        return sic_ko(sec.get('sic'), sec.get('sicDescription') or '')
    except Exception:
        return ''


def rows_of(data, section):
    block = data.get(section) or {}
    if section == 'upcoming':
        block = block.get('upcomingTable') or {}
    for r in block.get('rows') or []:
        yield {
            'section': section,
            'deal_id': r.get('dealID') or '',
            'industry': '',
            'symbol': r.get('proposedTickerSymbol') or '',
            'company': r.get('companyName') or '',
            'exchange': r.get('proposedExchange') or '',
            'price': r.get('proposedSharePrice') or '',
            'shares': r.get('sharesOffered') or '',
            'amount': r.get('dollarValueOfSharesOffered') or '',
            'date': r.get('pricedDate') or r.get('expectedPriceDate') or r.get('withdrawDate') or r.get('filedDate') or '',
        }


def is_spac(r):
    # SPAC은 이름에 Acquisition/Merger가 붙거나, 거의 다 공모가 10달러로 나온다
    name = r['company'].lower()
    return ('acquisition' in name or 'merger' in name or 'spac' in name
            or r['price'] == '10.00' or r['industry'].startswith('SPAC'))


def months_back(n):
    d = datetime.date.today().replace(day=1)
    out = []
    for _ in range(n):
        out.append(d.strftime('%Y-%m'))
        d = (d - datetime.timedelta(days=1)).replace(day=1)
    return out


def date_key(r):
    try:
        return datetime.datetime.strptime(r['date'], '%m/%d/%Y')
    except ValueError:
        return datetime.datetime.min


def drop_past(rows, today):
    # 날짜가 지났는데 상장 예정에 남은 건(가격 미정, 나스닥 갱신 지연)을 뺀다. 날짜를 못 읽으면 남긴다
    return [r for r in rows
            if r['section'] != 'upcoming' or date_key(r) == datetime.datetime.min or date_key(r).date() >= today]


SENT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sent_ipos.json')
SENT_KEEP_DAYS = 180


def row_key(r):
    # 종목 코드는 비거나 바뀔 수 있어 나스닥 dealID를 먼저 쓴다
    return r['deal_id'] or f"{r['section']}|{r['symbol']}|{r['company']}"


def new_rows(rows, sent):
    return [r for r in rows if row_key(r) not in sent]


def mark_sent(sent, rows, today):
    for r in rows:
        sent.setdefault(row_key(r), today.isoformat())


def prune(sent, today, days=SENT_KEEP_DAYS):
    cut = (today - datetime.timedelta(days=days)).isoformat()
    return {k: v for k, v in sent.items() if v >= cut}


def load_sent(path):
    try:
        with open(path, encoding='utf-8') as fp:
            return json.load(fp)
    except FileNotFoundError:
        return {}


def save_sent(path, sent):
    with open(path, 'w', encoding='utf-8') as fp:
        json.dump(sent, fp, ensure_ascii=False, indent=1, sort_keys=True)


def main():
    p = argparse.ArgumentParser(description='미국 IPO 목록 (나스닥 캘린더)')
    p.add_argument('-m', '--months', type=int, default=1, help='이번 달부터 거슬러 몇 달 (기본 1)')
    p.add_argument('-s', '--sections', nargs='+', default=['upcoming'],
                   choices=['priced', 'upcoming', 'filed', 'withdrawn'])
    p.add_argument('--no-spac', action='store_true', help='SPAC(Acquisition Corp) 빼기')
    p.add_argument('--no-industry', action='store_true', help='업종 조회 건너뛰기 (건마다 요청 2번이라 목록이 길면 느리다)')
    p.add_argument('--csv', help='CSV 파일로 저장')
    p.add_argument('--telegram', action='store_true', help='결과를 텔레그램으로 보내기 (환경변수 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)')
    p.add_argument('--new-only', action='store_true',
                   help='텔레그램으로 이미 보낸 종목 빼기 (기록: sent_ipos.json, 텔레그램 발송 성공 때만 남긴다)')
    a = p.parse_args()

    seen, rows = set(), []
    for ym in months_back(a.months):
        try:
            data = fetch_month(ym)
        except Exception as e:
            print(f'{ym} 가져오기 실패: {e}', file=sys.stderr)
            continue
        for s in a.sections:
            # 상장 예정은 어느 달을 물어도 같은 목록이 오므로 한 번만 담는다
            for r in rows_of(data, s):
                key = (s, r['symbol'], r['company'])
                if key in seen:
                    continue
                if a.no_spac and is_spac(r):
                    continue
                seen.add(key)
                rows.append(r)

    today = datetime.date.today()
    rows = drop_past(rows, today)
    if a.new_only:
        sent = prune(load_sent(SENT_PATH), today)
        rows = new_rows(rows, sent)
    rows.sort(key=date_key, reverse=True)

    if not a.no_industry:
        for r in rows:
            if r['deal_id']:
                r['industry'] = industry_of(r['deal_id'])
        if a.no_spac:
            rows = [r for r in rows if not is_spac(r)]

    if a.csv:
        with open(a.csv, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=COLS, extrasaction='ignore')
            w.writeheader()
            w.writerows(rows)
        print(f'{len(rows)}건 -> {a.csv}')
        return

    for r in rows:
        print(f"{r['date']:>10}  {r['section']:<9} {r['symbol']:<6} {r['price']:>11}  {r['amount']:>16}  {r['company'][:36]:<36}  {r['industry']}")
    print(f'\n총 {len(rows)}건')

    if a.telegram:
        send_telegram(telegram_text(rows, a.sections, a.new_only))
        print('텔레그램 보냄')
        # 보내기에 성공했을 때만 기록한다. 손으로 돌려 본 결과가 일요일 알림을 가로채지 않게 한다
        if a.new_only:
            mark_sent(sent, rows, today)
            save_sent(SENT_PATH, sent)


SECTION_KO = {'priced': '상장 완료', 'upcoming': '상장 예정', 'filed': '신청 접수', 'withdrawn': '철회'}


def short_amount(s):
    try:
        v = float(s.replace('$', '').replace(',', ''))
    except ValueError:
        return ''
    return f'{v / 1e8:.1f}억 달러' if v >= 1e8 else f'{v / 1e6:.0f}백만 달러'


def telegram_text(rows, sections, new_only=False):
    title = '·'.join(SECTION_KO[s] for s in sections) + (' 새 종목' if new_only else '')
    head = f"<b>미국 IPO {title}</b> ({datetime.date.today():%m/%d} 기준, {len(rows)}건)"
    if not rows:
        return head + ('\n\n지난번 이후 새 종목 없음.' if new_only else '\n\n잡혀 있는 건이 없습니다.')
    lines = [head]
    for r in rows:
        tag = '' if len(sections) == 1 else f" [{SECTION_KO[r['section']]}]"
        detail = ' · '.join(x for x in [r['industry'], f"${r['price']}" if r['price'] else '', short_amount(r['amount'])] if x)
        lines.append(f"\n<b>{html.escape(r['date'])}  {html.escape(r['symbol'] or '-')}</b>{tag}\n"
                     f"{html.escape(r['company'])}\n{html.escape(detail)}")
    return '\n'.join(lines)


def send_telegram(text):
    token, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat:
        sys.exit('환경변수 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 가 없습니다')
    # 텔레그램 한 메시지는 4096자까지라 빈 줄 단위로 끊어 보낸다
    chunks, cur = [], ''
    for block in text.split('\n\n'):
        if cur and len(cur) + len(block) + 2 > 4000:
            chunks.append(cur)
            cur = block
        else:
            cur = f'{cur}\n\n{block}' if cur else block
    chunks.append(cur)
    for c in chunks:
        body = urllib.parse.urlencode({'chat_id': chat, 'text': c, 'parse_mode': 'HTML',
                                       'disable_web_page_preview': 'true'}).encode()
        try:
            urllib.request.urlopen(f'https://api.telegram.org/bot{token}/sendMessage', body, timeout=20)
        except Exception as e:
            # 오류 메시지에 토큰이 든 주소가 섞여 나오지 않게 한다
            sys.exit(f'텔레그램 보내기 실패: {type(e).__name__} {getattr(e, "code", "")}'.strip())


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
