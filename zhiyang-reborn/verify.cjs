const assert=require('node:assert/strict');
const E=require('./engine.js');
let checks=0;
function test(name,fn){fn();checks++;console.log('PASS '+name)}
function tick(r,n,input={}){for(let i=0;i<n;i++)E.step(r,1/60,input)}
test('Eight heroes and distinct skills are fully configured',()=>{assert.equal(Object.keys(E.heroes).length,8);for(const h of Object.values(E.heroes)){assert.equal(h.skills.length,3);assert.ok(h.hp>0&&h.atk>0)}});
test('Save round trip sanitizes imported state and rejects invalid versions',()=>{const s=E.freshSave();s.name='<img onerror=alert(1)>';s.gold=-10;s.heroes.yao.level=99;s.runes.fire=20;s.settings.volume=150;const clean=E.sanitizeSave(JSON.parse(JSON.stringify(s)));assert.equal(clean.gold,0);assert.equal(clean.heroes.yao.level,30);assert.equal(clean.runes.fire,10);assert.equal(clean.settings.volume,100);assert.throws(()=>E.sanitizeSave({version:1}));assert.throws(()=>E.sanitizeSave(null));assert.equal(clean.suspended,null)});
test('Hero training and equipped rune stacking change combat stats',()=>{const s=E.freshSave(),base=E.stats(s,'yao');s.heroes.yao.level=5;s.loadouts.yao=['fire','fire','water','ice','dark','earth'];s.runes.fire=3;const boosted=E.stats(s,'yao');assert.ok(boosted.atk>base.atk*1.35);assert.ok(boosted.maxHp>base.maxHp);assert.equal(boosted.leech,.01);assert.equal(boosted.def,.02)});
test('Enemy attacks are telegraphed before damage and flash dodge protects',()=>{const r=E.createRun(E.freshSave(),'duel',0,'normal',77);r.enemies[0].x=30;r.enemies[0].y=0;r.enemies[0].cd=0;r.enemies[0].skill=20;const hp=r.p.hp;E.step(r,.016);assert.ok(r.warnings.length);assert.equal(r.p.hp,hp);E.useDash(r,1,0);tick(r,60,{mx:1});assert.equal(r.p.hp,hp);assert.ok(r.p.x>100)});
test('Shield absorbs damage and health never exceeds max',()=>{const r=E.createRun(E.freshSave(),'trial',0,'normal',55);E.useSkill(r,1);assert.ok(r.p.shield>0);const hp=r.p.hp;E.damagePlayer(r,50);assert.equal(r.p.hp,hp);assert.ok(r.p.shield<hp*.3);r.p.hp=1;E.radial(r,0,0,100,0);assert.ok(r.p.hp<=r.p.maxHp)});
test('Every hero can execute all skills and progress without NaN',()=>{for(const id of Object.keys(E.heroes)){const s=E.freshSave();s.hero=id;const r=E.createRun(s,'campaign',0,'story',123);tick(r,130);for(let i=0;i<3;i++)assert.equal(E.useSkill(r,i),true,id+' skill '+i);tick(r,360,{mx:.5,my:.25});assert.ok(Number.isFinite(r.p.hp)&&Number.isFinite(r.p.atk));assert.ok(r.projectiles.length<=150);assert.ok(r.warnings.every(x=>Number.isFinite(x.damage)))}});
test('Wave clear grants three choices, reroll once, stack effects and advances',()=>{const r=E.createRun(E.freshSave(),'campaign',0,'story',8);tick(r,120);E.radial(r,0,0,5000,1e6);E.step(r,.016);assert.equal(r.phase,'choosing');assert.equal(new Set(r.options).size,3);assert.equal(E.reroll(r),true);assert.equal(E.reroll(r),false);assert.equal(E.choose(r,'INVALID'),false);const before=r.upgrades.length;assert.equal(E.choose(r,r.options[0]),true);assert.equal(r.upgrades.length,before+1);tick(r,100);assert.equal(r.wave,2);assert.ok(r.enemies.length>0)});
test('A complete five-wave campaign unlocks the next chapter and rewards only once',()=>{const s=E.freshSave(),r=E.createRun(s,'campaign',0,'normal',9);for(let i=0;i<5;i++){tick(r,120);E.radial(r,0,0,5000,1e6);E.step(r,.016);if(i<4){assert.equal(r.phase,'choosing');E.choose(r,r.options[0])}}assert.equal(r.phase,'won');assert.equal(r.wave,5);const reward=E.award(s,r,false,'2026-10-08');assert.ok(reward.gold>0&&reward.gems>0);assert.equal(s.clears[0],2);assert.equal(s.stats.wins,1);assert.equal(E.award(s,r),null);assert.equal(s.stats.wins,1)});
test('Exploration chests, guarded shrines and final boss form a complete loop',()=>{const s=E.freshSave(),r=E.createRun(s,'world',0,'normal',10);r.p.x=r.chests[0].x;r.p.y=r.chests[0].y;E.step(r,.016);assert.equal(r.chests[0].open,true);const sh=r.shrines[0];r.p.x=sh.x;r.p.y=sh.y;assert.equal(E.interact(r),false);E.radial(r,0,0,5000,1e6);E.step(r,.016);for(const sh of r.shrines){r.p.x=sh.x;r.p.y=sh.y;assert.equal(E.interact(r),true);if(r.phase==='choosing')E.choose(r,r.options[0])}assert.ok(r.enemies.some(e=>e.type==='boss'));E.radial(r,0,0,5000,1e6);E.step(r,.016);assert.equal(r.phase,'won');E.award(s,r);assert.equal(s.stats.shrines,3)});
test('Battle checkpoints recover health, enemies, choices and random sequence',()=>{const s=E.freshSave(),r=E.createRun(s,'trial',0,'normal',11);tick(r,160);r.p.hp=777;const packed=E.packRun(r),restored=E.restoreRun(JSON.parse(JSON.stringify(packed)));assert.equal(restored.p.hp,777);assert.equal(restored.enemies.length,r.enemies.length);assert.equal(restored.seed,r.seed);assert.ok(restored.p.invuln>0);E.radial(r,0,0,5000,1e6);E.step(r,.016);const choice=E.restoreRun(E.packRun(r));assert.equal(choice.phase,'choosing');assert.deepEqual(choice.options,r.options);assert.equal(E.restoreRun({schema:3}),null)});
test('Defeat and retreat settle earned rewards and preserve permanent progression',()=>{const s=E.freshSave(),r=E.createRun(s,'duel',0,'normal',12);r.gold=100;r.gems=10;r.p.hp=1;E.damagePlayer(r,10000);assert.equal(r.phase,'lost');assert.equal(r.p.hp,0);const a=E.award(s,r,false,'2026-10-08');assert.equal(a.win,false);assert.equal(s.gold,12100);assert.equal(s.gems,510);assert.equal(s.history.length,1);assert.equal(s.suspended,null)});
test('Seeded combat simulations keep memory bounded and produce actual victories',()=>{
 let victories=0,summary=[];
 for(const id of Object.keys(E.heroes)){
  const s=E.freshSave();s.hero=id;const r=E.createRun(s,'campaign',0,'story',120);
  for(let i=0;i<60*240&&r.phase!=='won'&&r.phase!=='lost';i++){
   if(r.phase==='choosing'){E.choose(r,r.options.find(k=>['leech','vital','heal','regen'].includes(k))||r.options[0]);continue}
   const target=E.nearest(r),p=r.p;let mx=0,my=0;
   if(target){const dx=target.x-p.x,dy=target.y-p.y,d=Math.hypot(dx,dy)||1,ideal=E.heroes[id].ranged?260:70;const move=d>ideal?1:d<ideal*.7?-1:0;mx=dx/d*move;my=dy/d*move;}
   E.step(r,1/60,{mx,my,autoAim:true});
   if(i%10===0){for(let k=0;k<3;k++)E.useSkill(r,k);if(r.warnings.some(w=>Math.hypot(w.x-p.x,w.y-p.y)<w.radius+30&&w.time<.3))E.useDash(r,-my||1,mx)}
   r.events=[];
   assert.ok(Number.isFinite(p.x)&&Number.isFinite(p.hp));assert.ok(r.projectiles.length<=150);assert.ok(r.enemies.length<80);
  }
  if(r.phase==='won')victories++;summary.push(`${id}:${r.phase}/wave${r.wave}/${Math.round(r.time)}s`);
 }
 console.log('  Simulations '+summary.join(' | '));assert.ok(victories>=3,'at least 3 distinct hero archetypes win without cheat damage');
});
test('All six guardians run their elemental phase-two patterns without invalid state',()=>{
 for(let chapter=0;chapter<6;chapter++){
  const r=E.createRun(E.freshSave(),'trial',chapter,'hard',30+chapter);r.wait=0;r.wave=3;
  const b=E.spawnEnemy(r,'boss',200,0);b.hp=b.maxHp*.45;r.p.maxHp=r.p.hp=1e7;r.auto=false;
  for(let i=0;i<60*24;i++){E.step(r,1/60,{mx:Math.sin(i/120),my:Math.cos(i/120)});r.events=[]}
  assert.equal(b.phase,2);assert.ok(Number.isFinite(r.p.hp));assert.ok(r.warnings.every(w=>Number.isFinite(w.x)&&Number.isFinite(w.damage)));assert.ok(r.projectiles.length<=150);
 }
});
test('Endless upgrades never exhaust the choice pool and cosmetics persist',()=>{
 const s=E.freshSave();s.skin='jade';s.ownedSkins.push('jade');const clean=E.sanitizeSave(s);assert.equal(clean.skin,'jade');const r=E.createRun(s,'trial',0,'normal',18);r.upgrades=E.upgrades.flatMap(u=>Array(5).fill(u.id));r.wait=0;r.wave=98;E.radial(r,0,0,3000,1e6);E.step(r,.016);assert.equal(r.phase,'choosing');assert.equal(r.options.length,3);assert.ok(E.choose(r,r.options[0]));
});
console.log(`\n${checks} gameplay checks passed.`);
