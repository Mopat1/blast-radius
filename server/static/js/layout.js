/* Saved layouts (localStorage, per repo). */
import { $, store, toast } from './utils.js';
import * as graph from './graph.js';
import * as repos from './repos.js';

const key = id => 'br_layout_' + id;

export function init(){
  $('saveLayout').onclick = save;
}

export function load(repoId){
  try{ return JSON.parse(store.get(key(repoId))||'null'); }catch(e){ return null; }
}

function save(){
  const id = repos.current();
  const snap = graph.snapshot();
  if(!id || !snap) return;
  store.set(key(id), JSON.stringify(snap));
  toast('Layout saved for this repo (stored in this browser).');
}

export function clear(repoId){ store.del(key(repoId)); }
