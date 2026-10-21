#!/usr/bin/env node
"use strict";
const fs=require("fs"),path=require("path"),puppeteer=require("puppeteer"),impactFrames=require("./impact_frames");
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
 const transitionTypes=new Set(["none","fade","wipe-left","wipe-right","slide-left","slide-right","zoom"]);
 for(const [index,scene] of s.scenes.entries()){
  if(!scene||typeof scene!=="object"||Array.isArray(scene))throw new Error("Scene "+index+" must be a JSON object.");
  const kind=String(scene.visual_type||"hero").toLowerCase();
  if(!visualTypes.has(kind))throw new Error("Unsupported visual_type in scene "+index+": "+kind);
  const transition=String(scene.transition_in||"none").toLowerCase();
  if(!transitionTypes.has(transition))throw new Error("Unsupported transition_in in scene "+index+": "+transition);
  scene.transition_in=transition;
  if(scene.transition_frames!==undefined&&(!Number.isInteger(Number(scene.transition_frames))||Number(scene.transition_frames)<1||Number(scene.transition_frames)>60))throw new Error("transition_frames must be an integer from 1 to 60.");
  scene._impact_events=impactFrames.normalizeImpactEvents(scene,index,fps);
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
 impactFrames.assertUniqueImpactEventIds(s.scenes);
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
  const directionCheck=await page.evaluate(()=>({
   urdu:window.textDirectionForTest("یہ Python API ہے"),
   english:window.textDirectionForTest("English API")
  }));
  if(directionCheck.urdu!=="rtl"||directionCheck.english!=="ltr")throw new Error("Script-direction regression: Urdu must be RTL and English LTR. "+JSON.stringify(directionCheck));
  const rigCheck=await page.evaluate(()=>window.characterRigCapabilitiesForTest());
  const requiredJoints=["shoulder","elbow","wrist","hip","knee","ankle","neck","head"];
  const requiredVisemes=["closed","open","wide","round","teeth","tongue","sibilant","lip","open_wide","open_round"];
  if(!rigCheck||rigCheck.version!==2||!requiredJoints.every(x=>rigCheck.joints.includes(x))||!requiredVisemes.every(x=>rigCheck.visemeShapes.includes(x)))throw new Error("Character-rig capability regression: "+JSON.stringify(rigCheck));
  const rigDrawCheck=await page.evaluate(()=>{
   const shapes=window.characterRigCapabilitiesForTest().visemeShapes;
   for(const shape of shapes){
    window.drawCharacterForTest({enabled:true,x:0.5,y:0.5,scale:0.2,expression:"curious",pose:"explain",visemes:[{t:0,shape},{t:1,shape}]},0.5,42);
   }
   const canvas=document.getElementById("frame");return {shapes_drawn:shapes.length,canvas_width:canvas.width,canvas_height:canvas.height};
  });
  if(!rigDrawCheck||rigDrawCheck.shapes_drawn!==requiredVisemes.length||rigDrawCheck.canvas_width!==w||rigDrawCheck.canvas_height!==h)throw new Error("Character-rig draw smoke check failed: "+JSON.stringify(rigDrawCheck));
  const captionCheck=await page.evaluate(()=>{
   const text=Array.from({length:80},(_,i)=>"captionword"+i).join(" ");
   const info=window.captionPageForTest(text,180,"16px Arial",0.5);
   const first=window.captionPageForTest(text,180,"16px Arial",0);
   const last=window.captionPageForTest(text,180,"16px Arial",0.99999);
   return {totalLines:info.allLines.length,totalPages:info.totalPages,firstIndex:first.pageIndex,lastIndex:last.pageIndex};
  });
  if(captionCheck.totalPages<2||captionCheck.firstIndex!==0||captionCheck.lastIndex!==captionCheck.totalPages-1)throw new Error("Caption pagination regression: long narration is not split across readable pages.");
  const impactPixelSmoke=await page.evaluate((types)=>{
   const canvas=document.getElementById("frame"),ctx=canvas.getContext("2d"),base={visual_type:"quote",headline:"Impact test",subhead:"Pixel-difference smoke check",caption:"Readable text stays in front"};
   const changedPixels=(a,b)=>{let count=0;for(let i=0;i<a.length;i+=4)if(Math.abs(a[i]-b[i])>12||Math.abs(a[i+1]-b[i+1])>12||Math.abs(a[i+2]-b[i+2])>12)count++;return count;};
   const results={};for(const type of types){window.drawFrame(base,15,30,15,true);const a=ctx.getImageData(0,0,canvas.width,canvas.height).data;const event={id:"pixel-probe-"+type,type,start_frame:15,duration_frames:2,intensity:.65,x:.52,y:.5};window.drawFrame({...base,_impact_events:[event]},15,30,15,true);const b=ctx.getImageData(0,0,canvas.width,canvas.height).data;results[type]=changedPixels(a,b);}
   return {passed:Object.values(results).every(n=>n>=20),changed_pixels:results,types_tested:types};
  },impactFrames.IMPACT_TYPES);
  if(!impactPixelSmoke||impactPixelSmoke.passed!==true)throw new Error("Impact-frame pixel smoke failed: "+JSON.stringify(impactPixelSmoke));
  console.log("Impact-frame pixel smoke:",JSON.stringify(impactPixelSmoke));
  let total=0;
  const transitionRecords=[];
  const impactEvents=[];
  for(let si=0;si<s.scenes.length;si++){
   const scene=s.scenes[si],sec=Number(scene.duration_seconds);
   if(!Number.isFinite(sec)||sec<=0||sec>600)throw new Error("scene duration must be >0 and <=600 seconds");
   const count=Math.max(1,Math.round(sec*fps));
   for(const event of (scene._impact_events||[]))impactEvents.push({id:event.id,scene:si+1,type:event.type,frame:total+event.start_frame,timestamp_seconds:Number(((total+event.start_frame)/fps).toFixed(6)),scene_frame:event.start_frame,duration_frames:event.duration_frames,duration_seconds:Number((event.duration_frames/fps).toFixed(6)),intensity:event.intensity,x:event.x,y:event.y,pixel_smoke_test_passed:impactPixelSmoke.passed});
   const previous=si>0?s.scenes[si-1]:null;
   const requested=Number(scene.transition_frames)||12;
   const transitionFrames=previous&&scene.transition_in!=="none"?Math.min(count,Math.max(1,Math.min(60,Math.round(requested)))):0;
   transitionRecords.push({scene:si+1,type:scene.transition_in,frames:transitionFrames});
   const previousCount=previous?Math.max(1,Math.round(Number(previous.duration_seconds)*fps)):0;
   for(let lf=0;lf<count;lf++){
    if(transitionFrames&&lf<transitionFrames){
     const t=transitionFrames<=1?1:lf/(transitionFrames-1);
     await page.evaluate((prev,pf,pc,pg,cur,cf,cc,cg,kind,progress)=>window.drawTransitionFrame(prev,pf,pc,pg,cur,cf,cc,cg,kind,progress),previous,previousCount-1,previousCount,Math.max(0,total-1),scene,lf,count,total,String(scene.transition_in),t);
    }else{ await page.evaluate((sc,l,n,g)=>window.drawFrame(sc,l,n,g),scene,lf,count,total); }
    await page.screenshot({path:path.join(dir,"frame-"+String(total).padStart(6,"0")+".png"),type:"png"});total++;
   }
   console.log("Rendered scene "+(si+1)+"/"+s.scenes.length+" ("+count+" frames)");
  }
  fs.writeFileSync(path.resolve(__dirname,"render-manifest.json"),JSON.stringify({title:String(s.title||"Offline Agent HQ video"),width:w,height:h,fps,frame_count:total,duration_seconds:total/fps,scene_count:s.scenes.length,transitions:transitionRecords,impact_events:impactEvents,impact_pixel_smoke:impactPixelSmoke,generated_at:new Date().toISOString()},null,2)+"\n");
  console.log("Rendered "+total+" frames to "+dir);
 }finally{await browser.close()}
}
main().catch(e=>{console.error("RENDER ERROR: "+(e&&e.message?e.message:String(e)));process.exitCode=1});
