import { getStaff } from "@/lib/auth";
import { getInquiries } from "@/lib/data/admin";
import { setInquiryStatus } from "@/lib/actions/admin";
import { Badge, Empty, Panel, PageTitle } from "@/components/admin/ui";
import { StatusSelect } from "@/components/admin/controls";

const statuses = [
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "quoted", label: "Quote sent" },
  { value: "converted", label: "Converted to order" },
  { value: "closed", label: "Closed" },
] as const;

export default async function InquiriesPage() {
  await getStaff();
  const inquiries = await getInquiries();
  return (
    <>
      <PageTitle title="Inquiries" sub="Bridal consultations, bulk orders and questions from the website." />
      <Panel>
        {inquiries.length === 0 ? (
          <Empty>No inquiries yet.</Empty>
        ) : (
          <ul className="divide-y divide-line">
            {inquiries.map((i) => (
              <li key={i.id} className="grid gap-3 py-4 md:grid-cols-[1fr_auto] md:items-center">
                <div className="text-sm">
                  <p className="font-semibold">
                    {i.name} <Badge value={i.type} />
                  </p>
                  <p className="mt-1 text-muted">{i.message}</p>
                  <p className="mt-1 text-xs text-muted">
                    <a href={`https://wa.me/${i.phone.replace(/\D/g, "")}`} target="_blank" rel="noopener noreferrer" className="text-plum underline">
                      {i.phone}
                    </a>{" "}
                    · {new Date(i.created_at).toLocaleString("en-PK")}
                  </p>
                </div>
                <div className="w-48">
                  <StatusSelect value={i.status} options={statuses} onChange={setInquiryStatus.bind(null, i.id)} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}
