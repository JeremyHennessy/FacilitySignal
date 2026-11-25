"use strict";
const $=id=>document.getElementById(id), app=$("app"), N=new Intl.NumberFormat("en-US"), pageSize=25;
const states="AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VA WA WV WI WY DC AS GU MP PR VI".split(" ");
const names={"hospital":"Hospitals","nursing":"Nursing homes","dialysis":"Dialysis facilities","home-health":"Home health agencies","hospice":"Hospice providers","rehabilitation":"Inpatient rehabilitation","long-term-hospital":"Long-term care hospitals","nursing-health":"Nursing health citations","nursing-fire":"Nursing fire citations","qies":"QIES","iqies":"iQIES","clia":"CLIA laboratories","qcor-hospital":"QCOR hospital survey workbook","hospital-enrollment":"Hospital enrollments","hospital-owner":"Hospital organizational roles","hospital-chow":"Hospital ownership changes","snf-enrollment":"Skilled nursing enrollments","snf-owner":"Skilled nursing organizational roles","snf-chow":"Skilled nursing ownership changes"};
const alias={id:["CMS Certification Number (CCN)","Facility ID","PRVDR_NUM","CLIA_LAB_NUM","CLIA_NUM","CLIA_ID","CLIA_NUMBER","CMS_CERTIFICATION_NUMBER"],name:["Facility Name","Provider Name","Provider","FAC_NAME","LAB_NAME","LABORATORY_NAME"],address:["Address","Provider Address","Address Line 1","Street Address","ST_ADR","LAB_ADR","LAB_ADDRESS"],city:["City/Town","City","CITY_NAME","LAB_CITY"],state:["State","STATE_CD","LAB_STATE"],zip:["ZIP Code","ZIP","ZIP_CD","LAB_ZIP"],capacity:["Number of Certified Beds","# of Dialysis Stations","Number of Dialysis Stations"],ownership:["Hospital Ownership","Ownership Type","Profit or Non-Profit","Ownership"],chain:["Chain Name","Chain Organization"],date:["Survey Date"],tag:["Deficiency Tag Number"],prefix:["Deficiency Prefix"],description:["Deficiency Description"],severity:["Scope Severity Code"],correction:["Deficiency Corrected"],correctedDate:["Correction Date"],providerType:["PRVDR_TYPE_ID","PRVDR_CTGRY_CD","LAB_TYPE_CD","LAB_TYPE"],certDate:["CRTFCTN_DT","CERTIFICATION_DATE","CERT_EFCTV_DT"],termination:["TRMNTN_EXPRTN_DT","TERMINATION_DATE"],status:["FED_CRTFCTN_STUS_NAME","FED_CRTFCTN_STUS_ID","CMPLNC_STUS_CD","PGM_TRMNTN_CD","CERT_STATUS"]};
const registryAlias={...alias,name:["FAC_NAME","LAB_NAME","LABORATORY_NAME","PROVIDER_NAME"],id:["PRVDR_NUM","CLIA_LAB_NUM","CLIA_NUM","CLIA_ID","CLIA_NUMBER","CMS_CERTIFICATION_NUMBER"]};
const key=s=>String(s).toLowerCase().replace(/[^a-z0-9]/g,"");
function fields(row,registry){const actual=new Map(Object.keys(row).map(k=>[key(k),k]));return Object.fromEntries(Object.entries(registry?registryAlias:alias).map(([k,opts])=>[k,opts.map(o=>actual.get(key(o))).find(Boolean)]))}
const value=(r,f,k)=>f[k]===undefined?"":String(r[f[k]]??"").trim();
const shown=v=>v||"Not reported";
const el=(tag,txt,cls)=>{const e=document.createElement(tag);if(txt!==undefined)e.textContent=String(txt);if(cls)e.className=cls;return e};
function add(p,...children){p.append(...children);return p}
function anchor(txt,href,external=false){const a=el("a",txt);a.href=href;if(external){a.target="_blank";a.rel="noopener noreferrer"}return a}
function route(view,p={}){const u=new URLSearchParams();for(const [k,v] of Object.entries(p))if(v!==""&&v!==null&&v!==undefined)u.set(k,String(v));return "#"+view+(u.size?"?"+u:"")}
function read(){const [view,query=""]=location.hash.slice(1).split("?",2);return {view:view||"overview",p:Object.fromEntries(new URLSearchParams(query))}}
function linkSource(s){return s.family==="care-compare"?"https://data.cms.gov/provider-data/dataset/"+s.catalog_id:s.family==="registry"?s.metadata.api:s.family==="qcor"?"https://qcor.cms.gov/Hospital_2567_Reports":"https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities";}
function safeExternal(url){try{const u=new URL(url);return u.protocol==="https:"?u.href:null}catch{return null}}
function sourceLink(s,txt="Official source"){return anchor(txt,linkSource(s),true)}
function table(headers,rows){const wrap=el("div",undefined,"table-wrap");wrap.tabIndex=0;wrap.setAttribute("role","region");wrap.setAttribute("aria-label","Scrollable results table");const t=el("table"),head=el("thead"),tr=el("tr"),body=el("tbody");headers.forEach(x=>{const th=el("th",x);th.scope="col";tr.append(th)});head.append(tr);for(const r of rows){const line=el("tr");for(const c of r){const td=el("td");td.append(c instanceof Node?c:document.createTextNode(String(c??"")));line.append(td)}body.append(line)}t.append(head,body);return add(wrap,t)}
function title(text,note){app.replaceChildren(el("h1",text),el("p",note,"intro"))}
function card(label,count,note,href){const a=anchor("",href);a.className="metric";return add(a,el("small",label),el("strong",N.format(count)),el("span",note),el("span","Explore ›","go"))}
let lock,register,coverage,publicManifest,active,sequence=0;const schemas=new Map();
const byFamily=f=>lock.sources.filter(s=>s.family===f);
const providerSources=()=>byFamily("care-compare").filter(s=>!s.key.startsWith("nursing-"));
const citationSources=()=>byFamily("care-compare").filter(s=>s.key.startsWith("nursing-"));
const aggregate=items=>items.reduce((n,s)=>n+s.stored_rows,0);
function sourceRows(items){return items.map(s=>[s.family==="care-compare"?anchor(names[s.key]||s.key,route(s.key.startsWith("nursing-")?"citations":"facilities",{source:s.key})):names[s.key]||s.key,s.release||s.metadata?.period||"Publication date unavailable",N.format(s.stored_rows),sourceLink(s)])}
function historicalNote(){return el("div","Historical qualification as of "+lock.as_of+". These figures describe the pinned releases. The public site includes a limited Care Compare directory and nursing citation aggregates, not the integrated database. Counts are source rows, not unique active facilities or outstanding violations.","notice")}
function overview(){title("National overview","National healthcare provider, certification and compliance research. Public Care Compare directory and source-specific qualification evidence.");app.append(historicalNote());const group=el("div",undefined,"metrics");const pecos=byFamily("pecos");for(const [label,items,note,href] of [
["Care Compare providers",providerSources(),"Provider records",route("facilities")],["Certifications & laboratories",byFamily("registry"),"Includes historical records",route("certifications")],["Nursing home citations",citationSources(),"Health and fire source rows",route("citations")],["Hospital survey rows",byFamily("qcor"),"Includes memos and repeated tags",route("hospital-surveys")],["PECOS enrollments",pecos.filter(s=>s.key.endsWith("enrollment")),"Historical qualification; aggregate only",route("ownership")],["Organizational roles",pecos.filter(s=>s.key.endsWith("owner")),"Individual rows excluded",route("ownership")],["Ownership changes",pecos.filter(s=>s.key.endsWith("chow")),"Not legal property title",route("ownership")],["Jurisdictions represented",publicManifest.jurisdictions.map(()=>({stored_rows:1})),"Care Compare reported addresses",route("geography")]])group.append(card(label,aggregate(items),note,href));app.append(group,el("h2","Provider source coverage"),table(["Provider family","Qualified release","Historical rows","Evidence"],sourceRows(providerSources())),el("h2","Research coverage"),el("p","The local development database also supports registry, hospital survey and aggregate ownership research. Raw registry, hospital survey and PECOS data are not published on this public site. Equipment, environmental, property and procurement data remain unqualified or unavailable here.","notice"))}
function options(label,id,items,selected){const wrap=el("label",label);const select=el("select");select.name=id;for(const [v,t] of items){let o=el("option",t);o.value=v;select.append(o)}select.value=items.some(x=>x[0]===selected)?selected:items[0][0];return add(wrap,select)}
function input(label,id,v){let l=el("label",label,id==="q"?"query":""),i=el("input");i.name=id;i.maxLength=100;i.value=v||"";return add(l,i)}
function formFor(view,p,sources){let f=el("form",undefined,"toolbar"),modes=view==="citations"?[["id","Exact CCN"],["name","Provider name contains"]]:[["name","Provider name contains"],["id","Exact identifier"],["city","Exact city"],["zip","Exact ZIP"],["address","Address contains"]];f.append(options("Source","source",sources.map(s=>[s.key,names[s.key]||s.key]),p.source),options("State / territory","state",[["","All jurisdictions"],...states.map(s=>[s,s])],p.state),options("Search field","field",modes,p.field),input("Search value","q",p.q),options("Sort by","sort",[["state","Jurisdiction / name"],["name","Name A–Z"],["name_desc","Name Z–A"],["id","CCN"],...(view==="citations"?[["citations","Historical citation rows (descending)"]]:[])],p.sort),el("button","Search"));f.addEventListener("submit",e=>{e.preventDefault();location.hash=route(view,{...Object.fromEntries(new FormData(f)),page:1})});return f}
async function loadShard(s,signal){
    if(s.family!=="care-compare"||!/^[-a-z]+$/.test(s.key))throw Error("Unsupported public source");
    const response=await fetch("web/public-directory/"+s.key+".json",{signal});
    if(!response.ok)throw Error("Static source HTTP "+response.status);
    const data=await response.json(),published=publicManifest.sources[s.key];
    if(data.source!==s.key||data.release!==s.release||!Array.isArray(data.records)||data.row_count!==s.stored_rows||data.records.length!==published?.published_records)throw Error("Static source manifest mismatch");
    if(s.key.startsWith("nursing-")){
        if(data.records.some(r=>!Number.isSafeInteger(r.citation_rows)||r.citation_rows<1)||data.records.reduce((n,r)=>n+r.citation_rows,0)!==data.row_count)throw Error("Citation aggregate reconciliation failed");
    }else if(data.records.length!==data.row_count)throw Error("Provider count mismatch");
    return data
}
const publicFields={id:"ccn",name:"name",address:"address",city:"city",state:"state",zip:"zip",capacity:"capacity",count:"citation_rows"};
function matchesPublic(r,p){
    const field=p.field||"name",q=(p.q||"").trim().slice(0,100).toLowerCase(),f=publicFields;
    if(!["id","name","city","zip","address"].includes(field))throw Error("Unsupported search field");
    if(p.state&&!states.includes(p.state))throw Error("Invalid jurisdiction");
    const v=value(r,f,field).toLowerCase();
    return (!p.state||r.state===p.state)&&(!q||(["name","address"].includes(field)?v.includes(q):v===q))
}
async function query(s,p,signal,limit=pageSize){
    const data=await loadShard(s,signal),matches=data.records.filter(r=>matchesPublic(r,p));
    const order=p.sort||"state";
    const textCompare=(a,b)=>String(a||"").localeCompare(String(b||""),"en",{sensitivity:"base"});
    if(order==="name")matches.sort((a,b)=>textCompare(a.name,b.name)||textCompare(a.state,b.state)||textCompare(a.ccn,b.ccn));
    else if(order==="name_desc")matches.sort((a,b)=>textCompare(b.name,a.name)||textCompare(a.state,b.state)||textCompare(a.ccn,b.ccn));
    else if(order==="id")matches.sort((a,b)=>textCompare(a.ccn,b.ccn)||textCompare(a.state,b.state));
    else if(order==="citations"&&s.key.startsWith("nursing-"))matches.sort((a,b)=>b.citation_rows-a.citation_rows||textCompare(a.ccn,b.ccn)||textCompare(a.state,b.state));
    const page=Math.max(1,Math.min(100000,Number.parseInt(p.page||"1",10)||1)),offset=(page-1)*limit;
    return {rows:matches.slice(offset,offset+limit),f:publicFields,page,total:matches.length,release:data.release};
}
async function unifiedSearch(p,signal,epoch){
    title("Unified search","Search across the seven published Care Compare provider sources. Each matching source record remains separate; no canonical site or certification status is inferred.");
    const form=el("form",undefined,"toolbar");
    const searchFields=[["name","Provider name contains"],["id","Exact CCN"],["city","Exact city"],["zip","Exact ZIP"],["address","Address contains"]];
    const qInput=input("Search value","q",p.q);qInput.querySelector("input").required=true;
    form.append(qInput,options("Search field","field",searchFields,p.field),options("State / territory","state",[["","All jurisdictions"],...states.map(s=>[s,s])],p.state),el("button","Search"));
    form.addEventListener("submit",e=>{e.preventDefault();location.hash=route("search",Object.fromEntries(new FormData(form)))});
    app.append(form);
    if(!(p.q||"").trim()){app.append(el("div","Enter a provider name, CCN, address, city or ZIP. A search reads only the limited published provider projections, one source at a time.","empty"));return}
    const progress=el("div","Searching published provider sources…","notice");app.append(progress);
    let total=0,completed=0,failed=0;
    for(const s of providerSources()){
        if(epoch!==sequence)return;
        try{
            const result=await query(s,{...p,page:1},signal,5);
            if(epoch!==sequence)return;
            total+=result.total;completed++;
            if(!result.total)continue;
            app.append(el("h2",names[s.key]+" · "+N.format(result.total)+" matches"),
                table(["Provider / CCN","Reported address","Reported capacity","Evidence"],result.rows.map(r=>cells("facilities",s,r,result.f))),
                add(el("p"),anchor("View all "+N.format(result.total)+" matching records",route("facilities",{source:s.key,q:p.q,field:p.field,state:p.state}))));
        }catch(e){if(epoch!==sequence||e.name==="AbortError")return;failed++;app.append(errorBox(s,e))}
    }
    if(epoch!==sequence)return;
    progress.textContent=N.format(total)+" matching source records across "+completed+" of 7 provider sources."+(failed?" "+failed+" source(s) unavailable; totals are partial.":"");
    if(!total&&!failed)app.append(el("div","No matching published Care Compare source records. Other registries or sources may contain records.","empty"));
}
async function geography(signal,epoch){
    title("Market explorer","Regional provider-source aggregation by reported state or territory. Coordinates have not been qualified; no individual facility pins or centroid approximations are shown.");
    const status=el("div","Reading qualified provider projections…","notice");app.append(status);
    const sources=providerSources(),counts=new Map(states.map(s=>[s,new Map()]));
    let completed=0,failed=0,total=0;
    for(const s of sources){
        try{
            const data=await loadShard(s,signal);if(epoch!==sequence)return;
            for(const row of data.records){if(!counts.has(row.state))throw Error("Unrecognized jurisdiction");}
            for(const row of data.records){const m=counts.get(row.state);m.set(s.key,(m.get(s.key)||0)+1);total++}
            completed++;
        }catch(e){if(epoch!==sequence||e.name==="AbortError")return;failed++;app.append(errorBox(s,e))}
    }
    if(epoch!==sequence)return;
    status.textContent=N.format(total)+" provider source records across "+completed+" of 7 sources."+(failed?" Partial coverage; unavailable categories are marked —.":" All 56 target jurisdictions are represented in this snapshot.");
    const sums=[...counts].map(([state,m])=>({state,m,total:[...m.values()].reduce((n,v)=>n+v,0)})).sort((a,b)=>b.total-a.total||a.state.localeCompare(b.state));
    app.append(table(["Jurisdiction",...sources.map(s=>names[s.key]),"Total source records"],sums.map(({state,m,total})=>[state,...sources.map(s=>m.has(s.key)?anchor(N.format(m.get(s.key)),route("facilities",{source:s.key,state})):failed?"—":"0"),N.format(total)])));
    app.append(el("p","Counts refer to source records, not unique physical facilities or complete regional regulatory coverage.","intro"))
}
function errorBox(s,e){return add(el("div",undefined,"error"),el("strong","Source unavailable. "),el("span",e.message+". This is not a zero-result or compliance finding. "),sourceLink(s,"Open the official source"))}
function recordCell(s,r,f){const id=value(r,f,"id"),name=value(r,f,"name"),cell=el("div");if(id)cell.append(anchor(shown(name),route("detail",{source:s.key,id,state:value(r,f,"state")})));else cell.append(el("span",shown(name)));cell.append(el("small",shown(id)));return cell}
function cells(view,s,r,f){const v=k=>value(r,f,k);if(view==="citations")return [anchor(shown(v("name")),route("detail",{source:"nursing",id:v("id"),state:v("state")})),shown(v("id")),shown(v("state")),N.format(r.citation_rows),sourceLink(s)];return [recordCell(s,r,f),shown([v("address"),v("city"),v("state"),v("zip")].filter(Boolean).join(", ")),shown(v("capacity")),sourceLink(s)]}
async function directory(view,p,signal,epoch){
    const sources=view==="facilities"?providerSources():citationSources();
    const s=sources.find(s=>s.key===p.source)||sources[0];
    p={...p,source:s.key,field:p.field||(view==="citations"?"id":"name")};
    title(view==="facilities"?"Facilities":"Nursing home citations",view==="facilities"?"Browse qualified public Care Compare provider records. Source-scoped records are not resolved physical facilities.":"Historical health or fire citation source-row totals grouped by reported CCN and state. These are not open deficiencies or inspection event counts.");
    app.append(formFor(view,p,sources));
    const status=el("div","Loading qualified public source projection…","notice");app.append(status);
    try{
        const {rows,f,page,total,release}=await query(s,p,signal);if(epoch!==sequence)return;
        status.replaceChildren(el("span","Source release "+release+" · "+names[s.key]+" · "+N.format(total)+" matching "+(view==="citations"?"provider/state groups":"provider records")+". "),sourceLink(s));
        if(!rows.length)app.append(el("div","No matching records in this source projection. This does not establish absence of other records or compliance.","empty"));
        else app.append(table(view==="citations"?["Provider","CCN","State","Historical citation rows","Evidence"]:["Provider / CCN","Reported address","Reported capacity","Evidence"],rows.map(r=>cells(view,s,r,f))));
        const pager=el("div",undefined,"pager");pager.append(el("span","Page "+page+" · "+N.format(total)+" matches"));
        if(page>1)pager.append(anchor("Previous",route(view,{...p,page:page-1})));
        if(page*pageSize<total)pager.append(anchor("Next",route(view,{...p,page:page+1})));
        app.append(pager)
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return;status.replaceWith(errorBox(s,e))}
}
function certificationCoverage(){title("Certifications & laboratories","Qualified QIES, iQIES and CLIA release coverage. Direct browser API access failed; row-level registry data are not published on this Pages site.");app.append(historicalNote(),table(["Registry","Release period","Historical source rows","Official API"],sourceRows(byFamily("registry"))),el("div","Certification status, current operations and equipment are not inferred. Full registry research remains in the local qualified application.","notice"))}
async function detail(p,signal,epoch){
    const s=providerSources().find(s=>s.key===p.source);
    title("Source record","Exact source identifier lookup. This is not a canonical property or controlling-ownership determination.");
    if(!s||!p.id){app.append(el("div","Source and identifier are required.","empty"));return}
    if(p.state&&!states.includes(p.state)){app.append(el("div","Invalid jurisdiction.","error"));return}
    const status=el("div","Loading qualified provider record…","notice");app.append(status);
    try{
        const result=await query(s,{field:"id",q:p.id,state:p.state||""},signal);
        if(epoch!==sequence)return;
        if(!result.total){status.replaceWith(el("div","No matching source record returned.","empty"));return}
        status.textContent=names[s.key]+" · Source release "+s.release+" · "+N.format(result.total)+" source record(s)";
        if(result.total>1)app.append(el("div","Multiple source records share the requested identifier; no silent merge has been performed.","notice"));
        for(const r of result.rows){
            const v=k=>value(r,result.f,k),grid=el("dl",undefined,"detail-grid");
            app.append(el("h2",shown(v("name"))));
            for(const [label,k] of [["CCN","id"],["Address","address"],["City","city"],["State","state"],["ZIP","zip"],[s.key==="nursing"?"Certified beds":s.key==="dialysis"?"Dialysis stations":"Reported capacity","capacity"]])grid.append(add(el("div"),el("dt",label),el("dd",shown(v(k)))));
            app.append(grid);
            if(s.key==="nursing"){
                const compliance=el("section"),summary=el("div","Loading same-state historical citation evidence…","notice");
                compliance.append(el("h2","Nursing home compliance evidence"),el("p","Exact CCN and reported state candidate links. Historical citation rows do not establish currently outstanding violations or compliance.","intro"),summary);app.append(compliance);
                const cellsOut=[];
                for(const cs of citationSources()){
                    try{
                        const cr=await query(cs,{field:"id",q:v("id"),state:v("state")},signal);
                        if(epoch!==sequence)return;
                        const n=cr.rows.reduce((a,b)=>a+b.citation_rows,0);
                        cellsOut.push([names[cs.key],cr.total?N.format(n):"No matching group",cs.release,anchor("Inspect source totals",route("citations",{source:cs.key,field:"id",q:v("id"),state:v("state")}))])
                    }catch(e){if(epoch!==sequence||e.name==="AbortError")return;cellsOut.push([names[cs.key],"Unavailable",cs.release,sourceLink(cs)])}
                }
                if(epoch!==sequence)return;summary.replaceWith(table(["Source","Historical citation rows","Source release","Evidence"],cellsOut))
            }
        }
        const links=el("div",undefined,"links");links.append(sourceLink(s),anchor("Back to directory",route("facilities",{source:s.key,state:p.state})));app.append(links);
        app.append(el("h2","Related source coverage"),add(el("div",undefined,"links"),anchor("Certification registry coverage",route("certifications")),anchor("Hospital survey coverage",route("hospital-surveys")),anchor("Ownership evidence coverage",route("ownership"))),
            el("div","Individual-level certification, equipment, environmental, property and ownership relationships are not inferred or published here. The related links show source-family coverage, not resolved links for this facility.","notice"))
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return;status.replaceWith(errorBox(s,e))}
}
function coverageView(view){const own=view==="ownership",items=byFamily(own?"pecos":"qcor");title(own?"Ownership evidence coverage":"Hospital survey coverage",own?"Aggregate PECOS qualification only. Individual ownership records and organizational projections are not published on this public site.":"QCOR survey rows include tags, memos, repeated projections and historical evidence. Correction status is unknown; narrative and row-level workbook data are not published here.");app.append(historicalNote(),table(["Source","Release period","Historical retained rows","Evidence"],sourceRows(items)),el("div",own?"Exact CCN and state candidates do not establish controlling ownership, physical property title, complete portfolios or current operational responsibility.":"Use the official QCOR report for source research. This site does not publish or infer active hospital violations.","notice"))}
function sourceRegister(p){title("Source register","Discovered sources, historical qualification, and reuse review are separate. A listed source is not necessarily loaded or publicly searchable.");const f=el("form",undefined,"toolbar");f.append(input("Filter source names, publishers or jurisdiction","q",p.q),el("button","Filter"));f.addEventListener("submit",e=>{e.preventDefault();location.hash=route("sources",Object.fromEntries(new FormData(f)))});app.append(f);let overlay=new Map(coverage.sources.map(s=>[s.id,s]));let q=(p.q||"").toLowerCase();let rows=register.sources.filter(s=>!q||[s.id,s.source,s.publisher,s.jurisdiction,s.category].some(x=>String(x).toLowerCase().includes(q)));let page=Math.max(1,Math.min(Math.ceil(rows.length/pageSize)||1,Number(p.page)||1));app.append(el("p",N.format(rows.length)+" source entries · original register preserved"));app.append(table(["Source","Jurisdiction","Qualification","Reuse review","Evidence"],rows.slice((page-1)*pageSize,page*pageSize).map(s=>[s.id+" · "+s.source,s.jurisdiction,overlay.get(s.id)?.status||"Discovered / not tested",s.reuse_review,safeExternal(s.source_url)?anchor("Publisher source",safeExternal(s.source_url),true):"See register"])));const pager=el("div",undefined,"pager");if(page>1)pager.append(anchor("Previous",route("sources",{...p,page:page-1})));if(page*pageSize<rows.length)pager.append(anchor("Next",route("sources",{...p,page:page+1})));app.append(pager)}
async function render(){if(!lock)return;if(active)active.abort();active=new AbortController();const {view,p}=read(),epoch=++sequence;for(const a of document.querySelectorAll("nav a")){if(a.getAttribute("href")==="#"+view)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current")}if(view==="overview")overview();else if(view==="search")await unifiedSearch(p,active.signal,epoch);else if(view==="geography")await geography(active.signal,epoch);else if(["facilities","citations"].includes(view))await directory(view,p,active.signal,epoch);else if(view==="certifications")certificationCoverage();else if(view==="detail")await detail(p,active.signal,epoch);else if(["ownership","hospital-surveys"].includes(view))coverageView(view);else if(view==="sources")sourceRegister(p);else title("Page not found","Choose an available workspace from navigation.");}
$("global-search").addEventListener("submit",e=>{e.preventDefault();let q=$("global-q").value.trim();location.hash=route("search",{field:/^\d{5}$/.test(q)?"zip":/^(?=.*[0-9])[A-Za-z0-9]{6}$/.test(q)?"id":"name",q})});
window.addEventListener("hashchange",()=>{if(location.hash==="#workspace"){$("workspace").focus();return}render()});
(async()=>{try{[lock,register,coverage,publicManifest]=await Promise.all(["research/snapshot_release_20261125.json","research/facilitysignal_source_register_v0.2.json","research/coverage_status.json","web/public-directory/manifest.json"].map(async path=>{let r=await fetch(path);if(!r.ok)throw Error("Source metadata HTTP "+r.status);return r.json()}));if(!Array.isArray(lock.sources)||!Array.isArray(register.sources)||!Array.isArray(coverage.sources)||!Array.isArray(publicManifest.jurisdictions)||!publicManifest.sources)throw Error("Invalid source metadata");render()}catch(e){title("Source metadata unavailable","The workspace could not load its source metadata. No data are inferred.");app.append(el("div",e.message,"error"),anchor("FacilitySignal repository","https://github.com/JeremyHennessy/FacilitySignal",true))}})();
