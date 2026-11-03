// Style Journal — original, practical articles. Each section is a heading + paragraphs.

export type Article = {
  slug: string;
  title: string;
  excerpt: string;
  category: string;
  published: string; // ISO date
  readMinutes: number;
  sections: { heading: string; body: string[] }[];
};

export const articles: Article[] = [
  {
    slug: "how-to-measure-for-a-shalwar-kameez",
    title: "How to measure yourself for a perfect shalwar kameez",
    excerpt: "Seven measurements, one tape and ten minutes — the method our master tailors use, explained for home.",
    category: "Fit guide",
    published: "2026-10-20",
    readMinutes: 6,
    sections: [
      {
        heading: "Before you start",
        body: [
          "Use a soft tailoring tape, not a metal one, and measure over a thin layer of clothing — ideally the kind of fabric you plan to stitch. Stand naturally with your arms relaxed. Asking someone to help gives far more accurate results than measuring alone, especially for shoulder and sleeve length.",
          "Write each number down in inches as you go. If you are between two marks, take the larger one: a tailor can always take a seam in, but cannot add fabric that was never there.",
        ],
      },
      {
        heading: "Chest, waist and hip",
        body: [
          "Chest: wrap the tape around the fullest part of the bust, keeping it level across your back. Waist: measure at the natural waistline — the narrowest point, usually just above the navel. Hip: measure around the fullest part of the hips, about 7–8 inches below the waist.",
          "Keep one finger between the tape and your body. This is not ease (the tailor adds that based on the fit you choose) — it simply stops the tape from being pulled too tight.",
        ],
      },
      {
        heading: "Shoulder, sleeve and armhole",
        body: [
          "Shoulder: measure across the back from the tip of one shoulder bone to the other. Sleeve: from the shoulder tip down to where you want the sleeve to end — wrist for full sleeves, mid-forearm for three-quarter. Armhole: loop the tape around the top of your arm where it meets the shoulder, snug but comfortable.",
          "Armhole is the measurement most people skip, and the most common reason a kameez feels tight when you lift your arms.",
        ],
      },
      {
        heading: "Lengths",
        body: [
          "Shirt length: from the highest point of the shoulder (next to the neck) down to where you want the hem. For a trouser or shalwar, measure from the waist to the ankle bone, then decide on the bottom width (pancha) — around 14–16 inches for straight trousers, wider for shalwar.",
        ],
      },
      {
        heading: "When in doubt, copy a suit that already fits",
        body: [
          "The most reliable measurement is often a suit you already love wearing. Send it with your fabric and our tailor will measure the garment itself and copy the fit — then return it with your order. You can also book a home measurement visit if you are in Lahore.",
        ],
      },
    ],
  },
  {
    slug: "eid-stitching-timeline",
    title: "The Eid stitching timeline: when to send your fabric",
    excerpt: "Tailors fill up weeks before Eid. Here is a realistic calendar so your suit is ready before chaand raat.",
    category: "Planning",
    published: "2026-10-28",
    readMinutes: 4,
    sections: [
      {
        heading: "Why Eid orders get late",
        body: [
          "Every tailor in Lahore receives most of their Eid orders in the same three weeks. Workshops take on more than they can stitch, and the suits that slip are always the ones that arrived last. The fix is simple: book early, and choose a tailor who stops accepting orders once they are full.",
        ],
      },
      {
        heading: "A practical calendar",
        body: [
          "Five to six weeks before Eid: send formal and party wear, anything with lining, cancan or heavy embellishment. Four weeks before: everyday Eid suits and family orders. Two to three weeks before: last standard bookings — after this, rely on Priority or Express stitching where it is still available.",
          "At Laraib Creative the checkout calendar only offers delivery dates the workshop can actually meet. When the Eid capacity is full, booking closes rather than accepting orders we would deliver late.",
        ],
      },
      {
        heading: "Save time on measurements",
        body: [
          "If you have ordered before, choose your saved measurement profile. If not, send a suit that fits well along with your fabric, so nothing has to wait for a fitting appointment.",
        ],
      },
    ],
  },
  {
    slug: "choosing-a-neckline",
    title: "Choosing a neckline for your kameez",
    excerpt: "Round, V, boat, sweetheart or band collar? How each neckline frames the face and works with different fabrics.",
    category: "Design",
    published: "2026-11-01",
    readMinutes: 5,
    sections: [
      {
        heading: "Round and V-neck: the everyday pair",
        body: [
          "A round neck is the most versatile choice for lawn and cotton — it sits comfortably, frames embroidery well and suits almost every face shape. A V-neck lengthens the neck and works beautifully on printed fabrics because it breaks up a busy pattern vertically.",
        ],
      },
      {
        heading: "Boat and band collar: clean and modern",
        body: [
          "A boat neckline runs wide and shallow from shoulder to shoulder. It looks elegant in solid colours and structured fabrics like cotton silk. A band collar (mandarin) is crisp and formal — a strong choice for office wear and for khaddar in winter.",
        ],
      },
      {
        heading: "Sweetheart and keyhole: for evenings",
        body: [
          "Sweetheart necklines suit chiffon and organza party wear, especially with lining. A keyhole adds a small opening at the front or back and pairs well with potli buttons or a tassel tie. Both need careful finishing, so allow a little more stitching time.",
        ],
      },
      {
        heading: "Let the fabric decide",
        body: [
          "If your fabric already has a heavy embroidered neckline panel, follow its shape rather than fighting it. Upload a photo of the fabric when you order and our tailor will suggest the neckline that uses the embroidery best.",
        ],
      },
    ],
  },
  {
    slug: "caring-for-lawn-and-chiffon",
    title: "Caring for lawn, chiffon and khaddar suits",
    excerpt: "Washing, ironing and storage tips that keep colours bright and stitching strong for years.",
    category: "Care",
    published: "2026-11-02",
    readMinutes: 4,
    sections: [
      {
        heading: "Lawn and cotton",
        body: [
          "Wash dark and printed lawn separately in cold water for the first two washes — that is when most dye runs. Turn suits inside out to protect prints and embroidery, and dry them in the shade. Iron while still slightly damp on the reverse side.",
        ],
      },
      {
        heading: "Chiffon, organza and lined party wear",
        body: [
          "Hand wash gently or dry clean. Never wring chiffon; roll it in a towel to remove water. Lined garments should be steamed rather than pressed flat, so the lining and outer fabric do not shrink differently.",
        ],
      },
      {
        heading: "Khaddar and winter fabrics",
        body: [
          "Khaddar softens beautifully with washing, but can shrink on the first wash. Pre-washing the fabric before stitching avoids a kameez that becomes short after one season — mention it in your order notes and we will advise.",
        ],
      },
      {
        heading: "Storage",
        body: [
          "Store embellished suits folded in cotton bags rather than plastic, which traps moisture. Hang structured kurtas on padded hangers so the shoulders keep their shape.",
        ],
      },
    ],
  },
];
