const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('desktop', {
	isElectron: true,
	platform: process.platform,
	openBrowser: url => ipcRenderer.invoke('open-secure-browser', url),
});
