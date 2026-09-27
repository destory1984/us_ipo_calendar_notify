import datetime, os, tempfile, unittest

import ipo_fetch as f


def row(section='upcoming', date='10/01/2026', deal_id='', symbol='ABC', company='Abc Inc.'):
    return {'section': section, 'date': date, 'deal_id': deal_id, 'symbol': symbol, 'company': company,
            'industry': '', 'exchange': '', 'price': '', 'shares': '', 'amount': ''}


TODAY = datetime.date(2026, 9, 27)


class DropPast(unittest.TestCase):
    def test_drops_upcoming_before_today(self):
        rows = [row(date='09/25/2026'), row(date='09/27/2026'), row(date='10/02/2026')]
        self.assertEqual([r['date'] for r in f.drop_past(rows, TODAY)], ['09/27/2026', '10/02/2026'])

    def test_keeps_unparsable_date(self):
        self.assertEqual(len(f.drop_past([row(date='')], TODAY)), 1)

    def test_keeps_other_sections(self):
        self.assertEqual(len(f.drop_past([row(section='priced', date='09/01/2026')], TODAY)), 1)


class RowKey(unittest.TestCase):
    def test_uses_deal_id(self):
        self.assertEqual(f.row_key(row(deal_id='123-4')), '123-4')

    def test_falls_back_without_deal_id(self):
        self.assertEqual(f.row_key(row()), 'upcoming|ABC|Abc Inc.')


class NewRows(unittest.TestCase):
    def test_keeps_only_unsent(self):
        rows = [row(deal_id='1'), row(deal_id='2')]
        self.assertEqual([r['deal_id'] for r in f.new_rows(rows, {'1': '2026-09-20'})], ['2'])


class Sent(unittest.TestCase):
    def test_prune_drops_old(self):
        sent = {'old': '2026-03-01', 'new': '2026-09-01'}
        self.assertEqual(f.prune(sent, TODAY), {'new': '2026-09-01'})

    def test_mark_sent_keeps_first_date(self):
        sent = {'1': '2026-09-20'}
        f.mark_sent(sent, [row(deal_id='1'), row(deal_id='2')], TODAY)
        self.assertEqual(sent, {'1': '2026-09-20', '2': '2026-09-27'})

    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'sent.json')
            self.assertEqual(f.load_sent(path), {})
            f.save_sent(path, {'1': '2026-09-27'})
            self.assertEqual(f.load_sent(path), {'1': '2026-09-27'})


class TelegramText(unittest.TestCase):
    def test_new_only_empty(self):
        self.assertIn('새 종목 없음', f.telegram_text([], ['upcoming'], new_only=True))


if __name__ == '__main__':
    unittest.main()
