import { getStaff } from "@/lib/auth";
import { getDesignsAdmin, type AdminDesign } from "@/lib/data/admin";
import { saveDesign, setDesignActive } from "@/lib/actions/admin";
import { Badge, Empty, Panel, PageTitle } from "@/components/admin/ui";
import { ActionButton, ActionForm } from "@/components/admin/controls";
import { MediaImage } from "@/components/brand/media-image";
import { Button } from "@/components/ui/button";
import { Input, Label, Select, Textarea } from "@/components/ui/field";
import { designOptions, garments } from "@/lib/config";
import { rs } from "@/lib/utils";

const occasions = ["everyday", "eid", "party", "formal", "bridal"];

function DesignForm({ design }: { design?: AdminDesign }) {
  return (
    <ActionForm action={saveDesign} success="Design saved" className="space-y-4">
      <input type="hidden" name="id" value={design?.id ?? ""} />
      <div>
        <Label>Title</Label>
        <Input name="title" defaultValue={design?.title} required placeholder="e.g. Chiffon party wear with lining" />
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <Label>Garment</Label>
          <Select name="garment" defaultValue={design?.garment?.slug ?? "designer"}>
            {garments.map((g) => (
              <option key={g.slug} value={g.slug}>{g.name}</option>
            ))}
          </Select>
        </div>
        <div>
          <Label>Occasion</Label>
          <Select name="occasion" defaultValue={design?.occasion ?? "everyday"}>
            {occasions.map((o) => (
              <option key={o} value={o} className="capitalize">{o}</option>
            ))}
          </Select>
        </div>
        <div>
          <Label>Price from</Label>
          <Input name="priceFrom" type="number" min={1} defaultValue={design?.price_from} required />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {designOptions.map((g) => (
          <div key={g.key}>
            <Label className="text-xs">{g.label}</Label>
            <Select name={g.key} defaultValue={design?.options[g.key] ?? ""}>
              <option value="">Customer chooses</option>
              {g.options.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </Select>
          </div>
        ))}
      </div>
      <div>
        <Label>Description</Label>
        <Textarea name="description" defaultValue={design?.description ?? ""} className="min-h-20" />
      </div>
      <div>
        <Label>Tags</Label>
        <Input name="tags" defaultValue={design?.tags.join(", ")} placeholder="lawn, summer, pastel" />
      </div>
      <div>
        <Label>Photos (up to 4 — the second shows on hover)</Label>
        <input name="photos" type="file" accept="image/*" multiple className="block w-full text-sm text-muted" />
        {design && design.images.length > 0 && <p className="mt-1 text-xs text-muted">Uploading new photos replaces the current {design.images.length}.</p>}
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="featured" defaultChecked={design?.featured} className="accent-[var(--color-plum)]" /> Feature at the top of the Lookbook
      </label>
      <Button type="submit">{design ? "Save changes" : "Add design"}</Button>
    </ActionForm>
  );
}

export default async function DesignsAdminPage() {
  await getStaff();
  const designs = await getDesignsAdmin();
  return (
    <>
      <PageTitle title="Lookbook designs" sub="Each design opens the order form with its options pre-selected. Use real photos of suits you have stitched." />
      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <Panel title={`Designs (${designs.filter((d) => d.is_active).length} live)`}>
          {designs.length === 0 ? (
            <Empty>No designs yet — add your first look.</Empty>
          ) : (
            <ul className="grid gap-5 sm:grid-cols-2">
              {designs.map((d) => (
                <li key={d.id} className={d.is_active ? "" : "opacity-50"}>
                  <div className="aspect-[4/5] overflow-hidden rounded-[var(--radius-md)]">
                    <MediaImage src={d.image_url} alt={d.title} sizes="300px" />
                  </div>
                  <p className="mt-2 font-semibold">{d.title}</p>
                  <p className="text-xs text-muted">
                    <span className="capitalize">{d.occasion}</span> · from {rs(d.price_from)} {d.featured && <Badge value="featured" />}
                  </p>
                  <div className="mt-2 flex gap-2">
                    <details className="flex-1">
                      <summary className="cursor-pointer text-sm text-plum">Edit</summary>
                      <div className="mt-3">
                        <DesignForm design={d} />
                      </div>
                    </details>
                    <ActionButton action={setDesignActive.bind(null, d.id, !d.is_active)} success={d.is_active ? "Hidden from Lookbook" : "Live on Lookbook"} variant="ghost">
                      {d.is_active ? "Hide" : "Show"}
                    </ActionButton>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Add a design">
          <DesignForm />
        </Panel>
      </div>
    </>
  );
}
