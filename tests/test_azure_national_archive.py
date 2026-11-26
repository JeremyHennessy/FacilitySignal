import io,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import azure_national_archive as a
class Store:
    def __init__(self,private=True):self.data={};self.counter=0;self.is_private=private;self.deleted=[];self.corrupt=False
    def private(self):
        if not self.is_private:raise ValueError("public")
    def exists(self,n):return n in self.data
    def create(self,n,s,size,kind):
        a.allowed_name(n)
        if n in self.data:raise ValueError("exists")
        data=s.read()
        if len(data)!=size:raise ValueError("size")
        self.counter+=1;e=str(self.counter);self.data[n]=(data,e);return e
    def head(self,n):
        d,e=self.data[n];return {"bytes":len(d),"etag":e}
    def chunks(self,n,e):
        d,t=self.data[n]
        if e!=t:raise ValueError("etag")
        yield b"x"*len(d) if self.corrupt else d
    def delete_probe(self,n,e):
        if not n.startswith(a.PREFIX+"/_probes/") or self.head(n)["etag"]!=e:raise ValueError("delete")
        self.deleted.append(n);del self.data[n]
    def list(self,p):
        for n,(d,e) in self.data.items():
            if n.startswith(p+"/"):yield {"name":n,"bytes":len(d),"etag":e}
class Tests(unittest.TestCase):
    run="bootstrap-123-1"
    def test_destination_and_path(self):
        env={"AZURE_STORAGE_ACCOUNT":"pharm3r","AZURE_STORAGE_CONTAINER":"data","AZURE_STORAGE_PREFIX":"CMS Facility Demo","AZURE_STORAGE_KEY":"synthetic"}
        a.destination(env)
        for name in ("towersignal-data/releases/a","CMS Facility Demo/../other","CMS Facility Demo/unapproved","CMS Facility Demo/releases/bootstrap-1-1/../bad"):
            with self.assertRaises(ValueError):a.allowed_name(name)
        with self.assertRaises(ValueError):a.destination({**env,"AZURE_STORAGE_PREFIX":"towersignal-data"})
    def test_probe(self):
        s=Store();a.preflight(s,self.run);self.assertEqual(len(s.deleted),1);self.assertEqual(s.data,{})
    def test_public_denied(self):
        s=Store(False)
        with self.assertRaises(ValueError):a.preflight(s,self.run)
        self.assertEqual(s.data,{})
    def test_existing_pointer_denied(self):
        s=Store();a.put_bytes(s,a.POINTER,b"old")
        with self.assertRaises(ValueError):a.preflight(s,self.run)
        self.assertEqual(s.data[a.POINTER][0],b"old")
    def test_corruption_fails_closed(self):
        s=Store();s.corrupt=True
        with self.assertRaises(ValueError):a.preflight(s,self.run)
        self.assertEqual(s.data,{})
    def test_publish_and_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"data";p.write_bytes(b"sample")
            r=a.rec("snapshot/test",p);s=Store()
            audit={"source_records_total":1904060,"database_bytes":6,"database_sha256":r["sha256"],"source_lock_sha256":"test"}
            with patch.object(a,"stage",return_value=(audit,{"snapshot/test":p},[r])):
                result=a.publish(s,self.run,"a"*40,Path(d))
                self.assertEqual(result["file_count"],1)
                self.assertTrue(s.exists(a.POINTER))
                with self.assertRaises(ValueError):a.publish(s,self.run,"a"*40,Path(d))
    def test_corrupt_payload_never_promotes(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"data";p.write_bytes(b"sample")
            r=a.rec("snapshot/test",p);s=Store();s.corrupt=True
            with patch.object(a,"stage",return_value=({},{"snapshot/test":p},[r])):
                with self.assertRaises(ValueError):a.publish(s,self.run,"a"*40,Path(d))
                self.assertFalse(s.exists(a.POINTER))
    def test_extra_inventory_denied(self):
        s=Store();prefix=a.PREFIX+"/releases/"+self.run+"/files"
        n=prefix+"/extra";s.create(n,io.BytesIO(b"x"),1,"application/octet-stream")
        with self.assertRaises(ValueError):a.check_inventory(s,prefix,[],{})
