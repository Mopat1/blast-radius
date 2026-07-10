/* Entry point: coordinates all modules. */
import { $, toast, APP_VERSION } from './utils.js';
import { ReposAPI } from './api.js';
import * as auth from './auth.js';
import * as repos from './repos.js';
import * as graph from './graph.js';
import * as blast from './blast.js';
import * as ui from './ui.js';
import * as search from './search.js';
import * as exporter from './export.js';
import * as theme from './theme.js';
import * as layouts from './layout.js';
import * as hero from './hero.js';

/* deep links: #r=<repoId>&t=<target> restores a shared blast radius */
function parseHash(){
  const m = location.hash.match(/#r=(\d+)(?:&t=([^&]+))?/);
  return m ? {r: +m[1], t: m[2] ? decodeURIComponent(m[2]) : null} : null;
}
const pendingLink = parseHash();

async function openRepo(id){
  let full;
  try{ full = await ReposAPI.graph(id); }catch(e){ return; }
  graph.open(full, await layouts.load(id));
  $('empty').style.display='none';
  ui.overviewLoading();
  ui.setClearVisible(false);
  if(pendingLink && pendingLink.r === id && pendingLink.t){
    const t = pendingLink.t; pendingLink.t = null;
    setTimeout(()=>graph.focusSymbol(t), 900);   // after first layout settles
  }
  ReposAPI.hotspots(id)
    .then(h => ui.showOverview({counts:graph.symbolCounts(), files:graph.fileCount(), hotspots:h.hotspots}))
    .catch(() => ui.showOverview({counts:graph.symbolCounts(), files:graph.fileCount(), hotspots:[]}));
}

/* Each module boots independently: a failure in one (e.g. a stale cached
   file after a deploy) must never take down login or the rest of the app. */
function safe(name, fn){
  try{ fn(); }
  catch(e){ console.error(name+'.init failed:', e); toast(name+' failed to start — try a hard refresh (Cmd+Shift+R)'); }
}

window.addEventListener('DOMContentLoaded', ()=>{
  console.log('BlastRadius frontend v' + APP_VERSION);
  document.querySelectorAll('.ver').forEach(el => el.textContent = 'frontend v' + APP_VERSION);
  safe('auth',   ()=>auth.init(()=>repos.init(openRepo, pendingLink && pendingLink.r)));   // login first, always
  safe('theme',  ()=>theme.init(()=>graph.restyle()));
  safe('ui',     ()=>ui.init());
  safe('graph',  ()=>graph.init({ onSymbolTap: blast.detonate, onBackgroundTap: blast.clear }));
  safe('search', ()=>search.init());
  safe('export', ()=>exporter.init());
  safe('layout', ()=>layouts.init());
  safe('hero',   ()=>hero.init());
  document.addEventListener('br:clear', blast.clear);
  document.addEventListener('keydown', e=>{ if(e.key==='Escape') blast.clear(); });
});
