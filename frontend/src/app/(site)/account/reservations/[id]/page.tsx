import { ReservationView } from "./reservation-view";

export default async function ReservationPage({ params }: PageProps<"/account/reservations/[id]">) {
  const { id } = await params;
  return <ReservationView id={Number(id)} />;
}
