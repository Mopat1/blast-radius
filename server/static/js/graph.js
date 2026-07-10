/* Cytoscape renderer — Obsidian-inspired presentation:
   - labels fade in progressively as you zoom (no text soup at overview)
   - hovering a node highlights its neighborhood and fades the rest
   - sparse aesthetic: small dots, thin faint edges
   Nothing authentication-related lives here. */
import { $, cssVar, toast, tryAny } from './utils.js';

/* ---------------- view settings (Obsidian-style display sliders) ------ */
import { store } from './utils.js';
const S_DEFAULT = { nodeScale:1, edgeOpacity:.4, labelDensity:1, spacing:1 };
let SETTINGS = {...S_DEFAULT};
try{ SETTINGS = {...S_DEFAULT, ...(JSON.parse(store.get('br_view')||'{}'))}; }catch(e){}
function saveSettings(){ store.set('br_view', JSON.stringify(SETTINGS)); }

/* ---------------- library loading (async, never blocks login) -------- */
let LIBS_READY=false, HAS_FCOSE=false, HAS_SVG=false, pendingRender=false;
export const libs = { get ready(){return LIBS_READY;}, get svg(){return HAS_SVG;} };

(async ()=>{
  const okCy = await tryAny([
    'https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.2/cytoscape.min.js',
    'https://cdn.jsdelivr.net/npm/cytoscape@3.30.2/dist/cytoscape.min.js',
    'https://unpkg.com/cytoscape@3.30.2/dist/cytoscape.min.js',
  ]);
  if(!okCy){ toast('Could not load graph library from any CDN — login still works, graph disabled.'); return; }
  HAS_FCOSE =
       await tryAny(['https://cdn.jsdelivr.net/npm/layout-base@2.0.1/layout-base.js','https://unpkg.com/layout-base@2.0.1/layout-base.js'])
    && await tryAny(['https://cdn.jsdelivr.net/npm/cose-base@2.2.0/cose-base.js','https://unpkg.com/cose-base@2.2.0/cose-base.js'])
    && await tryAny(['https://cdn.jsdelivr.net/npm/cytoscape-fcose@2.2.0/cytoscape-fcose.js','https://unpkg.com/cytoscape-fcose@2.2.0/cytoscape-fcose.js']);
  HAS_SVG = await tryAny([
    'https://cdn.jsdelivr.net/npm/cytoscape-svg@0.4.0/cytoscape-svg.js',
    'https://unpkg.com/cytoscape-svg@0.4.0/cytoscape-svg.js',
  ]);
  LIBS_READY = true;
  document.dispatchEvent(new Event('br:libs'));
  if(pendingRender){ pendingRender=false; render(); }
})();

/* ---------------- state ---------------------------------------------- */
let FULL=null, DEG={}, PKG={}, NODE={};
let expanded=new Set(), hiddenKinds=new Set();
let cy=null, pendingFocus=null, pendingPath=null;
let CALLADJ = {};   // src -> [dst] over CALLS edges, for path finding
let handlers={ onSymbolTap:null, onBackgroundTap:null };

export const node = id => NODE[id];
export const getCy = () => cy;
export const hidden = () => hiddenKinds;

export function symbolNodes(){ return FULL ? FULL.nodes.filter(n=>n.kind!=='module') : []; }
export function symbolCounts(){
  const c={}; symbolNodes().forEach(n=>c[n.kind]=(c[n.kind]||0)+1); return c;
}
export function fileCount(){
  return new Set(symbolNodes().map(n=>n.file).filter(Boolean)).size;
}
export function findSymbol(q){
  q=q.toLowerCase();
  return symbolNodes().find(n=>n.id.toLowerCase().includes(q));
}

const pkgOf = n => { const f=n.file||''; return f.includes('/') ? f.slice(0,f.lastIndexOf('/')) : '(root)'; };
const EDGE_KINDS = () => [...document.querySelectorAll('.kchip.on')].map(c=>c.dataset.kind);
const blastActive = () => cy && cy.$('.origin').length > 0;

/* ---------------- init ------------------------------------------------ */
export function init(h){
  handlers = {...handlers, ...h};
  $('limitSel').onchange = ()=>render();
  $('relayout').onclick = ()=>render();
  document.querySelectorAll('.kchip').forEach(c=>c.onclick=()=>{c.classList.toggle('on');render();});
  $('expandAll').onclick = ()=>{ if(FULL){ expanded = new Set(Object.values(PKG)); render(); } };
  $('collapseAll').onclick = ()=>{ if(FULL){ expanded = new Set(); render(); } };
  initMinimap();

  /* view settings popover */
  const pop = $('viewPop');
  $('viewBtn').onclick = () => { pop.hidden = !pop.hidden; };
  const bind = (id, key, onDone) => {
    const el = $(id);
    if(!el){ console.warn('view slider missing:', id); return; }
    el.value = SETTINGS[key];
    el.addEventListener('input', () => {
      SETTINGS[key] = parseFloat(el.value);
      saveSettings();
      onDone();
    });
  };
  bind('vNode',  'nodeScale',    () => restyle());
  bind('vEdge',  'edgeOpacity',  () => restyle());
  let spaceTimer = null;
  bind('vSpace', 'spacing', () => {          /* debounce: re-layout is heavy */
    clearTimeout(spaceTimer);
    spaceTimer = setTimeout(() => render(), 350);
  });
}

/* ---------------- open a repo ---------------------------------------- */
export function open(fullGraph, saved){
  FULL = fullGraph;
  DEG={}; PKG={}; NODE={};
  FULL.nodes.forEach(n=>{ NODE[n.id]=n; if(n.kind!=='module') PKG[n.id]=pkgOf(n); });
  CALLADJ = {};
  FULL.edges.forEach(e=>{
    if(['CALLS','EXPOSES','TESTS','INHERITS'].includes(e.kind)){
      DEG[e.src]=(DEG[e.src]||0)+1; DEG[e.dst]=(DEG[e.dst]||0)+1;
    }
    if(e.kind==='CALLS') (CALLADJ[e.src]=CALLADJ[e.src]||[]).push(e.dst);
  });
  if(saved){
    expanded = new Set(saved.expanded||[]);
    hiddenKinds = new Set(saved.hiddenKinds||[]);
    if(saved.limit!=null) $('limitSel').value = saved.limit;
  }else{
    expanded = symbolNodes().length<=300 ? new Set(Object.values(PKG)) : new Set();
    hiddenKinds = new Set();
  }
  render({preset: saved && saved.positions});
}

export function snapshot(){
  if(!cy) return null;
  const positions={};
  cy.nodes().forEach(n=>{const p=n.position();positions[n.id()]={x:Math.round(p.x),y:Math.round(p.y)};});
  return { positions, expanded:[...expanded], hiddenKinds:[...hiddenKinds], limit:$('limitSel').value };
}

export function toggleKind(k){
  hiddenKinds.has(k) ? hiddenKinds.delete(k) : hiddenKinds.add(k);
  render();
}

/* ---------------- elements ------------------------------------------- */
function buildElements(){
  const kinds = EDGE_KINDS();
  const limit = parseInt($('limitSel').value,10);

  const els=[], visibleSym=new Set(), pkgCount={};

  symbolNodes().forEach(n=>{
    if(hiddenKinds.has(n.kind)) return;
    const p = PKG[n.id];
    if(!expanded.has(p)) pkgCount[p]=(pkgCount[p]||0)+1;
  });

  let syms = symbolNodes().filter(n=>!hiddenKinds.has(n.kind) && expanded.has(PKG[n.id]));
  if(limit>0 && syms.length>limit)
    syms = [...syms].sort((a,b)=>(DEG[b.id]||0)-(DEG[a.id]||0)).slice(0,limit);

  syms.forEach(n=>{
    visibleSym.add(n.id);
    els.push({data:{id:n.id, label:n.name, kind:n.kind, file:n.file, line:n.line,
                    pkg:PKG[n.id], deg:Math.min(DEG[n.id]||0,60)}});
  });
  Object.entries(pkgCount).forEach(([p,c])=>{
    els.push({data:{id:'pkg:'+p, label:p+'\n('+c+')', kind:'package', pkg:p,
                    deg:Math.min(14+c/4,60)}});
  });

  const rep = id => {
    if(visibleSym.has(id)) return id;
    const p = PKG[id];
    if(p!==undefined && !expanded.has(p) && pkgCount[p]) return 'pkg:'+p;
    return null;
  };
  const agg={};
  FULL.edges.forEach(e=>{
    if(!kinds.includes(e.kind)) return;
    const a=rep(e.src), b=rep(e.dst);
    if(!a || !b || a===b) return;
    const k=a+'|'+b+'|'+e.kind;
    agg[k]=agg[k]||{source:a,target:b,kind:e.kind,w:0};
    agg[k].w++;
  });
  Object.values(agg).forEach((e,i)=>els.push({data:{id:'e'+i, ...e}}));
  return els;
}

/* ---------------- style (Obsidian-inspired) --------------------------- */
const KIND_COLOR = () => ({
  function:cssVar('--safe'), method:cssVar('--safe'), 'class':cssVar('--class'),
  test:cssVar('--ok'), api_endpoint:cssVar('--warn'), package:cssVar('--pkg'),
});
export function kindColors(){ return KIND_COLOR(); }

function buildStyle(n=0){
  const C = KIND_COLOR();
  const edgeOp = SETTINGS.edgeOpacity * (n>900 ? .55 : n>400 ? .75 : 1);
  return [
    /* small dots; labels hidden by default and revealed by zoom tier / hover */
    {selector:'node', style:{
      'background-color':C.function,'width':`mapData(deg,0,60,${9*SETTINGS.nodeScale},${30*SETTINGS.nodeScale})`,'height':`mapData(deg,0,60,${9*SETTINGS.nodeScale},${30*SETTINGS.nodeScale})`,
      'label':'data(label)','color':cssVar('--muted'),'font-family':'IBM Plex Mono',
      'font-size':10,'text-opacity':0,
      'text-valign':'bottom','text-margin-y':4,'border-width':0
    }},
    {selector:'node[kind="class"]',        style:{'background-color':C['class']}},
    {selector:'node[kind="test"]',         style:{'background-color':C.test}},
    {selector:'node[kind="api_endpoint"]', style:{'background-color':C.api_endpoint,'shape':'round-rectangle'}},
    {selector:'node[kind="package"]',      style:{
      'background-color':C.package,'shape':'round-rectangle',
      'border-width':1.5,'border-color':cssVar('--safe'),'border-style':'dashed',
      'label':'data(label)','text-wrap':'wrap','text-max-width':110,
      'text-valign':'center','text-halign':'center',
      'color':cssVar('--text'),'font-size':10,'text-opacity':1,
      'width':'mapData(deg,0,60,60,130)','height':'mapData(deg,0,60,44,90)'
    }},
    /* thin, faint edges — structure without noise */
    {selector:'edge', style:{
      'curve-style':'haystack','haystack-radius':0,
      'line-color':cssVar('--line'),'width':'mapData(w,1,20,0.8,3)','opacity':edgeOp
    }},
    /* hover neighborhood */
    {selector:'.faded',    style:{'opacity':.08}},
    {selector:'node.hoverlbl', style:{'text-opacity':1,'color':cssVar('--text')}},
    {selector:'edge.hovered',  style:{'opacity':.9,'line-color':cssVar('--safe')}},
    /* blast radius */
    {selector:'.impacted', style:{'background-color':cssVar('--blast'),'color':cssVar('--text'),'z-index':9}},
    {selector:'node.origin', style:{'background-color':cssVar('--blast'),'border-width':3,'border-color':cssVar('--text'),'border-style':'solid','z-index':10,'text-opacity':1,'color':cssVar('--text')}},
    {selector:'edge.impacted', style:{'line-color':cssVar('--blast'),'width':2.5,'opacity':1,'z-index':9}},
    {selector:'.dim', style:{'opacity':.15}},
    {selector:'node.path', style:{'border-width':3,'border-color':cssVar('--warn'),
      'border-style':'solid','opacity':1,'z-index':12,'color':cssVar('--text'),'text-opacity':1}},
    {selector:'edge.pathedge', style:{'line-color':cssVar('--warn'),'width':3,'opacity':1,'z-index':12}},
  ];
}
export function restyle(){ if(cy){ cy.style(buildStyle(cy.elements().length)); updateMinimapImage(); } }

/* Labels are shown ONLY on hover or when part of a blast selection.
   (Zoom-tier labels produced text soup on large repos — removed.) */
let lblRaf=0;
function scheduleLabels(){
  if(lblRaf) return;
  lblRaf = requestAnimationFrame(()=>{ lblRaf=0; drawMinimap(); });
}

/* ---------------- layout + render ------------------------------------ */
const FCOSE = (n, extra={}) => ({
  name:'fcose', quality:n>800?'draft':'default',
  animate:true, animationDuration:700,
  nodeDimensionsIncludeLabels:false,   /* labels are opacity-managed now, not layout-reserved */
  nodeRepulsion:5500*SETTINGS.spacing*(1+Math.min(1,Math.max(0,n-300)/900)),
  idealEdgeLength:80*SETTINGS.spacing*(1+Math.min(.8,Math.max(0,n-300)/1100)),
  numIter:n>800?800:2500,
  packComponents:true, randomize:true, ...extra,
});
function layoutFor(n){
  if(HAS_FCOSE) return FCOSE(n);
  return n>600 ? {name:'concentric', concentric:x=>x.data('deg'), levelWidth:()=>8, animate:true, animationDuration:600}
               : {name:'cose', animate:true, numIter:600};
}

export function render(opts={}){
  if(!FULL) return;
  if(!LIBS_READY || typeof cytoscape === 'undefined'){
    pendingRender = true;
    $('loadOverlay').style.display='flex';
    $('loadOverlay').textContent='loading graph library…';
    return;
  }
  $('loadOverlay').textContent='computing layout…';
  $('loadOverlay').style.display='flex';
  document.dispatchEvent(new Event('br:render'));

  const els = buildElements();
  if(cy) cy.destroy();
  cy = cytoscape({
    container: $('cy'),
    elements: els,
    style: buildStyle(els.length),
    textureOnViewport: els.length>2500,   /* full-res rendering; texture only on huge graphs */
    hideEdgesOnViewport: els.length>1500,
    motionBlur:false,
    pixelRatio: 'auto',                    /* crisp on retina — never downsample */
    wheelSensitivity:1.2,                 /* fast, responsive zoom */
    minZoom:.05, maxZoom:6,
  });

  $('gstats').textContent =
    `${cy.nodes().length} nodes · ${cy.edges().length} edges shown (of ${FULL.nodes.length}/${FULL.edges.length})`;

  let layout;
  const saved = opts.preset;
  if(saved && cy.nodes().filter(n=>saved[n.id()]).length >= cy.nodes().length*0.5){
    cy.nodes().forEach(n=>{
      n.position(saved[n.id()] || {x:(Math.random()-.5)*200, y:(Math.random()-.5)*200});
    });
    layout = cy.layout({name:'preset', animate:false});
  }else{
    try{ layout = cy.layout(layoutFor(cy.nodes().length)); }
    catch(e){ layout = cy.layout({name:'concentric', concentric:x=>x.data('deg'), levelWidth:()=>8, animate:false}); }
  }
  layout.on('layoutstop', ()=>{
    $('loadOverlay').style.display='none';
    if(opts.focusPkg){
      const sel = cy.nodes(`[pkg = "${opts.focusPkg}"]`);
      if(sel.length) cy.animate({fit:{eles:sel, padding:80}, duration:300});
    } else cy.fit(undefined, 40);
    updateMinimapImage();
    if(pendingFocus){ const id=pendingFocus; pendingFocus=null; focusSymbol(id); }
    if(pendingPath){ const p=pendingPath; pendingPath=null; applyPath(p); }
  });
  layout.run();

  /* ---- interactions ---- */
  cy.on('tap','node', evt=>{
    const n = evt.target;
    if(n.data('kind')==='package'){
      expanded.add(n.data('pkg'));
      render({focusPkg:n.data('pkg')});
      return;
    }
    handlers.onSymbolTap && handlers.onSymbolTap(n.id());
  });
  cy.on('tap', evt=>{
    if(evt.target===cy) handlers.onBackgroundTap && handlers.onBackgroundTap();
  });

  /* Obsidian-style hover: highlight neighborhood, fade the rest (idle mode only) */
  cy.on('mouseover','node', e=>{
    if(blastActive()) return;
    const hood = e.target.closedNeighborhood();
    cy.elements().not(hood).addClass('faded');
    const fs = Math.max(10, Math.min(26, 12/cy.zoom()));   /* readable at any zoom */
    hood.nodes().addClass('hoverlbl').style('font-size', fs);
    e.target.style('font-size', fs*1.15);
    hood.edges().addClass('hovered');
  });
  cy.on('mouseout','node', ()=>{
    if(blastActive()) return;
    cy.nodes('.hoverlbl').removeStyle('font-size');
    cy.elements().removeClass('faded hoverlbl hovered');
  });

  /* spring physics on drag release */
  cy.on('dragfree','node', ()=>{
    if(HAS_FCOSE && cy.nodes().length<=800){
      cy.layout(FCOSE(cy.nodes().length,
        {randomize:false, numIter:250, animationDuration:450, fit:false})).run();
    }
    updateMinimapImage();
  });

  cy.on('zoom', scheduleLabels);
  cy.on('pan',  ()=>throttleDrawMinimap());
}

/* ---------------- focus / visibility --------------------------------- */
export function focusSymbol(id){
  if(!FULL || !NODE[id]) return;
  const p = PKG[id];
  if(p!==undefined && !expanded.has(p)){
    expanded.add(p);
    pendingFocus = id;
    render();
    return;
  }
  let n = cy.getElementById(id);
  if(n.empty()){ ensureVisible([id]); n = cy.getElementById(id); }
  if(n.length){
    cy.animate({fit:{eles:n.closedNeighborhood(), padding:80}, duration:300});
    handlers.onSymbolTap && handlers.onSymbolTap(id);
  }
}

export function ensureVisible(ids){
  if(!cy) return;
  const missing = ids.filter(id=>NODE[id] && cy.getElementById(id).empty() && expanded.has(PKG[id]));
  if(!missing.length) return;
  cy.add(missing.map(id=>{
    const n=NODE[id];
    return {data:{id:n.id,label:n.name,kind:n.kind,file:n.file,line:n.line,
                  pkg:PKG[id],deg:Math.min(DEG[id]||0,60)}};
  }));
  const visible = new Set(cy.nodes().map(n=>n.id()));
  const kinds = EDGE_KINDS();
  const eAdds=[];
  FULL.edges.forEach((e,i)=>{
    if(kinds.includes(e.kind) && visible.has(e.src) && visible.has(e.dst) && cy.getElementById('x'+i).empty())
      eAdds.push({data:{id:'x'+i, source:e.src, target:e.dst, kind:e.kind, w:1}});
  });
  cy.add(eAdds);
  cy.nodes().filter(n=>missing.includes(n.id())).forEach(n=>{
    const nb=n.neighborhood('node');
    if(nb.length){
      const p=nb[0].position();
      n.position({x:p.x+(Math.random()*80-40), y:p.y+(Math.random()*80-40)});
    }
  });
}

export function visibleElementFor(id){
  if(!cy) return null;
  let el = cy.getElementById(id);
  if(el.empty() && PKG[id]!==undefined && !expanded.has(PKG[id]))
    el = cy.getElementById('pkg:'+PKG[id]);
  return el.length ? el : null;
}

export function clearClasses(){
  if(cy) cy.elements().removeClass('impacted origin dim faded hoverlbl hovered path pathedge');
  throttleDrawMinimap();
}

/* ---------------- minimap -------------------------------------------- */
let mm, mmx, mmImg=null, mmBB=null, mmRaf=0;
function initMinimap(){
  mm = $('minimap'); mmx = mm.getContext('2d');
  mm.onclick = e=>{
    if(!cy || !mmBB || !mmImg) return;
    const r=mm.getBoundingClientRect(), W=mm.width, H=mm.height;
    const s=Math.min(W/mmImg.width, H/mmImg.height);
    const iw=mmImg.width*s, ih=mmImg.height*s, ox=(W-iw)/2, oy=(H-ih)/2;
    const px=(e.clientX-r.left-ox)/iw, py=(e.clientY-r.top-oy)/ih;
    const mxp=mmBB.x1+px*mmBB.w, myp=mmBB.y1+py*mmBB.h;
    const z=cy.zoom();
    cy.animate({pan:{x:cy.width()/2-mxp*z, y:cy.height()/2-myp*z}, duration:200});
  };
}
export function updateMinimapImage(){
  if(!cy || cy.nodes().empty()){ if(mm) mm.style.display='none'; return; }
  mm.style.display='block';
  mmBB = cy.elements().boundingBox();
  const png = cy.png({full:true, scale:Math.min(1, 400/Math.max(mmBB.w,1)), bg:cssVar('--panel2')});
  mmImg = new Image();
  mmImg.onload = drawMinimap;
  mmImg.src = png;
}
function drawMinimap(){
  if(!mmImg || !mmBB || !cy) return;
  const W=mm.width, H=mm.height;
  mmx.clearRect(0,0,W,H);
  const s=Math.min(W/mmImg.width, H/mmImg.height);
  const iw=mmImg.width*s, ih=mmImg.height*s, ox=(W-iw)/2, oy=(H-ih)/2;
  mmx.drawImage(mmImg, ox, oy, iw, ih);
  const ext=cy.extent();
  const fx=x=>ox+((x-mmBB.x1)/Math.max(mmBB.w,1))*iw;
  const fy=y=>oy+((y-mmBB.y1)/Math.max(mmBB.h,1))*ih;
  mmx.strokeStyle=cssVar('--blast'); mmx.lineWidth=1.5;
  mmx.strokeRect(fx(ext.x1), fy(ext.y1), fx(ext.x2)-fx(ext.x1), fy(ext.y2)-fy(ext.y1));
}
function throttleDrawMinimap(){
  if(mmRaf) return;
  mmRaf = requestAnimationFrame(()=>{ mmRaf=0; drawMinimap(); });
}


/* ---------------- call-path explainer ----------------
   Why does changing `target` affect `caller`? Shortest CALLS chain:
   caller -> ... -> target. Computed client-side from the full IR. */
export function findCallPath(fromId, toId){
  if(fromId===toId) return [fromId];
  const prev = {[fromId]: null};
  let frontier = [fromId];
  while(frontier.length){
    const nxt = [];
    for(const cur of frontier){
      for(const n of (CALLADJ[cur]||[])){
        if(!(n in prev)){
          prev[n] = cur;
          if(n===toId){
            const path=[toId]; let p=cur;
            while(p!==null){ path.push(p); p=prev[p]; }
            return path.reverse();
          }
          nxt.push(n);
        }
      }
    }
    frontier = nxt;
  }
  return null;
}

export function showCallPath(pathIds){
  if(!cy || !pathIds || pathIds.length<2) return;
  const need = pathIds.filter(id=>PKG[id]!==undefined && !expanded.has(PKG[id]));
  if(need.length){
    need.forEach(id=>expanded.add(PKG[id]));
    pendingPath = pathIds;
    render();
    return;
  }
  applyPath(pathIds);
}

function applyPath(pathIds){
  ensureVisible(pathIds);
  cy.elements().removeClass('path pathedge');
  const els = pathIds.map(id=>cy.getElementById(id)).filter(e=>e.length);
  els.forEach(e=>e.addClass('path'));
  for(let i=0;i<pathIds.length-1;i++){
    const a=pathIds[i], b=pathIds[i+1];
    cy.edges().filter(e =>
      (e.source().id()===a && e.target().id()===b) ||
      (e.source().id()===b && e.target().id()===a)
    ).addClass('pathedge');
  }
  if(els.length){
    const coll = cy.collection(); els.forEach(e=>coll.merge(e));
    cy.animate({fit:{eles:coll, padding:90}, duration:350});
  }
  updateMinimapImage();
}
