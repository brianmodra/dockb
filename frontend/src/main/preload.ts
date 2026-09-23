import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("dockb", {
  platform: process.platform,
});