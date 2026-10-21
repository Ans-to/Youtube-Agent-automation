#!/usr/bin/env node
"use strict";
const fs=require("fs"),path=require("path"),http=require("http"),puppeteer=require("puppeteer");
async function main(){
 const storyboardPath=path.resolve(process.argv[2]||"storyboard.example.json");
 if(!fs.existsSync(storyboardPath))throw new Error("Storyboard not found: "+storyboardPath);
 const s=JSON.parse(fs.readFileSync(storyboardPath,"utf8"));
 if(!s||typeof s!=="object"||Array.isArray(s))throw new Error("Storyboard root must be a JSON object.");
 const w=s.width===undefined?1920:Number(s.width),h=s.height===undefined?1080:Number(s.height),fps=s.fps===undefined?30:Number(s.fps);
 if(!Number.isInteger(w)||w<320||w>3840)throw new Error("width must be 320..3840");
 if(!Number.isInteger(h)||h<180||h>3840)throw new Error("height must be 180..3840");
 if(!Number.isInteger(fps)||fps<1||fps>60)throw new Error("fps must be 1..60");
 if(!Array.isArray(s.scenes)||s.scenes.length<1||s.scenes.length>100)throw new Error("scenes must contain 1..100 entries");
 const visualTypes=new Set(["hero","stat","timeline","diagram","comparison","code","quote","waveform","kinetic-type","bar-chart"]);
 const transitionTypes=new Set(["none","cut","whip-pan","masked-reveal","morph","glitch","match-cut","fade","wipe-left","wipe-right","slide-left","slide-right","zoom","push","dissolve"]);
 const easingTypes=new Set(["editorial","entrance","exit","settle","snap","glide","dramatic"]);
 const toneTypes=new Set(["corporate","edgy","minimalist","cinematic","playful"]);
 const paletteKeys=["bg","panel","fg","muted","accent","support","grid","line","scrim"];
 const cameraMotionTypes=new Set(["static","push-in","pull-out","pan-left","pan-right","drift"]);
 for(const [index,scene] of s.scenes.entries()){
  if(!scene||typeof scene!=="object"||Array.isArray(scene))throw new Error("Scene "+index+" must be a JSON object.");
  const kind=String(scene.visual_type||"hero").toLowerCase();
  if(!visualTypes.has(kind))throw new Error("Unsupported visual_type in scene "+index+": "+kind);
  const transition=String(scene.transition_in||"none").toLowerCase();
  if(!transitionTypes.has(transition))throw new Error("Unsupported transition_in in scene "+index+": "+transition);
  scene.transition_in=transition;
  const cameraMotion=String(scene.camera_motion||"static").toLowerCase();
  if(!cameraMotionTypes.has(cameraMotion))throw new Error("Unsupported camera_motion in scene "+index+": "+cameraMotion);
  scene.camera_motion=cameraMotion;
  if(scene.character!==undefined&&scene.character!==null){
   if(typeof scene.character!=="object"||Array.isArray(scene.character))throw new Error("Scene "+index+" character must be an object.");
   for(const key of ["x","y","walk_from_x","walk_to_x"])if(scene.character[key]!==undefined&&(!Number.isFinite(Number(scene.character[key]))||Number(scene.character[key])<0||Number(scene.character[key])>1))throw new Error("Scene "+index+" character "+key+" must be between 0 and 1.");
   if(scene.character.walking!==undefined&&![0,1,false,true].includes(scene.character.walking))throw new Error("Scene "+index+" character walking must be 0 or 1.");
  }
  if(scene.transition_frames!==undefined&&(!Number.isInteger(Number(scene.transition_frames))||Number(scene.transition_frames)<0||Number(scene.transition_frames)>60))throw new Error("transition_frames must be an integer from 0 to 60; 0 is a hard cut.");
  for(const key of ["headline","eyebrow","subhead","narration","caption"])if(scene[key]!==undefined&&typeof scene[key]!=="string")throw new Error("Scene "+index+" field "+key+" must be text.");
  for(const key of ["headline","eyebrow","subhead","narration","stat_value","stat_label","quote","quote_source","graphic_label","comparison_left_title","comparison_right_title"])if(scene[key]!==undefined&&typeof scene[key]==="string"&&scene[key].length>12000)throw new Error("Scene "+index+" field "+key+" exceeds the 12000-character safety limit.");
  const arrayLimits={visual_nodes:4,timeline_events:4,comparison_left:3,comparison_right:3,code_lines:6,chart_labels:6};
  for(const [key,maxItems] of Object.entries(arrayLimits))if(scene[key]!==undefined&&(!Array.isArray(scene[key])||scene[key].length>maxItems||!scene[key].every(v=>typeof v==="string"&&v.length<=120)))throw new Error("Scene "+index+" field "+key+" must be an array of at most "+maxItems+" short strings.");
  if(scene.chart_values!==undefined&&(!Array.isArray(scene.chart_values)||scene.chart_values.length<2||scene.chart_values.length>6||!scene.chart_values.every(v=>typeof v==="number"&&Number.isFinite(v)&&v>=0)))throw new Error("Scene "+index+" chart_values must contain 2–6 finite non-negative numbers.");
  if(scene.audio_envelope!==undefined&&(!Array.isArray(scene.audio_envelope)||scene.audio_envelope.length<8||scene.audio_envelope.length>120||!scene.audio_envelope.every(v=>typeof v==="number"&&Number.isFinite(v)&&v>=0&&v<=1)))throw new Error("Scene "+index+" audio_envelope must contain 8–120 finite normalized RMS values from 0 to 1.");
  if(kind==="waveform"&&scene.audio_envelope!==undefined&&scene.waveform_source!=="final_scene_narration_pcm16_rms")throw new Error("Scene "+index+" waveform envelope is missing its final narration RMS provenance.");
  if(kind==="bar-chart"){
   if(!Array.isArray(scene.chart_values)||scene.chart_values.length<2||scene.chart_values.length>6)throw new Error("bar-chart requires 2–6 chart_values.");
   if(!Array.isArray(scene.chart_labels)||scene.chart_labels.length!==scene.chart_values.length)throw new Error("bar-chart requires one chart_label per chart_value.");
  }
 }
 if(s.style!==undefined&&s.style!==null){
  if(typeof s.style!=="object"||Array.isArray(s.style))throw new Error("style must be an object.");
  if(s.style.tone!==undefined&&!toneTypes.has(String(s.style.tone).toLowerCase()))throw new Error("Unsupported style.tone: "+s.style.tone);
  const paletteBlock=s.style.palette;
  if(paletteBlock!==undefined){
   if(typeof paletteBlock!=="object"||Array.isArray(paletteBlock))throw new Error("style.palette must be an object.");
   for(const key of paletteKeys)if(paletteBlock[key]!==undefined&&!/^#[0-9a-fA-F]{6}$/.test(String(paletteBlock[key])))throw new Error("style.palette."+key+" must be a 6-digit hex colour.");
  }
  const gradeBlock=s.style.grade;
  if(gradeBlock!==undefined){
   if(typeof gradeBlock!=="object"||Array.isArray(gradeBlock))throw new Error("style.grade must be an object.");
   for(const [key,min,max] of [["vignette",0,.4],["grain",0,.08],["bloom",0,.3],["contrast",.9,1.2]]){
    if(gradeBlock[key]===undefined)continue;
    const value=Number(gradeBlock[key]);
    if(!Number.isFinite(value)||value<min||value>max)throw new Error("style.grade."+key+" must be between "+min+" and "+max+".");
   }
  }
  const easingBlock=s.style.easing;
  if(easingBlock!==undefined){
   if(typeof easingBlock!=="object"||Array.isArray(easingBlock))throw new Error("style.easing must be an object.");
   for(const role of Object.keys(easingBlock))if(!easingTypes.has(String(easingBlock[role])))throw new Error("style.easing."+role+" uses an unknown curve: "+easingBlock[role]);
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
 let server=null;
 try{
  const page=await browser.newPage({viewport:{width:w,height:h},deviceScaleFactor:1});
  // A file:// page is an opaque origin, so Chrome blocks the @font-face files
  // beside it and the film would silently fall back to a system font. Serve the
  // studio directory from a throwaway loopback server instead: the page gets a
  // real origin, every relative asset resolves normally, and nothing is
  // downloaded or exposed beyond 127.0.0.1.
  const MIME={".html":"text/html; charset=utf-8",".js":"text/javascript; charset=utf-8",
   ".css":"text/css; charset=utf-8",".woff2":"font/woff2",".woff":"font/woff",".ttf":"font/ttf",
   ".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".svg":"image/svg+xml",".json":"application/json"};
  const studioRoot=__dirname+path.sep;
  server=http.createServer((req,res)=>{
   const requested=decodeURIComponent((req.url||"/").split("?")[0]);
   const target=path.resolve(__dirname,requested==="/"?"render.html":"."+requested);
   if(!target.startsWith(studioRoot)){res.writeHead(403);res.end("forbidden");return;}
   fs.readFile(target,(error,data)=>{
    if(error){res.writeHead(404);res.end("not found");return;}
    res.writeHead(200,{"Content-Type":MIME[path.extname(target).toLowerCase()]||"application/octet-stream"});
    res.end(data);
   });
  });
  await new Promise(resolve=>server.listen(0,"127.0.0.1",resolve));
  const origin="http://127.0.0.1:"+server.address().port;
  await page.goto(origin+"/render.html",{waitUntil:"load"});
  await page.setViewport({width:w,height:h,deviceScaleFactor:1});
  await page.evaluate((width,height)=>window.setCanvasSize(width,height),w,h);
  if(s.style)await page.evaluate(style=>window.setStyle(style),s.style);
  await page.evaluate(rate=>window.setFrameRate(rate),fps);
  // @font-face is lazy: nothing has drawn text yet, so check() would report
  // false even for fonts that are perfectly available. Ask for each weight we
  // use, which forces the download, and only then verify.
  await page.evaluate(async ()=>{
   const wanted=["400 16px Inter","500 16px Inter","600 16px Inter","700 16px Inter","800 16px Inter",
    '400 16px "Space Grotesk"','500 16px "Space Grotesk"','600 16px "Space Grotesk"','700 16px "Space Grotesk"'];
   await Promise.all(wanted.map(spec=>document.fonts.load(spec)));
   await document.fonts.ready;
  });
  const fontCheck=await page.evaluate(()=>({
   inter:document.fonts.check('700 64px Inter'),
   display:document.fonts.check('700 64px "Space Grotesk"'),
   faces:Array.from(document.fonts).map(face=>face.family+"/"+face.weight+"/"+face.status)
  }));
  if(!fontCheck.inter||!fontCheck.display)throw new Error("Bundled font regression: professional faces did not load. "+JSON.stringify(fontCheck));
  console.log("Font check:",JSON.stringify(fontCheck));
  const wrapCheck=await page.evaluate(()=>window.measureWrappedLines("word ".repeat(80),180,"16px Arial"));
  if(!Number.isInteger(wrapCheck)||wrapCheck<2)throw new Error("Text wrapping regression: long text did not wrap to multiple lines.");
  const directionCheck=await page.evaluate(()=>({
   urdu:window.textDirectionForTest("یہ Python API ہے"),
   english:window.textDirectionForTest("English API")
  }));
  if(directionCheck.urdu!=="rtl"||directionCheck.english!=="ltr")throw new Error("Script-direction regression: Urdu must be RTL and English LTR. "+JSON.stringify(directionCheck));
  const captionLayoutCheck=await page.evaluate(()=>{
   const landscape=window.captionLayoutForTest(1920,1080,150,1620);
   const portrait=window.captionLayoutForTest(1080,1920,84,912);
   return {landscape,portrait};
  });
  if(!captionLayoutCheck.landscape||captionLayoutCheck.landscape.width>1920*.60||
     captionLayoutCheck.landscape.x!==150||captionLayoutCheck.landscape.portrait!==false||
     !captionLayoutCheck.portrait||captionLayoutCheck.portrait.width!==912||
     captionLayoutCheck.portrait.portrait!==true){
   throw new Error("Caption/presenter safe-lane regression: "+JSON.stringify(captionLayoutCheck));
  }

  const rigCheck=await page.evaluate(()=>window.characterRigCapabilitiesForTest());
  if(rigCheck.version!==3||rigCheck.travelMotion!==true)throw new Error("Character travel-motion capability regression: "+JSON.stringify(rigCheck));
  const motionCheck=await page.evaluate(()=>{
   const pushStart=window.cameraTransformForTest({camera_motion:"push-in"},0,1920,1080);
   const pushEnd=window.cameraTransformForTest({camera_motion:"push-in"},1,1920,1080);
   const panEnd=window.cameraTransformForTest({camera_motion:"pan-left"},1,1920,1080);
   const walkStart=window.characterPositionForTest({x:.8,walking:1,walk_from_x:.2,walk_to_x:.8},0,1920,1080);
   const walkMid=window.characterPositionForTest({x:.8,walking:1,walk_from_x:.2,walk_to_x:.8},.5,1920,1080);
   const walkEnd=window.characterPositionForTest({x:.8,walking:1,walk_from_x:.2,walk_to_x:.8},1,1920,1080);
   return {pushStart:pushStart.scale,pushEnd:pushEnd.scale,panEnd:panEnd.offsetX,walk:[walkStart.x,walkMid.x,walkEnd.x]};
  });
  if(!(motionCheck.pushStart===1&&motionCheck.pushEnd>1&&motionCheck.panEnd<0&&motionCheck.walk[0]===.2&&motionCheck.walk[1]===.5&&motionCheck.walk[2]===.8))throw new Error("Camera or character travel motion regression: "+JSON.stringify(motionCheck));
  console.log("Camera/character motion smoke check:",JSON.stringify(motionCheck));

  const requiredJoints=["shoulder","elbow","wrist","hip","knee","ankle","neck","head"];
  const requiredVisemes=["closed","open","wide","round","teeth","tongue","sibilant","lip","open_wide","open_round"];
  if(!rigCheck||rigCheck.version!==3||!requiredJoints.every(x=>rigCheck.joints.includes(x))||!requiredVisemes.every(x=>rigCheck.visemeShapes.includes(x)))throw new Error("Character-rig capability regression: "+JSON.stringify(rigCheck));
  const rigDrawCheck=await page.evaluate(()=>{
   const shapes=window.characterRigCapabilitiesForTest().visemeShapes;
   for(const shape of shapes){
    window.drawCharacterForTest({enabled:true,x:0.5,y:0.5,scale:0.2,expression:"curious",pose:"explain",visemes:[{t:0,shape},{t:1,shape}]},0.5,42);
   }
   const canvas=document.getElementById("frame");return {shapes_drawn:shapes.length,canvas_width:canvas.width,canvas_height:canvas.height};
  });
  if(!rigDrawCheck||rigDrawCheck.shapes_drawn!==requiredVisemes.length||rigDrawCheck.canvas_width!==w||rigDrawCheck.canvas_height!==h)throw new Error("Character-rig draw smoke check failed: "+JSON.stringify(rigDrawCheck));
  const easingCheck=await page.evaluate(()=>{
   const start=window.easeForTest("editorial",0),finish=window.easeForTest("editorial",1),middle=window.easeForTest("editorial",.5);
   const settlePeak=Math.max(...Array.from({length:33},(_,i)=>window.easeForTest("settle",i/32)));
   const anti=window.anticipationForTest(.10,.18,.08);
   const capabilities=window.motionCapabilitiesForTest();
   return {start,finish,middle,settlePeak,anti,curves:capabilities.curves,grade:capabilities.grade};
  });
  if(easingCheck.start!==0||easingCheck.finish!==1||Math.abs(easingCheck.middle-.5)>1e-6||easingCheck.settlePeak<=1||easingCheck.anti>=0||easingCheck.curves.length<7)throw new Error("Easing or anticipation regression: "+JSON.stringify(easingCheck));
  if(!(easingCheck.grade.vignette>0&&easingCheck.grade.grain>0))throw new Error("Grade regression: vignette or grain missing.");
  console.log("Easing/anticipation smoke check:",JSON.stringify(easingCheck));

  const transitionCheck=await page.evaluate(async()=>{
   const previous={visual_type:"hero",headline:"Previous scene",subhead:"Outgoing text",caption:"Outgoing narration",transition_in:"none"};
   const current={visual_type:"diagram",headline:"Current scene",subhead:"Incoming text",caption:"Incoming narration",visual_nodes:["INPUT","PROCESS","OUTPUT"],transition_in:"none"};
   const modes=window.motionCapabilitiesForTest().transitions;
   for(const mode of modes){
    await window.drawTransitionFrame(previous,29,30,29,current,0,30,30,mode,0.5);
   }
   return {modes_rendered:modes,canvas_width:document.getElementById("frame").width,canvas_height:document.getElementById("frame").height};
  });
  if(!transitionCheck||transitionCheck.modes_rendered.length!==14||transitionCheck.canvas_width!==w||transitionCheck.canvas_height!==h)throw new Error("Transition rendering smoke check failed: "+JSON.stringify(transitionCheck));
  console.log("Transition smoke check:",JSON.stringify(transitionCheck));
  const waveformCheck=await page.evaluate(()=>{
   const values=Array.from({length:64},(_,i)=>Math.max(0,Math.min(1,Math.abs(Math.sin(i*.2)))));
   window.drawFrame({visual_type:"waveform",headline:"Audio energy",subhead:"Measured narration envelope",caption:"Sample narration",audio_envelope:values,waveform_source:"final_scene_narration_pcm16_rms"},15,30,15,true);
   return {bins:values.length,source:"final_scene_narration_pcm16_rms",width:document.getElementById("frame").width};
  });
  if(!waveformCheck||waveformCheck.bins!==64||waveformCheck.source!=="final_scene_narration_pcm16_rms"||waveformCheck.width!==w)throw new Error("Audio waveform rendering smoke check failed: "+JSON.stringify(waveformCheck));
  console.log("Waveform smoke check:",JSON.stringify(waveformCheck));
  const captionCheck=await page.evaluate(()=>{
   const text=Array.from({length:80},(_,i)=>"captionword"+i).join(" ");
   const info=window.captionPageForTest(text,180,"16px Arial",0.5);
   const first=window.captionPageForTest(text,180,"16px Arial",0);
   const last=window.captionPageForTest(text,180,"16px Arial",0.99999);
   return {totalLines:info.allLines.length,totalPages:info.totalPages,firstIndex:first.pageIndex,lastIndex:last.pageIndex};
  });
  if(captionCheck.totalPages<2||captionCheck.firstIndex!==0||captionCheck.lastIndex!==captionCheck.totalPages-1)throw new Error("Caption pagination regression: long narration is not split across readable pages.");
  let total=0;
  const transitionRecords=[];
  for(let si=0;si<s.scenes.length;si++){
   const scene=s.scenes[si],sec=Number(scene.duration_seconds);
   if(!Number.isFinite(sec)||sec<=0||sec>600)throw new Error("scene duration must be >0 and <=600 seconds");
   const count=Math.max(1,Math.round(sec*fps));
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
  fs.writeFileSync(path.resolve(__dirname,"render-manifest.json"),JSON.stringify({title:String(s.title||"Offline Agent HQ video"),width:w,height:h,fps,frame_count:total,duration_seconds:total/fps,scene_count:s.scenes.length,transitions:transitionRecords,style:s.style||null,tone:(s.style&&s.style.tone)||null,generated_at:new Date().toISOString()},null,2)+"\n");
  console.log("Rendered "+total+" frames to "+dir);
 }finally{await browser.close();if(server)await new Promise(resolve=>server.close(resolve))}
}
main().catch(e=>{console.error("RENDER ERROR: "+(e&&e.message?e.message:String(e)));process.exitCode=1});
