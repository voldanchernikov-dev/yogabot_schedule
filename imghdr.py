# imghdr.py — совместимость для Python 3.13+
import pathlib
import mimetypes

def what(file, h=None):
    file = pathlib.Path(file)
    mime, _ = mimetypes.guess_type(file)
    if mime and mime.startswith("image/"):
        return mime.split("/")[1]
    return None
