import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Laraib Creative — Ladies Tailoring Lahore",
    short_name: "Laraib",
    description: "Premium ladies suit stitching in Lahore with doorstep pickup, saved measurements and live order tracking.",
    start_url: "/",
    scope: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#f7f1e8",
    theme_color: "#3b1f2b",
    lang: "en-PK",
    categories: ["shopping", "lifestyle", "business"],
    icons: [
      { src: "/brand-icon/192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/brand-icon/512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/brand-icon/maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    shortcuts: [
      { name: "Start an order", url: "/order", icons: [{ src: "/brand-icon/96.png", sizes: "96x96" }] },
      { name: "Track my order", url: "/track", icons: [{ src: "/brand-icon/96.png", sizes: "96x96" }] },
      { name: "Rider app", url: "/rider", icons: [{ src: "/brand-icon/96.png", sizes: "96x96" }] },
    ],
  };
}
