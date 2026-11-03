"use client";

/**
 * Downscales phone photos (often 4–8 MB) to ~1600px JPEGs before upload so
 * forms stay fast on mobile data and under the server request limit.
 * PDFs and small images pass through untouched.
 */
export async function compressImage(file: File, maxSize = 1600, quality = 0.82): Promise<File> {
  if (!file.type.startsWith("image/") || file.type === "image/gif" || file.size < 400_000) return file;
  try {
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, maxSize / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
    if (!blob || blob.size >= file.size) return file;
    return new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch {
    return file; // unsupported format (e.g. HEIC on some browsers) — upload as is
  }
}

/** Returns a copy of the form data with every image file compressed. */
export async function compressFormData(formData: FormData): Promise<FormData> {
  const out = new FormData();
  for (const [key, value] of formData.entries()) {
    out.append(key, value instanceof File && value.size > 0 ? await compressImage(value) : value);
  }
  return out;
}
