import { contextBridge, ipcRenderer, webUtils } from "electron";

contextBridge.exposeInMainWorld("dockb", {
  platform: process.platform,
  isElectron: true,
  openExternal: (url: string) => ipcRenderer.invoke("open-external", url),
  quit: () => ipcRenderer.send("quit"),
  getPathForFile: (file: File) => webUtils.getPathForFile(file),
  chooseCacheDirectory: () => ipcRenderer.invoke("cache-choose-directory"),
  setCacheRoot: (directory: string) => ipcRenderer.invoke("cache-set-root", directory),
  cacheRead: (relativePath: string) => ipcRenderer.invoke("cache-read", relativePath),
  cacheWrite: (relativePath: string, content: string) =>
    ipcRenderer.invoke("cache-write", relativePath, content),
  cacheDelete: (relativePath: string) => ipcRenderer.invoke("cache-delete", relativePath),
  cacheRename: (from: string, to: string) => ipcRenderer.invoke("cache-rename", from, to),
  cacheMoveDirectory: (from: string, to: string) =>
    ipcRenderer.invoke("cache-move-directory", from, to),
  cacheList: () => ipcRenderer.invoke("cache-list"),
});
