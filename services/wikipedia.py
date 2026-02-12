import re

from collections import Counter
from urllib.parse import unquote

import httpx

from bs4 import BeautifulSoup

from utils.logger import get_logger


logger = get_logger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


class WikipediaAnalyzer:
    """Class to handle Wikipedia crawling and text extraction."""
    def __init__(self):
        self._wikipedia_url = "https://en.wikipedia.org/wiki/" 
        self.client = httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
            headers={"User-Agent": "Mozilla/5.0 (compatible; WordFrequencyBot/1.0; +https://github.com/)"},
        )
        self.visited_articles = set()
        self.word_counter = Counter()

    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()
    
    @property
    def wikipedia_url(self):
        return self._wikipedia_url

    def _extract_text_from_html(self, html_content: str) -> str:
        """Extract clean text from Wikipedia HTML"""
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # Remove unwanted elements
            for element in soup.find_all(['script', 'style', 'sup', 'table', 'img']):
                element.decompose()
            
            # Get text from main content
            text = soup.get_text(separator=' ', strip=True)
            return text
        except Exception as e:
            logger.error(f"Error extracting text from HTML: {e}")
            return ""
    

    def _normalize_title(self, title: str) -> str:
        """Normalize Wikipedia article titles for consistent processing."""
        return unquote(title.strip().replace(' ', '_')).lower()

    def _tokenize_text(self, text: str) -> list[str]: 
        """Tokenize text into words, removing punctuation and normalizing case."""
        words = re.findall(r"[a-z0-9]+(?:'[a-z]+)*", text.lower())
        return words

    async def fetch_article(self, title: str) -> str:
        """Fetch the text content of a Wikipedia article by title."""
        url = self.wikipedia_url + title.replace(' ', '_')
        for attempt in range(3):
            try:
                logger.info(f"Fetching article: {title} (attempt {attempt + 1})")
                response = await self.client.get(url)

                if response.status_code == 200:
                    return response.text
                elif response.status_code == 404:
                    logger.warning(f"Article not found: {title}")
                    return ""
                else:
                    logger.error(f"Error fetching article {title}: {response.status_code}")
            except httpx.RequestError as e:
                logger.error(f"Request error for article {title}: {e}")
            return ""
        

    def _extract_links(self, html_content: str) -> list[str]:
        """Extract internal Wikipedia links from HTML"""
        
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            content = soup.find('div', id='bodyContent')
            if not content:
                return []
            links = []

            for link in content.find_all('a', href=True):
                href = link['href']
                if href.startswith('/wiki/') and ':' not in href:
                    article_name = href[len('/wiki/'):]
                    links.append(article_name)
            
            return links
        except Exception as e:
            logger.error(f"Error extracting links: {e}")
            return []
    

    async def crawl(self, article: str, current_depth: int, depth: int) -> None:
        """Crawl Wikipedia starting from *article* up to *depth* levels.

        Returns a list of article text contents. Uses a visited set to
        avoid processing the same article twice.
        """
        normalized_title = self._normalize_title(article)
        if normalized_title in self.visited_articles: 
            return
        
        if current_depth > depth:
            return
            
        self.visited_articles.add(normalized_title)
        html_content = await self.fetch_article(article)
        if not html_content:
            logger.warning(f"No content for article: {article}")
            return
        
        text = self._extract_text_from_html(html_content)
        words = self._tokenize_text(text)
        self.word_counter.update(words)

        if current_depth < depth:
            links = self._extract_links(html_content)

            for link in links[:3]:
                await self.crawl(link, current_depth + 1, depth)

    def calculate_statistics(self):
        """Calculate word frequency statistics"""
        total_words = sum(self.word_counter.values())
        
        if total_words == 0:
            return {
                'word_count': {},
                'word_percentage': {},
                'total_words': 0
            }
        
        word_percentages = {
            word: (count / total_words) * 100
            for word, count in self.word_counter.items()
        }
        
        return {
            'word_count': dict(self.word_counter),
            'word_percentage': word_percentages,
            'total_words': total_words
        }
    
    def filter_by_percentile(
        self,
        percentile: int,
        ignore_list: list[str]
    ) -> dict:
        """Filter results by percentile and ignore list"""
        stats = self.calculate_statistics()
        
        if not stats['word_count']:
            return {
                **stats,
                'filtered_words': 0
            }
        
        # Calculate percentile threshold
        counts = sorted(stats['word_count'].values(), reverse=True)
        if percentile == 100:
            threshold = counts[0] if counts else 0
        elif percentile == 0:
            threshold = 0
        else:
            index = int(len(counts) * (1 - percentile / 100))
            threshold = counts[min(index, len(counts) - 1)]
        
        # Filter words
        ignore_set = set(ignore_list)
        filtered_count = {
            word: count
            for word, count in stats['word_count'].items()
            if count >= threshold and word not in ignore_set
        }
        
        filtered_percentage = {
            word: stats['word_percentage'][word]
            for word in filtered_count.keys()
        }
        
        return {
            'word_count': filtered_count,
            'word_percentage': filtered_percentage,
            'total_words': stats['total_words'],
            'filtered_words': len(filtered_count)
        }

    

async def run():
    article = "Python (programming language)"
    try:
        async with WikipediaAnalyzer() as analyzer:
            await analyzer.crawl(article, 0, 1)
            print(analyzer.filter_by_percentile(98, ["bezae"])["word_count"])
    except Exception as e:
        logger.error(f"{e}")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run())