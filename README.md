# Wikipedia Word-Frequency Analyzer

API that crawls Wikipedia articles to a given depth and returns word frequency statistics.

## Run with Docker

```bash
docker build -t word-frequency .
docker run -p 8000:8000 word-frequency
```

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## Local Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# Copy and configure environment variables
cp .env.example .env

# Start dev server with hot reload
uv run uvicorn api.app:app --reload

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=services --cov=api --cov=utils --cov-report=term-missing
```

## API Endpoints

### GET /word-frequency

Returns word counts and percentages for a Wikipedia article and its linked articles.

```
GET /word-frequency?article=Python_(programming_language)&max_depth=1
```

| Parameter  | Type   | Description                          |
|------------|--------|--------------------------------------|
| article    | string | Wikipedia article title              |
| max_depth  | int    | Crawl depth (0-10)                   |

### POST /keywords

Returns filtered word frequencies, excluding specified words and filtered by percentile.

```json
POST /keywords
{
    "article": "Python_(programming_language)",
    "depth": 1,
    "ignore_list": ["the", "a", "is"],
    "percentile": 90
}
```

## Environment Variables

| Variable        | Default                              | Description              |
|-----------------|--------------------------------------|--------------------------|
| WIKIPEDIA_URL   | https://en.wikipedia.org/wiki/       | Base URL for Wikipedia   |
| FETCH_RETRY     | 3                                    | Retry attempts per fetch |
