/* Repository list, add form, per-repo actions, and status polling. */
import { $, toast } from './utils.js';
import { ReposAPI } from './api.js';

let poll = null, currentRepo = null, onOpen = null;

export function current(){ return currentRepo; }

export function init(openCb){
  onOpen = openCb;
  $('rAdd').onclick = add;
  load();
  if(poll) clearInterval(poll);
  poll = setInterval(load, 3000);
}

async function add(){
  try{
    await ReposAPI.add($('rName').value, $('rSource').value);
    $('rName').value=''; $('rSource').value='';
    load();
  }catch(e){ toast(e.message); }
}

async function load(){
  let repos;
  try{ repos = await ReposAPI.list(); }catch(e){ return; }
  const box = $('repoList');
  box.innerHTML = '';
  if(!repos.length){
    box.innerHTML = '<p class="hintp">No repositories yet — add one below.</p>';
    return;
  }
  repos.forEach(r => {
    const div = document.createElement('div');
    div.className = 'repo' + (currentRepo===r.id ? ' active' : '');
    div.innerHTML = `
      <div class="name">${r.name}
        <span style="display:flex;gap:8px;align-items:center">
          <span class="acts">
            <span data-act="re" title="re-analyze">⟳</span>
            <span data-act="del" title="delete">✕</span>
          </span>
          <span class="dot ${r.status}"></span>
        </span>
      </div>
      <div class="meta mono">${r.status==='ready' ? r.n_nodes+' nodes · '+r.n_edges+' edges' : r.status}${r.error?' — '+r.error:''}</div>`;

    div.addEventListener('click', () => {
      currentRepo = r.id;
      load();
      if(r.status==='ready' && onOpen) onOpen(r.id);
    });
    div.querySelector('[data-act="re"]').addEventListener('click', async e=>{
      e.stopPropagation();
      try{ await ReposAPI.analyze(r.id); toast(`Re-analyzing “${r.name}”…`); load(); }
      catch(err){ toast(err.message); }
    });
    div.querySelector('[data-act="del"]').addEventListener('click', async e=>{
      e.stopPropagation();
      if(!confirm(`Delete repository “${r.name}”? This cannot be undone.`)) return;
      try{
        await ReposAPI.remove(r.id);
        if(currentRepo===r.id) currentRepo=null;
        load();
      }catch(err){ toast(err.message); }
    });
    box.appendChild(div);
  });
}
