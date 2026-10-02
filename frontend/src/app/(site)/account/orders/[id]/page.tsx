import { OrderView } from "./order-view";

export default async function OrderPage({ params }: PageProps<"/account/orders/[id]">) {
  const { id } = await params;
  return <OrderView id={Number(id)} />;
}
