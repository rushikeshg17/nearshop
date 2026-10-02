import type { Metadata } from "next";

import { AiLabView } from "./ai-lab-view";

export const metadata: Metadata = { title: "AI Lab", description: "How NearShop uses machine learning, with live metrics." };

export default function AiLabPage() {
  return <AiLabView />;
}
