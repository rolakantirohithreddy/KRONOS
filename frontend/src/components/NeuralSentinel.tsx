/**
 * NeuralSentinel — animated canvas: neural mesh, attack cycle, shockwave, waveform.
 *
 * 13-second cycle:
 *  0–5 s   IDLE     calm violet particles on curved mesh
 *  5–8 s   ATTACK   corruption crawls amber→crimson toward hub; node glitches
 *  8–9 s   DETECT   hub emits expanding shockwave ring
 *  9–10 s  SETTLE   node flashes emerald → snaps back to violet
 * 10–13 s  (idle tail, then loops)
 */
import { useEffect, useRef } from 'react';

// ── Colour helpers ────────────────────────────────────────────────────────────
type RGB = [number, number, number];

function hexToRgb(hex: string): RGB {
  hex = hex.trim().replace('#', '');
  if (hex.length === 3) hex = hex.split('').map(c => c + c).join('');
  return [parseInt(hex.slice(0,2),16), parseInt(hex.slice(2,4),16), parseInt(hex.slice(4,6),16)];
}

function rgba(rgb: RGB, a: number) {
  return `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${a.toFixed(3)})`;
}

function lerpRgb(a: RGB, b: RGB, t: number): RGB {
  t = Math.max(0, Math.min(1, t));
  return [Math.round(a[0]+(b[0]-a[0])*t), Math.round(a[1]+(b[1]-a[1])*t), Math.round(a[2]+(b[2]-a[2])*t)];
}

function clamp(v: number, lo: number, hi: number) { return v < lo ? lo : v > hi ? hi : v; }

// ── Palette ───────────────────────────────────────────────────────────────────
interface Pal { violet:RGB; magenta:RGB; amber:RGB; crimson:RGB; emerald:RGB; bg:RGB }

function readPalette(): Pal {
  const s = getComputedStyle(document.documentElement);
  const g = (v: string, fb: string) => s.getPropertyValue(v).trim() || fb;
  return {
    violet:  hexToRgb(g('--accent-primary',   '#A855F7')),
    magenta: hexToRgb(g('--accent-secondary',  '#E879F9')),
    amber:   hexToRgb(g('--accent-warn',       '#F59E0B')),
    crimson: hexToRgb(g('--accent-danger',     '#F43F5E')),
    emerald: hexToRgb(g('--accent-safe',       '#34D399')),
    bg:      hexToRgb(g('--bg-primary',        '#0B0710')),
  };
}

// ── Geometry ──────────────────────────────────────────────────────────────────
interface Vec2 { x:number; y:number }
interface NSNode { pos:Vec2; layer:0|1|2; isHub:boolean; baseR:number }
interface NSEdge { from:number; to:number; cp1:Vec2; cp2:Vec2 }
interface NSParticle { t:number; speed:number; dir:1|-1; edgeIdx:number }
interface Shockwave  { r:number; maxR:number; opacity:number }

function makeCurve(a: Vec2, b: Vec2, c: number): {cp1:Vec2;cp2:Vec2} {
  const mx=(a.x+b.x)/2, my=(a.y+b.y)/2, dx=b.x-a.x, dy=b.y-a.y;
  const nx=-dy*c, ny=dx*c;
  return { cp1:{x:mx+nx*0.6,y:my+ny*0.6}, cp2:{x:mx-nx*0.4,y:my-ny*0.4} };
}

function bezierPt(p0:Vec2, cp1:Vec2, cp2:Vec2, p1:Vec2, t:number): Vec2 {
  const u=1-t;
  return { x:u*u*u*p0.x+3*u*u*t*cp1.x+3*u*t*t*cp2.x+t*t*t*p1.x,
           y:u*u*u*p0.y+3*u*u*t*cp1.y+3*u*t*t*cp2.y+t*t*t*p1.y };
}

// ── Canvas draw helpers ───────────────────────────────────────────────────────
function glowLine(
  ctx: CanvasRenderingContext2D,
  p0:Vec2, cp1:Vec2, cp2:Vec2, p1:Vec2,
  col:RGB, alpha:number, lw:number, glowW:number, glowA:number,
) {
  ctx.save();
  ctx.filter = 'blur(5px)';
  ctx.beginPath(); ctx.moveTo(p0.x,p0.y); ctx.bezierCurveTo(cp1.x,cp1.y,cp2.x,cp2.y,p1.x,p1.y);
  ctx.strokeStyle=rgba(col,glowA); ctx.lineWidth=glowW; ctx.stroke();
  ctx.filter='none';
  ctx.beginPath(); ctx.moveTo(p0.x,p0.y); ctx.bezierCurveTo(cp1.x,cp1.y,cp2.x,cp2.y,p1.x,p1.y);
  ctx.strokeStyle=rgba(col,alpha); ctx.lineWidth=lw; ctx.stroke();
  ctx.restore();
}

function glowDot(ctx: CanvasRenderingContext2D, pos:Vec2, r:number, col:RGB, alpha:number, glowR:number, glowA:number) {
  const g = ctx.createRadialGradient(pos.x,pos.y,0,pos.x,pos.y,glowR);
  g.addColorStop(0, rgba(col,glowA)); g.addColorStop(1, rgba(col,0));
  ctx.beginPath(); ctx.arc(pos.x,pos.y,glowR,0,Math.PI*2); ctx.fillStyle=g; ctx.fill();
  ctx.beginPath(); ctx.arc(pos.x,pos.y,r,0,Math.PI*2); ctx.fillStyle=rgba(col,alpha); ctx.fill();
}

// ── Cycle constants ───────────────────────────────────────────────────────────
const CYCLE  = 13000;
const T_ATK  = 5000;
const T_DET  = 8000;
const T_NEUT = 9000;
const T_SETT = 10000;

type Phase = 'idle'|'attack'|'detect'|'settle';

// ── Component ─────────────────────────────────────────────────────────────────
export function NeuralSentinel() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // All references below are guaranteed non-null. Alias for TS.
    const cvs: HTMLCanvasElement       = canvas;
    const c:   CanvasRenderingContext2D = ctx;

    let raf = 0;
    let pal = readPalette();
    let nodes: NSNode[]      = [];
    let edges: NSEdge[]      = [];
    let parts: NSParticle[]  = [];
    let waves: Shockwave[]   = [];
    let atkEdge = 0;
    let W = 0, H = 0;

    // Waveform buffer
    const WLEN = 200;
    const wBuf = new Float32Array(WLEN);
    let wOff = 0;

    // Hub pulse
    let hPulse = 1.0, hDir = 1;

    // Glitch counter
    let glitchN = 0;

    // Time
    let t0 = -1, tPrev = -1;

    // ── Build scene ─────────────────────────────────────────────────────
    function build() {
      W = cvs.offsetWidth  || 800;
      H = cvs.offsetHeight || 600;
      cvs.width  = W;
      cvs.height = H;
      pal = readPalette();
      nodes=[]; edges=[]; parts=[]; waves=[]; wBuf.fill(0); wOff=0;

      const cx=W*0.47, cy=H*0.48;
      nodes.push({pos:{x:cx,y:cy},layer:2,isHub:true,baseR:14});

      const sats = [
        {a:-0.4, d:0.30, l:2 as const},
        {a: 0.7, d:0.28, l:2 as const},
        {a: 1.5, d:0.26, l:1 as const},
        {a: 2.3, d:0.31, l:1 as const},
        {a: 3.2, d:0.27, l:0 as const},
        {a: 4.1, d:0.34, l:0 as const},
        {a: 4.9, d:0.29, l:1 as const},
        {a:-1.2, d:0.35, l:0 as const},
      ];
      const diag = Math.sqrt(W*W+H*H);
      sats.forEach(({a,d,l}) => {
        const jA=(Math.random()-0.5)*0.28, jD=(Math.random()-0.5)*0.05;
        const r=diag*(d+jD), ang=a+jA;
        const baseR = l===2 ? 5+Math.random()*3 : l===1 ? 3.5+Math.random()*2 : 2+Math.random()*1.5;
        nodes.push({pos:{x:cx+Math.cos(ang)*r,y:cy+Math.sin(ang)*r},layer:l,isHub:false,baseR});
      });

      for(let i=1;i<nodes.length;i++){
        const curv=(0.25+Math.random()*0.2)*(Math.random()>0.5?1:-1);
        const {cp1,cp2}=makeCurve(nodes[i].pos,nodes[0].pos,curv);
        edges.push({from:i,to:0,cp1,cp2});
      }

      edges.forEach((_,ei)=>{
        for(let p=0;p<2+Math.floor(Math.random()*2);p++){
          parts.push({t:Math.random(),speed:0.0014+Math.random()*0.001,dir:Math.random()>0.5?1:-1,edgeIdx:ei});
        }
      });

      atkEdge = 1+Math.floor(Math.random()*(edges.length-1));
    }

    // ── Waveform ─────────────────────────────────────────────────────────
    function pushWave(phase:Phase, prog:number) {
      let amp: number;
      if      (phase==='idle')   amp=0.08+Math.sin(Date.now()*0.003)*0.04;
      else if (phase==='attack') amp=0.15+prog*0.55;
      else if (phase==='detect') amp=0.7+(1-prog)*0.2;
      else                       amp=0.2*(1-prog);
      wBuf[wOff%WLEN]=(Math.random()*2-1)*amp;
      wOff++;
    }

    function drawWaveform(phase:Phase, prog:number) {
      const bH=50, yB=H-bH/2, xS=W/WLEN;

      let wCol: RGB;
      if      (phase==='idle')   wCol=pal.violet;
      else if (phase==='attack') wCol=lerpRgb(pal.amber,pal.crimson,prog);
      else if (phase==='detect') wCol=pal.crimson;
      else                       wCol=lerpRgb(pal.crimson,pal.violet,prog);

      // Edge-faded stroke gradients so the waveform never has a hard cut at panel boundaries
      const strokeGrad = c.createLinearGradient(0, 0, W, 0);
      strokeGrad.addColorStop(0, rgba(wCol, 0));
      strokeGrad.addColorStop(0.04, rgba(wCol, 0.85));
      strokeGrad.addColorStop(0.92, rgba(wCol, 0.85));
      strokeGrad.addColorStop(1, rgba(wCol, 0));

      const glowGrad = c.createLinearGradient(0, 0, W, 0);
      glowGrad.addColorStop(0, rgba(wCol, 0));
      glowGrad.addColorStop(0.04, rgba(wCol, 0.22));
      glowGrad.addColorStop(0.92, rgba(wCol, 0.22));
      glowGrad.addColorStop(1, rgba(wCol, 0));

      const path=()=>{
        c.beginPath();
        for(let i=0;i<WLEN;i++){
          const x=i*xS, y=yB+wBuf[(wOff+i)%WLEN]*(bH*0.4);
          i===0?c.moveTo(x,y):c.lineTo(x,y);
        }
      };
      path(); c.strokeStyle=strokeGrad; c.lineWidth=1.5; c.stroke();
      c.save(); c.filter='blur(3px)';
      path(); c.strokeStyle=glowGrad; c.lineWidth=5; c.stroke();
      c.restore();
    }

    // ── Corruption overlay ────────────────────────────────────────────────
    function drawCorruption(edge:NSEdge, fromN:NSNode, toN:NSNode, tEnd:number, col:RGB) {
      const N=40;
      c.save();
      c.beginPath();
      for(let i=0;i<=N;i++){
        const t=i/N*tEnd;
        const pt=bezierPt(fromN.pos,edge.cp1,edge.cp2,toN.pos,t);
        i===0?c.moveTo(pt.x,pt.y):c.lineTo(pt.x,pt.y);
      }
      c.strokeStyle=rgba(col,0.9); c.lineWidth=2.5; c.stroke();
      c.filter='blur(4px)';
      c.beginPath();
      for(let i=0;i<=N;i++){
        const t=i/N*tEnd;
        const pt=bezierPt(fromN.pos,edge.cp1,edge.cp2,toN.pos,t);
        i===0?c.moveTo(pt.x,pt.y):c.lineTo(pt.x,pt.y);
      }
      c.strokeStyle=rgba(col,0.3); c.lineWidth=8; c.stroke();
      c.restore();
    }

    // ── Main render ───────────────────────────────────────────────────────
    function render(ts: number) {
      if(t0<0){ t0=ts; tPrev=ts; }
      const dt=ts-tPrev; tPrev=ts;

      const ct=(ts-t0)%CYCLE;
      let phase:Phase, prog:number;

      if      (ct<T_ATK)  { phase='idle';   prog=ct/T_ATK; }
      else if (ct<T_DET)  { phase='attack'; prog=(ct-T_ATK)/(T_DET-T_ATK); }
      else if (ct<T_NEUT) { phase='detect'; prog=(ct-T_DET)/(T_NEUT-T_DET); }
      else if (ct<T_SETT) { phase='settle'; prog=(ct-T_NEUT)/(T_SETT-T_NEUT); }
      else                { phase='idle';   prog=(ct-T_SETT)/(CYCLE-T_SETT); }

      if(ct<60 && phase==='idle' && prog<0.01){
        atkEdge=1+Math.floor(Math.random()*(edges.length-1));
        glitchN=0;
      }

      c.clearRect(0,0,W,H);

      // Hub heartbeat
      hPulse+=hDir*dt*0.0007;
      if(hPulse>1.05) hDir=-1;
      if(hPulse<1.00) hDir= 1;

      // ── Edges ──
      edges.forEach((edge,i)=>{
        const fN=nodes[edge.from], tN=nodes[edge.to];
        let col:RGB=pal.violet, la=0.55, gA=0.12, lw=1.2;
        if(fN.layer===0){la=0.22;gA=0.05;lw=0.8;}
        else if(fN.layer===1){la=0.38;gA=0.09;lw=1.0;}

        if(i===atkEdge){
          if(phase==='attack'){
            col=lerpRgb(pal.amber,pal.crimson,prog); la=0.7; gA=0.2; lw=1.8;
          } else if(phase==='settle'){
            col=lerpRgb(pal.crimson,pal.violet,prog);
          }
        }
        glowLine(c, fN.pos,edge.cp1,edge.cp2,tN.pos, col,la,lw,lw*6,gA);

        if(i===atkEdge && phase==='attack'){
          const tEnd=clamp(prog*1.1,0,1);
          drawCorruption(edge,fN,tN,tEnd,lerpRgb(pal.amber,pal.crimson,prog));
        }
      });

      // ── Particles ──
      parts.forEach(p=>{
        p.t+=p.speed*p.dir;
        if(p.t>1) p.t=0;
        if(p.t<0) p.t=1;
        if(p.edgeIdx===atkEdge && phase==='attack') return;
        const edge=edges[p.edgeIdx];
        const fN=nodes[edge.from], tN=nodes[edge.to];
        const pos=bezierPt(fN.pos,edge.cp1,edge.cp2,tN.pos,p.t);
        const col=p.dir===1?pal.violet:pal.magenta;
        const a=fN.layer===0?0.5:fN.layer===1?0.7:0.9;
        const r=fN.layer===0?1.5:fN.layer===1?2.0:2.5;
        glowDot(c,pos,r,col,a,r*4,a*0.3);
      });

      // ── Satellite nodes ──
      nodes.forEach((node,ni)=>{
        if(node.isHub) return;
        const l=node.layer;
        let col:RGB=pal.violet;
        let alpha=l===0?0.45:l===1?0.65:0.85;
        let gR=node.baseR*(l===0?3:l===1?4:5);
        let gA=l===0?0.08:l===1?0.14:0.20;

        const atkFrom=edges[atkEdge]?.from===ni;
        if(atkFrom){
          if(phase==='attack'){
            col=lerpRgb(pal.violet,pal.crimson,prog); gA=0.3;
            // Chromatic aberration glitch
            if(prog>0.45 && glitchN<6){
              glitchN++;
              c.globalAlpha=0.35;
              glowDot(c,{x:node.pos.x+3,y:node.pos.y},node.baseR,[255,0,80],0.5,gR,0.1);
              glowDot(c,{x:node.pos.x-3,y:node.pos.y-2},node.baseR,[0,220,255],0.4,gR,0.08);
              c.globalAlpha=1;
            }
          } else if(phase==='detect'){
            col=pal.crimson; gA=0.35;
          } else if(phase==='settle'){
            col=prog<0.4 ? lerpRgb(pal.crimson,pal.emerald,prog/0.4)
                         : lerpRgb(pal.emerald,pal.violet,(prog-0.4)/0.6);
            gA=0.25;
          }
        } else if(phase==='attack'||phase==='detect'){
          alpha*=0.7;
        }
        glowDot(c,node.pos,node.baseR,col,alpha,gR,gA);
      });

      // ── Hub ──
      {
        const hub=nodes[0];
        let hCol:RGB=pal.violet, hA=0.95, hGR=hub.baseR*5*hPulse, hGA=0.25;
        if(phase==='detect'){
          hCol=lerpRgb(pal.violet,pal.crimson,1-prog); hGR=hub.baseR*7; hGA=0.4;
        } else if(phase==='settle'){
          hCol=lerpRgb(pal.crimson,pal.violet,prog); hGA=0.3;
        }
        glowDot(c,hub.pos,hub.baseR*hPulse,hCol,hA,hGR,hGA);
        c.beginPath(); c.arc(hub.pos.x,hub.pos.y,hub.baseR*hPulse+4,0,Math.PI*2);
        c.strokeStyle=rgba(hCol,0.35); c.lineWidth=1; c.stroke();
      }

      // ── Shockwave ──
      if(phase==='detect' && prog<0.45 && waves.length===0){
        waves.push({r:0,maxR:Math.max(W,H)*0.55,opacity:0.8});
      }
      waves=waves.filter(sw=>{
        sw.r+=dt*0.28;
        sw.opacity=clamp(1-sw.r/sw.maxR,0,0.8);
        const hub=nodes[0];
        c.beginPath(); c.arc(hub.pos.x,hub.pos.y,sw.r,0,Math.PI*2);
        c.strokeStyle=rgba(pal.violet,sw.opacity*0.9); c.lineWidth=2; c.stroke();
        c.save(); c.filter='blur(5px)';
        c.beginPath(); c.arc(hub.pos.x,hub.pos.y,sw.r,0,Math.PI*2);
        c.strokeStyle=rgba(pal.violet,sw.opacity*0.3); c.lineWidth=8; c.stroke();
        c.restore();
        return sw.opacity>0.01;
      });

      // ── Waveform ──
      pushWave(phase, prog);
      drawWaveform(phase, prog);

      raf=requestAnimationFrame(render);
    }

    // ── Start ──────────────────────────────────────────────────────────────
    build();
    raf=requestAnimationFrame(render);

    const onResize=()=>{ build(); t0=-1; tPrev=-1; };
    window.addEventListener('resize',onResize);

    const obs=new MutationObserver(()=>{ pal=readPalette(); });
    obs.observe(document.documentElement,{attributes:true,attributeFilter:['data-theme']});

    return ()=>{ cancelAnimationFrame(raf); window.removeEventListener('resize',onResize); obs.disconnect(); };
  },[]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 h-full w-full"
      style={{pointerEvents:'none'}}
    />
  );
}
