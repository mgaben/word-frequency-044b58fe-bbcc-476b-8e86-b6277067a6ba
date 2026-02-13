from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from api.models import KeywordsRequest, KeywordFrequencyResponse
from utils.logger import get_logger
from services.wikipedia import WikipediaAnalyzer, DEFAULT_TIMEOUT

logger = get_logger(__name__)

http_client: httpx.AsyncClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    http_client = httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        headers={"User-Agent": "Mozilla/5.0 (compatible; WordFrequencyBot/1.0; +https://github.com/)"},
    )
    logger.info("HTTP client initialized")
    yield
    await http_client.aclose()
    logger.info("HTTP client closed")


app = FastAPI(
    title="Wikipedia Word-Frequency Analyzer",
    description="Analyze word frequencies across Wikipedia articles with depth traversal",
    version="1.0.0",
    lifespan=lifespan,
)

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    logger.warning(f"HTTP {exc.status_code}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

@app.get("/")
async def root():
    """Root endpoint with API information"""
    logger.info("Serving root endpoint")
    return {
        "name": "Wikipedia Word-Frequency Analyzer",
        "version": "1.0.0",
        "endpoints": {
            "/word-frequency": "GET - Analyze word frequencies",
            "/keywords": "POST - Get filtered keywords by percentile"
        }
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/word-frequency", response_model=KeywordFrequencyResponse)
async def word_frequency(
    article: str = Query(..., min_length=1, description="Wikipedia article title"), 
    max_depth: int = Query(..., ge=0, le=10, description="Traversal depth")
):
    logger.info(f"Starting word-frequency analysis for '{article}' with depth {max_depth}")
    try:
        async with WikipediaAnalyzer(client=http_client) as analyzer:
            await analyzer.crawl(article, 0, max_depth)
            stats = analyzer.calculate_statistics()

            response = KeywordFrequencyResponse(
                word_count=stats['word_count'],
                word_percentage=stats['word_percentage']
            )

            logger.info(
                f"Word-frequency analysis complete for '{article}': "
                f"{stats['total_words']} total words, "
                f"{len(stats['word_count'])} unique words, "
                f"{len(analyzer.visited_articles)} articles processed"
            )

            return response

    except Exception as e:
        logger.error(f"Error in word-frequency endpoint for '{article}': {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during analysis: {str(e)}"
        )

@app.post("/keywords", response_model=KeywordFrequencyResponse)
async def get_keywords(request: KeywordsRequest):
    """
    Get filtered keywords based on percentile threshold and ignore list.
    Returns filtered word counts and percentages.
    """
    try:
        logger.info(
            f"Starting keywords analysis for '{request.article}' with depth {request.depth}, "
            f"percentile {request.percentile}, ignoring {len(request.ignore_list)} words"
        )
        
        async with WikipediaAnalyzer(client=http_client) as analyzer:
            await analyzer.crawl(request.article, 0, request.depth)
            filtered_stats = analyzer.filter_by_percentile(
                request.percentile,
                request.ignore_list
            )
            
            response = KeywordFrequencyResponse(
                word_count=filtered_stats['word_count'],
                word_percentage=filtered_stats['word_percentage']
            )

            logger.info(
                f"Keywords analysis complete for '{request.article}': "
                f"{filtered_stats['filtered_words']} keywords filtered from "
                f"{filtered_stats['total_words']} total words, "
                f"{len(analyzer.visited_articles)} articles processed"
            )

            return response
            
    except Exception as e:
        logger.error(f"Error in keywords endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during analysis: {str(e)}"
        )
