from fastapi import FastAPI

app = FastAPI(
    title="Geospatial File Measurement API",
    description="API for uploading geospatial files and retrieving measurements.",
    version="0.1.0",
)


@app.get("/")
def read_root():
    return {"message": "Geospatial File Measurement API is running"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
