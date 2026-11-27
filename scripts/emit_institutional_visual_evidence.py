"""Emit compact public-only screenshot evidence for actual visual review."""
import base64,hashlib,os
from pathlib import Path
root=Path(os.environ.get("RUNNER_TEMP","/tmp"))/"institutional-browser-evidence"
for width in (390,768,1024,1440):
    for view in ("filters","profile","service-topic-asc","service-topic-dialysis"):
        name=f"{width}-{view}.jpg"
        path=root/name
        if not path.is_file():raise ValueError("missing required screenshot")
        raw=path.read_bytes()
        if not 0<len(raw)<300000:raise ValueError("screenshot size out of scope")
        encoded=base64.b64encode(raw).decode("ascii")
        chunks=[encoded[i:i+2400] for i in range(0,len(encoded),2400)]
        print("PUBLIC_VISUAL_BEGIN",name,len(chunks),hashlib.sha256(raw).hexdigest(),flush=True)
        for i,chunk in enumerate(chunks):print("PUBLIC_VISUAL_CHUNK",name,i,chunk,flush=True)
        print("PUBLIC_VISUAL_END",name,flush=True)
