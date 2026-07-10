/* Blast radius: compute impact, highlight, details panel. */
import { $ } from './utils.js';
import { ReposAPI } from './api.js';
import * as graph from './graph.js';
import * as repos from './repos.js';
import { restoreOverview, setClearVisible, showModal, setModalBody, closeModal } from './ui.js';
import { toast, renderAiNote, download } from './utils.js';

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
  history.replaceState(null, '', location.pathname);
  lastTarget = null;
  graph.clearClasses();
  setClearVisible(false);
  restoreOverview();
}

let lastTarget = null;

function showPath(fromId){
  if(!lastTarget) return;
  const path = graph.findCallPath(fromId, lastTarget);
  if(!path){ graph.focusSymbol(fromId); return; }
  graph.showCallPath(path);
  const box = document.getElementById('pathBox');
  if(box){
    box.innerHTML = '<div class="t">call chain — why this is affected</div>' +
      '<div class="chain">' + path.map((id,i)=>
        '<span class="hop mono" data-i="'+i+'">'+id.split('.').slice(-2).join('.')+'</span>'
      ).join('<span class="arrow">→</span>') + '</div>';
    box.querySelectorAll('.hop').forEach((el,i)=>{
      el.title = path[i];
      el.addEventListener('click', ()=>graph.focusSymbol(path[i]));
    });
    box.style.display = 'block';
  }
}

function section(title, items, opts={}){
  const wrap = document.createElement('div'); wrap.className='sect';
  wrap.innerHTML = `<div class="t">${title} (${items.length})</div>`;
  const ul = document.createElement('ul');
  if(!items.length){
    ul.innerHTML = '<li class="flat">—</li>';
  } else items.forEach(x=>{
    const li = document.createElement('li');
    li.textContent = x;
    if(opts.path && graph.node(x)) li.addEventListener('click', ()=>showPath(x));
    else if(graph.node(x)) li.addEventListener('click', ()=>graph.focusSymbol(x));
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
    <div style="display:flex;gap:8px;margin-top:12px;flex-wrap:wrap">
      <button class="b-mini" id="aiBtn"
              data-tip="AI reviewer note in a focused view. Uses the graph, not your raw code.">✨ explain</button>
      <button class="b-mini" id="mdBtn"
              data-tip="Download this impact report as Markdown.">📄 report</button>
    </div>`;
  box.appendChild(head);
  history.replaceState(null, '', '#r=' + repos.current() + '&t=' + encodeURIComponent(d.target));
  head.querySelector('#mdBtn').addEventListener('click', ()=>downloadReport(d));
  head.querySelector('#aiBtn').addEventListener('click', ()=>openAiModal(d));
  lastTarget = d.target;
  const pathBox = document.createElement('div');
  pathBox.id = 'pathBox'; pathBox.className = 'sect'; pathBox.style.display = 'none';
  box.appendChild(pathBox);
  box.appendChild(section('affected functions — click for call chain', d.affected_functions, {path:true}));
  box.appendChild(section('affected endpoints', d.affected_endpoints));
  box.appendChild(section('tests to run', d.affected_tests));
  box.appendChild(section('affected files', d.affected_files));
  if(d.coupled_files && d.coupled_files.length){
    const s = section('hidden dependencies — co-change from git history', d.coupled_files);
    s.title = 'These files historically change together with this code, but are outside its static blast radius.';
    box.appendChild(s);
  }
}


/* ---------------- AI modal ---------------- */
async function openAiModal(d){
  showModal({
    title: d.target,
    badge: `${d.risk_score} ${d.risk_level}`,
    badgeClass: d.risk_level,
    html: '<div class="ai-loading"><span class="spin"></span> Asking the reviewer…</div>',
    actions: [
      {label:'copy', onClick: el=>{
        const t = el.querySelector('.modal-body').innerText;
        navigator.clipboard.writeText(t).then(()=>toast('Copied.'));
      }},
      {label:'close', onClick: ()=>closeModal()},
    ],
  });
  try{
    const res = await ReposAPI.explain(repos.current(), d.target);
    setModalBody(renderAiNote(res.explanation));
  }catch(e){
    setModalBody('<div class="ai-p" style="color:var(--blast)">' + e.message + '</div>');
  }
}

/* ---------------- markdown report ---------------- */
function downloadReport(d){
  const li = a => a.length ? a.map(x=>'- `'+x+'`').join('\n') : '- —';
  const md = [
    '# BlastRadius impact report', '',
    '**Target:** `' + d.target + '`', '',
    '**Risk:** ' + d.risk_score + ' (' + d.risk_level + ') · call depth ' + d.call_depth, '',
    '## Affected functions (' + d.affected_functions.length + ')', li(d.affected_functions), '',
    '## Affected endpoints (' + d.affected_endpoints.length + ')', li(d.affected_endpoints), '',
    '## Tests to run (' + d.affected_tests.length + ')', li(d.affected_tests), '',
    '## Affected files (' + d.affected_files.length + ')', li(d.affected_files), '',
    (d.coupled_files && d.coupled_files.length
      ? '## Hidden dependencies (git co-change)\n' + li(d.coupled_files) + '\n' : ''),
    '_Generated by BlastRadius_',
  ].join('\n');
  const url = URL.createObjectURL(new Blob([md], {type:'text/markdown'}));
  download(d.target.replace(/[^a-z0-9_.-]/gi,'_') + '-impact.md', url);
  setTimeout(()=>URL.revokeObjectURL(url), 5000);
}
