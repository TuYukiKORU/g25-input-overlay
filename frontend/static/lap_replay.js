/* Compare recorded positions using elapsed time from a shared track distance. */
(function(root){
  'use strict';
  const finite=value=>value!=null&&Number.isFinite(Number(value));
  const hasPosition=s=>finite(s?.position?.x)&&finite(s?.position?.z);
  function positionJump(a,b){
    if(!hasPosition(a)||!hasPosition(b))return false;
    const dt=Math.max(0,Number(b.lap_time_ms)-Number(a.lap_time_ms))/1000;
    const distance=Math.abs(Number(b.lap_distance)-Number(a.lap_distance));
    const speed=Math.max(...[a.speed,b.speed].filter(finite).map(Number),0)||400;
    // Packet groups arrive separately; allow timing skew and measurement noise.
    const allowance=Math.max(25,distance*2+10,speed/3.6*(dt+.15)*2+10);
    return Math.hypot(Number(b.position.x)-Number(a.position.x),Number(b.position.z)-Number(a.position.z))>allowance;
  }
  function continuous(a,b){
    if(!hasPosition(a)||!hasPosition(b))return false;
    const dt=Number(b.lap_time_ms)-Number(a.lap_time_ms),distance=Number(b.lap_distance)-Number(a.lap_distance);
    return Number.isFinite(dt)&&dt>=0&&dt<=1500&&Number.isFinite(distance)&&distance>=0&&distance<=100&&!positionJump(a,b);
  }
  function cleanPositions(rows){
    return rows.map((s,i)=>{
      if(!hasPosition(s)||rows.length<3)return s;
      const before=rows[i-1],after=rows[i+1];
      const isolated=!before?positionJump(s,after)&&continuous(after,rows[i+2])
        :!after?positionJump(before,s)&&continuous(rows[i-2],before)
        :positionJump(before,s)&&positionJump(s,after)&&continuous(before,after);
      return isolated?{...s,position:null,_positionRejected:true}:s;
    });
  }
  function series(lap){
    const rows=(lap?.samples||[]).filter(s=>finite(s.lap_time_ms)&&finite(s.lap_distance));
    if(rows.some((s,i)=>i&&(Number(s.lap_time_ms)<Number(rows[i-1].lap_time_ms)||
                          Number(s.lap_distance)<Number(rows[i-1].lap_distance))))return [];
    return cleanPositions(rows.filter((s,i)=>!i||Number(s.lap_time_ms)>Number(rows[i-1].lap_time_ms)));
  }
  function interpolate(rows,value,key){
    if(!rows.length||!finite(value)||value<Number(rows[0][key])||value>Number(rows.at(-1)[key]))return null;
    let lo=0,hi=rows.length-1;
    while(lo<hi){const mid=(lo+hi)>>1;if(Number(rows[mid][key])<value)lo=mid+1;else hi=mid;}
    const b=rows[lo],a=rows[Math.max(0,lo-1)];
    const usable=s=>finite(s.position?.x)&&finite(s.position?.z);
    if(Number(b[key])===value)return usable(b)?b:null;
    if(!continuous(a,b))return null;
    const ratio=(value-Number(a[key]))/(Number(b[key])-Number(a[key]));
    const blend=k=>finite(a[k])&&finite(b[k])?Number(a[k])+(Number(b[k])-Number(a[k]))*ratio:null;
    return {lap_time_ms:blend('lap_time_ms'),lap_distance:blend('lap_distance'),speed:blend('speed'),
      position:{x:Number(a.position.x)+(Number(b.position.x)-Number(a.position.x))*ratio,
                z:Number(a.position.z)+(Number(b.position.z)-Number(a.position.z))*ratio}};
  }
  function commonRange(a,b){
    if(!a.length||!b.length)return null;
    const start=Math.max(Number(a[0].lap_time_ms),Number(b[0].lap_time_ms));
    const end=Math.min(Number(a.at(-1).lap_time_ms),Number(b.at(-1).lap_time_ms));
    return end>start?{start,end}:null;
  }
  function alignedRange(a,b,minimumDistance=0){
    if(!a.length||!b.length)return null;
    const first=Math.max(minimumDistance,Number(a[0].lap_distance),Number(b[0].lap_distance));
    const last=Math.min(Number(a.at(-1).lap_distance),Number(b.at(-1).lap_distance));
    // If the boundary falls in a telemetry gap, try the next recorded position.
    const candidates=[first,...a.map(s=>Number(s.lap_distance)),...b.map(s=>Number(s.lap_distance))]
      .filter(d=>d>=first&&d<last).sort((x,y)=>x-y);
    for(const distance of new Set(candidates)){
      const selected=interpolate(a,distance,'lap_distance'),ghost=interpolate(b,distance,'lap_distance');
      if(!selected||!ghost)continue;
      const start=Number(selected.lap_time_ms),ghostOffset=Number(ghost.lap_time_ms)-start;
      const end=Math.min(Number(a.at(-1).lap_time_ms),Number(b.at(-1).lap_time_ms)-ghostOffset);
      if(end>start)return {start,end,ghostOffset,distance};
    }
    return null;
  }
  function frame(points){
    const meanX=points.reduce((sum,s)=>sum+Number(s.position.x),0)/points.length;
    const meanZ=points.reduce((sum,s)=>sum+Number(s.position.z),0)/points.length;
    const covariance=points.reduce((v,s)=>{const x=Number(s.position.x)-meanX,z=Number(s.position.z)-meanZ;
      v.xx+=x*x;v.zz+=z*z;v.xz+=x*z;return v;},{xx:0,zz:0,xz:0});
    const angle=.5*Math.atan2(2*covariance.xz,covariance.xx-covariance.zz),cos=Math.cos(angle),sin=Math.sin(angle);
    return s=>{const x=Number(s.position.x)-meanX,z=Number(s.position.z)-meanZ;return [x*cos+z*sin,-x*sin+z*cos];};
  }
  function projection(points,rotate,width,height,padding=25){
    const rotated=points.map(rotate),xs=rotated.map(p=>p[0]),ys=rotated.map(p=>p[1]);
    const minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys),maxY=Math.max(...ys);
    const scale=Math.min(Math.max(1,width-padding*2)/(maxX-minX||1),Math.max(1,height-padding*2)/(maxY-minY||1));
    const ox=(width-(maxX-minX)*scale)/2,oy=(height-(maxY-minY)*scale)/2;
    const xyRotated=([x,y])=>[ox+(x-minX)*scale,oy+(y-minY)*scale];
    return {xy:s=>xyRotated(rotate(s)),xyRotated,
      bounds:{minX:minX-ox/scale,maxX:minX+(width-ox)/scale,minY:minY-oy/scale,maxY:minY+(height-oy)/scale}};
  }
  const api={series,cleanPositions,continuous,atTime:(rows,time)=>interpolate(rows,time,'lap_time_ms'),
    atDistance:(rows,distance)=>interpolate(rows,distance,'lap_distance'),commonRange,alignedRange,frame,projection};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.LapReplay=api;
})(typeof window!=='undefined'?window:globalThis);
