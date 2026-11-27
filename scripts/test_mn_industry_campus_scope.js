// From the repository root: node scripts/test_mn_industry_campus_scope.js
// Render-function contract using a minimal DOM stub; not a browser visual gate.
const fs=require('fs'),vm=require('vm'),assert=require('assert').strict;
const js=fs.readFileSync("web/pages.js","utf8");
const start=js.indexOf("function industryResearch("), end=js.indexOf("\nconst marketGeometryUrl",start);
const el=(tag,text,cls)=>({tag,text,cls,children:[],append(...c){this.children.push(...c)},addEventListener(){}});
const anchor=(text,href,external=false)=>({tag:"a",text,href,external,children:[]});
const route=(route,param)=>"#"+route+(param?"?"+new URLSearchParams(param):"");
const add=(n,...c)=>(n.append(...c),n),flat=n=>[n,...n.children.flatMap(flat)];
function render(state) {
 const app=el("main");
 const env={app,el,anchor,route,add,title(){},options(){return el("select")},states:["MN","NY"],p:{state}};
 vm.runInNewContext(js.slice(start,end)+"\nindustryResearch(p)",env);
 return flat(app);
}
const mn=render("MN"), panel=mn.find(n=>n.tag==="section"&&n.children[0]?.text==="Minnesota boiler registration research"), all=flat(panel);
assert(all.some(n=>n.text==="CMS provider records are not a full list of physical campuses. Some Minnesota hospitals stop reporting independently while continuing to operate as offsite campuses. A certificate for one address does not verify equipment at another campus."));
assert(all.some(n=>n.text?.includes("Equipment is not linked")));
const links=all.filter(n=>n.tag==="a");
assert.equal(links.length,3);
for(const [i,source] of ["hospital","nursing"].entries()){
  const h=new URL(links[i].href,"https://placeholder.example").hash;
  assert.equal(h,`#advanced?source=${source}&state=MN&run=1`);
  assert.equal(links[i].external,false);
}
assert.equal(links[2].external,true);
assert(links[2].href.startsWith("https://dli.mn.gov/"));
for(const state of ["","NY","invalid"]) assert(!render(state).some(n=>n.text?.includes("physical campuses")));
console.log("MN_ONLY_INDUSTRY_ROUTE_CONTRACT_PASS");
