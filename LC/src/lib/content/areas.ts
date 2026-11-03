// Local landing pages ("ladies tailor in <area>"). Each carries area-specific
// service details so the pages are genuinely useful, not keyword copies.

export type Area = {
  slug: string;
  name: string;
  zone: "A" | "B" | "C";
  distanceKm: string;
  pickupDays: string;
  sectors: string[];
  intro: string;
  popular: string[];
};

export const areas: Area[] = [
  {
    slug: "gulberg",
    name: "Gulberg",
    zone: "A",
    distanceKm: "6–9",
    pickupDays: "Daily, same-day slots",
    sectors: ["Gulberg I", "Gulberg II", "Gulberg III", "Gulberg IV", "Gulberg V", "MM Alam Road", "Main Boulevard"],
    intro:
      "Gulberg is one of our busiest pickup areas — working women who want office-ready kurtas and evening wear without a weekend trip to the tailor. Our riders cover every block daily.",
    popular: ["Designer suits for office", "Party wear", "Express 48-hour stitching"],
  },
  {
    slug: "dha-lahore",
    name: "DHA Lahore",
    zone: "B",
    distanceKm: "10–18",
    pickupDays: "Daily for Phases 1–6; Phases 7–9 on Tuesdays & Fridays",
    sectors: ["Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5", "Phase 6", "Phase 7", "Phase 8", "Phase 9 Town"],
    intro:
      "From formal dinners to wedding season, DHA customers order more party and formal wear than anywhere else in Lahore. We collect your fabric in a sealed, QR-tagged bag and return it stitched on the date we promise.",
    popular: ["Formal & party wear", "Maxi and frocks", "Home measurement visits"],
  },
  {
    slug: "cantt",
    name: "Lahore Cantt",
    zone: "A",
    distanceKm: "5–8",
    pickupDays: "Daily, same-day slots",
    sectors: ["Saddar", "Cavalry Ground", "Sarwar Road", "Walton Road", "Defence Road"],
    intro: "Cantt is minutes from our Garhi Shahu workshop, so pickups are quick and same-day slots are almost always available.",
    popular: ["Everyday lawn suits", "Kurtis", "Alterations"],
  },
  {
    slug: "askari",
    name: "Askari Lahore",
    zone: "B",
    distanceKm: "8–12",
    pickupDays: "Daily slots",
    sectors: ["Askari 10", "Askari 11", "Askari 9", "Askari 5"],
    intro: "Our riders pick up from Askari societies every day — let your gate know a Laraib rider is coming, and ask for a female measurer for home visits.",
    popular: ["Family orders", "Eid suits", "Home measurement visits"],
  },
  {
    slug: "model-town",
    name: "Model Town",
    zone: "B",
    distanceKm: "9–12",
    pickupDays: "Daily slots",
    sectors: ["Blocks A–R", "Model Town Extension", "Faisal Town", "Garden Town"],
    intro: "Model Town and Garden Town families often order for the whole household — save a measurement profile for each person and re-order in two taps.",
    popular: ["Family & wedding orders", "Simple suits", "Saved measurement profiles"],
  },
  {
    slug: "shadman",
    name: "Shadman & GOR",
    zone: "A",
    distanceKm: "3–5",
    pickupDays: "Daily, same-day slots",
    sectors: ["Shadman I", "Shadman II", "GOR-I", "Upper Mall", "Zaman Park", "Aitchison area"],
    intro: "Our closest neighbourhoods. Drop your fabric at the studio near Railway Headquarters, or let a rider collect it the same day.",
    popular: ["Designer suits", "Express stitching", "Studio drop-off"],
  },
  {
    slug: "johar-town",
    name: "Johar Town",
    zone: "C",
    distanceKm: "14–20",
    pickupDays: "Tuesdays & Fridays",
    sectors: ["Phase 1", "Phase 2", "Wapda Town", "EME", "Valencia"],
    intro: "Pickups run on fixed days so one rider can cover the whole area. Book a Tuesday or Friday slot at checkout.",
    popular: ["Student & office wear", "Kurtis", "Eid bookings"],
  },
  {
    slug: "bahria-town",
    name: "Bahria Town Lahore",
    zone: "C",
    distanceKm: "25–30",
    pickupDays: "Tuesdays & Fridays",
    sectors: ["Sector B", "Sector C", "Sector D", "Sector E", "Overseas Enclave", "Bahria Orchard"],
    intro: "Bahria Town is on our fixed-day route. Pickup and delivery are free on larger orders, and Express stitching is available.",
    popular: ["Party & formal wear", "Bridal consultations", "Free pickup on larger orders"],
  },
];
