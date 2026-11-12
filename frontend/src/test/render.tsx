import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import "../i18n";

function Where() {
  const loc = useLocation();
  return <output data-testid="where">{loc.pathname + loc.search}</output>;
}

export function renderRoutes(routes: Record<string, ReactElement>, initial: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    client,
    ...render(
      <MantineProvider>
        <QueryClientProvider client={client}>
          <MemoryRouter initialEntries={[initial]}>
            <Where />
            <Routes>
              {Object.entries(routes).map(([path, el]) => (
                <Route key={path} path={path} element={el} />
              ))}
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </MantineProvider>,
    ),
  };
}
