/* Blast radius: compute impact, highlight, details panel. */
import { $ } from './utils.js';
import { ReposAPI } from './api.js';
import * as graph from './graph.js';
import * as repos from './repos.js';
import { restoreOverview, setClearVisible } from './ui.js';
import { toast } from './utils.js';

export async function detonate(id){
  const rid = repos.current();
  if(!rid) return;
  let d;
  try{ d = await ReposAPI.impact(rid, id); }catch(e){ return; }
  if(d.ambiguous) return;

  const blast = [d.target, ...d.affected_functions, ...d.affected_endpoints, ...d.affected_tests];
  graph.ensureVisible(blast);

  const cy = graph.getCy();
  cy.batch(()=>{
    cy.elements().removeClass('impacted origin dim');
    cy.elements().addClass('dim');
    const set = new Set();
    blast.forEach(bid=>{
      const el = graph.visibleElementFor(bid);
      if(el){
        el.removeClass('dim').addClass(bid===d.target ? 'origin' : 'impacted');
        set.add(el.id());
      }
    });
    cy.edges().forEach(e=>{
      if(set.has(e.source().id()) && set.has(e.target().id()))
        e.removeClass('dim').addClass('impacted');
    });
  });
  graph.updateMinimapImage();
  renderPanel(d);
  setClearVisible(true);
}

export function clear(){
  graph.clearClasses();
  setClearVisible(false);
  restoreOverview();
}

function section(title, items){
  const wrap = document.createElement('div'); wrap.className='sect';
  wrap.innerHTML = `<div class="t">${title} (${items.length})</div>`;
  const ul = document.createElement('ul');
  if(!items.length){
    ul.innerHTML = '<li class="flat">—</li>';
  } else items.forEach(x=>{
    const li = document.createElement('li');
    li.textContent = x;
    if(graph.node(x)) li.addEventListener('click', ()=>graph.focusSymbol(x));
    else li.classList.add('flat');
    ul.appendChild(li);
  });
  wrap.appendChild(ul);
  return wrap;
}

function renderPanel(d){
  const box = $('report');
  box.innerHTML = '';
  const src = graph.node(d.target);
  const head = document.createElement('div');
  head.innerHTML = `
    <div class="mono" style="font-size:.8rem;word-break:break-all">${d.target}</div>
    ${src ? `<div class="nodemeta">${src.kind} · ${src.file}:${src.line}</div>` : ''}
    <div class="risk ${d.risk_level}">${d.risk_score} <span style="font-size:.8rem">${d.risk_level}</span></div>
    <div class="mono" style="color:var(--muted);font-size:.75rem">call depth ${d.call_depth}</div>
    <button class="b-mini" id="aiBtn" style="margin-top:10px"
            data-tip="AI reviewer note: what could break and what to check. Uses the graph, not your raw code.">✨ explain this impact</button>
    <div id="aiOut"></div>`;
  box.appendChild(head);
  const btn = head.querySelector('#aiBtn');
  btn.addEventListener('click', async ()=>{
    const out = head.querySelector('#aiOut');
    btn.disabled = true; btn.textContent = 'thinking…';
    try{
      const rid = repos.current();
      const res = await ReposAPI.explain(rid, d.target);
      out.innerHTML = '';
      const s = document.createElement('div'); s.className = 'sect';
      s.innerHTML = '<div class="t">AI review note</div>';
      const p = document.createElement('p'); p.className = 'hintp';
      p.textContent = res.explanation;
      s.appendChild(p); out.appendChild(s);
      btn.remove();
    }catch(e){
      toast(e.message);
      btn.disabled = false; btn.textContent = '✨ explain this impact';
    }
  });
  box.appendChild(section('affected functions', d.affected_functions));
  box.appendChild(section('affected endpoints', d.affected_endpoints));
  box.appendChild(section('tests to run', d.affected_tests));
  box.appendChild(section('affected files', d.affected_files));
  if(d.coupled_files && d.coupled_files.length){
    const s = section('hidden dependencies — co-change from git history', d.coupled_files);
    s.title = 'These files historically change together with this code, but are outside its static blast radius.';
    box.appendChild(s);
  }
}
