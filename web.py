import os
from fastapi.responses import FileResponse

def frontend():
    return FileResponse(
        os.path.join(os.path.dirname(__file__), 'index.html'),
        headers={'Cache-Control': 'no-store, max-age=0'},
    )
