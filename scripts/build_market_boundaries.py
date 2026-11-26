"""Create a bounded, display-only SVG path projection from official Census geography.

Download only the 2025 1:500,000 state/equivalent boundary ZIP; no healthcare
coordinates, no external tile service, no retained raw archive in the repo.
"""
import argparse,hashlib,io,json,math,re,urllib.request,zipfile
from pathlib import Path
from urllib.parse import urlsplit
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
URL="https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip"
STEM="cb_2025_us_state_500k"
INSETS=["AK","HI","PR","VI","GU","MP","AS"]
LIMIT=12_000_000
def expected_states():
    return set(json.loads((ROOT/"web/public-directory/manifest.json").read_text())["jurisdictions"])
def require(ok,msg):
    if not ok:raise ValueError(msg)
def download():
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            require(urlsplit(newurl).scheme=="https" and urlsplit(newurl).hostname=="www2.census.gov","Unexpected Census redirect")
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    req=urllib.request.Request(URL,headers={"User-Agent":"FacilitySignal public cartographic qualification/1.0","Accept":"application/zip,application/octet-stream,*/*"})
    with urllib.request.build_opener(Redirect()).open(req,timeout=90) as r:
        raw=r.read(LIMIT+1)
        require(r.status==200 and len(raw)<=LIMIT,"Boundary ZIP HTTP/size gate")
        return raw,r.headers.get("Last-Modified"),datetime.now(timezone.utc).isoformat()
def verify(data):
    require(data["version"]==1 and data["vintage"]==2025 and data["source_url"]==URL and data["view_box"]=="0 0 960 560","Unexpected projection provenance")
    require(re.fullmatch(r"[0-9a-f]{64}",data["source_sha256"]) is not None,"Source hash missing")
    regions=data["regions"];keys=[r["state"] for r in regions]
    require(len(keys)==len(set(keys))==56 and set(keys)==expected_states(),"Boundary/source jurisdiction mismatch")
    require([i["state"] for i in data["insets"]]==INSETS,"Inset layout mismatch")
    for r in regions:
        require(set(r)=={"state","name","path"} and r["name"] and isinstance(r["path"],str),"Unexpected region projection fields")
        require(re.fullmatch(r"M[MLZ0-9., -]+Z",r["path"]) is not None,"Invalid SVG path")
        nums=[float(n) for n in re.findall(r"-?\d+(?:\.\d+)?",r["path"])]
        require(len(nums)>=6 and len(nums)%2==0 and all(0<=x<=960 for x in nums[::2]) and all(0<=y<=560 for y in nums[1::2]),"Boundary outside view box")
    require(len(json.dumps(data).encode())<5_000_000,"Boundary payload too large")
def convert(raw,last_modified,retrieved_at):
    import shapefile
    from pyproj import CRS,Transformer
    from shapely.geometry import shape
    from shapely.ops import transform
    require(len(raw)<=LIMIT,"Boundary archive too large")
    sha=hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        members=z.infolist()
        require(sum(x.file_size for x in members)<=80_000_000,"Expanded ZIP exceeds bound")
        names=z.namelist()
        require(len(names)==len(set(names)) and all(not n.startswith(("/", "\\")) and ".." not in Path(n).parts for n in names),"Unsafe ZIP entries")
        for ext in ("shp","shx","dbf","prj"):
            require(STEM+"."+ext in names,"Missing shapefile member "+ext)
        crs=CRS.from_wkt(z.read(STEM+".prj").decode("ascii"))
        require(crs.is_geographic and "NAD83" in crs.name.upper(),"Unexpected Census geographic CRS")
        sf=shapefile.Reader(shp=io.BytesIO(z.read(STEM+".shp")),shx=io.BytesIO(z.read(STEM+".shx")),dbf=io.BytesIO(z.read(STEM+".dbf")),encoding="utf-8")
        fields={x[0] for x in sf.fields[1:]}
        require({"STUSPS","NAME","STATEFP"}<=fields,"Missing boundary fields")
        shapes={}
        for sr in sf.iterShapeRecords():
            rec=sr.record.as_dict()
            key=rec["STUSPS"]
            require(key in expected_states() and key not in shapes,"Unexpected or duplicate jurisdiction "+str(key))
            geom=shape(sr.shape.__geo_interface__)
            require(not geom.is_empty and geom.geom_type in ("Polygon","MultiPolygon") and geom.is_valid,"Invalid source geometry "+key)
            shapes[key]=(rec["NAME"],geom)
    require(set(shapes)==expected_states(),"Not all 56 jurisdiction geometries represented")
    groups=[([s for s in shapes if s not in INSETS],(12,8,936,405),CRS.from_epsg(5070))]
    centers={"HI":(-157,20),"PR":(-66.5,18.2),"VI":(-64.8,18.0),"GU":(144.8,13.5),"MP":(145.5,16.0),"AS":(-170,-14.3)}
    inset_meta=[]
    for i,key in enumerate(INSETS):
        x=5+i*136
        box=[x,427,132,127]
        inset_meta.append({"state":key,"box":box})
        proj=CRS.from_epsg(3338) if key=="AK" else CRS.from_proj4("+proj=aeqd +lat_0="+str(centers[key][1])+" +lon_0="+str(centers[key][0])+" +datum=WGS84 +units=m +no_defs")
        groups.append(([key],(x+5,445,122,104),proj))
    regions=[]
    for keys,box,proj in groups:
        tr=Transformer.from_crs(crs,proj,always_xy=True)
        geoms={k:transform(tr.transform,shapes[k][1]) for k in keys}
        require(all(not g.is_empty and g.is_valid and all(math.isfinite(v) for v in g.bounds) for g in geoms.values()),"Invalid projected geometry")
        minx=min(g.bounds[0] for g in geoms.values());miny=min(g.bounds[1] for g in geoms.values())
        maxx=max(g.bounds[2] for g in geoms.values());maxy=max(g.bounds[3] for g in geoms.values())
        x,y,w,h=box
        scale=min(w/(maxx-minx),h/(maxy-miny))
        ox=x+(w-(maxx-minx)*scale)/2
        oy=y+(h-(maxy-miny)*scale)/2
        def path_ring(ring):
            coords=[(round(ox+(a-minx)*scale,1),round(oy+(maxy-b)*scale,1)) for a,b,*_ in ring.coords]
            unique=[]
            for pt in coords:
                if not unique or unique[-1]!=pt:unique.append(pt)
            if unique and unique[0]==unique[-1]:unique.pop()
            if len(set(unique))<3:return ""
            return "M"+"L".join(f"{a:.1f},{b:.1f}" for a,b in unique)+"Z"
        for key,g in geoms.items():
            # 0.25 screen-unit simplification, topology preserved per feature.
            g=g.simplify(0.25/scale,preserve_topology=True)
            require(g.is_valid and not g.is_empty,"Simplified geometry invalid "+key)
            pieces=[]
            for poly in ([g] if g.geom_type=="Polygon" else g.geoms):
                outer=path_ring(poly.exterior)
                if not outer:continue
                pieces.append(outer+"".join(path_ring(r) for r in poly.interiors))
            path="".join(pieces)
            require(bool(path),"Jurisdiction not drawable "+key)
            regions.append({"state":key,"name":shapes[key][0],"path":path})
    result={"version":1,"vintage":2025,"source_url":URL,"source_sha256":sha,"source_bytes":len(raw),"last_modified":last_modified,"retrieved_at":retrieved_at,"view_box":"0 0 960 560","scale":"1:500,000; screen-simplified display projection","projection":"NAD83 / Conus Albers for mainland; Alaska Albers and local azimuthal equidistant for insets; independent scales","limitations":"Display only; not precise area, boundary relationship, facility location or geocoding evidence.","insets":inset_meta,"regions":sorted(regions,key=lambda r:r["state"])}
    verify(result);return result
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--download",action="store_true")
    p.add_argument("--archive",type=Path)
    p.add_argument("--expected-sha256")
    p.add_argument("--check",action="store_true")
    p.add_argument("--output",type=Path,default=ROOT/"web/market-boundaries.json")
    a=p.parse_args()
    if a.check:
        verify(json.loads(a.output.read_text()));print("MARKET_BOUNDARIES_CHECK_PASS");return
    require(a.download != bool(a.archive),"Choose exactly one official download or archived source")
    require(not a.output.exists(),"Do not overwrite a qualified boundary projection")
    if a.download:raw,modified,retrieved=download()
    else:
        require(bool(a.expected_sha256),"Archived source requires expected SHA")
        raw=a.archive.read_bytes();modified=None;retrieved=datetime.now(timezone.utc).isoformat()
    if a.expected_sha256:require(hashlib.sha256(raw).hexdigest()==a.expected_sha256,"Boundary source changed")
    result=convert(raw,modified,retrieved)
    a.output.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    print("MARKET_BOUNDARIES_VERIFIED",json.dumps({k:result[k] for k in ("vintage","source_sha256","source_bytes","last_modified","retrieved_at","projection")}|{"jurisdictions":len(result["regions"]),"bytes":a.output.stat().st_size}),flush=True)
if __name__=="__main__":main()
