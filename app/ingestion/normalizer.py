from readability import Document
from bs4 import BeautifulSoup

def normalize(html: str) -> str:
    #print("normalize html", html)
    doc = Document(html)
    #print("normalize doc", doc)
    soup = BeautifulSoup(doc.summary(), "lxml")
    print("normalize soup", soup)
    return soup.get_text(" ", strip=True)