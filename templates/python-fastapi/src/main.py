from fastapi import FastAPI

app = FastAPI(title="CNP App")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return {"message": "Hello from CNP!"}
