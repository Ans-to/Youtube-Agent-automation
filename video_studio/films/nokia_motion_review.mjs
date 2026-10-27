/**
 * Nokia review revision: narration-led, original vector motion graphics only.
 *
 * Each sentence-level cue is validated against the existing recorded narration.
 * Cue times within a recorded line are estimated, not forced-aligned: listening
 * and visual review remain required. Pictures are deliberately stylized, not
 * product photographs or archival reconstructions. Audio is never changed here.
 *
 *   node video_studio/films/nokia_motion_review.mjs --validate
 *   node video_studio/films/nokia_motion_review.mjs --sample 230 --out /tmp/frame.png
 *   node video_studio/films/nokia_motion_review.mjs --pipe --fps 30 --from 0 --to 900
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { createCanvas } from '@napi-rs/canvas';
import { loadFonts } from '../motion/kit/fonts.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '../..');
const PLAN = path.join(HERE, 'nokia_motion_review_plan.json');
const SHOTS = path.join(ROOT, 'docs/media/nokia/nokia-15-minute-review-shots.json');
const VOICE = path.join(ROOT, 'docs/media/nokia/nokia-15-minute-review-voice-timing.json');
const PHRASES = path.join(HERE, 'nokia_motion_review_phrase_timing.json');
export const W = 1920;
export const H = 1080;
export const FPS = 30;
const TAU = Math.PI * 2;
const clamp = (x, lo=0, hi=1) => Math.max(lo, Math.min(hi, x));
const ease = (v) => 1 - Math.pow(1-clamp(v), 3);
const phase = (t, delay=0, duration=.55) => ease((t-delay)/duration);
const blend = (a,b,p)=>{
  p=clamp(p);const x=parseInt(a.slice(1),16),y=parseInt(b.slice(1),16);
  const channels=[16,8,0].map(s=>Math.round(((x>>s)&255)*(1-p)+((y>>s)&255)*p));
  return `rgb(${channels[0]},${channels[1]},${channels[2]})`;
};
const C = { ink:'#edf5f4', faint:'#a2bdc5', cyan:'#6ae4d3', blue:'#62a8f1',
  gold:'#efbf73', coral:'#e07e6d', light:'#d5e4df', dark:'#0b1a2a',
  navy:'#112b3d', plate:'#142e42', track:'#365265' };
const CHAPTER = {1:'THE NOKIA STORY',2:'FINNISH ORIGINS',3:'EARLY MOBILE',4:'MOBILE FOR EVERYONE',
  5:'THE GLOBAL LEADER',6:'THE iPHONE ARRIVES',7:'THE ANDROID CHALLENGE',8:'THE SOFTWARE QUESTION',
  9:'A DIFFICULT TRANSITION',10:'THE DEAL',11:'WHAT WENT WRONG?',12:'REINVENTION',13:'THE LESSON'};
export const VISUALS = new Set(['factory','distribution','strategy','software','apps','tower','mill','industry',
  'car','cityman','1011','3210','3310','9000','5800','iphone','g1','lumia','stage','memo','share','merger',
  'platform','ecosystem','deal','burning','snake','covers','durable','compare','origin','river','name',
  'portfolio','classicpair','functions','contract','calendar','appointment','convert','netmerge','sharegrid']);

// Approximate weights allocate recorded time over the actual words and punctuation.
// This is NOT word-level alignment or an assertion that a cue is audible there.
function speechWeight(text) {
  const pieces = text.match(/[\p{L}\p{N}’']+|[.,!?;:]/gu) || [];
  return pieces.reduce((sum, piece) => sum + (/[.!?]/.test(piece) ? 1.25 :
    /[,;:]/.test(piece) ? .35 : Math.max(.65, Math.pow([...piece].length,.55)/2)), 0);
}
export function buildTimeline(plan, shots, voice, fps=FPS, phraseTiming=null) {
  if (!Number.isInteger(fps) || fps<1 || fps>60) throw new Error('fps must be an integer from 1 to 60');
  if (plan?.schema_version!==1 || !plan.shots || !Array.isArray(shots) || !Array.isArray(voice)) throw new Error('invalid inputs');
  const byVoice = new Map(voice.map(row=>[row.shot,row]));
  if(phraseTiming && (phraseTiming.schema_version!==1 || !Array.isArray(phraseTiming.shots))) throw new Error('invalid phrase timings');
  const byPhrase = phraseTiming ? new Map(phraseTiming.shots.map(row=>[row.shot,row])) : null;
  const ids = shots.map(row=>row.id);
  if (byVoice.size!==voice.length || new Set(ids).size!==ids.length || ids.length!==voice.length ||
      ids.length!==Object.keys(plan.shots).length || ids.some(id=>!byVoice.has(id)||!plan.shots[id])) {
    throw new Error('plan, shot clock and narration must cover identical ordered shot IDs');
  }
  if(byPhrase&&(byPhrase.size!==ids.length||phraseTiming.shots.length!==ids.length||ids.some(id=>!byPhrase.has(id))))
    throw new Error('phrase timings must cover the same shots');
  let expected=0; const result=[];
  shots.forEach((shot,si)=>{
    const row=byVoice.get(shot.id), beats=plan.shots[shot.id];
    const first=Math.round(shot.start*fps);
    // Round intermediate cuts identically; cover the audio's final fractional frame.
    const end=si===shots.length-1 ? Math.ceil(shot.end*fps) : Math.round(shot.end*fps);
    if (first!==expected || end<=first || !(shot.start<=row.start && row.start<=row.end && row.end<=shot.end)) {
      throw new Error(`shot/narration clock is invalid at ${shot.id}`);
    }
    expected=end;
    const phrases=byPhrase?.get(shot.id);
    if(phrases){
      if(phrases.sample_rate!==48000||Math.abs(phrases.samples/phrases.sample_rate-row.vo)>.002||!Array.isArray(phrases.phrases)||!phrases.phrases.length)
        throw new Error(`phrase/voice duration mismatch at ${shot.id}`);
      let sample=0, charEnd=0;
      for(const p of phrases.phrases){
        if(p.start_sample!==sample||p.end_sample<=p.start_sample||p.pause_samples<0||p.char_start<charEnd||
           row.text.slice(p.char_start,p.char_end)!==p.text)throw new Error(`invalid phrase data at ${shot.id}`);
        sample=p.end_sample+p.pause_samples;charEnd=p.char_end;
      }
      if(sample!==phrases.samples)throw new Error(`phrase samples do not cover ${shot.id}`);
    }
    if (!Array.isArray(beats)||!beats.length||beats[0].cue!=='') throw new Error(`missing first cue at ${shot.id}`);
    let position=-1; const starts=[first];
    beats.forEach((beat,i)=>{
      if (!VISUALS.has(beat.visual)||!beat.headline||!beat.detail || typeof beat.cue!=='string') {
        throw new Error(`invalid visual, text or cue at ${shot.id}`);
      }
      if (i===0) return;
      if (!beat.cue) throw new Error(`empty interior cue at ${shot.id}`);
      const text=row.text.toLocaleLowerCase('en-US');
      const pos=text.indexOf(beat.cue.toLocaleLowerCase('en-US'),position+1);
      if (pos<0) throw new Error(`cue not found or out of order in ${shot.id}: ${beat.cue}`);
      position=pos;
      let at;
      if(phrases){
        const phrase=phrases.phrases.find(p=>pos>=p.char_start&&pos<p.char_end);
        if(!phrase)throw new Error(`cue is outside recovered phrase at ${shot.id}: ${beat.cue}`);
        const within=row.text.slice(phrase.char_start,pos);
        const fraction=speechWeight(within)/speechWeight(phrase.text);
        at=row.start+(phrase.start_sample+fraction*(phrase.end_sample-phrase.start_sample))/phrases.sample_rate;
      }else{
        const fraction=speechWeight(row.text.slice(0,pos))/speechWeight(row.text);
        at=row.start+(row.end-row.start)*fraction;
      }
      const frame=Math.round(at*fps);
      if (frame<=starts[starts.length-1]||frame>=end) throw new Error(`empty/overlapping cue in ${shot.id}: ${beat.cue}`);
      starts.push(frame);
    });
    beats.forEach((beat,i)=>result.push({...beat,shot:shot.id,scene:shot.scene,
      startFrame:starts[i], endFrame:starts[i+1]??end, fps,
      start:starts[i]/fps,end:(starts[i+1]??end)/fps, approximateCue:i>0}));
  });
  // Keep the same animated object moving continuously across a text-only cut.
  // Restarting a pie chart or game at zero on each heading is misleading/jarring.
  result.forEach((beat,i)=>{
    const prev=result[i-1];
    beat.motionStartFrame=prev&&prev.visual===beat.visual&&prev.scene===beat.scene
      ? prev.motionStartFrame : beat.startFrame;
  });
  for(let i=result.length-1;i>=0;i--){
    const next=result[i+1],beat=result[i];
    beat.motionEndFrame=next&&next.motionStartFrame===beat.motionStartFrame ? next.motionEndFrame : beat.endFrame;
  }
  return result;
}
function rr(ctx,x,y,w,h,r,fill,stroke=null,lw=2) {
  ctx.beginPath();ctx.roundRect(x,y,w,h,r);
  if(fill){ctx.fillStyle=fill;ctx.fill();}
  if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=lw;ctx.stroke();}
}
function line(ctx,x1,y1,x2,y2,color=C.faint,width=4) {
  ctx.beginPath();ctx.moveTo(x1,y1);ctx.lineTo(x2,y2);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.lineCap='round';ctx.stroke();
}
function circle(ctx,x,y,r,color,stroke=null,width=3) {
  ctx.beginPath();ctx.arc(x,y,r,0,TAU);if(color){ctx.fillStyle=color;ctx.fill();}
  if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=width;ctx.stroke();}
}
function poly(ctx,points,fill,stroke=null,width=3) {
  ctx.beginPath();points.forEach((v,i)=>i?ctx.lineTo(v[0],v[1]):ctx.moveTo(v[0],v[1]));ctx.closePath();
  if(fill){ctx.fillStyle=fill;ctx.fill();}if(stroke){ctx.strokeStyle=stroke;ctx.lineWidth=width;ctx.stroke();}
}
function label(ctx,text,x,y,size=25,color=C.ink,weight=700,align='center') {
  ctx.fillStyle=color;ctx.font=`${weight} ${size}px "Space Grotesk", sans-serif`;
  ctx.textAlign=align;ctx.textBaseline='middle';ctx.fillText(text,x,y);ctx.textAlign='left';
}
function arrow(ctx,x1,y1,x2,y2,p,color=C.cyan,width=7) {
  const x=x1+(x2-x1)*p,y=y1+(y2-y1)*p;line(ctx,x1,y1,x,y,color,width);
  if(p>.9){const a=Math.atan2(y2-y1,x2-x1);const k=19;
    line(ctx,x,y,x-k*Math.cos(a-.58),y-k*Math.sin(a-.58),color,width);
    line(ctx,x,y,x-k*Math.cos(a+.58),y-k*Math.sin(a+.58),color,width);}
}
function arc(ctx,x,y,r,a0,a1,color,width=5){ctx.beginPath();ctx.arc(x,y,r,a0,a1);ctx.strokeStyle=color;ctx.lineWidth=width;ctx.stroke();}

/** Stylized keypad phone. Deliberately illustrative; never a model-exact render. */
function classic(ctx,style,t,{x=210,y=55,scale=1}={}) {
  ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);
  const isEarly=style==='cityman'||style==='1011';const body=style==='3310'?'#28547c':style==='3210'?'#435e81':'#516474';
  const w=isEarly?230:260,h=isEarly?510:490;
  if(scale>=.95&&style!=='snake'){
    // Expanding call signals express the phone's purpose, rather than noise.
    for(let i=0;i<3;i++){const r=44+((t*42+i*45)%125),a=clamp(1-(r-44)/125);
      ctx.globalAlpha=a*.7;arc(ctx,-30,140,r,2.65,3.6,C.cyan,5);arc(ctx,w+30,140,r,-.48,.48,C.cyan,5);}
    ctx.globalAlpha=1;
  }
  if(isEarly){rr(ctx,31,-68,25,110,12,'#91a5ab');rr(ctx,37,-90,13,80,7,'#cedadb');}
  rr(ctx,-14,16,w+28,h+5,52,'#071522');
  rr(ctx,0,0,w,h,47,body,'#a1c3cd',3);
  rr(ctx,15,14,w-30,h-28,36,'#1a3449');
  rr(ctx,w*.34,33,w*.32,8,4,'#8aa7b2');
  rr(ctx,35,74,w-70,118,12,'#a4c4a6');
  rr(ctx,42,82,w-84,102,8,'#b6d0b0');
  if(style==='snake'){
    const grid=[[0,0],[1,0],[2,0],[2,1],[2,2],[3,2],[4,2],[4,3],[5,3],[5,2],[5,1],[6,1],[7,1],[7,2],[7,3],[8,3],[8,2]];
    const head=Math.floor(t*2.7)%grid.length;
    for(let k=4;k>=0;k--){const [gx,gy]=grid[(head-k+grid.length)%grid.length];rr(ctx,55+gx*13,94+gy*14,11,11,1,'#203d35');}
    circle(ctx,177,145,4,'#203d35');
  } else {
    for(let i=0;i<4;i++) rr(ctx,55,100+i*16,Math.max(10,(w-112)*(i===2?.58:.82)),4,2,'#496b58');
    for(let i=0;i<4;i++)rr(ctx,w-68+i*7,141-i*6,5,8+i*6,1,'#355844');
    const progress=(t*.20)%1;rr(ctx,54,167,(w-110)*progress,5,2,'#315945');
  }
  if(!isEarly)rr(ctx,w*.32,211,w*.36,25,13,'#a8c3c6');
  const ky=isEarly?225:255;const kh=isEarly?49:45;
  for(let r=0;r<4;r++)for(let c=0;c<3;c++){
    const px=30+c*(w-60)/3,py=ky+r*kh;
    const active=Math.floor(t*2.2)%12===r*3+c;
    rr(ctx,px,py,(w-68)/3,kh-9,13,active?'#d2e6e1':'#8ea6b0');
    label(ctx,r===3?['*','0','#'][c]:String(r*3+c+1),px+(w-68)/6,py+(kh-9)/2,18,'#1d3844',700);
  }
  if(scale>=.95&&style!=='snake'){
    // A message emerges from the handset, to explain communication rather than
    // merely sliding a still product picture around the frame.
    const cycle=(t*.25)%1, show=cycle<.22?ease(cycle/.22):cycle>.8?ease((1-cycle)/.2):1;
    ctx.save();ctx.globalAlpha=show;const bx=w+18+35*show,by=220;
    rr(ctx,bx,by,140,148,17,'#c9e4d8');poly(ctx,[[bx,by+100],[bx-24,by+122],[bx,by+120]],'#c9e4d8');
    for(let k=0;k<3;k++)rr(ctx,bx+18,by+35+k*30,104-(k%2)*25,9,4,'#4a7d80');ctx.restore();
  }
  ctx.restore();
}
function smartphone(ctx,style,t,{x=220,y=55,scale=1}={}) {
  ctx.save();ctx.translate(x,y);ctx.scale(scale,scale);
  const w=260,h=500;const lum=style==='lumia';
  rr(ctx,-13,12,w+26,h+8,47,'#071522');
  rr(ctx,0,0,w,h,42,lum?'#38bce3':'#2a3d4b','#97bbc9',4);
  rr(ctx,13,15,w-26,h-30,31,'#0a1726');
  const sy=49,sh=372;rr(ctx,28,sy,204,sh,10,lum?'#064472':'#102d48');
  rr(ctx,97,27,66,5,3,'#adcbd0');
  if(lum){
    const tiles=[[0,0,2,1],[0,1,1,1],[1,1,1,1],[0,2,1,1],[1,2,1,1],[0,3,2,1]];
    tiles.forEach(([c,r,span],i)=>{
      const a=phase(t,.4+i*.22,.45);ctx.globalAlpha=.25+.75*a;
      rr(ctx,38+c*96,61+r*85,span===2?184:88,76,3,i%3===0?'#2bbde5':i%3===1?'#1989cc':'#54d2df');
      circle(ctx,63+c*96,82+r*85,8,'#d7f3f3');ctx.globalAlpha=1;
    });
    const cycle=t%4, app=cycle<1?phase(cycle,0,1):cycle<2.4?1:cycle<3.3?1-phase(cycle,2.4,.9):0;
    if(app>0){ctx.save();ctx.globalAlpha=app*.92;rr(ctx,49,192,162,112,6,'#c4edeb');
      rr(ctx,64,212,130,9,4,'#278ca6');rr(ctx,64,238,88,9,4,'#55aabb');ctx.restore();}
    label(ctx,'‹',72,455,39,'#dcebea');label(ctx,'◆',130,455,25,'#dcebea');
    circle(ctx,183,452,8,null,'#dcebea',3);line(ctx,189,458,195,464,'#dcebea',3);
  } else {
    for(let r=0;r<4;r++)for(let c=0;c<3;c++){
      const i=r*3+c, a=phase(t,.35+i*.10,.4);ctx.globalAlpha=.28+.72*a;
      const colors=['#56b9dd','#e7a85b','#66d3b0','#a18cdc','#dd7a6e','#8bb6d2'];
      rr(ctx,48+c*57,75+r*70,42,42,10,colors[i%colors.length]);
      circle(ctx,69+c*57,96+r*70,8,'rgba(255,255,255,.58)');ctx.globalAlpha=1;
    }
    // A tapped app opens and closes inside the illustrated screen.
    const cycle=t%4, app=cycle<1?phase(cycle,0,1):cycle<2.4?1:cycle<3.3?1-phase(cycle,2.4,.9):0;
    if(app>0){ctx.save();ctx.globalAlpha=app*.92;rr(ctx,57,175,146,100,12,'#d3e8dc');
      rr(ctx,74,194,112,8,4,'#407383');rr(ctx,74,216,80,8,4,'#6ba3a5');rr(ctx,74,239,96,8,4,'#6ba3a5');ctx.restore();}
    rr(ctx,42,372,176,31,10,'#284963');
    if(style==='5800'){
      rr(ctx,63,446,34,15,8,'#d3e1dc');rr(ctx,113,446,34,15,8,'#d3e1dc');rr(ctx,163,446,34,15,8,'#d3e1dc');
    }else circle(ctx,130,458,20,null,'#a6c2c7',3);
  }
  if(scale>=.95){
    // Expand the app interface out of the phone so the software experience is
    // visible at documentary scale; it is a vector, not a captured screen.
    const cycle=(t*.22)%1, show=cycle<.24?ease(cycle/.24):cycle>.78?ease((1-cycle)/.22):1;
    const px=w+20+32*show;ctx.save();ctx.globalAlpha=show;
    rr(ctx,px,120,145,254,15,'#d2e9df');
    rr(ctx,px+18,145,109,50,8,lum?'#56afd0':'#5f9dad');
    for(let i=0;i<3;i++)rr(ctx,px+18,222+i*35,100-(i%2)*20,10,5,'#568a91');
    label(ctx,'APP',px+72,345,27,'#234d5a');ctx.restore();
  }
  ctx.restore();
}
function communicator(ctx,t) {
  rr(ctx,58,145,585,378,30,'#294355','#a1bdc3',4);
  rr(ctx,77,165,547,175,13,'#142d39');rr(ctx,91,179,520,145,6,'#6a9690');
  // Large pages slide through the illustrated display to show mobile computing.
  ctx.save();ctx.beginPath();ctx.roundRect(91,179,520,145,6);ctx.clip();
  const offset=(t*105)%1170;
  for(let i=-1;i<3;i++){const x=110+i*390-offset;rr(ctx,x,191,370,121,7,'#c4ddc6');
    label(ctx,['MAIL','WEB','NOTES'][(i+3)%3],x+95,224,29,'#294f4b');
    for(let j=0;j<3;j++)rr(ctx,x+190,206+j*26,140-j*27,7,3,'#537d70');}
  ctx.restore();
  rr(ctx,76,356,549,147,13,'#1a3140');
  for(let r=0;r<3;r++)for(let c=0;c<11;c++)rr(ctx,96+c*46,369+r*39,36,29,5,Math.floor(t*3)%33===r*11+c?'#d3e1d9':'#91a8a7');
}
function g1(ctx,t) {
  rr(ctx,83,182,525,300,42,'#344a5b','#a7c5cc',4);
  rr(ctx,104,200,483,151,18,'#163a55');
  for(let r=0;r<2;r++)for(let c=0;c<4;c++)rr(ctx,128+c*93,219+r*52,69,38,8,['#62b5d1','#6abda6','#dcaa67'][((r*4+c)%3)]);
  const p=phase(t,.5,1);ctx.save();ctx.translate(0,40*(1-p));ctx.globalAlpha=p;
  for(let r=0;r<3;r++)for(let c=0;c<10;c++)rr(ctx,120+c*43,367+r*31,36,23,5,'#bacccd');ctx.restore();
}
function tower(ctx,t) {
  line(ctx,350,120,250,560,C.light,12);line(ctx,350,120,450,560,C.light,12);
  line(ctx,300,340,400,340,C.light,8);line(ctx,280,425,420,425,C.light,8);line(ctx,258,525,442,525,C.light,8);
  line(ctx,350,120,350,65,C.gold,8);circle(ctx,350,65,12,C.gold);
  for(let i=0;i<3;i++){const r=70+((t*48+i*52)%180);ctx.globalAlpha=clamp(1-(r-70)/180)*.75;
    arc(ctx,350,65,r,-.87,-.28,C.cyan,7);arc(ctx,350,65,r,Math.PI+.28,Math.PI+.87,C.cyan,7);}
  ctx.globalAlpha=1;line(ctx,170,565,530,565,C.track,5);
  // Network endpoints visibly receive transmissions from the mast.
  [125,575].forEach((x,i)=>{
    line(ctx,350,345,x,460,'#669ba7',4);
    const active=.5+.5*Math.cos(TAU*(t*.30-i*.5));
    rr(ctx,x-70,420,140,145,16,blend('#396a78','#b0dfd1',active),'#a6cbc6',3);
    rr(ctx,x-45,443,90,56,8,'#214f62');circle(ctx,x,532,10,'#214f62');
    const p=(t*.3+i*.5)%1;circle(ctx,350+(x-350)*p,345+(460-345)*p,12,C.gold);
  });
}
function mill(ctx,t) {
  // Stylized mill, animated waterwheel and river -- not an archival image.
  line(ctx,45,535,650,535,C.track,5);poly(ctx,[[115,260],[350,135],[585,260]],'#6c8190','#a6c1c8',4);
  rr(ctx,130,255,440,242,9,'#315062','#a6c1c8',4);rr(ctx,421,125,53,125,4,'#7795a1');
  for(let i=0;i<3;i++){const p=(t*.42+i*.33)%1;ctx.globalAlpha=(1-p)*.6;circle(ctx,447+17*Math.sin(p*4),102-p*65,10+12*p,'#cadbd8');}ctx.globalAlpha=1;
  for(let i=0;i<3;i++)rr(ctx,164+i*110,301,76,74,5,'#b5d0bd');
  rr(ctx,216,405,80,92,5,'#1a3446');
  circle(ctx,480,461,82,'#183747','#a1c3b8',6);ctx.save();ctx.translate(480,461);ctx.rotate(t*.7);
  for(let i=0;i<8;i++){ctx.rotate(TAU/8);line(ctx,0,0,0,-78,C.gold,5);}ctx.restore();circle(ctx,480,461,15,C.gold);
  for(let i=0;i<4;i++){const dx=(t*45+i*160)%180;line(ctx,60+i*145+dx*.28,571+i*13,158+i*145+dx*.28,571+i*13,C.blue,4);}
  // Sheets leave the mill, visibly illustrating the product it made.
  for(let i=0;i<2;i++){const x=250+((t*46+i*170)%300);rr(ctx,x,515,50,35,3,'#c9ddca');rr(ctx,x+8,523,34,4,2,'#759993');}
}
function industry(ctx,t) {
  const positions=[105,320,535];
  positions.forEach((x,i)=>{const p=phase(t,i*.3,.55);ctx.save();ctx.translate(x,260+(1-p)*60);ctx.globalAlpha=p;
    rr(ctx,-75,-70,150,180,18,'#25485a','#779ba5',3);
    if(i===0){for(let j=0;j<4;j++){const slide=(t*32+j*24)%45;rr(ctx,-48+slide*.25,-28+j*24,96,14,2,'#d5ddcb');}label(ctx,'PAPER',0,88,22,C.ink);}
    if(i===1){circle(ctx,0,0,55,'#1b2d3a','#bdc9c5',4);circle(ctx,0,0,20,'#738e96');
      ctx.save();ctx.rotate(t);for(let k=0;k<4;k++){ctx.rotate(TAU/4);line(ctx,25,0,48,0,'#a9c4bf',4);}ctx.restore();label(ctx,'RUBBER',0,88,22,C.ink);}
    if(i===2){circle(ctx,0,0,56,'#cc9568','#e6c39a',4);circle(ctx,0,0,42,null,'#274552',8);circle(ctx,0,0,13,'#274552');
      ctx.save();ctx.rotate(-t*.6);line(ctx,17,0,48,0,'#294552',6);ctx.restore();label(ctx,'CABLE',0,88,22,C.ink);}
    ctx.restore();});
  arrow(ctx,100,520,535,520,phase(t,.9,1.1),C.cyan,5);
}
function factory(ctx,t) {
  poly(ctx,[[65,215],[187,145],[187,215],[311,145],[311,215],[435,145],[435,215],[595,215],[595,430],[65,430]],'#294f62','#82a7b1',4);
  for(let i=0;i<6;i++)rr(ctx,100+i*76,265,48,50,4,'#94b5ae');
  rr(ctx,30,466,640,31,16,'#7fa5ad');
  for(let i=0;i<5;i++){
    const x=50+((t*65+i*142)%600);rr(ctx,x,397,45,69,10,'#c0d2c5');rr(ctx,x+6,405,33,25,3,'#385968');
    for(let r=0;r<2;r++)for(let c=0;c<3;c++)circle(ctx,x+12+c*10,440+r*9,2.5,'#385968');
  }
  for(let i=0;i<7;i++)circle(ctx,75+i*90,482,7,'#284456');
}
function globe(ctx,t) {
  circle(ctx,350,315,210,'#183e52','#99c2c2',5);arc(ctx,350,315,156,0,TAU,'#4b7b88',3);
  ctx.beginPath();ctx.ellipse(350,315,95,210,0,0,TAU);ctx.strokeStyle='#65929a';ctx.lineWidth=3;ctx.stroke();
  ctx.beginPath();ctx.ellipse(350,315,210,72,0,0,TAU);ctx.stroke();
  ctx.beginPath();ctx.ellipse(350,315,210,145,0,0,TAU);ctx.stroke();
  [[188,260],[275,150],[480,195],[515,378],[250,444]].forEach(([x,y],i)=>{
    circle(ctx,x,y,12,C.gold);const a=(t*.45+i*.2)%1;circle(ctx,x+45*Math.sin(a*TAU),y-30*Math.cos(a*TAU),6,C.cyan);
    line(ctx,350,315,x,y,'rgba(110,224,207,.40)',3);
  });
}
function car(ctx,t) {
  rr(ctx,91,291,518,133,37,'#497485','#b5ced0',4);
  poly(ctx,[[175,294],[238,212],[439,212],[516,294]],'#406f82','#bad2d1',4);
  poly(ctx,[[243,228],[319,228],[319,286],[197,286]],'#173a50');poly(ctx,[[333,228],[435,228],[487,286],[333,286]],'#173a50');
  [207,498].forEach(x=>{circle(ctx,x,426,54,'#12283a','#bdcdca',4);circle(ctx,x,426,22,'#7799a2');
    ctx.save();ctx.translate(x,426);ctx.rotate(t*1.8);line(ctx,-18,0,18,0,C.light,4);ctx.restore();});
  rr(ctx,369,253,39,69,9,'#d4dfd3');rr(ctx,379,266,19,20,3,'#3e696b');
  for(let i=0;i<3;i++)line(ctx,59+i*215+((t*100)%120),518,150+i*215+((t*100)%120),518,C.track,4);
}
function stage(ctx,t){
  poly(ctx,[[350,36],[95,459],[605,459]],'rgba(119,185,207,.15)');
  rr(ctx,118,115,464,242,12,'#244c67','#7fb2c0',4);smartphone(ctx,'iphone',t,{x:287,y:128,scale:.40});
  rr(ctx,65,479,570,24,12,'#76979f');rr(ctx,265,445,170,33,10,'#426a7a');
  circle(ctx,350,404,19,C.ink);line(ctx,350,425,350,469,C.ink,10);line(ctx,350,438,385,421,C.ink,8);
  label(ctx,'2007',350,562,37,C.gold);
}
function code(ctx,t,duration=5){
  rr(ctx,80,115,540,410,24,'#173d52','#82adb8',4);
  rr(ctx,80,115,540,65,24,'#315d6c');[0,1,2].forEach(i=>circle(ctx,110+i*29,148,7,[C.coral,C.gold,C.cyan][i]));
  // Build a legible software stack instead of unreadable mock code. The
  // sequence is conceptual and contains no invented dates or metrics.
  const step=Math.max(.55,(duration-.55)/3), labels=['APPLICATIONS','OPERATING SYSTEM','HARDWARE'];
  for(let i=0;i<3;i++){
    const p=clamp((t-i*step)/step), y=198+i*101;
    rr(ctx,113,y,475,82,10,blend('#315d6c',i===1?'#e4bf80':'#b7e2d5',p),'#96bbb8',3);
    label(ctx,labels[i],350,y+41,32,p>.55?'#193e4c':C.ink);
  }
}
function platform(ctx,t,duration=5){
  const labels=['HARDWARE','OPERATING SYSTEM','APPLICATIONS','ONLINE SERVICES'];
  const step=Math.max(.4,(duration-.5)/4);
  labels.forEach((txt,i)=>{const p=clamp((t-i*step)/step);ctx.save();
    rr(ctx,120,100+i*112,460,84,14,blend('#214654','#75adab',p),'#b1d4ce',3);
    label(ctx,txt,350,142+i*112,35,C.ink);ctx.restore();});
  arrow(ctx,615,515,615,136,clamp((t-step)/(3*step)),C.gold,6);
}
function ecosystem(ctx,t){
  const pts=[[350,145,'USERS'],[150,460,'DEVELOPERS'],[550,460,'MAKERS']];
  arrow(ctx,325,188,173,414,phase(t,.25,.9),'#70d9d2',6);
  arrow(ctx,218,474,480,474,phase(t,.8,.9),'#70d9d2',6);
  arrow(ctx,530,414,375,188,phase(t,1.35,.9),'#70d9d2',6);
  pts.forEach(([x,y,txt],i)=>{const p=phase(t,.12+i*.35,.5);ctx.save();ctx.translate(x,y);ctx.scale(.85+.15*p,.85+.15*p);
    // Successive participants become active as the network exchanges value.
    const active=.5+.5*Math.cos(TAU*(t*.34-i/3));
    circle(ctx,0,0,90,blend('#4d7f86','#c5e9d9',active),'#a0d4cd',4);label(ctx,txt,0,0,25,'#102c39');ctx.restore();});
  // Messages flow among the three ecosystem participants (not decorative drift).
  const a=(t*.34)%1;circle(ctx,242+216*a,474,10,C.gold);
  circle(ctx,305-100*a,230+145*a,9,C.gold);
  circle(ctx,495-100*a,375-145*a,9,C.gold);
}
function share(ctx,t){
  const p=phase(t,.3,2.7);circle(ctx,350,315,215,null,'#3a5d6d',50);
  arc(ctx,350,315,215,-Math.PI/2,-Math.PI/2+TAU*.378*p,C.cyan,50);
  label(ctx,`${(37.8*p).toFixed(1)}%`,350,302,73,C.ink);label(ctx,'GARTNER · 2007',350,368,25,C.faint);
  label(ctx,'ALL MOBILE PHONES',350,594,22,C.faint);
}
function sharegrid(ctx,t,duration=5){
  // One hundred equal cells make the all-mobile-phone denominator explicit;
  // the final cell is 80% filled so the graphic represents 37.8, not 38.0.
  const p=clamp(t/Math.max(1,duration*.7)), amount=37.8*p;
  for(let i=0;i<100;i++){
    const x=136+(i%10)*43,y=75+Math.floor(i/10)*43;
    rr(ctx,x,y,31,31,4,'#345868');
    const fill=clamp(amount-i);if(fill>0)rr(ctx,x,y,31*fill,31,4,C.cyan);
  }
  label(ctx,`${amount.toFixed(1)} OF EVERY 100`,350,562,32,C.ink);
}
function merger(ctx,t){
  const labels=['NOKIA AB','RUBBER WORKS','CABLE WORKS'];
  labels.forEach((txt,i)=>{const y=140+i*112,p=phase(t,i*.3,.55);ctx.save();ctx.globalAlpha=p;
    rr(ctx,70,y,300,78,14,'#2b5363','#94b9bb',3);label(ctx,txt,220,y+39,24,C.ink);ctx.restore();
    arrow(ctx,370,y+39,490,290,phase(t,.9+i*.3,.8),C.cyan,5);});
  const q=phase(t,1.6,.6);ctx.save();ctx.globalAlpha=q;rr(ctx,475,234,170,110,19,'#4f8990','#b8d4cb',3);label(ctx,'NOKIA',560,274,29,C.ink);label(ctx,'1967',560,309,24,C.ink);ctx.restore();
}
function strategy(ctx,t,duration=5){
  // The three large stages build in order over the spoken thought. This is a
  // conceptual decision flow, not an invented financial trend or statistic.
  const nodes=[[125,315,'THEN'],[350,315,'DECISION'],[575,315,'NEXT']];
  const step=Math.max(.55,(duration-.45)/3);
  arrow(ctx,205,315,262,315,clamp((t-step*.7)/step),C.cyan,7);
  arrow(ctx,438,315,495,315,clamp((t-step*1.7)/step),C.cyan,7);
  nodes.forEach(([x,y,txt],i)=>{
    const p=clamp((t-i*step)/step);
    circle(ctx,x,y,80,blend('#295466','#abdcd1',p),'#b4dbd1',4);
    label(ctx,txt,x,y,txt==='DECISION'?26:31,p>.55?'#173747':C.ink);
  });
  label(ctx,'A CHANGING DIRECTION',350,505,29,C.faint);
}
function memo(ctx,t){
  rr(ctx,145,85,410,475,18,'#d8e4df','#a8c4bf',4);
  rr(ctx,170,115,360,65,8,'#27576b');label(ctx,'STEPHEN ELOP',350,147,27,C.ink);
  for(let i=0;i<7;i++){let p=phase(t,.3+i*.22,.7);rr(ctx,181,220+i*38,(i===6?190:300)*p,8,4,'#82a0a1');}
  rr(ctx,181,495,200*phase(t,1.5,1),18,3,C.coral);
}
function burning(ctx,t){
  rr(ctx,110,415,480,46,8,'#9aa9a4');line(ctx,160,460,125,570,'#90a6a7',8);line(ctx,530,460,565,570,'#90a6a7',8);
  for(let i=0;i<4;i++){
    const x=200+i*85, h=120+20*Math.sin(t*2+i);poly(ctx,[[x-40,415],[x-25,415-h*.6],[x,415-h],[x+25,415-h*.5],[x+43,415]],i%2?C.coral:C.gold);
  }
  for(let i=0;i<4;i++)line(ctx,72+i*140+((t*35)%40),590,160+i*140+((t*35)%40),590,'#5aa9b8',4);
  label(ctx,'METAPHOR',350,70,25,C.faint);
}
function deal(ctx,t,duration=5){
  const p=clamp((t-.25)/Math.max(1,duration-1));
  rr(ctx,52,180,225,150,20,blend('#a9d6ca','#315f70',p),'#a2c9c6',3);label(ctx,'NOKIA',164,230,32,p<.45?'#183b48':C.ink);label(ctx,'DEVICES',164,280,25,p<.45?'#183b48':C.faint);
  rr(ctx,423,180,225,150,20,blend('#315f70','#a9d6ca',p),'#a2c9c6',3);label(ctx,'MICROSOFT',536,255,28,p>.55?'#183b48':C.ink);
  arrow(ctx,282,255,416,255,p,C.cyan,7);
  // A contract travels from seller to buyer, a concrete visual for the deal.
  const x=125+335*p;rr(ctx,x,365,110,134,10,'#d0e5d8');
  for(let i=0;i<3;i++)rr(ctx,x+16,391+i*25,78-i*12,7,3,'#518184');
  label(ctx,'2013 → 2014',350,572,30,C.gold);
}
function compare(ctx,t){
  classic(ctx,'3310',t,{x:62,y:112,scale:.62});smartphone(ctx,'iphone',t,{x:480,y:105,scale:.62});
  arrow(ctx,275,275,432,275,phase(t,.5,1.2),C.cyan,7);
  label(ctx,'BUTTONS',145,520,26,C.faint);label(ctx,'TOUCH',560,520,26,C.faint);
}
function covers(ctx,t){
  const colors=['#cc8c71','#62bfc3','#dfa85e'];
  colors.forEach((color,i)=>{const p=phase(t,.45+i*.30,.7);ctx.save();ctx.globalAlpha=p*.8;
    ctx.translate(355+(i-1)*165,200+(1-p)*80);ctx.rotate((i-1)*.10);rr(ctx,-80,0,160,320,40,color);ctx.restore();});
  classic(ctx,'3210',t,{x:245,y:70,scale:.8});
  label(ctx,'NO EXTERNAL ANTENNA',350,575,22,C.faint);
}
function durable(ctx,t){
  classic(ctx,'3310',t,{x:100,y:60,scale:.90});
  const p=phase(t,.7,.7);ctx.save();ctx.globalAlpha=p;
  poly(ctx,[[480,160],[555,190],[555,270],[480,345],[405,270],[405,190]],'#3a8594','#b7dbd3',4);
  line(ctx,440,246,470,275,C.ink,9);line(ctx,470,275,520,216,C.ink,9);
  rr(ctx,408,405,145,64,9,'#9ac3a9');rr(ctx,553,425,9,24,3,'#9ac3a9');
  rr(ctx,420,417,112*phase(t,1,1.7),40,5,'#e2f1d4');ctx.restore();
}
function origin(ctx,t){
  // A wood-pulp-to-paper process, with arrows drawn in sequence.
  poly(ctx,[[110,370],[176,185],[242,370]],'#498574','#a4cab8',4);
  rr(ctx,165,360,22,85,5,'#bea37c');
  arrow(ctx,260,315,317,315,phase(t,.35,.7),C.cyan,5);
  rr(ctx,325,255,110,120,14,'#386a79','#9dc6c2',3);
  circle(ctx,380,315,35,null,C.gold,5);ctx.save();ctx.translate(380,315);ctx.rotate(t);
  for(let i=0;i<6;i++){ctx.rotate(TAU/6);line(ctx,0,0,0,-34,C.gold,3);}ctx.restore();
  arrow(ctx,445,315,502,315,phase(t,1.05,.7),C.cyan,5);
  rr(ctx,510,230,115,158,8,'#d8e5d8');
  for(let i=0;i<4;i++)rr(ctx,530,260+i*24,75*phase(t,1.4+i*.15,.5),5,2,'#668d86');
  // Wood and paper travel through the process after the connecting arrows draw.
  const travel=(t*.24)%1;
  if(travel<.5)rr(ctx,257+travel*140,295,35,30,7,C.gold);
  else rr(ctx,438+(travel-.5)*140,285,30,42,3,'#e5eee0');
  label(ctx,'WOOD',175,483,32,C.faint);label(ctx,'PULP',380,483,32,C.faint);label(ctx,'PAPER',567,483,32,C.faint);
}
function river(ctx,t){
  ctx.beginPath();ctx.moveTo(65,455);ctx.bezierCurveTo(175,555,285,510,355,410);ctx.bezierCurveTo(445,285,505,350,635,205);
  ctx.strokeStyle='#326b7c';ctx.lineWidth=125;ctx.lineCap='round';ctx.stroke();
  // Wide moving bands travel along the river's actual path, illustrating flow.
  ctx.beginPath();ctx.moveTo(65,455);ctx.bezierCurveTo(175,555,285,510,355,410);ctx.bezierCurveTo(445,285,505,350,635,205);
  ctx.strokeStyle='#62b7bf';ctx.lineWidth=76;ctx.setLineDash([105,90]);ctx.lineDashOffset=-t*60;ctx.stroke();ctx.setLineDash([]);
  poly(ctx,[[110,275],[182,220],[254,275]],'#95b2aa');rr(ctx,120,275,124,110,8,'#426c73');
  for(let i=0;i<2;i++)rr(ctx,139+i*47,302,32,35,4,'#d0ddc9');
  label(ctx,'NOKIANVIRTA',420,560,29,C.ink);
}
function nameGraphic(ctx,t){
  label(ctx,'NOKIANVIRTA',350,262,56,C.faint);
  const p=phase(t,.6,1.1);
  rr(ctx,75,317,550*p,6,3,C.cyan);
  ctx.save();ctx.translate(0,30*(1-p));ctx.globalAlpha=p;
  label(ctx,'NOKIA',350,410,96,C.ink);ctx.restore();
}
function portfolio(ctx,t){
  const x=[115,350,585];
  x.forEach((cx,i)=>{const p=phase(t,i*.3,.6);ctx.save();ctx.translate(cx,280+(1-p)*30);ctx.globalAlpha=p;
    rr(ctx,-83,-105,166,210,18,'#2e5969','#98bdbb',3);
    if(i===0){circle(ctx,0,-20,52,null,'#e3bd86',10);circle(ctx,0,-20,27,null,'#d7aa77',6);circle(ctx,0,-20,7,C.gold);
      ctx.save();ctx.translate(0,-20);ctx.rotate(t*.8);line(ctx,9,0,48,0,'#294552',6);ctx.restore();}
    if(i===1){circle(ctx,0,-20,54,'#172e3d','#a7c0be',5);circle(ctx,0,-20,24,'#638b91');
      ctx.save();ctx.translate(0,-20);ctx.rotate(-t*.7);for(let k=0;k<4;k++){ctx.rotate(TAU/4);line(ctx,27,0,46,0,'#a9c4bf',4);}ctx.restore();}
    if(i===2){rr(ctx,-42,-62,84,84,7,'#94c4b0');for(let a=-1;a<=1;a++){line(ctx,-54,a*22-20,-42,a*22-20,C.light,4);line(ctx,42,a*22-20,54,a*22-20,C.light,4);}
      const signal=(t*.7)%1;rr(ctx,-32+signal*50,-30,14,14,3,C.cyan);}
    label(ctx,['CABLE','RUBBER','CHIPS'][i],0,73,30,C.ink);ctx.restore();});
}
function classicpair(ctx,t){
  classic(ctx,'3210',t,{x:65,y:125,scale:.68});classic(ctx,'3310',t,{x:415,y:125,scale:.68});
  arrow(ctx,264,293,396,293,phase(t,.5,1),C.cyan,6);
}
function features(ctx,t,beat){
  const nav=beat.headline.includes('NAVIGATION');
  const icons=nav?['PIN','WEB','APPS']:['CAMERA','MUSIC','WEB'];
  icons.forEach((name,i)=>{const p=phase(t,.18+i*.32,.6),x=120+i*230;ctx.save();ctx.translate(x,290+(1-p)*35);ctx.globalAlpha=p;
    rr(ctx,-93,-112,186,224,20,'#2f5c6d','#9ac6c2',3);
    if(name==='CAMERA'){rr(ctx,-51,-56,102,75,10,C.light);circle(ctx,0,-18,25,'#285466');circle(ctx,0,-18,10+4*(.5+.5*Math.sin(t*2)),C.cyan);}
    if(name==='MUSIC'){line(ctx,14,-68,14,8,C.light,9);line(ctx,14,-67,52,-76,C.light,9);line(ctx,52,-76,52,-4,C.light,9);circle(ctx,0,8,15,C.light);circle(ctx,38,-4,15,C.light);
      for(let k=0;k<2;k++){const r=15+((t*28+k*28)%50);ctx.globalAlpha=p*(1-(r-15)/50);arc(ctx,-12,-45,r,2.3,3.7,C.cyan,4);}ctx.globalAlpha=p;}
    if(name==='WEB'){circle(ctx,0,-22,50,null,C.light,4);ctx.beginPath();ctx.ellipse(0,-22,5+35*Math.abs(Math.cos(t*.6)),50,0,0,TAU);ctx.strokeStyle=C.light;ctx.lineWidth=3;ctx.stroke();line(ctx,-47,-22,47,-22,C.light,3);}
    if(name==='PIN'){poly(ctx,[[-45,-30],[-35,-65],[0,-80],[35,-65],[45,-30],[0,40]],C.light);circle(ctx,0,-35,15,'#285466');
      const r=12+((t*25)%40);ctx.globalAlpha=p*(1-(r-12)/40);circle(ctx,0,40,r,null,C.cyan,3);ctx.globalAlpha=p;}
    if(name==='APPS'){for(let r=0;r<2;r++)for(let c=0;c<2;c++)rr(ctx,-42+c*48,-67+r*48,36,36,7,C.light);}
    label(ctx,name,0,76,30,C.ink);ctx.restore();});
}
function contract(ctx,t){
  rr(ctx,148,98,404,455,16,'#d8e4df','#a8c4bf',4);rr(ctx,180,140,340,58,8,'#315b6b');label(ctx,'AGREEMENT',350,169,28,C.ink);
  ['DEVICES','ASSETS','LICENSES'].forEach((s,i)=>{const p=phase(t,.3+i*.4,.65);ctx.save();ctx.globalAlpha=p;
    rr(ctx,186,225+i*78,40,40,5,'#76a998');line(ctx,195,244+i*78,205,254+i*78,C.ink,4);line(ctx,205,254+i*78,219,234+i*78,C.ink,4);
    label(ctx,s,252,245+i*78,27,'#214657',700,'left');ctx.restore();});
}
function calendar(ctx,t,beat){
  const january=beat.headline.includes('JANUARY'), september=beat.headline.includes('SEPTEMBER');
  const month=january?'JANUARY 2007':september?'SEPTEMBER':'APRIL 2014';
  const day=january?'09':september?'2013':'25';
  rr(ctx,148,120,404,398,22,'#d9e6df','#b1d0c8',4);rr(ctx,148,120,404,105,22,'#3d7785');
  label(ctx,month,350,170,42,C.ink);label(ctx,day,350,344,september?100:150,'#234e5d');
  const p=phase(t,.65,1);arc(ctx,350,350,135,-Math.PI/2,-Math.PI/2+TAU*p,C.cyan,8);
}
function appointment(ctx,t){
  // A labeled, anonymous vector avatar: not a portrait of the named person.
  rr(ctx,125,110,450,420,24,'#214e60','#9dc4be',4);
  circle(ctx,350,245,65,'#aed2c8');poly(ctx,[[230,440],[242,364],[280,320],[350,302],[420,320],[458,364],[470,440]],'#aed2c8');
  const p=phase(t,.5,1);rr(ctx,164,470,372*p,7,4,C.cyan);label(ctx,'CHIEF EXECUTIVE',350,565,29,C.faint);
}
function convert(ctx,t){
  circle(ctx,160,305,105,'#325c6a','#b3d1c8',4);label(ctx,'€',160,305,100,C.ink);
  circle(ctx,540,305,105,'#325c6a','#b3d1c8',4);label(ctx,'$',540,305,100,C.ink);
  arrow(ctx,278,305,420,305,phase(t,.4,1.2),C.cyan,7);
  label(ctx,'APPROXIMATE VALUE',350,525,28,C.faint);
}
function netmerge(ctx,t,duration=6){
  // Move the two companies toward their shared network business, then reveal
  // the resulting infrastructure; no fabricated measure is implied.
  const p=clamp(t/Math.max(1,duration*.72)), fade=1-clamp((p-.7)/.3);
  ctx.save();ctx.globalAlpha=fade;ctx.translate(130*p,100*p);
  rr(ctx,55,150,240,125,18,'#315f70','#a2c9c6',3);label(ctx,'NOKIA',175,212,33,C.ink);ctx.restore();
  ctx.save();ctx.globalAlpha=fade;ctx.translate(-130*p,100*p);
  rr(ctx,405,150,240,125,18,'#315f70','#a2c9c6',3);label(ctx,'ALCATEL',525,200,30,C.ink);label(ctx,'LUCENT',525,237,30,C.ink);ctx.restore();
  const q=clamp((p-.35)/.65);circle(ctx,350,420,40+75*q,blend('#315f70','#b7e2d3',q),'#a2c9c6',4);
  if(q>.4){ctx.save();ctx.globalAlpha=clamp((q-.4)/.2);label(ctx,'NETWORKS',350,420,25,q>.55?'#183b48':C.ink);ctx.restore();}
  arrow(ctx,190,535,275,455,clamp((t-duration*.58)/(duration*.35)),C.cyan,6);
  arrow(ctx,510,535,425,455,clamp((t-duration*.58)/(duration*.35)),C.cyan,6);
}
function drawVisual(ctx,visual,t,beat){
  const duration=(beat.motionEndFrame-beat.motionStartFrame)/beat.fps;
  if(visual==='origin')return origin(ctx,t);
  if(visual==='river')return river(ctx,t);
  if(visual==='name')return nameGraphic(ctx,t);
  if(visual==='portfolio')return portfolio(ctx,t);
  if(visual==='classicpair')return classicpair(ctx,t);
  if(visual==='functions')return features(ctx,t,beat);
  if(visual==='contract')return contract(ctx,t);
  if(visual==='calendar')return calendar(ctx,t,beat);
  if(visual==='appointment')return appointment(ctx,t);
  if(visual==='convert')return convert(ctx,t);
  if(visual==='netmerge')return netmerge(ctx,t,duration);
  if(['cityman','1011','3210','3310','snake'].includes(visual)) return classic(ctx,visual,t);
  if(['iphone','5800','lumia','apps'].includes(visual)) return smartphone(ctx,visual==='apps'?'iphone':visual,t);
  if(visual==='9000')return communicator(ctx,t);
  if(visual==='g1')return g1(ctx,t);
  if(visual==='tower')return tower(ctx,t);
  if(visual==='mill')return mill(ctx,t);
  if(visual==='industry')return industry(ctx,t);
  if(visual==='factory')return factory(ctx,t);
  if(visual==='distribution')return globe(ctx,t);
  if(visual==='car')return car(ctx,t);
  if(visual==='stage')return stage(ctx,t);
  if(visual==='software')return code(ctx,t,duration);
  if(visual==='platform')return platform(ctx,t,duration);
  if(visual==='ecosystem')return ecosystem(ctx,t);
  if(visual==='share')return share(ctx,t);
  if(visual==='sharegrid')return sharegrid(ctx,t,duration);
  if(visual==='merger')return merger(ctx,t);
  if(visual==='strategy')return strategy(ctx,t,duration);
  if(visual==='memo')return memo(ctx,t);
  if(visual==='burning')return burning(ctx,t);
  if(visual==='deal')return deal(ctx,t,duration);
  if(visual==='compare')return compare(ctx,t);
  if(visual==='covers')return covers(ctx,t);
  if(visual==='durable')return durable(ctx,t);
  throw new Error(`unknown visual ${visual}`);
}

function chapterColor(scene){return scene<=1?'#10213a':scene<=5?'#133348':scene<=8?'#19284b':scene<=11?'#312634':'#183e42';}
const backgrounds=new Map();
function mirrored(scene){return [2,4,7,10,12].includes(scene);}
function background(scene){
  const tone=chapterColor(scene), mirror=mirrored(scene),key=`${tone}-${mirror}`;if(backgrounds.has(key))return backgrounds.get(key);
  const c=createCanvas(W,H),ctx=c.getContext('2d');
  const g=ctx.createLinearGradient(mirror?W:0,0,mirror?0:W,H);g.addColorStop(0,'#081522');g.addColorStop(.55,tone);g.addColorStop(1,'#091723');
  ctx.fillStyle=g;ctx.fillRect(0,0,W,H);
  const cx=mirror?530:1434;
  ctx.fillStyle='rgba(139,213,213,.06)';ctx.beginPath();ctx.arc(cx,506,380,0,TAU);ctx.fill();
  ctx.strokeStyle='rgba(169,215,210,.11)';ctx.lineWidth=2;ctx.beginPath();ctx.arc(cx,506,380,0,TAU);ctx.stroke();
  // quiet title-safe rules; these are not used as artificial motion.
  ctx.fillStyle='rgba(162,197,207,.20)';ctx.fillRect(126,967,1668,2);backgrounds.set(key,c);return c;
}
function wrap(ctx,text,width){
  const lines=[];for(const paragraph of text.split('\n')){let current='';for(const word of paragraph.split(/\s+/)){
    const next=current?`${current} ${word}`:word;if(current&&ctx.measureText(next).width>width){lines.push(current);current=word;}else current=next;
  }if(current)lines.push(current);}return lines;
}
function headlineLayout(ctx,text){
  for(let size=80;size>=44;size-=2){ctx.font=`700 ${size}px "Space Grotesk", sans-serif`;
    const lines=wrap(ctx,text,760);if(lines.length<=4&&lines.every(l=>ctx.measureText(l).width<=760))return {size,lines};}
  throw new Error(`headline cannot fit: ${text}`);
}
// Cache only a few text layers: allocation is bounded even for long films.
const textCache=new Map();
function textLayers(beat){
  const key=`${beat.shot}|${beat.headline}|${beat.detail}`;if(textCache.has(key))return textCache.get(key);
  const heading=createCanvas(850,610),detail=createCanvas(850,180);const ctx=heading.getContext('2d');
  const {size,lines}=headlineLayout(ctx,beat.headline);ctx.font=`700 ${size}px "Space Grotesk", sans-serif`;
  ctx.fillStyle=C.ink;ctx.textBaseline='top';lines.forEach((s,i)=>ctx.fillText(s,0,i*size*1.16));
  const dy=Math.min(610-80,lines.length*size*1.16+48);
  const d=detail.getContext('2d');d.font='400 42px "Inter", sans-serif';d.fillStyle='#c5d9d8';d.textBaseline='top';
  const details=wrap(d,beat.detail,760);if(details.length>3)throw new Error(`detail too long: ${beat.detail}`);
  details.forEach((s,i)=>d.fillText(s,0,i*54));
  const result={heading,detail,dy};textCache.set(key,result);if(textCache.size>6)textCache.delete(textCache.keys().next().value);return result;
}
export function drawFrame(ctx,beat,t,graphicTime=t){
  ctx.setTransform(1,0,0,1,0,0);ctx.globalAlpha=1;ctx.drawImage(background(beat.scene),0,0);
  const layers=textLayers(beat);const a=phase(t,0,.5);const b=phase(t,.17,.55);
  const mirror=mirrored(beat.scene), textX=mirror?1000:126, graphicX=mirror?180:1080;
  ctx.save();ctx.fillStyle=C.cyan;ctx.fillRect(textX,102,8,42);
  label(ctx,`${String(beat.scene).padStart(2,'0')}  /  ${CHAPTER[beat.scene]}`,textX+24,125,25,C.faint,700,'left');
  ctx.translate(textX+(1-a)*32,259);ctx.globalAlpha=a;ctx.drawImage(layers.heading,0,0);
  ctx.globalAlpha=b;ctx.drawImage(layers.detail,0,layers.dy);ctx.restore();
  ctx.save();ctx.globalAlpha=phase(graphicTime,.06,.65);ctx.translate(graphicX,188+(1-phase(graphicTime,.05,.8))*30);
  // Subject movement and per-element animation are rendered at the output fps;
  // no still-image panning or interpolation of the earlier film is used.
  drawVisual(ctx,beat.visual,graphicTime,beat);ctx.restore();
  label(ctx,'ILLUSTRATIVE MOTION GRAPHICS',126,1013,21,C.faint,700,'left');
  label(ctx,'NOKIA  /  REVIEW DRAFT',1794,1013,21,C.faint,700,'right');
}
function beatIndexAt(timeline,frame){
  let l=0,r=timeline.length-1;while(l<r){const m=Math.floor((l+r+1)/2);if(timeline[m].startFrame<=frame)l=m;else r=m-1;}return l;
}
let transitionCanvas;
function drawAtFrame(ctx,timeline,frame,fps){
  const index=beatIndexAt(timeline,frame),beat=timeline[index],t=(frame-beat.startFrame)/fps;
  if(index>0&&t<.34){
    // Keep the outgoing shot alive during a short circular masked reveal; this
    // avoids dissolving two sets of words together. Both shots remain animated.
    const prev=timeline[index-1];drawFrame(ctx,prev,(frame-prev.startFrame)/fps,(frame-prev.motionStartFrame)/fps);
    if(!transitionCanvas)transitionCanvas=createCanvas(W,H);
    drawFrame(transitionCanvas.getContext('2d'),beat,t,(frame-beat.motionStartFrame)/fps);
    ctx.save();ctx.beginPath();ctx.arc(W/2,H/2,Math.hypot(W/2,H/2)*ease(t/.34),0,TAU);ctx.clip();
    ctx.drawImage(transitionCanvas,0,0);ctx.restore();
  }else drawFrame(ctx,beat,t,(frame-beat.motionStartFrame)/fps);
}
function readJson(file){return JSON.parse(fs.readFileSync(file,'utf8'));}
function argValue(args,name,fallback=null){const i=args.indexOf(name);if(i<0)return fallback;if(!args[i+1]||args[i+1].startsWith('--'))throw new Error(`${name} requires a value`);return args[i+1];}
async function main(){
  const args=process.argv.slice(2);const fps=Number(argValue(args,'--fps','30'));loadFonts();
  const phraseTiming=fs.existsSync(PHRASES)?readJson(PHRASES):null;
  if(!phraseTiming&&!args.includes('--estimate'))throw new Error('phrase timing missing; recover it or explicitly use --estimate for a scratch render');
  const plan=readJson(PLAN), shots=readJson(SHOTS), voice=readJson(VOICE);
  const timeline=buildTimeline(plan,shots,voice,fps,phraseTiming);
  if(args.includes('--validate')){
    const longest=Math.max(...timeline.map(b=>b.end-b.start));const shortest=Math.min(...timeline.map(b=>b.end-b.start));
    console.log(JSON.stringify({shots:new Set(timeline.map(b=>b.shot)).size,beats:timeline.length,fps,
      duration:timeline.at(-1).end,longestBeat:longest,shortestBeat:shortest,visuals:[...new Set(timeline.map(b=>b.visual))],
      timing:phraseTiming?'phrase boundaries reconstructed; within-phrase cues estimated; human review required':'all intra-line cues estimated; human review required'},null,2));return;
  }
  const storyboard=argValue(args,'--storyboard');
  if(storyboard){
    const scenes=[];
    for(const shot of shots){
      let scene=scenes.find(item=>item.scene===shot.scene);
      if(!scene){scene={scene:shot.scene,shots:[]};scenes.push(scene);}
      const narration=voice.find(row=>row.shot===shot.id);
      scene.shots.push({id:shot.id,scene:shot.scene,start:shot.start,end:shot.end,voStart:narration.start,
        transition:'0.34-second animated circular masked reveal',
        narration:narration.text,
        visualCues:timeline.filter(b=>b.shot===shot.id).map(({cue,visual,headline,detail,start,end,approximateCue})=>
          ({cue,visual,headline,detail,start,end,approximateCue}))});
    }
    const result={title:'Nokia: The Rise, Fall, and Reinvention of a Phone Giant',status:'unapproved motion-graphics review draft',
      cueTiming:'Narration clip clock is measured; intra-phrase positions are estimates, not word-level alignment. Human listening/visual review required.',
      fps,scenes};
    fs.mkdirSync(path.dirname(path.resolve(storyboard)),{recursive:true});fs.writeFileSync(storyboard,JSON.stringify(result,null,2)+'\n');
    console.error(`wrote ${timeline.length} storyboard beats`);return;
  }
  const canvas=createCanvas(W,H),ctx=canvas.getContext('2d');
  if(args.includes('--render-check')){
    for(const beat of timeline)drawFrame(ctx,beat,(beat.endFrame-beat.startFrame)/(2*fps));
    console.log(`Drew ${timeline.length} planned graphics at ${W}x${H}; content and synchronization still require human review.`);return;
  }
  const sample=argValue(args,'--sample');
  if(sample!==null){const time=Number(sample),output=argValue(args,'--out');
    if(!output||!Number.isFinite(time)||time<0||time>=timeline.at(-1).end)throw new Error('invalid sample time/output');
    const frame=Math.floor(time*fps),beat=timeline[beatIndexAt(timeline,frame)];drawAtFrame(ctx,timeline,frame,fps);
    fs.mkdirSync(path.dirname(path.resolve(output)),{recursive:true});fs.writeFileSync(output,canvas.toBuffer('image/png'));
    console.error(`sample ${time}s: ${beat.shot} ${beat.visual} ${beat.headline}`);return;
  }
  if(!args.includes('--pipe'))throw new Error('choose --validate, --sample, or --pipe');
  const from=Number(argValue(args,'--from','0'));const to=Number(argValue(args,'--to',String(timeline.at(-1).endFrame)));
  if(!Number.isInteger(from)||!Number.isInteger(to)||from<0||to<=from||to>timeline.at(-1).endFrame)throw new Error('invalid frame range');
  for(let frame=from;frame<to;frame++){
    drawAtFrame(ctx,timeline,frame,fps);
    if(!process.stdout.write(canvas.data()))await new Promise(resolve=>process.stdout.once('drain',resolve));
    if(frame>from&&(frame-from)%1500===0)console.error(`rendered ${frame-from}/${to-from} frames`);
  }
}
if(process.argv[1]&&import.meta.url===`file://${path.resolve(process.argv[1])}`){main().catch(e=>{console.error(`Nokia motion review: ${e.message}`);process.exitCode=2;});}
