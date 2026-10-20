#!/usr/bin/env node
"use strict";
const fs=require("fs"),path=require("path"),puppeteer=require("puppeteer");
async function main(){
 const storyboardPath=path.resolve(process.argv[2]||"storyboard.example.json");
 if(!fs.existsSync(storyboardPath))throw new Error("Storyboard not found: "+storyboardPath);
 const s=JSON.parse(fs.readFileSync(storyboardPath,"utf8"));
 if(!s||typeof s!=="object"||Array.isArray(s))throw new Error("Storyboard root must be a JSON object.");
 const w=s.width===undefined?1920:Number(s.width),h=s.height===undefined?1080:Number(s.height),fps=s.fps===undefined?30:Number(s.fps);
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
  if(scene.transition_frames!==undefined&&(!Number.isInteger(Number(scene.transition_frames))||Number(scene.transition_frames)<1||Number(scene.transition_frames)>60))throw new Error("transition_frames must be an integer from 1 to 60.");\n  if(scene.transition_frames!==undefined&&Number(scene.transition_frames)<15)throw new Error("transition_frames below 15 are disallowed: micro-transitions look like flashes.");
  for(const key of ["headline","eyebrow","subhead","narration","caption"])if(scene[key]!==undefined&&typeof scene[key]!=="string")throw new Error("Scene "+index+" field "+key+" must be text.");
  for(const key of ["headline","eyebrow","subhead","narration","stat_value","stat_label","quote","quote_source","graphic_label","comparison_left_title","comparison_right_title"])if(scene[key]!==undefined&&typeof scene[key]==="string"&&scene[key].length>12000)throw new Error("Scene "+index+" field "+key+" exceeds the 12000-character safety limit.");
  const arrayLimits={visual_nodes:4,timeline_events:4,comparison_left:3,comparison_right:3,code_lines:6,chart_labels:6};
  for(const [key,maxItems] of Object.entries(arrayLimits))if(scene[key]!==undefined&&(!Array.isArray(scene[key])||scene[key].length>maxItems||!scene[key].every(v=>typeof v==="string"&&v.length<=120)))throw new Error("Scene "+index+" field "+key+" must be an array of at most "+maxItems+" short strings.");
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
  const captionCheck=await page.evaluate(()=>{
   const text=Array.from({length:80},(_,i)=>"captionword"+i).join(" ");
   const info=window.captionPageForTest(text,180,"16px Arial",0.5);
   const first=window.captionPageForTest(text,180,"16px Arial",0);
   const last=window.captionPageForTest(text,180,"16px Arial",0.99999);
   return {totalLines:info.allLines.length,totalPages:info.totalPages,firstIndex:first.pageIndex,lastIndex:last.pageIndex};
  });
  if(captionCheck.totalPages<2||captionCheck.firstIndex!==0||captionCheck.lastIndex!==captionCheck.totalPages-1)throw new Error("Caption pagination regression: long narration is not split across readable pages.");
  let total=0,previousFrameUrl=null;
  for(let si=0;si<s.scenes.length;si++){
   const scene=s.scenes[si],sec=Number(scene.duration_seconds);
   if(!Number.isFinite(sec)||sec<=0||sec>600)throw new Error("scene duration must be >0 and <=600 seconds");
   const count=Math.max(1,Math.round(sec*fps));
   const transition=String(scene.transition_in||"none").toLowerCase();
   const transitionFrames=Math.min(count,Math.max(15,Math.min(24,Number(scene.transition_frames)||18)));
   for(let lf=0;lf<count;lf++){
    await page.evaluate((sc,l,n,g)=>window.drawFrame(sc,l,n,g),scene,lf,count,total);
    if(si>0&&previousFrameUrl&&transition!=="none"&&lf<transitionFrames){
     await page.evaluate(async(previousUrl,type,progress)=>{
      const canvas=document.getElementById("frame"),ctx=canvas.getContext("2d");
      const oldFrame=new Image();oldFrame.src=previousUrl;
      await new Promise((resolve,reject)=>{if(oldFrame.complete)return resolve();oldFrame.onload=resolve;oldFrame.onerror=reject;});
      ctx.save();
      if(type==="wipe-left"||type==="wipe-right"){
       const reveal=Math.round(canvas.width*progress);
       if(type==="wipe-left"){ctx.beginPath();ctx.rect(reveal,0,canvas.width-reveal,canvas.height);}
       else{ctx.beginPath();ctx.rect(0,0,canvas.width-reveal,canvas.height);}
       ctx.clip();ctx.drawImage(oldFrame,0,0,canvas.width,canvas.height);
      }else{
       ctx.globalAlpha=1-progress;
       ctx.drawImage(oldFrame,0,0,canvas.width,canvas.height);
      }
      ctx.restore();
     },previousFrameUrl,transition,(lf+1)/transitionFrames);
    }
    await page.screenshot({path:path.join(dir,"frame-"+String(total).padStart(6,"0")+".png"),type:"png"});total++;
   }
   previousFrameUrl=await page.evaluate(()=>document.getElementById("frame").toDataURL("image/png"));
   console.log("Rendered scene "+(si+1)+"/"+s.scenes.length+" ("+count+" frames; transition="+transition+")");
  }
  fs.writeFileSync(path.resolve(__dirname,"render-manifest.json"),JSON.stringify({title:String(s.title||"Offline Agent HQ video"),width:w,height:h,fps,frame_count:total,duration_seconds:total/fps,scene_count:s.scenes.length,generated_at:new Date().toISOString()},null,2)+"\n");
  console.log("Rendered "+total+" frames to "+dir);
 }finally{await browser.close()}
}
main().catch(e=>{console.error("RENDER ERROR: "+(e&&e.message?e.message:String(e)));process.exitCode=1});
