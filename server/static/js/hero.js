/* Login-page ambience: slow-drifting constellation with soft, capped
   blast ripples. 30fps, DPR-aware, pauses when hidden or after sign-in. */
import { $, cssVar } from './utils.js';

let raf = 0, last = 0;

export function init(){
  const cv = $('heroCanvas');
  if(!cv) return;
  const ctx = cv.getContext('2d');
  const N = 34, LINK = 150;
  let W=0, H=0, dpr=1, pts=[], ripples=[], nextRipple=2.5, t=0;

  function resize(){
    const r = cv.parentElement.getBoundingClientRect();
    dpr = Math.min(2, window.devicePixelRatio||1);
    W = r.width; H = r.height;
    cv.width = W*dpr; cv.height = H*dpr;
    cv.style.width = W+'px'; cv.style.height = H+'px';
  }
  resize();
  window.addEventListener('resize', resize);

  for(let i=0;i<N;i++){
    pts.push({
      x:Math.random(), y:Math.random(),
      r:1.6+Math.random()*2.4,
      ax:Math.random()*Math.PI*2, ay:Math.random()*Math.PI*2,   // drift phases
      sx:.006+Math.random()*.01,  sy:.006+Math.random()*.01,    // drift speed
      mx:14+Math.random()*22,     my:14+Math.random()*22,       // drift radius px
      heat:0,
    });
  }

  function frame(now){
    raf = requestAnimationFrame(frame);
    if(document.hidden) return;
    if($('auth').style.display==='none'){ cancelAnimationFrame(raf); raf=0; return; }
    const dt = Math.min(.05, (now-last)/1000 || 0); last = now;
    if(dt < 1/34) return;                       // ~30fps cap
    t += dt;

    ctx.setTransform(dpr,0,0,dpr,0,0);
    ctx.clearRect(0,0,W,H);

    const safe = cssVar('--safe'), blast = cssVar('--blast');

    // positions: gentle sinusoidal drift around home points (perfectly smooth)
    const P = pts.map(p=>({
      px: p.x*W + Math.sin(t*p.sx*60 + p.ax)*p.mx,
      py: p.y*H + Math.cos(t*p.sy*60 + p.ay)*p.my,
      p,
    }));

    // ripples
    nextRipple -= dt;
    if(nextRipple<=0){
      const o = P[(Math.random()*P.length)|0];
      ripples.push({x:o.px, y:o.py, r:6, life:1});
      nextRipple = 3.5 + Math.random()*2.5;
    }
    ripples = ripples.filter(rp=>rp.life>0);
    ripples.forEach(rp=>{
      rp.r += dt*55; rp.life -= dt*.5;
      ctx.beginPath(); ctx.arc(rp.x, rp.y, rp.r, 0, 7);
      ctx.strokeStyle = blast; ctx.globalAlpha = .35*rp.life; ctx.lineWidth = 1.2; ctx.stroke();
      P.forEach(q=>{                             // warm nearby nodes briefly
        const d = Math.hypot(q.px-rp.x, q.py-rp.y);
        if(Math.abs(d-rp.r) < 26) q.p.heat = Math.min(1, q.p.heat + dt*4);
      });
    });

    // links (distance-faded)
    for(let i=0;i<P.length;i++) for(let j=i+1;j<P.length;j++){
      const a=P[i], b=P[j], d=Math.hypot(a.px-b.px, a.py-b.py);
      if(d<LINK){
        ctx.beginPath(); ctx.moveTo(a.px,a.py); ctx.lineTo(b.px,b.py);
        ctx.strokeStyle = safe; ctx.globalAlpha = .11*(1-d/LINK); ctx.lineWidth = 1; ctx.stroke();
      }
    }

    // nodes
    P.forEach(q=>{
      q.p.heat = Math.max(0, q.p.heat - dt*.9);
      ctx.beginPath(); ctx.arc(q.px, q.py, q.p.r + q.p.heat*1.6, 0, 7);
      ctx.fillStyle = q.p.heat>0.02 ? blast : safe;
      ctx.globalAlpha = .5 + q.p.heat*.5;
      ctx.fill();
    });
    ctx.globalAlpha = 1;
  }
  raf = requestAnimationFrame(frame);
}
