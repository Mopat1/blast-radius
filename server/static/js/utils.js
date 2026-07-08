export const APP_VERSION = '0.4.0';
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
