import { getStaff } from "@/lib/auth";
import { getGalleryAdmin, getReviews } from "@/lib/data/admin";
import { featureReview, moderateReview, removeGalleryItem, replyToReview, setGalleryFeatured } from "@/lib/actions/admin";
import { Badge, Empty, Panel, PageTitle } from "@/components/admin/ui";
import { ActionButton, ActionForm } from "@/components/admin/controls";
import { Stars } from "@/components/site/sections";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";

export default async function ReviewsAdminPage() {
  await getStaff();
  const [reviews, gallery] = await Promise.all([getReviews(), getGalleryAdmin()]);
  const pending = reviews.filter((r) => r.status === "pending");
  const others = reviews.filter((r) => r.status !== "pending");

  const ReviewItem = ({ r }: { r: (typeof reviews)[number] }) => (
    <li className="space-y-3 py-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Stars value={r.rating} />
          <span className="text-sm font-semibold">{r.customer_name}</span>
          <span className="text-xs text-muted">
            {r.area} · {r.order?.order_no} · {new Date(r.created_at).toLocaleDateString("en-PK")}
          </span>
        </div>
        <span className="flex items-center gap-2">
          <Badge value={r.status} />
          {r.featured && <Badge value="featured" />}
        </span>
      </div>
      <p className="text-xs text-muted">
        Fit {r.fit ?? "–"}/5 · Finishing {r.finishing ?? "–"}/5 · On time {r.on_time ?? "–"}/5
      </p>
      <p className="text-sm">{r.body}</p>
      {r.media.length > 0 && (
        <div className="flex gap-2">
          {r.media.map((m) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img key={m} src={m} alt="Customer photo" className="size-20 rounded-[var(--radius-md)] object-cover" />
          ))}
        </div>
      )}
      <ActionForm action={replyToReview} success="Reply saved" className="flex gap-2">
        <input type="hidden" name="id" value={r.id} />
        <Input name="reply" defaultValue={r.reply ?? ""} placeholder="Public reply from Laraib (optional)" className="h-10" />
        <Button type="submit" size="sm" variant="outline">Reply</Button>
      </ActionForm>
      <div className="flex flex-wrap gap-2">
        {r.status !== "published" && (
          <ActionButton action={moderateReview.bind(null, r.id, "published")} success="Review published">Publish</ActionButton>
        )}
        {r.status !== "hidden" && (
          <ActionButton action={moderateReview.bind(null, r.id, "hidden")} success="Review hidden" variant="outline">Hide</ActionButton>
        )}
        <ActionButton action={featureReview.bind(null, r.id, !r.featured)} success={r.featured ? "Unfeatured" : "Featured on home page"} variant="ghost">
          {r.featured ? "Unfeature" : "Feature"}
        </ActionButton>
      </div>
    </li>
  );

  return (
    <>
      <PageTitle title="Reviews & gallery" sub="Publish honest reviews — including critical ones, with a reply. Gallery photos are added from each order's page." />
      <div className="grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          <Panel title={`Waiting for moderation (${pending.length})`}>
            {pending.length === 0 ? <Empty>No new reviews.</Empty> : <ul className="divide-y divide-line">{pending.map((r) => <ReviewItem key={r.id} r={r} />)}</ul>}
          </Panel>
          <Panel title="All reviews">
            {others.length === 0 ? <Empty>Nothing yet.</Empty> : <ul className="divide-y divide-line">{others.map((r) => <ReviewItem key={r.id} r={r} />)}</ul>}
          </Panel>
        </div>
        <Panel title={`Stitched by Laraib (${gallery.filter((g) => g.consent_verified).length} live)`}>
          {gallery.length === 0 ? (
            <Empty>No gallery photos yet. Open an order and use “Finished suit photo”.</Empty>
          ) : (
            <ul className="grid grid-cols-2 gap-3">
              {gallery.map((g) => (
                <li key={g.id} className={g.consent_verified ? "" : "opacity-40"}>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={g.image_url} alt={g.title} className="aspect-[3/4] w-full rounded-[var(--radius-md)] object-cover" />
                  <p className="mt-1 truncate text-xs font-medium">{g.title}</p>
                  <p className="text-[0.7rem] text-muted">{g.order?.order_no}</p>
                  {g.consent_verified && (
                    <div className="mt-1 flex gap-1">
                      <ActionButton action={setGalleryFeatured.bind(null, g.id, !g.featured)} success="Updated" variant="ghost" className="h-7 px-2 text-xs">
                        {g.featured ? "★ Featured" : "☆ Feature"}
                      </ActionButton>
                      <ActionButton action={removeGalleryItem.bind(null, g.id)} success="Removed from gallery" variant="ghost" confirm="Remove this photo from the public gallery?" className="h-7 px-2 text-xs text-danger">
                        Remove
                      </ActionButton>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}
