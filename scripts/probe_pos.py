"""Identify CMS registry releases, public access, counts and column names without logging records."""
import json
import urllib.request
from urllib.parse import urlsplit

ROOT="https://data.cms.gov"
TITLES={
    "qies":"Provider of Services File - Quality Improvement and Evaluation System",
    "iqies":"Provider of Services File - Internet Quality Improvement and Evaluation System",
    "clia":"Provider of Services File - Clinical Laboratories",
}
VERSIONS={"qies":"b1e5b072-5e82-4e37-9bd6-de8708679935","iqies":"8b2c0a70-7e47-4b0f-a592-e51eb315cead"}

def get(url):
    if urlsplit(url).scheme!="https" or urlsplit(url).hostname!="data.cms.gov":
        raise ValueError("non-CMS endpoint")
    req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"FacilitySignal-development/0.1"})
    with urllib.request.urlopen(req,timeout=45) as r:
        if urlsplit(r.url).hostname!="data.cms.gov": raise ValueError("unexpected host")
        b=r.read(60_000_001)
    if len(b)>60_000_000: raise ValueError("metadata too large")
    return json.loads(b)

def main():
    catalog=get(ROOT+"/v1-1-data.json")
    for key,title in TITLES.items():
        matches=[d for d in catalog.get("dataset",[]) if d.get("title")==title]
        if len(matches)!=1:
            raise ValueError("missing/ambiguous title: "+title)
        d=matches[0]
        print("CATALOG",key,json.dumps({k:d.get(k) for k in ("title","identifier","modified","license","accessLevel")}),flush=True)
        dist=d.get("distribution",[])
        for item in dist[:8]:
            print("DISTRIBUTION",key,json.dumps({k:item.get(k) for k in ("title","description","format","mediaType","downloadURL","accessURL","identifier","temporal")}),flush=True)
        api=[x["accessURL"] for x in dist if x.get("format")=="API" and x.get("description")=="latest" and x.get("accessURL")]
        if len(api)!=1: raise ValueError("ambiguous latest API for "+key)
        endpoint=api[0]
        if key in VERSIONS and VERSIONS[key] not in endpoint:
            raise ValueError("latest release changed; review new version")
        data=get(endpoint+"?size=1&offset=0")
        if not isinstance(data,list) or len(data)!=1 or not isinstance(data[0],dict):
            raise ValueError("unexpected data shape")
        stats=get(endpoint+"/stats")
        print("API_SCHEMA",key,json.dumps(list(data[0])),flush=True)
        print("API_STATS",key,json.dumps(stats)[:1000],flush=True)
if __name__=="__main__":
    main()
