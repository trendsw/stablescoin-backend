from sqlalchemy import *
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Article(Base):
    __tablename__ = "articles"
    id = Column(Integer, primary_key=True)
    title = Column(Text)
    content = Column(Text)
    url = Column(Text, unique=True)
    publish_date = Column(DateTime)
    source = Column(Text)
    country = Column(Text)
    credibility_score = Column(Float)
    topic_cluster_id = Column(Integer, ForeignKey("truth_clusters.id"))

class Claim(Base):
    __tablename__ = "claims"
    id = Column(Integer, primary_key=True)
    article_id = Column(Integer, ForeignKey("articles.id"))
    claim_text = Column(Text)
    claim_type = Column(Enum("fact","prediction","opinion","speculation", name="claim_type_enum"))
    sentiment = Column(Enum("positive","negative","neutral", name="sentiment_enum"))

class TruthCluster(Base):
    __tablename__ = "truth_clusters"
    id = Column(Integer, primary_key=True)
    topic_summary = Column(Text)
    final_truth_summary = Column(Text)
    confidence_score = Column(Float)

class ClaimSupport(Base):
    __tablename__ = "claim_support"
    id = Column(Integer, primary_key=True)
    cluster_id = Column(Integer)
    claim_id = Column(Integer)
    support_type = Column(Enum("supporting","contradicting", name="support_type_enum"))
    
class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        if self.parent.setdefault(x, x) != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra