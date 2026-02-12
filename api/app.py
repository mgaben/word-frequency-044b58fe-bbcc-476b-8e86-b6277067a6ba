from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from api.models import KeywordsRequest, KeywordFrequencyResponse
from utils.logger import get_logger
from services.wikipedia import WikipediaAnalyzer

logger = get_logger(__name__)

app = FastAPI(
    title="Wikipedia Word-Frequency Analyzer",
    description="Analyze word frequencies across Wikipedia articles with depth traversal",
    version="1.0.0"
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
    try:
        async with WikipediaAnalyzer() as analyzer:
            await analyzer.crawl(article, 0, max_depth)
            stats = analyzer.calculate_statistics()

            response = KeywordFrequencyResponse(
                word_count=stats['word_count'],
                word_percentage=stats['word_percentage']
            )

            logger.info(f"Analysis complete")
            
            return response
            
    except Exception as e:
        logger.error(f"Error in word-frequency endpoint: {e}", exc_info=True)
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
        
        async with WikipediaAnalyzer() as analyzer:
            await analyzer.crawl(request.article, 0, request.depth)
            filtered_stats = analyzer.filter_by_percentile(
                request.percentile,
                request.ignore_list
            )
            
            response = KeywordFrequencyResponse(
                word_count=filtered_stats['word_count'],
                word_percentage=filtered_stats['word_percentage']
            )
            
            return response
            
    except Exception as e:
        logger.error(f"Error in keywords endpoint: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error during analysis: {str(e)}"
        )
