from fastapi import FastAPI
from starlette.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles
import os

app = FastAPI()

# # Mount the 'dist' directory at the root of your app
# app.mount("/", StaticFiles(directory="./dist"), name="dist")
@app.get("/")
async def root():
    if os.path.isfile('dist/index.html'):
        return FileResponse('dist/index.html')
    else:
        raise HTTPException(status_code=404)

app.mount("/", StaticFiles(directory="dist"), name="dist")