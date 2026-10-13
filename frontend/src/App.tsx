import { useState } from "react";
import { RouterProvider, type DataRouter } from "react-router-dom";
import { createAppRouter } from "./routes";

export default function App({ router: injected }: { router?: DataRouter }) {
  const [router] = useState(() => injected ?? createAppRouter());
  return <RouterProvider router={router} />;
}
