import { whatsappLink } from '@/data/site';
import { WhatsappIcon } from '@/components/ui/BrandIcons';

export default function FloatingContact() {
  return (
    <a
      href={whatsappLink()}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Chat with MTK Codex on WhatsApp"
      className="fixed bottom-5 right-5 z-40 grid size-14 place-items-center rounded-full bg-[#25d366] text-white shadow-[0_12px_32px_-8px_rgba(37,211,102,0.7)] transition hover:scale-105"
    >
      <WhatsappIcon className="size-7" />
    </a>
  );
}
