import "./styles.css";
import { mountShell } from "./main";

const root = document.getElementById("app");
if (root) {
  mountShell(root);
}