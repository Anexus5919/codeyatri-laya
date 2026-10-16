import { createRoot } from "react-dom/client";
import "./styles/tokens.css";
import "./styles/app.css";
import { App } from "./App";
import { startFeed } from "./lib/feed";
import { registerFonts } from "./lib/fonts";
import { initRoute } from "./lib/route";

void registerFonts();
initRoute();
startFeed();

const root = document.getElementById("root");
if (root) createRoot(root).render(<App />);
