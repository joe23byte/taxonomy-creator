import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@fontsource-variable/inter";
import "./index.css";
import App from "./App";
import { LiveProvider } from "./lib/live";
import { I18nProvider } from "./lib/i18n";
import { TooltipProvider } from "./components/ui/primitives";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, staleTime: 1500, retry: 1 } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <LiveProvider>
          <TooltipProvider>
            <App />
          </TooltipProvider>
        </LiveProvider>
      </I18nProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
