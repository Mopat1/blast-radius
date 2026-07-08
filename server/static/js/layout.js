/* Saved layouts: stored on your account (server), with localStorage fallback. */
import { $, store, toast } from './utils.js';
import { ReposAPI } from './api.js';
import * as graph from './graph.js';
import * as repos from './repos.js';

const key = id => 'br_layout_' + id;

export function init(){
  $('saveLayout').onclick = save;
}

export async function load(repoId){
  try{
    const d = await ReposAPI.getLayout(repoId);
    if(d && d.layout && d.layout.positions) return d.layout;
  }catch(e){ /* fall back to this browser */ }
  try{ return JSON.parse(store.get(key(repoId))||'null'); }catch(e){ return null; }
}

async function save(){
  const id = repos.current();
  const snap = graph.snapshot();
  if(!id || !snap) return;
  store.set(key(id), JSON.stringify(snap));            // local fallback always
  try{
    await ReposAPI.putLayout(id, snap);
    toast('Layout saved to your account.');
  }catch(e){
    toast('Saved in this browser only (server: ' + e.message + ')');
  }
}

export function clear(repoId){ store.del(key(repoId)); }
