/* 智阳神传·天启 — deterministic, DOM-independent gameplay core */
const GameEngine = (() => {
'use strict';
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v)),TAU=Math.PI*2;
const heroes={
 yao:{name:'曜',title:'宇宙核心之子',role:'近战 · 战士',element:'光',color:'#eac67c',dark:'#344853',hp:1600,atk:95,speed:245,range:125,rate:.43,crit:.08,ranged:false,icon:'sun',quote:'残星亦可燃作太阳。吾之所往，即是破晓。',passive:'三段普攻：第三击伤害提升 70%，命中回复少量生命。',skills:[{name:'逐日斩',cd:5,desc:'斩出三道剑气，每道造成 160% 攻击伤害。'},{name:'抗击',cd:12,desc:'获得 30% 最大生命护盾，持续 5 秒。'},{name:'天启·乱斗',cd:24,desc:'震荡周围敌人，造成 550% 伤害，获得 1.2 秒无敌。'}]},
 yan:{name:'焰',title:'熔岩之心',role:'远程 · 法师',element:'火',color:'#f39571',dark:'#693c3a',hp:1200,atk:120,speed:228,range:460,rate:.65,crit:.05,ranged:true,icon:'flame',quote:'焚尽旧世的灰，才有新生的光。',passive:'命中附加灼烧，3 秒内持续造成每秒 25% 攻击伤害。',skills:[{name:'流火',cd:5,desc:'发射五枚穿透火球，每枚造成 140% 伤害。'},{name:'烈焰领域',cd:12,desc:'脚下生成持续 5 秒的烈焰，灼烧近敌。'},{name:'陨日',cd:24,desc:'召唤陨星轰击瞄准位置，造成 650% 范围伤害。'}]},
 shuang:{name:'霜',title:'永冬之源',role:'远程 · 控制',element:'冰',color:'#a7dce8',dark:'#335d6b',hp:1350,atk:92,speed:235,range:440,rate:.55,crit:.07,ranged:true,icon:'snow',quote:'万籁归寂之时，听见冰下的心跳。',passive:'攻击使敌人减速 30%，持续 2 秒。',skills:[{name:'寒星',cd:5,desc:'发射七道冰锥，每道造成 110% 伤害。'},{name:'霜甲',cd:11,desc:'获得 25% 生命护盾，并冻结周围敌人 2 秒。'},{name:'永冬',cd:24,desc:'生成 6 秒暴风雪，持续伤害并减速。'}]},
 ying:{name:'影',title:'暗影深渊',role:'近战 · 刺客',element:'暗',color:'#c2a3dd',dark:'#403754',hp:1150,atk:127,speed:275,range:110,rate:.31,crit:.2,ranged:false,icon:'moon',quote:'世人追逐太阳，我守住它背后的夜。',passive:'对生命低于 35% 的目标造成 40% 额外伤害。',skills:[{name:'影袭',cd:5,desc:'沿瞄准方向突进，沿途造成 260% 伤害。'},{name:'暗幕',cd:10,desc:'获得 2 秒无敌，并回复 12% 最大生命。'},{name:'夜葬',cd:22,desc:'大范围斩杀；低于 35% 生命的普通敌人立即消灭。'}]},
 yan2:{name:'岩',title:'大地之灵',role:'近战 · 守护',element:'土',color:'#d9ba88',dark:'#595244',hp:2150,atk:80,speed:208,range:145,rate:.62,crit:.04,ranged:false,icon:'shield',quote:'众生身后，当有一座不倒的山。',passive:'受到的伤害降低 20%，击中敌人额外击退。',skills:[{name:'撼地',cd:5,desc:'震荡周围敌人，造成 260% 伤害并眩晕。'},{name:'石肤',cd:12,desc:'获得 45% 最大生命护盾，持续 6 秒。'},{name:'山崩',cd:25,desc:'造成 650% 范围伤害并眩晕 3 秒。'}]},
 feng:{name:'岚',title:'风暴之眼',role:'远程 · 游侠',element:'风',color:'#98d7b5',dark:'#365b54',hp:1250,atk:100,speed:285,range:490,rate:.39,crit:.12,ranged:true,icon:'wind',quote:'风没有归处，所以万里皆是故乡。',passive:'普攻有 25% 概率额外射出两支风箭。',skills:[{name:'穿云',cd:4,desc:'发射三支穿透风箭，每支造成 220% 伤害。'},{name:'疾行',cd:9,desc:'移速增加 55%，持续 4 秒，回复 8% 最大生命。'},{name:'风眼',cd:23,desc:'召唤持续 6 秒的风暴，持续伤害并牵引敌人。'}]},
 guang:{name:'圣',title:'圣光之辉',role:'远程 · 治疗',element:'圣',color:'#e9e4af',dark:'#586258',hp:1500,atk:87,speed:230,range:420,rate:.56,crit:.05,ranged:true,icon:'sun',quote:'光从不挑选被照耀的人。',passive:'战斗中每秒恢复 0.7% 最大生命。',skills:[{name:'净光',cd:4,desc:'三发穿透圣光，每发造成 180% 伤害。'},{name:'圣愈',cd:11,desc:'立即恢复 30% 最大生命，并击退周围敌人。'},{name:'光耀降临',cd:25,desc:'回复 40% 生命；周围敌人受到 500% 伤害。'}]},
 lei:{name:'霆',title:'雷池之心',role:'远程 · 爆发',element:'雷',color:'#b6b7f0',dark:'#454b73',hp:1220,atk:116,speed:244,range:445,rate:.5,crit:.14,ranged:true,icon:'bolt',quote:'若长夜不肯退，就用雷霆将它劈开。',passive:'暴击时雷电跃迁到附近敌人，造成 60% 攻击伤害。',skills:[{name:'惊雷',cd:5,desc:'在瞄准位置落雷，造成 360% 范围伤害。'},{name:'雷铠',cd:11,desc:'获得 25% 生命护盾，雷击周围敌人。'},{name:'万雷天引',cd:24,desc:'全场落雷造成 600% 伤害，眩晕 1.5 秒。'}]}
};
const chapters=[
 {name:'遗落星庭',en:'THE FALLEN COURT',color:'#7bbfaf',floor:'#274c4b',sky:'#132f34',boss:'蚀星守卫',desc:'在悬空的残殿中，点亮智阳留下的第一道火种。',story:'星庭曾是诸神聆听天命的地方。如今殿宇悬于虚空，只有一盏不灭的灯，等着失散的神裔归来。'},
 {name:'绯烬之谷',en:'VALLEY OF EMBERS',color:'#df9775',floor:'#55433d',sky:'#30252c',boss:'焚天巨灵',desc:'穿过燃烧的赤色山谷，让失控的烈焰重归秩序。',story:'熔岩之心停止跳动的那日，谷中的风第一次有了温度。焰说，火不是惩罚，而是尚未读懂的求救。'},
 {name:'月隐竹海',en:'MOONLIT GROVE',color:'#96c695',floor:'#2b4840',sky:'#102b2b',boss:'影月妖王',desc:'竹影深处藏着失落的誓言，夜色正在苏醒。',story:'竹海有一万条小径，却没有一条通向同一个梦。守林者以影为名，记着每个在这里迷失的人。'},
 {name:'凛冬天阙',en:'PALACE OF FROST',color:'#b5d7e3',floor:'#426170',sky:'#243d4b',boss:'玄霜龙魂',desc:'攀上永冬封锁的天阙，唤醒被冰雪遗忘的太阳。',story:'霜从冰壁里听见了千年前的心跳。那并不是困兽的挣扎，而是仍在等待春天的巨龙。'},
 {name:'雷鸣孤峰',en:'THUNDER PEAK',color:'#b5b7e6',floor:'#404557',sky:'#252738',boss:'九霄雷尊',desc:'在碎裂的雷池之上，迎接九霄最后的审判。',story:'天命落在孤峰，化作千万声惊雷。霆从不相信神谕，他只相信每一次劈开黑暗的选择。'},
 {name:'智阳核心',en:'HEART OF ZHIYANG',color:'#edd5a0',floor:'#555341',sky:'#36352f',boss:'寂灭之阳',desc:'穿越最后一道星门，为这个世界夺回黎明。',story:'在宇宙的核心，太阳已沉默太久。没有谁生来注定成为救世主；那些走到这里的人，已经给出了答案。'}
];
const modes={campaign:{name:'神传征途',sub:'六重秘境 · 首领挑战',icon:'map'},trial:{name:'无尽试炼',sub:'随机构筑 · 极限生存',icon:'rune'},world:{name:'星野漫游',sub:'探索祭坛 · 寻宝冒险',icon:'leaf'},duel:{name:'镜像斗场',sub:'战术对决 · AI 神裔',icon:'sword'}};
const skins={original:{name:'神裔本色',price:0,color:null,dark:null,desc:'每位神裔的原初装束。'},gold:{name:'金阳神谕',price:260,color:'#f1ce83',dark:'#635747',desc:'鎏金披甲，携日而行。八位神裔通用。'},jade:{name:'苍月流光',price:220,color:'#93e0d5',dark:'#315b63',desc:'月色入衣，星河流转。八位神裔通用。'},void:{name:'虚空夜行',price:280,color:'#d1b3ef',dark:'#4c3b66',desc:'将幽夜化作锋芒。八位神裔通用。'},ember:{name:'赤霞焚天',price:240,color:'#f8a285',dark:'#734f48',desc:'如绯色黎明披在肩头。八位神裔通用。'}};
const runes={
 fire:{name:'赤焰',glyph:'火',color:'#ec9a76',desc:'每级攻击 +3%',stat:'atk',value:.03},
 water:{name:'沧溟',glyph:'水',color:'#98c9df',desc:'每级生命 +4%',stat:'hp',value:.04},
 wood:{name:'长生',glyph:'木',color:'#9bd0a9',desc:'每级每秒回复 0.15% 生命',stat:'regen',value:.0015},
 earth:{name:'镇岳',glyph:'土',color:'#d2b88a',desc:'每级伤害减免 +2%',stat:'def',value:.02},
 light:{name:'曜光',glyph:'光',color:'#ebd5a0',desc:'每级攻击与生命 +2%',stat:'all',value:.02},
 wind:{name:'流风',glyph:'风',color:'#a0d6bc',desc:'每级移速 +3%',stat:'speed',value:.03},
 thunder:{name:'震霄',glyph:'雷',color:'#bcbbee',desc:'每级暴击率 +2%',stat:'crit',value:.02},
 ice:{name:'玄冰',glyph:'冰',color:'#b0dfe4',desc:'每级技能冷却缩减 +2%',stat:'cdr',value:.02},
 dark:{name:'夜魄',glyph:'暗',color:'#c2a6d7',desc:'每级吸血 +1%',stat:'leech',value:.01}
};
const upgrades=[
 {id:'power',name:'破军',icon:'sword',desc:'攻击力增加 22%',kind:'攻击',apply:r=>r.p.atk*=1.22},
 {id:'vital',name:'长生',icon:'leaf',desc:'最大生命增加 25%，恢复 25% 生命',kind:'生存',apply:r=>{r.p.maxHp*=1.25;r.p.hp=Math.min(r.p.maxHp,r.p.hp+r.p.maxHp*.25)}},
 {id:'crit',name:'惊鸿',icon:'bolt',desc:'暴击率增加 15%，暴击伤害增加 20%',kind:'攻击',apply:r=>{r.p.crit+=.15;r.p.critDmg+=.2}},
 {id:'swift',name:'追风',icon:'wind',desc:'移速增加 15%，闪避冷却减少 15%',kind:'机动',apply:r=>{r.p.speed*=1.15;r.p.dashRate*=.85}},
 {id:'haste',name:'回响',icon:'rune',desc:'技能冷却减少 15%',kind:'技能',apply:r=>r.p.cdr=1-(1-r.p.cdr)*.85},
 {id:'leech',name:'饮血',icon:'moon',desc:'攻击回复造成伤害的 5%',kind:'生存',apply:r=>r.p.leech+=.05},
 {id:'armor',name:'玄武',icon:'shield',desc:'受到伤害减少 15%',kind:'生存',apply:r=>r.p.def=1-(1-r.p.def)*.85},
 {id:'regen',name:'春息',icon:'leaf',desc:'每秒恢复 0.8% 最大生命',kind:'生存',apply:r=>r.p.regen+=.008},
 {id:'reach',name:'裂空',icon:'sword',desc:'普攻范围增加 20%，攻击速度增加 15%',kind:'攻击',apply:r=>{r.p.range*=1.2;r.p.rate*=.85}},
 {id:'orbit',name:'巡星',icon:'sun',desc:'增加一枚环绕星刃，持续伤害近敌',kind:'灵器',apply:r=>r.p.orbits++},
 {id:'nova',name:'星陨',icon:'flame',desc:'击败敌人引发爆炸，造成 90% 攻击伤害',kind:'元素',apply:r=>r.p.nova+=.9},
 {id:'chain',name:'雷织',icon:'bolt',desc:'每次普攻命中弹射一道雷电',kind:'元素',apply:r=>r.p.chain+=.4},
 {id:'slow',name:'寒川',icon:'snow',desc:'所有伤害附加 25% 减速',kind:'元素',apply:r=>r.p.slow=Math.max(r.p.slow,.25)},
 {id:'shield',name:'金钟',icon:'shield',desc:'立即获得 35% 最大生命护盾，持续 30 秒',kind:'生存',apply:r=>{r.p.shield+=r.p.maxHp*.35;r.p.shieldTime=30}},
 {id:'burn',name:'灼心',icon:'flame',desc:'所有攻击附加每秒 20% 攻击灼烧',kind:'元素',apply:r=>r.p.burn+=.2},
 {id:'double',name:'两仪',icon:'rune',desc:'远程额外一枚弹体；近战追加 35% 伤害',kind:'攻击',apply:r=>r.p.extra++},
 {id:'burst',name:'破晓',icon:'sun',desc:'大招伤害增加 40%',kind:'技能',apply:r=>r.p.ult*=1.4},
 {id:'heal',name:'甘露',icon:'leaf',desc:'恢复全部生命，攻击增加 8%',kind:'恢复',apply:r=>{r.p.hp=r.p.maxHp;r.p.atk*=1.08}}
];
const freshSave=()=>({version:3,name:'智阳使者',gold:12000,gems:500,xp:0,hero:'yao',skin:'original',ownedSkins:['original'],heroes:Object.fromEntries(Object.keys(heroes).map(k=>[k,{level:1,xp:0}])),runes:Object.fromEntries(Object.keys(runes).map(k=>[k,1])),loadouts:{yao:['light','fire','water',null,null,null]},clears:[0,0,0,0,0,0],best:0,stats:{kills:0,runs:0,wins:0,bosses:0,shrines:0,duels:0,time:0},history:[],achievements:[],daily:{date:'',claimed:false,kills:0,wins:0,tasks:[]},settings:{volume:35,music:true,auto:true,aim:true,quality:'high',reduce:false},suspended:null});
function sanitizeSave(data){
 if(!data||typeof data!=='object'||Array.isArray(data))throw Error('无效的存档格式');
 if(data.version!==3)throw Error('请选择天启重制版导出的存档');
 const s=freshSave(),num=(v,d,max=1e9)=>Number.isFinite(v)?clamp(Math.floor(v),0,max):d;
 s.name=typeof data.name==='string'?data.name.slice(0,16):s.name;
 for(const k of ['gold','gems','xp'])s[k]=num(data[k],s[k]);
 s.hero=heroes[data.hero]?data.hero:'yao';
 s.ownedSkins=['original',...new Set((Array.isArray(data.ownedSkins)?data.ownedSkins:[]).filter(k=>skins[k]&&k!=='original'))];s.skin=s.ownedSkins.includes(data.skin)?data.skin:'original';
 for(const k of Object.keys(heroes)){s.heroes[k].level=clamp(num(data.heroes?.[k]?.level,1,30),1,30);s.heroes[k].xp=num(data.heroes?.[k]?.xp,0);s.loadouts[k]=Array.from({length:6},(_,i)=>runes[data.loadouts?.[k]?.[i]]?data.loadouts[k][i]:null)}
 for(const k of Object.keys(runes))s.runes[k]=clamp(num(data.runes?.[k],1,10),1,10);
 s.clears=Array.from({length:6},(_,i)=>num(data.clears?.[i],0,3));s.best=num(data.best,0,10000);
 for(const k of Object.keys(s.stats))s.stats[k]=num(data.stats?.[k],0);
 s.achievements=Array.isArray(data.achievements)?data.achievements.filter(k=>typeof k==='string').slice(0,30):[];
 s.history=Array.isArray(data.history)?data.history.filter(x=>x&&heroes[x.hero]&&modes[x.mode]&&Number.isFinite(x.kills)&&Number.isFinite(x.time)).slice(0,20).map(x=>({hero:x.hero,mode:x.mode,win:!!x.win,kills:num(x.kills,0),time:num(x.time,0),wave:num(x.wave,0),date:typeof x.date==='string'?x.date.slice(0,10):''})):[];
 if(data.settings){s.settings.volume=num(data.settings.volume,35,100);s.settings.quality=data.settings.quality==='low'?'low':'high';for(const k of ['music','auto','aim','reduce'])if(typeof data.settings[k]==='boolean')s.settings[k]=data.settings[k]}
 if(data.daily&&typeof data.daily.date==='string'){s.daily={date:data.daily.date.slice(0,10),claimed:!!data.daily.claimed,kills:num(data.daily.kills,0),wins:num(data.daily.wins,0),tasks:Array.isArray(data.daily.tasks)?data.daily.tasks.filter(x=>['kills','wins'].includes(x)):[]}}
 // Imported files never inject executable or arbitrary battle state.
 return s;
}
function stats(s,id){const h=heroes[id],lv=s.heroes[id]?.level||1;
 const p={maxHp:h.hp*(1+(lv-1)*.055),atk:h.atk*(1+(lv-1)*.055),speed:h.speed,range:h.range,rate:h.rate,crit:h.crit,critDmg:1.8,cdr:0,def:id==='yan2'?.2:0,regen:id==='guang'?.007:0,leech:0,burn:id==='yan'?.25:0,slow:id==='shuang'?.3:0,chain:0,extra:0,orbits:0,nova:0,ult:1,dashRate:1};
 for(const k of s.loadouts[id]||[]){const a=runes[k];if(!a)continue;const val=a.value*(s.runes[k]||1);if(a.stat==='all'){p.atk*=1+val;p.maxHp*=1+val}else if(a.stat==='hp')p.maxHp*=1+val;else if(a.stat==='speed'||a.stat==='atk')p[a.stat]*=1+val;else p[a.stat]+=val}
 p.cdr=Math.min(.55,p.cdr);p.def=Math.min(.7,p.def);p.crit=Math.min(.85,p.crit);return p;
}
function random(r){r.seed=(r.seed*1664525+1013904223)>>>0;return r.seed/4294967296}
function rand(r,a,b){return a+(b-a)*random(r)}
function event(r,type,data={}){if(r.events.length<400)r.events.push({type,...data})}
function createRun(s,mode='campaign',chapter=0,difficulty='normal',seed=Date.now()){
 if(!modes[mode])throw Error('未知玩法');chapter=clamp(chapter,0,5);const h=heroes[s.hero],p=stats(s,s.hero);
 Object.assign(p,{x:0,y:0,hp:p.maxHp,shield:0,shieldTime:0,dir:0,invuln:0,dash:0,dashX:0,dashY:0,dashCd:0,attackCd:0,cd:[0,0,0],boost:0,slowTime:0,attackCombo:0,anim:0,orbitT:0});
 const r={schema:3,seed:seed>>>0,mode,chapter,difficulty,hero:s.hero,p,phase:'playing',time:0,wave:0,kills:0,bosses:0,combo:0,comboMax:0,comboT:0,level:1,xp:0,xpNeed:45,gold:0,gems:0,damage:0,damageTaken:0,enemies:[],projectiles:[],zones:[],warnings:[],drops:[],events:[],upgrades:[],options:[],wait:1.8,uid:0,shake:0,flash:0,hitstop:0,spawnTime:0,reroll:true,bounds:mode==='world'?1150:mode==='duel'?535:610,shrines:[],chests:[],props:[],resultAwarded:false,auto:s.settings.auto};
 r.factor=({story:.68,normal:1,hard:1.4})[difficulty]||1;
 const decorRand=()=>random(r);for(let i=0;i<44;i++){const a=decorRand()*Math.PI*2,d=mode==='world'?250+decorRand()*850:650+decorRand()*320;r.props.push({x:Math.cos(a)*d,y:Math.sin(a)*d,type:i%5===0?'temple':i%3===0?'tree':'crystal',size:.6+decorRand()*.8,seed:decorRand()})}
 if(mode==='world'){r.shrines=[{x:-580,y:-440,active:false},{x:660,y:-180,active:false},{x:90,y:730,active:false}];r.chests=[{x:-240,y:330,open:false},{x:480,y:490,open:false},{x:-760,y:210,open:false},{x:160,y:-690,open:false}];r.wave=1;r.wait=0;for(const sh of r.shrines)for(let i=0;i<4;i++)spawnEnemy(r,i%3===0?'archer':'wraith',sh.x+rand(r,-190,190),sh.y+rand(r,-140,140));event(r,'announce',{title:'星野漫游',sub:'寻访三座祭坛，驱散星庭的阴霾'})}
 if(mode==='duel'){r.wave=1;r.wait=0;const ks=Object.keys(heroes).filter(k=>k!==s.hero);r.opponent=ks[Math.floor(random(r)*ks.length)];spawnEnemy(r,'duelist',260,100);event(r,'announce',{title:'镜像斗场',sub:`对手 · ${heroes[r.opponent].name} / 预判攻击，抓住破绽`})}
 return r;
}
function spawnEnemy(r,type,x,y){const k=Math.max(0,r.wave-1),base=(1+r.chapter*.26+k*.1)*r.factor*(r.mode==='trial'?Math.pow(1.028,Math.min(k,130)):1);const e={id:++r.uid,type,x,y,radius:type==='boss'?43:type==='golem'?25:18,hp:0,maxHp:0,speed:0,atk:0,cd:rand(r,.5,1.8),anim:0,flash:0,slow:0,slowTime:0,burn:0,burnTime:0,burnTick:0,stun:0,dx:0,dy:0,phase:1,skill:rand(r,2,4),dir:0};
 const t={wraith:[220,112,70],wolf:[170,155,56],archer:[185,85,62],golem:[440,73,110],boss:[2900,80,130],duelist:[3600,180,110]}[type]||[220,112,70];
 e.maxHp=t[0]*base;e.hp=e.maxHp;e.speed=t[1];e.atk=t[2]*base;
 if(type==='boss'){e.name=chapters[r.chapter].boss;e.maxHp*=r.mode==='trial'?1+Math.floor(r.wave/3)*.18:1;e.hp=e.maxHp}
 if(type==='duelist'){e.name=heroes[r.opponent].name+' · 镜像';e.maxHp=3200*r.factor;e.hp=e.maxHp;e.atk=130*r.factor;e.speed=heroes[r.opponent].speed*.78}
 r.enemies.push(e);event(r,'spawn',{x,y,boss:type==='boss'||type==='duelist'});return e;
}
function wave(r){r.wave++;r.p.hp=Math.min(r.p.maxHp,r.p.hp+r.p.maxHp*.15);r.reroll=true;
 const boss=r.mode==='campaign'?r.wave===5:r.wave%3===0;
 if(r.mode==='trial'&&r.wave>1&&(r.wave-1)%3===0){r.chapter=(r.chapter+1)%6;event(r,'notice',{text:'星门轮转 · '+chapters[r.chapter].name})}
 if(boss){spawnEnemy(r,'boss',0,-340);for(let i=0;i<Math.min(5,2+Math.floor(r.wave/6));i++){const a=random(r)*Math.PI*2;spawnEnemy(r,'wolf',Math.cos(a)*450,Math.sin(a)*450)}event(r,'announce',{title:'首领降临',sub:chapters[r.chapter].boss})}
 else{const count=7+Math.min(15,Math.floor(r.wave*1.3))+r.chapter;for(let i=0;i<count;i++){const a=2*Math.PI*i/count+random(r)*.3,rad=rand(r,340,540);spawnEnemy(r,['wraith','wolf','archer',r.wave>2?'golem':'wolf'][i%4],Math.cos(a)*rad,Math.sin(a)*rad)}event(r,'announce',{title:`第 ${r.wave} 重试炼`,sub:'击败所有来敌 · 星庭因你而醒'})}
}
function offer(r){r.phase='choosing';r.options=selectOptions(r);r.projectiles=r.projectiles.filter(p=>!p.enemy);r.warnings=[];event(r,'choice')}
function selectOptions(r){const available=upgrades.filter(u=>['power','vital','heal'].includes(u.id)||r.upgrades.filter(k=>k===u.id).length<5);const out=[];while(out.length<3&&available.length)out.push(available.splice(Math.floor(random(r)*available.length),1)[0].id);return out}
function choose(r,id){if(r.phase!=='choosing'||!r.options.includes(id))return false;const u=upgrades.find(u=>u.id===id);u.apply(r);r.p.crit=Math.min(.9,r.p.crit);r.p.cdr=Math.min(.7,r.p.cdr);r.p.def=Math.min(.8,r.p.def);r.upgrades.push(id);r.phase='playing';r.options=[];r.wait=1.4;r.p.invuln=1;event(r,'upgrade',{name:u.name});return true}
function reroll(r){if(r.phase!=='choosing'||!r.reroll)return false;r.options=selectOptions(r);r.reroll=false;return true}
function nearest(r,range=Infinity,x=r.p.x,y=r.p.y){let best=null,d=range;for(const e of r.enemies){if(e.hp<=0)continue;const n=Math.hypot(x-e.x,y-e.y);if(n<d){d=n;best=e}}return best}
function hurt(r,e,damage,crit=false,proc=true){if(e.hp<=0)return;let val=damage;if(r.hero==='ying'&&e.hp<e.maxHp*.35)val*=1.4;const actual=Math.min(e.hp,val);e.hp-=val;e.flash=.12;r.damage+=actual;
 if(r.p.leech)r.p.hp=Math.min(r.p.maxHp,r.p.hp+actual*r.p.leech);
 if(r.p.burn&&proc){e.burn=r.p.atk*r.p.burn;e.burnTime=3}
 if(r.p.slow&&proc){e.slow=Math.max(e.slow,r.p.slow);e.slowTime=2}
 event(r,'hit',{x:e.x,y:e.y,value:Math.round(val),crit,color:heroes[r.hero].color});r.shake=Math.max(r.shake,crit?4:1.2);
 if(crit&&r.hero==='lei'&&proc){const other=r.enemies.find(t=>t!==e&&t.hp>0&&Math.hypot(t.x-e.x,t.y-e.y)<230);if(other){hurt(r,other,r.p.atk*.6,false,false);event(r,'lightning',{x:e.x,y:e.y,tx:other.x,ty:other.y})}}
 if(e.hp<=0)kill(r,e);
}
function kill(r,e){r.kills++;r.combo++;r.comboMax=Math.max(r.comboMax,r.combo);r.comboT=4;r.gold+=e.type==='boss'?250:e.type==='duelist'?300:12;r.xp+=e.type==='boss'?130:e.type==='golem'?28:17;
 if(e.type==='boss'||e.type==='duelist'){r.bosses++;r.gems+=e.type==='boss'?35:25;event(r,'bossDead',{x:e.x,y:e.y})}else event(r,'death',{x:e.x,y:e.y,color:'#acb3a4'});
 r.drops.push({x:e.x,y:e.y,type:random(r)<.13?'heal':'xp',value:e.type==='boss'?80:15,t:0});
 if(r.p.nova){event(r,'nova',{x:e.x,y:e.y,radius:115});for(const n of r.enemies)if(n!==e&&n.hp>0&&Math.hypot(n.x-e.x,n.y-e.y)<115)hurt(r,n,r.p.atk*r.p.nova,false,false)}
 if(r.xp>=r.xpNeed){r.xp-=r.xpNeed;r.level++;r.xpNeed=Math.round(r.xpNeed*1.35);r.p.atk*=1.045;r.p.maxHp*=1.04;r.p.hp=Math.min(r.p.maxHp,r.p.hp+r.p.maxHp*.14);event(r,'level',{level:r.level})}
}
function damagePlayer(r,val){const p=r.p;if(p.invuln>0||r.phase!=='playing')return false;val*=1-p.def;if(p.shield>0){const absorbed=Math.min(val,p.shield);p.shield-=absorbed;val-=absorbed}p.hp-=val;r.damageTaken+=val;p.invuln=.35;r.combo=0;r.shake=7;r.flash=.14;event(r,'hurt',{value:Math.round(val),x:p.x,y:p.y});if(p.hp<=0){p.hp=0;r.phase='lost';event(r,'end',{win:false})}return true}
function projectile(r,x,y,a,damage,enemy=false,opt={}){if(r.projectiles.length>=150)return;r.projectiles.push({id:++r.uid,x,y,dx:Math.cos(a),dy:Math.sin(a),speed:enemy?250:640,damage,enemy,radius:enemy?9:7,life:enemy?5:1.4,hit:[],color:enemy?'#f28d7f':heroes[r.hero].color,pierce:false,...opt})}
function radial(r,x,y,rad,damage,opts={}){event(r,'ring',{x,y,radius:rad,color:heroes[r.hero].color});for(const e of r.enemies){const dist=Math.hypot(e.x-x,e.y-y);if(e.hp<=0||dist>rad+e.radius)continue;hurt(r,e,damage,opts.crit||false);if(opts.stun)e.stun=opts.stun;if(opts.push){e.dx=(e.x-x)/(dist||1)*opts.push;e.dy=(e.y-y)/(dist||1)*opts.push}}}
function aim(r,input){const p=r.p;if(Number.isFinite(input.ax)&&Number.isFinite(input.ay)&&!input.autoAim){p.dir=Math.atan2(input.ay-p.y,input.ax-p.x);return p.dir}const e=nearest(r,700);if(e)p.dir=Math.atan2(e.y-p.y,e.x-p.x);else if(input.mx||input.my)p.dir=Math.atan2(input.my,input.mx);return p.dir}
function attack(r){const p=r.p,h=heroes[r.hero];if(r.phase!=='playing'||p.attackCd>0)return false;p.attackCd=p.rate;p.anim=.22;p.attackCombo=(p.attackCombo+1)%3;const c=random(r)<p.crit,combo=r.hero==='yao'&&p.attackCombo===0;const dmg=p.atk*(c?p.critDmg:1)*(combo?1.7:1);
 if(h.ranged){projectile(r,p.x,p.y,p.dir,dmg,false,{crit:c,life:p.range/640});const extra=p.extra+(r.hero==='feng'&&random(r)<.25?2:0);for(let i=0;i<extra;i++)projectile(r,p.x,p.y,p.dir+(i%2===0?1:-1)*(.16+.09*Math.floor(i/2)),dmg*.7,false,{crit:c,life:p.range/640})}
 else{event(r,'slash',{x:p.x,y:p.y,dir:p.dir,radius:p.range,color:h.color,heavy:combo});for(const e of r.enemies){const dx=e.x-p.x,dy=e.y-p.y,d=Math.hypot(dx,dy),ang=Math.atan2(dy,dx);if(e.hp>0&&d<p.range+e.radius&&(Math.cos(ang-p.dir)>.1||d<55)){hurt(r,e,dmg*(1+p.extra*.35),c);e.dx+=dx/(d||1)*(r.hero==='yan2'?175:85);e.dy+=dy/(d||1)*(r.hero==='yan2'?175:85);if(combo)p.hp=Math.min(p.maxHp,p.hp+p.maxHp*.012);if(p.chain)chain(r,e,p.chain)}}}
 event(r,'attack');return true;
}
function chain(r,from,mult){const e=r.enemies.find(e=>e!==from&&e.hp>0&&Math.hypot(e.x-from.x,e.y-from.y)<260);if(e){hurt(r,e,r.p.atk*mult,false,false);event(r,'lightning',{x:from.x,y:from.y,tx:e.x,ty:e.y})}}
function useDash(r,mx=0,my=0){const p=r.p;if(r.phase!=='playing'||p.dashCd>0)return false;const len=Math.hypot(mx,my);p.dashX=len?mx/len:Math.cos(p.dir);p.dashY=len?my/len:Math.sin(p.dir);p.dash=.19;p.invuln=.32;p.dashCd=2.4*p.dashRate;event(r,'dash',{x:p.x,y:p.y,dir:Math.atan2(p.dashY,p.dashX)});return true}
function useSkill(r,i){const p=r.p,id=r.hero;if(r.phase!=='playing'||p.cd[i]>0||!heroes[id].skills[i])return false;p.cd[i]=heroes[id].skills[i].cd*(1-p.cdr);p.anim=.4;const target=nearest(r,600),tx=target?target.x:p.x+Math.cos(p.dir)*220,ty=target?target.y:p.y+Math.sin(p.dir)*220;
 event(r,'skill',{i,name:heroes[id].skills[i].name,x:p.x,y:p.y,color:heroes[id].color});
 if(i===0){
  if(id==='yao'||id==='feng'||id==='guang'){for(let j=-1;j<=1;j++)projectile(r,p.x,p.y,p.dir+j*.19,p.atk*(id==='feng'?2.2:id==='yao'?1.6:1.8),false,{radius:12,pierce:true,life:1.1,speed:780})}
  if(id==='yan'||id==='shuang'){const n=id==='yan'?5:7;for(let j=0;j<n;j++)projectile(r,p.x,p.y,p.dir+(j-(n-1)/2)*.16,p.atk*(id==='yan'?1.4:1.1),false,{radius:id==='yan'?12:9,pierce:true})}
  if(id==='ying'){p.dashX=Math.cos(p.dir);p.dashY=Math.sin(p.dir);p.dash=.26;p.invuln=.5;radial(r,p.x+p.dashX*130,p.y+p.dashY*130,180,p.atk*2.6)}
  if(id==='yan2')radial(r,p.x,p.y,200,p.atk*2.6,{stun:1.3,push:250});
  if(id==='lei'){radial(r,tx,ty,155,p.atk*3.6);event(r,'lightning',{x:tx,y:ty,tx,ty:ty-220})}
 }else if(i===1){
  if(['yao','yan2','shuang','lei'].includes(id)){p.shield=Math.max(p.shield,p.maxHp*({yao:.3,yan2:.45,shuang:.25,lei:.25}[id]));p.shieldTime=id==='yan2'?6:5;event(r,'ring',{x:p.x,y:p.y,radius:90,color:heroes[id].color})}
  if(id==='yan')r.zones.push({x:p.x,y:p.y,radius:200,life:5,maxLife:5,tick:0,damage:p.atk*.65,type:'fire'});
  if(id==='shuang')radial(r,p.x,p.y,230,p.atk*.5,{stun:2});
  if(id==='ying'){p.invuln=2;p.hp=Math.min(p.maxHp,p.hp+p.maxHp*.12)}
  if(id==='feng'){p.boost=4;p.hp=Math.min(p.maxHp,p.hp+p.maxHp*.08)}
  if(id==='guang'){p.hp=Math.min(p.maxHp,p.hp+p.maxHp*.3);radial(r,p.x,p.y,240,p.atk*.4,{push:320})}
  if(id==='lei')radial(r,p.x,p.y,210,p.atk*1.5,{stun:.8});
 }else{
  p.invuln=Math.max(p.invuln,1.2);r.shake=10;
  if(['yao','yan2','guang','ying'].includes(id)){const rad=id==='ying'?350:310;for(const e of r.enemies){if(e.hp>0&&Math.hypot(e.x-p.x,e.y-p.y)<rad){if(id==='ying'&&e.hp<e.maxHp*.35&&!['boss','duelist'].includes(e.type))hurt(r,e,e.hp+1,true);else hurt(r,e,p.atk*(id==='yan2'?6.5:id==='guang'?5:5.5)*p.ult,true);e.stun=id==='yan2'?3:1}}event(r,'ultimate',{x:p.x,y:p.y,radius:rad,color:heroes[id].color});if(id==='guang')p.hp=Math.min(p.maxHp,p.hp+p.maxHp*.4)}
  if(id==='yan'){radial(r,tx,ty,290,p.atk*6.5*p.ult,{stun:1});event(r,'ultimate',{x:tx,y:ty,radius:290,color:heroes[id].color})}
  if(id==='shuang'||id==='feng'){r.zones.push({x:tx,y:ty,radius:260,life:6,maxLife:6,tick:0,damage:p.atk*.9*p.ult,type:id==='shuang'?'ice':'wind'});event(r,'ultimate',{x:tx,y:ty,radius:260,color:heroes[id].color})}
  if(id==='lei'){for(const e of r.enemies)if(e.hp>0){hurt(r,e,p.atk*6*p.ult,true);e.stun=1.5;event(r,'lightning',{x:e.x,y:e.y,tx:e.x,ty:e.y-220})}event(r,'ultimate',{x:p.x,y:p.y,radius:500,color:heroes[id].color})}
 }
 return true;
}
function warning(r,e,type,x,y,rad=80,delay=.9,opts={}){r.warnings.push({id:++r.uid,owner:e.id,type,x,y,radius:rad,time:delay,maxTime:delay,damage:e.atk,...opts})}
function updateEnemy(r,e,dt){const p=r.p;e.anim+=dt;e.flash=Math.max(0,e.flash-dt);e.cd-=dt;e.skill-=dt;e.stun=Math.max(0,e.stun-dt);e.slowTime-=dt;if(e.slowTime<=0)e.slow=0;
 if(e.burnTime>0){e.burnTime-=dt;e.burnTick-=dt;if(e.burnTick<=0){e.burnTick=.5;hurt(r,e,e.burn*.5,false,false)}}if(e.hp<=0)return;
 e.x=clamp(e.x+e.dx*dt,-r.bounds,r.bounds);e.y=clamp(e.y+e.dy*dt,-r.bounds,r.bounds);e.dx*=Math.pow(.03,dt);e.dy*=Math.pow(.03,dt);
 if(e.stun>0)return;const dx=p.x-e.x,dy=p.y-e.y,d=Math.hypot(dx,dy)||1;e.dir=Math.atan2(dy,dx);
 if(r.mode==='world'&&d>600&&e.type!=='boss')return;
 if(['boss','duelist'].includes(e.type)){
  if(e.hp<e.maxHp*.5&&e.phase===1){e.phase=2;e.speed*=1.3;e.skill=.2;event(r,'announce',{title:e.type==='boss'?'狂暴觉醒':'镜像解放',sub:'攻击节奏加速 · 注意地面预警'})}
  if(e.skill<=0){e.skill=e.phase===2?2.5:3.6;const n=Math.floor(random(r)*3);if(n===0){warning(r,e,'circle',p.x,p.y,e.type==='boss'?155:100,.95);if(e.phase===2){warning(r,e,'circle',p.x+130,p.y-110,100,1.2);warning(r,e,'circle',p.x-130,p.y+110,100,1.45)}}else if(n===1){warning(r,e,'ring',e.x,e.y,e.type==='boss'?290:200,1.05);if(e.type==='boss')for(let j=0;j<8;j++)projectile(r,e.x,e.y,j*Math.PI/4,e.atk*.65,true,{speed:180,radius:9})}else{warning(r,e,'line',e.x,e.y,65,.85,{dir:e.dir,length:550});if(e.type==='duelist')e.stun=.6}
   // Each guardian adds a different readable elemental pattern.
   if(e.type==='boss'&&r.chapter===1){for(let j=0;j<3;j++)warning(r,e,'circle',p.x+(j-1)*160,p.y,88,1.1+j*.15,{burn:true})}
   if(e.type==='boss'&&r.chapter===2){e.x=clamp(p.x+Math.cos(r.time)*260,-r.bounds,r.bounds);e.y=clamp(p.y+Math.sin(r.time)*260,-r.bounds,r.bounds);event(r,'trail',{x:e.x,y:e.y,color:'#a6d1b8'});warning(r,e,'line',e.x,e.y,40,1,{dir:Math.atan2(p.y-e.y,p.x-e.x),length:470})}
   if(e.type==='boss'&&r.chapter===3){for(let j=-1;j<=1;j++)projectile(r,e.x,e.y,e.dir+j*.3,e.atk*.6,true,{speed:205,color:'#b8e3ef',slow:true})}
   if(e.type==='boss'&&r.chapter===4){for(let j=0;j<4;j++){const a=r.time+j*Math.PI/2;warning(r,e,'circle',p.x+Math.cos(a)*165,p.y+Math.sin(a)*165,80,1.05+j*.1)}}
   if(e.type==='boss'&&r.chapter===5){for(let j=0;j<12;j++)projectile(r,e.x,e.y,r.time+j*TAU/12,e.atk*.45,true,{speed:165,color:'#e9c078'});warning(r,e,'circle',p.x,p.y,180,1.2)}
  }
 }
 if(e.type==='archer'){if(d>340){e.x+=dx/d*e.speed*dt*(1-e.slow);e.y+=dy/d*e.speed*dt*(1-e.slow)}else if(d<190){e.x-=dx/d*e.speed*dt;e.y-=dy/d*e.speed*dt}if(e.cd<=0&&d<600){e.cd=2;projectile(r,e.x,e.y,e.dir,e.atk,true);event(r,'enemyShot',{x:e.x,y:e.y})}}
 else{const reach=e.type==='boss'?95:e.type==='golem'?80:e.type==='duelist'?125:47;if(d>reach){e.x+=dx/d*e.speed*(1-e.slow)*dt;e.y+=dy/d*e.speed*(1-e.slow)*dt}else if(e.cd<=0){e.cd=e.type==='wolf'?1.3:e.type==='duelist'?1.5:1.9;warning(r,e,'circle',p.x,p.y,e.type==='golem'?100:e.type==='boss'?125:60,e.type==='wolf'?.48:.7)}
  if(e.type==='duelist'&&e.cd<=0&&d<460&&d>125){e.cd=1.4;projectile(r,e.x,e.y,e.dir,e.atk*.7,true,{speed:300})}
 }
 e.x=clamp(e.x,-r.bounds+25,r.bounds-25);e.y=clamp(e.y,-r.bounds+25,r.bounds-25);
}
function interact(r){if(r.phase!=='playing'||r.mode!=='world')return false;for(const sh of r.shrines){if(sh.active||Math.hypot(sh.x-r.p.x,sh.y-r.p.y)>105)continue;const guarded=r.enemies.some(e=>e.hp>0&&Math.hypot(e.x-sh.x,e.y-sh.y)<260);if(guarded){event(r,'notice',{text:'先清除祭坛周围的守卫'});return false}sh.active=true;r.gold+=160;r.gems+=15;r.p.hp=Math.min(r.p.maxHp,r.p.hp+r.p.maxHp*.2);event(r,'shrine',{x:sh.x,y:sh.y});
  if(r.shrines.every(x=>x.active)){spawnEnemy(r,'boss',0,0);event(r,'announce',{title:'星门已开',sub:'蚀星守卫现身 · 夺回星庭的光'})}else{offer(r);r.wait=0}return true}return false}
function step(r,dt,input={}){if(r.phase!=='playing')return;dt=clamp(dt,0,.05);r.time+=dt;const p=r.p;r.shake=Math.max(0,r.shake-dt*22);r.flash=Math.max(0,r.flash-dt);r.comboT-=dt;if(r.comboT<=0)r.combo=0;
 p.invuln=Math.max(0,p.invuln-dt);p.anim=Math.max(0,p.anim-dt);p.attackCd=Math.max(0,p.attackCd-dt);p.dashCd=Math.max(0,p.dashCd-dt);p.boost=Math.max(0,p.boost-dt);p.slowTime=Math.max(0,(p.slowTime||0)-dt);p.shieldTime-=dt;if(p.shieldTime<=0)p.shield=0;for(let i=0;i<3;i++)p.cd[i]=Math.max(0,p.cd[i]-dt);p.hp=Math.min(p.maxHp,p.hp+p.maxHp*p.regen*dt);
 const mx=input.mx||0,my=input.my||0,len=Math.hypot(mx,my)||1;aim(r,input);
 if(p.dash>0){p.dash-=dt;p.x+=p.dashX*930*dt;p.y+=p.dashY*930*dt;if(Math.floor(r.time*50)%2===0)event(r,'trail',{x:p.x,y:p.y,color:heroes[r.hero].color})}
 else{const move=p.speed*(p.boost?1.55:1)*(p.slowTime>0?.65:1);p.x+=mx/Math.max(1,len)*move*dt;p.y+=my/Math.max(1,len)*move*dt}
 p.x=clamp(p.x,-r.bounds+30,r.bounds-30);p.y=clamp(p.y,-r.bounds+30,r.bounds-30);
 if((input.attack||r.auto)&&nearest(r,p.range+60))attack(r);
 if(r.wait>0){r.wait-=dt;if(r.wait<=0&&['campaign','trial'].includes(r.mode))wave(r)}
 for(const e of r.enemies){if(e.hp>0)updateEnemy(r,e,dt);if(r.phase!=='playing')break}if(r.phase!=='playing')return;
 // Soft body separation avoids piling every enemy on the same point.
 for(let i=0;i<r.enemies.length;i++)for(let j=i+1;j<r.enemies.length;j++){const a=r.enemies[i],b=r.enemies[j];if(a.hp<=0||b.hp<=0)continue;const dx=a.x-b.x,dy=a.y-b.y,d=Math.hypot(dx,dy),min=(a.radius+b.radius)*.8;if(d>0&&d<min){const f=(min-d)*.5;a.x+=dx/d*f;a.y+=dy/d*f;b.x-=dx/d*f;b.y-=dy/d*f}}
 for(const w of r.warnings){w.time-=dt;if(w.time<=0){const owner=r.enemies.find(e=>e.id===w.owner&&e.hp>0);if(owner){let hit=false;if(w.type==='line'){const dx=p.x-w.x,dy=p.y-w.y,along=dx*Math.cos(w.dir)+dy*Math.sin(w.dir),cross=Math.abs(-dx*Math.sin(w.dir)+dy*Math.cos(w.dir));hit=along>0&&along<w.length&&cross<w.radius;owner.x=clamp(owner.x+Math.cos(w.dir)*200,-r.bounds,r.bounds);owner.y=clamp(owner.y+Math.sin(w.dir)*200,-r.bounds,r.bounds)}else hit=Math.hypot(p.x-w.x,p.y-w.y)<w.radius;
   if(hit)damagePlayer(r,w.damage);if(w.burn)r.zones.push({x:w.x,y:w.y,radius:w.radius,life:2.5,maxLife:2.5,tick:.3,damage:w.damage*.25,type:'fire',enemy:true});event(r,'enemyImpact',{x:w.x,y:w.y,radius:w.radius,type:w.type,dir:w.dir,length:w.length});}}
 }
 r.warnings=r.warnings.filter(w=>w.time>0&&r.enemies.some(e=>e.id===w.owner&&e.hp>0));
 for(const b of r.projectiles){b.life-=dt;b.x+=b.dx*b.speed*dt;b.y+=b.dy*b.speed*dt;
  if(b.enemy){if(Math.hypot(p.x-b.x,p.y-b.y)<b.radius+18){if(damagePlayer(r,b.damage)&&b.slow)p.slowTime=2.5;b.life=0}}
  else for(const e of r.enemies){if(e.hp<=0||b.hit.includes(e.id)||Math.hypot(e.x-b.x,e.y-b.y)>e.radius+b.radius)continue;hurt(r,e,b.damage,!!b.crit);b.hit.push(e.id);if(p.chain)chain(r,e,p.chain);if(!b.pierce){b.life=0;break}}
 }
 r.projectiles=r.projectiles.filter(b=>b.life>0);
 for(const z of r.zones){z.life-=dt;z.tick-=dt;if(z.tick<=0){z.tick=.5;if(z.enemy){if(Math.hypot(p.x-z.x,p.y-z.y)<z.radius)damagePlayer(r,z.damage)}else for(const e of r.enemies)if(e.hp>0&&Math.hypot(e.x-z.x,e.y-z.y)<z.radius){hurt(r,e,z.damage);if(z.type==='ice'){e.slow=.65;e.slowTime=1}if(z.type==='wind'){e.dx+=(z.x-e.x)*.3;e.dy+=(z.y-e.y)*.3}}}}
 r.zones=r.zones.filter(z=>z.life>0);
 p.orbitT+=dt;if(p.orbits){for(let i=0;i<p.orbits;i++){const a=r.time*2.8+i*Math.PI*2/p.orbits,x=p.x+Math.cos(a)*105,y=p.y+Math.sin(a)*105;if(p.orbitT>=.32)for(const e of r.enemies)if(e.hp>0&&Math.hypot(e.x-x,e.y-y)<40)hurt(r,e,p.atk*.5)}}if(p.orbitT>=.32)p.orbitT=0;
 for(const d of r.drops){d.t+=dt;const dx=p.x-d.x,dy=p.y-d.y,n=Math.hypot(dx,dy);if(n<140){d.x+=dx*dt*7;d.y+=dy*dt*7}if(n<25){if(d.type==='heal'){p.hp=Math.min(p.maxHp,p.hp+p.maxHp*.08);event(r,'heal',{x:p.x,y:p.y})}d.t=99}}
 r.drops=r.drops.filter(d=>d.t<25);
 r.enemies=r.enemies.filter(e=>e.hp>0);
 if(r.mode==='world'){
  for(const chest of r.chests)if(!chest.open&&Math.hypot(chest.x-p.x,chest.y-p.y)<65){chest.open=true;r.gold+=120;r.gems+=8;p.hp=Math.min(p.maxHp,p.hp+p.maxHp*.12);event(r,'chest',{x:chest.x,y:chest.y})}
  if(r.shrines.every(s=>s.active)&&r.bosses>0&&r.enemies.length===0){r.phase='won';event(r,'end',{win:true})}
 }else if(r.mode==='duel'){if(!r.enemies.length){r.phase='won';event(r,'end',{win:true})}}
 else if(r.wait<=0&&r.wave>0&&!r.enemies.length){if(r.mode==='campaign'&&r.wave>=5){r.phase='won';event(r,'end',{win:true})}else offer(r)}
}
function packRun(r){if(!r||!['playing','choosing'].includes(r.phase))return null;const data=JSON.parse(JSON.stringify(r));data.events=[];data.projectiles=data.projectiles.filter(p=>!p.enemy);data.warnings=[];return data}
function restoreRun(data){if(!data||data.schema!==3||!heroes[data.hero]||!modes[data.mode]||!['playing','choosing'].includes(data.phase)||!Number.isFinite(data.p?.hp)||!Number.isFinite(data.time)||!Array.isArray(data.enemies))return null;
 try{const r=JSON.parse(JSON.stringify(data));r.events=[];r.p.invuln=1.5;r.warnings=[];return r}catch{return null}}
function award(s,r,abandon=false,date=''){if(r.resultAwarded)return null;r.resultAwarded=true;const win=r.phase==='won';const mult=r.difficulty==='hard'?1.5:r.difficulty==='story'?.8:1;const gold=Math.round((r.gold+(win?400:0))*mult),gems=Math.round((r.gems+(win?30:0))*mult);s.gold+=gold;s.gems+=gems;s.xp+=r.kills*8+(win?180:20);s.heroes[r.hero].xp+=r.kills*5+(win?100:0);s.stats.kills+=r.kills;s.stats.runs++;s.stats.wins+=win?1:0;s.stats.bosses+=r.bosses;s.stats.time+=Math.floor(r.time);s.stats.shrines+=r.shrines.filter(x=>x.active).length;s.stats.duels+=r.mode==='duel'&&win?1:0;
 if(r.mode==='campaign'&&win){const stars=r.difficulty==='hard'?3:r.difficulty==='normal'?2:1;s.clears[r.chapter]=Math.max(s.clears[r.chapter],stars)}
 if(r.mode==='trial')s.best=Math.max(s.best,r.wave);s.daily.kills+=r.kills;s.daily.wins+=win?1:0;s.suspended=null;s.history.unshift({hero:r.hero,mode:r.mode,win,kills:r.kills,time:Math.floor(r.time),wave:r.wave,date});s.history=s.history.slice(0,20);return{gold,gems,win,abandon}}
return{heroes,chapters,modes,skins,runes,upgrades,clamp,freshSave,sanitizeSave,stats,createRun,step,attack,useSkill,useDash,choose,reroll,interact,packRun,restoreRun,award,nearest,spawnEnemy,damagePlayer,radial};
})();
if(typeof module!=='undefined')module.exports=GameEngine;
