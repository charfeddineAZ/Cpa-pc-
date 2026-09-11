import { app, BrowserWindow, ipcMain } from 'electron';
import { spawn } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
let api;
function createWindow(){ const win = new BrowserWindow({width:1440,height:900,minWidth:1100,minHeight:700,backgroundColor:'#080d1a',title:'CPA Control Center',webPreferences:{preload:path.join(__dirname,'preload.cjs'),contextIsolation:true,nodeIntegration:false}}); const url=process.env.VITE_DEV_SERVER_URL||'http://localhost:5173'; win.loadURL(url); }
app.whenReady().then(()=>{ if(!process.env.VITE_DEV_SERVER_URL){ api=spawn(process.platform==='win32'?'python':'python3',[path.join(__dirname,'..','backend','main.py')],{stdio:'inherit'}); } createWindow(); app.on('activate',()=>BrowserWindow.getAllWindows().length===0&&createWindow()); });
app.on('window-all-closed',()=>{if(api) api.kill(); if(process.platform!=='darwin')app.quit();});
