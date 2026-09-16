// Faz 48 — `guacamole-common-js` (Apache-2.0) resmi bir TypeScript
// tip tanımı yayınlamıyor. Tam bir tip seti burada elle YAZILMADI
// (bakımı külfetli, API yüzeyi geniş) — yalnızca `any` tipinde bir
// varsayılan export bildirilip kullanım noktalarında (`components/
// GuacamoleRdpViewer.tsx`) gerekli alanlara dar tip daraltmaları
// yapılıyor.
declare module "guacamole-common-js" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const Guacamole: any;
  export default Guacamole;
}
