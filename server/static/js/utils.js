export const APP_VERSION = '0.7.0';
/* Shared helpers: DOM, storage, colors, toast, downloads. */
export const $ = id => document.getElementById(id);
export const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

export const store = {
  get(k){ try{ return localStorage.getItem(k); }catch(e){ return null; } },
  set(k,v){ try{ localStorage.setItem(k,v); }catch(e){} },
  del(k){ try{ localStorage.removeItem(k); }catch(e){} },
};

export function toast(msg){
  let t = document.getElementById('toast');
  if(!t){ t = document.createElement('div'); t.id='toast'; document.body.appendChild(t); }
  t.textContent = msg;
  clearTimeout(t._h); t._h = setTimeout(()=>t.remove(), 8000);
}
window.addEventListener('error', e => toast('JS error: ' + (e.message||'unknown')));

export function download(name, href){
  const a=document.createElement('a'); a.href=href; a.download=name;
  document.body.appendChild(a); a.click(); a.remove();
}

export function loadScript(src){
  return new Promise(res=>{
    const s=document.createElement('script'); s.src=src;
    s.onload=()=>res(true); s.onerror=()=>res(false);
    document.head.appendChild(s);
  });
}
export async function tryAny(urls){ for(const u of urls){ if(await loadScript(u)) return true; } return false; }

/* ---- AI note rendering: escape, parse template sections, md-lite fallback ---- */
const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const strip = s => s.replace(/\*\*|__|###?\s?|```|`/g, '').trim();

export function renderAiNote(text){
  const t = strip(text);
  const heads = ['SUMMARY','RISK','TESTS FIRST','WATCH OUT'];
  const rx = new RegExp('^\\s*(' + heads.join('|') + ')\\s*:?\\s*$|^\\s*(' + heads.join('|') + ')\\s*:\\s*(.*)$', 'i');
  const sections = []; let cur = null;
  t.split(/\n/).forEach(line=>{
    const m = line.match(rx);
    if(m){
      const name = (m[1]||m[2]).toUpperCase();
      cur = {name, body:[]};
      sections.push(cur);
      if(m[3]) cur.body.push(m[3]);
    } else if(cur && line.trim()){
      cur.body.push(line.trim());
    }
  });
  if(sections.length < 2){                      // model ignored the template
    return '<div class="ai-p">' + t.split(/\n{2,}/).map(p=>esc(p)).join('</div><div class="ai-p">') + '</div>';
  }
  return sections.map(s=>{
    const items = s.body.filter(l=>/^[-•]/.test(l)).map(l=>esc(l.replace(/^[-•]\s*/,'')));
    const prose = s.body.filter(l=>!/^[-•]/.test(l)).join(' ');
    return '<div class="ai-sec"><div class="ai-h">' + esc(s.name) + '</div>'
      + (prose ? '<div class="ai-p">' + esc(prose) + '</div>' : '')
      + (items.length ? '<ul class="ai-ul">' + items.map(i=>'<li>'+i+'</li>').join('') + '</ul>' : '')
      + '</div>';
  }).join('');
}
