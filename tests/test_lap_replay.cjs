const {test}=require('node:test');
const assert=require('node:assert/strict');
const replay=require('../frontend/static/lap_replay.js');
const point=(t,d,x=d,z=0)=>({lap_time_ms:t,lap_distance:d,speed:100,position:{x,z}});
test('positions share elapsed time rather than track distance',()=>{
  const selected=[point(0,0),point(1000,50)],ghost=[point(0,0),point(1000,70)];
  assert.equal(replay.atTime(selected,500).lap_distance,25);
  assert.equal(replay.atTime(ghost,500).lap_distance,35);
  assert.equal(replay.atTime(ghost,500).position.x-replay.atTime(selected,500).position.x,10);
});
test('replay uses only the recorded overlap and never invents a finish position',()=>{
  const selected=[point(20,1),point(1000,50)],ghost=[point(30,2),point(1100,60)];
  assert.deepEqual(replay.commonRange(selected,ghost),{start:30,end:1000});
  assert.equal(replay.atTime(selected,10),null);
  assert.equal(replay.atTime(selected,1100),null);
  assert.equal(replay.commonRange(selected,[point(1200,50),point(1300,60)]),null);
});
test('missing positions and long telemetry gaps do not produce a fabricated ghost',()=>{
  assert.equal(replay.atTime([point(0,0),point(2000,50)],1000),null);
  assert.equal(replay.atTime([point(0,0),point(1000,200)],500),null);
  assert.equal(replay.atTime([point(0,0),{...point(1000,50),position:{x:null,z:0}}],500),null);
  assert.deepEqual(replay.series({samples:[point(1000,50),point(500,25)]}),[]);
});
test('chart distance seeks the selected clock, then locates the ghost at that time',()=>{
  const selected=[point(1000,50),point(2000,100)];
  const time=replay.atDistance(selected,75).lap_time_ms;
  assert.equal(time,1500);
  assert.equal(replay.atTime([point(1000,70),point(2000,130)],time).lap_distance,100);
});
test('shared start aligns different sample positions and clocks without flattening pace',()=>{
  const selected=[point(20,1),point(1020,51)],ghost=[point(200,6),point(1200,76)];
  const range=replay.alignedRange(selected,ghost);
  assert.deepEqual(range,{start:120,end:1020,ghostOffset:80,distance:6});
  assert.equal(replay.atTime(selected,range.start).lap_distance,6);
  assert.equal(replay.atTime(ghost,range.start+range.ghostOffset).lap_distance,6);
  assert.equal(replay.atTime(selected,range.start+500).lap_distance,31);
  assert.equal(replay.atTime(ghost,range.start+range.ghostOffset+500).lap_distance,41);
  assert.equal(replay.atTime(selected,range.start-150),null);
});
test('zoom starts both cars at its boundary and stops before either recording ends',()=>{
  const selected=[point(1000,50),point(2000,100)],ghost=[point(2000,50),point(3000,130)];
  const range=replay.alignedRange(selected,ghost,75);
  assert.deepEqual(range,{start:1500,end:2000,ghostOffset:812.5,distance:75});
  assert.equal(replay.atTime(ghost,range.start+range.ghostOffset).lap_distance,75);
  assert.equal(replay.alignedRange(selected,ghost,100),null);
});
test('alignment skips unusable boundaries and never extrapolates across a missing interval',()=>{
  const selected=[point(0,0),point(2000,50),point(3000,100)];
  const ghost=[point(200,25),point(1200,50),point(2200,100)];
  assert.equal(replay.alignedRange(selected,ghost).distance,50);
  assert.equal(replay.alignedRange(selected,[point(0,101),point(1000,151)]),null);
  assert.equal(replay.alignedRange(selected,[{...point(0,50),position:{x:null,z:null}}]),null);
});
test('overview box maps the exact detail viewport in the same orientation',()=>{
  const all=[point(0,0,0,0),point(1000,50,50,20),point(2000,100,100,0),point(3000,150,0,-50)];
  const rotate=replay.frame(all),detail=replay.projection(all.slice(1,3),rotate,300,250);
  const bounds=detail.bounds;
  const [left,top]=detail.xyRotated([bounds.minX,bounds.minY]);
  const [right,bottom]=detail.xyRotated([bounds.maxX,bounds.maxY]);
  assert.ok(Math.abs(left)<1e-8&&Math.abs(top)<1e-8);
  assert.ok(Math.abs(right-300)<1e-8&&Math.abs(bottom-250)<1e-8);
  const overview=replay.projection(all,rotate,140,145,12);
  const a=overview.xyRotated([bounds.minX,bounds.minY]),b=overview.xyRotated([bounds.maxX,bounds.maxY]);
  assert.ok(b[0]>a[0]&&b[1]>a[1]);
});
test('stale COTA start position is excluded without changing the recorded sample',()=>{
  const first={...point(1735,115.890625,-170.266876,984.856995),speed:73};
  const next={...point(1852,123.34375,-620.111999,730.206421),speed:268};
  const third={...point(1902,128.351563,-618.100342,731.676453),speed:269};
  const selected=replay.series({samples:[first,next,third]});
  assert.equal(selected[0].position,null);
  assert.equal(selected[0]._positionRejected,true);
  assert.equal(first.position.x,-170.266876);
  assert.equal(replay.atTime(selected,1790),null);
  const ghost=[point(1700,115.890625,-623,728),point(1900,128.351563,-618,732)];
  assert.equal(replay.alignedRange(selected,ghost).distance,123.34375);
});
test('an impossible jump cannot become a driving line or an interpolated replay position',()=>{
  const rows=[point(0,0,0),point(100,7,500)];
  assert.equal(replay.continuous(...rows),false);
  assert.equal(replay.atTime(rows,50),null);
  const gap=[point(0,0),point(2000,50),point(2100,55)];
  assert.equal(replay.cleanPositions(gap)[0],gap[0]);
  assert.equal(replay.continuous(gap[0],gap[1]),false);
});
test('isolated bad positions are rejected while ordinary packet skew stays usable',()=>{
  const rows=[point(0,0,0),point(100,7,500),point(200,14,14)];
  assert.equal(replay.cleanPositions(rows)[1].position,null);
  const normal=[{...point(0,0),speed:330},{...point(50,5,10),speed:330},point(150,14,15)];
  assert.equal(replay.continuous(normal[0],normal[1]),true);
  assert.deepEqual(replay.cleanPositions(normal),normal);
});
