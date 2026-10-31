const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const root=__dirname;
let html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const css=fs.readFileSync(path.join(root,'style.css'),'utf8');
html=html.replace('<link rel="stylesheet" href="style.css">',`<style>\n${css}\n</style>`);
for(const name of ['engine.js','render.js','game.js']){
 const code=fs.readFileSync(path.join(root,name),'utf8');
 new vm.Script(code,{filename:name});
 html=html.replace(`<script src="${name}"></script>`,`<script>\n${code.replace(/<\/script/gi,'<\\/script')}\n</script>`);
}
if(/<(script|link)[^>]+(?:src|href)="(?:https?:|[^#])/i.test(html))throw Error('External dependency found in release');
if(!html.includes('万象赴新生')||!html.includes('GameEngine'))throw Error('Release is incomplete');
const out=path.join(root,'智阳神传·天启.html');
fs.writeFileSync(out,html,'utf8');
console.log(`Built ${out} (${Buffer.byteLength(html)} bytes). Fully self-contained.`);
