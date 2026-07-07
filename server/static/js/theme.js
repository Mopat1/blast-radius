/* Light / dark theme with persistence. */
import { $, store } from './utils.js';

let onChange = null;

export function init(cb){
  onChange = cb;
  $('themeBtn').onclick = () =>
    set(document.documentElement.getAttribute('data-theme')==='light' ? 'dark' : 'light');
  if(store.get('br_theme')==='light') set('light');
}

function set(t){
  document.documentElement.setAttribute('data-theme', t);
  store.set('br_theme', t);
  $('themeBtn').textContent = t==='light' ? '◑' : '◐';
  onChange && onChange();
}
