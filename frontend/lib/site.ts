/** The operator (developer) of this system. Written here once: the About page card and the footer credit read it. */
export const OPERATOR = {
  name: "Mr. Mhechela",
  callsign: "Cratos",
  email: "predatora186@gmail.com",
  phone: "0693 696 717",
  phoneTel: "+255693696717",              // the same number in international form, for the tap-to-call link
  avatar: "/operator/cratos.jpg",
  avatarAlt: "Cratos: a samurai in silhouette against a glowing blue moon",
};

/** Edit these once: they appear in the footer, the About page and the legal pages. */
export const SITE = {
  school: "Amani Girls Secondary School",
  app: "Amani Exams",
  version: "1.0",
  year: 2026,
  updated: "28 October 2026",
  email: OPERATOR.email,                // CHANGE: the school's real contact e-mail
  phone: "+255 693 696 717",            // CHANGE: the school's real phone number
  address: "Amani Girls Secondary School, Tanzania",
  developer: `${OPERATOR.name} (call sign ${OPERATOR.callsign})`,   // the personal credit on the About page
  retention: "while the student is enrolled and for the period the school keeps its academic records",
};
