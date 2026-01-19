import uvicorn
from fastapi import FastAPI
from api.routes import truth, articles, opinions
from core.scheduler import start_scheduler
from core.logging import init_logging
from db.init_db import init_db
from dotenv import load_dotenv
from ml.embeddings import load_embedding_model
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()
def create_app() -> FastAPI:
    init_logging()

    app = FastAPI(
        title="Blockchain Truth Engine",
        version="1.0.0"
    )
    
    origins = [
        "*",  # your Next.js frontend
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,  # allows requests from these domains
        allow_credentials=True,
        allow_methods=["*"],    # GET, POST, PUT, DELETE
        allow_headers=["*"],    # allow all headers
    )
    # API Routes
    app.include_router(truth.router, prefix="/truth", tags=["Truth"])
    app.include_router(articles.router, tags=["Articles"])
    app.include_router(opinions.router, tags=["Opinions"])

    @app.on_event("startup")
    async def startup():
        init_db()
        load_embedding_model()  
        start_scheduler()

    return app

app = create_app()

@app.get("/")
def health():
    return {"status": "ok"}

# if __name__ == "__main__":
#     uvicorn.run(
#         "main:app",
#         host="0.0.0.0",
#         port=8000,
#         reload=True
#     )