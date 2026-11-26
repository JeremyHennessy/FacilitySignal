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
function overview(){
    title("National overview","Discover healthcare facilities, investigate historical evidence and build a research portfolio. Start with a question rather than a dataset.");
    const panel=el("section",undefined,"home-discovery");
    panel.append(el("h2","Find facilities"),el("p","Search public provider records by name, identifier, address or location.","intro"));
    const f=el("form",undefined,"toolbar home-discovery-form");
    const category=options("Provider category","source",[["all","All provider categories"],...providerSources().map(s=>[s.key,names[s.key]])],"all");
    const state=options("State / territory","state",[["","All jurisdictions"],...states.slice().sort().map(s=>[s,s])],"");
    const field=options("Search field","field",[["name","Provider name contains"],["id","Exact CCN"],["city","Exact city"],["zip","Exact ZIP"],["address","Address contains"]],"name");
    const q=input("Search value (optional)","q","");
    const go=el("button","Find matching facilities");go.type="submit";
    f.append(category,state,field,q,go);
    f.addEventListener("submit",e=>{e.preventDefault();location.hash=route("advanced",{...Object.fromEntries(new FormData(f)),run:1})});
    panel.append(f);app.append(panel);
    const metrics=el("div",undefined,"metrics home-metrics");
    metrics.append(card("Published provider records",aggregate(providerSources()),"Seven source families",route("facilities")),card("Jurisdictions",publicManifest.jurisdictions.length,"Reported provider geography",route("geography")),card("Historical nursing citation rows",aggregate(citationSources()),"Health and fire source rows",route("citations")));
    app.append(metrics,el("p","Pinned historical releases · source records are not unique buildings, and citation rows are not current outstanding violations.","intro home-scope"));
    const tasks=[
        ["Discover a market","Compare regional provider coverage and reported capacity.",[["Explore the national map",route("geography")],["Research reported capacity",route("capacity")]]],
        ["Investigate facilities and compliance","Find historical regulatory evidence and operational context.",[["Historical compliance research",route("compliance-research")],["Hospital infrastructure",route("hospital-infrastructure")],["Equipment and water safety evidence",route("equipment-environment")]]],
        ["Research organizations and portfolios","Save source records, compare facilities and review reported affiliation evidence.",[["Open my saved portfolio",route("saved-portfolio")],["Reported nursing chain research",route("nursing-portfolios")],["Organizational relationship evidence",route("ownership")]]],
        ["Explore commercial markets","Follow evidence-based service, financial and purchasing research pathways.",[["Browse industry research pathways",route("industry")],["Historical financial report evidence",route("financial-research")],["Federal procurement evidence",route("procurement")]]]
    ];
    app.append(el("h2","Choose a research workflow"));
    const grid=el("div",undefined,"home-workflows");
    for(const [label,note,links] of tasks){const box=el("section",undefined,"home-workflow");box.append(el("h3",label),el("p",note,"intro"));const list=el("div",undefined,"home-workflow-links");for(const [text,url] of links)list.append(anchor(text,url));box.append(list);grid.append(box)}
    app.append(grid);
    const coverageDetails=el("details",undefined,"home-coverage");
    coverageDetails.append(el("summary","Data coverage and limitations"),historicalNote(),el("h2","Published provider source coverage"),table(["Provider family","Qualified release","Historical rows","Evidence"],sourceRows(providerSources())));
    const pecos=byFamily("pecos");
    coverageDetails.append(el("h2","Additional qualified historical source rows"),table(["Source evidence","Rows"],[
        [anchor("Certification and laboratory coverage",route("certifications")),N.format(aggregate(byFamily("registry")))],
        [anchor("Hospital survey evidence",route("hospital-surveys")),N.format(aggregate(byFamily("qcor")))],
        [anchor("Reported enrollment evidence",route("ownership")),N.format(aggregate(pecos.filter(s=>s.key.endsWith("enrollment"))))],
        ["Reported organizational roles",N.format(aggregate(pecos.filter(s=>s.key.endsWith("owner"))))],
        ["Reported ownership changes",N.format(aggregate(pecos.filter(s=>s.key.endsWith("chow"))))]
    ]),el("p","Individual registry, hospital survey, ownership and financial records are not published in this public workspace. Qualified aggregate evidence cannot establish legal title, current equipment or confirmed purchasing intent.","intro"),aggregateResearchLinks());
    app.append(coverageDetails,add(el("div",undefined,"links"),anchor("Review source inventory",route("sources")),anchor("Review national data quality",route("data-evidence"))))
}
function aggregateResearchLinks(){
    const wrap=el("div",undefined,"links");
    for(const [name,view] of [["Advanced facility search","advanced"],["Industry research","industry"],["Service intelligence","services"],["Compliance research","compliance-research"],["Equipment & environmental research","equipment-environment"],["Procurement research","procurement"],["Financial report research","financial-research"],["Saved facility portfolio","saved-portfolio"],["Data intelligence","data-evidence"]])wrap.append(anchor(name,route(view)));
    return wrap
}
async function intelligence(view,signal,epoch){
    const labels={"financial-research":"Financial report research","hospital-infrastructure":"Hospital infrastructure research","nursing-portfolios":"Nursing portfolio research",services:"Service intelligence","compliance-research":"Compliance research","equipment-environment":"Equipment & environmental research","data-evidence":"Data intelligence"};
    title(labels[view],"Historical national aggregate qualification. Public research only; not a live national database.");
    const waiting=el("div","Loading qualified aggregate evidence…","notice");app.append(waiting);
    try{
        const response=await fetch("web/public-intelligence.json",{signal});
        if(!response.ok)throw Error("Evidence projection HTTP "+response.status);
        const data=await response.json();if(epoch!==sequence)return;
        if(data.version!==1||data.scope!=="historical national aggregate qualification"||!Array.isArray(data.sections))throw Error("Unexpected evidence projection");
        const nursingPortfolio=view==="nursing-portfolios",hospitalInfra=view==="hospital-infrastructure";
        const ids=nursingPortfolio?["nursing-chain-coverage","nursing-affiliation-corroboration","nursing-inspection-disputes"]:hospitalInfra?["qies-hospital-comparison","qies-hospital-service-subset","qies-hospital-count-subset","hospital-enrollment-subgroups"]:[];
        const allGroups=ids.length?data.sections.flatMap(s=>s.groups):[];
        if(ids.some(id=>allGroups.filter(g=>g.id===id).length!==1))throw Error("Missing or ambiguous qualification group");
        const section=ids.length?{title:labels[view],intro:nursingPortfolio?"Research CMS-reported nursing-home groups, their member records and reported capacity by geography. Publisher-defined affiliations are not legal ownership or physical property portfolios.":"Research historical national service-provision and infrastructure evidence. QIES historical code labels are provisional; these aggregates are not installed equipment inventories, current operations, staffing totals or facility-level relationships.",groups:ids.map(id=>allGroups.find(g=>g.id===id))}:data.sections.find(x=>x.id===view);
        if(!section||!Array.isArray(section.groups))throw Error("Missing evidence section");
        title(section.title,section.intro);
        const nav=el("div",undefined,"links");
        if(view==="services")nav.append(anchor("Search reported public capacity",route("capacity")),anchor("Browse facility directory",route("facilities")),dialysisResearchLink(),hhaResearchLink(),anchor("Hospital infrastructure research",route("hospital-infrastructure")));
        if(view==="compliance-research")nav.append(anchor("Search public nursing citation aggregates",route("citations")),anchor("Hospital survey coverage",route("hospital-surveys")),anchor("Nursing portfolio research",route("nursing-portfolios")));
        if(nursingPortfolio){
            const waiting=el("div","Loading exact nursing chain membership evidence…","notice");app.append(waiting);
            const explorer=await nursingChainExplorer(read().p,signal,epoch);if(!explorer||epoch!==sequence)return;
            waiting.replaceWith(explorer);
            const form=el("form",undefined,"toolbar");
            const state=options("Research jurisdiction","state",[["","All jurisdictions"],...states.slice().sort().map(s=>[s,s])],"");
            const select=options("Research pathway","path",[["facilities","Nursing provider directory"],["capacity","Reported certified beds"],["nursing-health","Historical health citations"],["nursing-fire","Historical fire citations"]],"facilities");
            const submit=el("button","Open research");submit.type="submit";
            form.append(state,select,submit);
            form.addEventListener("submit",e=>{
                e.preventDefault();const p=Object.fromEntries(new FormData(form));
                if(p.state&&!states.includes(p.state))return;
                if(["facilities","capacity"].includes(p.path))location.hash=route(p.path,{source:"nursing",state:p.state});
                else if(["nursing-health","nursing-fire"].includes(p.path))location.hash=route("citations",{source:p.path,state:p.state});
            });
            app.append(el("h2","Research individual nursing-home records"),el("p","Jurisdiction filters open the existing qualified source-specific workspaces. These results are not filtered by chain membership.","intro"),form);
            nav.append(anchor("Ownership evidence coverage",route("ownership")),anchor("National data intelligence",route("data-evidence")));
        }
        if(hospitalInfra){
            const f=el("form",undefined,"toolbar"),state=options("Hospital research jurisdiction","state",[["","All jurisdictions"],...states.slice().sort().map(s=>[s,s])],"");
            const go=el("button","Browse hospital records");go.type="submit";f.append(state,go);
            f.addEventListener("submit",e=>{e.preventDefault();const st=new FormData(f).get("state");if(st&&!states.includes(st))return;location.hash=route("facilities",{source:"hospital",state:st})});
            app.append(el("h2","Research individual hospitals"),el("p","The jurisdiction selector opens the provider directory only; national infrastructure aggregates below cannot be filtered by jurisdiction or attributed to individual hospitals.","intro"),f);
            nav.append(anchor("Hospital market explorer",route("geography",{source:"hospital"})),anchor("Hospital survey coverage",route("hospital-surveys")),anchor("Ownership evidence coverage",route("ownership")));
        }
        if(view==="financial-research")nav.append(anchor("Hospital directory",route("facilities",{source:"hospital"})),anchor("Nursing directory",route("facilities",{source:"nursing"})),anchor("Home health directory",route("facilities",{source:"home-health"})),anchor("Hospital infrastructure research",route("hospital-infrastructure")));
        if(view==="equipment-environment")nav.append(anchor("Review source register",route("sources")),anchor("Hospital infrastructure research",route("hospital-infrastructure")),anchor("Nursing fire citations",route("citations",{source:"nursing-fire"})),anchor("Dialysis service research",route("dialysis-services")));
        if(view==="data-evidence")nav.append(anchor("Source inventory",route("sources")),anchor("Certification registry coverage",route("certifications")));
        app.append(nav);
        for(const g of section.groups){
            if(!Number.isSafeInteger(g.run)||g.run<=0||!Array.isArray(g.columns)||!Array.isArray(g.rows)||g.rows.some(r=>!Array.isArray(r)||r.length!==g.columns.length||r.some(x=>x!==null&&typeof x!=="string"&&!(Number.isSafeInteger(x)&&x>=0))))throw Error("Invalid evidence group");
            const src=safeExternal(g.source);
            const evidenceTable=table(g.columns,g.rows.map(r=>r.map(x=>x===null?"—":typeof x==="number"?N.format(x):x)));
            evidenceTable.classList.add("intelligence-table");
            evidenceTable.setAttribute("aria-label",g.title+"; scroll horizontally if needed");
            const note=g.id==="nursing-chain-coverage"?g.note.replace("names and identifiers are not published.","the original aggregate audit does not contain names or identifiers. The separate nursing portfolio membership projection is qualified independently."):g.note;
            app.append(el("h2",g.title),el("p",note,"intro"));
            if(g.columns.length>3||g.id==="clia-certificate")app.append(el("p","Scroll horizontally to see all columns.","intelligence-scroll-hint"));
            if((hospitalInfra&&["qies-hospital-service-subset","qies-hospital-count-subset"].includes(g.id))||(view==="financial-research"&&g.id.endsWith("-cost-measure-quality"))){
                const filter=el("div",undefined,"toolbar"),field=input("Filter "+(g.id.endsWith("service-subset")?"service names":g.id.endsWith("-cost-measure-quality")?"measure names":"infrastructure field names"),"q","");
                const search=field.querySelector("input"),summary=el("p",N.format(g.rows.length)+" evidence categories","intro");
                const body=evidenceTable.querySelector("tbody"),rows=Array.from(body.rows);
                search.addEventListener("input",()=>{const q=search.value.trim().toLowerCase();let n=0;rows.forEach((tr,i)=>{tr.hidden=!String(g.rows[i][0]).toLowerCase().includes(q);if(!tr.hidden)n++});summary.textContent=N.format(n)+" of "+N.format(rows.length)+" evidence categories"});
                filter.append(field,summary);app.append(filter);
            }
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
    const enrichment=s.key==="long-term-hospital"?publicManifest.field_enrichments?.[s.key]:null;
    if(s.key==="long-term-hospital"&&(!enrichment||!/^[0-9a-f]{64}$/.test(enrichment.projection_sha256)))throw Error("Qualified total-bed projection unavailable");
    const response=await fetch("web/public-directory/"+s.key+".json"+(enrichment?"?v="+enrichment.projection_sha256.slice(0,16):""),{signal});
    if(!response.ok)throw Error("Static source HTTP "+response.status);
    const data=await response.json(),published=publicManifest.sources[s.key];
    if(data.source!==s.key||data.release!==s.release||!Array.isArray(data.records)||data.row_count!==s.stored_rows||data.records.length!==published?.published_records)throw Error("Static source manifest mismatch");
    if(s.key.startsWith("nursing-")){
        if(data.records.some(r=>!Number.isSafeInteger(r.citation_rows)||r.citation_rows<1)||data.records.reduce((n,r)=>n+r.citation_rows,0)!==data.row_count)throw Error("Citation aggregate reconciliation failed");
    }else if(data.records.length!==data.row_count)throw Error("Provider count mismatch");
    if(enrichment){const totals=summarizeCapacity(data.records);if(totals.reported!==enrichment.numeric_rows||totals.unknown!==enrichment.unknown_rows||totals.sum!==enrichment.sum)throw Error("Total-bed projection reconciliation failed")}
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



const institutionalPin=Object.freeze({payload:"7e5c5afa86a535c1acf753b39a5f1ad97dc3ecb925cded12e64a4dd703dd567d",scope:"Candidate public CMS reported institutional flags; historical release, not live service, legal title, risk or compliance.",sources:{"dialysis":{"directory_sha256":"e8343f678ec1780ac49047f162754657f60eaa3f61b1d4f48ea4b55d39d4008a","fields":["chain_owned_or_managed","late_shift","in_center_hemodialysis","peritoneal_dialysis","home_hemodialysis_training"],"release":"2026-10-28","source_sha256":"9b0232d73b8aa9628b51bc76b7246b8590daa0393ec9dfd3126171ce571469ed","rows":7471,"yes":{"chain_owned_or_managed":6734,"late_shift":1136,"in_center_hemodialysis":6959,"peritoneal_dialysis":4067,"home_hemodialysis_training":2411}},"hospital":{"directory_sha256":"222096b1bf7cfbfcb37c4c6375d6ba686c6e3ccdd7af47c542bfb91ad34d621a","fields":["emergency_services"],"release":"2026-11-12","source_sha256":"ff2a82a7149975fb86348e7f901aa3bcd9f3701e8b0ecd0ab34702df193ff559","rows":5435,"yes":{"emergency_services":4501}},"nursing":{"directory_sha256":"36363899e56c97433686ce8617a7d4b557b272a155e8a8eba1822c6f7a36e3ce","fields":["ownership_change_12_months"],"release":"2026-10-28","source_sha256":"ab70309ae6f0ee86b19fe9acb61a6d2953f970d3b09e80bb9b090e4b19ce35a2","rows":14686,"yes":{"ownership_change_12_months":60}}}});
const institutionalLabels=Object.freeze({emergency_services:"Emergency services",chain_owned_or_managed:"Chain owned or managed",late_shift:"Shift starting at 5 p.m. or later",in_center_hemodialysis:"In-center hemodialysis",peritoneal_dialysis:"Peritoneal dialysis",home_hemodialysis_training:"Home hemodialysis training",ownership_change_12_months:"Ownership change in preceding 12 months"});
const institutionalValues=Object.freeze({reported_yes:"Reported yes",reported_no:"Reported no"});
const institutionalKey=r=>r.state+":"+r.ccn;
function institutionalFilter(p,source){
    const field=p.institutional_field||"",value=p.institutional_value||"";
    if(!field&&!value)return null;
    if(!Object.hasOwn(institutionalPin.sources,source)||!institutionalPin.sources[source].fields.includes(field)||!Object.hasOwn(institutionalValues,value))throw Error("Choose an institutional characteristic and reported value for its applicable provider category.");
    return {field,value}
}
async function institutionalEvidence(s,signal){
    const pin=institutionalPin.sources[s.key];
    if(!pin||s.release!==pin.release||s.sha256!==pin.source_sha256||s.stored_rows!==pin.rows||publicManifest.sources[s.key]?.published_records!==pin.rows)throw Error("Institutional source release requires requalification");
    const [directory,pack]=await Promise.all([
        exactJson("web/public-directory/"+s.key+".json?v="+pin.directory_sha256.slice(0,16),pin.directory_sha256,signal),
        exactJson("web/institutional-evidence.json?v="+institutionalPin.payload.slice(0,16),institutionalPin.payload,signal)
    ]);
    if(directory.source!==s.key||directory.release!==pin.release||directory.row_count!==pin.rows||!Array.isArray(directory.records)||directory.records.length!==pin.rows)throw Error("Institutional directory scope mismatch");
    if(!dialysisKeys(pack,["format_version","scope","sources"])||pack.format_version!==1||pack.scope!==institutionalPin.scope||!dialysisKeys(pack.sources,Object.keys(institutionalPin.sources)))throw Error("Institutional pack scope mismatch");
    const part=pack.sources[s.key];
    if(!dialysisKeys(part,["release","source_sha256","directory_sha256","fields","records"])||part.release!==pin.release||part.source_sha256!==pin.source_sha256||part.directory_sha256!==pin.directory_sha256||!Array.isArray(part.fields)||part.fields.join("|")!==pin.fields.join("|")||!Array.isArray(part.records)||part.records.length!==pin.rows)throw Error("Institutional evidence pin mismatch");
    const keys=new Set(directory.records.map(institutionalKey)),records=new Map(),counts=Object.fromEntries(pin.fields.map(f=>[f,0]));
    if(keys.size!==pin.rows)throw Error("Duplicate directory key");
    for(const row of part.records){
        if(!Array.isArray(row)||row.length!==2+pin.fields.length||typeof row[0]!=="string"||!/^[A-Z0-9]{6}$/.test(row[0])||!states.includes(row[1]))throw Error("Invalid institutional key");
        const key=row[1]+":"+row[0];
        if(!keys.has(key)||records.has(key))throw Error("Institutional membership mismatch");
        const obs={};
        for(let i=0;i<pin.fields.length;i++){const f=pin.fields[i],v=row[i+2];if(!Object.hasOwn(institutionalValues,v))throw Error("Invalid institutional value");obs[f]=v;if(v==="reported_yes")counts[f]++}
        records.set(key,obs);
    }
    if(records.size!==keys.size||pin.fields.some(f=>counts[f]!==pin.yes[f]))throw Error("Institutional evidence counts mismatch");
    return {directory,records,release:pin.release}
}
async function institutionalProfile(r,s,signal,epoch){
    const section=el("section",undefined,"institutional-profile");
    section.append(el("h2","Care Compare reported characteristics"),el("p","Historical CMS publisher-reported flags from "+s.release+". Distinct from current availability, equipment, legal title and clinical or property risk.","intro"));
    try{
        const data=await institutionalEvidence(s,signal);if(epoch!==sequence)return null;
        const obs=data.records.get(institutionalKey(r));if(!obs)throw Error("No exact provider evidence");
        const grid=el("dl",undefined,"detail-grid");
        for(const field of institutionalPin.sources[s.key].fields){
            const cell=add(el("div"),el("dt",institutionalLabels[field]),el("dd",institutionalValues[obs[field]]));
            cell.dataset.field=field;cell.dataset.value=obs[field];grid.append(cell)
        }
        section.append(grid,add(el("div",undefined,"links"),sourceLink(s,"Official CMS source"),anchor("Search these reported characteristics",route("advanced",{source:s.key,state:r.state,institutional_field:institutionalPin.sources[s.key].fields[0],institutional_value:obs[institutionalPin.sources[s.key].fields[0]],run:1}))));
        section.dataset.evidence="qualified";
    }catch(e){if(epoch!==sequence||signal.aborted||e.name==="AbortError")return null;section.dataset.evidence="unavailable";section.append(el("div","Qualified institutional evidence unavailable. No reported yes/no value has been inferred.","error"),sourceLink(s))}
    return section
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
    if(filteredCapacity&&!Object.hasOwn(capacityUnits,source))throw Error("Choose one capacity-qualified category: nursing homes, dialysis facilities or long-term care hospitals. Their units cannot be combined.");
    if(bounds.min!==null&&bounds.max!==null&&bounds.min>bounds.max)throw Error("Minimum capacity cannot exceed maximum capacity");
    if(reported==="unknown"&&(bounds.min!==null||bounds.max!==null))throw Error("Capacity bounds cannot be combined with missing capacity");
    if(p.page&&!/^\d{1,6}$/.test(p.page))throw Error("Invalid page");
    const page=Math.max(1,Math.min(100000,Number(p.page)||1));
    return {...p,source,field,reported,q:(p.q||"").trim(),state:p.state||"",page,bounds,filteredCapacity,institutional:institutionalFilter(p,source)}
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
    const institutionalField=options("Institutional characteristic","institutional_field",[["","Any characteristic"]],"");
    const institutionalValue=options("Reported value","institutional_value",Object.entries(institutionalValues),p.institutional_value);
    f.append(category,state,field,q,evidence,min,max,hint,institutionalField,institutionalValue,apply,reset);
    const selector=category.querySelector("select"),ev=evidence.querySelector("select"),lo=min.querySelector("input"),hi=max.querySelector("input");
    const ifield=institutionalField.querySelector("select"),ivalue=institutionalValue.querySelector("select");
    function syncInstitutional(selected){
        const pin=institutionalPin.sources[selector.value];
        ifield.replaceChildren(...[["","Any characteristic"],...(pin?pin.fields.map(k=>[k,k==="ownership_change_12_months"?"Ownership change (past year)":institutionalLabels[k]]):[])].map(([v,t])=>{const o=el("option",t);o.value=v;return o}));
        ifield.value=pin?.fields.includes(selected)?selected:"";
        ifield.disabled=!pin;ivalue.disabled=!pin||!ifield.value;
        institutionalField.hidden=!pin;institutionalValue.hidden=!pin;
    }
    ifield.addEventListener("change",()=>{ivalue.disabled=!ifield.value;if(!ivalue.disabled)ivalue.value="reported_yes"});
    syncInstitutional(p.institutional_field);
    function sync(){
        const unit=capacityUnits[selector.value],available=!!unit;
        for(const c of [ev,lo,hi]){c.disabled=!available;c.setAttribute("aria-describedby",hint.id)}
        if(!available){ev.value="all";lo.value="";hi.value="";hint.textContent="Capacity filters require a single nursing-home, dialysis or long-term care hospital category. Other public provider categories do not contain a qualified numeric capacity unit."}
        else{
            hint.textContent="Capacity unit: "+unit.label+". Reported zero is distinct from missing or nonnumeric data. For qualified individual dialysis service observations use Dialysis service research.";
            const missing=ev.value==="unknown";lo.disabled=missing;hi.disabled=missing;
            if(missing){lo.value="";hi.value=""}
        }
    }
    selector.addEventListener("change",()=>{ev.value="all";lo.value="";hi.value="";sync();syncInstitutional("")});
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
    const include=rows.some(x=>x.institutional);
    if(include)header.push("institutional_field","institutional_value","institutional_release");
    const records=rows.map(({s,r,institutional})=>{const unit=capacityUnits[s.key],n=unit?publicCapacity(r):null;return [s.key,s.release,r.ccn,r.name,r.address,r.city,r.state,r.zip,n,unit?unit.label:"",unit?(n===null?"missing_or_nonnumeric":"numeric_reported"):"no_qualified_public_unit",...(include?[institutional?.field||"",institutional?.value||"",institutional?s.release:""]:[])]});
    const content=[header,...records].map(row=>row.map(safeCsvCell).join(",")).join("\r\n")+"\r\n";
    const url=URL.createObjectURL(new Blob([content],{type:"text/csv;charset=utf-8"})),a=el("a");
    a.href=url;a.download="facilitysignal-public-search-page.csv";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
async function advancedResearch(p,signal,epoch){
    title("Advanced facility search","Combine provider category, jurisdiction, text or identifier search, source-specific capacity and selected reported institutional characteristics. Results are program records, not unique buildings or confirmed service opportunities.");
    const sources=providerSources(),form=advancedForm(p,sources);
    app.append(form,add(el("div",undefined,"links"),anchor("Service research coverage",route("services")),anchor("Industry research pathways",route("industry",{state:p.state})),dialysisResearchLink(p.state),hhaResearchLink(p.state)));
    let params;
    try{params=advancedParameters(p,sources)}catch(e){app.append(el("div",e.message,"error"));return}
    if(!p.run&&!p.q&&!p.state&&!p.source&&!p.reported&&!p.min&&!p.max&&!p.institutional_field){app.append(el("div","Select filters and apply the search. Searching all categories without text is allowed; results are paginated.","empty"));return}
    const chosen=sources.filter(s=>params.source==="all"||params.source===s.key);
    const status=el("div","Searching qualified public provider projections…","notice");status.classList.add("advanced-status");app.append(status);
    const page= params.page,offset=(page-1)*pageSize,items=[],counts=[];
    let total=0,completed=0,failed=0;
    const cmp=(a,b)=>String(a.name||"").localeCompare(String(b.name||""),"en",{sensitivity:"base"})||String(a.state).localeCompare(String(b.state))||String(a.ccn).localeCompare(String(b.ccn));
    for(const s of chosen){
        try{
            const inst=params.institutional?await institutionalEvidence(s,signal):null;
            const data=inst?inst.directory:await loadShard(s,signal);if(epoch!==sequence)return;
            const matches=data.records.filter(row=>matchesPublic(row,params)&&advancedCapacityMatch(row,params)&&(!params.institutional||inst.records.get(institutionalKey(row))?.[params.institutional.field]===params.institutional.value)).sort(cmp);
            const start=Math.max(0,offset-total),end=Math.min(matches.length,offset+pageSize-total);
            if(end>start)for(const row of matches.slice(start,end))items.push({s,r:row,institutional:params.institutional});
            total+=matches.length;completed++;counts.push([s.key,matches.length,s.release]);
        }catch(e){if(epoch!==sequence||e.name==="AbortError")return;failed++;counts.push([s.key,null,s.release]);app.append(errorBox(s,e))}
    }
    if(epoch!==sequence)return;
    status.textContent=N.format(total)+" matching provider source records across "+completed+" of "+chosen.length+" selected sources."+(failed?" Partial results: one or more sources unavailable; totals and pagination are incomplete.":" Sorted by provider category, then name.");
    status.dataset.total=String(total);status.dataset.complete=String(failed===0);
    const breakdown=el("div",undefined,"advanced-breakdown");
    for(const [key,n,release] of counts){const card=el("div",undefined,"advanced-source-count");card.append(el("strong",n===null?"Unavailable":N.format(n)),el("span",names[key]),el("small","Release "+release));breakdown.append(card)}
    if(params.institutional)app.append(el("p",institutionalLabels[params.institutional.field]+" · "+institutionalValues[params.institutional.value]+" · CMS snapshot","intro"));
    app.append(breakdown,el("h2","Matching source records"));
    if(items.length){
        const wrapper=table(["Provider / CCN","Provider category","Reported address","Capacity evidence",...(params.institutional?["Institutional evidence"]:[]),"Source release"],items.map(({s,r,institutional})=>[recordCell(s,r,publicFields),names[s.key],shown([r.address,r.city,r.state,r.zip].filter(Boolean).join(", ")),advancedCapacityText(s,r),...(institutional?[institutionalValues[institutional.value]]:[]),add(el("div"),el("span",s.release),el("small",sourceLink(s,"Official source").textContent))]));
        // Keep actual source links, not plain text.
        for(let i=0;i<items.length;i++){const td=wrapper.querySelectorAll("tbody tr")[i].lastElementChild;td.replaceChildren(el("span",items[i].s.release),el("small"));td.lastChild.append(sourceLink(items[i].s))}
        wrapper.classList.add("advanced-results");wrapper.setAttribute("aria-label","Matching provider records; scroll horizontally if needed");
        app.append(wrapper);
        if(!failed){const exportButton=el("button","Export current page (CSV)");exportButton.type="button";exportButton.addEventListener("click",()=>exportAdvancedPage(items));app.append(add(el("div",undefined,"links"),exportButton))}
    }else app.append(el("div",total?"This page is outside the available matches. Return to the first page.":failed?"No matches were returned from available sources; unavailable sources were not searched.":"No published source records match these filters.","empty"));
    const pager=el("div",undefined,"pager");
    pager.append(el("span","Page "+page+" · "+N.format(total)+" matches"+(failed?" (partial)":"")));
    const safe={source:params.source,state:params.state,field:params.field,q:params.q,reported:params.reported,min:p.min,max:p.max,institutional_field:params.institutional?.field,institutional_value:params.institutional?.value,run:1};
    if(page>1)pager.append(anchor("First page",route("advanced",{...safe,page:1})),anchor("Previous",route("advanced",{...safe,page:page-1})));
    if(page*pageSize<total&&!failed)pager.append(anchor("Next",route("advanced",{...safe,page:page+1})));
    app.append(pager,el("p","Institutional filters apply only to the selected provider category and exact pinned CMS snapshot. Reported yes/no does not establish current service availability, installed equipment, legal title or procurement intent. Other iQIES and home health service evidence remains in its separate research workspaces.","intro"))
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
        ["Water treatment & dialysis","Research reported dialysis station capacity and relevant national water-system source coverage. A dialysis provider record does not establish a water-treatment installation.",[["Dialysis providers",search("dialysis")],["Dialysis station capacity",cap("dialysis")],["Dialysis service research",route("dialysis-services",{state})],["National water / environmental evidence",route("equipment-environment")]]],
        ["Sterilization & infection prevention","Research hospital and nursing-home markets alongside national surgical-capability and infection-prevention context. Facility-level sterilization service or critical-water evidence is not published.",[["Hospital providers",search("hospital")],["Nursing home capacity",cap("nursing")],["National service evidence",route("services")],["National compliance research",route("compliance-research")]]],
        ["Medical imaging & equipment","Research provider markets and the national FDA mammography and QIES service-code evidence. There is no qualified individual installed-unit filter.",[["Hospital providers",search("hospital")],["Mammography source coverage",route("equipment-environment")],["National imaging service evidence",route("services")]]],
        ["Fire protection & emergency preparedness","Research nursing provider markets and historical citation aggregates. National life-safety context is not a current finding or a facility vulnerability assessment.",[["Nursing providers",search("nursing")],["Historical nursing fire citations",route("citations",{source:"nursing-fire",state})],["National compliance research",route("compliance-research")]]],
        ["Laboratory & clinical services","Research the provider directory and national certification/laboratory coverage. Individual CLIA relationships remain unpublished; selected dialysis and home health service evidence have separate qualified research views.",[["Public provider search",search("all")],["Registry and laboratory coverage",route("certifications")],["National service evidence",route("services")],["Home health service research",route("hha-services",{state})]]],
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
    return "web/market-summary.json?v="+(publicManifest.field_enrichments?.["long-term-hospital"]?.projection_sha256||publicManifest.source_database_sha256).slice(0,16)
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

const capacityUnits=Object.freeze({nursing:{label:"Certified beds",plural:"certified beds"},dialysis:{label:"Dialysis stations",plural:"dialysis stations"},"long-term-hospital":{label:"Total beds",plural:"total reported beds"}});
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
    return source==="nursing"||source==="long-term-hospital"?[[0,0],[1,49],[50,99],[100,199],[200,null]]:[[0,0],[1,9],[10,19],[20,39],[40,null]]
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
    title("Capacity explorer","Research source-reported nursing-home certified beds, dialysis stations and long-term care hospital total beds. These measures are kept separate and are never added together. This is a public market-size indicator, not proof of current operating capacity, installed equipment, service demand or a procurement opportunity.");
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
            capacityMetric(s.key==="long-term-hospital"?"Total reported beds":unit.label+" reported total",totals.reported?totals.sum:null,"Sum of numeric values only; not unique sites"),
            capacityMetric("Numeric capacity reported",totals.reported,N.format(totals.zero)+" records explicitly report zero"),
            capacityMetric("Missing or nonnumeric",totals.unknown,"Excluded from totals; not treated as zero"));
        app.append(metrics,capacityDistribution(s,p,region),el("h2","Matching providers"));
        if(!filtered.length)app.append(el("div","No source records match these filters. Adjust the selection to continue.","empty"));
        else{
            const result=filtered.slice((page-1)*pageSize,page*pageSize);
            const cells=result.map(r=>[recordCell(s,r,publicFields),shown([r.address,r.city,r.state,r.zip].filter(Boolean).join(", ")),publicCapacity(r)===null?"Not reported / nonnumeric":N.format(publicCapacity(r)),sourceLink(s)]);
            const resultsTable=table(["Provider / CCN","Reported address",unit.label,"Evidence"],cells);
            if(s.key==="long-term-hospital"){resultsTable.classList.add("ltch-capacity-table");app.append(el("p","Scroll horizontally to see all columns if needed.","intelligence-scroll-hint"))}
            app.append(resultsTable)
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
            const regionalTable=table(["Jurisdiction","Matching records","Numeric capacity reported","Missing / nonnumeric",unit.label+" reported total"],regional.map(g=>[anchor(g.state,route("capacity",{...p,state:g.state,page:1})),N.format(g.records),N.format(g.reported),N.format(g.unknown),g.reported?N.format(g.sum):"—"]));if(s.key==="long-term-hospital")regionalTable.classList.add("ltch-capacity-region");app.append(regionalTable)
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
function certificationCoverage(){title("Certifications & laboratories","Qualified QIES, iQIES and CLIA release coverage. Direct browser API access failed; raw registry records are not published. A narrow corroborated dialysis service projection is available separately.");app.append(historicalNote(),table(["Registry","Release period","Historical source rows","Official API"],sourceRows(byFamily("registry"))),el("div","Certification status, current operations and equipment are not inferred. Full registry research remains in the local qualified application.","notice"))}

const profileSections=[["summary","Summary"],["services","Services & capacity"],["compliance","Compliance evidence"],["location","Location & peers"],["sources","Sources & coverage"]];
function localResearchReturn(hash){
    if(typeof hash!=="string"||hash.length>1600||!/^#(?:facilities|citations|capacity|search|advanced|dialysis-services|hha-services|nursing-portfolios)(?:\?|$)/.test(hash))return "";
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
    for(const [label,k] of [["CCN","id"],["Address","address"],["City","city"],["State","state"],["ZIP","zip"],[capacityUnits[s.key]?.label||"Reported capacity","capacity"]])grid.append(add(el("div"),el("dt",label),el("dd",shown(v(k)))));
    return grid
}
const historicalCapacityPins=Object.freeze({"hospital":{"form":"hospital","payload":"48691c4574b372eed3dd50b17b75b04cbeb48b4c1e03f4789d57c4ce8554e3d5","rows":3561,"providers":3508,"directory":"222096b1bf7cfbfcb37c4c6375d6ba686c6e3ccdd7af47c542bfb91ad34d621a","release":"2026-11-12","directoryRows":5435,"fields":["available_beds_at_period_end"],"source":"bde32414133a7b4ae0bb092654f805ad9d20335764cb4f91feeb4ca129c4e782","run":45872218782,"official":"https://data.cms.gov/provider-compliance/cost-reports/hospital-provider-cost-report"},"nursing":{"form":"snf","payload":"fb710c1ad8d8bdc94f0d42717c91b2a5ad7285bcb1cb6e2de9055faf5de3035f","rows":13408,"providers":12894,"directory":"36363899e56c97433686ce8617a7d4b557b272a155e8a8eba1822c6f7a36e3ce","release":"2026-10-28","directoryRows":14686,"fields":["available_beds_at_period_end","available_bed_days"],"source":"adcef64de8d15b772aa37ca03bba162e78f781d22198b8fbb478810685e6c05c","run":45872218782,"official":"https://data.cms.gov/provider-compliance/cost-reports/skilled-nursing-facility-cost-report"}});
function historicalCapacityLink(s,r,p){
    return anchor("Historical FY2024 cost-report capacity",route("detail",{source:s.key,id:r.ccn,state:r.state,return:localResearchReturn(p?.return),section:"services"}))
}
async function historicalCapacityProfile(r,s,signal,epoch){
    const pin=historicalCapacityPins[s.key],section=el("section",undefined,"historical-capacity-profile");
    section.dataset.evidence="loading";section.dataset.form=pin.form;
    section.append(el("h2","Historical cost-report capacity"),el("p","FY2024 selected CMS cost reports, published October 5, 2026. Historical available beds at period end are separate from the directory's reported capacity. Reports are not summed or interpreted as current occupancy.","intro"));
    const evidence=el("div",undefined,"links");
    evidence.append(anchor("Official CMS cost-report data",pin.official,true),anchor("Source qualification run "+pin.run,"https://github.com/JeremyHennessy/FacilitySignal/actions/runs/"+pin.run,true),anchor("Financial report research",route("financial-research")));
    try{
        if(s.release!==pin.release)throw Error("Provider source release changed; requalification required");
        const [pack,directory]=await Promise.all([exactJson("web/hcris-capacity/"+pin.form+".json?v="+pin.payload.slice(0,16),pin.payload,signal),exactJson("web/public-directory/"+s.key+".json",pin.directory,signal)]);
        if(epoch!==sequence||signal.aborted)return null;
        if(!dialysisKeys(pack,["version","scope","form","records"])||pack.version!==1||pack.scope!=="FY2024 selected CMS PUF historical report capacity; exact matched candidate cohort, not current certified capacity"||pack.form!==pin.form||!Array.isArray(pack.records)||pack.records.length!==pin.rows)throw Error("Historical capacity envelope mismatch");
        if(directory.source!==s.key||directory.release!==pin.release||!Array.isArray(directory.records)||directory.records.length!==pin.directoryRows)throw Error("Directory envelope mismatch");
        const matches=directory.records.filter(x=>x.ccn===r.ccn);
        if(matches.length!==1||matches[0].state!==r.state||["name","address","city","zip","capacity"].some(k=>matches[0][k]!==r[k]))throw Error("Unique exact directory record not corroborated");
        const seen=new Set(),providers=new Set();
        for(const x of pack.records){
            if(!dialysisKeys(x,["report_key","ccn","state","period_begin","period_end","measures"])||typeof x.report_key!=="string"||!/^[0-9]{1,20}$/.test(x.report_key)||seen.has(x.report_key)||typeof x.ccn!=="string"||!/^[A-Z0-9]{6}$/.test(x.ccn)||!states.includes(x.state)||!/^\d{4}-\d{2}-\d{2}$/.test(x.period_begin)||!/^\d{4}-\d{2}-\d{2}$/.test(x.period_end)||x.period_begin<"2023-10-01"||x.period_begin>"2024-09-30"||x.period_end<x.period_begin||!dialysisKeys(x.measures,pin.fields)||Object.values(x.measures).some(v=>v!==null&&(!Number.isSafeInteger(v)||v<0)))throw Error("Historical report schema mismatch");
            seen.add(x.report_key);providers.add(x.state+":"+x.ccn)
        }
        if(providers.size!==pin.providers)throw Error("Historical provider count mismatch");
        const records=pack.records.filter(x=>x.ccn===r.ccn&&x.state===r.state).sort((a,b)=>b.period_begin.localeCompare(a.period_begin)||b.period_end.localeCompare(a.period_end)||a.report_key.localeCompare(b.report_key));
        if(records.some((x,i)=>records.slice(0,i).some(y=>x.period_begin<=y.period_end&&y.period_begin<=x.period_end)))throw Error("Conflicting reporting periods");
        section.dataset.evidence=records.length?"qualified":"unlinked";
        section.dataset.reports=String(records.length);
        if(!records.length)section.append(el("div","No qualified FY2024 report matches this exact provider record. This does not establish zero historical capacity or absence of a cost report.","notice"));
        else{
            section.append(el("p",N.format(records.length)+" qualified historical report(s) · exact CCN and state · separate fiscal periods","intro"));
            for(const x of records){
                const item=el("article",undefined,"historical-capacity-report");item.dataset.reportKey=x.report_key;
                item.append(el("h3","Fiscal period "+x.period_begin+" – "+x.period_end));
                const grid=el("dl",undefined,"detail-grid");
                for(const [field,label] of [["available_beds_at_period_end","Available beds at period end"],["available_bed_days","Available bed-days"]]){
                    if(!pin.fields.includes(field))continue;
                    const v=x.measures[field],cell=add(el("div"),el("dt",label),el("dd",v===null?"Not reported":N.format(v)));
                    cell.dataset.field=field;cell.dataset.state=v===null?"missing":v===0?"reported_zero":"reported_positive";grid.append(cell)
                }
                grid.append(add(el("div"),el("dt","CMS report record number"),el("dd",x.report_key)));
                item.append(grid);section.append(item)
            }
        }
        section.append(el("p","Matched report subset only. Monetary values, asset purchases and current certified beds are not inferred from these reports.","intro"),evidence);
    }catch(e){
        if(epoch!==sequence||signal.aborted||e.name==="AbortError")return null;
        section.dataset.evidence="unavailable";section.append(el("div","Qualified historical capacity evidence unavailable. No values inferred; source version or validation may require requalification.","error"),evidence);
    }
    return section
}
async function profileService(r,s,f,signal,epoch){
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
    if(historicalCapacityPins[s.key]){const historical=await historicalCapacityProfile(r,s,signal,epoch);if(!historical||epoch!==sequence)return null;section.append(historical)}
    if(s.key==="dialysis"){const evidence=await dialysisProfile(r,signal,epoch);if(!evidence||epoch!==sequence)return null;section.append(evidence)}
    else if(s.key==="home-health"){const evidence=await hhaProfile(r,signal,epoch);if(!evidence||epoch!==sequence)return null;section.append(evidence)}
    else section.append(el("h2","Other service capabilities"),el("div","Individual QIES and iQIES service observations are not published for this source record. National aggregate evidence is available separately; it is not evidence of a particular service at this facility.","notice"),add(el("p"),anchor("National service evidence",route("services"))));
    if(["hospital","dialysis"].includes(s.key)){const inst=await institutionalProfile(r,s,signal,epoch);if(!inst||epoch!==sequence)return null;section.append(inst)}
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
function profileResearchActions(s,r,f){
    const state=value(r,f,"state"),city=value(r,f,"city"),addr=value(r,f,"address"),zip=value(r,f,"zip");
    const box=el("section",undefined,"profile-research-actions");
    box.append(el("h2","Continue this research"),el("p","Explore related public source records by reported geography. These searches do not establish co-location, ownership, service provision or a shared physical property.","intro"));
    const links=el("div",undefined,"links");
    links.append(anchor("Same category in "+(state||"all jurisdictions"),route("advanced",{source:s.key,state,run:1})));
    if(city)links.append(anchor("All provider records in reported city",route("advanced",{source:"all",state,field:"city",q:city,run:1})));
    if(zip)links.append(anchor("Search reported ZIP",route("advanced",{source:"all",state,field:"zip",q:zip,run:1})));
    if(addr&&addr.length<=100)links.append(anchor("Search reported address text",route("advanced",{source:"all",state,field:"address",q:addr,run:1})));
    links.append(anchor("Regional industry research",route("industry",{state})),anchor("Regional market map",route("geography",{state,source:s.key})));
    box.append(links);
    return box
}

const dialysisRelease=Object.freeze({period:"2026-07-01/2026-09-30",payload:"9617a05946fc165416c1c69c937eaeb4d82f29871bd7f04a88413664c80cb738",provider:"e8343f678ec1780ac49047f162754657f60eaa3f61b1d4f48ea4b55d39d4008a",source:"50b3fd74d88e08d2eaaf60e11a9230175acae0045b9fe9f803b91be8b8359dd2",dictionary:"bd68d76dc72ee5c3b3249c459644ff2ed90c8e8cf6e182b76742ec53164c0594",qualified:2194,publicRows:7471,run:45827234729});
const dialysisFields=Object.freeze({dlys_stn_cnt:"Approved in-center dialysis stations",hmdlys_srvc_sw:"In-center hemodialysis",prtnl_dlys_srvc_sw:"In-center peritoneal dialysis",home_trng_sprt_only_srvc_sw:"Onsite home training"});
const dialysisStateLabels={reported_yes:"Reported yes",reported_no:"Reported no",reported_count:"Numeric count reported",not_available:"Not available",not_applicable_conflict:"Applicability conflict",blank:"Blank",unrecognized:"Unrecognized"};
function dialysisKeys(a,b){return a&&typeof a==="object"&&!Array.isArray(a)&&Object.keys(a).sort().join("|")===b.slice().sort().join("|")}
async function exactJson(path,digest,signal){
    const response=await fetch(path,{signal});
    if(!response.ok)throw Error("Evidence HTTP "+response.status);
    const bytes=await response.arrayBuffer();
    if(!globalThis.crypto?.subtle)throw Error("Secure evidence verification unavailable");
    const actual=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes)),b=>b.toString(16).padStart(2,"0")).join("");
    if(actual!==digest)throw Error("Evidence checksum mismatch");
    return JSON.parse(new TextDecoder().decode(bytes))
}
async function dialysisEvidence(signal){
    const d=dialysisRelease;
    const [directory,payload]=await Promise.all([exactJson("web/public-directory/dialysis.json",d.provider,signal),exactJson("web/dialysis-service-evidence.json?v="+d.payload.slice(0,16),d.payload,signal)]);
    if(directory.source!=="dialysis"||!Array.isArray(directory.records)||directory.row_count!==d.publicRows||directory.records.length!==d.publicRows||publicManifest.sources.dialysis?.published_records!==d.publicRows)throw Error("Dialysis directory baseline mismatch");
    const byId=new Map(directory.records.map(r=>[r.ccn,r]));
    if(byId.size!==d.publicRows||!dialysisKeys(payload,["dictionary_sha256","fields","format_version","period","public_dialysis_sha256","records","registry","scope","source_sha256"])||payload.format_version!==1||payload.registry!=="iqies"||payload.period!==d.period||payload.source_sha256!==d.source||payload.dictionary_sha256!==d.dictionary||payload.public_dialysis_sha256!==d.provider||!dialysisKeys(payload.fields,Object.keys(dialysisFields))||!payload.records||Object.keys(payload.records).length!==d.qualified)throw Error("Qualified dialysis metadata mismatch");
    for(const [id,obs] of Object.entries(payload.records)){
        if(!byId.has(id)||!dialysisKeys(obs,Object.keys(dialysisFields)))throw Error("Evidence record outside qualified scope");
        for(const [field,v] of Object.entries(obs)){
            const count=field==="dlys_stn_cnt";
            if(!dialysisKeys(v,count?["state","count"]:["state"])||!Object.hasOwn(dialysisStateLabels,v.state))throw Error("Invalid observation");
            if(count){
                if(!["reported_count","not_available","not_applicable_conflict","blank","unrecognized"].includes(v.state)|| (v.state==="reported_count"?(!Number.isSafeInteger(v.count)||v.count<0):v.count!==null))throw Error("Invalid count observation")
            }else if(v.state==="reported_count")throw Error("Invalid indicator observation");
        }
    }
    return {directory,byId,records:payload.records}
}
function dialysisObservation(value){
    if(!value)return "No corroborated evidence";
    return value.state==="reported_count"?N.format(value.count):dialysisStateLabels[value.state]
}
function dialysisResearchLink(state=""){return anchor("Search dialysis service evidence",route("dialysis-services",{state}))}
function dialysisFilterForm(p){
    const f=el("form",undefined,"toolbar dialysis-service-form");
    const field=options("Reported service","field",Object.entries(dialysisFields),p.field||"hmdlys_srvc_sw");
    const jurisdiction=options("State / territory","state",[["","All jurisdictions"],...states.slice().sort().map(s=>[s,s])],p.state);
    const ev=options("Evidence filter","evidence",[["corroborated","Any corroborated record"],["all","All provider records"],["reported_yes","Reported yes"],["reported_no","Reported no"],["reported_count","Numeric count reported"],["not_available","Reported not available"],["unlinked","No corroborated evidence"]],p.evidence||"corroborated");
    const q=input("Provider name contains","q",p.q),min=input("Minimum approved stations","min",p.min),max=input("Maximum approved stations","max",p.max);
    for(const w of [min,max]){const n=w.querySelector("input");n.type="number";n.min="0";n.max="1000000";n.step="1"}
    const hint=el("p",undefined,"dialysis-filter-hint");
    const submit=el("button","Apply service filters");submit.type="submit";
    f.append(jurisdiction,field,ev,q,min,max,hint,submit,anchor("Reset",route("dialysis-services")));
    const fld=field.querySelector("select"),sel=ev.querySelector("select"),lo=min.querySelector("input"),hi=max.querySelector("input");
    function sync(){
        const numeric=fld.value==="dlys_stn_cnt";
        for(const o of sel.options)o.disabled=numeric?["reported_yes","reported_no"].includes(o.value):o.value==="reported_count";
        if(sel.selectedOptions[0]?.disabled)sel.value="corroborated";
        const enabled=numeric&&["corroborated","all","reported_count"].includes(sel.value);
        lo.disabled=hi.disabled=!enabled;if(!enabled)lo.value=hi.value="";
        hint.textContent=numeric?"Station bounds apply only to the iQIES approved in-center station field, not the separate Care Compare station count.":"Yes/no are historical source-reported indicators; unavailable and unlinked evidence are not reported no."
    }
    fld.addEventListener("change",sync);sel.addEventListener("change",sync);sync();
    f.addEventListener("submit",e=>{e.preventDefault();location.hash=route("dialysis-services",Object.fromEntries(new FormData(f)))});
    return f
}
function dialysisParams(p){
    const field=p.field||"hmdlys_srvc_sw",evidence=p.evidence||"corroborated",state=p.state||"",q=(p.q||"").trim();
    if(!Object.hasOwn(dialysisFields,field)||!["corroborated","all","reported_yes","reported_no","reported_count","not_available","unlinked"].includes(evidence)||state&&!states.includes(state)||q.length>100)throw Error("Invalid service filter");
    const numeric=field==="dlys_stn_cnt";
    if(numeric&&["reported_yes","reported_no"].includes(evidence)||!numeric&&evidence==="reported_count")throw Error("Filter does not apply to the selected source field");
    const bounds={};
    for(const key of ["min","max"]){const v=p[key]??"";if(v===""){bounds[key]=null;continue}if(!/^\d{1,7}$/.test(v)||Number(v)>1000000)throw Error("Invalid station bound");bounds[key]=Number(v)}
    if((bounds.min!==null||bounds.max!==null)&&(!numeric||!["corroborated","all","reported_count"].includes(evidence)))throw Error("Station bounds require numeric station evidence");
    if(bounds.min!==null&&bounds.max!==null&&bounds.min>bounds.max)throw Error("Minimum cannot exceed maximum");
    if(p.page&&!/^\d{1,6}$/.test(p.page))throw Error("Invalid page");
    return {field,evidence,state,q,min:p.min||"",max:p.max||"",bounds,page:Math.max(1,Math.min(100000,Number(p.page)||1))}
}
async function dialysisServices(p,signal,epoch){
    title("Dialysis service research","Explore corroborated Q3 2026 iQIES observations on existing public Care Compare dialysis records. Registry evidence is not proof of current operation, equipment installation or purchase intent.");
    let v;try{v=dialysisParams(p)}catch(e){app.append(el("div",e.message,"error"),anchor("Reset filters",route("dialysis-services")));return}
    app.append(dialysisFilterForm(v),add(el("div",undefined,"links"),anchor("Care Compare dialysis capacity",route("capacity",{source:"dialysis",state:v.state})),anchor("National service evidence",route("services")),anchor("Qualification run "+dialysisRelease.run,"https://github.com/JeremyHennessy/FacilitySignal/actions/runs/"+dialysisRelease.run,true)));
    const status=el("div","Verifying source checksums…","notice");app.append(status);
    try{
        const data=await dialysisEvidence(signal);if(epoch!==sequence)return;
        const regional=data.directory.records.filter(r=>!v.state||r.state===v.state),linked=regional.filter(r=>Object.hasOwn(data.records,r.ccn)).length;
        const matched=regional.filter(r=>{
            if(v.q&&!r.name.toLowerCase().includes(v.q.toLowerCase()))return false;
            const obs=data.records[r.ccn]?.[v.field];
            if(v.evidence==="corroborated"&&!obs||v.evidence==="unlinked"&&obs)return false;
            if(!["all","corroborated","unlinked"].includes(v.evidence)&&obs?.state!==v.evidence)return false;
            if(v.bounds.min!==null&&(obs?.state!=="reported_count"||obs.count<v.bounds.min)||v.bounds.max!==null&&(obs?.state!=="reported_count"||obs.count>v.bounds.max))return false;
            return true
        }).sort((a,b)=>a.name.localeCompare(b.name,"en",{sensitivity:"base"})||a.ccn.localeCompare(b.ccn));
        status.textContent="Verified historical source evidence · "+dialysisRelease.period+" · "+N.format(matched.length)+" matching provider records.";
        status.classList.add("dialysis-status");status.dataset.ready="true";status.dataset.total=String(matched.length);
        const metrics=el("div",undefined,"metrics");
        metrics.append(capacityMetric("Provider records in geography",regional.length,"Care Compare source records"),capacityMetric("Corroborated registry evidence",linked,"Exact single ESRD identifier and address text"),capacityMetric("No corroborated evidence",regional.length-linked,"Not reported no or zero"),capacityMetric("Matching records",matched.length,"Current search filters"));
        app.append(metrics,el("h2","Matching dialysis records"));
        const slice=matched.slice((v.page-1)*pageSize,v.page*pageSize);
        if(slice.length){
            const s=providerSources().find(x=>x.key==="dialysis");
            const rows=slice.map(r=>{
                const obs=data.records[r.ccn],cell=el("div");
                cell.append(anchor(r.name,route("detail",{source:"dialysis",id:r.ccn,state:r.state,section:"services",return:localResearchReturn(location.hash)})),el("small",r.ccn));
                return [cell,[r.city,r.state].filter(Boolean).join(", "),dialysisObservation(obs?.dlys_stn_cnt),dialysisObservation(obs?.hmdlys_srvc_sw),dialysisObservation(obs?.prtnl_dlys_srvc_sw),dialysisObservation(obs?.home_trng_sprt_only_srvc_sw)]
            });
            const wrap=table(["Provider / CCN","Reported city / state","Approved stations (iQIES)","Hemodialysis","Peritoneal dialysis","Home training"],rows);
            wrap.classList.add("dialysis-results");wrap.setAttribute("aria-label","Dialysis service observations; scroll horizontally if needed");app.append(wrap)
        }else app.append(el("div",matched.length?"Page outside matching results. Return to the first page.":"No provider records match the filters.","empty"));
        const pager=el("div",undefined,"pager"),safe={field:v.field,evidence:v.evidence,state:v.state,q:v.q,min:v.min,max:v.max};
        pager.append(el("span","Page "+v.page+" · "+N.format(matched.length)+" matches"));
        if(v.page>1)pager.append(anchor("First page",route("dialysis-services",{...safe,page:1})),anchor("Previous",route("dialysis-services",{...safe,page:v.page-1})));
        if(v.page*pageSize<matched.length)pager.append(anchor("Next",route("dialysis-services",{...safe,page:v.page+1})));
        app.append(pager,el("p","National coverage: 2,194 of 7,471 public dialysis provider records meet the strict source-link evidence gate; 5,262 have differing address text and 15 have no exact ESRD identifier candidate. Unlinked records remain available in the directory, but their individual service values are not published. Approved iQIES station counts and Care Compare station counts are distinct and must not be summed.","intro"));
        app.append(anchor("Official iQIES POS source","https://data.cms.gov/provider-characteristics/hospitals-and-other-facilities/provider-of-services-file-internet-quality-improvement-and-evaluation-system",true))
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return;status.replaceWith(el("div","Dialysis service evidence unavailable: "+e.message+". No values inferred.","error"))}
}
async function dialysisProfile(r,signal,epoch){
    const section=el("section",undefined,"dialysis-profile");
    section.append(el("h2","iQIES dialysis service observations"));
    try{
        const data=await dialysisEvidence(signal);if(epoch!==sequence)return null;
        const reference=data.byId.get(r.ccn);
        if(!reference||["ccn","name","state","address","city","zip"].some(k=>reference[k]!==r[k]))throw Error("Profile directory record differs from qualified source");
        const obs=data.records[r.ccn];
        if(!obs){section.append(el("div","No sufficiently corroborated iQIES service evidence is published for this provider. This does not mean services are absent.","notice"));section.dataset.evidence="unlinked"}
        else{
            const grid=el("dl",undefined,"detail-grid dialysis-profile-grid");
            for(const [key,label] of Object.entries(dialysisFields)){const cell=add(el("div"),el("dt",label),el("dd",dialysisObservation(obs[key])));cell.dataset.field=key;grid.append(cell)}
            section.append(el("p","Historical registry period "+dialysisRelease.period+". One ESRD source candidate with exact CCN, reported state and normalized literal address, city and ZIP5 agreement. Not a confirmed physical-site match or current clinical service availability.","intro"),grid);
            section.dataset.evidence="corroborated"
        }
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return null;section.dataset.evidence="unavailable";section.append(el("div","Registry evidence unavailable: "+e.message+". No values inferred.","error"))}
    section.append(add(el("div",undefined,"links"),dialysisResearchLink(r.state),anchor("Qualification evidence","https://github.com/JeremyHennessy/FacilitySignal/actions/runs/"+dialysisRelease.run,true)),el("p","Approved in-center stations from iQIES are a separate source measure from the Care Compare station count shown above.","intro"));
    return section
}


const hhaRelease=Object.freeze({release:"2026-10-21",payload:"88dd0b1a9db445c8c5b33ad09225ed86a9a9c516ad6be3c259f035a3e06263e1",provider:"3b244338ff11e39258aa0620a4b3a6f1813c6b8569f0290380f06493e0344d3d",source:"7adf3e17961949bbd64ef243545aa387224d9837e8c5601476f5b11946e76d22",rows:12409,run:45828532285});
const hhaFields=Object.freeze(["Nursing Care","Physical Therapy","Occupational Therapy","Speech Pathology","Medical Social","Home Health Aide"]);
const hhaStates=Object.freeze({yes:"Reported yes",no:"Reported no",dash_marker:"Unknown (source dash)"});
const hhaKey=r=>r.state+":"+r.ccn;
async function hhaEvidence(signal){
    const d=hhaRelease;
    const [directory,payload]=await Promise.all([exactJson("web/public-directory/home-health.json",d.provider,signal),exactJson("web/hha-service-evidence.json?v="+d.payload.slice(0,16),d.payload,signal)]);
    if(directory.source!=="home-health"||directory.release!==d.release||!Array.isArray(directory.records)||directory.row_count!==d.rows||directory.records.length!==d.rows||publicManifest.sources["home-health"]?.published_records!==d.rows)throw Error("Home health directory baseline mismatch");
    const byId=new Map(directory.records.map(r=>[hhaKey(r),r]));
    if(byId.size!==d.rows||!dialysisKeys(payload,["format_version","scope","source","release","source_sha256","public_directory_sha256","fields","records"])||payload.format_version!==1||payload.source!=="care-compare-home-health"||payload.release!==d.release||payload.source_sha256!==d.source||payload.public_directory_sha256!==d.provider||!Array.isArray(payload.fields)||payload.fields.join("|")!==hhaFields.join("|")||!payload.records||Object.keys(payload.records).length!==d.rows)throw Error("Qualified home health metadata mismatch");
    for(const [id,obs] of Object.entries(payload.records))if(!byId.has(id)||!dialysisKeys(obs,hhaFields)||Object.values(obs).some(v=>!Object.hasOwn(hhaStates,v)))throw Error("Invalid home health observation");
    return {directory,byId,records:payload.records}
}
function hhaResearchLink(state=""){return anchor("Search home health service evidence",route("hha-services",{state}))}
function hhaParams(p){
    const field=p.field||"Nursing Care",evidence=p.evidence||"all",state=p.state||"",q=(p.q||"").trim(),required=p.required?p.required.split("|"):[];
    if(!hhaFields.includes(field)||!["all",...Object.keys(hhaStates)].includes(evidence)||state&&!states.includes(state)||q.length>100||required.length>hhaFields.length||new Set(required).size!==required.length||required.some(v=>!hhaFields.includes(v)))throw Error("Invalid home health service filter");
    if(p.page&&!/^\d{1,6}$/.test(p.page))throw Error("Invalid page");
    return {field,evidence,state,q,required,page:Math.max(1,Math.min(100000,Number(p.page)||1))}
}
function hhaForm(v){
    const f=el("form",undefined,"toolbar hha-service-form");
    const field=options("Service to examine","field",hhaFields.map(x=>[x,x]),v.field),state=options("State / territory","state",[["","All jurisdictions"],...states.slice().sort().map(s=>[s,s])],v.state);
    const ev=options("Source evidence","evidence",[["all","All evidence states"],...Object.entries(hhaStates)],v.evidence),q=input("Provider name contains","q",v.q);
    const checks=el("fieldset",undefined,"hha-required");
    checks.append(el("legend","Require additional services reported yes"));
    for(const service of hhaFields){const l=el("label"),c=el("input");c.type="checkbox";c.name="required";c.value=service;c.checked=v.required.includes(service);l.append(c,document.createTextNode(service));checks.append(l)}
    const hint=el("p","Multiple required services use AND logic; unknown and reported no never satisfy a required-yes filter.","hha-filter-hint");
    const button=el("button","Apply service filters");button.type="submit";
    f.append(state,field,ev,q,checks,hint,button,anchor("Reset",route("hha-services")));
    f.addEventListener("submit",e=>{e.preventDefault();const fd=new FormData(f),params=Object.fromEntries(fd);params.required=fd.getAll("required").join("|");location.hash=route("hha-services",params)});
    return f
}
function hhaExport(rows,records){
    const header=["source","release","ccn","reported_name","reported_address","city","state","zip",...hhaFields.map(f=>"Offers "+f+" Services")];
    const values=rows.map(r=>["CMS Care Compare home-health",hhaRelease.release,r.ccn,r.name,r.address,r.city,r.state,r.zip,...hhaFields.map(f=>records[hhaKey(r)][f])]);
    const text=[header,...values].map(row=>row.map(safeCsvCell).join(",")).join("\r\n")+"\r\n";
    const url=URL.createObjectURL(new Blob([text],{type:"text/csv;charset=utf-8"})),a=el("a");a.href=url;a.download="facilitysignal-home-health-search-page.csv";document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
async function hhaServices(p,signal,epoch){
    title("Home health service research","Explore six source-reported service offerings on the October 2026 CMS Care Compare home health release. Evidence is historical, not current availability, staff capacity or purchasing intent.");
    let v;try{v=hhaParams(p)}catch(e){app.append(el("div",e.message,"error"),anchor("Reset filters",route("hha-services")));return}
    app.append(hhaForm(v),add(el("div",undefined,"links"),anchor("Home health provider directory",route("facilities",{source:"home-health",state:v.state})),anchor("National service evidence",route("services")),anchor("Qualification run "+hhaRelease.run,"https://github.com/JeremyHennessy/FacilitySignal/actions/runs/"+hhaRelease.run,true)));
    const status=el("div","Verifying exact source checksums…","notice");app.append(status);
    try{
        const d=await hhaEvidence(signal);if(epoch!==sequence)return;
        const regional=d.directory.records.filter(r=>!v.state||r.state===v.state),tally={yes:0,no:0,dash_marker:0};
        for(const r of regional)tally[d.records[hhaKey(r)][v.field]]++;
        const matched=regional.filter(r=>{
            const obs=d.records[hhaKey(r)];
            return (!v.q||r.name.toLowerCase().includes(v.q.toLowerCase()))&&(v.evidence==="all"||obs[v.field]===v.evidence)&&v.required.every(f=>obs[f]==="yes")
        }).sort((a,b)=>a.name.localeCompare(b.name,"en",{sensitivity:"base"})||a.state.localeCompare(b.state)||a.ccn.localeCompare(b.ccn));
        status.textContent=N.format(matched.length)+" matching provider source records · CMS release "+hhaRelease.release+".";
        status.classList.add("hha-status");status.dataset.ready="true";status.dataset.total=String(matched.length);
        const metrics=el("div",undefined,"metrics hha-metrics");
        metrics.append(capacityMetric("Provider records in geography",regional.length,"All source records before other filters"),capacityMetric(v.field+" · yes",tally.yes,"Reported yes before other filters"),capacityMetric(v.field+" · no",tally.no,"Reported no before other filters"),capacityMetric(v.field+" · unknown",tally.dash_marker,"Source dash, not reported no"));
        app.append(metrics,el("h2","Matching home health records"));
        const slice=matched.slice((v.page-1)*pageSize,v.page*pageSize);
        if(slice.length){
            const rows=slice.map(r=>{const cell=el("div");cell.append(anchor(r.name,route("detail",{source:"home-health",id:r.ccn,state:r.state,section:"services",return:localResearchReturn(location.hash)})),el("small",r.ccn));return [cell,[r.city,r.state].filter(Boolean).join(", "),...hhaFields.map(f=>hhaStates[d.records[hhaKey(r)][f]])]});
            const wrap=table(["Provider / CCN","Reported city / state",...hhaFields],rows);wrap.classList.add("hha-results");wrap.setAttribute("aria-label","Home health service observations; scroll horizontally if needed");app.append(el("p","Scroll horizontally to see all six service columns if needed.","hha-table-hint"),wrap);
            const exp=el("button","Export current page (CSV)");exp.type="button";exp.addEventListener("click",()=>hhaExport(slice,d.records));app.append(add(el("div",undefined,"links"),exp))
        }else app.append(el("div",matched.length?"Page outside matching results. Return to the first page.":"No provider records match these filters.","empty"));
        const pager=el("div",undefined,"pager"),safe={state:v.state,field:v.field,evidence:v.evidence,q:v.q,required:v.required.join("|")};
        pager.append(el("span","Page "+v.page+" · "+N.format(matched.length)+" matches"));
        if(v.page>1)pager.append(anchor("First page",route("hha-services",{...safe,page:1})),anchor("Previous",route("hha-services",{...safe,page:v.page-1})));
        if(v.page*pageSize<matched.length)pager.append(anchor("Next",route("hha-services",{...safe,page:v.page+1})));
        app.append(pager,el("p","All 12,409 existing public home health provider records reconcile to the same pinned CMS release and exact institutional identity fields. A reported dash is unknown, not no. No new identity/contact or patient data are published.","intro"),anchor("Official CMS home health provider source","https://data.cms.gov/provider-data/dataset/6jpm-sxkc",true))
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return;status.replaceWith(el("div","Home health service evidence unavailable: "+e.message+". No values inferred.","error"))}
}
async function hhaProfile(r,signal,epoch){
    const section=el("section",undefined,"hha-profile");section.append(el("h2","Home health reported service offerings"));
    try{
        const data=await hhaEvidence(signal);if(epoch!==sequence)return null;
        const ref=data.byId.get(hhaKey(r));
        if(!ref||["ccn","name","state","address","city","zip"].some(k=>ref[k]!==r[k]))throw Error("Profile directory record differs from qualified source");
        const obs=data.records[hhaKey(r)],grid=el("dl",undefined,"detail-grid hha-profile-grid");
        for(const field of hhaFields){const cell=add(el("div"),el("dt",field),el("dd",hhaStates[obs[field]]));cell.dataset.field=field;grid.append(cell)}
        section.append(el("p","CMS release "+hhaRelease.release+". Same source record, exact CCN/state and reported identity fields. Historical reported offerings do not establish current service availability or staffing.","intro"),grid);section.dataset.evidence="qualified"
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return null;section.dataset.evidence="unavailable";section.append(el("div","Home health service evidence unavailable: "+e.message+". No values inferred.","error"))}
    section.append(add(el("div",undefined,"links"),hhaResearchLink(r.state),anchor("Official CMS source","https://data.cms.gov/provider-data/dataset/6jpm-sxkc",true),anchor("Qualification evidence","https://github.com/JeremyHennessy/FacilitySignal/actions/runs/"+hhaRelease.run,true)));
    return section
}

// Research within the already published record grain. No new physical-site or organization resolution.
function reportedAddressKey(r){
    const parts=["address","city","state","zip"].map(k=>String(r[k]||"").trim().replace(/\s+/g," ").toUpperCase());
    // Require a complete reported tuple. No ZIP truncation, punctuation stripping, abbreviation expansion or geocoding.
    return parts.every(Boolean)?JSON.stringify(parts):null
}
async function profileLocation(r,s,signal,epoch,p){
    const section=el("section",undefined,"profile-location");
    section.append(el("h2","Location and peer evidence"),el("p","Compare the reported address tuple and same-category records in the reported jurisdiction. Text agreement is not a verified physical site, ownership link, or distance measurement.","intro"));
    const status=el("div","Checking the seven published provider sources…","notice");section.append(status);
    const outcomes=await Promise.all(providerSources().map(async source=>{
        try{return {source,rows:(await loadShard(source,signal)).records}}
        catch(e){return {source,error:true}}
    }));
    if(epoch!==sequence||signal.aborted)return null;
    const available=outcomes.filter(x=>!x.error),own=available.find(x=>x.source.key===s.key),state=r.state,tuple=reportedAddressKey(r);
    const peers=own?own.rows.filter(x=>x.state===state):null;
    const matches=tuple?available.flatMap(({source,rows})=>rows.filter(x=>reportedAddressKey(x)===tuple&&!(source.key===s.key&&x.state===r.state&&x.ccn===r.ccn)).map(row=>({source,row}))):[];
    matches.sort((a,b)=>a.source.key.localeCompare(b.source.key)||a.row.name.localeCompare(b.row.name)||a.row.ccn.localeCompare(b.row.ccn));
    status.textContent=available.length+" of "+outcomes.length+" provider sources checked."+(available.length!==outcomes.length?" Partial results; unavailable sources were not interpreted as zero.":"");
    section.dataset.complete=String(available.length===outcomes.length);
    section.append(el("h3","Same-category jurisdiction context"));
    if(!peers)section.append(el("div","The source needed for peer context is unavailable.","error"));
    else{
        const unit=capacityUnits[s.key],grid=el("div",undefined,"metrics profile-peer-metrics");
        grid.append(capacityMetric("Same-category source records",peers.length,state+" · "+s.release));
        if(unit){
            const values=peers.map(publicCapacity).filter(x=>x!==null).sort((a,b)=>a-b),v=publicCapacity(r);
            const mid=Math.floor(values.length/2),median=values.length?(values.length%2?values[mid]:(values[mid-1]+values[mid])/2):null;
            grid.append(capacityMetric("Numeric capacity reported",values.length,unit.label+" · "+N.format(peers.length-values.length)+" unknown"),capacityMetric("Jurisdiction median",median,unit.label+" among numeric reports"));
            if(v!==null&&values.length)grid.append(capacityMetric("Records at or below this value",values.filter(x=>x<=v).length,"Of "+N.format(values.length)+" numeric reports, including this record"));
        }
        section.append(grid,el("p","This is historical source-record context, not a risk ranking or unique-site benchmark. Explicit zeros remain in the numeric distribution; unknown values are excluded from the median. No different units are combined.","intro"));
    }
    section.append(add(el("div",undefined,"links"),anchor("Browse same category in "+state,route("advanced",{source:s.key,state,run:1})),anchor("Open jurisdiction map",route("geography",{source:s.key,state}))));
    section.append(el("h3","Other records with matching reported address text"));
    if(!tuple)section.append(el("div","Address comparison unavailable: one or more reported street, city, state or ZIP fields are missing. No relationship is inferred.","notice"));
    else{
        const rawPage=p.locpage||"1",valid=/^\d{1,6}$/.test(rawPage),page=valid?Math.max(1,Number(rawPage)):1,start=(page-1)*pageSize;
        const summary=el("p",N.format(matches.length)+" other source records with the same reported address tuple"+(available.length!==outcomes.length?" in the available sources":"")+".","intro location-match-count");
        summary.dataset.total=String(matches.length);section.append(summary,el("p","Matching uses complete street, city, state and ZIP text with case and whitespace normalized only. Different programs or organizations may report the same address. This is a research lead, not a resolved relationship.","intro"));
        if(!valid)section.append(el("div","Invalid location results page; showing the first page.","notice"));
        if(matches.length&&start<matches.length){
            const visible=matches.slice(start,start+pageSize);
            const wrapper=table(["Provider / CCN","Category","Reported address","Source release"],visible.map(({source,row})=>[add(el("div"),anchor(row.name,route("detail",{source:source.key,id:row.ccn,state:row.state})),el("small",row.ccn)),names[source.key],[row.address,row.city,row.state,row.zip].join(", "),source.release]));
            wrapper.classList.add("profile-location-table");wrapper.setAttribute("aria-label","Reported address text matches");section.append(wrapper);
        }else section.append(el("div",matches.length?"Page outside matching records. Return to the first page.":available.length===outcomes.length?"No other matching address tuple was found in these seven published source projections.":"No match in the available sources; comparison incomplete.","empty"));
        if(matches.length>pageSize||page>1){
            const pager=el("div",undefined,"pager"),base={source:s.key,id:r.ccn,state:r.state,section:"location",return:localResearchReturn(p.return)};
            pager.append(el("span","Page "+page+" · "+N.format(matches.length)+" matches"));
            if(page>1)pager.append(anchor("First page",route("detail",{...base,locpage:1})),anchor("Previous",route("detail",{...base,locpage:page-1})));
            if(page*pageSize<matches.length)pager.append(anchor("Next",route("detail",{...base,locpage:page+1})));
            section.append(pager);
        }
    }
    const evidence=el("details",undefined,"location-coverage");evidence.append(el("summary","Sources checked and limitations"),table(["Provider category","Release","Lookup status"],outcomes.map(({source,error})=>[names[source.key],source.release,error?"Unavailable":"Published projection checked"])));
    section.append(evidence);
    section.dataset.ready="true";return section
}
// Source-scoped CMS group identifiers never become legal owner IDs.
const nursingChainPin=Object.freeze({payload:"93c9c581f78511e79a22255524c14f2b34a62545598a8633eea6bb6efab22322",directory:"36363899e56c97433686ce8617a7d4b557b272a155e8a8eba1822c6f7a36e3ce",source:"ab70309ae6f0ee86b19fe9acb61a6d2953f970d3b09e80bb9b090e4b19ce35a2",release:"2026-10-28",rows:14686,groups:612,assigned:10227,unassigned:4459,scope:"CMS nursing-home chain affiliation; publisher-defined historical group, not legal ownership."});
const chainToken=v=>typeof v==="string"&&/^[0-9]{1,8}$/.test(v);
async function nursingChainEvidence(signal){
    const p=nursingChainPin,s=providerSources().find(x=>x.key==="nursing");
    if(!s||s.release!==p.release||s.sha256!==p.source||s.stored_rows!==p.rows||publicManifest.sources.nursing?.published_records!==p.rows)throw Error("Nursing source release requires chain requalification");
    const [directory,pack]=await Promise.all([exactJson("web/public-directory/nursing.json?v="+p.directory.slice(0,16),p.directory,signal),exactJson("web/nursing-chain-evidence.json?v="+p.payload.slice(0,16),p.payload,signal)]);
    if(directory.source!=="nursing"||directory.release!==p.release||directory.row_count!==p.rows||!Array.isArray(directory.records)||directory.records.length!==p.rows)throw Error("Nursing directory scope mismatch");
    if(!dialysisKeys(pack,["format_version","scope","source","release","source_sha256","directory_sha256","groups","members"])||pack.format_version!==1||pack.source!=="nursing"||pack.scope!==p.scope||pack.release!==p.release||pack.source_sha256!==p.source||pack.directory_sha256!==p.directory||!Array.isArray(pack.groups)||pack.groups.length!==p.groups||!Array.isArray(pack.members)||pack.members.length!==p.rows)throw Error("Chain projection scope mismatch");
    const groups=new Map(),labels=new Set(),directoryByKey=new Map(directory.records.map(r=>[institutionalKey(r),r])),membership=new Map();
    if(directoryByKey.size!==p.rows)throw Error("Duplicate public directory key");
    for(const item of pack.groups){
        if(!Array.isArray(item)||item.length!==3||!chainToken(item[0])||typeof item[1]!=="string"||!item[1].trim()||item[1].length>300||!Number.isSafeInteger(item[2])||item[2]<2||item[2]>p.assigned||groups.has(item[0])||labels.has(item[1]))throw Error("Invalid CMS group");
        groups.set(item[0],{id:item[0],name:item[1],size:item[2],members:[]});labels.add(item[1]);
    }
    let assigned=0,unassigned=0;
    for(const item of pack.members){
        if(!Array.isArray(item)||item.length!==3||typeof item[0]!=="string"||!/^[A-Z0-9]{6}$/.test(item[0])||!states.includes(item[1])||(item[2]!==null&&!groups.has(item[2])))throw Error("Invalid chain member");
        const key=item[1]+":"+item[0],r=directoryByKey.get(key);
        if(!r||membership.has(key))throw Error("Chain membership identity mismatch");
        membership.set(key,item[2]);
        if(item[2]===null)unassigned++;else{assigned++;groups.get(item[2]).members.push(r)}
    }
    if(membership.size!==p.rows||assigned!==p.assigned||unassigned!==p.unassigned||[...groups.values()].some(g=>g.members.length!==g.size))throw Error("Chain membership reconciliation failed");
    return {groups,membership,directoryByKey}
}
function chainSourceLinks(){return add(el("div",undefined,"links"),anchor("CMS Provider Information","https://data.cms.gov/provider-data/dataset/4pq5-n9py",true),anchor("CMS chain methodology","https://data.cms.gov/sites/default/files/2025-06/97e4c3cd-4104-408e-8bef-24dfab14bf07/UPDATE_Methodology_Nursing_Home_Chain_Performance.pdf",true),anchor("Qualification evidence","https://github.com/JeremyHennessy/FacilitySignal/actions/runs/45886406286",true))}
async function nursingChainExplorer(params,signal,epoch){
    const section=el("section",undefined,"chain-explorer");
    section.append(el("h2","CMS reported chain directory"),el("p","October 28, 2026 source release. Group names are CMS-published labels, not verified parent corporations. Missing group assignment is not proof of independence.","intro"));
    try{
        const d=await nursingChainEvidence(signal);if(epoch!==sequence||signal.aborted)return null;
        const q=(params.chain_q||"").trim(),state=params.chain_state||"",id=params.chain||"",raw=params.chain_page||"1";
        if(q.length>100||(state&&!states.includes(state))||(id&&!chainToken(id))||!/^\d{1,6}$/.test(raw))throw Error("Invalid group research filter");
        const page=Math.max(1,Number(raw)),offset=(page-1)*pageSize;
        const form=el("form",undefined,"toolbar chain-form");
        if(!id)form.append(input("Group name or CMS chain ID","chain_q",q));
        form.append(options("Group research jurisdiction","chain_state",[["","All jurisdictions"],...states.slice().sort().map(s=>[s,s])],state));
        const go=el("button",id?"Filter members":"Find groups");go.type="submit";form.append(go,anchor(id?"All group members":"Reset group filters",route("nursing-portfolios",id?{chain:id}:{})));
        form.addEventListener("submit",e=>{e.preventDefault();const p=Object.fromEntries(new FormData(form));location.hash=route("nursing-portfolios",{...p,chain:id||""})});
        const status=el("p","","intro chain-status");section.append(form,status);
        const pageLinks=(total,base)=>{const pager=el("div",undefined,"pager");
            if(page>1)pager.append(anchor("First page",route("nursing-portfolios",{...base,chain_page:1})),anchor("Previous groups or members",route("nursing-portfolios",{...base,chain_page:page-1})));
            if(offset+pageSize<total)pager.append(anchor("Next groups or members",route("nursing-portfolios",{...base,chain_page:page+1})));
            if(pager.childNodes.length)section.append(pager)
        };
        if(!id){
            const all=[...d.groups.values()].filter(g=>!q||g.name.toLowerCase().includes(q.toLowerCase())||g.id===q);
            const hits=all.map(g=>({g,n:state?g.members.filter(r=>r.state===state).length:g.size})).filter(x=>x.n>0).sort((a,b)=>b.n-a.n||a.g.name.localeCompare(b.g.name)||a.g.id.localeCompare(b.g.id));
            status.textContent=N.format(hits.length)+" matching CMS groups · "+N.format(hits.reduce((n,x)=>n+x.n,0))+" assigned provider records"+(state?" in "+state:"")+".";
            status.dataset.total=String(hits.length);
            const rows=hits.slice(offset,offset+pageSize).map(({g,n})=>[anchor(g.name,route("nursing-portfolios",{chain:g.id,chain_state:state,chain_q:q})),g.id,N.format(n),N.format(g.size),N.format(new Set(g.members.map(r=>r.state)).size)]);
            if(rows.length){const t=table(["CMS reported group","Chain ID","Matching members","National members","Jurisdictions"],rows);t.classList.add("chain-groups");section.append(t)}
            else section.append(el("div",hits.length?"Page outside matching groups. Return to the first page.":"No published groups match these filters.","empty"));
            pageLinks(hits.length,{chain_q:q,chain_state:state});
        }else{
            const g=d.groups.get(id);
            if(!g){status.textContent="CMS group ID not present in this pinned release.";status.dataset.total="0";section.append(anchor("Back to group directory",route("nursing-portfolios")));section.dataset.ready="true";return section}
            section.insertBefore(el("h3",g.name,"chain-group-title"),form);
            section.insertBefore(add(el("div",undefined,"links"),anchor("Back to group directory",route("nursing-portfolios",{chain_q:q,chain_state:state}))),form);
            const members=g.members.filter(r=>!state||r.state===state).sort((a,b)=>a.state.localeCompare(b.state)||a.name.localeCompare(b.name)||a.ccn.localeCompare(b.ccn));
            const known=members.map(publicCapacity).filter(x=>x!==null);
            status.textContent=N.format(members.length)+" matching member records · CMS chain ID "+id+" · "+nursingChainPin.release+".";
            status.dataset.total=String(members.length);
            const grid=el("div",undefined,"metrics");
            grid.append(capacityMetric("National group membership",g.size,"CMS reported size; reconciled"),capacityMetric("Matching member records",members.length,state||"All jurisdictions"),capacityMetric("Known certified beds",known.length?known.reduce((n,v)=>n+v,0):null,N.format(known.length)+" numeric reports; "+N.format(members.length-known.length)+" unknown"),capacityMetric("Matching jurisdictions",new Set(members.map(r=>r.state)).size,"Reported member states / territories"));
            section.append(grid,el("p","Capacity sums known source-reported certified beds within the selected membership; it is not occupancy, a count of physical properties, or current ownership.","intro"));
            const regions=[...new Set(g.members.map(r=>r.state))].sort().map(st=>[anchor(st,route("nursing-portfolios",{chain:id,chain_state:st})),N.format(g.members.filter(r=>r.state===st).length)]);
            const distribution=el("details",undefined,"location-coverage");distribution.append(el("summary","Group membership by jurisdiction"),table(["Reported jurisdiction","Member records"],regions));section.append(distribution);
            const rows=members.slice(offset,offset+pageSize).map(r=>[add(el("div"),anchor(r.name,route("detail",{source:"nursing",id:r.ccn,state:r.state,return:localResearchReturn(location.hash)})),el("small",r.ccn)),[r.city,r.state].filter(Boolean).join(", "),publicCapacity(r)===null?"Not reported":N.format(publicCapacity(r)),nursingChainPin.release]);
            if(rows.length){const t=table(["Member provider / CCN","Reported city / state","Certified beds","Source release"],rows);t.classList.add("chain-members");section.append(t)}
            else section.append(el("div",members.length?"Page outside matching members. Return to the first page.":"No members in the selected jurisdiction.","empty"));
            if(members.length){
                const exp=el("button","Export matching members (CSV)");exp.type="button";exp.addEventListener("click",()=>downloadResearchCsv("facilitysignal-cms-chain-"+id+".csv",[["source","release","cms_chain_id","cms_group_label","ccn","provider_name","city","state","reported_certified_beds","capacity_evidence"],...members.map(r=>["CMS Care Compare nursing",nursingChainPin.release,id,g.name,r.ccn,r.name,r.city,r.state,publicCapacity(r),publicCapacity(r)===null?"not_reported":"reported_numeric"])]));section.append(add(el("div",undefined,"links"),exp))
            }
            pageLinks(members.length,{chain:id,chain_state:state,chain_q:q});
        }
        section.append(chainSourceLinks());section.dataset.ready="true";
    }catch(e){if(epoch!==sequence||signal.aborted||e.name==="AbortError")return null;section.append(el("div","CMS chain evidence unavailable: "+e.message+". No membership inferred.","error"));section.dataset.ready="false"}
    return section
}
async function nursingChainProfile(r,signal,epoch){
    const section=el("section",undefined,"nursing-chain-profile");section.append(el("h2","CMS reported chain affiliation"));
    try{
        const d=await nursingChainEvidence(signal);if(epoch!==sequence||signal.aborted)return null;
        const key=institutionalKey(r),reference=d.directoryByKey.get(key);
        if(!reference||["ccn","name","state","address","city","zip"].some(k=>reference[k]!==r[k])||!d.membership.has(key))throw Error("Profile record differs from qualified directory");
        const id=d.membership.get(key);
        if(id===null){section.append(el("p","No group ID reported in this CMS release. This does not establish that the facility is independent.","notice"));section.dataset.evidence="unassigned"}
        else{const g=d.groups.get(id);section.append(add(el("p"),anchor(g.name,route("nursing-portfolios",{chain:id}))),el("p",N.format(g.size)+" reported member records · CMS group ID "+id+" · release "+nursingChainPin.release,"intro"));section.dataset.evidence="assigned"}
        section.append(el("p","Publisher-defined group membership is not proof of controlling or property ownership.","intro"));
    }catch(e){if(epoch!==sequence||signal.aborted||e.name==="AbortError")return null;section.dataset.evidence="unavailable";section.append(el("div","Chain affiliation evidence unavailable; no membership inferred.","error"))}
    section.append(chainSourceLinks());return section
}
function profileSources(s,r,f){
    const section=el("section");
    section.append(el("h2","Source and release"),table(["Evidence","Value"],[["Provider source",names[s.key]],["Source identifier (CCN)",shown(value(r,f,"id"))],["Reported state",shown(value(r,f,"state"))],["Published release",s.release],["Public projection",sourceLink(s,"Official source")]]),
        el("h2","Evidence availability for this record"),
        el("p","Scroll horizontally to see all evidence columns.","profile-scroll-hint"),profileEvidenceTable(["Evidence area","Public availability","Research link"],[
            ["Provider identity","Published source record",sourceLink(s)],
            ["Comparable capacity",capacityUnits[s.key]?(publicCapacity(r)===null?"Unknown":"Source-reported "+capacityUnits[s.key].label.toLowerCase()):"No qualified unit",capacityUnits[s.key]?anchor("Capacity explorer",route("capacity",{source:s.key,state:value(r,f,"state")})):"—"],
            ...(historicalCapacityPins[s.key]?[["Historical cost-report capacity","FY2024 selected CMS report subset; check exact record",historicalCapacityLink(s,r,read().p)]]:[]),
            ["Nursing citation aggregates",s.key==="nursing"?"Same-CCN/state candidate lookup":"No facility-linked public evidence",s.key==="nursing"?anchor("Compliance section",route("detail",{source:s.key,id:value(r,f,"id"),state:value(r,f,"state"),return:localResearchReturn(read().p.return),section:"compliance"})):anchor("National compliance research",route("compliance-research"))],
            ["Certification registry evidence","Individual relationships not published",anchor("Certification registry coverage",route("certifications"))],
            ["Clinical service capability",s.key==="dialysis"?"Selected iQIES and Care Compare observations; separate source releases":s.key==="home-health"?"Six same-source Care Compare service indicators":s.key==="hospital"?"Same-source emergency-services flag":"Individual observations not published",["hospital","dialysis","home-health"].includes(s.key)?anchor("Services & capacity section",route("detail",{source:s.key,id:r.ccn,state:r.state,section:"services",return:localResearchReturn(read().p.return)})):anchor("National service evidence",route("services"))],
            ["PECOS organizational roles","Individual relationships not published",anchor("Ownership evidence coverage",route("ownership"))],
            ...(s.key==="nursing"?[["CMS nursing chain membership","Published source-scoped affiliation; check Summary for the exact record",anchor("Nursing portfolio research",route("nursing-portfolios"))]]:[]),
            ["Equipment and environment","Individual relationships not published",anchor("National equipment and environmental research",route("equipment-environment"))],
            ["Property / procurement","No qualified public facility relationships",anchor("Procurement research",route("procurement"))]
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
                if(result.total===1)app.append(portfolioSavePanel(s,r,f));
                const evidence=el("section",undefined,"dossier-evidence");
                evidence.append(el("h2","Published facility evidence"),el("p","Only evidence available for this exact source record is shown here. Source periods and observation types remain separate.","intro"));
                if(capacityUnits[s.key]){
                    const unit=capacityUnits[s.key],v=publicCapacity(r);
                    evidence.append(add(el("div",undefined,"dossier-capacity"),el("strong",v===null?"Not reported / nonnumeric":N.format(v)+" "+unit.label.toLowerCase()),el("span",v===null?"Unknown capacity":v===0?"Explicit reported zero":"Source-reported capacity"),anchor("Explore comparable records",route("capacity",{source:s.key,state:r.state}))));
                }
                if(historicalCapacityPins[s.key])evidence.append(add(el("p"),historicalCapacityLink(s,r,p)));
                app.append(evidence);
                if(s.key==="nursing"){const c=await profileCompliance(r,s,f,signal,epoch);if(!c||epoch!==sequence)return;evidence.append(c)}
                else if(s.key==="dialysis"){const c=await dialysisProfile(r,signal,epoch);if(!c||epoch!==sequence)return;evidence.append(c)}
                else if(s.key==="home-health"){const c=await hhaProfile(r,signal,epoch);if(!c||epoch!==sequence)return;evidence.append(c)}
                else if(!Object.hasOwn(institutionalPin.sources,s.key))evidence.append(el("p","Additional individual service, inspection or infrastructure observations are not currently published for this category.","notice"));
                if(Object.hasOwn(institutionalPin.sources,s.key)){const inst=await institutionalProfile(r,s,signal,epoch);if(!inst||epoch!==sequence)return;evidence.append(inst)}
                if(s.key==="nursing"){const chain=await nursingChainProfile(r,signal,epoch);if(!chain||epoch!==sequence)return;evidence.append(chain)}
                evidence.dataset.ready="true";
                const base={source:s.key,id:r.ccn,state:r.state,return:localResearchReturn(p.return)};
                app.append(profileResearchActions(s,r,f),add(el("div",undefined,"links"),anchor("Investigate reported address and peers",route("detail",{...base,section:"location"})),anchor("View sources and coverage",route("detail",{...base,section:"sources"}))));
                const related=el("details",undefined,"dossier-coverage");
                related.append(el("summary","National research and evidence limitations"),el("p","Monetary financial measures and individual-level equipment, environmental, property and ownership relationships are not inferred or published here. National coverage links do not establish relationships for this facility.","intro"),add(el("div",undefined,"links"),anchor("Certification registry coverage",route("certifications")),anchor("Hospital survey coverage",route("hospital-surveys")),anchor("Ownership evidence coverage",route("ownership")),anchor("National service evidence",route("services")),anchor("National equipment and environmental research",route("equipment-environment")),anchor("Financial report research",route("financial-research"))));app.append(related);
            }else if(section==="services"){const services=await profileService(r,s,f,signal,epoch);if(!services||epoch!==sequence)return;app.append(services)}
            else if(section==="compliance"){const c=await profileCompliance(r,s,f,signal,epoch);if(!c||epoch!==sequence)return;app.append(c)}
            else if(section==="location"){const waiting=el("div","Loading source-scoped location evidence…","notice");app.append(waiting);const c=await profileLocation(r,s,signal,epoch,p);if(!c||epoch!==sequence)return;waiting.replaceWith(c)}
            else app.append(profileSources(s,r,f))
        }
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return;title("Source record","Provider evidence unavailable.");app.append(errorBox(s,e))}
}

// A user-curated list of public source records, not an inferred ownership portfolio.
// Only a bounded, validated set of source keys and public labels is stored in this browser.
const portfolioStorageKey="facilitysignal.public.portfolio.v1",portfolioLimit=100;
const portfolioKey=r=>[r.source,r.state,r.ccn].join(":");
function validPortfolioRecord(r){
    return r&&Object.keys(r).sort().join("|")==="ccn|name|release|source|state"&&providerSources().some(s=>s.key===r.source)&&states.includes(r.state)&&/^[A-Z0-9]{6}$/.test(r.ccn)&&typeof r.name==="string"&&r.name.length>0&&r.name.length<=300&&typeof r.release==="string"&&/^\d{4}-\d{2}-\d{2}$/.test(r.release);
}
function readPortfolio(){
    const raw=localStorage.getItem(portfolioStorageKey);if(raw===null)return [];
    const rows=JSON.parse(raw);if(!Array.isArray(rows)||rows.length>portfolioLimit||rows.some(r=>!validPortfolioRecord(r))||new Set(rows.map(portfolioKey)).size!==rows.length)throw Error("Saved portfolio data is invalid; no records were overwritten.");
    return rows
}
function writePortfolio(rows){if(rows.length>portfolioLimit||rows.some(r=>!validPortfolioRecord(r))||new Set(rows.map(portfolioKey)).size!==rows.length)throw Error("Invalid saved portfolio");localStorage.setItem(portfolioStorageKey,JSON.stringify(rows))}
function portfolioSavePanel(s,r,f){
    const panel=el("section",undefined,"portfolio-save"),record={source:s.key,state:value(r,f,"state"),ccn:value(r,f,"id"),name:value(r,f,"name"),release:s.release};
    if(!validPortfolioRecord(record))return panel;
    const status=el("p","","intro"),button=el("button","Save to research portfolio");button.type="button";
    panel.append(el("h2","Personal research portfolio"),el("p","Save this exact public source record in this browser only. No account, private notes, ownership grouping or server synchronization.","intro"),add(el("div",undefined,"links"),button,anchor("Open saved portfolio",route("saved-portfolio"))),status);
    function refresh(){
        try{const rows=readPortfolio(),has=rows.some(x=>portfolioKey(x)===portfolioKey(record));button.disabled=has||rows.length>=portfolioLimit;button.textContent=has?"Saved to research portfolio":"Save to research portfolio";status.textContent=has?"Record already saved.":rows.length>=portfolioLimit?"Portfolio limit reached (100 records).":""}
        catch(e){button.disabled=true;status.textContent="Browser storage unavailable or invalid. No records changed."}
    }
    button.addEventListener("click",()=>{try{const rows=readPortfolio();if(!rows.some(x=>portfolioKey(x)===portfolioKey(record))){if(rows.length>=portfolioLimit)throw Error("Portfolio full");writePortfolio([...rows,record])}refresh()}catch(e){status.textContent="Unable to save; existing records were not intentionally changed."}});
    refresh();return panel
}
function downloadResearchCsv(filename,rows){
    const content=rows.map(row=>row.map(safeCsvCell).join(",")).join("\r\n")+"\r\n";
    const url=URL.createObjectURL(new Blob([content],{type:"text/csv;charset=utf-8"})),a=el("a");
    a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000)
}
function savedPortfolio(p){
    title("Saved facility portfolio","A personal research list of exact public provider source records, not an inferred company or property portfolio. Stored only in this browser; other applications on the same origin may access browser storage. Do not store confidential information here.");
    app.append(add(el("div",undefined,"links"),anchor("Find facilities",route("advanced")),anchor("Nursing chain evidence",route("nursing-portfolios")),anchor("Hospital infrastructure",route("hospital-infrastructure")),anchor("Financial report research",route("financial-research")),anchor("Procurement research",route("procurement"))));
    let rows;try{rows=readPortfolio()}catch(e){app.append(el("div","Saved portfolio unavailable: browser storage is blocked or invalid. Existing storage was not changed.","error"));return}
    const count=el("p",N.format(rows.length)+" saved source records · maximum "+portfolioLimit,"intro portfolio-count");app.append(count);
    const form=el("form",undefined,"toolbar"),source=options("Saved provider category","source",[["","All categories"],...providerSources().map(s=>[s.key,names[s.key]])],p.source||""),state=options("Saved jurisdiction","state",[["","All jurisdictions"],...states.slice().sort().map(s=>[s,s])],p.state||"");
    form.append(source,state,el("button","Filter"));form.addEventListener("submit",e=>{e.preventDefault();location.hash=route("saved-portfolio",Object.fromEntries(new FormData(form)))});app.append(form);
    const filtered=rows.filter(r=>(!p.source||r.source===p.source)&&(!p.state||r.state===p.state));
    if(!filtered.length){app.append(el("div",rows.length?"No saved records match these filters.":"No records saved. Open a facility profile and save the exact source record.","notice"));return}
    const picked=new Set(),checks=[],compare=el("button","Compare selected (0 / 4)");compare.type="button";compare.disabled=true;
    const compareStatus=el("span","Select 2–4 saved records to compare source-reported evidence.","intro");
    const update=()=>{compare.disabled=picked.size<2;compare.textContent="Compare selected ("+picked.size+" / 4)";for(const c of checks)c.disabled=!c.checked&&picked.size>=4};
    compare.addEventListener("click",()=>{if(picked.size>=2&&picked.size<=4)location.hash=route("compare",{records:[...picked].join("|")})});
    const exportList=el("button","Export filtered portfolio CSV");exportList.type="button";
    exportList.addEventListener("click",()=>downloadResearchCsv("facilitysignal-saved-portfolio.csv",[
        ["source","source_identifier","reported_name_at_save","reported_state","saved_source_release","current_published_release","evidence_scope"],
        ...filtered.map(r=>[r.source,r.ccn,r.name,r.state,r.release,providerSources().find(s=>s.key===r.source)?.release||"Unavailable","Saved public source record; not a unique property or an inferred ownership relationship"])
    ]));
    app.append(add(el("div",undefined,"links portfolio-compare-controls"),compare,compareStatus,exportList));
    const grid=el("div",undefined,"metrics"),groups=new Map();
    for(const r of filtered)groups.set(r.source,(groups.get(r.source)||0)+1);
    for(const [source,n] of groups)grid.append(capacityMetric(names[source],n,"Saved source records (not unique sites)"));
    const results=table(["Saved provider / CCN","Category","Reported state","Saved source release","Action"],filtered.map(r=>{
        const current=providerSources().find(s=>s.key===r.source),remove=el("button","Remove");remove.type="button";
        remove.addEventListener("click",()=>{try{writePortfolio(readPortfolio().filter(x=>portfolioKey(x)!==portfolioKey(r)));savedPortfolio(p)}catch(e){app.append(el("div","Unable to remove record; browser storage unavailable.","error"))}});
        const pick=el("input");pick.type="checkbox";pick.setAttribute("aria-label","Select "+r.name+" ("+r.ccn+") for comparison");checks.push(pick);
        pick.addEventListener("change",()=>{if(pick.checked){if(picked.size>=4){pick.checked=false;return}picked.add(portfolioKey(r))}else picked.delete(portfolioKey(r));update()});
        return [add(el("div",undefined,"portfolio-provider-cell"),pick,add(el("div"),anchor(r.name,route("detail",{source:r.source,id:r.ccn,state:r.state})),el("small"," · "+r.ccn))),names[r.source],r.state,r.release+(current.release!==r.release?" (newer source available)":""),remove]
    }));
    results.classList.add("portfolio-results");results.setAttribute("aria-label","Saved facility source records; scroll horizontally if needed");
    app.append(grid,el("p","Scroll the saved records table horizontally to view source dates and actions.","portfolio-scroll-hint intro"),results,el("p","Source names and dates are saved snapshots. Open profiles to re-check current published source records; no identity merge or update is inferred.","intro"));
}

async function compareFacilities(p,signal,epoch){
    title("Compare saved facilities","Compare 2–4 exact public provider source records. Different capacity units are not combined; national coverage is not attributed to individual facilities.");
    app.append(add(el("div",undefined,"links"),anchor("Back to saved portfolio",route("saved-portfolio"))));
    let selected;
    try{
        const tokens=(p.records||"").split("|"),rows=readPortfolio(),map=new Map(rows.map(r=>[portfolioKey(r),r]));
        if(tokens.length<2||tokens.length>4||new Set(tokens).size!==tokens.length||tokens.some(k=>!map.has(k)))throw Error("Select 2–4 distinct records from your saved portfolio.");
        selected=tokens.map(k=>map.get(k));
    }catch(e){app.append(el("div",e.message,"error"));return}
    const status=el("div","Loading exact source records and historical nursing citation aggregates…","notice");app.append(status);
    const wanted=new Set(selected.map(r=>r.source));
    if(wanted.has("nursing")){wanted.add("nursing-health");wanted.add("nursing-fire")}
    const data=new Map();
    await Promise.all([...wanted].map(async key=>{
        const source=lock.sources.find(s=>s.key===key&&s.family==="care-compare");
        try{if(!source)throw Error("Source missing");data.set(key,{source,rows:(await loadShard(source,signal)).records})}
        catch(e){data.set(key,{source,error:true})}
    }));
    if(epoch!==sequence||signal.aborted)return;
    function observation(key,r){
        const d=data.get(key);
        if(!d||d.error)return {label:"Source unavailable",record:null};
        const found=d.rows.filter(x=>x.ccn===r.ccn&&x.state===r.state);
        if(found.length!==1)return {label:found.length?"Multiple matching source records":"No matching source record",record:null};
        return {label:"Exact CCN and reported state match",record:found[0]}
    }
    const obs=selected.map(r=>observation(r.source,r));
    const cellsFor=(label,fn)=>[label,...selected.map((r,i)=>fn(r,obs[i],i))];
    const citation=(key,r,o)=>{
        if(r.source!=="nursing")return "Not applicable to this source";
        if(!o.record)return "Provider record unresolved";
        const c=observation(key,r);
        return c.record?N.format(c.record.citation_rows)+" historical rows":c.label+" (not zero)"
    };
    const rows=[
        cellsFor("Provider category",r=>names[r.source]),
        cellsFor("Source identifier",r=>r.ccn),
        cellsFor("Reported state",r=>r.state),
        cellsFor("Saved source release",r=>r.release),
        cellsFor("Current published release",r=>data.get(r.source)?.source?.release||"Unavailable"),
        cellsFor("Source record lookup",(_,o)=>o.label),
        cellsFor("Published provider name",(_,o)=>o.record?shown(o.record.name):"Unavailable"),
        cellsFor("Published address",(_,o)=>o.record?[o.record.address,o.record.city,o.record.state,o.record.zip].filter(Boolean).join(", ")||"Not reported":"Unavailable"),
        cellsFor("Reported capacity", (r,o)=>o.record?advancedCapacityText(data.get(r.source).source,o.record):"Unavailable"),
        cellsFor("Nursing health citation evidence",(r,o)=>citation("nursing-health",r,o)),
        cellsFor("Nursing fire citation evidence",(r,o)=>citation("nursing-fire",r,o)),
        cellsFor("Facility evidence profile",r=>anchor("Open source record",route("detail",{source:r.source,id:r.ccn,state:r.state})))
    ];
    const wrapper=table(["Evidence field",...selected.map(r=>r.name+" · "+r.ccn)],rows);wrapper.classList.add("comparison-table");wrapper.dataset.records=String(selected.length);wrapper.setAttribute("aria-label","Saved facility evidence comparison; scroll horizontally");
    status.replaceWith(el("p",N.format(selected.length)+" selected source records · "+N.format(obs.filter(o=>o.record).length)+" exact published records resolved","intro comparison-status"));
    const exportComparison=el("button","Export comparison CSV");exportComparison.type="button";
    exportComparison.addEventListener("click",()=>downloadResearchCsv("facilitysignal-facility-comparison.csv",[
        ["Evidence field",...selected.map(r=>r.name+" · "+r.ccn)],
        ...rows.slice(0,-1),
        ["Facility evidence profile",...selected.map(r=>new URL(route("detail",{source:r.source,id:r.ccn,state:r.state}),location.href).href)],
        ["Evidence limitations",...selected.map(()=>"Historical nursing citation rows are not current findings or counts of inspections. Missing or unresolved evidence does not establish compliance. No portfolio ownership or shared property is inferred.")]
    ]));
    app.append(add(el("div",undefined,"links"),exportComparison),el("p","On narrow screens, scroll the table horizontally to see all selected facilities. Evidence field labels stay visible.","comparison-scroll-hint intro"),wrapper,el("div","Historical nursing citation rows are not current findings or counts of inspections. Missing or unresolved evidence does not establish compliance. No portfolio ownership or shared property is inferred.","notice"))
}

async function procurementResearch(signal,epoch){
    title("Procurement research","Research documented public purchasing activity. This is source discovery and evidence methodology; there is no qualified searchable contract or active solicitation feed in this public workspace.");
    const sources=[
        ["SAM.gov contract opportunities","Public opportunities and notice versions","Active or archived notice; confirm closing dates and amendments with the publisher.","API key required for the documented public API. No feed ingested.","https://sam.gov/content/opportunities","https://open.gsa.gov/api/get-opportunities-public-api/"],
        ["USAspending.gov","Federal award and obligation records","Historical award activity; not an open tender, purchasing intent or facility-specific contract without corroboration.","Bounded historical award sample qualified; no public award or contractor rows.","https://www.usaspending.gov/search","https://api.usaspending.gov/"],
        ["Department of Veterans Affairs acquisition","VA procurement information","Issuing agency or contracting office is not necessarily the physical place of performance.","Publisher research; no qualified facility links.","https://www.va.gov/opal/","https://www.va.gov/opal/"]
    ];
    const sourceTable=table(["Publisher / source","Evidence grain","Interpretation","Current coverage","Research links"],sources.map(([n,grain,meaning,status,url,docs])=>[n,grain,meaning,status,add(el("div"),anchor("Publisher",url,true),add(el("small"),anchor("Documentation",docs,true)))]));
    sourceTable.classList.add("procurement-source-table");
    app.append(el("h2","Official research sources"),sourceTable);
    const pilot=el("section",undefined,"procurement-pilot");pilot.append(el("h2","Bounded federal award qualification"),el("p","Loading the qualified aggregate audit…","intro"));app.append(pilot);
    app.append(el("h2","Commercial evidence classifications"),table(["Evidence classification","What is required","What it does not establish"],[
        ["Documented active solicitation","Publisher notice ID, active status, publication and closing dates; verify amendments.","Award, guaranteed purchase or facility relationship."],
        ["Documented historical award","Official award identifier, award type, issuer, source reporting date and recipient.","Open opportunity, outstanding balance or service failure."],
        ["Research context","Documented provider type, capacity or source-level service / regulatory evidence.","Purchasing intent, installed equipment or confirmed need."],
        ["Unresolved relationship","Institutional name / geography candidate requiring independent corroboration.","Legal ownership, contractor responsibility or physical-site identity."]
    ]),el("div","No confirmed procurement opportunities or contractor relationships are published. Use the official sources for actual notices and awards. Do not infer a sale from historical citations, capacity or agency association.","notice"));
    app.append(add(el("div",undefined,"links"),anchor("Industry research",route("industry")),anchor("Saved facility portfolio",route("saved-portfolio")),anchor("Financial report research",route("financial-research")),anchor("Data intelligence",route("data-evidence"))));
    try{
        const res=await fetch("research/procurement_awards_audit_20261126.json",{signal});
        if(!res.ok)throw Error("Audit HTTP "+res.status);
        const d=await res.json();if(epoch!==sequence)return;
        const a=d.audit;
        if(!a||!Number.isSafeInteger(d.qualification_run)||d.qualification_run<=0||a.qualification!=="bounded_award_page_schema_and_grain"||a.publisher!=="USAspending.gov"||!Number.isSafeInteger(a.sample_rows)||a.sample_rows<=0||a.sample_rows>100||a.unique_generated_award_ids!==a.sample_rows||a.retained_row_level_records!==0||a.confirmed_active_opportunities!==0||a.confirmed_facility_relationships!==0||typeof a.additional_pages_reported!=="boolean"||a.request?.page!==1)throw Error("Unexpected qualification audit");
        const window=a.request?.filters?.time_period?.[0];
        if(!window||!/^\d{4}-\d{2}-\d{2}$/.test(window.start_date)||!/^\d{4}-\d{2}-\d{2}$/.test(window.end_date))throw Error("Invalid audit period");
        pilot.replaceChildren(el("h2","Bounded federal award qualification"),
            el("p","USAspending.gov · Department of Veterans Affairs awarding department · "+window.start_date+" to "+window.end_date+" search window. One high-amount award page; not representative of national healthcare purchasing.","intro"));
        const metrics=el("div",undefined,"metrics");
        metrics.append(capacityMetric("Sampled historical award rows",a.sample_rows,"One bounded page"),capacityMetric("Distinct source award IDs",a.unique_generated_award_ids,"No duplicate identifiers in this page"));
        pilot.append(metrics,el("p",a.additional_pages_reported?"Publisher reports more result pages; full coverage not established.":"No additional page was reported for this sample request. No broader completeness established.","intro"),
            el("p","No facility relationship or active solicitation was verified. No award or recipient rows retained; commercial reuse review pending.","intro"),
            add(el("div",undefined,"links"),anchor("Qualification run "+d.qualification_run,"https://github.com/JeremyHennessy/FacilitySignal/actions/runs/"+d.qualification_run,true),anchor("Official USAspending award search", "https://www.usaspending.gov/search",true)));
        const fields=[["Award identifier present",a.award_id_present_count],["Contract type present",a.contract_type_present_count],["Recipient UEI format present",a.uei_format_present_count],["US reported performance jurisdiction",a.performance_state_scope_counts?.us_jurisdiction],["Confirmed facility relationships",a.confirmed_facility_relationships],["Confirmed active opportunities",a.confirmed_active_opportunities]];
        if(fields.some(([,v])=>!Number.isSafeInteger(v)||v<0||v>a.sample_rows))throw Error("Invalid award field coverage");
        pilot.append(el("h2","Sampled award field coverage"),table(["Source field or relationship","Sample rows"],fields.map(([k,v])=>[k,N.format(v)])));
        pilot.dataset.qualified="true"
    }catch(e){if(epoch!==sequence||e.name==="AbortError")return;pilot.replaceChildren(el("h2","Bounded federal award qualification"),el("div","Aggregate audit unavailable. No award counts inferred. "+e.message,"error"))}
}

function coverageView(view){const own=view==="ownership",items=byFamily(own?"pecos":"qcor");title(own?"Ownership evidence coverage":"Hospital survey coverage",own?"Aggregate PECOS qualification only. Individual ownership records and organizational projections are not published on this public site.":"QCOR survey rows include tags, memos, repeated projections and historical evidence. Correction status is unknown; narrative and row-level workbook data are not published here.");app.append(historicalNote());if(own){app.append(add(el("div",undefined,"links"),anchor("Nursing portfolio research",route("nursing-portfolios"))));const group=el("div",undefined,"metrics");for(const [label,prefix] of [["Hospital enrollment evidence","hospital"],["Skilled nursing enrollment evidence","snf"]]){const family=items.filter(s=>s.key.startsWith(prefix+"-"));const enroll=family.filter(s=>s.key.endsWith("-enrollment")),roles=family.filter(s=>s.key.endsWith("-owner")),changes=family.filter(s=>s.key.endsWith("-chow"));group.append(capacityMetric(label,aggregate(enroll),"Historical source enrollment rows"),capacityMetric(prefix==="hospital"?"Hospital organizational roles":"SNF organizational roles",aggregate(roles),"Organization role source rows; not unique owners"),capacityMetric(prefix==="hospital"?"Hospital ownership changes":"SNF ownership changes",aggregate(changes),"Historical CHOW source rows"))}app.append(group,el("p","Organization research requires a source-family enrollment ID and provider PAC ID relationship, with separate CCN/state corroboration. Individual source relationships remain local-only; no public portfolio can be inferred from these aggregate counts.","intro"))}app.append(table(["Source","Release period","Historical retained rows","Evidence"],sourceRows(items)),el("div",own?"Exact CCN and state candidates do not establish controlling ownership, physical property title, complete portfolios or current operational responsibility.":"Use the official QCOR report for source research. This site does not publish or infer active hospital violations.","notice"))}
function sourceRegister(p){title("Source register","Discovered sources, historical qualification, and reuse review are separate. A listed source is not necessarily loaded or publicly searchable.");const f=el("form",undefined,"toolbar");f.append(input("Filter source names, publishers or jurisdiction","q",p.q),el("button","Filter"));f.addEventListener("submit",e=>{e.preventDefault();location.hash=route("sources",Object.fromEntries(new FormData(f)))});app.append(f);let overlay=new Map(coverage.sources.map(s=>[s.id,s]));let q=(p.q||"").toLowerCase();let rows=register.sources.filter(s=>!q||[s.id,s.source,s.publisher,s.jurisdiction,s.category].some(x=>String(x).toLowerCase().includes(q)));let page=Math.max(1,Math.min(Math.ceil(rows.length/pageSize)||1,Number(p.page)||1));app.append(el("p",N.format(rows.length)+" source entries · original register preserved"));app.append(table(["Source","Jurisdiction","Qualification","Reuse review","Evidence"],rows.slice((page-1)*pageSize,page*pageSize).map(s=>[s.id+" · "+s.source,s.jurisdiction,overlay.get(s.id)?.private_archive_evidence?.display_status||overlay.get(s.id)?.status||"Discovered / not tested",overlay.get(s.id)?.reuse_review||s.reuse_review,safeExternal(s.source_url)?anchor("Publisher source",safeExternal(s.source_url),true):"See register"])));const pager=el("div",undefined,"pager");if(page>1)pager.append(anchor("Previous",route("sources",{...p,page:page-1})));if(page*pageSize<rows.length)pager.append(anchor("Next",route("sources",{...p,page:page+1})));app.append(pager)}
async function render(){if(!lock)return;if(active)active.abort();active=new AbortController();const {view,p}=read(),epoch=++sequence;for(const a of document.querySelectorAll("nav[aria-label='Primary navigation'] a")){if(a.getAttribute("href")==="#"+(view==="compare"?"saved-portfolio":view==="detail"?"facilities":view))a.setAttribute("aria-current","page");else a.removeAttribute("aria-current")}if(view==="overview")overview();else if(view==="search")await unifiedSearch(p,active.signal,epoch);else if(view==="advanced")await advancedResearch(p,active.signal,epoch);else if(view==="industry")industryResearch(p);else if(view==="procurement")await procurementResearch(active.signal,epoch);else if(view==="saved-portfolio")savedPortfolio(p);else if(view==="compare")await compareFacilities(p,active.signal,epoch);else if(view==="geography")await geography(p,active.signal,epoch);else if(view==="capacity")await capacityExplorer(p,active.signal,epoch);else if(view==="dialysis-services")await dialysisServices(p,active.signal,epoch);else if(view==="hha-services")await hhaServices(p,active.signal,epoch);else if(["services","compliance-research","equipment-environment","data-evidence","nursing-portfolios","hospital-infrastructure","financial-research"].includes(view))await intelligence(view,active.signal,epoch);else if(["facilities","citations"].includes(view))await directory(view,p,active.signal,epoch);else if(view==="certifications")certificationCoverage();else if(view==="detail")await detail(p,active.signal,epoch);else if(["ownership","hospital-surveys"].includes(view))coverageView(view);else if(view==="sources")sourceRegister(p);else title("Page not found","Choose an available workspace from navigation.");}
$("global-search").addEventListener("submit",e=>{e.preventDefault();let q=$("global-q").value.trim();location.hash=route("search",{field:/^\d{5}$/.test(q)?"zip":/^(?=.*[0-9])[A-Za-z0-9]{6}$/.test(q)?"id":"name",q})});
document.querySelector(".skip").addEventListener("click",e=>{e.preventDefault();$("workspace").focus()});
const mobileSelect=$("mobile-route"),primaryNav=document.querySelector("nav[aria-label='Primary navigation']");
for(const item of primaryNav.children){
    if(item.matches("a")){const o=el("option",item.textContent);o.value=item.getAttribute("href");mobileSelect.append(o)}
    else if(item.matches("details")){const group=el("optgroup");group.label=item.querySelector("summary").textContent;for(const a of item.querySelectorAll("a")){const o=el("option",a.textContent);o.value=a.getAttribute("href");group.append(o)}mobileSelect.append(group)}
}
function syncMobileRoute(){const {view}=read();const target=view==="detail"?"#facilities":view==="compare"?"#saved-portfolio":"#"+view;
    const activeLink=[...primaryNav.querySelectorAll("a")].find(a=>a.getAttribute("href")===target);
    for(const group of primaryNav.querySelectorAll("details"))group.open=!!activeLink&&group.contains(activeLink);
    if([...mobileSelect.options].some(o=>o.value===target))mobileSelect.value=target;
    if(window.matchMedia("(max-width:720px)").matches&&activeLink&&activeLink.getClientRects().length){const x=activeLink.getBoundingClientRect().left-primaryNav.getBoundingClientRect().left;if(x<0||x+activeLink.offsetWidth>primaryNav.clientWidth)primaryNav.scrollLeft+=x-10}
}
mobileSelect.addEventListener("change",()=>{location.hash=mobileSelect.value});
window.addEventListener("hashchange",()=>{render();syncMobileRoute()});
(async()=>{try{[lock,register,coverage,publicManifest]=await Promise.all(["research/snapshot_release_20261125.json","research/facilitysignal_source_register_v0.2.json","research/coverage_status.json","web/public-directory/manifest.json"].map(async path=>{let r=await fetch(path);if(!r.ok)throw Error("Source metadata HTTP "+r.status);return r.json()}));if(!Array.isArray(lock.sources)||!Array.isArray(register.sources)||!Array.isArray(coverage.sources)||!Array.isArray(publicManifest.jurisdictions)||!publicManifest.sources)throw Error("Invalid source metadata");render();syncMobileRoute()}catch(e){title("Source metadata unavailable","The workspace could not load its source metadata. No data are inferred.");app.append(el("div",e.message,"error"),anchor("FacilitySignal repository","https://github.com/JeremyHennessy/FacilitySignal",true))}})();
