"use strict";
const $=id=>document.getElementById(id), app=$("app"), N=new Intl.NumberFormat("en-US"), pageSize=25;
const states="AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI".split(" ");
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
["Care Compare providers",providerSources(),"Provider records",route("facilities")],["Certifications & laboratories",byFamily("registry"),"Includes historical records",route("certifications")],["Nursing home citations",citationSources(),"Health and fire source rows",route("citations")],["Hospital survey rows",byFamily("qcor"),"Includes memos and repeated tags",route("hospital-surveys")],["PECOS enrollments",pecos.filter(s=>s.key.endsWith("enrollment")),"Historical qualification; aggregate only",route("ownership")],["Organizational roles",pecos.filter(s=>s.key.endsWith("owner")),"Individual rows excluded",route("ownership")],["Ownership changes",pecos.filter(s=>s.key.endsWith("chow")),"Not legal property title",route("ownership")],["Jurisdictions represented",publicManifest.jurisdictions.map(()=>({stored_rows:1})),"Care Compare reported addresses",route("geography")]])group.append(card(label,aggregate(items),note,href));app.append(group,el("h2","Provider source coverage"),table(["Provider family","Qualified release","Historical rows","Evidence"],sourceRows(providerSources())),el("h2","Research coverage"),el("p","The local development database also supports registry, hospital survey and aggregate ownership research. Raw registry, hospital survey and PECOS data are not published on this public site. Equipment and environmental aggregate research is available; individual equipment/environmental records, property and procurement relationships remain unavailable here.","notice"),el("h2","Qualified aggregate research"),el("p","Explore national evidence separately from publicly searchable provider records.","intro"),aggregateResearchLinks())}
function aggregateResearchLinks(){
    const wrap=el("div",undefined,"links");
    for(const [name,view] of [["Advanced facility search","advanced"],["Industry research","industry"],["Service intelligence","services"],["Compliance research","compliance-research"],["Equipment & environmental research","equipment-environment"],["Data intelligence","data-evidence"]])wrap.append(anchor(name,route(view)));
    return wrap
}
async function intelligence(view,signal,epoch){
    const labels={services:"Service intelligence","compliance-research":"Compliance research","equipment-environment":"Equipment & environmental research","data-evidence":"Data intelligence"};
    title(labels[view],"Historical national aggregate qualification. Public research only; not a live national database.");
    const waiting=el("div","Loading qualified aggregate evidence…","notice");app.append(waiting);
    try{
        const response=await fetch("web/public-intelligence.json",{signal});
        if(!response.ok)throw Error("Evidence projection HTTP "+response.status);
        const data=await response.json();if(epoch!==sequence)return;
        if(data.version!==1||data.scope!=="historical national aggregate qualification"||!Array.isArray(data.sections))throw Error("Unexpected evidence projection");
        const section=data.sections.find(x=>x.id===view);
        if(!section||!Array.isArray(section.groups))throw Error("Missing evidence section");
        title(section.title,section.intro);
        const nav=el("div",undefined,"links");
        if(view==="services")nav.append(anchor("Search reported public capacity",route("capacity")),anchor("Browse facility directory",route("facilities")));
        if(view==="compliance-research")nav.append(anchor("Search public nursing citation aggregates",route("citations")),anchor("Hospital survey coverage",route("hospital-surveys")));
        if(view==="equipment-environment")nav.append(anchor("Review source register",route("sources")));
        if(view==="data-evidence")nav.append(anchor("Source inventory",route("sources")),anchor("Certification registry coverage",route("certifications")));
        app.append(nav);
        for(const g of section.groups){
            if(!Number.isSafeInteger(g.run)||g.run<=0||!Array.isArray(g.columns)||!Array.isArray(g.rows)||g.rows.some(r=>!Array.isArray(r)||r.length!==g.columns.length||r.some(x=>x!==null&&typeof x!=="string"&&!(Number.isSafeInteger(x)&&x>=0))))throw Error("Invalid evidence group");
            const src=safeExternal(g.source);
            const evidenceTable=table(g.columns,g.rows.map(r=>r.map(x=>x===null?"—":typeof x==="number"?N.format(x):x)));
            evidenceTable.classList.add("intelligence-table");
            evidenceTable.setAttribute("aria-label",g.title+"; scroll horizontally if needed");
            app.append(el("h2",g.title),el("p",g.note,"intro"));
            if(g.columns.length>3)app.append(el("p","Scroll horizontally to see all columns.","intelligence-scroll-hint"));
            app.append(evidenceTable);
            const evidence=el("div",undefined,"links");
            evidence.append(anchor("Qualification run "+g.run,"https://github.com/JeremyHennessy/FacilitySignal/actions/runs/"+g.run,true));
            if(src)evidence.append(anchor("Official documentation / evidence",src,true));
            app.append(evidence)
        }
        app.append(el("div","These aggregates do not establish confirmed service opportunities, current facility operation or current compliance. Additional row-level publication remains subject to separate review.","notice"))
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return;app.replaceChildren(el("h1",labels[view]),el("div","Qualified aggregate evidence unavailable: "+e.message+". No values inferred.","error"))}
}
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


function advancedParameters(p,sources){
    const source=p.source||"all",field=p.field||"name",reported=p.reported||"all";
    if(source!=="all"&&!sources.some(s=>s.key===source))throw Error("Invalid provider category");
    if(p.state&&!states.includes(p.state))throw Error("Invalid jurisdiction");
    if(!["name","id","city","zip","address"].includes(field))throw Error("Invalid search field");
    if(!["all","known","unknown"].includes(reported))throw Error("Invalid capacity evidence");
    if((p.q||"").length>100)throw Error("Search value exceeds 100 characters");
    const bounds={};
    for(const key of ["min","max"]){
        if(p[key]==null||p[key]===""){bounds[key]=null;continue}
        if(!/^\d{1,7}$/.test(String(p[key]))||Number(p[key])>1000000)throw Error("Capacity bounds must be whole numbers from 0 to 1,000,000");
        bounds[key]=Number(p[key])
    }
    const filteredCapacity=reported!=="all"||bounds.min!==null||bounds.max!==null;
    if(filteredCapacity&&!Object.hasOwn(capacityUnits,source))throw Error("Choose one capacity-qualified category: nursing homes or dialysis facilities. Their units cannot be combined.");
    if(bounds.min!==null&&bounds.max!==null&&bounds.min>bounds.max)throw Error("Minimum capacity cannot exceed maximum capacity");
    if(reported==="unknown"&&(bounds.min!==null||bounds.max!==null))throw Error("Capacity bounds cannot be combined with missing capacity");
    if(p.page&&!/^\d{1,6}$/.test(p.page))throw Error("Invalid page");
    const page=Math.max(1,Math.min(100000,Number(p.page)||1));
    return {...p,source,field,reported,q:(p.q||"").trim(),state:p.state||"",page,bounds,filteredCapacity}
}
function advancedForm(p,sources){
    const f=el("form",undefined,"toolbar advanced-form");
    const category=options("Provider category","source",[["all","All seven provider categories"],...sources.map(s=>[s.key,names[s.key]])],p.source||"all");
    const state=options("State / territory","state",[["","All jurisdictions"],...states.slice().sort().map(s=>[s,s])],p.state);
    const field=options("Search field","field",[["name","Provider name contains"],["id","Exact CCN"],["city","Exact city"],["zip","Exact ZIP"],["address","Address contains"]],p.field);
    const q=input("Search value (optional)","q",p.q);
    const evidence=options("Capacity evidence","reported",[["all","Any evidence"],["known","Numeric value reported"],["unknown","Missing / nonnumeric"]],p.reported);
    const min=input("Minimum capacity","min",p.min),max=input("Maximum capacity","max",p.max);
    for(const wrap of [min,max]){const n=wrap.querySelector("input");n.type="number";n.min="0";n.max="1000000";n.step="1";n.placeholder="Any"}
    const hint=el("p",undefined,"advanced-capacity-hint");
    hint.id="advanced-capacity-hint";
    const apply=el("button","Apply search filters");apply.type="submit";
    const reset=anchor("Reset filters",route("advanced"));reset.className="advanced-reset";
    f.append(category,state,field,q,evidence,min,max,hint,apply,reset);
    const selector=category.querySelector("select"),ev=evidence.querySelector("select"),lo=min.querySelector("input"),hi=max.querySelector("input");
    function sync(){
        const unit=capacityUnits[selector.value],available=!!unit;
        for(const c of [ev,lo,hi]){c.disabled=!available;c.setAttribute("aria-describedby",hint.id)}
        if(!available){ev.value="all";lo.value="";hi.value="";hint.textContent="Capacity filters require a single nursing-home or dialysis category. Other public provider categories do not contain a qualified numeric capacity unit."}
        else{
            hint.textContent="Capacity unit: "+unit.label+". Reported zero is distinct from missing or nonnumeric data. Individual registry service observations are not published.";
            const missing=ev.value==="unknown";lo.disabled=missing;hi.disabled=missing;
            if(missing){lo.value="";hi.value=""}
        }
    }
    selector.addEventListener("change",()=>{ev.value="all";lo.value="";hi.value="";sync()});
    ev.addEventListener("change",sync);sync();
    f.addEventListener("submit",e=>{e.preventDefault();const params=Object.fromEntries(new FormData(f));params.run="1";location.hash=route("advanced",params)});
    return f
}
function advancedCapacityMatch(row,p){
    if(!p.filteredCapacity)return true;
    const n=publicCapacity(row);
    return !(p.reported==="known"&&n===null||p.reported==="unknown"&&n!==null||p.bounds.min!==null&&(n===null||n<p.bounds.min)||p.bounds.max!==null&&(n===null||n>p.bounds.max))
}
function advancedCapacityText(s,row){
    const unit=capacityUnits[s.key];
    if(!unit)return "No qualified public unit";
    const n=publicCapacity(row);
    return n===null?"Not reported / nonnumeric":N.format(n)+" "+unit.label.toLowerCase()
}
function safeCsvCell(v){
    let s=String(v??"");
    if(/^\s*[=+\-@\t\r\n]/.test(s))s="'"+s;
    return '"'+s.replaceAll('"','""')+'"'
}
function exportAdvancedPage(rows){
    const header=["source","release","ccn","reported_name","reported_address","city","state","zip","reported_numeric_capacity","capacity_unit","capacity_evidence"];
    const records=rows.map(({s,r})=>{const unit=capacityUnits[s.key],n=unit?publicCapacity(r):null;return [s.key,s.release,r.ccn,r.name,r.address,r.city,r.state,r.zip,n,unit?unit.label:"",unit?(n===null?"missing_or_nonnumeric":"numeric_reported"):"no_qualified_public_unit"]});
    const content=[header,...records].map(row=>row.map(safeCsvCell).join(",")).join("\r\n")+"\r\n";
    const url=URL.createObjectURL(new Blob([content],{type:"text/csv;charset=utf-8"})),a=el("a");
    a.href=url;a.download="facilitysignal-public-search-page.csv";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
async function advancedResearch(p,signal,epoch){
    title("Advanced facility search","Combine published provider category, jurisdiction, exact or text search, and source-specific capacity evidence. Results are reported program records, not unique buildings or a list of confirmed service opportunities.");
    const sources=providerSources(),form=advancedForm(p,sources);
    app.append(form,add(el("div",undefined,"links"),anchor("Service research coverage",route("services")),anchor("Industry research pathways",route("industry",{state:p.state}))));
    let params;
    try{params=advancedParameters(p,sources)}catch(e){app.append(el("div",e.message,"error"));return}
    if(!p.run&&!p.q&&!p.state&&!p.source&&!p.reported&&!p.min&&!p.max){app.append(el("div","Select filters and apply the search. Searching all categories without text is allowed; results are paginated.","empty"));return}
    const chosen=sources.filter(s=>params.source==="all"||params.source===s.key);
    const status=el("div","Searching qualified public provider projections…","notice");status.classList.add("advanced-status");app.append(status);
    const page= params.page,offset=(page-1)*pageSize,items=[],counts=[];
    let total=0,completed=0,failed=0;
    const cmp=(a,b)=>String(a.name||"").localeCompare(String(b.name||""),"en",{sensitivity:"base"})||String(a.state).localeCompare(String(b.state))||String(a.ccn).localeCompare(String(b.ccn));
    for(const s of chosen){
        try{
            const data=await loadShard(s,signal);if(epoch!==sequence)return;
            const matches=data.records.filter(row=>matchesPublic(row,params)&&advancedCapacityMatch(row,params)).sort(cmp);
            const start=Math.max(0,offset-total),end=Math.min(matches.length,offset+pageSize-total);
            if(end>start)for(const row of matches.slice(start,end))items.push({s,r:row});
            total+=matches.length;completed++;counts.push([s.key,matches.length,s.release]);
        }catch(e){if(epoch!==sequence||e.name==="AbortError")return;failed++;counts.push([s.key,null,s.release]);app.append(errorBox(s,e))}
    }
    if(epoch!==sequence)return;
    status.textContent=N.format(total)+" matching provider source records across "+completed+" of "+chosen.length+" selected sources."+(failed?" Partial results: one or more sources unavailable; totals and pagination are incomplete.":" Sorted by provider category, then name.");
    status.dataset.total=String(total);status.dataset.complete=String(failed===0);
    const breakdown=el("div",undefined,"advanced-breakdown");
    for(const [key,n,release] of counts){const card=el("div",undefined,"advanced-source-count");card.append(el("strong",n===null?"Unavailable":N.format(n)),el("span",names[key]),el("small","Release "+release));breakdown.append(card)}
    app.append(breakdown,el("h2","Matching source records"));
    if(items.length){
        const wrapper=table(["Provider / CCN","Provider category","Reported address","Capacity evidence","Source release"],items.map(({s,r})=>[recordCell(s,r,publicFields),names[s.key],shown([r.address,r.city,r.state,r.zip].filter(Boolean).join(", ")),advancedCapacityText(s,r),add(el("div"),el("span",s.release),el("small",sourceLink(s,"Official source").textContent))]));
        // Keep actual source links, not plain text.
        for(let i=0;i<items.length;i++){const td=wrapper.querySelectorAll("tbody tr")[i].lastElementChild;td.replaceChildren(el("span",items[i].s.release),el("small"));td.lastChild.append(sourceLink(items[i].s))}
        wrapper.classList.add("advanced-results");wrapper.setAttribute("aria-label","Matching provider records; scroll horizontally if needed");
        app.append(wrapper);
        if(!failed){const exportButton=el("button","Export current page (CSV)");exportButton.type="button";exportButton.addEventListener("click",()=>exportAdvancedPage(items));app.append(add(el("div",undefined,"links"),exportButton))}
    }else app.append(el("div",total?"This page is outside the available matches. Return to the first page.":failed?"No matches were returned from available sources; unavailable sources were not searched.":"No published source records match these filters.","empty"));
    const pager=el("div",undefined,"pager");
    pager.append(el("span","Page "+page+" · "+N.format(total)+" matches"+(failed?" (partial)":"")));
    const safe={source:params.source,state:params.state,field:params.field,q:params.q,reported:params.reported,min:p.min,max:p.max,run:1};
    if(page>1)pager.append(anchor("First page",route("advanced",{...safe,page:1})),anchor("Previous",route("advanced",{...safe,page:page-1})));
    if(page*pageSize<total&&!failed)pager.append(anchor("Next",route("advanced",{...safe,page:page+1})));
    app.append(pager,el("p","Only existing public provider records and capacity fields are searchable. Individual clinical service, equipment, ownership and regulatory relationships remain subject to qualification and publication review.","intro"))
}
function industryResearch(p){
    title("Industry research","Start a documented healthcare-market research workflow. Each pathway links to available public provider or national aggregate evidence; these are not confirmed leads, equipment inventories or findings of noncompliance.");
    if(p.state&&!states.includes(p.state)){app.append(el("div","Invalid jurisdiction.","error"),anchor("Reset industry research",route("industry")));return}
    const state=p.state||"",f=el("form",undefined,"toolbar industry-form");
    f.append(options("Research jurisdiction","state",[["","All jurisdictions"],...states.slice().sort().map(s=>[s,s])],state),el("button","Apply jurisdiction"));
    f.addEventListener("submit",e=>{e.preventDefault();location.hash=route("industry",Object.fromEntries(new FormData(f)))});
    app.append(f);
    const cap=(source)=>route("capacity",{source,state}),search=(source)=>route("advanced",{source,state,run:1});
    const sections=[
        ["Water treatment & dialysis","Research reported dialysis station capacity and relevant national water-system source coverage. A dialysis provider record does not establish a water-treatment installation.",[["Dialysis providers",search("dialysis")],["Dialysis station capacity",cap("dialysis")],["National water / environmental evidence",route("equipment-environment")]]],
        ["Sterilization & infection prevention","Research hospital and nursing-home markets alongside national surgical-capability and infection-prevention context. Facility-level sterilization service or critical-water evidence is not published.",[["Hospital providers",search("hospital")],["Nursing home capacity",cap("nursing")],["National service evidence",route("services")],["National compliance research",route("compliance-research")]]],
        ["Medical imaging & equipment","Research provider markets and the national FDA mammography and QIES service-code evidence. There is no qualified individual installed-unit filter.",[["Hospital providers",search("hospital")],["Mammography source coverage",route("equipment-environment")],["National imaging service evidence",route("services")]]],
        ["Fire protection & emergency preparedness","Research nursing provider markets and historical citation aggregates. National life-safety context is not a current finding or a facility vulnerability assessment.",[["Nursing providers",search("nursing")],["Historical nursing fire citations",route("citations",{source:"nursing-fire",state})],["National compliance research",route("compliance-research")]]],
        ["Laboratory & clinical services","Research the provider directory and national certification/laboratory coverage. Individual CLIA and service registry projections are not published.",[["Public provider search",search("all")],["Registry and laboratory coverage",route("certifications")],["National service evidence",route("services")]]],
        ["Property management & infrastructure","Research market scale and reported provider addresses. Physical sites, ownership, contractors and procurement relationships are not inferred.",[["Regional market explorer",route("geography",{state})],["Public provider search",search("all")],["Ownership source coverage",route("ownership")]]]
    ];
    const grid=el("div",undefined,"industry-grid");
    for(const [label,note,links] of sections){const item=el("section",undefined,"industry-panel");item.append(el("h2",label),el("p",note,"intro"));const list=el("div",undefined,"industry-links");for(const [name,url] of links)list.append(anchor(name,url));item.append(list);grid.append(item)}
    app.append(grid,el("div","National aggregate pages are not jurisdiction-filtered unless explicitly stated. These research pathways do not establish current purchasing intent or confirmed opportunities.","notice"))
}

const marketGeometryUrl="web/market-boundaries.json";
const marketGeometrySource="https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_500k.zip";
const marketBands=[{lo:0,hi:0,label:"0",cls:"band-0"},{lo:1,hi:49,label:"1–49",cls:"band-1"},{lo:50,hi:199,label:"50–199",cls:"band-2"},{lo:200,hi:499,label:"200–499",cls:"band-3"},{lo:500,hi:999,label:"500–999",cls:"band-4"},{lo:1000,hi:null,label:"1,000+",cls:"band-5"}];
const svgNS="http://www.w3.org/2000/svg";
function svgNode(tag,attrs={},text){
    const e=document.createElementNS(svgNS,tag);
    for(const [key,value] of Object.entries(attrs))e.setAttribute(key,String(value));
    if(text!==undefined)e.textContent=text;
    return e
}
function marketControls(p,sources){
    const form=el("form",undefined,"toolbar market-toolbar");
    form.append(options("Map provider category","source",[["all","All provider source records"],...sources.map(s=>[s.key,names[s.key]])],p.source||"all"),
        options("Jurisdiction","state",[["","Select a jurisdiction"],...states.slice().sort().map(s=>[s,s])],p.state||""),el("button","Apply map filters"));
    form.addEventListener("submit",e=>{e.preventDefault();location.hash=route("geography",Object.fromEntries(new FormData(form)))});
    return form
}
function marketValue(row,source){return source==="all"?row.total:(row.m.get(source)||0)}
function marketSelection(p,sources,sums){
    const box=el("section",undefined,"market-selection");
    const row=sums.find(x=>x.state===p.state);
    if(!row){box.append(el("h2","Explore a jurisdiction"),el("p","Choose a region on the map, use the jurisdiction selector, or select a jurisdiction in the table. The map shows source-record counts, not physical facility locations.","intro"));return box}
    const source=p.source||"all",v=marketValue(row,source);
    box.append(el("h2",row.state+" market"),el("p",(source==="all"?"All provider sources":names[source])+" · "+N.format(v)+" source records","market-selected-count"));
    const links=el("div",undefined,"links");
    for(const s of sources){
        const n=row.m.get(s.key)||0;
        if(n)links.append(anchor(names[s.key]+" · "+N.format(n),route("facilities",{source:s.key,state:row.state})))
    }
    box.append(links,el("p","Explore reported capacity separately:","intro"),
        add(el("div",undefined,"links"),anchor("Certified nursing beds",route("capacity",{source:"nursing",state:row.state})),anchor("Dialysis stations",route("capacity",{source:"dialysis",state:row.state}))));
    if(source!=="all")box.append(add(el("p"),anchor("Open selected category in directory",route("facilities",{source,state:row.state}))));
    return box
}
function marketShape(data,sums,p){
    if(!data||data.version!==1||data.vintage!==2025||data.source_url!==marketGeometrySource||!Array.isArray(data.regions)||data.regions.length!==states.length||!Array.isArray(data.insets))throw Error("Boundary projection manifest mismatch");
    if(!/^[0-9a-f]{64}$/.test(data.source_sha256)||data.view_box!=="0 0 960 560")throw Error("Boundary provenance missing");
    const seen=new Set(), rows=new Map(sums.map(row=>[row.state,row]));
    const source=p.source||"all",selected=p.state||"";
    const svg=svgNode("svg",{viewBox:data.view_box,role:"group","aria-label":"Interactive jurisdiction map: "+(source==="all"?"all provider source records":names[source]),class:"market-svg"});
    svg.append(svgNode("title",{},"Provider source records by reported state or territory"));
    for(const i of data.insets){
        if(!Array.isArray(i.box)||i.box.length!==4||i.box.some(x=>!Number.isFinite(x))||!states.includes(i.state))throw Error("Invalid map inset");
        const [x,y,w,h]=i.box;
        svg.append(svgNode("rect",{x,y,width:w,height:h,rx:3,class:"market-inset"}),svgNode("text",{x:x+7,y:y+14,class:"market-inset-label"},i.state))
    }
    for(const r of data.regions){
        if(!states.includes(r.state)||seen.has(r.state)||typeof r.name!=="string"||typeof r.path!=="string"||!/^M[MLZ0-9., -]+Z$/.test(r.path)||!rows.has(r.state))throw Error("Invalid or duplicate map region");
        seen.add(r.state);
        const n=marketValue(rows.get(r.state),source);
        const band=marketBands.find(b=>n>=b.lo&&(b.hi===null||n<=b.hi));
        if(!band)throw Error("Invalid map value");
        const label=r.name+" ("+r.state+"): "+N.format(n)+" provider source records";
        const a=svgNode("a",{href:route("geography",{source,state:r.state}),tabindex:0,"aria-label":label,"data-state":r.state,"data-count":n,class:"market-region "+band.cls+(selected===r.state?" selected":"")});
        if(selected===r.state)a.setAttribute("aria-current","true");
        a.append(svgNode("title",{},label),svgNode("path",{d:r.path,"fill-rule":"evenodd","vector-effect":"non-scaling-stroke"}));svg.append(a)
    }
    if(seen.size!==states.length)throw Error("Incomplete jurisdiction coverage");
    const frame=el("div",undefined,"market-map-frame");frame.append(svg);
    return frame
}
async function marketMap(panel,p,sums,sources,signal,epoch){
    const selected=marketSelection(p,sources,sums);
    const legend=el("div",undefined,"market-legend");
    for(const b of marketBands)legend.append(add(el("span",undefined,"market-legend-item"),el("span",undefined,"market-swatch "+b.cls),el("span",b.label)));
    const notice=el("p","Loading qualified Census boundary projection…","notice");
    panel.append(el("h2","National jurisdiction map"),el("p","Shading shows absolute counts of source records in the selected provider category, not population-adjusted rates or risk. Select a jurisdiction for directory links.","intro"),legend,notice,selected);
    try{
        const resp=await fetch(marketGeometryUrl,{signal});
        if(!resp.ok)throw Error("Boundary projection HTTP "+resp.status);
        const data=await resp.json();if(epoch!==sequence)return;
        notice.replaceWith(marketShape(data,sums,p));
        panel.append(add(el("p",undefined,"intro"),document.createTextNode("Boundaries: U.S. Census Bureau, 2025 Cartographic Boundary Files, 1:500,000, simplified for display. Alaska, Hawaii and territorial insets are displaced and independently scaled. Not for geocoding or precise area measurement. "),anchor("Boundary source",data.source_url,true)))
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return;notice.textContent="Map geometry unavailable. The jurisdiction table and selector remain usable; no boundary or location is inferred. "+e.message;notice.className="error"}
}

function marketSummaryUrl(){
    if(!/^[0-9a-f]{64}$/.test(publicManifest.source_database_sha256))throw Error("Public manifest source hash unavailable");
    return "web/market-summary.json?v="+publicManifest.source_database_sha256.slice(0,16)
}
async function readMarketSummary(sources,signal){
    const response=await fetch(marketSummaryUrl(),{signal});
    if(!response.ok)throw Error("Regional aggregate HTTP "+response.status);
    const d=await response.json(),stateKeys=states.slice().sort(),sourceKeys=sources.map(s=>s.key).sort();
    if(d.version!==1||d.source_database_sha256!==publicManifest.source_database_sha256||d.as_of!==publicManifest.as_of||d.provider_rows!==publicManifest.provider_rows||!d.sources||!d.regions||JSON.stringify(Object.keys(d.sources).sort())!==JSON.stringify(sourceKeys)||JSON.stringify(Object.keys(d.regions).sort())!==JSON.stringify(stateKeys))throw Error("Regional aggregate manifest mismatch");
    const counts=new Map(),totals=new Map(sourceKeys.map(k=>[k,0]));
    for(const state of stateKeys){
        const values=d.regions[state];
        if(!values||JSON.stringify(Object.keys(values).sort())!==JSON.stringify(sourceKeys))throw Error("Regional aggregate categories mismatch");
        const map=new Map();
        for(const key of sourceKeys){const n=values[key];if(!Number.isSafeInteger(n)||n<0)throw Error("Invalid regional count");map.set(key,n);totals.set(key,totals.get(key)+n)}
        counts.set(state,map)
    }
    let total=0;
    for(const s of sources){
        const meta=d.sources[s.key],n=totals.get(s.key);
        if(!meta||meta.release!==s.release||meta.rows!==s.stored_rows||n!==s.stored_rows||n!==publicManifest.sources[s.key]?.source_rows||! /^[0-9a-f]{64}$/.test(meta.sha256))throw Error("Regional aggregate source reconciliation failed");
        total+=n
    }
    if(total!==publicManifest.provider_rows)throw Error("Regional aggregate national reconciliation failed");
    return {counts,total}
}

async function geography(p,signal,epoch){
    title("Market explorer","Regional provider-source aggregation by reported state or territory. No individual facility coordinates or centroid approximations are shown.");
    const status=el("div","Reading qualified provider projections…","notice");app.append(status);
    const sources=providerSources();let counts=new Map(states.map(s=>[s,new Map()]));
    if(p.source&&p.source!=="all"&&!sources.some(s=>s.key===p.source)||p.state&&!states.includes(p.state)){
        status.replaceWith(el("div","Invalid market category or jurisdiction.","error"));app.append(add(el("p"),anchor("Reset Market Explorer",route("geography"))));return
    }
    p={...p,source:p.source||"all"};
    app.append(marketControls(p,sources));
    const panel=el("section",undefined,"market-map-panel");app.append(panel);
    let completed=0,failed=0,total=0;
    const loaded=new Set();
    let summaryUsed=false;
    try{const result=await readMarketSummary(sources,signal);if(epoch!==sequence)return;counts=result.counts;total=result.total;completed=sources.length;sources.forEach(s=>loaded.add(s.key));summaryUsed=true}
    catch(e){if(epoch!==sequence||e.name==="AbortError")return;status.textContent="Regional aggregate unavailable; reading the original qualified provider projections…"}
    if(!summaryUsed)for(const s of sources){
        try{
            const data=await loadShard(s,signal);if(epoch!==sequence)return;
            for(const row of data.records){if(!counts.has(row.state))throw Error("Unrecognized jurisdiction");}
            for(const row of data.records){const m=counts.get(row.state);m.set(s.key,(m.get(s.key)||0)+1);total++}
            loaded.add(s.key);completed++;
        }catch(e){if(epoch!==sequence||e.name==="AbortError")return;failed++;app.append(errorBox(s,e))}
    }
    if(epoch!==sequence)return;
    status.dataset.aggregation=summaryUsed?"precomputed":"source-shard-fallback";
    status.textContent=N.format(total)+" provider source records across "+completed+" of 7 sources."+(failed?" Partial coverage; unavailable categories are marked —.":" All 56 target jurisdictions are represented in this snapshot.");
    const sums=[...counts].map(([state,m])=>({state,m,total:[...m.values()].reduce((n,v)=>n+v,0)})).sort((a,b)=>marketValue(b,p.source)-marketValue(a,p.source)||a.state.localeCompare(b.state));
    const tableWrap=table(["Jurisdiction",...sources.map(s=>names[s.key]),"Total source records"],sums.map(({state,m,total})=>[anchor(state,route("geography",{source:p.source,state})),...sources.map(s=>m.has(s.key)&&m.get(s.key)>0?anchor(N.format(m.get(s.key)),route("facilities",{source:s.key,state})):loaded.has(s.key)?"0":"—"),N.format(total)]));
    tableWrap.classList.add("market-region-table");
    for(const row of tableWrap.querySelectorAll("tbody tr"))if(row.firstChild.textContent===p.state)row.classList.add("market-selected-row");
    app.append(el("h2","All provider categories by jurisdiction"),el("p","Sorted by the selected map category. Select a numeric count to open the filtered facility directory. Scroll horizontally if needed.","intro"),tableWrap,el("p","Counts refer to source records, not unique physical facilities or complete regional regulatory coverage.","intro"));
    if(failed)panel.append(el("div","The map is not displayed because one or more public provider sources are unavailable. The table shows only available records.","notice"));
    else await marketMap(panel,p,sums,sources,signal,epoch)
}

const capacityUnits=Object.freeze({nursing:{label:"Certified beds",plural:"certified beds"},dialysis:{label:"Dialysis stations",plural:"dialysis stations"}});
function publicCapacity(row){
    const text=String(row.capacity??"").trim();
    if(!/^\d+$/.test(text))return null;
    const n=Number(text);
    return Number.isSafeInteger(n)?n:null
}
function summarizeCapacity(rows){
    let reported=0,unknown=0,zero=0,sum=0;
    for(const r of rows){
        const n=publicCapacity(r);
        if(n===null){unknown++;continue}
        reported++;if(n===0)zero++;sum+=n
    }
    if(!Number.isSafeInteger(sum))throw Error("Capacity total exceeds safe numeric range");
    return {records:rows.length,reported,unknown,zero,sum}
}
function capacityForm(p,sources){
    const f=el("form",undefined,"toolbar");
    const min=input("Minimum reported capacity","min",p.min),max=input("Maximum reported capacity","max",p.max);
    for(const control of [min,max]){const number=control.querySelector("input");number.type="number";number.min="0";number.max="1000000";number.step="1";number.placeholder="Any"}
    f.append(options("Facility type","source",sources.map(s=>[s.key,names[s.key]]),p.source),
        options("State / territory","state",[["","All jurisdictions"],...states.map(s=>[s,s])],p.state),
        options("Capacity evidence","reported",[["all","All source records"],["known","Numeric capacity reported"],["unknown","Missing or nonnumeric capacity"]],p.reported),
        min,max,options("Sort by","sort",[["capacity_desc","Capacity high to low"],["capacity_asc","Capacity low to high"],["name","Name A–Z"]],p.sort),
        el("button","Apply filters"));
    f.addEventListener("submit",e=>{e.preventDefault();location.hash=route("capacity",Object.fromEntries(new FormData(f)))});
    return f
}
function capacityBands(source){
    return source==="nursing"?[[0,0],[1,49],[50,99],[100,199],[200,null]]:[[0,0],[1,9],[10,19],[20,39],[40,null]]
}
function capacityDistribution(s,p,region){
    const panel=el("section",undefined,"capacity-distribution");
    panel.append(el("h2","Capacity distribution"),el("p","All source records in the selected geography before capacity filters. Choose a band to replace the current capacity filters.","intro"));
    const list=el("div",undefined,"capacity-band-list");
    const entries=capacityBands(s.key).map(([lo,hi])=>({lo,hi,count:0}));let unknown=0;
    for(const r of region){
        const n=publicCapacity(r);
        if(n===null){unknown++;continue}
        const b=entries.find(x=>n>=x.lo&&(x.hi===null||n<=x.hi));
        if(!b)throw Error("Capacity outside distribution bounds");
        b.count++
    }
    if(entries.reduce((n,x)=>n+x.count,unknown)!==region.length)throw Error("Capacity distribution reconciliation failure");
    for(const b of entries){
        const label=b.lo===b.hi?N.format(b.lo):b.hi===null?N.format(b.lo)+"+":N.format(b.lo)+"–"+N.format(b.hi);
        const a=anchor("",route("capacity",{...p,reported:"known",min:b.lo,max:b.hi,page:1}));a.className="capacity-band";a.dataset.band=label;
        a.append(el("span",label+" "+capacityUnits[s.key].label.toLowerCase()),el("strong",N.format(b.count)),el("span","provider records"));list.append(a)
    }
    const a=anchor("",route("capacity",{...p,reported:"unknown",min:"",max:"",page:1}));a.className="capacity-band";a.dataset.band="unknown";
    a.append(el("span","Missing / nonnumeric"),el("strong",N.format(unknown)),el("span","provider records"));list.append(a);
    panel.append(list);return panel
}
function capacityMetric(label,count,note){
    const a=el("article",undefined,"metric");
    a.append(el("small",label),el("strong",count===null?"—":N.format(count)),el("span",note));
    return a
}
async function capacityExplorer(p,signal,epoch){
    const sources=providerSources().filter(s=>Object.hasOwn(capacityUnits,s.key));
    const s=sources.find(s=>s.key===p.source)||sources.find(s=>s.key==="nursing");
    p={...p,source:s.key,reported:p.reported||"all",sort:p.sort||"capacity_desc"};
    const unit=capacityUnits[s.key];
    title("Capacity explorer","Research source-reported nursing-home certified beds and dialysis stations. These are different units and are never added together. This is a public market-size indicator, not proof of current operating capacity, installed equipment, service demand or a procurement opportunity.");
    app.append(capacityForm(p,sources));
    const status=el("div","Loading qualified public capacity fields…","notice");app.append(status);
    try{
        if(p.state&&!states.includes(p.state))throw Error("Invalid jurisdiction");
        if(!["all","known","unknown"].includes(p.reported))throw Error("Invalid capacity evidence filter");
        if(!["capacity_desc","capacity_asc","name"].includes(p.sort))throw Error("Invalid sort");
        const min=p.min==null||p.min===""?null:publicCapacity({capacity:p.min});
        const max=p.max==null||p.max===""?null:publicCapacity({capacity:p.max});
        if(p.min!=null&&p.min!==""&&(min===null||min>1000000))throw Error("Minimum capacity must be a nonnegative whole number up to 1,000,000");
        if(p.max!=null&&p.max!==""&&(max===null||max>1000000))throw Error("Maximum capacity must be a nonnegative whole number up to 1,000,000");
        if(min!==null&&max!==null&&min>max)throw Error("Minimum capacity cannot exceed maximum capacity");
        if((min!==null||max!==null)&&p.reported==="unknown")throw Error("Capacity bounds cannot be combined with missing capacity");
        const data=await loadShard(s,signal);if(epoch!==sequence)return;
        const region=data.records.filter(r=>!p.state||r.state===p.state);
        const filtered=region.filter(r=>{
            const n=publicCapacity(r);
            return !(p.reported==="known"&&n===null||p.reported==="unknown"&&n!==null||min!==null&&(n===null||n<min)||max!==null&&(n===null||n>max))
        });
        const totals=summarizeCapacity(filtered),regionTotals=summarizeCapacity(region);
        const alpha=(a,b)=>String(a.name||"").localeCompare(String(b.name||""),"en",{sensitivity:"base"})||String(a.ccn).localeCompare(String(b.ccn))||String(a.state).localeCompare(String(b.state));
        filtered.sort((a,b)=>{
            if(p.sort==="name")return alpha(a,b);
            const av=publicCapacity(a),bv=publicCapacity(b);
            if(av===null&&bv!==null)return 1;if(bv===null&&av!==null)return -1;
            if(av!==null&&bv!==null&&av!==bv)return p.sort==="capacity_desc"?bv-av:av-bv;
            return alpha(a,b)
        });
        const page=Math.max(1,Math.min(Math.max(1,Math.ceil(filtered.length/pageSize)),Number.parseInt(p.page||"1",10)||1));
        status.replaceChildren(el("span",names[s.key]+" · Source release "+data.release+" · "+N.format(totals.records)+" matching provider source records. "),sourceLink(s));
        const metrics=el("div",undefined,"metrics");
        metrics.append(capacityMetric("Matching source records",totals.records,"Filtered provider records"),
            capacityMetric(unit.label+" reported total",totals.reported?totals.sum:null,"Sum of numeric values only; not unique sites"),
            capacityMetric("Numeric capacity reported",totals.reported,N.format(totals.zero)+" records explicitly report zero"),
            capacityMetric("Missing or nonnumeric",totals.unknown,"Excluded from totals; not treated as zero"));
        app.append(metrics,capacityDistribution(s,p,region),el("h2","Matching providers"));
        if(!filtered.length)app.append(el("div","No source records match these filters. Adjust the selection to continue.","empty"));
        else{
            const result=filtered.slice((page-1)*pageSize,page*pageSize);
            const cells=result.map(r=>[recordCell(s,r,publicFields),shown([r.address,r.city,r.state,r.zip].filter(Boolean).join(", ")),publicCapacity(r)===null?"Not reported / nonnumeric":N.format(publicCapacity(r)),sourceLink(s)]);
            app.append(table(["Provider / CCN","Reported address",unit.label,"Evidence"],cells))
        }
        const pager=el("div",undefined,"pager");pager.append(el("span","Page "+page+" · "+N.format(totals.records)+" matches"));
        if(page>1)pager.append(anchor("Previous",route("capacity",{...p,page:page-1})));
        if(page*pageSize<totals.records)pager.append(anchor("Next",route("capacity",{...p,page:page+1})));
        app.append(pager);
        if(!p.state){
            app.append(el("h2","Regional capacity coverage"),el("p","The same capacity filters apply to these regional aggregates. Select a jurisdiction to inspect its matching source records.","intro"));
            const grouped=new Map(states.map(st=>[st,[]]));
            for(const row of filtered){if(!grouped.has(row.state))throw Error("Unrecognized jurisdiction in provider shard");grouped.get(row.state).push(row)}
            const regional=[...grouped].map(([state,rows])=>({state,...summarizeCapacity(rows)}));
            regional.sort((a,b)=>b.sum-a.sum||b.records-a.records||a.state.localeCompare(b.state));
            app.append(table(["Jurisdiction","Matching records","Numeric capacity reported","Missing / nonnumeric",unit.label+" reported total"],regional.map(g=>[anchor(g.state,route("capacity",{...p,state:g.state,page:1})),N.format(g.records),N.format(g.reported),N.format(g.unknown),g.reported?N.format(g.sum):"—"])))
        }else app.append(add(el("p"),anchor("View all jurisdictions",route("capacity",{...p,state:"",page:1}))));
        app.append(el("p","Within the selected geography, "+N.format(regionTotals.reported)+" of "+N.format(regionTotals.records)+" provider source records report a nonnegative whole-number capacity before capacity filters. Reported zeros are retained. Blank, nonnumeric and negative values are not interpreted. Capacity is derived only from the existing public Care Compare projection.","intro"))
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return;status.replaceWith(errorBox(s,e))}
}

function errorBox(s,e){return add(el("div",undefined,"error"),el("strong","Source unavailable. "),el("span",e.message+". This is not a zero-result or compliance finding. "),sourceLink(s,"Open the official source"))}
function recordCell(s,r,f){const id=value(r,f,"id"),name=value(r,f,"name"),cell=el("div");if(id)cell.append(anchor(shown(name),profileHref(s,r,f)));else cell.append(el("span",shown(name)));cell.append(el("small",shown(id)));return cell}
function cells(view,s,r,f){const v=k=>value(r,f,k);if(view==="citations")return [anchor(shown(v("name")),route("detail",{source:"nursing",id:v("id"),state:v("state"),return:localResearchReturn(location.hash)})),shown(v("id")),shown(v("state")),N.format(r.citation_rows),sourceLink(s)];return [recordCell(s,r,f),shown([v("address"),v("city"),v("state"),v("zip")].filter(Boolean).join(", ")),shown(v("capacity")),sourceLink(s)]}
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

const profileSections=[["summary","Summary"],["services","Services & capacity"],["compliance","Compliance evidence"],["sources","Sources & coverage"]];
function localResearchReturn(hash){
    if(typeof hash!=="string"||hash.length>1600||!/^#(?:facilities|citations|capacity|search|advanced)(?:\?|$)/.test(hash))return "";
    return hash
}
function profileHref(s,r,f){
    return route("detail",{source:s.key,id:value(r,f,"id"),state:value(r,f,"state"),return:localResearchReturn(location.hash)})
}
function profileNav(p,section){
    const nav=el("div",undefined,"profile-nav");
    nav.setAttribute("role","navigation");nav.setAttribute("aria-label","Facility evidence sections");
    for(const [id,label] of profileSections){
        const a=anchor(label,route("detail",{source:p.source,id:p.id,state:p.state,return:localResearchReturn(p.return),section:id==="summary"?"":id}));
        if(id===section)a.setAttribute("aria-current","page");
        nav.append(a)
    }
    return nav
}
function profileGrid(r,s,f){
    const v=k=>value(r,f,k),grid=el("dl",undefined,"detail-grid");
    for(const [label,k] of [["CCN","id"],["Address","address"],["City","city"],["State","state"],["ZIP","zip"],[s.key==="nursing"?"Certified beds":s.key==="dialysis"?"Dialysis stations":"Reported capacity","capacity"]])grid.append(add(el("div"),el("dt",label),el("dd",shown(v(k)))));
    return grid
}
function profileService(r,s,f){
    const unit=capacityUnits[s.key];
    const section=el("section");
    section.append(el("h2","Reported capacity and service evidence"));
    if(unit){
        const v=publicCapacity(r);
        const d=el("dl",undefined,"detail-grid");
        d.append(add(el("div"),el("dt",unit.label),el("dd",v===null?"Not reported / nonnumeric":N.format(v))),add(el("div"),el("dt","Capacity evidence"),el("dd",v===null?"Unknown":v===0?"Reported zero":"Numeric capacity reported")),add(el("div"),el("dt","Publisher source release"),el("dd",s.release)));
        section.append(d,el("p","Capacity describes the reported source field. It does not establish occupancy, current operations, installed equipment or purchase demand.","intro"),
            add(el("p"),anchor("Explore reported capacity in this jurisdiction",route("capacity",{source:s.key,state:value(r,f,"state")}))));
    }else section.append(el("div","No qualified, comparable numeric capacity unit is published for this provider category. Any original reported capacity text in Summary is not interpreted as a standardized measurement.","notice"));
    section.append(el("h2","Other service capabilities"),el("div","Individual QIES and iQIES service observations are not published for this source record. National aggregate evidence is available separately; it is not evidence of a particular service at this facility.","notice"),add(el("p"),anchor("National service evidence",route("services"))));
    return section
}
async function profileCompliance(r,s,f,signal,epoch){
    const section=el("section"),v=k=>value(r,f,k);
    if(s.key!=="nursing"){
        section.append(el("h2","Compliance evidence"),el("div","The public directory does not contain facility-linked inspection or citation evidence for this provider category. Missing evidence is not a finding of compliance.","notice"),add(el("p"),anchor("Hospital survey coverage",route("hospital-surveys"))));
        return section
    }
    const summary=el("div","Loading same-state historical citation evidence…","notice");
    section.append(el("h2","Nursing home compliance evidence"),el("p","Exact CCN and reported state candidate links. Historical citation rows do not establish currently outstanding violations or compliance.","intro"),summary);
    const rows=[];
    for(const cs of citationSources()){
        try{
            const cr=await query(cs,{field:"id",q:v("id"),state:v("state")},signal);
            if(epoch!==sequence)return null;
            const n=cr.rows.reduce((a,b)=>a+b.citation_rows,0);
            rows.push([names[cs.key],cr.total?N.format(n):"No matching group",cs.release,anchor("Inspect source totals",route("citations",{source:cs.key,field:"id",q:v("id"),state:v("state")}))])
        }catch(e){if(epoch!==sequence||e.name==="AbortError")return null;rows.push([names[cs.key],"Unavailable",cs.release,sourceLink(cs)])}
    }
    if(epoch!==sequence)return null;
    summary.replaceWith(table(["Source","Historical citation rows","Source release","Evidence"],rows));
    section.append(add(el("p"),anchor("National compliance research",route("compliance-research"))));
    return section
}
function profileEvidenceTable(headers,rows){
    const wrap=table(headers,rows);wrap.classList.add("profile-evidence-table");wrap.setAttribute("aria-label","Evidence availability; scroll horizontally if needed");return wrap
}
function profileSources(s,r,f){
    const section=el("section");
    section.append(el("h2","Source and release"),table(["Evidence","Value"],[["Provider source",names[s.key]],["Source identifier (CCN)",shown(value(r,f,"id"))],["Reported state",shown(value(r,f,"state"))],["Published release",s.release],["Public projection",sourceLink(s,"Official source")]]),
        el("h2","Evidence availability for this record"),
        el("p","Scroll horizontally to see all evidence columns.","profile-scroll-hint"),profileEvidenceTable(["Evidence area","Public availability","Research link"],[
            ["Provider identity","Published source record",sourceLink(s)],
            ["Comparable capacity",capacityUnits[s.key]?(publicCapacity(r)===null?"Unknown":"Source-reported "+capacityUnits[s.key].label.toLowerCase()):"No qualified unit",capacityUnits[s.key]?anchor("Capacity explorer",route("capacity",{source:s.key,state:value(r,f,"state")})):"—"],
            ["Nursing citation aggregates",s.key==="nursing"?"Same-CCN/state candidate lookup":"No facility-linked public evidence",s.key==="nursing"?anchor("Compliance section",route("detail",{source:s.key,id:value(r,f,"id"),state:value(r,f,"state"),return:localResearchReturn(read().p.return),section:"compliance"})):anchor("National compliance research",route("compliance-research"))],
            ["Certification registry evidence","Individual relationships not published",anchor("Certification registry coverage",route("certifications"))],
            ["Clinical service capability","Individual observations not published",anchor("National service evidence",route("services"))],
            ["Organizational relationships","Individual relationships not published",anchor("Ownership evidence coverage",route("ownership"))],
            ["Equipment and environment","Individual relationships not published",anchor("National equipment and environmental research",route("equipment-environment"))],
            ["Property / procurement","No qualified public facility relationships","—"]
        ]),el("div","The coverage links describe national source-family research, not resolved links for this facility. Exact source identifiers are not canonical physical-site or property ownership determinations.","notice"));
    return section
}
async function detail(p,signal,epoch){
    const s=providerSources().find(s=>s.key===p.source);
    title("Source record","Exact source identifier lookup. This is not a canonical property or controlling-ownership determination.");
    if(!s||!p.id){app.append(el("div","Source and identifier are required.","empty"));return}
    if(p.state&&!states.includes(p.state)){app.append(el("div","Invalid jurisdiction.","error"));return}
    const section=p.section||"summary";
    if(!profileSections.some(x=>x[0]===section)){app.append(el("div","Unknown facility evidence section.","error"));return}
    const status=el("div","Loading qualified provider record…","notice");app.append(status);
    try{
        const result=await query(s,{field:"id",q:p.id,state:p.state||""},signal);
        if(epoch!==sequence)return;
        if(!result.total){status.replaceWith(el("div","No matching source record returned.","empty"));return}
        const first=result.rows[0],f=result.f;
        title(result.total===1?shown(value(first,f,"name")):"Provider source records","Source-scoped Care Compare facility research. This is not a canonical physical property or controlling-ownership determination.");
        const meta=el("div",undefined,"profile-meta");
        meta.append(el("span",names[s.key]),el("span","CCN "+p.id),el("span","Source release "+s.release),el("span",N.format(result.total)+" matching source record(s)"));
        app.append(meta);
        const back=localResearchReturn(p.return),links=el("div",undefined,"links");
        links.append(anchor(back?"Back to results":"Back to directory",back||route("facilities",{source:s.key,state:p.state})),sourceLink(s));app.append(links,profileNav(p,section));
        if(result.total>1)app.append(el("div","Multiple source records share the requested identifier; no silent merge has been performed. Each record is displayed separately.","notice"));
        for(const r of result.rows){
            if(result.total>1)app.append(el("h2",shown(value(r,f,"name"))+" · "+shown(value(r,f,"state"))));
            if(section==="summary"){
                app.append(el("h2","Provider identity"),profileGrid(r,s,f));
                if(capacityUnits[s.key])app.append(add(el("p"),anchor("Explore reported capacity in this jurisdiction",route("capacity",{source:s.key,state:value(r,f,"state")}))));
                if(s.key==="nursing"){const c=await profileCompliance(r,s,f,signal,epoch);if(!c||epoch!==sequence)return;app.append(c)}
                app.append(el("h2","Related source coverage"),add(el("div",undefined,"links"),anchor("Certification registry coverage",route("certifications")),anchor("Hospital survey coverage",route("hospital-surveys")),anchor("Ownership evidence coverage",route("ownership")),anchor("National service evidence",route("services")),anchor("National equipment and environmental research",route("equipment-environment"))),el("div","Individual-level certification, equipment, environmental, property and ownership relationships are not inferred or published here. Coverage links describe national source families, not resolved relationships for this facility.","notice"));
            }else if(section==="services")app.append(profileService(r,s,f));
            else if(section==="compliance"){const c=await profileCompliance(r,s,f,signal,epoch);if(!c||epoch!==sequence)return;app.append(c)}
            else app.append(profileSources(s,r,f))
        }
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return;title("Source record","Provider evidence unavailable.");app.append(errorBox(s,e))}
}
function coverageView(view){const own=view==="ownership",items=byFamily(own?"pecos":"qcor");title(own?"Ownership evidence coverage":"Hospital survey coverage",own?"Aggregate PECOS qualification only. Individual ownership records and organizational projections are not published on this public site.":"QCOR survey rows include tags, memos, repeated projections and historical evidence. Correction status is unknown; narrative and row-level workbook data are not published here.");app.append(historicalNote(),table(["Source","Release period","Historical retained rows","Evidence"],sourceRows(items)),el("div",own?"Exact CCN and state candidates do not establish controlling ownership, physical property title, complete portfolios or current operational responsibility.":"Use the official QCOR report for source research. This site does not publish or infer active hospital violations.","notice"))}
function sourceRegister(p){title("Source register","Discovered sources, historical qualification, and reuse review are separate. A listed source is not necessarily loaded or publicly searchable.");const f=el("form",undefined,"toolbar");f.append(input("Filter source names, publishers or jurisdiction","q",p.q),el("button","Filter"));f.addEventListener("submit",e=>{e.preventDefault();location.hash=route("sources",Object.fromEntries(new FormData(f)))});app.append(f);let overlay=new Map(coverage.sources.map(s=>[s.id,s]));let q=(p.q||"").toLowerCase();let rows=register.sources.filter(s=>!q||[s.id,s.source,s.publisher,s.jurisdiction,s.category].some(x=>String(x).toLowerCase().includes(q)));let page=Math.max(1,Math.min(Math.ceil(rows.length/pageSize)||1,Number(p.page)||1));app.append(el("p",N.format(rows.length)+" source entries · original register preserved"));app.append(table(["Source","Jurisdiction","Qualification","Reuse review","Evidence"],rows.slice((page-1)*pageSize,page*pageSize).map(s=>[s.id+" · "+s.source,s.jurisdiction,overlay.get(s.id)?.status||"Discovered / not tested",overlay.get(s.id)?.reuse_review||s.reuse_review,safeExternal(s.source_url)?anchor("Publisher source",safeExternal(s.source_url),true):"See register"])));const pager=el("div",undefined,"pager");if(page>1)pager.append(anchor("Previous",route("sources",{...p,page:page-1})));if(page*pageSize<rows.length)pager.append(anchor("Next",route("sources",{...p,page:page+1})));app.append(pager)}
async function render(){if(!lock)return;if(active)active.abort();active=new AbortController();const {view,p}=read(),epoch=++sequence;for(const a of document.querySelectorAll("nav a")){if(a.getAttribute("href")==="#"+view)a.setAttribute("aria-current","page");else a.removeAttribute("aria-current")}if(view==="overview")overview();else if(view==="search")await unifiedSearch(p,active.signal,epoch);else if(view==="advanced")await advancedResearch(p,active.signal,epoch);else if(view==="industry")industryResearch(p);else if(view==="geography")await geography(p,active.signal,epoch);else if(view==="capacity")await capacityExplorer(p,active.signal,epoch);else if(["services","compliance-research","equipment-environment","data-evidence"].includes(view))await intelligence(view,active.signal,epoch);else if(["facilities","citations"].includes(view))await directory(view,p,active.signal,epoch);else if(view==="certifications")certificationCoverage();else if(view==="detail")await detail(p,active.signal,epoch);else if(["ownership","hospital-surveys"].includes(view))coverageView(view);else if(view==="sources")sourceRegister(p);else title("Page not found","Choose an available workspace from navigation.");}
$("global-search").addEventListener("submit",e=>{e.preventDefault();let q=$("global-q").value.trim();location.hash=route("search",{field:/^\d{5}$/.test(q)?"zip":/^(?=.*[0-9])[A-Za-z0-9]{6}$/.test(q)?"id":"name",q})});
document.querySelector(".skip").addEventListener("click",e=>{e.preventDefault();$("workspace").focus()});
window.addEventListener("hashchange",()=>{render()});
(async()=>{try{[lock,register,coverage,publicManifest]=await Promise.all(["research/snapshot_release_20261125.json","research/facilitysignal_source_register_v0.2.json","research/coverage_status.json","web/public-directory/manifest.json"].map(async path=>{let r=await fetch(path);if(!r.ok)throw Error("Source metadata HTTP "+r.status);return r.json()}));if(!Array.isArray(lock.sources)||!Array.isArray(register.sources)||!Array.isArray(coverage.sources)||!Array.isArray(publicManifest.jurisdictions)||!publicManifest.sources)throw Error("Invalid source metadata");render()}catch(e){title("Source metadata unavailable","The workspace could not load its source metadata. No data are inferred.");app.append(el("div",e.message,"error"),anchor("FacilitySignal repository","https://github.com/JeremyHennessy/FacilitySignal",true))}})();
