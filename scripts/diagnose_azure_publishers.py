"""Read only official catalog/ZIP central-directory diagnostics; no Azure credentials."""
import argparse,io,json,re,urllib.request,zipfile
from urllib.parse import urljoin,urlsplit
from pathlib import PurePosixPath
from scripts import archive_hcris_form_indexes as forms,qualify_hcris_hha as h,archive_ppef_enrollment as p
import collect_registry as reg
from build_combined import require

class RangeReader(io.RawIOBase):
    def __init__(self,url):
        self.url=h.allowed(url);self.pos=0;self.transferred=0;self.calls=0;self.size=None;self.etag=None
        self.start,self.tail=self.fetch("bytes=-65557")
    def fetch(self,range_header):
        headers={"Range":range_header,"Accept-Encoding":"identity","User-Agent":"FacilitySignal ZIP metadata diagnostic"}
        if self.etag:headers["If-Match"]=self.etag
        req=urllib.request.Request(self.url,headers=headers)
        with urllib.request.build_opener(h.Redirect()).open(req,timeout=60) as res:
            require(res.status==206,"publisher range requests unavailable")
            match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)",res.headers.get("Content-Range",""))
            require(match is not None,"invalid Content-Range")
            start,end,total=map(int,match.groups())
            require(0<=start<=end<total and (self.size is None or total==self.size),"remote size changed")
            self.size=total
            etag=res.headers.get("ETag")
            require(self.etag is None or etag==self.etag,"remote ETag changed")
            if etag and not etag.startswith("W/"):self.etag=etag
            length=end-start+1;self.calls+=1;self.transferred+=length
            require(self.calls<=30 and self.transferred<=8_000_000,"ZIP metadata range bound")
            data=res.read(length+1);require(len(data)==length,"range byte count")
            return start,data
    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,offset,whence=0):
        self.pos=offset if whence==0 else self.pos+offset if whence==1 else self.size+offset
        require(0<=self.pos<=self.size,"range seek out of bounds");return self.pos
    def read(self,n=-1):
        n=self.size-self.pos if n<0 else min(n,self.size-self.pos)
        if n==0:return b""
        require(n>0 and n<=8_000_000,"ZIP central directory read bound")
        start=self.pos;end=start+n
        if self.start<=start and end<=self.start+len(self.tail):data=self.tail[start-self.start:end-self.start]
        else:
            observed,data=self.fetch(f"bytes={start}-{end-1}");require(observed==start and len(data)==n,"unexpected range response")
        self.pos=end;return data

def hcris(source):
    _,form,slug,label=forms.TARGETS[source];page=forms.BASE+slug
    with h.request(page) as res:
        raw=res.read(5_000_001);require(0<len(raw)<=5_000_000,"page bound")
    parser=h.Links();parser.feed(raw.decode("utf-8",errors="strict"))
    links=[]
    for href,title in parser.links:
        url=urljoin(page,href)
        if urlsplit(url).hostname in h.HOSTS and urlsplit(url).path.lower().endswith(".zip"):
            links.append({"label":title,"url":h.allowed(url)})
    print("HCRIS_DIAGNOSTIC_LINKS",source,json.dumps(links),flush=True)
    try:url=forms.resolve(raw.decode("utf-8",errors="strict"),page,label)
    except Exception:return
    try:
        with RangeReader(url) as reader,zipfile.ZipFile(reader) as z:
            files=[i for i in z.infolist() if not i.is_dir()]
            result={"source":source,"form":form,"url":url,"archive_bytes":reader.size,"member_count":len(files),"expanded_bytes":sum(i.file_size for i in files),"transferred_bytes":reader.transferred,"members":[{"name":PurePosixPath(i.filename).name,"bytes":i.file_size,"compressed":i.compress_size,"crc":format(i.CRC,"08x")} for i in files[:300]]}
        print("HCRIS_DIAGNOSTIC_MEMBERS",json.dumps(result),flush=True)
    except Exception as e:
        print("HCRIS_DIAGNOSTIC_RANGE_BLOCKED",source,type(e).__name__,str(e)[:200],flush=True)

def ppef():
    catalog=reg.get_json("https://data.cms.gov/data.json")
    print("PPEF_CATALOG_DIAGNOSTIC",json.dumps({"top_level_keys":list(catalog),"series_matches":[x for x in catalog.get("datasetSeries",[]) if "fee-for-service public provider enrollment" in str(x.get("title","")).casefold()],"dataset_titles":[d.get("title") for d in catalog.get("dataset",[]) if "fee-for-service public provider enrollment" in str(d.get("title","")).casefold()][:20]}),flush=True)
    meta=p.catalog_selection(catalog);resources=reg.get_json(meta["resource_api"])
    print("PPEF_RESOURCES_DIAGNOSTIC",json.dumps({"version":meta,"resources":[{"name":x.get("name"),"downloadURL":x.get("downloadURL"),"id":x.get("id")} for x in resources["data"]]}),flush=True)
    print("PPEF_SELECTED_RESOURCE",json.dumps(p.resource_selection(resources)),flush=True)
def main():
    parser=argparse.ArgumentParser();parser.add_argument("source",choices=[*forms.TARGETS,"ppef"]);a=parser.parse_args()
    ppef() if a.source=="ppef" else hcris(a.source)
if __name__=="__main__":main()
