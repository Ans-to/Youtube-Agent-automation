#!/usr/bin/env node
"use strict";
const fs=require("fs"),path=require("path"),puppeteer=require("puppeteer");
async function main(){
 const storyboardPath=path.resolve(process.argv[2]||"storyboard.example.json");
 if(!fs.existsSync(storyboardPath))throw new Error("Storyboard not found: "+storyboardPath);
 const s=JSON.parse(fs.readFileSync(storyboardPath,"utf8")),w=Number(s.width||1920),h=Number(s.height||1080),fps=Number(s.fps||30);
 if(!Number.isInteger(w)||w<320||w>3840)throw new Error("width must be 320..3840");
 if(!Number.isInteger(h)||h<180||h>2160)throw new Error("height must be 180..2160");
 if(!Number.isInteger(fps)||fps<1||fps>60)throw new Error("fps must be 1..60");
 if(!Array.isArray(s.scenes)||s.scenes.length<1||s.scenes.length>100)throw new Error("scenes must contain 1..100 entries");
 const visualTypes=new Set(["hero","stat","timeline","diagram","comparison","code","quote","waveform","kinetic-type","bar-chart"]);
 const transitionTypes=new Set(["none","fade","wipe-left","wipe-right"]);
 for(const [index,scene] of s.scenes.entries()){
  if(!scene||typeof scene!=="object"||Array.isArray(scene))throw new Error("Scene "+index+" must be a JSON object.");
  const kind=String(scene.visual_type||"hero").toLowerCase();
  if(!visualTypes.has(kind))throw new Error("Unsupported visual_type in scene "+index+": "+kind);
  const transition=String(scene.transition_in||"none").toLowerCase();
  if(!transitionTypes.has(transition))throw new Error("Unsupported transition_in in scene "+index+": "+transition);
  if(scene.transition_frames!==undefined&&(!Number.isInteger(Number(scene.transition_frames))||Number(scene.transition_frames)<1||Number(scene.transition_frames)>60))throw new Error("transition_frames must be an integer from 1 to 60.");
  for(const key of ["headline","eyebrow","subhead","narration"])if(scene[key]!==undefined&&typeof scene[key]!=="string")throw new Error("Scene "+index+" field "+key+" must be text.");
  for(const key of ["headline","eyebrow","subhead","narration","stat_value","stat_label","quote","quote_source","graphic_label","comparison_left_title","comparison_right_title"])if(scene[key]!==undefined&&typeof scene[key]==="string"&&scene[key].length>12000)throw new Error("Scene "+index+" field "+key+" exceeds the 12000-character safety limit.");
  for(const key of ["visual_nodes","timeline_events","comparison_left","comparison_right","code_lines","chart_labels"])if(scene[key]!==undefined&&(!Array.isArray(scene[key])||scene[key].length>8||!scene[key].every(v=>typeof v==="string"&&v.length<=120)))throw new Error("Scene "+index+" field "+key+" must be an array of at most 8 short strings.");
  if(scene.chart_values!==undefined&&(!Array.isArray(scene.chart_values)||scene.chart_values.length<2||scene.chart_values.length>6||!scene.chart_values.every(v=>typeof v==="number"&&Number.isFinite(v)&&v>=0)))throw new Error("Scene "+index+" chart_values must contain 2–6 finite non-negative numbers.");
  if(kind==="bar-chart"){
   if(!Array.isArray(scene.chart_values)||scene.chart_values.length<2||scene.chart_values.length>6)throw new Error("bar-chart requires 2–6 chart_values.");
   if(!Array.isArray(scene.chart_labels)||scene.chart_labels.length!==scene.chart_values.length)throw new Error("bar-chart requires one chart_label per chart_value.");
  }
 }
 const MAX_FRAMES=30000,MAX_SECONDS=1000;
 const totalSeconds=s.scenes.reduce((sum,scene)=>{const sec=Number(scene&&scene.duration_seconds);if(!Number.isFinite(sec)||sec<=0||sec>600)throw new Error("Each scene duration must be >0 and <=600 seconds");return sum+sec;},0);
 if(totalSeconds>MAX_SECONDS)throw new Error("Storyboard exceeds the 1000-second render limit.");
 const estimatedFrames=s.scenes.reduce((sum,scene)=>sum+Math.max(1,Math.round(Number(scene.duration_seconds)*fps)),0);
 if(estimatedFrames>MAX_FRAMES)throw new Error("Storyboard exceeds the 30000-frame render limit.");
 const dir=path.resolve(__dirname,"frames");fs.mkdirSync(dir,{recursive:true});
 for(const f of fs.readdirSync(dir))if(/^frame-\d{6}\.png$/.test(f))fs.unlinkSync(path.join(dir,f));
 const browser=await puppeteer.launch({headless:true,args:["--no-sandbox","--disable-setuid-sandbox"]});
 try{
  const page=await browser.newPage({viewport:{width:w,height:h},deviceScaleFactor:1});
  await page.goto("file://"+path.resolve(__dirname,"render.html"),{waitUntil:"load"});await page.setViewport({width:w,height:h,deviceScaleFactor:1});
  await page.evaluate((width,height)=>window.setCanvasSize(width,height),w,h);
  const wrapCheck=await page.evaluate(()=>window.measureWrappedLines("word ".repeat(80),180,"16px Arial"));
  if(!Number.isInteger(wrapCheck)||wrapCheck<2)throw new Error("Text wrapping regression: long text did not wrap to multiple lines.");
  let total=0;
  for(let si=0;si<s.scenes.length;si++){
   const scene=s.scenes[si],sec=Number(scene.duration_seconds);
   if(!Number.isFinite(sec)||sec<=0||sec>600)throw new Error("scene duration must be >0 and <=600 seconds");
   const count=Math.max(1,Math.round(sec*fps));
   for(let lf=0;lf<count;lf++){
    await page.evaluate((sc,l,n,g)=>window.drawFrame(sc,l,n,g),scene,lf,count,total);
    await page.screenshot({path:path.join(dir,"frame-"+String(total).padStart(6,"0")+".png"),type:"png"});total++;
   }
   console.log("Rendered scene "+(si+1)+"/"+s.scenes.length+" ("+count+" frames)");
  }
  fs.writeFileSync(path.resolve(__dirname,"render-manifest.json"),JSON.stringify({title:String(s.title||"Offline Agent HQ video"),width:w,height:h,fps,frame_count:total,duration_seconds:total/fps,scene_count:s.scenes.length,generated_at:new Date().toISOString()},null,2)+"\n");
  console.log("Rendered "+total+" frames to "+dir);
 }finally{await browser.close()}
}
main().catch(e=>{console.error("RENDER ERROR: "+(e&&e.message?e.message:String(e)));process.exitCode=1});
