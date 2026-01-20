from pydantic import BaseModel
from typing import List
from datetime import datetime

class ArticleOut(BaseModel):
    id: int
    title: str
    excerpt: str
    image: str
    slug: str
    date: str
    source: str
    url: str
    summary: str
    country: str
    class Config:
        from_attributes  = True


class HomeArticlesResponse(BaseModel):
    featuredArticle: ArticleOut
    sideArticles: list[ArticleOut]
    storyCards: list[ArticleOut]
    articleListItems: list[ArticleOut]
    
class PaginatedArticlesOut(BaseModel):
    items: List[ArticleOut]
    page: int
    page_size: int
    total: int
    total_pages: int