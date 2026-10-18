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
 const dir=path.resolve("frames");fs.mkdirSync(dir,{recursive:true});
 for(const f of fs.readdirSync(dir))if(/^frame-\d{6}\.png$/.test(f))fs.unlinkSync(path.join(dir,f));
 const browser=await puppeteer.launch({headless:true,args:["--no-sandbox","--disable-setuid-sandbox"]});
 try{
  const page=await browser.newPage({viewport:{width:w,height:h},deviceScaleFactor:1});
  await page.goto("file://"+path.resolve(__dirname,"render.html"),{waitUntil:"load"});await page.setViewport({width:w,height:h,deviceScaleFactor:1});
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
  fs.writeFileSync(path.resolve("render-manifest.json"),JSON.stringify({title:String(s.title||"Offline Agent HQ video"),width:w,height:h,fps,frame_count:total,duration_seconds:total/fps,scene_count:s.scenes.length,generated_at:new Date().toISOString()},null,2)+"\n");
  console.log("Rendered "+total+" frames to "+dir);
 }finally{await browser.close()}
}
main().catch(e=>{console.error("RENDER ERROR: "+(e&&e.message?e.message:String(e)));process.exitCode=1});
