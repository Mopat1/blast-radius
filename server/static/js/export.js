/* PNG / SVG export. */
import { $, cssVar, download, toast } from './utils.js';
import * as graph from './graph.js';

export function init(){
  $('exportPng').onclick = ()=>{
    const cy = graph.getCy();
    if(!cy) return;
    download('blastradius.png', cy.png({full:true, scale:2, bg:cssVar('--ink')}));
  };
  $('exportSvg').onclick = ()=>{
    const cy = graph.getCy();
    if(!cy || !cy.svg){ toast('SVG export library not loaded'); return; }
    const blob = new Blob([cy.svg({full:true, scale:1, bg:cssVar('--ink')})], {type:'image/svg+xml'});
    const url = URL.createObjectURL(blob);
    download('blastradius.svg', url);
    setTimeout(()=>URL.revokeObjectURL(url), 5000);
  };
  document.addEventListener('br:libs', ()=>{
    if(graph.libs.svg) $('exportSvg').style.display='';
  });
  if(graph.libs.svg) $('exportSvg').style.display='';
}
