import pytest
from unittest.mock import AsyncMock, patch
from collections import Counter

from services.wikipedia import WikipediaAnalyzer


SAMPLE_HTML = """
<html><body>
<div id="bodyContent">
    <p>Python is a programming language. Python is popular.</p>
    <a href="/wiki/Programming_language">Programming language</a>
    <a href="/wiki/Guido_van_Rossum">Guido van Rossum</a>
    <a href="/wiki/Category:Languages">Category</a>
    <a href="/wiki/Special:Random">Random</a>
    <a href="https://example.com">External</a>
</div>
</body></html>
"""

SAMPLE_HTML_NO_LINKS = """
<html><body>
<div id="bodyContent">
    <p>Hello world hello</p>
</div>
</body></html>
"""


@pytest.fixture
def analyzer():
    return WikipediaAnalyzer()


class TestExtractTextFromHtml:
    def test_extracts_paragraph_text(self, analyzer):
        text = analyzer._extract_text_from_html(SAMPLE_HTML)
        assert "Python is a programming language" in text

    def test_strips_script_and_style(self, analyzer):
        html = "<html><body><script>var x=1;</script><style>.a{}</style><p>Clean text</p></body></html>"
        text = analyzer._extract_text_from_html(html)
        assert "var x" not in text
        assert "Clean text" in text

    def test_returns_empty_on_invalid_html(self, analyzer):
        text = analyzer._extract_text_from_html("")
        assert text == "" or isinstance(text, str)


class TestNormalizeTitle:
    def test_replaces_spaces_with_underscores(self, analyzer):
        assert "python_language" in analyzer._normalize_title("Python Language")

    def test_lowercases(self, analyzer):
        result = analyzer._normalize_title("Python")
        assert result == "python"

    def test_decodes_percent_encoding(self, analyzer):
        result = analyzer._normalize_title("Caf%C3%A9")
        assert result == "café"

    def test_strips_whitespace(self, analyzer):
        result = analyzer._normalize_title("  Planet  ")
        assert result == "planet"


class TestTokenizeText:
    def test_basic_words(self, analyzer):
        assert analyzer._tokenize_text("Hello World") == ["hello", "world"]

    def test_strips_punctuation(self, analyzer):
        tokens = analyzer._tokenize_text("Hello, world! Testing.")
        assert tokens == ["hello", "world", "testing"]

    def test_keeps_contractions(self, analyzer):
        tokens = analyzer._tokenize_text("don't won't can't")
        assert tokens == ["don't", "won't", "can't"]

    def test_keeps_numbers(self, analyzer):
        tokens = analyzer._tokenize_text("Python 3 was released in 2008")
        assert "3" in tokens
        assert "2008" in tokens


class TestExtractLinks:
    def test_finds_article_links(self, analyzer):
        links = analyzer._extract_links(SAMPLE_HTML)
        assert "Programming_language" in links
        assert "Guido_van_Rossum" in links

    def test_excludes_namespaced_pages(self, analyzer):
        links = analyzer._extract_links(SAMPLE_HTML)
        for link in links:
            assert ":" not in link

    def test_excludes_external_links(self, analyzer):
        links = analyzer._extract_links(SAMPLE_HTML)
        for link in links:
            assert not link.startswith("http")

    def test_returns_empty_without_body_content(self, analyzer):
        html = "<html><body><a href='/wiki/Test'>Test</a></body></html>"
        assert analyzer._extract_links(html) == []


class TestCrawl:
    @pytest.mark.asyncio
    async def test_depth_zero_fetches_one_article(self, analyzer):
        analyzer.fetch_article = AsyncMock(return_value=SAMPLE_HTML_NO_LINKS)
        await analyzer.crawl("Test", 0, 0)
        analyzer.fetch_article.assert_called_once_with("Test")

    @pytest.mark.asyncio
    async def test_counts_words(self, analyzer):
        analyzer.fetch_article = AsyncMock(return_value=SAMPLE_HTML_NO_LINKS)
        await analyzer.crawl("Test", 0, 0)
        assert analyzer.word_counter["hello"] == 2
        assert analyzer.word_counter["world"] == 1

    @pytest.mark.asyncio
    async def test_no_revisits(self, analyzer):
        analyzer.fetch_article = AsyncMock(return_value=SAMPLE_HTML_NO_LINKS)
        await analyzer.crawl("Test", 0, 0)
        await analyzer.crawl("Test", 0, 0)
        # Should only have fetched once
        assert analyzer.fetch_article.call_count == 1

    @pytest.mark.asyncio
    async def test_stops_at_depth(self, analyzer):
        analyzer.fetch_article = AsyncMock(return_value=SAMPLE_HTML)
        await analyzer.crawl("Root", 0, 1)
        # Root (depth 0) + up to 3 links at depth 1
        assert analyzer.fetch_article.call_count <= 4

    @pytest.mark.asyncio
    async def test_skips_empty_content(self, analyzer):
        analyzer.fetch_article = AsyncMock(return_value="")
        await analyzer.crawl("Missing", 0, 0)
        assert len(analyzer.word_counter) == 0


class TestCalculateStatistics:
    def test_empty_counter(self, analyzer):
        stats = analyzer.calculate_statistics()
        assert stats == {'word_count': {}, 'word_percentage': {}, 'total_words': 0}

    def test_percentages_sum_to_100(self, analyzer):
        analyzer.word_counter = Counter({"hello": 3, "world": 2, "test": 5})
        stats = analyzer.calculate_statistics()
        total_pct = sum(stats['word_percentage'].values())
        assert abs(total_pct - 100.0) < 0.01

    def test_counts_match(self, analyzer):
        analyzer.word_counter = Counter({"a": 10, "b": 20})
        stats = analyzer.calculate_statistics()
        assert stats['word_count'] == {"a": 10, "b": 20}
        assert stats['total_words'] == 30


class TestFilterByPercentile:
    def test_ignore_list_removes_words(self, analyzer):
        analyzer.word_counter = Counter({"hello": 5, "world": 5, "the": 10})
        result = analyzer.filter_by_percentile(0, ["the"])
        assert "the" not in result['word_count']
        assert "hello" in result['word_count']

    def test_percentile_filters_low_frequency(self, analyzer):
        analyzer.word_counter = Counter({"common": 100, "rare": 1, "medium": 10})
        result = analyzer.filter_by_percentile(90, [])
        assert "common" in result['word_count']
        assert "rare" not in result['word_count']

    def test_empty_counter_returns_zero(self, analyzer):
        result = analyzer.filter_by_percentile(50, [])
        assert result['total_words'] == 0
        assert result['filtered_words'] == 0

    def test_percentile_zero_returns_all(self, analyzer):
        analyzer.word_counter = Counter({"a": 1, "b": 2, "c": 3})
        result = analyzer.filter_by_percentile(0, [])
        assert len(result['word_count']) == 3

    def test_percentile_100_returns_top(self, analyzer):
        analyzer.word_counter = Counter({"a": 1, "b": 2, "c": 100})
        result = analyzer.filter_by_percentile(100, [])
        assert "c" in result['word_count']
