from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import fetch_intraday_primary_sources as producer


class Page:
    def __init__(self, value):
        self.value = value

    def extract_text(self):
        return self.value


class Reader:
    metadata = None

    def __init__(self, text):
        self.pages = [Page(text)]


class SourceIdentityTests(unittest.TestCase):
    def test_matching_original_identity_and_global_eighty_word_quote_bound(self):
        source = producer.SOURCES[0]
        text = ('Beat the Market Intraday Momentum Zarattini Aziz Barbon '
                'sigma ' + 'method ' * 70 + ' vwap ' + 'method ' * 70 +
                ' commission ' + 'method ' * 70 + ' out-of-sample ' + 'method ' * 70)
        result, full = producer.pdf_details(b'%PDF synthetic', source, lambda stream: Reader(text))
        self.assertTrue(result['title_verified_by_tokens'])
        self.assertTrue(result['authors_verified_by_surnames'])
        self.assertLessEqual(result['quoted_word_count'], 80)
        self.assertEqual(result['quoted_word_count'], sum(len(row['text'].split()) for row in result['excerpts']))
        self.assertIn('PAGE 1', full)
        self.assertFalse(result['human_full_paper_review_completed'])

    def test_student_replication_with_real_author_names_is_not_original_paper(self):
        text = ('Financial Data Analysis course assignment Common Risk Factors in Cryptocurrency '
                'Liu Tsyvinski Wu submitted by a student replication and extension')
        with self.assertRaisesRegex(ValueError, 'identity mismatch'):
            producer.pdf_details(b'%PDF synthetic', producer.SOURCES[2], lambda stream: Reader(text))

    def test_html_error_and_oversized_bodies_are_not_original_pdfs(self):
        for raw in (b'<html>403</html>', b'%PDF' + b'x' * producer.MAX_BYTES):
            with self.assertRaisesRegex(ValueError, 'bounded actual PDF'):
                producer.pdf_details(raw, producer.SOURCES[0])

    def test_missing_text_needs_ocr_instead_of_fake_method_review(self):
        with self.assertRaisesRegex(ValueError, 'extractable text'):
            producer.pdf_details(b'%PDF synthetic', producer.SOURCES[0], lambda stream: Reader(''))

    def test_unknown_redirect_host_refuses_storage(self):
        class Response:
            status = 200

            def __enter__(self): return self
            def __exit__(self, *args): return None
            def geturl(self): return 'https://unrelated.example/paper.pdf'
            def read(self, count): return b'%PDF synthetic'

        with TemporaryDirectory() as temporary, patch.object(producer, 'urlopen', return_value=Response()):
            result = producer.acquire(producer.SOURCES[0], Path(temporary))
            self.assertFalse(result['accepted_original_pdf'])
            self.assertEqual(list(Path(temporary).iterdir()), [])

    def test_failed_identity_cannot_store_unrelated_copyrighted_body(self):
        class Response:
            status = 200

            def __enter__(self): return self
            def __exit__(self, *args): return None
            def geturl(self): return producer.SOURCES[0]['url']
            def read(self, count): return b'%PDF synthetic'

        with TemporaryDirectory() as temporary, patch.object(producer, 'urlopen', return_value=Response()), \
                patch.object(producer, 'pdf_details', side_effect=ValueError('identity mismatch')):
            result = producer.acquire(producer.SOURCES[0], Path(temporary))
            self.assertFalse(result['accepted_original_pdf'])
            self.assertEqual(list(Path(temporary).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
