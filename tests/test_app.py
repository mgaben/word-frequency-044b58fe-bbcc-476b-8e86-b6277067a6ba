import pytest

from unittest.mock import AsyncMock, Mock, patch

from httpx import ASGITransport, AsyncClient

from api.app import app


MOCK_STATS = {
    'word_count': {'python': 5, 'language': 3},
    'word_percentage': {'python': 62.5, 'language': 37.5},
    'total_words': 8,
}

MOCK_FILTERED_STATS = {
    **MOCK_STATS,
    'filtered_words': 1,
    'word_count': {'python': 5},
    'word_percentage': {'python': 100.0},
}


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


def _mock_analyzer(stats):
    """Create a mock WikipediaAnalyzer that returns the given stats."""
    analyzer = AsyncMock()
    # calculate_statistics and filter_by_percentile are sync methods — use Mock
    analyzer.calculate_statistics = Mock(return_value=stats)
    analyzer.filter_by_percentile = Mock(return_value=stats)
    analyzer.visited_articles = {"test_article"}
    analyzer.__aenter__ = AsyncMock(return_value=analyzer)
    analyzer.__aexit__ = AsyncMock(return_value=False)
    return analyzer


class TestHealth:
    @pytest.mark.asyncio
    async def test_returns_ok(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestRoot:
    @pytest.mark.asyncio
    async def test_returns_api_info(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert "endpoints" in data


class TestWordFrequency:
    @pytest.mark.asyncio
    @patch("api.app.WikipediaAnalyzer")
    async def test_returns_word_counts(self, mock_class, client):
        mock_class.return_value = _mock_analyzer(MOCK_STATS)
        resp = await client.get("/word-frequency?article=Python&max_depth=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["word_count"]["python"] == 5
        assert data["word_percentage"]["python"] == 62.5

    @pytest.mark.asyncio
    @patch("api.app.WikipediaAnalyzer")
    async def test_calls_crawl_with_correct_args(self, mock_class, client):
        analyzer = _mock_analyzer(MOCK_STATS)
        mock_class.return_value = analyzer
        await client.get("/word-frequency?article=Planet&max_depth=2")
        analyzer.crawl.assert_called_once_with("Planet", 0, 2)

    @pytest.mark.asyncio
    async def test_missing_article_returns_422(self, client):
        resp = await client.get("/word-frequency?max_depth=1")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_depth_returns_422(self, client):
        resp = await client.get("/word-frequency?article=Python")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_negative_depth_returns_422(self, client):
        resp = await client.get("/word-frequency?article=Python&max_depth=-1")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_depth_over_limit_returns_422(self, client):
        resp = await client.get("/word-frequency?article=Python&max_depth=11")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @patch("api.app.WikipediaAnalyzer")
    async def test_internal_error_returns_500(self, mock_class, client):
        analyzer = _mock_analyzer(MOCK_STATS)
        analyzer.crawl.side_effect = RuntimeError("connection failed")
        mock_class.return_value = analyzer
        resp = await client.get("/word-frequency?article=Python&max_depth=0")
        assert resp.status_code == 500


class TestKeywords:
    @pytest.mark.asyncio
    @patch("api.app.WikipediaAnalyzer")
    async def test_returns_filtered_keywords(self, mock_class, client):
        mock_class.return_value = _mock_analyzer(MOCK_FILTERED_STATS)
        resp = await client.post("/keywords", json={
            "article": "Python",
            "depth": 1,
            "ignore_list": ["the", "a"],
            "percentile": 90,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "python" in data["word_count"]

    @pytest.mark.asyncio
    @patch("api.app.WikipediaAnalyzer")
    async def test_passes_percentile_and_ignore_list(self, mock_class, client):
        analyzer = _mock_analyzer(MOCK_FILTERED_STATS)
        mock_class.return_value = analyzer
        await client.post("/keywords", json={
            "article": "Test",
            "depth": 0,
            "ignore_list": ["the"],
            "percentile": 50,
        })
        analyzer.filter_by_percentile.assert_called_once_with(50, ["the"])

    @pytest.mark.asyncio
    async def test_missing_body_returns_422(self, client):
        resp = await client.post("/keywords")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_missing_fields_returns_422(self, client):
        resp = await client.post("/keywords", json={"article": "Python"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    @patch("api.app.WikipediaAnalyzer")
    async def test_internal_error_returns_500(self, mock_class, client):
        analyzer = _mock_analyzer(MOCK_FILTERED_STATS)
        analyzer.crawl.side_effect = RuntimeError("timeout")
        mock_class.return_value = analyzer
        resp = await client.post("/keywords", json={
            "article": "Python",
            "depth": 0,
            "ignore_list": [],
            "percentile": 50,
        })
        assert resp.status_code == 500
