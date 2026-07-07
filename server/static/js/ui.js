/* Pure DOM helpers: sidebar, legend, details panel, overview. */
import { $, store, cssVar } from './utils.js';
import * as graph from './graph.js';

let lastOverviewHTML = null, jumpIds = [];

export function init(){
  /* sidebar collapse */
  const apply = on => {
    document.body.classList.toggle('nosb', on);
    $('sbToggle').textContent = on ? '☰' : '◀';
    store.set('br_sb', on ? '1' : '0');
    window.dispatchEvent(new Event('resize'));
  };
  $('sbToggle').onclick = () => apply(!document.body.classList.contains('nosb'));
  if(store.get('br_sb')==='1') apply(true);

  /* redraw legend on every graph render */
  document.addEventListener('br:render', drawLegend);

  $('clearBtn').onclick = () => document.dispatchEvent(new Event('br:clear'));
}

export function setClearVisible(v){ $('clearBtn').style.display = v ? 'inline' : 'none'; }

export function drawLegend(){
  const counts = graph.symbolCounts();
  if(!Object.keys(counts).length){ $('legend').innerHTML=''; return; }
  const C = graph.kindColors();
  const label = {function:'function', method:'method', 'class':'class', test:'test', api_endpoint:'endpoint'};
  const box = $('legend'); box.innerHTML='';
  Object.entries(label).forEach(([k,name])=>{
    if(!counts[k]) return;
    const chip = document.createElement('span');
    chip.className = 'lchip' + (graph.hidden().has(k) ? ' off' : '');
    chip.innerHTML = `<i style="background:${C[k]}"></i>${name} ${counts[k]}`;
    chip.addEventListener('click', ()=>graph.toggleKind(k));
    box.appendChild(chip);
  });
  const pk = document.createElement('span');
  pk.className='lchip static';
  pk.innerHTML = `<i style="background:${cssVar('--pkg')}"></i>package`;
  box.appendChild(pk);
  const im = document.createElement('span');
  im.className='lchip static';
  im.innerHTML = `<i style="background:${cssVar('--blast')}"></i>impacted`;
  box.appendChild(im);
}

export function showOverview({counts, files, hotspots}){
  const total = Object.values(counts).reduce((a,b)=>a+b,0);
  const card = (v,l)=>`<div class="ovcard"><b>${v}</b><span>${l}</span></div>`;
  let html = `<div class="ovcards">
    ${card(total,'symbols')}${card(files,'files')}
    ${card(counts.test||0,'tests')}${card(counts.api_endpoint||0,'endpoints')}
  </div>`;
  if(hotspots && hotspots.length){
    html += `<div class="sect hot"><div class="t">top hotspots — riskiest functions</div><ul>` +
      hotspots.map((h,i)=>`<li data-jump="${i}"><b>${h.risk}</b>${h.id}</li>`).join('') + `</ul></div>`;
    jumpIds = hotspots.map(h=>h.id);
  } else jumpIds = [];
  html += `<p class="hintp" style="margin-top:14px">Click a <b>package</b> to expand it. Click a <b>symbol</b> to detonate its blast radius. Click the background or press <b>Esc</b> to reset.</p>`;
  lastOverviewHTML = html;
  paintOverview();
}

function paintOverview(){
  if(!lastOverviewHTML) return;
  $('report').innerHTML = lastOverviewHTML;
  document.querySelectorAll('#report [data-jump]').forEach(li=>{
    li.addEventListener('click', ()=>graph.focusSymbol(jumpIds[+li.dataset.jump]));
  });
}
export function restoreOverview(){ paintOverview(); }
export function overviewLoading(){
  $('report').innerHTML = '<p class="hintp">Loading repository overview…</p>';
}
