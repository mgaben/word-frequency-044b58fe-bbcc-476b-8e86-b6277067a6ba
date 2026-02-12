from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from api.models import KeywordsRequest, WordFrequency
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
            "/word-frequency": "GET - Analyze word frequencies"
        }
    }


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/word-frequency", response_model=WordFrequency)
async def word_frequency(article: str, depth: int):
    try:
        async with WikipediaAnalyzer() as analyzer:
            await analyzer.crawl(article, 0, 1)
            stats = analyzer.calculate_statistics()

            response = WordFrequency(
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
