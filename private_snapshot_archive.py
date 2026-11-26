"""Offline byte-preserving archive and restore of a closed, qualified snapshot.

Requires operator-approved private POSIX storage and a separately trusted audit SHA.
No network, no uploads, no runtime pointer change. Never use a live SQLite file.
"""
import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path
from build_combined import require,sha,check_integrity

ROOT=Path(__file__).resolve().parent
DB="facilitysignal.sqlite3"
AUDIT="recovery-audit.json"
NAMES={DB,AUDIT}
MAX_AUDIT=1024*1024
MAX_DB=4*1024**3

def private_directory(path):
    require(path.is_dir() and not path.is_symlink(),"private directory required")
    path=path.resolve()
    require(path!=ROOT and ROOT not in path.parents,"never store snapshot in repository")
    require(os.name=="posix" and path.stat().st_uid==os.getuid() and path.stat().st_mode&0o077==0,"owner-only POSIX directory required")
    return path

def regular(path):
    require(path.is_file() and not path.is_symlink(),"regular file required")

def audit_bytes(raw,expected):
    require(len(raw)<=MAX_AUDIT and hashlib.sha256(raw).hexdigest()==expected,"trusted audit SHA mismatch")
    a=json.loads(raw)
    require(type(a["database_bytes"]) is int and 0<a["database_bytes"]<=MAX_DB,"database size bound")
    d=a["database_sha256"]
    require(isinstance(d,str) and len(d)==64 and all(c in "0123456789abcdef" for c in d),"database SHA format")
    return a

def validate(folder,expected):
    for name in NAMES:regular(folder/name)
    require({p.name for p in folder.iterdir()}==NAMES,"snapshot must be closed and contain only database and recovery audit")
    p=folder/AUDIT
    require(p.stat().st_size<=MAX_AUDIT,"audit size bound")
    a=audit_bytes(p.read_bytes(),expected)
    db=folder/DB
    require(db.stat().st_size==a["database_bytes"] and sha(db)==a["database_sha256"],"database bytes differ")
    with closing(sqlite3.connect(db.as_uri()+"?mode=ro&immutable=1",uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        check_integrity(conn)
    require(sha(db)==a["database_sha256"] and sha(p)==expected,"snapshot changed during verification")
    return a

def unpack(archive,folder,expected):
    regular(archive)
    require(archive.stat().st_size<=MAX_DB+MAX_AUDIT+65536,"archive size bound")
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist()
        require(len(entries)==2 and {i.filename for i in entries}==NAMES,"unexpected archive membership")
        require(all(i.compress_type==zipfile.ZIP_STORED and not i.flag_bits&1 and stat.S_ISREG(i.external_attr>>16) for i in entries),"archive member type")
        info=z.getinfo(AUDIT)
        require(info.file_size<=MAX_AUDIT,"audit size bound")
        raw=z.read(info);a=audit_bytes(raw,expected)
        require(z.getinfo(DB).file_size==a["database_bytes"],"archive DB size mismatch")
        with z.open(DB) as src,(folder/DB).open("xb") as dst:
            os.fchmod(dst.fileno(),0o600)
            shutil.copyfileobj(src,dst,1024*1024);dst.flush();os.fsync(dst.fileno())
        with (folder/AUDIT).open("xb") as dst:
            os.fchmod(dst.fileno(),0o600);dst.write(raw);dst.flush();os.fsync(dst.fileno())
    return validate(folder,expected)

def sync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def backup(source,destination,expected):
    source=private_directory(source);parent=private_directory(destination.parent)
    destination=parent/destination.name
    require(not destination.exists() and not destination.is_symlink(),"destination already exists")
    a=validate(source,expected)
    with tempfile.TemporaryDirectory(prefix=".snapshot-archive-",dir=parent) as t:
        root=Path(t);archive=root/"snapshot.zip";check=root/"check";check.mkdir(mode=0o700)
        with zipfile.ZipFile(archive,"x",compression=zipfile.ZIP_STORED,allowZip64=True) as z:
            for name in sorted(NAMES):z.write(source/name,name)
        os.chmod(archive,0o600)
        unpack(archive,check,expected)
        validate(source,expected)
        with archive.open("rb") as f:os.fsync(f.fileno())
        digest=sha(archive)
        # Atomic no-clobber publication on the same private filesystem.
        os.link(archive,destination)
        sync_dir(parent)
    return {"archive_sha256":digest,"database_sha256":a["database_sha256"],"audit_sha256":expected}

def restore(archive,destination,expected,archive_sha):
    parent=private_directory(destination.parent);private_directory(archive.parent)
    archive=archive.resolve() if not archive.is_symlink() else archive
    regular(archive);require(sha(archive)==archive_sha,"trusted archive SHA mismatch")
    destination=parent/destination.name
    require(not destination.exists() and not destination.is_symlink(),"destination already exists")
    with tempfile.TemporaryDirectory(prefix=".snapshot-restore-",dir=parent) as t:
        stage=Path(t);a=unpack(archive,stage,expected)
        require(sha(archive)==archive_sha,"archive changed during restore")
        # Exclusive new directory; audit appears last as readiness marker.
        # No runtime points here automatically. A crash may leave a partial
        # directory; never treat one without the trusted audit as ready.
        destination.mkdir(mode=0o700)
        try:
            for name in (DB,AUDIT):os.link(stage/name,destination/name)
            sync_dir(destination);sync_dir(parent)
        except BaseException:
            for name in NAMES:
                (destination/name).unlink(missing_ok=True)
            destination.rmdir()
            raise
    return {"archive_sha256":archive_sha,"database_sha256":a["database_sha256"],"audit_sha256":expected}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("action",choices=("backup","restore"))
    p.add_argument("--source",type=Path,required=True);p.add_argument("--destination",type=Path,required=True)
    p.add_argument("--trusted-audit-sha256",required=True);p.add_argument("--trusted-archive-sha256")
    p.add_argument("--authorized-private-storage",action="store_true")
    a=p.parse_args()
    require(a.authorized_private_storage,"explicit authorization of private storage required")
    if a.action=="backup":result=backup(a.source,a.destination,a.trusted_audit_sha256)
    else:
        require(a.trusted_archive_sha256,"trusted archive SHA required")
        result=restore(a.source,a.destination,a.trusted_audit_sha256,a.trusted_archive_sha256)
    print(json.dumps(result),flush=True)

if __name__=="__main__":main()
