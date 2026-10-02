import { ProductView } from "./product-view";

export default async function ProductPage({ params }: PageProps<"/product/[id]">) {
  const { id } = await params;
  return <ProductView id={Number(id)} />;
}
