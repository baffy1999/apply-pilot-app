from fastapi import FastAPI

from api.resumes import router as resumes_router


app = FastAPI(title="Apply Pilot API")
app.include_router(resumes_router)
