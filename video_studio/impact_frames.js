"use strict";
const IMPACT_TYPES=Object.freeze(["flash","invert","burst","speed-lines","shockwave"]),MAX_EVENTS_PER_SCENE=8;
function normalizeImpactEvents(scene,sceneIndex,fps){
 const label="Scene "+(sceneIndex+1);
 if(!scene||typeof scene!=="object"||Array.isArray(scene))throw Error(label+" must be an object.");
 if(scene.impact_events===undefined)return [];
 if(!Array.isArray(scene.impact_events)||scene.impact_events.length>MAX_EVENTS_PER_SCENE)throw Error(label+" impact_events must be an array of at most 8 events.");
 if(!Number.isInteger(fps)||fps<1||fps>60)throw Error("Impact-frame FPS must be an integer from 1 to 60.");
 const duration=Number(scene.duration_seconds);if(!Number.isFinite(duration)||duration<=0)throw Error(label+" duration_seconds must be positive.");
 const frameCount=Math.max(1,Math.round(duration*fps)),ids=new Set();
 return scene.impact_events.map((event,i)=>{
  const item=label+" impact event "+(i+1);
  if(!event||typeof event!=="object"||Array.isArray(event))throw Error(item+" must be an object.");
  const type=typeof event.type==="string"?event.type.toLowerCase():"";
  if(!IMPACT_TYPES.includes(type))throw Error(item+" has an unsupported type.");
  const id=event.id===undefined?"scene-"+(sceneIndex+1)+"-impact-"+(i+1):event.id;
  if(typeof id!=="string"||!id.trim()||id.length>64||ids.has(id))throw Error(item+" id must be unique, non-empty, and at most 64 characters.");ids.add(id);
  if(typeof event.at_seconds!=="number"||!Number.isFinite(event.at_seconds)||event.at_seconds<0||event.at_seconds>=duration)throw Error(item+" at_seconds must be finite and within the scene duration.");
  if(!Number.isInteger(event.duration_frames)||event.duration_frames<1||event.duration_frames>6)throw Error(item+" duration_frames must be an integer from 1 to 6.");
  const start_frame=Math.round(event.at_seconds*fps);
  if(start_frame>=frameCount||start_frame+event.duration_frames>frameCount)throw Error(item+" event duration falls beyond available scene frames at this FPS.");
  const intensity=event.intensity===undefined?.45:event.intensity,x=event.x===undefined?.5:event.x,y=event.y===undefined?.5:event.y;
  if(typeof intensity!=="number"||!Number.isFinite(intensity)||intensity<.05||intensity>.75)throw Error(item+" intensity must be from 0.05 to 0.75.");
  for(const [coord,v] of [["x",x],["y",y]])if(typeof v!=="number"||!Number.isFinite(v)||v<0||v>1)throw Error(item+" "+coord+" must be normalized from 0 to 1.");
  return {id,type,at_seconds:event.at_seconds,start_frame,duration_frames:event.duration_frames,intensity,x,y};
 });
}
function assertUniqueImpactEventIds(scenes){const ids=new Set();for(const scene of scenes)for(const event of scene._impact_events||[]){if(ids.has(event.id))throw Error("Duplicate impact event ID across storyboard: "+event.id);ids.add(event.id);}return true;}
module.exports={IMPACT_TYPES,MAX_EVENTS_PER_SCENE,normalizeImpactEvents,assertUniqueImpactEventIds};
