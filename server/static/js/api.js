/* All backend communication lives here. */
import { store } from './utils.js';

/* When hosting this frontend separately from the API (e.g. Netlify),
   set API_BASE to your Render URL. Leave '' when served by FastAPI. */
export const API_BASE = '';

let onAuthFail = null;
export function setAuthFailHandler(fn){ onAuthFail = fn; }
export const token = () => store.get('br_token') || '';

export async function api(path, opts = {}){
  const r = await fetch(API_BASE + path, {...opts, headers:{
    'Content-Type':'application/json',
    ...(token() ? {Authorization:'Bearer '+token()} : {}), ...(opts.headers||{})
  }});
  if(r.status===401 && token()){ onAuthFail && onAuthFail(); throw new Error('session expired'); }
  if(!r.ok){ const d = await r.json().catch(()=>({})); throw new Error(d.detail||r.statusText); }
  return r.status===204 ? null : r.json();
}

export const AuthAPI = {
  login:    creds => api('/auth/login',    {method:'POST', body:JSON.stringify(creds)}),
  register: creds => api('/auth/register', {method:'POST', body:JSON.stringify(creds)}),
  demo:     ()    => api('/auth/demo',     {method:'POST'}),
};

export const ReposAPI = {
  list:     ()            => api('/repos'),
  add:      (name,source) => api('/repos', {method:'POST', body:JSON.stringify({name,source})}),
  graph:    id            => api(`/repos/${id}/graph`),
  impact:   (id,target)   => api(`/repos/${id}/impact?target=`+encodeURIComponent(target)),
  hotspots: id            => api(`/repos/${id}/hotspots`),
  search:   (id,q)        => api(`/repos/${id}/search?q=`+encodeURIComponent(q)),
  analyze:  id            => api(`/repos/${id}/analyze`, {method:'POST'}),
  remove:   id            => api(`/repos/${id}`, {method:'DELETE'}),
};
