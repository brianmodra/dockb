import { contextBridge, ipcRenderer, webUtils } from "electron";

contextBridge.exposeInMainWorld("dockb", {
  platform: process.platform,
  openExternal: (url: string) => ipcRenderer.invoke("open-external", url),
  quit: () => ipcRenderer.send("quit"),
  getPathForFile: (file: File) => webUtils.getPathForFile(file),
});
