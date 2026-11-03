import { getStaff } from "@/lib/auth";
import { getOrders } from "@/lib/data/admin";
import { PageTitle } from "@/components/admin/ui";
import { OrderBoard } from "@/components/admin/order-board";

export default async function OrdersPage() {
  await getStaff();
  const orders = await getOrders();
  return (
    <>
      <PageTitle title="Orders" sub="Change a status to move the order — every change is logged in the order timeline." />
      <OrderBoard orders={orders} />
    </>
  );
}
