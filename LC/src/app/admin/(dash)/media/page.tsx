import { getStaff } from "@/lib/auth";
import { getSiteMediaAdmin } from "@/lib/data/admin";
import { removeSiteMedia, saveSiteMedia } from "@/lib/actions/admin";
import { mediaSlots } from "@/lib/media";
import { Panel, PageTitle } from "@/components/admin/ui";
import { ActionButton, ActionForm } from "@/components/admin/controls";
import { MediaImage } from "@/components/brand/media-image";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/field";

export default async function SiteMediaPage() {
  await getStaff();
  const media = await getSiteMediaAdmin();
  const groups = [...new Set(mediaSlots.map((s) => s.group))];
  const filled = mediaSlots.filter((s) => media[s.key]).length;

  return (
    <>
      <PageTitle
        title="Site media"
        sub={`Photos on the public website — ${filled} of ${mediaSlots.length} slots filled. Use real photos: well-lit, no faces unless the model agreed, at least 1600px wide.`}
      />
      <div className="space-y-6">
        {groups.map((g) => (
          <Panel key={g} title={g}>
            <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-3">
              {mediaSlots
                .filter((s) => s.group === g)
                .map((slot) => {
                  const current = media[slot.key];
                  return (
                    <div key={slot.key} className="space-y-3">
                      <div className="overflow-hidden rounded-[var(--radius-md)] border border-line" style={{ aspectRatio: slot.ratio }}>
                        <MediaImage src={current?.url} alt={current?.alt ?? slot.label} sizes="400px" />
                      </div>
                      <div>
                        <p className="text-sm font-semibold">{slot.label}</p>
                        <p className="text-xs text-muted">
                          Ratio {slot.ratio.replace("/", ":")} {slot.hint && `· ${slot.hint}`}
                        </p>
                      </div>
                      <ActionForm action={saveSiteMedia} success="Photo saved — live on the site" className="space-y-2">
                        <input type="hidden" name="key" value={slot.key} />
                        <input name="photo" type="file" accept="image/*" className="block w-full text-xs text-muted file:mr-3 file:rounded-full file:border-0 file:bg-cream file:px-3 file:py-1.5 file:text-plum" />
                        <Input name="alt" defaultValue={current?.alt ?? ""} placeholder="Describe the photo (for Google & screen readers)" className="h-10 text-sm" />
                        <div className="flex gap-2">
                          <Button type="submit" size="sm">{current ? "Replace" : "Upload"}</Button>
                          {current && (
                            <ActionButton action={removeSiteMedia.bind(null, slot.key)} success="Photo removed" variant="ghost" confirm="Remove this photo from the website?">
                              Remove
                            </ActionButton>
                          )}
                        </div>
                      </ActionForm>
                    </div>
                  );
                })}
            </div>
          </Panel>
        ))}
      </div>
    </>
  );
}
