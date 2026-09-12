import { app, BrowserWindow, ipcMain, session } from 'electron';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
let api;
let secureBrowser;
function createWindow(){ const win = new BrowserWindow({width:1440,height:900,minWidth:1100,minHeight:700,backgroundColor:'#080d1a',title:'CPA Control Center',webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false,sandbox:true}}); const url=process.env.VITE_DEV_SERVER_URL||'http://localhost:5173'; win.loadURL(url); }
async function waitForApi(){ for(let attempt=0;attempt<30;attempt++){ try{ const response=await fetch('http://127.0.0.1:8765/api/health'); if(response.ok)return true; }catch{} await new Promise(resolve=>setTimeout(resolve,100)); } return false; }
function validUrl(value){ try { const url=new URL(value); return ['http:','https:'].includes(url.protocol) ? url.toString() : null; } catch { return null; } }
ipcMain.handle('open-secure-browser', async (_event, value) => {
	const url=validUrl(value);
	if(!url) throw new Error('يجب إدخال رابط HTTP أو HTTPS صالح');
	if(secureBrowser && !secureBrowser.isDestroyed()){ secureBrowser.loadURL(url); secureBrowser.focus(); return {opened:true}; }
	const partition=`persist:cpa-secure-${Date.now()}`;
	const browserSession=session.fromPartition(partition);
	browserSession.setPermissionRequestHandler((_webContents,_permission,callback)=>callback(false));
	secureBrowser=new BrowserWindow({width:1280,height:800,title:'CPA Secure Browser',webPreferences:{partition,contextIsolation:true,nodeIntegration:false,sandbox:true,webSecurity:true}});
	secureBrowser.webContents.setWindowOpenHandler(({url:target})=>({action:validUrl(target)?'allow':'deny'}));
	secureBrowser.webContents.on('will-navigate',(event,target)=>{if(!validUrl(target))event.preventDefault();});
	secureBrowser.on('closed',()=>{secureBrowser=null;});
	await secureBrowser.loadURL(url);
	return {opened:true};
});
app.whenReady().then(async()=>{ if(!process.env.VITE_DEV_SERVER_URL){ api=spawn(process.platform==='win32'?'python':'python3',[path.join(__dirname,'..','backend','main.py')],{stdio:'inherit',env:{...process.env,CPA_DB_PATH:path.join(app.getPath('userData'),'cpa.sqlite3')}}); await waitForApi(); } createWindow(); app.on('activate',()=>BrowserWindow.getAllWindows().length===0&&createWindow()); });
app.on('window-all-closed',()=>{if(api) api.kill(); if(process.platform!=='darwin')app.quit();});
