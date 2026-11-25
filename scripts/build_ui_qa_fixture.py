"""Synthetic national-volume QA fixture. Never a source or production database."""
import json, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import facilitysignal as fs
from collect_ownership import init as ownership_init

def main(path):
    assert not path.exists(), "new fixture only"
    start=time.perf_counter()
    fs.init(path)
    db=fs.connect(path)
    db.execute("PRAGMA journal_mode=OFF")
    db.execute("PRAGMA synchronous=OFF")
    ownership_init(db)
    datasets=[k for k in fs.CATALOG if k in fs.FACILITY_DATASETS]
    total=48004
    def addr(i):
        return f"{i+1} Synthetic Avenue",f"QA City {i%250:03d}",fs.STATES[i%len(fs.STATES)],f"{i%100000:05d}"
    def insert(table,values,columns):
        db.executemany("INSERT INTO "+table+" VALUES("+",".join(["?"]*columns)+")",values)
    def release(key,count,rid):
        db.execute("INSERT INTO releases VALUES(?,?,?,?,?,?,?,?,?)",(rid,key,"2025-01-01","2025-01-02","synthetic",count,count,0,"https://example.test/qa"))
        db.execute("INSERT INTO current_release VALUES(?,?)",(key,rid))
    for j,d in enumerate(datasets):
        rid=j+1
        ids=range(j,total,len(datasets))
        release(d,len(ids),rid)
        insert("facilities",((d,f"{i+1:06d}",f"Synthetic {d} {i+1:06d}",*addr(i),"QA County",fs.CATALOG[d][1],"QA subtype","QA ownership","QA chain",str(i%200+1),rid) for i in ids),14)
    nursing=range(datasets.index("nursing"),total,len(datasets))
    hospitals=range(datasets.index("hospital"),total,len(datasets))
    for j,(d,n) in enumerate((("nursing-health",480000),("nursing-fire",139069))):
        rid=20+j
        release(d,n,rid)
        def findings():
            for i in range(n):
                p=nursing[i%len(nursing)]
                ccn=f"{p+1:06d}"
                yield (d,f"synthetic-{i}",ccn,f"Synthetic nursing {ccn}",addr(p)[2],"2024-12-01","QA survey","F0001" if j==0 else "K0001","QA category","Synthetic finding; no actual regulatory evidence.","D","Corrected" if i%2 else "","2024-12-05" if i%2 else "",rid)
        insert("findings",findings(),14)
    for registry,n in (("qies",13598),("iqies",100334),("clia",686058)):
        db.execute("INSERT INTO certification_releases VALUES(?,?,?,?,?,?,?,?,?)",(registry,"Synthetic "+registry,"2025-01","https://example.test","https://example.test/qa","synthetic",n,"2025-01-02","{}"))
        def certs():
            for i in range(n):
                ident=f"{i+1:06d}" if registry=="qies" else ("99A" if registry=="clia" else "I")+f"{i+1:07d}"
                yield (registry,i+1,f"synthetic-{i}",ident,f"Synthetic {registry} {ident}",*addr(i),"QA","","2020-01-01","2024-01-01" if i%3==0 else "","X" if i%3==0 else "")
        insert("certification_records",certs(),14)
    n=284391
    db.execute("INSERT INTO qcor_hospital_releases VALUES(1,'synthetic','2025-01-02','https://example.test',1,?,?)",(n,n))
    db.execute("INSERT INTO qcor_hospital_current VALUES(1,1)")
    def surveys():
        for i in range(n):
            p=hospitals[i%len(hospitals)]
            ccn=f"{p+1:06d}"
            kind=("tag","memo","no_tag_reported")[i%3]
            yield (1,i+1,f"synthetic-{i}",ccn,f"Synthetic hospital {ccn}","QA",*addr(p),"QA",f"event-{i//3}","2024-12-01","QA survey","A0001" if kind=="tag" else "","Synthetic structured description","QA",kind)
    insert("qcor_hospital_rows",surveys(),18)
    for family,en,roles,chow,ids in (("hospital",9120,22735,779,hospitals),("snf",14401,100231,5340,nursing)):
        for suffix,n in (("enrollment",en),("owner",roles),("chow",chow)):
            db.execute("INSERT INTO pecos_releases VALUES(?,?,?,?,?,?,?,?,?,?)",(family+"-"+suffix,"2025-01","2025-01-01","https://example.test","https://example.test/qa","synthetic",n,n,0,"utf-8"))
        insert("pecos_enrollment_rows",((family+"-enrollment",i+1,f"E{i}",f"P{i}",f"{ids[i%len(ids)]+1:06d}",f"QA{i}",f"Synthetic organization {i}",json.dumps({"STATE":addr(ids[i%len(ids)])[2]})) for i in range(en)),8)
        insert("pecos_org_role_rows",((family+"-owner",i+1,f"E{i%en}",f"P{i%en}",f"O{i}",f"Synthetic role organization {i}","QA","QA role","{}") for i in range(roles)),9)
        insert("pecos_chow_rows",((family+"-chow",i+1,f"E{i%en}",f"E{(i+1)%en}",f"{ids[i%len(ids)]+1:06d}",f"{ids[(i+1)%len(ids)]+1:06d}","2024-12-01","{}") for i in range(chow)),8)
    db.commit()
    db.execute("ANALYZE")
    db.commit()
    result=fs.overview(db)
    expected={"facility_records":48004,"finding_records":619069,"certification_records":799990,"hospital_survey_records":284391,"enrollment_records":23521,"organization_role_records":122966,"ownership_change_records":6119}
    assert all(result[k]==v for k,v in expected.items()),result
    assert len(result["by_state"])==56
    assert db.execute("PRAGMA quick_check").fetchone()[0]=="ok"
    db.close()
    print("SYNTHETIC_QA_FIXTURE",json.dumps({"counts":expected,"jurisdictions":56,"seconds":round(time.perf_counter()-start,3),"bytes":path.stat().st_size,"not_real_data":True}),flush=True)
if __name__=="__main__":
    main(Path(sys.argv[1]))
