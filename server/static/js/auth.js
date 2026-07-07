/* Login / register / logout. Knows nothing about the graph. */
import { $, store } from './utils.js';
import { AuthAPI, setAuthFailHandler, token } from './api.js';

let mode = 'login', onEnter = null;

export function who(){ return store.get('br_email') || ''; }

export function init(enterCb){
  onEnter = enterCb;
  setAuthFailHandler(logout);

  $('authSwitch').onclick = () => {
    mode = mode==='login' ? 'register' : 'login';
    $('authBtn').textContent = mode==='login' ? 'Sign in' : 'Create account';
    $('authSub').textContent = mode==='login' ? 'Sign in to your workspace' : 'Create your workspace';
    $('authSwitch').innerHTML = mode==='login' ? 'New here? <b>Create an account</b>' : 'Have an account? <b>Sign in</b>';
  };
  $('authBtn').onclick = submit;
  $('pass').addEventListener('keydown', e => { if(e.key==='Enter') submit(); });
  $('logout').onclick = logout;

  $('demoBtn').onclick = async () => {
    const b = $('demoBtn');
    b.disabled = true; b.textContent = 'setting up demo…';
    try{
      const d = await AuthAPI.demo();
      store.set('br_token', d.token); store.set('br_email', d.email);
      enter();
    }catch(e){
      $('authErr').textContent = e.message;
      b.disabled = false; b.textContent = 'Try live demo — no signup';
    }
  };

  if(token()) enter();
}

async function submit(){
  $('authErr').textContent = '';
  try{
    const d = await (mode==='login' ? AuthAPI.login : AuthAPI.register)({
      email: $('email').value, password: $('pass').value });
    store.set('br_token', d.token); store.set('br_email', d.email);
    enter();
  }catch(e){
    $('authErr').textContent = (e.message==='Failed to fetch')
      ? 'Cannot reach server — check the API URL.' : e.message;
  }
}

function enter(){
  $('auth').style.display='none';
  $('app').classList.add('on');
  $('who').textContent = who();
  onEnter && onEnter();
}

export function logout(){
  store.del('br_token'); store.del('br_email');
  location.reload();
}
