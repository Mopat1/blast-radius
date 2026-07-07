/* Node search with auto-focus. */
import { $, toast } from './utils.js';
import * as graph from './graph.js';

export function init(){
  $('searchBox').addEventListener('keydown', e=>{
    if(e.key!=='Enter') return;
    const q = e.target.value.trim();
    if(!q) return;
    const hit = graph.findSymbol(q);
    if(!hit){ toast(`No symbol matching “${q}”`); return; }
    graph.focusSymbol(hit.id);
  });
}
