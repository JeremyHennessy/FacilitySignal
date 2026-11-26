"""Read actual public FRS ZIP headers and structural metadata only."""
import csv,io,json,tempfile,zipfile
from pathlib import Path
from scripts import archive_epa_frs_healthcare as frs
with tempfile.TemporaryDirectory(prefix="frs-schema-only-") as d:
    p=Path(d)/"source.zip";meta=frs.download(p)
    with zipfile.ZipFile(p) as z:
        ms=frs.members(z)
        out={}
        for name,info in ms.items():
            with z.open(info) as raw,io.TextIOWrapper(raw,encoding="utf-8-sig",newline="") as f:
                header=next(csv.reader(f,strict=True))
            out[name]={"headers":header,"uncompressed_bytes":info.file_size,"crc32":format(info.CRC,"08x")}
    print("FRS_SCHEMA_DIAGNOSTIC",json.dumps({"publisher":meta,"members":out},sort_keys=True),flush=True)
