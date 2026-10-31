/* Original vector artwork and perspective renderer; no external assets. */
const Painter = (() => {
'use strict';
const TAU=Math.PI*2;
let appearance='original';
function poly(c,pts,fill,stroke){c.beginPath();pts.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));c.closePath();if(fill){c.fillStyle=fill;c.fill()}if(stroke){c.strokeStyle=stroke;c.stroke()}}
function line(c,pts,color,width=1){c.beginPath();pts.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));c.strokeStyle=color;c.lineWidth=width;c.stroke()}
function circle(c,x,y,r,color,stroke){c.beginPath();c.arc(x,y,r,0,TAU);if(color){c.fillStyle=color;c.fill()}if(stroke){c.strokeStyle=stroke;c.stroke()}}
function ellipse(c,x,y,rx,ry,color,stroke){c.beginPath();c.ellipse(x,y,rx,ry,0,0,TAU);if(color){c.fillStyle=color;c.fill()}if(stroke){c.strokeStyle=stroke;c.stroke()}}
function glow(c,x,y,r,col){const g=c.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,col);g.addColorStop(1,col.slice(0,7)+'00');circle(c,x,y,r,g)}
function resize(canvas,quality=1){const rect=canvas.getBoundingClientRect(),dpr=Math.min(window.devicePixelRatio||1,quality===.7?1.2:2)*quality,w=Math.max(1,Math.round(rect.width)),h=Math.max(1,Math.round(rect.height));if(canvas.width!==Math.round(w*dpr)||canvas.height!==Math.round(h*dpr)){canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr)}const c=canvas.getContext('2d',{alpha:false});c.setTransform(dpr,0,0,dpr,0,0);return{c,w,h,dpr}}
function hero(c,id,x,y,scale=1,t=0,dir=0,attack=0,ghost=false,skinId=appearance){
 const h=GameEngine.heroes[id]||GameEngine.heroes.yao,skin=GameEngine.skins[skinId]||{},col=skin.color||h.color,dark=skin.dark||h.dark;
 c.save();c.translate(x,y);c.scale(scale,scale);if(ghost)c.globalAlpha=.25;
 ellipse(c,0,0,24,9,'#04141977');const bob=Math.sin(t*3)*1.6;c.translate(0,bob);
 const cape=Math.sin(t*2.5)*6;
 // Split silk cloak, angular armour and a luminous, faceted face.
 poly(c,[[-12,-68],[-31,-47],[-31+cape,-13],[-17,-21],[-6,-42]],dark);
 poly(c,[[12,-68],[29,-42],[34-cape,-13],[13,-20],[5,-43]],dark);
 poly(c,[[-17,-51],[-27,-19],[-10,-29],[-4,-45]],col+'50');
 poly(c,[[17,-51],[25,-15],[10,-24],[4,-45]],col+'38');
 poly(c,[[-8,-30],[-18,-7],[-15,-1],[-4,-5],[0,-30]],'#142b32');
 poly(c,[[3,-31],[6,-7],[17,-1],[21,-5],[13,-32]],'#21363b');
 poly(c,[[-15,-6],[-18,-1],[-3,1],[-5,-5]],col+'aa');poly(c,[[7,-6],[7,0],[23,1],[19,-5]],col+'aa');
 poly(c,[[-12,-64],[-16,-36],[0,-26],[17,-38],[12,-64]],dark);
 poly(c,[[0,-63],[-8,-54],[-5,-34],[1,-31],[8,-44],[7,-57]],col+'b0');
 poly(c,[[-15,-64],[-24,-56],[-20,-47],[-7,-55]],col);poly(c,[[14,-64],[24,-56],[20,-46],[7,-55]],col);
 line(c,[[-13,-35],[1,-31],[14,-37]],col,2);
 circle(c,1,-47,3,'#fff1b9');glow(c,1,-47,18,col+'50');
 poly(c,[[-7,-81],[-10,-71],[-4,-63],[5,-63],[12,-73],[8,-81]],'#182e32');
 poly(c,[[-7,-81],[1,-85],[10,-80],[6,-69],[0,-64],[-4,-73]],col);
 poly(c,[[1,-85],[10,-80],[6,-69],[0,-64],[1,-75]],'#667c77');
 line(c,[[-5,-75],[-1,-74]],'#fff5c8',1.6);line(c,[[4,-75],[8,-76]],'#fff5c8',1.6);
 if(id==='yao'||id==='guang'){line(c,[[-7,-81],[-12,-91],[-2,-85],[2,-95],[7,-85],[16,-91],[10,-80]],col,2);circle(c,2,-90,2,'#fff6cc')}
 if(id==='yan')poly(c,[[-8,-81],[-13,-94],[-4,-90],[0,-104],[7,-90],[16,-95],[11,-80]],col+'cc');
 if(id==='shuang')poly(c,[[-9,-81],[-15,-97],[-3,-90],[2,-103],[10,-88],[17,-95],[12,-81]],col+'b0');
 if(id==='ying'){poly(c,[[-11,-68],[-16,-80],[-5,-91],[5,-89],[17,-75],[13,-64],[9,-81],[0,-85],[-6,-80]],dark);line(c,[[-5,-72],[9,-72]],col,1.6)}
 if(id==='yan2'){poly(c,[[-21,-61],[-35,-67],[-43,-32],[-22,-16],[-17,-44]],col);poly(c,[[-35,-62],[-39,-33],[-24,-22],[-22,-46]],dark);line(c,[[-29,-53],[-32,-39],[-24,-31]],col,2)}
 const swing=attack?Math.sin(attack*10)*.8:Math.sin(t*2)*.05;
 c.save();c.translate(18,-49);c.rotate(-.22+swing);
 if(['yao','ying','yan2'].includes(id)){const length=id==='ying'?38:62;line(c,[[0,14],[0,-length]],col,3);poly(c,[[0,-length-8],[-3,-length+3],[-2,-5],[3,-8],[3,-length+2]],'#f4e9c5');line(c,[[-8,-5],[8,-5]],col,3);glow(c,0,-length/2,25,col+'44')}
 else if(id==='feng'){c.beginPath();c.moveTo(0,-31);c.quadraticCurveTo(28,-4,0,30);c.strokeStyle=col;c.lineWidth=3;c.stroke();line(c,[[0,-31],[0,30]],'#cfeecfa0',.8);line(c,[[-15,0],[24,0]],col,1.5)}
 else{line(c,[[0,26],[0,-61]],col,2.5);poly(c,[[0,-77],[-8,-64],[0,-50],[9,-64]],col+'bb');glow(c,0,-64,27,col+'44');circle(c,0,-64,3,'#fff6db')}
 c.restore();if(id==='guang'){ellipse(c,1,-100,19,5,null,col+'aa');glow(c,0,-70,60,col+'15')}
 if(id==='lei'){line(c,[[-30,-78],[-38,-51],[-30,-54],[-37,-31]],col+'80',1);line(c,[[29,-83],[33,-57],[27,-61],[35,-42]],col+'80',1)}
 // Floating sash.
 c.beginPath();c.moveTo(-13,-48);c.bezierCurveTo(-30,-38,-38-cape,-55,-48-cape,-41);c.strokeStyle=col+'aa';c.lineWidth=3;c.stroke();
 c.restore();
}
function crystal(c,x,y,s=1,col='#93d5c3',t=0){c.save();c.translate(x,y);c.scale(s,s);ellipse(c,0,0,20,6,'#06161950');poly(c,[[0,-61],[-13,-32],[-8,-5],[6,0],[15,-30]],col+'75');poly(c,[[0,-61],[0,-13],[6,0],[15,-30]],col+'40');line(c,[[0,-61],[0,-13],[-8,-5]],col+'b0',1);poly(c,[[-19,-28],[-25,-14],[-20,0],[-11,-4]],col+'55');glow(c,0,-24,47,col+'20');circle(c,Math.sin(t)*7,-66,1,col);c.restore()}
function tree(c,x,y,s=1,col='#739c83',kind=0){c.save();c.translate(x,y);c.scale(s,s);ellipse(c,0,0,38,11,'#04161940');line(c,[[0,0],[4,-80],[0,-132]],'#426260',7);line(c,[[2,-50],[-26,-100]],'#426260',4);line(c,[[3,-65],[26,-115]],'#426260',4);
 if(kind===2){for(let i=0;i<7;i++){line(c,[[i*7-21,0],[i*8-24,-150-i*4]],'#5e907666',3);for(let j=0;j<3;j++)poly(c,[[i*8-24,-60-j*28],[i*8-48,-87-j*25],[i*8-22,-76-j*27],[i*8-1,-99-j*28]],col+'90')}}
 else{for(const [px,py,rad]of [[-26,-103,29],[29,-113,31],[-2,-134,40],[-22,-137,23]]){ellipse(c,px,py,rad,rad*.57,col+'a0');ellipse(c,px-5,py-6,rad*.72,rad*.37,col+'60')}line(c,[[-40,-104],[-12,-117],[18,-127]],col+'aa',1)}c.restore()}
function temple(c,x,y,s=1,col='#658e87',t=0){c.save();c.translate(x,y);c.scale(s,s);ellipse(c,0,5,82,20,'#0314164a');poly(c,[[-61,0],[10,25],[66,0],[0,-22]],'#2d514f');poly(c,[[-55,-72],[-55,-4],[0,13],[54,-4],[54,-72]],'#244646');poly(c,[[0,-75],[0,13],[54,-4],[54,-72]],'#173536');
 for(const k of [-42,-20,20,42])line(c,[[k,-65],[k,-4]],col,4);
 for(let i=0;i<3;i++){const top=-77-i*31,w=76-i*17;poly(c,[[-w-13,top-9],[-w+9,top-7],[-5,top-32],[7,top-32],[w-9,top-7],[w+13,top-9],[w-1,top+4],[0,top+17],[-w+1,top+4]],col+'c0');poly(c,[[0,top-29],[w-9,top-7],[w+13,top-9],[w-1,top+4],[0,top+17]],'#365d58');line(c,[[-w-12,top-9],[-w+4,top+1],[0,top+13],[w-4,top+1],[w+12,top-9]],'#a0b59d50',1.2)}
 line(c,[[0,-172],[0,-195]],col,2);circle(c,0,-195,4,col);poly(c,[[-9,-57],[-9,-4],[11,2],[11,-56]],'#102f32');glow(c,0,-33,25,'#e9c07835');c.fillStyle='#e9c078';c.fillRect(-3,-43,5,13);c.restore()}
function platform(c,x,y,s=1,col='#5d8474'){c.save();c.translate(x,y);c.scale(s,s);poly(c,[[-160,0],[0,82],[160,0],[0,-82]],'#213f40');poly(c,[[-160,0],[-160,20],[0,107],[0,82]],'#142d32');poly(c,[[0,82],[0,107],[160,20],[160,0]],'#1b3436');poly(c,[[-154,-1],[0,-78],[154,-1],[0,77]],'#355957',col+'55');for(let i=-2;i<=2;i++){line(c,[[i*38-73,39-i*19],[i*38+73,-39-i*19]],col+'30');line(c,[[i*38-73,-39+i*19],[i*38+73,39+i*19]],col+'30')}ellipse(c,0,0,69,33,null,'#dbc68a66');ellipse(c,0,0,60,28,null,'#dbc68a22');for(let i=0;i<6;i++){const a=i*TAU/6;poly(c,[[Math.cos(a)*67,Math.sin(a)*32],[Math.cos(a)*74,Math.sin(a)*35],[Math.cos(a+.1)*70,Math.sin(a+.1)*33]],'#dbc68a')}
 poly(c,[[-38,65],[-38,83],[0,105],[37,83],[37,65],[0,84]],'#4a655a');line(c,[[-38,77],[0,98],[37,77]],'#b0c2a344');c.restore()}
function landscape(canvas,opt={},time=0){const {c,w,h}=resize(canvas),chapter=opt.chapter||0,ch=GameEngine.chapters[chapter],mini=!!opt.mini;
 const bg=c.createLinearGradient(0,0,0,h);bg.addColorStop(0,ch.sky);bg.addColorStop(.6,ch.floor);bg.addColorStop(1,'#11282b');c.fillStyle=bg;c.fillRect(0,0,w,h);
 const cx=w*(mini?.58:.71),cy=h*.37;
 glow(c,cx,cy,w*.43,ch.color+'25');circle(c,cx,cy,Math.min(w*.18,h*.3),null,ch.color+'18');circle(c,cx,cy,Math.min(w*.17,h*.285),null,ch.color+'30');
 // Eclipse and celestial geometry.
 const rr=Math.min(w*.085,h*.2);glow(c,cx,cy-25,rr*2,'#e9c07825');circle(c,cx,cy-25,rr,'#d7d3a963');circle(c,cx+rr*.24,cy-25-rr*.1,rr*.9,ch.sky);c.save();c.translate(cx,cy-25);c.rotate(time*.016);circle(c,0,0,rr*1.23,null,'#e9c07838');for(let i=0;i<12;i++){const a=i*TAU/12;line(c,[[Math.cos(a)*rr*1.16,Math.sin(a)*rr*1.16],[Math.cos(a)*rr*1.28,Math.sin(a)*rr*1.28]],'#e9c07855')}c.restore();
 for(let j=0;j<3;j++){let pts=[[0,h]];for(let i=0;i<=14;i++){const x=w*i/14,y=h*(.51+j*.105)+Math.sin(i*2.9+j*4)*h*.065;pts.push([x,y])}pts.push([w,h]);poly(c,pts,j===0?ch.color+'12':j===1?'#193d3e88':'#1a3839')}
 c.save();c.globalAlpha=.28;temple(c,w*.87,h*.61,.6*(h/400),ch.color);temple(c,w*.46,h*.58,.4*(h/400),ch.color);c.restore();
 const s=Math.min(w/(mini?470:w<640?520:880),h/400);platform(c,w*.72,h*.73,s*1.0,ch.color);
 // Portal with animated sigils, hand painted light pillars.
 const px=w*.72,py=h*.54,pr=78*s;c.save();c.translate(px,py);glow(c,0,0,pr*1.7,ch.color+'25');c.scale(1,.95);circle(c,0,0,pr,null,ch.color+'a0');circle(c,0,0,pr*.89,null,ch.color+'38');c.rotate(time*.07);for(let i=0;i<8;i++){const a=i*TAU/8,xx=Math.cos(a)*pr,yy=Math.sin(a)*pr;poly(c,[[xx-4*s,yy],[xx,yy-7*s],[xx+4*s,yy],[xx,yy+7*s]],'#e7d19b')};c.restore();
 if(!mini)hero(c,opt.hero||'yao',w*.72,h*.76,s*1.23,time,0,0);
 crystal(c,w*.85,h*.78,s*.7,ch.color,time);crystal(c,w*.58,h*.75,s*.5,ch.color,time);
 tree(c,w*.95,h*.93,s*1.25,chapter===1?'#b9756b':chapter===3?'#a8bcca':'#759785',chapter===2?2:0);tree(c,w*.40,h*1.09,s*1.1,'#4f7d73',chapter===2?2:0);
 // Floating islands and suspended fragments.
 for(let i=0;i<8;i++){const x=w*(.45+(i*.083)% .55),y=h*(.54+(i*.057)%.3)+Math.sin(time*.55+i)*3,sz=(i%3+1)*3;poly(c,[[x,y],[x+sz*3,y-sz],[x+sz*4,y+sz],[x+sz,y+sz*3]],'#53797155')}
 for(let i=0;i<55;i++){const x=(i*79.23+time*(i%3+1)*2)%w,y=(i*41.31+Math.sin(time*.4+i)*9)%h;circle(c,x,y,i%7===0?1.4:.7,i%4===0?'#e9c07888':ch.color+'66')}
 // Mist drifts across the foreground.
 const mist=c.createLinearGradient(0,h*.68,0,h);mist.addColorStop(0,'#9ecabc00');mist.addColorStop(1,'#a3c8ae11');c.fillStyle=mist;c.fillRect(0,h*.68,w,h*.32);
}
function portrait(canvas,id,time=0,skinId=appearance){const{c,w,h}=resize(canvas),a=GameEngine.heroes[id],col=GameEngine.skins[skinId]?.color||a.color;c.fillStyle='#14292d';c.fillRect(0,0,w,h);const s=Math.min(w/130,h/117);glow(c,w*.5,h*.48,h*.65,col+'14');ellipse(c,w*.5,h*.82,w*.32,h*.12,null,col+'25');c.save();c.translate(w*.5,h*.46);circle(c,0,0,Math.min(w*.35,h*.32),null,col+'20');for(let i=0;i<8;i++){const ang=i*TAU/8+time*.04;circle(c,Math.cos(ang)*w*.3,Math.sin(ang)*h*.3,1,col+'66')}c.restore();hero(c,id,w*.53,h*.94,s,time,0,0,false,skinId);}
function enemy(c,e,x,y,s,t,ch){c.save();c.translate(x,y);c.scale(s,s);ellipse(c,0,0,e.radius,8,'#03171a70');const col=e.flash>0?'#f8dfbb':e.type==='duelist'?GameEngine.heroes[e.hero||'ying']?.color:ch.color;const red=e.flash>0?'#fff8dc':'#e79b91';
 if(e.type==='duelist'){hero(c,e.hero||'ying',0,0,1.2,t,e.dir,0,false,'original');c.restore();return}
 if(e.type==='boss'){c.translate(0,Math.sin(t*2)*2);poly(c,[[-26,-70],[-54,-54],[-77,-88],[-61,-17],[-27,-28]],'#3b5655');poly(c,[[24,-73],[57,-54],[78,-91],[61,-16],[25,-28]],'#334a50');line(c,[[-74,-83],[-62,-33],[-35,-46]],ch.color+'b0',2);line(c,[[76,-87],[62,-32],[34,-47]],ch.color+'b0',2);poly(c,[[-24,-75],[-32,-26],[-15,-21],[-12,-5],[-34,0],[-33,6],[-6,6],[0,-24],[7,4],[33,5],[34,0],[16,-8],[17,-23],[32,-29],[24,-75]],e.flash>0?'#b5b1a2':'#253d43');poly(c,[[-20,-70],[0,-86],[22,-70],[13,-38],[0,-27],[-15,-40]],ch.color+'aa');poly(c,[[0,-85],[22,-70],[13,-38],[0,-27],[3,-54]],'#354952');poly(c,[[-12,-93],[-17,-115],[-5,-108],[0,-126],[8,-108],[21,-117],[15,-93],[7,-88],[-6,-88]],ch.color);poly(c,[[-13,-93],[-11,-83],[0,-76],[13,-85],[16,-94]],'#1c3037');line(c,[[-8,-89],[0,-87],[9,-90]],red,3);glow(c,0,-51,38,'#e9c07833');circle(c,0,-51,5,'#f1d491');line(c,[[-42,-53],[-50,1]],ch.color,5);poly(c,[[-50,-111],[-61,-65],[-50,-48],[-42,-69]],ch.color);if(e.phase===2){glow(c,0,-67,90,'#f3946220');line(c,[[-20,-102],[-33,-123],[-28,-138]],red,1.4)}}
 else if(e.type==='golem'){poly(c,[[-15,-46],[-30,-36],[-28,-14],[-17,-10],[-12,0],[0,-3],[10,0],[21,-9],[29,-15],[31,-34],[15,-44]],e.flash>0?'#cab9a0':'#677771');poly(c,[[-12,-49],[2,-61],[17,-48],[12,-34],[-12,-34]],e.flash>0?'#f8dfbb':'#889286');poly(c,[[1,-60],[17,-48],[12,-34],[0,-38]],'#455c58');line(c,[[-8,-47],[8,-47]],red,3);poly(c,[[-7,-31],[-9,-15],[2,-9],[10,-21],[7,-32]],ch.color+'a0')}
 else if(e.type==='wolf'){const bob=Math.sin(t*8+e.id)*2;c.translate(0,bob);poly(c,[[-26,-22],[-17,-36],[0,-30],[17,-41],[27,-23],[13,-8],[-15,-7]],e.flash>0?'#dcd2b6':'#597676');poly(c,[[0,-33],[13,-48],[28,-42],[37,-27],[22,-24],[18,-17]],'#7b9390');poly(c,[[12,-42],[12,-55],[21,-42]],ch.color);line(c,[[23,-34],[29,-35]],red,2);line(c,[[-15,-7],[-23,0]],'#8eaba0',4);line(c,[[13,-7],[20,0]],'#8eaba0',4);line(c,[[-26,-22],[-43,-34]],ch.color,3)}
 else{const bob=Math.sin(t*3+e.id)*3;c.translate(0,bob);poly(c,[[-8,-43],[-18,-22],[-25,-4],[-8,-12],[0,-4],[10,-12],[23,-2],[17,-27],[9,-43]],e.flash>0?'#c6c6b5':'#385b60');poly(c,[[-6,-43],[-5,-21],[0,-12],[7,-21],[8,-43]],ch.color+'60');poly(c,[[-11,-46],[-8,-61],[1,-65],[11,-57],[12,-45],[1,-39]],'#273e47');line(c,[[-5,-50],[5,-50]],red,2);if(e.type==='archer'){line(c,[[18,-45],[28,-14]],red,2);c.beginPath();c.moveTo(16,-45);c.quadraticCurveTo(37,-32,28,-14);c.strokeStyle=ch.color;c.lineWidth=2;c.stroke()}else{line(c,[[-10,-54],[-17,-64]],ch.color,2);line(c,[[9,-56],[15,-66]],ch.color,2)}glow(c,0,-35,27,ch.color+'13')}
 if(e.stun>0){circle(c,0,-80,10,null,'#e9c07899');circle(c,Math.sin(t*10)*10,-80,2,'#e9c078')}
 c.restore();
}
function battle(canvas,r,vis,time,settings){const{c,w,h}=resize(canvas,settings.quality==='low'?.7:1),ch=GameEngine.chapters[r.chapter],cam=vis.camera;
 const targetScale=Math.min(1.2,Math.max(.6,Math.min(w/1050,h/690)));cam.scale=targetScale;
 cam.x+=(r.p.x-cam.x)*.11;cam.y+=(r.p.y-cam.y)*.11;
 const sx=settings.reduce?0:(Math.random()-.5)*r.shake,sy=settings.reduce?0:(Math.random()-.5)*r.shake;
 const project=(x,y)=>[w/2+(x-cam.x)*targetScale+sx,h*.52+(y-cam.y)*targetScale*.64+sy];vis.project=project;vis.w=w;vis.h=h;
 const bg=c.createLinearGradient(0,0,0,h);bg.addColorStop(0,ch.sky);bg.addColorStop(1,'#081b21');c.fillStyle=bg;c.fillRect(0,0,w,h);
 for(let i=0;i<35;i++){const x=(i*171.81-cam.x*.13+Math.sin(time*.12+i)*15+w*10)%w,y=(i*63.17-cam.y*.09+h*10)%h;circle(c,x,y,.7,ch.color+'44')}
 const bounds=r.bounds,lt=project(-bounds,-bounds),rt=project(bounds,-bounds),rb=project(bounds,bounds),lb=project(-bounds,bounds);
 poly(c,[lt,rt,rb,lb],ch.floor+'bd');poly(c,[lb,rb,[rb[0],rb[1]+35],[lb[0],lb[1]+35]],'#122b32');
 c.lineWidth=1;for(let x=-Math.floor(bounds/90)*90;x<=bounds;x+=90){line(c,[project(x,-bounds),project(x,bounds)],'#c1d9bc0c');line(c,[project(-bounds,x),project(bounds,x)],'#c1d9bc0c')}
 poly(c,[lt,rt,rb,lb],null,ch.color+'32');
 // Inner ceremonial pattern and cracked gold inlays.
 const center=project(0,0);ellipse(c,...center,330*targetScale,210*targetScale,null,ch.color+'20');ellipse(c,...center,310*targetScale,198*targetScale,null,'#e3d5a414');
 for(let i=0;i<8;i++){const a=i*TAU/8;const pos=project(Math.cos(a)*324,Math.sin(a)*324);c.save();c.translate(...pos);c.rotate(a);poly(c,[[-6,0],[0,-8],[6,0],[0,8]],'#e8cf8c55');c.restore()}
 if(r.mode==='world')for(const sh of r.shrines){const p=project(sh.x,sh.y);ellipse(c,...p,80*targetScale,45*targetScale,sh.active?'#e4d69114':'#8cc8bd10',sh.active?'#e4d69188':'#8cc8bd35');if(sh.active)glow(c,p[0],p[1]-50*targetScale,90*targetScale,'#e9c07820')}
 for(const z of r.zones){const p=project(z.x,z.y),col=z.enemy?'#f18c72':z.type==='ice'?'#a8ddec':z.type==='fire'?'#ed956e':'#a5d7bb';ellipse(c,...p,z.radius*targetScale,z.radius*targetScale*.64,col+'25',col+'66');for(let i=0;i<5;i++){const a=time*2+i*TAU/5;const v=project(z.x+Math.cos(a)*z.radius*.7,z.y+Math.sin(a)*z.radius*.7);circle(c,...v,3,col+'88')}}
 const locked=GameEngine.nearest(r,r.p.range+90);if(locked){const v=project(locked.x,locked.y);ellipse(c,...v,(locked.radius+8)*targetScale,(locked.radius+8)*targetScale*.64,null,'#ebd19a88');poly(c,[[v[0],v[1]-95*targetScale],[v[0]-4,v[1]-102*targetScale],[v[0]+4,v[1]-102*targetScale]],'#e9d093')}
 for(const a of r.warnings){const p=project(a.x,a.y),f=1-a.time/a.maxTime;c.lineWidth=1.5;
  if(a.type==='line'){const dx=Math.cos(a.dir),dy=Math.sin(a.dir),nx=-dy*a.radius,ny=dx*a.radius;poly(c,[project(a.x+nx,a.y+ny),project(a.x-nx,a.y-ny),project(a.x+dx*a.length-nx,a.y+dy*a.length-ny),project(a.x+dx*a.length+nx,a.y+dy*a.length+ny)],'#ef7e7022','#ef9b8aaa');poly(c,[project(a.x+nx,a.y+ny),project(a.x-nx,a.y-ny),project(a.x+dx*a.length*f-nx,a.y+dy*a.length*f-ny),project(a.x+dx*a.length*f+nx,a.y+dy*a.length*f+ny)],'#ef7e7044')}
  else{ellipse(c,...p,a.radius*targetScale,a.radius*targetScale*.64,'#eb77621a','#ef9987bb');ellipse(c,...p,a.radius*targetScale*f,a.radius*targetScale*.64*f,'#ed846044');const ring=project(a.x,a.y);line(c,[[ring[0]-5,ring[1]],[ring[0]+5,ring[1]]],'#ffc0a7',1.5)}
 }
 for(const d of r.drops){const p=project(d.x,d.y);glow(c,p[0],p[1]-7,15,d.type==='heal'?'#9ee0b633':'#e9c07828');poly(c,[[p[0],p[1]-12],[p[0]+4,p[1]-7],[p[0],p[1]-1],[p[0]-4,p[1]-7]],d.type==='heal'?'#a4dbb1':'#dfcb8e')}
 // Depth sort allows moving behind tall ruins and trees.
 const entities=[...r.props.map(p=>({...p,draw:'prop'})),...r.enemies.map(e=>({...e,draw:'enemy'})),{...r.p,draw:'hero'}];
 if(r.mode==='world'){for(const s of r.shrines)entities.push({...s,draw:'shrine'});for(const s of r.chests)entities.push({...s,draw:'chest'})}
 entities.sort((a,b)=>a.y-b.y);
 for(const e of entities){const p=project(e.x,e.y);if(p[0]<-200||p[0]>w+200||p[1]<-50||p[1]>h+250)continue;
  if(e.draw==='hero'){if(e.shield>0){ellipse(c,p[0],p[1]-36*targetScale,32*targetScale,51*targetScale,'#e9d59908','#e9d59955')}if(e.invuln>.35)glow(c,p[0],p[1]-40*targetScale,80*targetScale,GameEngine.heroes[r.hero].color+'25');hero(c,r.hero,...p,targetScale,time,r.p.dir,r.p.anim);if(r.p.orbits)for(let i=0;i<r.p.orbits;i++){const a=r.time*2.8+i*TAU/r.p.orbits,v=project(e.x+Math.cos(a)*105,e.y+Math.sin(a)*105);glow(c,v[0],v[1]-12,17,'#e9c07855');poly(c,[[v[0],v[1]-24],[v[0]+4,v[1]-12],[v[0],v[1]],[v[0]-4,v[1]-12]],'#f3deae')}}
  else if(e.draw==='enemy'){enemy(c,{...e,hero:r.opponent},...p,targetScale,time,ch);if(e.hp<e.maxHp&&e.type!=='boss'&&e.type!=='duelist'){c.fillStyle='#102527';c.fillRect(p[0]-19*targetScale,p[1]-78*targetScale,38*targetScale,3);c.fillStyle='#d68d83';c.fillRect(p[0]-19*targetScale,p[1]-78*targetScale,38*targetScale*e.hp/e.maxHp,3)}}
  else if(e.draw==='prop'){if(e.type==='temple')temple(c,...p,targetScale*e.size*.8,ch.color);else if(e.type==='tree')tree(c,...p,targetScale*e.size,ch.color,r.chapter===2?2:0);else crystal(c,...p,targetScale*e.size,ch.color,time+e.seed)}
  else if(e.draw==='shrine'){platform(c,...p,targetScale*.36);crystal(c,p[0],p[1]-10*targetScale,targetScale*.9,e.active?'#ead6a2':'#84b7b4',time);if(!e.active){c.fillStyle='#b0c7bd';c.font='10px Microsoft YaHei';c.textAlign='center';c.fillText('失落祭坛',p[0],p[1]-93*targetScale)}}
  else if(e.draw==='chest'){poly(c,[[p[0]-15,p[1]-17],[p[0]+11,p[1]-22],[p[0]+18,p[1]-14],[p[0]+18,p[1]-1],[p[0]-12,p[1]+4],[p[0]-15,p[1]-3]],e.open?'#546a59':'#ae9566','#dbbc8155');line(c,[[p[0]-14,p[1]-10],[p[0]+17,p[1]-14]],'#ead3a977',2);if(!e.open)glow(c,p[0],p[1]-10,28,'#e9c07825')}
 }
 for(const b of r.projectiles){const p=project(b.x,b.y),tail=project(b.x-b.dx*25,b.y-b.dy*25);line(c,[[tail[0],tail[1]-25*targetScale],[p[0],p[1]-25*targetScale]],b.color+'b0',b.radius*targetScale*.7);glow(c,p[0],p[1]-25*targetScale,b.radius*2,b.color+'45');circle(c,p[0],p[1]-25*targetScale,b.radius*targetScale*.7,b.enemy?'#ee9b86':'#fff1c9')}
 for(const f of vis.fx){const p=project(f.x,f.y),q=f.t/f.life;c.save();c.globalAlpha=Math.max(0,1-q);
  if(f.type==='text'){c.fillStyle=f.color;c.font=`${f.crit?22:14}px ${f.crit?'SimSun':'Microsoft YaHei'}`;c.textAlign='center';c.fillText(f.text,p[0]+f.dx*f.t,p[1]-60*targetScale-f.t*43)}
  if(f.type==='particle'){circle(c,p[0]+f.dx*f.t,p[1]-f.z-f.dy*f.t,Math.max(.5,f.size*(1-q)),f.color)}
  if(['ring','ultimate','nova','enemyImpact'].includes(f.type)){const rad=f.radius*targetScale*(.3+q*.85);ellipse(c,...p,rad,rad*.64,null,f.color);c.lineWidth=f.type==='ultimate'?4:2;ellipse(c,...p,rad*.84,rad*.54,f.type==='ultimate'?f.color+'15':null,f.color+'55');if(f.type==='ultimate'){glow(c,p[0],p[1],rad,f.color+'25');for(let i=0;i<7;i++){const a=i*TAU/7;line(c,[p,[p[0]+Math.cos(a)*rad,p[1]+Math.sin(a)*rad*.64]],f.color+'66',1)}}}
  if(f.type==='slash'){c.save();c.translate(...p);c.scale(1,.64);c.rotate(f.dir);c.beginPath();c.arc(0,0,f.radius*targetScale*(.7+q*.3),-1.3+q,1.1+q);c.strokeStyle=f.color;c.lineWidth=(1-q)*(f.heavy?16:8);c.stroke();c.beginPath();c.arc(0,0,f.radius*targetScale*.83,-1.3+q,1.1+q);c.strokeStyle='#fff5d7';c.lineWidth=2;c.stroke();c.restore()}
  if(f.type==='lightning'){const v=project(f.tx,f.ty);const pts=[];for(let i=0;i<=6;i++)pts.push([p[0]+(v[0]-p[0])*i/6+(i>0&&i<6?(i%2?12:-12):0),p[1]+(v[1]-p[1])*i/6-32]);line(c,pts,'#d4d9ff',2.5);line(c,pts,'#969dfd66',6)}
  if(f.type==='trail')hero(c,r.hero,...p,targetScale,time,0,0,true);
  c.restore();
 }
 const vignette=c.createRadialGradient(w*.5,h*.5,h*.22,w*.5,h*.5,Math.max(w,h)*.65);vignette.addColorStop(0,'#03111600');vignette.addColorStop(1,'#03111699');c.fillStyle=vignette;c.fillRect(0,0,w,h);
 if(r.flash>0){c.fillStyle='#ce5b4844';c.fillRect(0,0,w,h)}
}
function minimap(canvas,r){const c=canvas.getContext('2d'),w=canvas.width,h=canvas.height,k=Math.min(w,h)/(r.bounds*2.4);c.fillStyle='#102529';c.fillRect(0,0,w,h);c.strokeStyle='#73938f30';c.strokeRect(w/2-r.bounds*k,h/2-r.bounds*k,r.bounds*k*2,r.bounds*k*2);const p=(x,y)=>[w/2+x*k,h/2+y*k];for(const s of r.shrines){const a=p(s.x,s.y);poly(c,[[a[0],a[1]-4],[a[0]+4,a[1]],[a[0],a[1]+4],[a[0]-4,a[1]]],s.active?'#e7c890':'#6fa9a0')}for(const ch of r.chests)if(!ch.open){const a=p(ch.x,ch.y);c.fillStyle='#dcb778';c.fillRect(a[0]-2,a[1]-2,3,3)}for(const e of r.enemies)circle(c,...p(e.x,e.y),e.type==='boss'||e.type==='duelist'?3:1.6,'#e99680');circle(c,...p(r.p.x,r.p.y),3,'#c9e8bf');}
return{resize,landscape,portrait,battle,minimap,hero,setAppearance:id=>{appearance=GameEngine.skins[id]?id:'original'}};
})();
